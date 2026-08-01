"""
Speech-to-Text: transcribes an uploaded audio file using OpenAI's Whisper
(run locally -- no API key required, works fully offline).

Workflow: audio file -> transcription -> (continues into the normal
text-based RAG pipeline in api/routes.py).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from utils.config import get_settings
from utils.exceptions import InvalidAudioFileError, SpeechToTextError
from utils.logger import logger

SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4"}


@lru_cache
def _load_whisper_model():
    import whisper

    settings = get_settings()
    logger.info(f"Loading Whisper model '{settings.whisper_model_size}' (first call only)...")
    model = whisper.load_model(settings.whisper_model_size)
    logger.info("Whisper model loaded.")
    return model


def _validate_audio_file(file_path: str) -> None:
    path = Path(file_path)
    if not path.exists():
        raise InvalidAudioFileError(f"Audio file not found: {file_path}")
    if path.stat().st_size == 0:
        raise InvalidAudioFileError(f"Audio file is empty: {file_path}")
    if path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        raise InvalidAudioFileError(
            f"Unsupported audio format '{path.suffix}'. Supported formats: "
            f"{', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}"
        )


def transcribe_audio(file_path: str) -> dict:
    """Transcribe the audio file at `file_path`. Returns a dict with the
    transcribed text and Whisper's own detected language (which is
    independent from, and a useful cross-check against, translation/translator.py's
    text-based language detection run afterward on the transcript).
    """
    _validate_audio_file(file_path)

    try:
        model = _load_whisper_model()
        result = model.transcribe(file_path)
    except Exception as exc:
        raise SpeechToTextError(f"Failed to transcribe audio '{file_path}': {exc}") from exc

    text = (result.get("text") or "").strip()
    if not text:
        raise SpeechToTextError(
            "Transcription produced no text -- the audio may be silent, "
            "too short, or in an unrecognized language."
        )

    logger.info(f"Transcribed audio ({file_path}) -> {len(text)} characters.")
    return {
        "text": text,
        "whisper_detected_language": result.get("language"),
    }
