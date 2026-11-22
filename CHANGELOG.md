# Pantenee changelog

This file records the models and runtime versions used by Pantenee releases so forks can reproduce the setup.

## Unreleased

- Added independent input and output language settings for dictation and typed text, including Simplified Chinese and Roman Urdu.
- Added a text window for editing and copying offline translations and background loading for the text model.
- Improved Windows microphone capture with WASAPI and capped gain for quiet recordings.
- Shortened the Whisper processing window for clear short recordings and added a full-window retry for uncertain results.
- Added spoken-language presets for offline translation into English, removed the voice workflow shortcuts and settings, and improved microphone recording error messages.

### Model and runtime versions

- **Speech recognition and speech-to-English translation:** Whisper Small multilingual (244M parameters), distributed as [Systran/faster-whisper-small at revision `536b0662742c02347bc0e980a01041f333bce120`](https://huggingface.co/Systran/faster-whisper-small/tree/536b0662742c02347bc0e980a01041f333bce120). `model.bin` SHA-256 `3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671`.
- **Optional text translation:** [Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B) using `llama-cpp-python` `0.3.36`. The [GGUF download](https://ollama.com/library/qwen3.5:2b) uses SHA-256 `e8bf47d40c5ba68baf8f3e503ee36710da6e8641cb0a670a508cff5b3f0cfbf7`.
- **Speech runtimes:** Faster Whisper `1.2.1`, CTranslate2 `4.9.0`, Silero VAD v6, and ONNX Runtime `1.32.0`.

## [v0.1.0](https://github.com/ubaid164/Pantenee/releases/tag/v0.1.0) — 2026-11-21

- First Windows x64 preview with hold-to-dictate, the desktop cat, and voice workflow shortcuts.
- The setup ZIP includes the multilingual Whisper Base weights for offline speech recognition.

### Model and runtime versions

- **Speech recognition:** Whisper Base multilingual (74M parameters), distributed as [Systran/faster-whisper-base at revision `ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`](https://huggingface.co/Systran/faster-whisper-base/tree/ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66).
- **Bundled weight checksum:** `model.bin` SHA-256 `d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9`.
- **Voice activity detection:** Silero VAD v6 bundled with Faster Whisper `1.2.1`.
- **Inference runtimes:** CTranslate2 `4.9.0` for Whisper and ONNX Runtime `1.32.0` for Silero VAD.
