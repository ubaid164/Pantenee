"""Capture microphone audio on demand and transcribe it with Faster Whisper."""

import logging
import os
import threading
import wave
from dataclasses import dataclass


WHISPER_RATE = 16000


@dataclass(frozen=True)
class EnglishTranslation:
    source_language: str | None = None


def pcm_samples(data, rate):
    import av
    import numpy as np

    samples = np.frombuffer(data, dtype=np.int16)
    if rate == WHISPER_RATE:
        return samples.astype(np.float32) / 32768.0

    frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
    frame.sample_rate = rate
    resampler = av.AudioResampler(format="flt", layout="mono", rate=WHISPER_RATE)
    frames = resampler.resample(frame) + resampler.resample(None)
    if not frames:
        return np.empty(0, dtype=np.float32)
    return np.concatenate([frame.to_ndarray().ravel() for frame in frames])


def transcribe(model, audio, *, translation=None):
    segments, _ = model.transcribe(audio, language=translation.source_language if translation else None,
                                   task="translate" if translation else "transcribe",
                                   beam_size=1, vad_filter=True,
                                   condition_on_previous_text=False)
    return " ".join(segment.text.strip() for segment in segments if segment.text.strip())


def load_model(model_path, cache_path=None):
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    if cache_path is not None:
        os.environ.setdefault("HF_HOME", str(cache_path.parent / "huggingface"))
    from ctranslate2 import get_supported_compute_types
    from faster_whisper import WhisperModel

    model = str(model_path) if model_path.is_dir() else "base"
    compute_type = "int8" if "int8" in get_supported_compute_types("cpu") else "float32"
    return WhisperModel(model, device="cpu", compute_type=compute_type,
                        local_files_only=model_path.is_dir(),
                        download_root=str(cache_path) if cache_path is not None else None)


def check_model(model_path, sample):
    """Exercise the packaged CPU model and VAD without a microphone or desktop."""
    if not model_path.is_dir():
        raise FileNotFoundError("The model folder must be present for the offline check.")
    with wave.open(str(sample), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth()) != (1, 2):
            raise ValueError("The check file must be a mono 16-bit PCM WAV.")
        audio = pcm_samples(wav.readframes(wav.getnframes()), wav.getframerate())
    return transcribe(load_model(model_path), audio)


class SpeechWorker:
    def __init__(self, commands, events, model_path, cache_path):
        self.commands = commands
        self.events = events
        self.model_path = model_path
        self.cache_path = cache_path

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="Speech").start()

    def run(self):
        try:
            import sounddevice as sd
            model = load_model(self.model_path, self.cache_path)
        except Exception:
            logging.exception("Speech startup failed")
            self.events.put(("model_error", "Could not load Whisper. Check the app log."))
            return

        self.events.put(("model_ready", None))
        while True:
            command = self.commands.get()
            if command == "quit":
                return
            if command != "record":
                continue

            try:
                command, samples, rate = self.record(sd)
            except Exception:
                logging.exception("Microphone capture failed")
                self.events.put(("speech_error", "Could not open or read the default microphone."))
                continue
            if command == "quit":
                return
            if command == "cancel":
                self.events.put(("discarded", None))
                continue
            try:
                audio = pcm_samples(samples, rate) if samples else None
            except Exception:
                logging.exception("Audio preparation failed")
                self.events.put(("speech_error", "Could not prepare the recording. Check the app log."))
                continue
            try:
                translation = command if isinstance(command, EnglishTranslation) else None
                text = (transcribe(model, audio, translation=translation)
                        if audio is not None and audio.size else "")
                self.events.put(("transcript", text))
            except Exception:
                logging.exception("Transcription failed")
                self.events.put(("speech_error", "Transcription failed. Check the app log."))

    def record(self, sd):
        frames = []

        def capture(indata, _frames, _time, _status):
            frames.append(bytes(indata))

        device = sd.query_devices(kind="input")
        rate = int(device["default_samplerate"])
        with sd.RawInputStream(samplerate=rate, channels=1, dtype="int16", latency="low",
                               callback=capture):
            self.events.put(("recording", None))
            command = self.commands.get()

        if command == "transcribe" or isinstance(command, EnglishTranslation):
            return command, b"".join(frames), rate
        return command, b"", rate
