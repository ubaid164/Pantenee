# Pantenee

Pantenee is a Windows desktop cat for offline dictation and a few local voice workflows. It follows your cursor, shows when it’s listening, and stays out of the way of clicks and typing.

## Run Pantenee

Use **Windows 11 x64** with a working microphone. A four-core Intel or AMD CPU, **8 GB RAM**, and **2 GB of free space** are a practical starting point. Pantenee runs on the CPU. The current build targets x64 Windows.

1. Download `Pantenee-Windows-x64.zip` from **Releases** and extract the entire ZIP.
2. Open `Pantenee.exe` and wait for **Ready**. Keep `_internal` and `model` beside the executable.
3. Click a text field, hold **Left Ctrl**, speak, and release to type.

The executable is unsigned. If your Windows policy blocks it, open `Run with Python.cmd` using an approved 64-bit Python 3.12 installation with Tkinter. The Python launcher installs dependencies on its first run. The downloaded ZIP includes the speech model.

## Voice workflows

Hold **Right Ctrl**, say a configured phrase, and release. Open **Workflows** to set each phrase in the language you speak and choose your work apps. If **Right Ctrl** is your dictation key, **Left Ctrl** takes over for workflows.

| Default phrase | Action |
| --- | --- |
| `Open Downloads` | Opens the Windows Downloads folder. |
| `Open work apps` | Opens the apps or shortcuts you selected. |
| `Open daily note` | Creates or opens today’s text note. An existing note keeps its contents. |

The workflow hotkey matches transcripts to those three actions. Ordinary dictation types text into the focused field. Settings and daily notes live in `%LOCALAPPDATA%\Pantenee`. In **Settings**, choose the dictation key, pet behavior, and whether **Enter** follows a transcript.

## Models and privacy

Pantenee uses multilingual **Whisper Base** (74M parameters) through Faster Whisper and **Silero VAD v6** to filter silence. It detects the spoken language automatically and uses CPU INT8 where the runtime supports it. Speech inference runs locally. Recordings and the last transcript live in memory during a session. [Model and dependency credits](THIRD_PARTY.md)

## Develop or build on Windows

Use 64-bit Python 3.12 with Tkinter.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools\build_release.py
```

The build downloads and verifies the pinned Whisper model and writes `dist/Pantenee-Windows-x64.zip`. Run from source with `python pantenee.py`. The first source launch may download the model if `model/` is absent.

GitHub Actions builds and exercises transcription on a Windows x64 runner. Before tagging a public release, try the ZIP on a separate Windows PC. Check microphone access, Left Ctrl dictation into Notepad, the workflow hotkey, and the cat’s click-through behavior. Use Releases for the ZIP and keep generated files and local settings out of Git.
