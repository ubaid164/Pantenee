# Pantenee changelog

This file records the models and runtime versions used by Pantenee releases so forks can reproduce the setup.

## Unreleased

- Added spoken-language presets for offline translation into English.
- Removed the voice workflow shortcuts and settings.
- Improved error reporting when Pantenee cannot prepare a microphone recording.
- Model and runtime pins are the same as in v0.1.0.

## [v0.1.0](https://github.com/ubaid164/Pantenee/releases/tag/v0.1.0) — 2026-11-21

- First Windows x64 preview with hold-to-dictate, the desktop cat, and voice workflow shortcuts.
- The setup ZIP includes the multilingual Whisper Base weights for offline speech recognition.

### Model and runtime versions

- **Speech recognition:** Whisper Base multilingual (74M parameters), distributed as [Systran/faster-whisper-base at revision `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`](https://huggingface.co/Systran/faster-whisper-base/tree/ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66).
- **Bundled weight checksum:** `model.bin` SHA-256 `d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9`.
- **Voice activity detection:** Silero VAD v6 bundled with Faster Whisper `1.2.1`.
- **Inference runtimes:** CTranslate2 `4.9.0` for Whisper and ONNX Runtime `1.32.0` for Silero VAD.
