"""
Unit tests for rag/retriever.py.

ChromaDB and the embedding model are both mocked out so these tests run
fast and don't require the heavy ML dependencies (sentence-transformers,
chromadb) or a pre-built vector store to be present. The distance -> cosine
similarity math and the min-similarity-score filtering are exercised for
real.
"""

from __future__ import annotations

import pytest

from utils.exceptions import RetrievalError
import rag.retriever as retriever_module


class _FakeCollection:
    """Stands in for a ChromaDB Collection's .query() result shape."""

    def __init__(self, ids, distances, metadatas):
        self._ids = ids
        self._distances = distances
        self._metadatas = metadatas

    def query(self, query_embeddings, n_results, include):
        return {
            "ids": [self._ids],
            "distances": [self._distances],
            "metadatas": [self._metadatas],
        }


def _patch_collection(monkeypatch, collection):
    monkeypatch.setattr(retriever_module, "_get_collection", lambda: collection)


def _patch_embed_query(monkeypatch):
    # rag.retriever imports embed_query lazily inside retrieve(), so patch
    # the function where it actually lives.
    import rag.embeddings as embeddings_module

    monkeypatch.setattr(embeddings_module, "embed_query", lambda text: [0.0] * 384)


def test_retrieve_raises_on_empty_question(monkeypatch):
    _patch_embed_query(monkeypatch)
    with pytest.raises(RetrievalError):
        retriever_module.retrieve("   ")


def test_retrieve_raises_when_collection_missing(monkeypatch):
    _patch_embed_query(monkeypatch)

    def _boom():
        raise RetrievalError("Vector store collection not found.")

    monkeypatch.setattr(retriever_module, "_get_collection", _boom)

    with pytest.raises(RetrievalError):
        retriever_module.retrieve("What helps with a cough?")


def test_retrieve_converts_distance_to_similarity_and_filters_by_threshold(monkeypatch):
    _patch_embed_query(monkeypatch)

    metadata_close = {
        "plant_id": 1,
        "common_name": "Tulsi",
        "botanical_name": "Ocimum tenuiflorum",
        "medicinal_properties": "Antibacterial",
        "traditional_uses": "Herbal tea for cough",
        "cultural_significance": "Sacred plant",
        "diseases_treated": "Cough and cold",
        "synonyms": "Holy Basil|OcimumTenuiflorum",
    }
    metadata_far = {
        "plant_id": 2,
        "common_name": "Neem",
        "botanical_name": "Azadirachta indica",
        "medicinal_properties": "Antifungal",
        "traditional_uses": "Leaf paste for skin",
        "cultural_significance": "Ayurvedic staple",
        "diseases_treated": "Skin infections",
        "synonyms": "",
    }

    # distance 0.1 -> similarity 0.95 (kept); distance 1.9 -> similarity 0.05 (dropped
    # given the default min_similarity_score of 0.35 from .env.example).
    collection = _FakeCollection(
        ids=["plant_1", "plant_2"],
        distances=[0.1, 1.9],
        metadatas=[metadata_close, metadata_far],
    )
    _patch_collection(monkeypatch, collection)

    passages = retriever_module.retrieve("What helps with a cough?", top_k=2)

    assert len(passages) == 1
    top = passages[0]
    assert top.plant_id == 1
    assert top.common_name == "Tulsi"
    assert top.synonyms == ["Holy Basil", "OcimumTenuiflorum"]
    assert top.similarity_score == pytest.approx(0.95, abs=1e-6)


def test_retrieve_returns_empty_list_when_nothing_meets_threshold(monkeypatch):
    _patch_embed_query(monkeypatch)

    metadata = {
        "plant_id": 3,
        "common_name": "Unrelated Plant",
        "botanical_name": None,
        "medicinal_properties": None,
        "traditional_uses": None,
        "cultural_significance": None,
        "diseases_treated": None,
        "synonyms": "",
    }
    collection = _FakeCollection(ids=["plant_3"], distances=[2.0], metadatas=[metadata])
    _patch_collection(monkeypatch, collection)

    passages = retriever_module.retrieve("Completely unrelated question")
    assert passages == []
