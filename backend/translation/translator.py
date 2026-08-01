"""
Multilingual support: language detection + translation.

Supported languages (per the NativeMed AI spec): English, Tamil, Hindi,
Malayalam, Telugu, Kannada.

Workflow used by api/routes.py's /chat endpoint:

    Detect language
        -> if not English: translate question to English
        -> retrieve + generate answer in English
        -> if original language wasn't English: translate answer back
"""

from __future__ import annotations

from dataclasses import dataclass

from utils.config import get_settings
from utils.exceptions import TranslationError, UnsupportedLanguageError
from utils.logger import logger

# Map ISO 639-1 codes (as returned by langdetect / used by deep-translator)
# to human-readable names, restricted to what NativeMed AI supports.
LANGUAGE_NAMES = {
    "en": "English",
    "ta": "Tamil",
    "hi": "Hindi",
    "ml": "Malayalam",
    "te": "Telugu",
    "kn": "Kannada",
}


@dataclass
class DetectionResult:
    language_code: str
    language_name: str
    confidence: float


def detect_language(text: str) -> DetectionResult:
    """Detect the language of `text`. Defaults to English for very short or
    ambiguous input (langdetect is unreliable below ~3-4 words) rather than
    raising, since a short greeting like "hi" is common and shouldn't hard-fail.
    """
    settings = get_settings()
    stripped = text.strip()

    if not stripped:
        raise TranslationError("Cannot detect language of empty text.")

    if len(stripped.split()) < 2:
        logger.debug("Input too short for reliable language detection; defaulting to English.")
        return DetectionResult(language_code="en", language_name="English", confidence=0.0)

    try:
        from langdetect import DetectorFactory, detect_langs

        DetectorFactory.seed = 0  # deterministic results
        candidates = detect_langs(stripped)
        best = candidates[0]
        code = best.lang
        confidence = float(best.prob)
    except Exception as exc:
        logger.warning(f"Language detection failed ({exc}); defaulting to English.")
        return DetectionResult(language_code="en", language_name="English", confidence=0.0)

    if code not in settings.supported_languages_list:
        raise UnsupportedLanguageError(
            f"Detected language '{code}' is not currently supported. "
            f"Supported languages: {', '.join(settings.supported_languages_list)}."
        )

    return DetectionResult(
        language_code=code,
        language_name=LANGUAGE_NAMES.get(code, code),
        confidence=round(confidence, 3),
    )


def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """Translate `text` from `source_lang` to `target_lang` (ISO 639-1 codes)."""
    if source_lang == target_lang:
        return text

    try:
        from deep_translator import GoogleTranslator

        return GoogleTranslator(source=source_lang, target=target_lang).translate(text)
    except Exception as exc:
        raise TranslationError(
            f"Failed to translate text from '{source_lang}' to '{target_lang}': {exc}"
        ) from exc


def translate_to_english(text: str) -> tuple[DetectionResult, str]:
    """Detect the language of `text` and translate it to English if needed.
    Returns (detection_result, english_text).
    """
    detection = detect_language(text)
    if detection.language_code == "en":
        return detection, text

    translated = translate_text(text, source_lang=detection.language_code, target_lang="en")
    logger.info(f"Translated question from '{detection.language_code}' to English.")
    return detection, translated


def translate_from_english(text: str, target_lang: str) -> str:
    """Translate English `text` back into `target_lang`. No-op if English."""
    if target_lang == "en":
        return text
    return translate_text(text, source_lang="en", target_lang=target_lang)
