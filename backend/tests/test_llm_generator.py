"""
Unit tests for llm/generator.py -- specifically the MockLLMProvider, since
that's what runs without an OpenAI API key (the default in this project
right now). These tests also verify the provider-selection factory logic.
"""

from __future__ import annotations

import llm.generator as generator_module
from llm.generator import MockLLMProvider, NO_EVIDENCE_ANSWER, SYSTEM_PROMPT
from rag.prompts import build_user_prompt


def test_mock_provider_returns_no_evidence_answer_for_empty_context():
    provider = MockLLMProvider()
    prompt = build_user_prompt("What treats a headache?", passages=[])
    response = provider.generate(SYSTEM_PROMPT, prompt)

    assert response.answer == NO_EVIDENCE_ANSWER
    assert response.provider == "mock"
    assert response.used_context is True


def test_mock_provider_extracts_top_passage_when_context_present():
    from rag.retriever import RetrievedPassage

    passage = RetrievedPassage(
        plant_id=1,
        common_name="Tulsi",
        botanical_name="Ocimum tenuiflorum",
        medicinal_properties="Antibacterial",
        traditional_uses="Herbal tea for cough",
        cultural_significance="Sacred plant",
        diseases_treated="Cough and cold",
        similarity_score=0.82,
    )
    prompt = build_user_prompt("What helps with a cough?", passages=[passage])

    provider = MockLLMProvider()
    response = provider.generate(SYSTEM_PROMPT, prompt)

    assert "Tulsi" in response.answer
    assert "mock mode" in response.answer.lower()


def test_build_provider_falls_back_to_mock_without_api_key(monkeypatch):
    from utils.config import Settings

    monkeypatch.setattr(
        generator_module,
        "get_settings",
        lambda: Settings(openai_api_key="", llm_provider="openai"),
    )
    generator_module._provider = None  # reset singleton cache

    provider = generator_module.get_provider()
    assert isinstance(provider, MockLLMProvider)

    generator_module._provider = None  # don't leak state into other tests
