"""Offline text translation shared by dictation and the text editor."""

import logging
import os
import re
import threading
import unicodedata


LANGUAGES = {
    "ar": "Arabic",
    "bn": "Bengali",
    "zh": "Chinese (Simplified)",
    "en": "English",
    "fr": "French",
    "de": "German",
    "hi": "Hindi",
    "id": "Indonesian",
    "ja": "Japanese",
    "mr": "Marathi",
    "pt": "Portuguese",
    "pa": "Punjabi",
    "ur": "Roman Urdu",
    "ru": "Russian",
    "es": "Spanish",
    "ta": "Tamil",
    "te": "Telugu",
    "tr": "Turkish",
    "vi": "Vietnamese",
}
MODEL_FILENAME = "qwen3.5-2b.gguf"
CONTEXT_SIZE = 2048
START_MESSAGE = "<|im_start|>"
END_MESSAGE = "<|im_end|>"
# Roman Urdu can contain English names and technical terms. Look for common Urdu grammar words
# before treating a Latin-script sentence with several English function words as a wrong-language result.
URDU_WORDS = frozenset("aap ap aapke hai hain ho hoon hun mera meri mujhe muje tum woh ka ki ke ko "
                       "se mein main mai ne aur kar karein karo karna raha rahi rahe ga gi hum nahi nahin kyun".split())
ENGLISH_WORDS = frozenset("the with from this that these those are was were will would have has you your "
                          "they their there by for to of please".split())


class TranslationError(Exception):
    """A problem the app can display without exposing private text in its log."""


class LocalTranslator:
    def __init__(self, model_path):
        self.model_path = model_path
        self.model = None
        self.lock = threading.Lock()
        self.warmup_started = False

    def warmup(self):
        if self.model is None and not self.warmup_started and self.model_path.is_file():
            self.warmup_started = True
            threading.Thread(target=self.preload, daemon=True, name="Translation warmup").start()

    def preload(self):
        try:
            with self.lock:
                if self.model is None:
                    self.model = self.load_model()
                    logging.info("Local text translation model ready")
        except TranslationError:
            logging.info("Local text translation will retry loading on demand")

    def load_model(self):
        if not self.model_path.is_file():
            raise TranslationError("Local translation model is missing. Run Set up translation.cmd.")
        try:
            from llama_cpp import Llama

            threads = min(4, os.cpu_count() or 1)
            return Llama(model_path=str(self.model_path), n_ctx=CONTEXT_SIZE, n_threads=threads,
                         n_threads_batch=threads, verbose=False)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            raise TranslationError("Could not load local translation. Run Set up translation.cmd.") from exc

    def translate(self, text, source, target, *, from_speech=False):
        text = text.strip()
        if not text or target == "same" or (source == target and target != "ur"):
            return text
        # Keep already-romanized typed Urdu as written.
        if source == target == "ur" and not from_speech and is_latin_text(text):
            return text
        input_language = LANGUAGES.get(source, "the language of the supplied text")
        if source == "ur":
            input_language = "Roman Urdu" if is_latin_text(text) else "Urdu"
        if source == target == "ur":
            instruction = "Write the supplied Urdu text in natural Pakistani Roman Urdu, keeping the original words."
        else:
            output_language = "Simplified Chinese" if target == "zh" else LANGUAGES[target]
            instruction = f"Translate the following text from {input_language} into {output_language}."
        if target == "ur":
            instruction += ' Use Pakistani Urdu written entirely in Latin letters, e.g. "Aap kaise hain?"'
        if len(text) > 6000:
            raise TranslationError("This text is too long for one translation. Use shorter sections.")
        # Escape ChatML message delimiters in user text before tokenizing.
        text = text.replace(START_MESSAGE, "< |im_start|>").replace(END_MESSAGE, "< |im_end|>")
        instruction += (" Preserve names, numbers, times, verb tense and the speaker's point of view. "
                        "Return only the result.")
        with self.lock:
            if self.model is None:
                self.model = self.load_model()
            translated = self.complete(instruction, text)
            if target == "ur" and not looks_like_roman_urdu(translated):
                roman_instruction = (f"Translate the following {input_language.removesuffix(' (Simplified)')} text "
                                     "into everyday Pakistani Urdu. "
                                     "Write the Urdu words using Latin letters. Keep the original meaning and all names, "
                                     'numbers and times. Example: "The shop opens tomorrow." → "Dukaan kal khulay gi." '
                                     "Output the Roman Urdu translation alone.")
                translated = self.complete(roman_instruction, text, prefill="Roman Urdu: ")
                if not looks_like_roman_urdu(translated):
                    raise TranslationError("The model didn’t return Roman Urdu. Try a shorter sentence.")
        return translated

    def complete(self, instruction, text, *, prefill=""):
        prompt = (f"{START_MESSAGE}user\n{instruction}\n\nText: {text}{END_MESSAGE}\n"
                  f"{START_MESSAGE}assistant\n<think>\n\n</think>\n\n{prefill}")
        tokens = self.model.tokenize(prompt.encode("utf-8"), add_bos=False, special=True)
        if len(tokens) > 1200:
            raise TranslationError("This text is too long for one translation. Use shorter sections.")
        result = self.model.create_completion(tokens, max_tokens=min(768, 3 * len(tokens)),
                                              temperature=0.0, stop=[END_MESSAGE, START_MESSAGE, "<think>"])
        choice = result["choices"][0]
        translated = choice["text"].strip()
        if choice["finish_reason"] == "length" or not translated:
            raise TranslationError("Could not finish the translation. Try a shorter sentence.")
        return translated


def is_latin_text(text):
    return all(not character.isalpha() or unicodedata.name(character, "").startswith("LATIN ")
               for character in text)


def looks_like_roman_urdu(text):
    words = set(re.findall(r"[a-z]+", text.lower()))
    return is_latin_text(text) and (bool(words & URDU_WORDS) or len(words & ENGLISH_WORDS) < 2)
