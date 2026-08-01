"""
Deprecated entrypoint, kept only for backwards compatibility.

Everything that used to live here (the plant-identification router) has
been merged into `app.py`, which now serves both the chatbot API and the
plant-identification API from one combined app. Run the server with:

    uvicorn app:app --reload --port 8000

This module just re-exports that same `app` object so any existing scripts
or shortcuts still pointing at `uvicorn main:app` keep working unchanged.
"""
# main.py — kept only for backwards compatibility
from app import app