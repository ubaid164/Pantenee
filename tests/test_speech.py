import sys
import unittest
from pathlib import Path
from queue import SimpleQueue
from types import SimpleNamespace
from unittest.mock import Mock, patch

from speech import EnglishTranslation, SpeechWorker


class SpeechWorkerTests(unittest.TestCase):
    def test_language_presets_auto_translation_and_normal_transcription_decode_on_release(self):
        class InputStream:
            def __init__(self, *, callback, **_):
                self.callback = callback

            def __enter__(self):
                self.callback(b"\x01\x00", 1, None, None)

            def __exit__(self, *_):
                pass

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
