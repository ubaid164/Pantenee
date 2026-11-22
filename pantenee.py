"""Compact Windows controls for local push-to-talk dictation."""

import ctypes as c
import json
import logging
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, SimpleQueue
from tkinter import messagebox, ttk

from desktop_pet import PET_MODES, Cat, CursorPet, animations_enabled
from speech import SpeechRequest, SpeechWorker, check_model
from translation import LANGUAGES, MODEL_FILENAME, LocalTranslator, TranslationError
from win_input import HOTKEYS, HoldKey, close_handle, create_mutex, insert_text


APP_NAME = "Pantenee"
DATA_OVERRIDE = os.environ.get("PANTENEE_DATA_DIR")
APP_DATA = Path(DATA_OVERRIDE) if DATA_OVERRIDE else Path(os.environ["LOCALAPPDATA"]) / APP_NAME
SETTINGS = APP_DATA / "settings.json"
APP_FOLDER = Path(sys.executable if getattr(sys, "frozen", False) else __file__).parent
MODEL_DIR = Path(os.environ.get("PANTENEE_MODEL_DIR") or APP_FOLDER / "model")
TRANSLATION_MODEL = Path(os.environ.get("PANTENEE_TRANSLATION_MODEL") or
                         APP_DATA / "translation" / MODEL_FILENAME)
MIN_HOLD = 0.28
SOURCE_NAMES = {"auto": "Auto-detect", **LANGUAGES}
TARGET_NAMES = {"same": "Same as input", **LANGUAGES}
SOURCE_CODES = {name: code for code, name in SOURCE_NAMES.items()}
TARGET_CODES = {name: code for code, name in TARGET_NAMES.items()}
PREVIOUS_SOURCES = {**SOURCE_CODES, "Chinese (Mandarin)": "zh", "Urdu": "ur"}
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
        legacy_default = "Urdu → English" if data.get("translate_urdu") is True else "As spoken"
        old_output = data.get("dictation_output", legacy_default)
        old_source = (PREVIOUS_SOURCES.get(old_output.removesuffix(" → English"))
                      if isinstance(old_output, str) and old_output.endswith(" → English") else None)
        source = data.get("source_language", old_source or "auto")
        target = data.get("target_language", "en" if old_source is not None else "same")
        return (key if key in HOTKEYS else "Left Ctrl", data.get("enter") is True,
                pet if pet in PET_MODES else default_pet,
                source if isinstance(source, str) and source in SOURCE_NAMES else "auto",
                target if isinstance(target, str) and target in TARGET_NAMES else "same")
    except FileNotFoundError:
        pass
    except (OSError, ValueError, AttributeError, TypeError):
        logging.exception("Settings could not be read")
    return "Left Ctrl", False, default_pet, "auto", "same"


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
        self.speech_request = SpeechRequest()
        self.translator = LocalTranslator(TRANSLATION_MODEL)
        self.text_window = None
        self.text_busy = False

        animate = animations_enabled()
        key, enter, pet, source, target = load_settings(
            "Follow cursor" if animate else "While dictating")
        self.key = tk.StringVar(value=key)
        self.enter = tk.BooleanVar(value=enter)
        self.pet_mode = tk.StringVar(value=pet)
        self.source = tk.StringVar(value=SOURCE_NAMES[source])
        self.output = tk.StringVar(value=TARGET_NAMES[target])
        self.help = tk.StringVar()
        initial_status = ("Loading the local Whisper model…" if MODEL_DIR.is_dir()
                          else "Loading Whisper… The first run may download the model.")
        self.status = tk.StringVar(value=initial_status)
        self.hook = HoldKey(self.events, HOTKEYS[key])
        preview = self.build_window()
        self.pet = CursorPet(root, preview, animate)
        self.pet.set_mode(pet)
        self.hook.start()
        SpeechWorker(self.commands, self.events, MODEL_DIR, APP_DATA / "models", self.translator).start()
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
        ttk.Button(actions, text="Translate text", command=self.open_text_window,
                   style="Pet.TButton").pack(side="left", padx=(6, 0))
        self.copy_button = ttk.Button(actions, text="Copy transcript", command=self.copy,
                                      state="disabled", style="Pet.TButton")
        self.copy_button.pack(side="right")

        self.options = ttk.Frame(content, padding=(0, 12, 0, 0), style="Pet.TFrame")
        self.options.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.options.columnconfigure(1, weight=1)
        for row, (label, variable, values) in enumerate((("Hold key", self.key, tuple(HOTKEYS)),
                                                        ("Input language", self.source, tuple(SOURCE_CODES)),
                                                        ("Output language", self.output, tuple(TARGET_CODES)),
                                                        ("Pantenee pet", self.pet_mode, PET_MODES))):
            self.choice_picker(self.options, row, label, variable, values)
        ttk.Checkbutton(self.options, text="Press Enter after typing", variable=self.enter,
                        command=self.change_settings, style="Pet.TCheckbutton").grid(
                            row=4, column=0, columnspan=2, sticky="w", pady=(3, 0))
        self.options.grid_remove()
        return preview

    def choice_picker(self, parent, row, label, variable, values):
        ttk.Label(parent, text=label, style="Pet.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 10))
        picker = ttk.Combobox(parent, textvariable=variable, values=values,
                              width=21, state="readonly", style="Pet.TCombobox")
        picker.grid(row=row, column=1, sticky="ew", pady=3)
        picker.bind("<<ComboboxSelected>>", self.change_settings)

    def open_text_window(self):
        if self.text_window:
            self.text_window.deiconify()
            self.text_window.lift()
            self.text_input.focus_set()
            return

        self.text_window = tk.Toplevel(self.root)
        self.text_window.title("Pantenee · Translate text")
        self.text_window.protocol("WM_DELETE_WINDOW", self.text_window.withdraw)
        panel = ttk.Frame(self.text_window, padding=16, style="Pet.TFrame")
        panel.pack(fill="both", expand=True)
        panel.columnconfigure(1, weight=1)
        self.choice_picker(panel, 0, "Input language", self.source, tuple(SOURCE_CODES))
        self.choice_picker(panel, 1, "Output language", self.output, tuple(TARGET_CODES))
        for row, label in ((2, "Text to translate"), (4, "Translation")):
            ttk.Label(panel, text=label, style="Pet.TLabel").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(10, 3))
        text_style = dict(width=44, height=5, wrap="word", font=("Segoe UI", 11), padx=6, pady=6,
                          bg="white", fg=TEXT, borderwidth=1, relief="solid")
        self.text_input = tk.Text(panel, **text_style)
        self.text_input.grid(row=3, column=0, columnspan=2, sticky="nsew")
        self.text_output = tk.Text(panel, state="disabled", **text_style)
        self.text_output.grid(row=5, column=0, columnspan=2, sticky="nsew")
        panel.rowconfigure(3, weight=1)
        panel.rowconfigure(5, weight=1)
        self.text_status = tk.StringVar()
        ttk.Label(panel, textvariable=self.text_status, wraplength=310, style="Quiet.Pet.TLabel").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(5, 0))
        self.translate_button = ttk.Button(panel, text="Translate", command=self.translate_text,
                                           style="Pet.TButton")
        self.translate_button.grid(row=7, column=0, sticky="w", pady=(7, 0))
        self.copy_translation = ttk.Button(panel, text="Copy translation", command=self.copy_text_translation,
                                           state="disabled", style="Pet.TButton")
        self.copy_translation.grid(row=7, column=1, sticky="e", pady=(7, 0))
        self.text_input.focus_set()

    def translate_text(self):
        text = self.text_input.get("1.0", "end-1c").strip()
        if not text or self.text_busy:
            return
        source = SOURCE_CODES[self.source.get()]
        target = TARGET_CODES[self.output.get()]
        if target == "same":
            self.text_status.set("Choose an output language to translate.")
            return
        self.set_text_translation("")
        self.text_busy = True
        self.translate_button.configure(state="disabled")
        self.text_status.set("Translating locally…")
        threading.Thread(target=self.run_text_translation, args=(text, source, target),
                         daemon=True, name="Text translation").start()

    def run_text_translation(self, text, source, target):
        try:
            translated = self.translator.translate(text, source, target)
        except TranslationError as error:
            self.events.put(("text_translation_error", str(error)))
        except Exception as error:
            logging.error("Text translation failed (%s)", type(error).__name__)
            self.events.put(("text_translation_error", "Translation failed. Check the app log."))
        else:
            self.events.put(("text_translation", (translated, TARGET_NAMES[target])))

    def set_text_translation(self, text):
        self.text_output.configure(state="normal")
        self.text_output.delete("1.0", "end")
        self.text_output.insert("1.0", text)
        if not text:
            self.text_output.configure(state="disabled")
        self.copy_translation.configure(state="normal" if text else "disabled")

    def copy_text_translation(self):
        text = self.text_output.get("1.0", "end-1c")
        if not text.strip():
            self.text_status.set("Enter a translation to copy.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.text_status.set("Translation copied")

    def toggle_settings(self):
        if self.options.winfo_manager():
            self.options.grid_remove()
            self.settings_button.configure(text="Settings")
        else:
            self.options.grid()
            self.settings_button.configure(text="Hide settings")

    def update_help(self):
        self.help.set(f"Hold {self.key.get()} and speak when Listening appears. Release to type.")

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
            "source_language": SOURCE_CODES[self.source.get()],
            "target_language": TARGET_CODES[self.output.get()],
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
            request = self.speech_language_request()
            if request.needs_text_translation:
                self.translator.warmup()
            mode = "Offline"
            if request.target != "same":
                mode = f"{SOURCE_NAMES[request.source]} → {TARGET_NAMES[request.target]}"
            self.present(f"Ready · {mode}", "idle")

    def speech_language_request(self):
        source = SOURCE_CODES[self.source.get()]
        target = TARGET_CODES[self.output.get()]
        if source == "ur" and target == "same":
            target = "ur"
        return SpeechRequest(source, target)

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
            self.speech_request = self.speech_language_request()
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
                message = "Translating…" if self.speech_request.whisper_task == "translate" else "Transcribing…"
                self.present(message, "thinking")
                self.commands.put(self.speech_request)
        elif kind == "translating" and self.phase == "processing":
            self.present("Translating locally…", "thinking")
        elif kind in ("text_translation", "text_translation_error"):
            self.text_busy = False
            self.translate_button.configure(state="normal")
            if kind == "text_translation":
                text, language = value
                self.set_text_translation(text)
                self.text_status.set(f"Translated to {language}")
            else:
                self.text_status.set(value)
        elif kind in ("transcript", "discarded", "speech_error"):
            self.phase = None
            self.refresh_ready()
            if kind == "transcript":
                self.deliver(value)
            elif kind == "speech_error":
                self.present(value, "error")

    def deliver(self, text):
        if not text:
            self.present("No speech heard. Check your Windows microphone level and try again.", "error")
            return
        self.last_text = text
        self.copy_button.configure(state="normal")
        if insert_text(text, self.target, self.send_enter):
            self.present("Transcript typed", "done")
        else:
            self.present("Couldn’t type in that field. Use Copy transcript.", "error")

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
