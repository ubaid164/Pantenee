"""Local actions selected by explicitly configured, spoken phrases."""

import ctypes as c
import logging
import os
import unicodedata
import uuid
from ctypes import wintypes as w
from datetime import date
from pathlib import Path

from win_input import bind


DEFAULT_PHRASES = {
    "downloads": "open downloads",
    "apps": "open work apps",
    "note": "open daily note",
}
LABELS = {"downloads": "Open Downloads", "apps": "Open work apps", "note": "Open daily note"}
APP_EXTENSIONS = {".exe", ".lnk"}


def normalize_phrase(text):
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join("".join(" " if unicodedata.category(ch).startswith(("P", "Z")) else ch
                            for ch in text if unicodedata.category(ch) != "Cf").split())


def match_phrase(text, phrases):
    phrase = normalize_phrase(text)
    matches = [action for action, spoken in phrases.items() if normalize_phrase(spoken) == phrase]
    return matches[0] if phrase and len(matches) == 1 else None


def downloads_folder():
    guid_type = c.c_ubyte * 16
    folder_id = guid_type.from_buffer_copy(uuid.UUID("374de290-123f-4565-9164-39c4925e467b").bytes_le)
    find = bind(c.WinDLL("shell32"), "SHGetKnownFolderPath", w.LONG, c.POINTER(guid_type),
                w.DWORD, w.HANDLE, c.POINTER(w.LPWSTR))
    free = bind(c.WinDLL("ole32"), "CoTaskMemFree", None, w.LPVOID)
    path = w.LPWSTR()
    try:
        if find(c.byref(folder_id), 0, None, c.byref(path)) < 0 or not path.value:
            raise OSError("Windows could not locate the Downloads folder.")
        return Path(path.value)
    finally:
        free(c.cast(path, c.c_void_p))


def run_workflow(action, app_paths, notes_folder):
    if action == "downloads":
        os.startfile(downloads_folder())
        return "Opened Downloads"
    if action == "note":
        today = date.today().isoformat()
        notes_folder.mkdir(parents=True, exist_ok=True)
        note = notes_folder / f"{today}.txt"
        try:
            with note.open("x", encoding="utf-8") as file:
                file.write(f"{today}\n\nPriorities\n\nNotes\n")
        except FileExistsError:
            pass
        os.startfile(note)
        return "Opened today’s note"
    if action != "apps":
        raise ValueError(f"Unknown workflow: {action}")
    if not app_paths:
        raise ValueError("Choose your work apps in Workflows first.")

    paths = [Path(path) for path in app_paths]
    if any(not path.is_absolute() or path.suffix.lower() not in APP_EXTENSIONS
           or not path.is_file() for path in paths):
        raise ValueError("A work app is missing. Update your list in Workflows.")
    failures = 0
    for path in paths:
        try:
            os.startfile(path)
        except OSError:
            logging.exception("Could not open a configured work app")
            failures += 1
    if failures:
        raise ValueError(f"Opened {len(paths) - failures} work apps. Couldn’t launch {failures}.")
    return f"Opened {len(paths)} work {'app' if len(paths) == 1 else 'apps'}"
