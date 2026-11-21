"""Settings for the three local voice workflows."""

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from workflows import LABELS, normalize_phrase


class WorkflowWindow(tk.Toplevel):
    def __init__(self, parent, phrases, apps, save, hotkey):
        super().__init__(parent)
        self.title("Pantenee Workflows")
        self.transient(parent)
        self.resizable(False, False)
        self.save = save
        self.apps = apps.copy()
        self.fields = {action: tk.StringVar(self, value=phrase)
                       for action, phrase in phrases.items()}
        panel = ttk.Frame(self, padding=16, style="Pet.TFrame")
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text=f"Hold {hotkey} and say a phrase to run its workflow.",
                  style="Pet.TLabel").grid(row=0, columnspan=2, sticky="w")
        ttk.Label(panel, text="Write the phrases in the language you speak.",
                  style="Quiet.Pet.TLabel").grid(row=1, columnspan=2, sticky="w", pady=(0, 10))
        for row, (action, label) in enumerate(LABELS.items(), start=2):
            ttk.Label(panel, text=label, style="Pet.TLabel").grid(row=row, sticky="w", pady=3)
            ttk.Entry(panel, width=31, textvariable=self.fields[action]).grid(
                row=row, column=1, sticky="ew", padx=(10, 0), pady=3)
        ttk.Label(panel, text="Work apps and shortcuts", style="Pet.TLabel").grid(
            row=5, columnspan=2, sticky="w", pady=(10, 4))
        self.app_list = tk.Listbox(panel, height=4, selectmode="extended", exportselection=False)
        self.app_list.grid(row=6, columnspan=2, sticky="ew")
        self.refresh_apps()
        controls = ttk.Frame(panel, style="Pet.TFrame")
        controls.grid(row=7, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(controls, text="Add apps…", command=self.add_apps, style="Pet.TButton").pack(side="left")
        ttk.Button(controls, text="Remove", command=self.remove_apps, style="Pet.TButton").pack(
            side="left", padx=(6, 0))
        ttk.Button(controls, text="Save", command=self.commit, style="Pet.TButton").pack(side="right")
        self.feedback = tk.StringVar(self)
        ttk.Label(panel, textvariable=self.feedback, style="Quiet.Pet.TLabel").grid(
            row=8, columnspan=2, sticky="w", pady=(6, 0))

    def refresh_apps(self):
        self.app_list.delete(0, "end")
        for path in self.apps:
            self.app_list.insert("end", Path(path).name)

    def add_apps(self):
        paths = filedialog.askopenfilenames(parent=self, title="Choose work apps",
                                            filetypes=[("Windows apps and shortcuts", "*.exe *.lnk")])
        known = {os.path.normcase(path) for path in self.apps}
        for path in map(os.path.normpath, paths):
            if os.path.normcase(path) not in known:
                self.apps.append(path)
                known.add(os.path.normcase(path))
        self.refresh_apps()

    def remove_apps(self):
        for index in reversed(self.app_list.curselection()):
            del self.apps[index]
        self.refresh_apps()

    def commit(self):
        phrases = {action: field.get().strip() for action, field in self.fields.items()}
        normalized = {normalize_phrase(phrase) for phrase in phrases.values()}
        if "" in normalized or len(normalized) != len(phrases):
            self.feedback.set("Give each workflow a different spoken phrase.")
        elif self.save(phrases, self.apps):
            self.destroy()
