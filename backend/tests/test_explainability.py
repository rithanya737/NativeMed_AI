"""Unit tests for explainability/evidence.py."""

from __future__ import annotations

from explainability.evidence import build_evidence
from rag.retriever import RetrievedPassage


def test_build_evidence_empty_passages():
    evidence = build_evidence([])
    assert evidence.sources == []
    assert evidence.retrieved_passages == []
    assert evidence.similarity_scores == []
    assert evidence.confidence_label == "none"
    assert evidence.confidence_score == 0.0
    assert evidence.used_context is False


def test_build_evidence_with_passages_high_confidence():
    passages = [
        RetrievedPassage(
            plant_id=1,
            common_name="Tulsi",
            botanical_name="Ocimum tenuiflorum",
            medicinal_properties="Antibacterial",
            traditional_uses="Herbal tea",
            cultural_significance="Sacred plant",
            diseases_treated="Cough and cold",
            similarity_score=0.81,
        ),
        RetrievedPassage(
            plant_id=2,
            common_name="Neem",
            botanical_name="Azadirachta indica",
            medicinal_properties="Antifungal",
            traditional_uses="Leaf paste",
            cultural_significance="Ayurvedic staple",
            diseases_treated="Skin infections",
            similarity_score=0.60,
        ),
    ]

    evidence = build_evidence(passages)

    assert evidence.sources == ["Tulsi (Ocimum tenuiflorum)", "Neem (Azadirachta indica)"]
    assert evidence.similarity_scores == [0.81, 0.60]
    assert evidence.confidence_label == "high"  # top score 0.81 >= 0.75
    assert evidence.confidence_score == 0.81
    assert evidence.used_context is True
    assert len(evidence.retrieved_passages) == 2
    assert evidence.retrieved_passages[0]["common_name"] == "Tulsi"


def test_build_evidence_confidence_labels_by_threshold():
    def passage_with_score(score: float) -> RetrievedPassage:
        return RetrievedPassage(
            plant_id=1,
            common_name="X",
            botanical_name="Y",
            medicinal_properties=None,
            traditional_uses=None,
            cultural_significance=None,
            diseases_treated=None,
            similarity_score=score,
        )

    assert build_evidence([passage_with_score(0.9)]).confidence_label == "high"
    assert build_evidence([passage_with_score(0.6)]).confidence_label == "medium"
    assert build_evidence([passage_with_score(0.4)]).confidence_label == "low"
