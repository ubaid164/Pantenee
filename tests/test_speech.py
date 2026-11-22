import sys
import unittest
from pathlib import Path
from queue import SimpleQueue
from types import SimpleNamespace
from unittest.mock import Mock, patch

from speech import (WHISPER_RATE, SpeechRequest, SpeechWorker, input_devices, load_model, pcm_samples,
                    start_microphone, transcribe, trim_encoder_padding)
from translation import TranslationError


class InputStream:
    def __init__(self, *, callback, **_):
        self.callback = callback

    def start(self):
        self.callback(b"\x01\x00", 1, None, None)

    def stop(self):
        pass

    def close(self):
        pass


class PortAudioError(Exception):
    pass


def audio_driver(rate=16000, *, with_wasapi=False):
    devices = {1: {"name": "Microphone Array (Intel Smart S", "index": 1, "hostapi": 0,
                   "default_samplerate": rate},
               9: {"name": "Microphone Array (Intel Smart Sound)", "index": 9, "hostapi": 1,
                   "default_samplerate": 48000}}
    hostapis = [{"name": "MME", "default_input_device": 1}]
    if with_wasapi:
        hostapis.append({"name": "Windows WASAPI", "default_input_device": 9})
    return SimpleNamespace(query_devices=lambda index=1, **_: devices[index],
                           query_hostapis=lambda: hostapis, RawInputStream=InputStream,
                           PortAudioError=PortAudioError)


class SpeechWorkerTests(unittest.TestCase):
    def test_short_encoder_preserves_all_audio_and_context_padding(self):
        import numpy as np

        features = np.zeros((80, 3000), dtype=np.float32)
        features[:, :1240] = 1
        trimmed = trim_encoder_padding(features)
        self.assertEqual(trimmed.shape, (80, 1740))
        np.testing.assert_array_equal(trimmed, features[:, :1740])
        self.assertTrue(trimmed.flags.c_contiguous)
        features[0, -1] = 1
        self.assertIs(trim_encoder_padding(features), features)

    def test_short_decode_uses_full_context_only_when_the_first_pass_is_uncertain(self):
        import numpy as np

        class TestWhisper:
            def __init__(self, *args, **kwargs):
                self.calls = []

            def encode(self, features):
                return features.shape[1]

            def transcribe(self, audio, **kwargs):
                def segments():
                    features = np.zeros((80, 3000), dtype=np.float32)
                    features[0, 10] = 1
                    frames = self.encode(features)
                    self.calls.append((frames, kwargs["temperature"]))
                    yield SimpleNamespace(text="English", avg_logprob=-0.2 if frames == 3000 else self.score,
                                          compression_ratio=1.0)

                return segments(), SimpleNamespace(duration_after_vad=1)

        modules = {"faster_whisper": SimpleNamespace(WhisperModel=TestWhisper),
                   "ctranslate2": SimpleNamespace(get_supported_compute_types=lambda _: {"int8"})}
        with patch.dict(sys.modules, modules):
            model = load_model(Path("model"))
        model.score = -0.2
        audio = np.zeros(16000, dtype=np.float32)
        request = SpeechRequest("ur", "en")

        self.assertEqual(transcribe(model, audio, request), "English")
        self.assertEqual(model.calls, [(1100, 0.0)])

        model.calls.clear()
        model.score = -1.4
        self.assertEqual(transcribe(model, audio, request), "English")
        self.assertEqual(model.calls, [(1100, 0.0), (3000, (0.0, 0.2, 0.4))])

    def test_audio_gain_boosts_quiet_samples_without_boosting_silence_or_loud_input(self):
        import numpy as np

        for peak, expected in ((0, 0), (16, 16), (160, 640), (2500, 5898), (20000, 20000)):
            with self.subTest(peak=peak):
                samples = np.array([-peak, 0, peak], dtype=np.int16)
                audio = pcm_samples(samples.tobytes(), WHISPER_RATE)
                self.assertEqual(audio.dtype, np.float32)
                np.testing.assert_allclose(audio, [-expected / 32768, 0, expected / 32768], atol=2e-5)

    def test_capture_prefers_the_same_windows_microphone_over_wasapi(self):
        driver = audio_driver(44100, with_wasapi=True)
        driver.RawInputStream = Mock(side_effect=InputStream)
        capture = Mock()
        stream, rate = start_microphone(driver, capture)
        stream.close()

        self.assertEqual(rate, 48000)
        self.assertEqual(driver.RawInputStream.call_args.kwargs["device"], 9)
        capture.assert_called_once()

    def test_capture_falls_back_and_closes_a_wasapi_stream_that_cannot_start(self):
        driver = audio_driver(44100, with_wasapi=True)
        unavailable = Mock()
        unavailable.start.side_effect = PortAudioError("Device busy")
        legacy = Mock()
        driver.RawInputStream = Mock(side_effect=[unavailable, legacy])

        stream, rate = start_microphone(driver, Mock())

        self.assertIs(stream, legacy)
        self.assertEqual(rate, 44100)
        unavailable.close.assert_called_once()
        legacy.start.assert_called_once()
        self.assertEqual([call.kwargs["device"] for call in driver.RawInputStream.call_args_list], [9, 1])

    def test_capture_keeps_the_default_when_wasapi_points_to_a_different_microphone(self):
        driver = audio_driver(with_wasapi=True)
        driver.query_devices(9)["name"] = "USB Headset"
        self.assertEqual([device["index"] for device in input_devices(driver)], [1])

    def test_short_recordings_skip_decoding_timestamps(self):
        model = Mock()
        model.transcribe.return_value = ([], None)
        for seconds in (3, 30, 31):
            transcribe(model, SimpleNamespace(size=seconds * WHISPER_RATE))
        self.assertEqual([call.kwargs["without_timestamps"] for call in model.transcribe.call_args_list],
                         [True, True, False])

    def test_language_presets_auto_translation_and_normal_transcription_decode_on_release(self):
        commands, events = SimpleQueue(), SimpleQueue()
        finishes = (SpeechRequest("zh", "en"), SpeechRequest("ur", "en"),
                    SpeechRequest("auto", "en"), SpeechRequest(), SpeechRequest("en", "en"))
        for finish in finishes:
            commands.put("record")
            commands.put(finish)
        commands.put("quit")
        sounddevice = audio_driver()
        model = Mock()
        model.transcribe.return_value = ([SimpleNamespace(text=" Test. ")], None)
        audio = SimpleNamespace(size=1)
        translator = Mock()
        worker = SpeechWorker(commands, events, Path("model"), Path("cache"), translator)
        with (
            patch.dict(sys.modules, {"sounddevice": sounddevice}),
            patch("speech.load_model", return_value=model),
            patch("speech.pcm_samples", return_value=audio) as convert,
        ):
            worker.run()

        self.assertEqual(convert.call_count, len(finishes))
        self.assertEqual([(call.kwargs["language"], call.kwargs["task"])
                          for call in model.transcribe.call_args_list],
                         [("zh", "translate"), ("ur", "translate"),
                          (None, "translate"), (None, "transcribe"), ("en", "transcribe")])
        self.assertEqual([call.kwargs["beam_size"] for call in model.transcribe.call_args_list], [1, 3, 1, 1, 1])
        self.assertEqual(model.transcribe.call_args_list[1].kwargs["temperature"], (0.0, 0.2, 0.4))
        translator.translate.assert_not_called()
        self.assertEqual(events.get_nowait(), ("model_ready", None))
        for _ in finishes:
            self.assertEqual(events.get_nowait(), ("recording", None))
            self.assertEqual(events.get_nowait(), ("transcript", "Test."))
        self.assertTrue(events.empty())

    def test_audio_preparation_failure_is_reported_and_next_recording_succeeds(self):
        commands, events = SimpleQueue(), SimpleQueue()
        for command in ("record", SpeechRequest(), "record", SpeechRequest("ur", "en"), "quit"):
            commands.put(command)
        device = audio_driver(44100)
        audio = SimpleNamespace(size=1)
        model = Mock()
        model.transcribe.return_value = ([SimpleNamespace(text=" Recovered. ")], None)
        worker = SpeechWorker(commands, events, Path("model"), Path("cache"), Mock())

        with (
            patch.dict(sys.modules, {"sounddevice": device}),
            patch("speech.load_model", return_value=model),
            patch("speech.pcm_samples", side_effect=[ValueError("resampling failed"), audio]),
            self.assertLogs(level="ERROR") as logs,
        ):
            worker.run()

        self.assertEqual(events.get_nowait(), ("model_ready", None))
        self.assertEqual(events.get_nowait(), ("recording", None))
        self.assertEqual(events.get_nowait(),
                         ("speech_error", "Could not prepare the recording. Check the app log."))
        self.assertEqual(events.get_nowait(), ("recording", None))
        self.assertEqual(events.get_nowait(), ("transcript", "Recovered."))
        self.assertIn("Audio preparation failed", logs.output[0])
        model.transcribe.assert_called_once()
        self.assertEqual(model.transcribe.call_args.kwargs["task"], "translate")
        self.assertTrue(events.empty())

    def test_non_english_targets_use_source_transcript_and_retry_after_translation_error(self):
        commands, events = SimpleQueue(), SimpleQueue()
        for command in ("record", SpeechRequest("ur", "zh"), "record", SpeechRequest("zh", "ur"), "quit"):
            commands.put(command)
        device = audio_driver()
        whisper = Mock()
        whisper.transcribe.side_effect = [([SimpleNamespace(text="سلام")], None),
                                          ([SimpleNamespace(text="你好")], None)]
        translator = Mock()
        translator.translate.side_effect = [TranslationError("Missing model"), "Assalam alaikum"]
        worker = SpeechWorker(commands, events, Path("model"), Path("cache"), translator)
        with (patch.dict(sys.modules, {"sounddevice": device}),
              patch("speech.load_model", return_value=whisper),
              patch("speech.pcm_samples", return_value=SimpleNamespace(size=1))):
            worker.run()

        self.assertEqual([(call.kwargs["language"], call.kwargs["task"])
                          for call in whisper.transcribe.call_args_list], [("ur", "transcribe"), ("zh", "transcribe")])
        self.assertEqual([call.args for call in translator.translate.call_args_list],
                         [("سلام", "ur", "zh"), ("你好", "zh", "ur")])
        self.assertEqual([events.get_nowait() for _ in range(7)],
                         [("model_ready", None), ("recording", None), ("translating", None),
                          ("speech_error", "Missing model"), ("recording", None), ("translating", None),
                          ("transcript", "Assalam alaikum")])
        self.assertTrue(events.empty())
