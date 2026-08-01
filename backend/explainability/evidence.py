"""
Explainable AI: packages retrieval evidence alongside the LLM's answer so
every /chat response is auditable -- the caller can always see exactly
which passages were retrieved, how similar each one was to the question,
and where each piece of information came from.

Confidence is deliberately derived ONLY from retrieval similarity scores,
never from the LLM's own (unreliable) self-reported certainty.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rag.prompts import is_preparation_question
from rag.retriever import RetrievedPassage


@dataclass
class Evidence:
    sources: list[str]
    retrieved_passages: list[dict]
    similarity_scores: list[float]
    confidence_label: str
    confidence_score: float
    used_context: bool = field(default=True)


def _confidence_label(top_score: float) -> str:
    """Map a top similarity score to a coarse, human-readable confidence
    label. Thresholds are intentionally conservative -- this reflects
    retrieval similarity, not a guarantee of medical accuracy.
    """
    if top_score >= 0.75:
        return "high"
    if top_score >= 0.55:
        return "medium"
    if top_score > 0.0:
        return "low"
    return "none"


def build_evidence(passages: list[RetrievedPassage], question: str = "") -> Evidence:
    """Build the explainability payload from a list of retrieved passages
    (already filtered to the configured similarity threshold upstream in
    rag/retriever.py).

    `question` gates the preparation_method / how_to_take / general_disclaimer
    fields in each passage the same way rag/prompts.py gates them for the
    LLM's context -- they're only surfaced (here, in the "sources" evidence
    panel) when the user actually asked about preparation/dosage, so the
    citation panel never volunteers dosing info for an unrelated question.
    """
    if not passages:
        return Evidence(
            sources=[],
            retrieved_passages=[],
            similarity_scores=[],
            confidence_label="none",
            confidence_score=0.0,
            used_context=False,
        )

    include_preparation = is_preparation_question(question)

    sources = [
        f"{p.common_name} ({p.botanical_name})" if p.botanical_name else p.common_name
        for p in passages
    ]
    similarity_scores = [p.similarity_score for p in passages]
    retrieved_passages = [
        {
            "plant_id": p.plant_id,
            "common_name": p.common_name,
            "botanical_name": p.botanical_name,
            "diseases_treated": p.diseases_treated,
            "medicinal_properties": p.medicinal_properties,
            "traditional_uses": p.traditional_uses,
            "cultural_significance": p.cultural_significance,
            "preparation_method": p.preparation_method if include_preparation else None,
            "how_to_take": p.how_to_take if include_preparation else None,
            "general_disclaimer": p.general_disclaimer if include_preparation else None,
            "synonyms": p.synonyms,
            "similarity_score": p.similarity_score,
            "source": p.source,
        }
        for p in passages
    ]

    top_score = max(similarity_scores)
    return Evidence(
        sources=sources,
        retrieved_passages=retrieved_passages,
        similarity_scores=similarity_scores,
        confidence_label=_confidence_label(top_score),
        confidence_score=round(top_score, 4),
        used_context=True,
    )
