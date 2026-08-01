"""Centralized frontend configuration.

Single place to configure the FastAPI backend's base URL so it is never
hardcoded in multiple files. Override via the `BACKEND_API_URL` environment
variable (e.g. in a `.env` file loaded by `python-dotenv`, or exported in
your shell) when the backend runs somewhere other than the default.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Load a frontend/.env file if present, without overriding variables that
# are already set in the real environment (e.g. by the hosting platform).
load_dotenv()

# Base URL of the FastAPI backend (see backend/app.py). Defaults to the
# standard local dev address used in backend/app.py's docstring
# (`uvicorn app:app --reload --port 8000`).
BACKEND_API_URL = os.environ.get("BACKEND_API_URL", "http://127.0.0.1:8000").rstrip("/")

# How long (seconds) the frontend will wait for the backend before treating
# it as unreachable. Chat/LLM calls can be slow, so this is generous.
BACKEND_REQUEST_TIMEOUT = float(os.environ.get("BACKEND_REQUEST_TIMEOUT", "60"))

# Flask's own secret key (session signing, flash messages, etc.). Must be
# supplied via environment variable in production -- never hardcode secrets
# in source. A random per-process fallback is used for local dev only so
# the app still runs out of the box.
SECRET_KEY = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24).hex()
