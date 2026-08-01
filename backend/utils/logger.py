"""
Shared application logger, built on loguru.

Import `logger` from this module anywhere in the codebase instead of
creating per-module `logging.getLogger(__name__)` instances, to keep log
formatting and configuration consistent across the whole backend.
"""

from __future__ import annotations

import sys

from loguru import logger

from utils.config import get_settings

_settings = get_settings()

logger.remove()
logger.add(
    sys.stderr,
    level=_settings.log_level.upper(),
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    ),
    backtrace=False,
    diagnose=False,
)

__all__ = ["logger"]
