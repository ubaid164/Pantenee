import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pantenee import load_settings
from translation import LocalTranslator, TranslationError


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.translator = LocalTranslator(Path("test.gguf"))
        self.model = Mock()
        self.model.tokenize.return_value = [1, 2, 3]

    def test_roman_urdu_requests_latin_urdu_and_reuses_the_model(self):
        self.model.create_completion.return_value = {
            "choices": [{"text": " Aap kaise hain? ", "finish_reason": "stop"}],
        }
        with patch.object(self.translator, "load_model", return_value=self.model) as load:
            self.assertEqual(self.translator.translate("你好吗？", "zh", "ur"), "Aap kaise hain?")
            self.assertEqual(self.translator.translate("How are you?", "en", "ur"), "Aap kaise hain?")
        load.assert_called_once()
        self.assertIn(b"Pakistani Urdu written entirely in Latin letters", self.model.tokenize.call_args.args[0])

    def test_roman_urdu_rejects_urdu_script_devanagari_and_english(self):
        self.translator.model = self.model
        for output in ("آپ کیسے ہیں؟", "आप कैसे हैं?", "Welcome to the voice recognition app."):
            with self.subTest(output=output):
                self.model.create_completion.return_value = {"choices": [{"text": output, "finish_reason": "stop"}]}
                with self.assertRaisesRegex(TranslationError, "didn’t return Roman Urdu"):
                    self.translator.translate("How are you?", "en", "ur")

    def test_roman_urdu_retries_an_english_result_with_a_roman_urdu_prompt(self):
        self.translator.model = self.model
        self.model.create_completion.side_effect = [
            {"choices": [{"text": "Thank you for your help.", "finish_reason": "stop"}]},
            {"choices": [{"text": "Aap ki madad ka shukriya.", "finish_reason": "stop"}]},
        ]
        self.assertEqual(self.translator.translate("谢谢你的帮助。", "zh", "ur"), "Aap ki madad ka shukriya.")
        self.assertTrue(self.model.tokenize.call_args.args[0].endswith(b"Roman Urdu: "))

    def test_preserves_typed_same_language_and_rejects_truncated_results(self):
        self.assertEqual(self.translator.translate("Kal miltay hain.", "ur", "ur"), "Kal miltay hain.")
        self.assertIsNone(self.translator.model)
        self.translator.model = self.model
        self.model.create_completion.return_value = {"choices": [{"text": "你好", "finish_reason": "length"}]}
        with self.assertRaisesRegex(TranslationError, "Could not finish"):
            self.translator.translate("Kal miltay hain.", "ur", "zh")

    def test_settings_preserve_legacy_and_current_choices(self):
        examples = (({"dictation_output": "Urdu → English"}, ("ur", "en")),
                    ({"dictation_output": "Chinese (Mandarin) → English"}, ("zh", "en")),
                    ({"dictation_output": "Auto-detect → English"}, ("auto", "en")),
                    ({"translate_urdu": True}, ("ur", "en")),
                    ({"dictation_output": "As spoken"}, ("auto", "same")),
                    ({"source_language": "zh", "target_language": "ur"}, ("zh", "ur")))
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / "settings.json"
            with patch("pantenee.SETTINGS", settings):
                for stored, languages in examples:
                    with self.subTest(stored=stored):
                        settings.write_text(json.dumps({"enter": True, **stored}), encoding="utf-8")
                        self.assertEqual(load_settings("Off"), ("Left Ctrl", True, "Off", *languages))
