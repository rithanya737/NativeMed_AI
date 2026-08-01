"""
Unit tests for translation/translator.py.

Network-dependent calls (Google Translate via deep-translator) are mocked
so these tests are fast and deterministic. Language *detection* (langdetect)
runs for real since it's a local, offline library.
"""

from __future__ import annotations

import pytest

from utils.exceptions import TranslationError, UnsupportedLanguageError
import translation.translator as translator_module


def test_detect_language_defaults_to_english_for_short_input():
    result = translator_module.detect_language("hi")
    assert result.language_code == "en"


def test_detect_language_raises_on_empty_text():
    with pytest.raises(TranslationError):
        translator_module.detect_language("")


def test_detect_language_english_sentence():
    result = translator_module.detect_language("What plants help with a cough and cold?")
    assert result.language_code == "en"
    assert result.language_name == "English"


def test_translate_text_noop_when_same_language():
    # No network call needed since source == target short-circuits.
    result = translator_module.translate_text("hello", source_lang="en", target_lang="en")
    assert result == "hello"


def test_translate_text_wraps_provider_errors(monkeypatch):
    class ExplodingTranslator:
        def __init__(self, source, target):
            pass

        def translate(self, text):
            raise RuntimeError("network down")

    monkeypatch.setattr(
        "deep_translator.GoogleTranslator", ExplodingTranslator, raising=False
    )

    with pytest.raises(TranslationError):
        translator_module.translate_text("hello", source_lang="en", target_lang="ta")


def test_translate_to_english_skips_translation_for_english(monkeypatch):
    monkeypatch.setattr(
        translator_module,
        "detect_language",
        lambda text: translator_module.DetectionResult("en", "English", 0.99),
    )
    detection, text = translator_module.translate_to_english("hello there")
    assert detection.language_code == "en"
    assert text == "hello there"


def test_translate_to_english_calls_translate_for_non_english(monkeypatch):
    monkeypatch.setattr(
        translator_module,
        "detect_language",
        lambda text: translator_module.DetectionResult("ta", "Tamil", 0.95),
    )
    monkeypatch.setattr(
        translator_module, "translate_text", lambda text, source_lang, target_lang: "translated!"
    )
    detection, text = translator_module.translate_to_english("சோதனை உரை")
    assert detection.language_code == "ta"
    assert text == "translated!"


def test_translate_from_english_noop_for_english():
    result = translator_module.translate_from_english("hello", "en")
    assert result == "hello"


def test_translate_from_english_calls_translate_for_other_languages(monkeypatch):
    monkeypatch.setattr(
        translator_module, "translate_text", lambda text, source_lang, target_lang: "translated!"
    )
    result = translator_module.translate_from_english("hello", "hi")
    assert result == "translated!"
