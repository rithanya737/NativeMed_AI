"""
Unit tests for api/routes.py using FastAPI's TestClient.

Every external dependency of the pipeline (translation, retrieval, the LLM,
text-to-speech, speech-to-text, the database) is monkeypatched so these
tests run fast, deterministically, and without needing the real ChromaDB
vector store, network access, or an OpenAI API key.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.routes as routes_module
from app import app
from rag.retriever import RetrievedPassage
from translation.translator import DetectionResult
from utils.exceptions import PlantNotFoundError, RetrievalError


client = TestClient(app)


def _sample_passage() -> RetrievedPassage:
    return RetrievedPassage(
        plant_id=1,
        common_name="Tulsi",
        botanical_name="Ocimum tenuiflorum",
        medicinal_properties="Antibacterial, Anti-inflammatory",
        traditional_uses="Boiled into herbal tea for coughs and colds",
        cultural_significance="Sacred plant in many South Asian households",
        diseases_treated="Cough and cold, Respiratory infections",
        synonyms=["Holy Basil"],
        similarity_score=0.9,
    )


def _patch_happy_path(monkeypatch, passages, language_code="en"):
    monkeypatch.setattr(
        routes_module,
        "translate_to_english",
        lambda text: (DetectionResult(language_code, "English" if language_code == "en" else "Other", 0.99), text),
    )
    monkeypatch.setattr(routes_module, "retrieve", lambda question, top_k=None: passages)
    monkeypatch.setattr(routes_module, "build_user_prompt", lambda q, p: "Context:\n...\n\nQuestion:\n" + q)

    class _FakeLLMResponse:
        answer = "Tulsi (Holy Basil) is traditionally used for cough and cold."

    monkeypatch.setattr(routes_module, "generate_answer", lambda prompt: _FakeLLMResponse())
    monkeypatch.setattr(routes_module, "translate_from_english", lambda text, lang: f"[{lang}] {text}")
    monkeypatch.setattr(routes_module, "synthesize_speech", lambda text, lang: f"/tmp/fake_{lang}.mp3")


def test_health_endpoint_reports_mock_llm_and_readiness_flags(monkeypatch):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["llm_provider"] in {"mock", "openai"}
    assert "database_ready" in body
    assert "vectorstore_ready" in body


def test_chat_endpoint_happy_path_english(monkeypatch):
    _patch_happy_path(monkeypatch, [_sample_passage()], language_code="en")

    response = client.post("/chat", json={"question": "What helps with a cough?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["language"] == "en"
    assert body["translated_answer"] is None
    assert body["sources"] == ["Tulsi (Ocimum tenuiflorum)"]
    assert body["confidence_label"] == "high"
    # /chat intentionally skips TTS (synthesize_audio=False) -- chat.js never
    # reads audio_path, so generating it was a wasted network call to
    # Google's TTS on every message. See _run_chat_pipeline's docstring.
    assert body["audio_path"] is None


def test_chat_endpoint_never_calls_synthesize_speech(monkeypatch):
    """Regression guard for the /chat TTS-skip optimization: fails loudly if
    something reintroduces a synthesize_speech() call on the text chat path."""
    _patch_happy_path(monkeypatch, [_sample_passage()], language_code="en")

    calls = []
    monkeypatch.setattr(
        routes_module, "synthesize_speech", lambda text, lang: calls.append((text, lang)) or "/tmp/should-not-be-called.mp3"
    )

    response = client.post("/chat", json={"question": "What helps with a cough?"})
    assert response.status_code == 200
    assert calls == []


def test_chat_endpoint_forces_fallback_when_no_passages_retrieved(monkeypatch):
    _patch_happy_path(monkeypatch, [], language_code="en")

    response = client.post("/chat", json={"question": "Something totally unrelated"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == routes_module.NO_EVIDENCE_ANSWER
    assert body["confidence_label"] == "none"
    assert body["retrieved_passages"] == []


def test_chat_endpoint_translates_for_non_english_language(monkeypatch):
    _patch_happy_path(monkeypatch, [_sample_passage()], language_code="ta")

    response = client.post("/chat", json={"question": "இருமலுக்கு என்ன உதவும்?"})
    assert response.status_code == 200
    body = response.json()
    assert body["language"] == "ta"
    assert body["translated_question"] is not None
    assert body["translated_answer"].startswith("[ta]")
    # Same TTS-skip as the English case above -- /chat never synthesizes audio.
    assert body["audio_path"] is None


def test_chat_endpoint_maps_retrieval_error_to_503(monkeypatch):
    def _boom(question, top_k=None):
        raise RetrievalError("Vector store not built yet.")

    monkeypatch.setattr(
        routes_module,
        "translate_to_english",
        lambda text: (DetectionResult("en", "English", 0.99), text),
    )
    monkeypatch.setattr(routes_module, "retrieve", _boom)

    response = client.post("/chat", json={"question": "What helps with a cough?"})
    assert response.status_code == 503
    assert response.json()["detail"]["error_type"] == "RetrievalError"


def test_chat_endpoint_rejects_empty_question():
    response = client.post("/chat", json={"question": ""})
    assert response.status_code == 422


def test_tts_endpoint_happy_path(monkeypatch):
    monkeypatch.setattr(routes_module, "synthesize_speech", lambda text, lang: f"/tmp/fake_{lang}.mp3")

    response = client.post("/tts", json={"text": "Hello there", "language": "en"})
    assert response.status_code == 200
    body = response.json()
    assert body["audio_path"] == "/tmp/fake_en.mp3"
    assert body["language"] == "en"


def test_get_plant_endpoint_happy_path(monkeypatch):
    fake_plant = {
        "plant_id": 1,
        "common_name": "Tulsi",
        "botanical_name": "Ocimum tenuiflorum",
        "medicinal_properties": "Antibacterial, Anti-inflammatory",
        "traditional_uses": "Boiled into herbal tea for coughs and colds",
        "cultural_significance": "Sacred plant in many South Asian households",
        "diseases_treated": "Cough and cold, Respiratory infections",
        "medicinal_properties_list": ["Antibacterial", "Anti-inflammatory"],
        "diseases_treated_list": ["Cough and cold", "Respiratory infections"],
        "synonyms": ["Holy Basil"],
    }
    monkeypatch.setattr(routes_module, "get_plant_by_id", lambda plant_id: fake_plant)

    response = client.get("/plants/1")
    assert response.status_code == 200
    assert response.json()["common_name"] == "Tulsi"


def test_get_plant_endpoint_returns_404_when_missing(monkeypatch):
    def _boom(plant_id):
        raise PlantNotFoundError(f"No plant with id {plant_id}")

    monkeypatch.setattr(routes_module, "get_plant_by_id", _boom)

    response = client.get("/plants/9999")
    assert response.status_code == 404
    assert response.json()["detail"]["error_type"] == "PlantNotFoundError"
