"""Capture microphone audio on demand and transcribe it with Faster Whisper."""

import logging
import os
import threading
import time
import wave
from dataclasses import dataclass

from translation import TranslationError


WHISPER_RATE = 16000
WHISPER_WINDOW_SECONDS = 30
DEFAULT_MODEL = "small"
MAX_QUICK_AUDIO_SECONDS = 18
MIN_ENCODER_FRAMES = 1100
ENCODER_PADDING_FRAMES = 500


@dataclass(frozen=True)
class SpeechRequest:
    source: str = "auto"
    target: str = "same"

    @property
    def whisper_task(self):
        return "translate" if self.target == "en" and self.source != "en" else "transcribe"

    @property
    def needs_text_translation(self):
        return self.target == "ur" or (self.target not in ("same", "en", self.source))


def pcm_samples(data, rate):
    import numpy as np

    samples = np.frombuffer(data, dtype=np.int16)
    if rate == WHISPER_RATE:
        audio = samples.astype(np.float32) / 32768.0
    else:
        import av

        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = rate
        resampler = av.AudioResampler(format="flt", layout="mono", rate=WHISPER_RATE)
        frames = resampler.resample(frame) + resampler.resample(None)
        if not frames:
            return np.empty(0, dtype=np.float32)
        audio = np.concatenate([frame.to_ndarray().ravel() for frame in frames])
    if audio.size:
        peak = max(float(audio.max()), -float(audio.min()))
        if 0.004 <= peak < 0.09:
            # Help quiet speech while preserving near-silent and already strong signals.
            audio *= min(4.0, 0.18 / peak)
    return audio


def transcribe(model, audio, request=SpeechRequest()):
    decoding = {"beam_size": 1}
    if request.source == "ur" and request.target == "en":
        # Compare several candidate translations and bound the expensive fallback on Urdu speech.
        decoding.update(beam_size=3, best_of=2, temperature=(0.0, 0.2, 0.4))
    segments, _ = model.transcribe(audio, language=None if request.source == "auto" else request.source,
                                   task=request.whisper_task,
                                   vad_filter=True,
                                   without_timestamps=audio.size <= WHISPER_RATE * WHISPER_WINDOW_SECONDS,
                                   condition_on_previous_text=False, **decoding)
    return " ".join(segment.text.strip() for segment in segments if segment.text.strip())


def trim_encoder_padding(features):
    """Keep the mel frames for the whole clip and some of Faster Whisper's zero padding."""
    import numpy as np

    if features.ndim != 2 or features.shape[1] <= MIN_ENCODER_FRAMES or np.any(features[:, -1]):
        return features
    content = np.flatnonzero(np.any(features, axis=0))
    if not content.size:
        return features
    end = max(MIN_ENCODER_FRAMES, int(content[-1]) + 1 + ENCODER_PADDING_FRAMES)
    return np.ascontiguousarray(features[:, :end]) if end < features.shape[-1] else features


def load_model(model_path, cache_path=None):
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    if cache_path is not None:
        os.environ.setdefault("HF_HOME", str(cache_path.parent / "huggingface"))
    from ctranslate2 import get_supported_compute_types
    from faster_whisper import WhisperModel

    class LocalWhisper(WhisperModel):
        compact_encoder = False

        def encode(self, features):
            if self.compact_encoder:
                features = trim_encoder_padding(features)
            return super().encode(features)

        def transcribe(self, audio, **options):
            if not options.get("without_timestamps") or audio.size > WHISPER_RATE * MAX_QUICK_AUDIO_SECONDS:
                return super().transcribe(audio, **options)
            self.compact_encoder = True
            try:
                segments, info = super().transcribe(audio, **{**options, "temperature": 0.0})
                segments = list(segments)
            finally:
                self.compact_encoder = False

            if not info.duration_after_vad or (segments and all(
                segment.avg_logprob >= -1.0 and segment.compression_ratio <= 2.4 for segment in segments
            )):
                return segments, info
            logging.info("Retrying short speech with the full Whisper window")
            return super().transcribe(audio, **options)

    model = str(model_path) if model_path.is_dir() else DEFAULT_MODEL
    compute_type = "int8" if "int8" in get_supported_compute_types("cpu") else "float32"
    whisper = LocalWhisper(model, device="cpu", compute_type=compute_type,
                           local_files_only=model_path.is_dir(),
                           download_root=str(cache_path) if cache_path is not None else None)
    logging.info("Loaded Whisper %s with CPU %s", model_path.name if model_path.is_dir() else DEFAULT_MODEL,
                 compute_type)
    return whisper


def check_model(model_path, sample):
    """Exercise the packaged CPU model and VAD without a microphone or desktop."""
    if not model_path.is_dir():
        raise FileNotFoundError("The model folder must be present for the offline check.")
    with wave.open(str(sample), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth()) != (1, 2):
            raise ValueError("The check file must be a mono 16-bit PCM WAV.")
        audio = pcm_samples(wav.readframes(wav.getnframes()), wav.getframerate())
    return transcribe(load_model(model_path), audio)


def input_devices(sd):
    """Prefer the WASAPI endpoint when it represents the same Windows default microphone."""
    default = sd.query_devices(kind="input")
    try:
        hostapis = sd.query_hostapis()
    except sd.PortAudioError:
        return (default,)
    for api in hostapis:
        index = api["default_input_device"]
        if api["name"] != "Windows WASAPI" or index < 0 or index == default["index"]:
            continue
        try:
            candidate = sd.query_devices(index, kind="input")
        except sd.PortAudioError:
            return (default,)
        default_name = default["name"].strip().casefold()
        candidate_name = candidate["name"].strip().casefold()
        # The MME backend can truncate a device name to 31 characters.
        is_truncated = hostapis[default["hostapi"]]["name"] == "MME" and len(default["name"]) == 31
        if candidate_name == default_name or (is_truncated and candidate_name.startswith(default_name)):
            return (candidate, default)
    return (default,)


def start_microphone(sd, capture):
    devices = input_devices(sd)
    for attempt, device in enumerate(devices):
        stream = None
        rate = int(device["default_samplerate"])
        started = time.perf_counter()
        try:
            stream = sd.RawInputStream(device=device["index"], samplerate=rate, channels=1,
                                       dtype="int16", latency="low", callback=capture)
            stream.start()
        except sd.PortAudioError:
            if stream is not None:
                stream.close()
            if attempt == len(devices) - 1:
                raise
            logging.info("WASAPI capture unavailable. Trying the Windows default input.")
        else:
            logging.info("Microphone input %d ready in %.0f ms at %d Hz",
                         device["index"], (time.perf_counter() - started) * 1000, rate)
            return stream, rate


class SpeechWorker:
    def __init__(self, commands, events, model_path, cache_path, translator):
        self.commands = commands
        self.events = events
        self.model_path = model_path
        self.cache_path = cache_path
        self.translator = translator

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
                text = ""
                if audio is not None and audio.size:
                    started = time.perf_counter()
                    text = transcribe(model, audio, command)
                    logging.info("Whisper finished in %.2f s", time.perf_counter() - started)
                if text and command.needs_text_translation:
                    self.events.put(("translating", None))
                    started = time.perf_counter()
                    text = self.translator.translate(text, command.source, command.target, from_speech=True)
                    logging.info("Text translation finished in %.2f s", time.perf_counter() - started)
                self.events.put(("transcript", text))
            except TranslationError as error:
                self.events.put(("speech_error", str(error)))
            except Exception:
                logging.exception("Transcription failed")
                self.events.put(("speech_error", "Transcription failed. Check the app log."))

    def record(self, sd):
        frames = []
        overflow = False

        def capture(indata, _frames, _time, status):
            nonlocal overflow
            if status and status.input_overflow:
                overflow = True
            frames.append(bytes(indata))

        stream, rate = start_microphone(sd, capture)
        try:
            self.events.put(("recording", None))
            command = self.commands.get()
        finally:
            try:
                stream.stop()
            finally:
                stream.close()

        if isinstance(command, SpeechRequest):
            if overflow:
                logging.warning("Microphone input overflowed during capture")
            return command, b"".join(frames), rate
        return command, b"", rate
