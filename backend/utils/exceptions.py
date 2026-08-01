"""Custom exception types used across the NativeMed AI backend.

Centralizing these lets api/routes.py translate them into consistent,
meaningful HTTP status codes instead of leaking raw stack traces.
"""

from __future__ import annotations


class NativeMedError(Exception):
    """Base class for all application-specific errors."""


class DatabaseError(NativeMedError):
    """Raised when a SQLite read/write operation fails."""


class CSVImportError(NativeMedError):
    """Raised when a CSV file is missing, malformed, or fails validation."""


class RetrievalError(NativeMedError):
    """Raised when the RAG retriever/vector store fails."""


class LLMError(NativeMedError):
    """Raised when the LLM provider fails or returns an invalid response."""


class TranslationError(NativeMedError):
    """Raised when language detection or translation fails."""


class UnsupportedLanguageError(TranslationError):
    """Raised when the detected/requested language isn't supported."""


class SpeechToTextError(NativeMedError):
    """Raised when audio transcription fails."""


class TextToSpeechError(NativeMedError):
    """Raised when speech synthesis fails."""


class InvalidAudioFileError(NativeMedError):
    """Raised when an uploaded audio file is missing/unsupported/corrupt."""


class PlantNotFoundError(NativeMedError):
    """Raised when a requested plant_id does not exist in the database."""
