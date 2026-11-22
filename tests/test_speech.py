import sys
import unittest
from pathlib import Path
from queue import SimpleQueue
from types import SimpleNamespace
from unittest.mock import Mock, patch

from speech import EnglishTranslation, SpeechWorker


class InputStream:
    def __init__(self, *, callback, **_):
        self.callback = callback

    def __enter__(self):
        self.callback(b"\x01\x00", 1, None, None)

    def __exit__(self, *_):
        pass


class SpeechWorkerTests(unittest.TestCase):
    def test_language_presets_auto_translation_and_normal_transcription_decode_on_release(self):
        commands, events = SimpleQueue(), SimpleQueue()
        finishes = (EnglishTranslation("zh"), EnglishTranslation("ur"), EnglishTranslation(), "transcribe")
        for finish in finishes:
            commands.put("record")
            commands.put(finish)
        commands.put("quit")
        sounddevice = SimpleNamespace(query_devices=lambda **_: {"default_samplerate": 16000},
                                      RawInputStream=InputStream)
        model = Mock()
        model.transcribe.return_value = ([SimpleNamespace(text=" Test. ")], None)
        audio = SimpleNamespace(size=1)
        worker = SpeechWorker(commands, events, Path("model"), Path("cache"))
        with (
            patch.dict(sys.modules, {"sounddevice": sounddevice}),
            patch("speech.load_model", return_value=model),
            patch("speech.pcm_samples", return_value=audio) as convert,
        ):
            worker.run()

        self.assertEqual(convert.call_count, 4)
        self.assertEqual([(call.kwargs["language"], call.kwargs["task"])
                          for call in model.transcribe.call_args_list],
                         [("zh", "translate"), ("ur", "translate"),
                          (None, "translate"), (None, "transcribe")])
        self.assertEqual(events.get_nowait(), ("model_ready", None))
        for _ in finishes:
            self.assertEqual(events.get_nowait(), ("recording", None))
            self.assertEqual(events.get_nowait(), ("transcript", "Test."))
        self.assertTrue(events.empty())

    def test_audio_preparation_failure_is_reported_and_next_recording_succeeds(self):
        commands, events = SimpleQueue(), SimpleQueue()
        for command in ("record", "transcribe", "record", EnglishTranslation("ur"), "quit"):
            commands.put(command)
        device = SimpleNamespace(query_devices=lambda **_: {"default_samplerate": 44100},
                                 RawInputStream=InputStream)
        audio = SimpleNamespace(size=1)
        model = Mock()
        model.transcribe.return_value = ([SimpleNamespace(text=" Recovered. ")], None)
        worker = SpeechWorker(commands, events, Path("model"), Path("cache"))

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
