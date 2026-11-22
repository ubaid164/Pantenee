# Pantenee

Pantenee is a Windows desktop cat for offline dictation and translation. It follows your cursor, shows when it’s listening, and stays out of the way of clicks and typing.

[Changelog and model versions](CHANGELOG.md)

## Run Pantenee

Use **Windows 11 x64** with a working microphone. A four-core Intel or AMD CPU, **8 GB RAM**, and **2 GB of free space** are a practical starting point. Pantenee runs on the CPU. The current build targets x64 Windows.

1. Download `Pantenee-Setup.zip` and extract the entire ZIP. [Releases](https://github.com/ubaid164/Pantenee/releases)
2. Install 64-bit Python 3.12 with Tkinter. Open `Run with Python.cmd` and wait for **Ready**. Keep `model` beside the launcher.
3. Click a text field, hold **Left Ctrl**, speak when Pantenee shows **Listening**, and release to type.

The launcher installs dependencies on its first run. The downloaded ZIP includes the speech model for offline inference.

Open **Settings** and choose **Input language** and **Output language**. **Auto-detect** guesses the input language, and **Same as input** keeps dictation in the spoken language. Hold your dictation key, speak, and release to type the result. For example, choose **Roman Urdu** and **Chinese (Simplified)** to speak Urdu and type Chinese, or choose **Chinese (Simplified)** and **Roman Urdu** to type Urdu in Latin letters. Choose **Roman Urdu** with **Same as input** to dictate Urdu in Latin letters.

Click **Translate text** to type or paste text, translate it, and edit the result before copying it. This window shares the language settings with dictation. Pick **Roman Urdu** as the input when you have typed Urdu in Latin letters.

Speech-to-English translation uses the bundled Whisper model. For typed translation and translated speech in other output languages, run **Set up translation.cmd** once, then start **Run with Python.cmd**. Setup needs an internet connection to install the CPU runtime and download the 2 GB Qwen3.5 model. Allow 3 GB of additional disk space. A PC with 16 GB RAM is recommended when using both models. After setup, translation runs offline. Use short sentences for quicker results and check the translation before submitting important text. Roman Urdu spellings vary.

Settings live in `%LOCALAPPDATA%\Pantenee`. In **Settings**, choose the dictation key, pet behavior, and whether **Enter** follows a transcript.

For Urdu speech with English output, choose **Roman Urdu** as the input and **English** as the output. This tells Whisper which language you are speaking. If Pantenee reports that it heard no speech, check the default input and input volume in **Windows Settings → System → Sound**.

## Models and privacy

Pantenee uses multilingual **Whisper Small** (244M parameters) through Faster Whisper and **Silero VAD v6** to filter silence. It uses CPU INT8 where the runtime supports it. On Windows, it prefers WASAPI for the default microphone when the same device is available and applies a capped gain to quiet recordings. Speech inference runs locally. Recordings and the last transcript live in memory during a session. [Model and dependency credits](THIRD_PARTY.md)

For short recordings, Pantenee skips most of Whisper's zero padding. It retries with the full window when the short pass is uncertain. If the selected language pair needs the text model, Pantenee loads it in the background so it is ready for the first translation.

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
