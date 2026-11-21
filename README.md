# Pantenee

Pantenee is a Windows desktop cat for offline dictation and translation. It follows your cursor, shows when it’s listening, and stays out of the way of clicks and typing.

## Run Pantenee

Use **Windows 11 x64** with a working microphone. A four-core Intel or AMD CPU, **8 GB RAM**, and **2 GB of free space** are a practical starting point. Pantenee runs on the CPU. The current build targets x64 Windows.

1. Download `Pantenee-Setup.zip` and extract the entire ZIP. [Releases](https://github.com/ubaid164/Pantenee/releases)
2. Install 64-bit Python 3.12 with Tkinter. Open `Run with Python.cmd` and wait for **Ready**. Keep `model` beside the launcher.
3. Click a text field, hold **Left Ctrl**, speak, and release to type.

The launcher installs dependencies on its first run. The downloaded ZIP includes the speech model for offline inference.

To speak one language and type English, open **Settings → Dictation output** and pick a language such as **Chinese (Mandarin) → English**, **Spanish → English**, or **Urdu → English**. Choose **Auto-detect → English** to let Whisper pick the language for each recording. Hold your dictation key, speak, and release to type the translation. Select **As spoken** for output in the original language. Translation uses the bundled model offline.

Settings live in `%LOCALAPPDATA%\Pantenee`. In **Settings**, choose the dictation key, pet behavior, and whether **Enter** follows a transcript.

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

The build downloads and verifies the pinned Whisper model and writes `dist/Pantenee-Windows-x64.zip` for local testing. That standalone executable is unsigned. Run from source with `python pantenee.py`. The first source launch may download the model if `model/` is absent.

GitHub Actions builds and exercises transcription on a Windows x64 runner. A `v*` tag publishes a preview with the Python launcher and bundled model after the tests pass. Before marking a release as stable, try the ZIP on a separate Windows PC. Check microphone access, Left Ctrl dictation and translation into Notepad, and the cat’s click-through behavior. Keep generated files and local settings out of Git.
