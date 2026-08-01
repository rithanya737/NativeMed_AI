"""Thin HTTP client wrapping the FastAPI backend's API.

Every Flask route that needs backend data goes through this module instead
of calling `requests` directly and instead of hardcoding the backend's URL.
Centralizing this here means:

  * There is exactly one place that knows the backend's base URL
    (see `config.py`, via `BACKEND_API_URL`).
  * Every caller gets the same, friendly error handling when the backend is
    unreachable or returns an error, instead of an unhandled exception
    bubbling up into a Flask 500 page.

Every function returns a plain `(data, error)` tuple:
    data  -- parsed JSON response (dict/list) on success, otherwise None
    error -- None on success, otherwise a short, user-friendly string
             describing what went wrong (safe to show directly in the UI)

This keeps calling code simple:

    plants, error = list_plants()
    if error:
        flash(error)
        plants = []
"""

from __future__ import annotations

from typing import Any

import requests

from config import BACKEND_API_URL, BACKEND_REQUEST_TIMEOUT

_UNREACHABLE_MESSAGE = (
    "The NativeMed AI backend isn't reachable right now. Please make sure "
    "it's running and try again in a moment."
)


def _get(path: str, params: dict[str, Any] | None = None) -> tuple[Any | None, str | None]:
    try:
        response = requests.get(
            f"{BACKEND_API_URL}{path}", params=params, timeout=BACKEND_REQUEST_TIMEOUT
        )
    except requests.exceptions.ConnectionError:
        return None, _UNREACHABLE_MESSAGE
    except requests.exceptions.Timeout:
        return None, "The backend took too long to respond. Please try again."
    except requests.exceptions.RequestException as exc:
        return None, f"Unexpected error contacting the backend: {exc}"

    return _handle_response(response)


def _post(
    path: str,
    json: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
) -> tuple[Any | None, str | None]:
    try:
        response = requests.post(
            f"{BACKEND_API_URL}{path}",
            json=json,
            files=files,
            timeout=BACKEND_REQUEST_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        return None, _UNREACHABLE_MESSAGE
    except requests.exceptions.Timeout:
        return None, "The backend took too long to respond. Please try again."
    except requests.exceptions.RequestException as exc:
        return None, f"Unexpected error contacting the backend: {exc}"

    return _handle_response(response)


def _handle_response(response: requests.Response) -> tuple[Any | None, str | None]:
    if response.ok:
        try:
            return response.json(), None
        except ValueError:
            return None, "The backend returned an unexpected (non-JSON) response."

    # Try to surface the backend's own structured error detail, falling back
    # to a generic message keyed off the HTTP status code.
    detail = None
    try:
        payload = response.json()
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, dict):
                detail = detail.get("detail")
    except ValueError:
        pass

    if response.status_code == 404:
        return None, detail or "The requested item was not found."
    if response.status_code >= 500:
        return None, detail or "The backend hit an internal error. Please try again shortly."
    return None, detail or f"The backend rejected the request (HTTP {response.status_code})."


def check_health() -> tuple[dict[str, Any] | None, str | None]:
    """GET /health -- backend liveness/readiness."""
    return _get("/health")


def list_plants(query: str | None = None, limit: int = 500, offset: int = 0):
    """GET /plants -- list every plant, or search with `query`."""
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if query:
        params["q"] = query
    return _get("/plants", params=params)


def get_plant(plant_id: int):
    """GET /plants/{plant_id} -- a single plant's full record."""
    return _get(f"/plants/{plant_id}")


def lookup_plant_by_name(name: str):
    """GET /plants/lookup -- resolve a raw ML-model label to a plant record."""
    return _get("/plants/lookup", params={"name": name})


def send_chat_message(question: str, top_k: int | None = None):
    """POST /chat -- ask the RAG-powered herbal assistant a question."""
    payload: dict[str, Any] = {"question": question}
    if top_k:
        payload["top_k"] = top_k
    return _post("/chat", json=payload)


def identify_plant(file_storage) -> tuple[dict[str, Any] | None, str | None]:
    """POST /api/identify-plant -- run the RF-DETR plant-ID model on an
    uploaded image (a Werkzeug/Flask `FileStorage` object)."""
    files = {
        "file": (
            file_storage.filename or "upload.jpg",
            file_storage.stream,
            file_storage.mimetype or "application/octet-stream",
        )
    }
    return _post("/api/identify-plant", files=files)
