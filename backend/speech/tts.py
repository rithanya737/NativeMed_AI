"""
Text-to-Speech: synthesizes speech audio from the chatbot's final answer
using gTTS (Google Text-to-Speech), which supports all 6 languages
NativeMed AI needs (English, Tamil, Hindi, Malayalam, Telugu, Kannada).
"""

from __future__ import annotations

import uuid

from utils.config import get_settings
from utils.exceptions import TextToSpeechError
from utils.logger import logger

# gTTS language codes match the ISO 639-1 codes used elsewhere in this
# codebase for every language NativeMed AI supports.
SUPPORTED_TTS_LANGUAGES = {"en", "ta", "hi", "ml", "te", "kn"}


def synthesize_speech(text: str, language: str = "en") -> str:
    """Generate an MP3 file for `text` in `language` and return its path.

    Raises TextToSpeechError for empty text, unsupported languages, or any
    failure from the underlying TTS engine.
    """
    if not text or not text.strip():
        raise TextToSpeechError("Cannot synthesize speech for empty text.")

    if language not in SUPPORTED_TTS_LANGUAGES:
        raise TextToSpeechError(
            f"Text-to-speech is not supported for language '{language}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_TTS_LANGUAGES))}"
        )

    settings = get_settings()
    output_dir = settings.resolved_tts_output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{uuid.uuid4().hex}.mp3"

    try:
        from gtts import gTTS

        tts = gTTS(text=text, lang=language)
        tts.save(str(output_path))
    except Exception as exc:
        raise TextToSpeechError(f"Failed to synthesize speech: {exc}") from exc

    logger.info(f"Synthesized speech ({language}) -> {output_path}")
    return str(output_path)
