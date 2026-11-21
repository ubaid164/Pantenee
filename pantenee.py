"""Compact Windows controls for local push-to-talk dictation."""

import ctypes as c
import json
import logging
import os
import sys
import tkinter as tk
from pathlib import Path
from queue import Empty, SimpleQueue
from tkinter import messagebox, ttk

from desktop_pet import PET_MODES, Cat, CursorPet, animations_enabled
from speech import EnglishTranslation, SpeechWorker, check_model
from win_input import HOTKEYS, HoldKey, close_handle, create_mutex, insert_text


APP_NAME = "Pantenee"
DATA_OVERRIDE = os.environ.get("PANTENEE_DATA_DIR")
APP_DATA = Path(DATA_OVERRIDE) if DATA_OVERRIDE else Path(os.environ["LOCALAPPDATA"]) / APP_NAME
SETTINGS = APP_DATA / "settings.json"
APP_FOLDER = Path(sys.executable if getattr(sys, "frozen", False) else __file__).parent
MODEL_DIR = Path(os.environ.get("PANTENEE_MODEL_DIR") or APP_FOLDER / "model")
MIN_HOLD = 0.28
AS_SPOKEN = "As spoken"
URDU_TO_ENGLISH = "Urdu → English"
AUTO_TO_ENGLISH = "Auto-detect → English"
TRANSLATION_LANGUAGES = {
    "Arabic": "ar",
    "Bengali": "bn",
    "Chinese (Mandarin)": "zh",
    "French": "fr",
    "German": "de",
    "Hindi": "hi",
    "Indonesian": "id",
    "Japanese": "ja",
    "Marathi": "mr",
    "Portuguese": "pt",
    "Punjabi": "pa",
    "Russian": "ru",
    "Spanish": "es",
    "Tamil": "ta",
    "Telugu": "te",
    "Turkish": "tr",
    "Urdu": "ur",
    "Vietnamese": "vi",
}
DICTATION_OUTPUTS = {
    AS_SPOKEN: None,
    AUTO_TO_ENGLISH: EnglishTranslation(),
    **{f"{language} → English": EnglishTranslation(code)
       for language, code in TRANSLATION_LANGUAGES.items()},
}
PAPER = "#fff8ee"
TEXT = "#29201b"
MUTED = "#6b5147"
SOFT = "#f5e5d7"
ACCENT = "#9f361f"
STATUS_COLORS = {"loading": MUTED, "idle": "#216655", "opening": ACCENT,
                 "listening": ACCENT, "thinking": "#6c4683", "done": "#216655", "error": ACCENT}


def load_settings(default_pet):
    settings = SETTINGS
    if not DATA_OVERRIDE and not settings.exists():
        settings = Path(os.environ["LOCALAPPDATA"]) / "HoldToDictate" / "settings.json"
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
        key = data.get("key")
        pet = data.get("pet")
        legacy_output = URDU_TO_ENGLISH if data.get("translate_urdu") is True else AS_SPOKEN
        output = data.get("dictation_output", legacy_output)
        return (key if key in HOTKEYS else "Left Ctrl", data.get("enter") is True,
                pet if pet in PET_MODES else default_pet,
                output if isinstance(output, str) and output in DICTATION_OUTPUTS else AS_SPOKEN)
    except FileNotFoundError:
        pass
    except (OSError, ValueError, AttributeError, TypeError):
        logging.exception("Settings could not be read")
    return "Left Ctrl", False, default_pet, AS_SPOKEN


def configure_styles(root):
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure("Pet.TFrame", background=PAPER)
    style.configure("Pet.TLabel", background=PAPER, foreground=TEXT, font=("Segoe UI", 10))
    style.configure("Title.Pet.TLabel", font=("Segoe UI Semibold", 17))
    style.configure("Quiet.Pet.TLabel", foreground=MUTED)
    style.configure("Pet.TButton", background=SOFT, foreground=TEXT,
                    bordercolor="#b79076", focuscolor=ACCENT, focusthickness=2,
                    padding=(11, 6), font=("Segoe UI", 10))
    style.map("Pet.TButton", background=[("disabled", PAPER), ("active", "#f1d7c3")],
              foreground=[("disabled", MUTED)],
              bordercolor=[("disabled", "#e0c8b7"), ("focus", ACCENT)])
    style.configure("Pet.TCheckbutton", background=PAPER, foreground=TEXT,
                    focuscolor=ACCENT, font=("Segoe UI", 10), padding=(0, 4))
    style.map("Pet.TCheckbutton", background=[("active", PAPER)])
    style.configure("Pet.TCombobox", padding=(6, 4), font=("Segoe UI", 10),
                    background=SOFT, bordercolor="#b79076", arrowcolor=TEXT)
    style.map("Pet.TCombobox", fieldbackground=[("readonly", PAPER)],
              bordercolor=[("focus", ACCENT)], foreground=[("readonly", TEXT)])


class DictationApp:
    def __init__(self, root):
        self.root = root
        self.events = SimpleQueue()
        self.commands = SimpleQueue()
        self.model_ready = False
        self.hotkey_ready = False
        self.startup_error = None
        self.phase = None
        self.held_at = 0.0
        self.target = None
        self.send_enter = False
        self.last_text = ""
        self.translation = None

        animate = animations_enabled()
        key, enter, pet, dictation_output = load_settings(
            "Follow cursor" if animate else "While dictating")
        self.key = tk.StringVar(value=key)
        self.enter = tk.BooleanVar(value=enter)
        self.pet_mode = tk.StringVar(value=pet)
        self.dictation_output = tk.StringVar(value=dictation_output)
        self.help = tk.StringVar()
        initial_status = ("Loading the local Whisper model…" if MODEL_DIR.is_dir()
                          else "Loading Whisper… The first run may download the model.")
        self.status = tk.StringVar(value=initial_status)
        self.hook = HoldKey(self.events, HOTKEYS[key])
        preview = self.build_window()
        self.pet = CursorPet(root, preview, animate)
        self.pet.set_mode(pet)
        self.hook.start()
        SpeechWorker(self.commands, self.events, MODEL_DIR, APP_DATA / "models").start()
        self.root.after(20, self.poll)

    def build_window(self):
        self.root.title(APP_NAME)
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.configure(background=PAPER)
        configure_styles(self.root)

        content = ttk.Frame(self.root, padding=(16, 12, 16, 14), style="Pet.TFrame")
        content.pack(fill="both", expand=True)
        content.columnconfigure(1, minsize=246, weight=1)
        preview = Cat(content, PAPER)
        preview.grid(row=0, column=0, rowspan=2, sticky="nw", padx=(0, 10))
        ttk.Label(content, text=APP_NAME, style="Title.Pet.TLabel").grid(row=0, column=1, sticky="sw")
        self.status_label = tk.Label(content, textvariable=self.status, bg=PAPER, fg=MUTED,
                                     font=("Segoe UI Semibold", 10), justify="left", wraplength=240,
                                     padx=0, pady=0)
        self.status_label.grid(row=1, column=1, sticky="nw", pady=(2, 4))
        self.update_help()
        ttk.Label(content, textvariable=self.help, wraplength=326, style="Quiet.Pet.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(5, 10))

        actions = ttk.Frame(content, style="Pet.TFrame")
        actions.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.settings_button = ttk.Button(actions, text="Settings", command=self.toggle_settings,
                                          style="Pet.TButton")
        self.settings_button.pack(side="left")
        self.copy_button = ttk.Button(actions, text="Copy transcript", command=self.copy,
                                      state="disabled", style="Pet.TButton")
        self.copy_button.pack(side="right")

        self.options = ttk.Frame(content, padding=(0, 12, 0, 0), style="Pet.TFrame")
        self.options.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.options.columnconfigure(1, weight=1)
        for row, (label, variable, values) in enumerate((("Hold key", self.key, tuple(HOTKEYS)),
                                                        ("Dictation output", self.dictation_output,
                                                         tuple(DICTATION_OUTPUTS)),
                                                        ("Pantenee pet", self.pet_mode, PET_MODES))):
            ttk.Label(self.options, text=label, style="Pet.TLabel").grid(row=row, column=0, sticky="w")
            picker = ttk.Combobox(self.options, textvariable=variable, values=values,
                                  width=27 if variable is self.dictation_output else 16,
                                  state="readonly", style="Pet.TCombobox")
            picker.grid(row=row, column=1, sticky="e", pady=3)
            picker.bind("<<ComboboxSelected>>", self.change_settings)
        ttk.Checkbutton(self.options, text="Press Enter after typing", variable=self.enter,
                        command=self.change_settings, style="Pet.TCheckbutton").grid(
                            row=3, column=0, columnspan=2, sticky="w", pady=(3, 0))
        self.options.grid_remove()
        return preview

    def toggle_settings(self):
        if self.options.winfo_manager():
            self.options.grid_remove()
            self.settings_button.configure(text="Settings")
        else:
            self.options.grid()
            self.settings_button.configure(text="Hide settings")

    def update_help(self):
        use = "dictate" if self.dictation_output.get() == AS_SPOKEN else "translate to English"
        self.help.set(f"Hold {self.key.get()} to {use}. Release to type.")

    def present(self, message, state):
        self.status.set(message)
        self.status_label.configure(fg=STATUS_COLORS[state])
        self.pet.set_state(state)

    def change_settings(self, _event=None):
        self.hook.key = HOTKEYS[self.key.get()]
        self.update_help()
        self.pet.set_mode(self.pet_mode.get())
        settings = {
            "key": self.key.get(),
            "enter": self.enter.get(),
            "pet": self.pet_mode.get(),
            "dictation_output": self.dictation_output.get(),
        }
        try:
            temporary = SETTINGS.with_suffix(".tmp")
            temporary.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
            temporary.replace(SETTINGS)
        except OSError:
            logging.exception("Settings could not be saved")
            messagebox.showerror(APP_NAME, "Could not save settings to this Windows profile.",
                                 parent=self.root)
        if self.phase is None:
            self.refresh_ready()

    def copy(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_text)
        if self.phase is None:
            self.present("Transcript copied", "done")

    def refresh_ready(self):
        self.hook.enabled = self.model_ready and self.hotkey_ready and self.phase is None
        if self.startup_error:
            self.present(self.startup_error, "error")
        elif self.hook.enabled:
            output = self.dictation_output.get()
            mode = "Offline" if output == AS_SPOKEN else output
            self.present(f"Ready · {mode}", "idle")

    def poll(self):
        while True:
            try:
                kind, value = self.events.get_nowait()
            except Empty:
                break
            self.handle_event(kind, value)
        self.root.after(20, self.poll)

    def handle_event(self, kind, value):
        if kind == "model_ready":
            self.model_ready = True
            logging.info("Whisper model ready")
            self.refresh_ready()
        elif kind == "hotkey_ready":
            self.hotkey_ready = True
            logging.info("Windows hotkey ready")
            self.refresh_ready()
        elif kind in ("model_error", "hotkey_error"):
            self.startup_error = value or "Could not register the global key. Check the app log."
            self.refresh_ready()
        elif kind == "hold" and self.hook.enabled:
            self.held_at, self.target = value
            self.send_enter = self.enter.get()
            self.translation = DICTATION_OUTPUTS[self.dictation_output.get()]
            self.phase = "held"
            self.hook.enabled = False
            self.present("Opening microphone…", "opening")
            self.commands.put("record")
        elif kind == "recording" and self.phase == "held":
            self.present("Listening…", "listening")
        elif kind in ("release", "cancel") and self.phase == "held":
            self.phase = "processing"
            if kind == "cancel" or value[0] - self.held_at < MIN_HOLD:
                self.commands.put("cancel")
            else:
                if value[1] != self.target:
                    self.target = None
                self.present("Translating…" if self.translation else "Transcribing…", "thinking")
                self.commands.put(self.translation or "transcribe")
        elif kind in ("transcript", "discarded", "speech_error"):
            self.phase = None
            self.refresh_ready()
            if kind == "transcript":
                self.deliver(value)
            elif kind == "speech_error":
                self.present(value, "error")

    def deliver(self, text):
        if not text:
            self.present("No speech heard. Hold the key and try again.", "error")
            return
        self.last_text = text
        self.copy_button.configure(state="normal")
        if insert_text(text, self.target, self.send_enter):
            self.present("Transcript typed", "done")
        else:
            self.present("Couldn’t type in that field. Copy the transcript below.", "error")

    def close(self):
        self.hook.close()
        self.commands.put("quit")
        self.root.destroy()


def main():
    mutex = create_mutex(None, False, r"Local\HoldToDictate")
    mutex_error = c.get_last_error()
    if not mutex:
        raise c.WinError(mutex_error)
    try:
        root = tk.Tk()
        if mutex_error == 183:  # ERROR_ALREADY_EXISTS
            root.withdraw()
            messagebox.showinfo(APP_NAME, "Pantenee is already open. Check the taskbar.",
                                parent=root)
            root.destroy()
            return
        APP_DATA.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(filename=APP_DATA / "app.log", encoding="utf-8",
                            level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        DictationApp(root)
        root.mainloop()
    finally:
        close_handle(mutex)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check-model":
        try:
            transcript = check_model(MODEL_DIR, Path(sys.argv[2]))
            if sys.stdout:
                print(transcript)
            sys.exit(0 if transcript else 1)
        except Exception:
            if sys.stderr:
                logging.exception("Offline model check failed")
            sys.exit(1)
    else:
        main()
