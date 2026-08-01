"""
Centralized application configuration.

All environment-driven settings live here so the rest of the codebase never
reads `os.environ` directly. This keeps configuration testable, discoverable,
and consistent (single source of truth), and makes it trivial to override
settings in unit tests via `Settings(**overrides)`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Root of the backend/ package, regardless of current working directory.
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM ---
    # Default provider is "ollama" -- a free, fully local model server
    # (https://ollama.com), so no API key is required out of the box.
    # Set to "openai" (and fill in openai_api_key) or "mock" to override.
    openai_api_key: str = ""
    llm_provider: str = "ollama"
    llm_model: str = "gpt-4o-mini"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # --- Database ---
    database_path: str = "database/plants.db"

    # --- Vector store ---
    vectorstore_path: str = "vectorstore/chroma"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    collection_name: str = "nativemed_plants"

    # --- Retrieval ---
    top_k_results: int = 5
    min_similarity_score: float = 0.35

    # --- Multilingual ---
    default_language: str = "en"
    supported_languages: str = "en,ta,hi,ml,te,kn"

    # --- Speech ---
    whisper_model_size: str = "base"
    tts_output_dir: str = "data/audio_out"

    # --- App ---
    app_env: str = "development"
    log_level: str = "INFO"

    @property
    def supported_languages_list(self) -> list[str]:
        return [lang.strip() for lang in self.supported_languages.split(",") if lang.strip()]

    @property
    def resolved_database_path(self) -> Path:
        path = Path(self.database_path)
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def resolved_vectorstore_path(self) -> Path:
        path = Path(self.vectorstore_path)
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def resolved_tts_output_dir(self) -> Path:
        path = Path(self.tts_output_dir)
        return path if path.is_absolute() else BASE_DIR / path

    @property
    def is_llm_configured(self) -> bool:
        """Whether a real LLM provider key is available, or we must mock."""
        return bool(self.openai_api_key) and self.llm_provider.lower() != "mock"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor so we parse the environment only once."""
    return Settings()
