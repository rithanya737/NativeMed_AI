"""
Reusable prompt templates for the RAG pipeline.

Keeping prompt construction in one place makes it easy to tune wording
without touching retriever/LLM code, and keeps the "Context:" / "Question:"
format that llm/generator.py's MockLLMProvider parses in sync with what's
actually sent to the real LLM.
"""

from __future__ import annotations

from rag.retriever import RetrievedPassage

NO_RELEVANT_CONTEXT_TEXT = "No relevant verified information was found in the knowledge base."

# Keywords that signal the user is actually asking how to prepare, dose, or
# take/apply a plant. Preparation/dosage details (and their safety
# disclaimer) are only ever surfaced in the LLM context when the question
# looks like one of these -- otherwise they're withheld even if the
# retrieved plant has them, per NativeMed's "only answer preparation
# questions when asked" requirement.
_PREPARATION_KEYWORDS = (
    "prepare", "preparation", "preparing", "make", "making", "brew",
    "brewing", "boil", "boiling", "steep", "steeping", "decoction",
    "infusion", "poultice", "paste", "extract", "how to take",
    "how do i take", "how should i take", "how to use", "how do i use",
    "how to apply", "how do i apply", "apply it", "take it", "dose",
    "dosage", "dosing", "how much", "administer", "administration",
    "consume", "ingest", "recipe", "instructions", "method", "directions",
    "how is it used", "how is it made", "how is it taken",
)


def is_preparation_question(question: str) -> bool:
    """Heuristic check for whether `question` is asking about preparation,
    dosage, or how to take/apply a plant (as opposed to e.g. what it treats
    or its cultural significance)."""
    lowered = (question or "").lower()
    return any(keyword in lowered for keyword in _PREPARATION_KEYWORDS)


def format_passage(passage: RetrievedPassage, index: int, include_preparation: bool = False) -> str:
    """Render one retrieved passage as human/LLM-readable text.

    `include_preparation` gates the preparation method / how-to-take /
    disclaimer fields -- they're only included when the user's question was
    actually about preparation, so the assistant doesn't volunteer
    dosing/preparation instructions for unrelated questions (e.g. "what does
    this plant treat?").
    """
    lines = [
        f"[Passage {index}] Plant: {passage.common_name} ({passage.botanical_name or 'unknown botanical name'})",
    ]
    if passage.synonyms:
        lines.append(f"Also known as: {', '.join(passage.synonyms)}")
    if passage.diseases_treated:
        lines.append(f"Diseases/conditions treated: {passage.diseases_treated}")
    if passage.medicinal_properties:
        lines.append(f"Medicinal properties: {passage.medicinal_properties}")
    if passage.traditional_uses:
        lines.append(f"Traditional uses: {passage.traditional_uses}")
    if passage.cultural_significance:
        lines.append(f"Cultural significance: {passage.cultural_significance}")
    if include_preparation:
        if passage.preparation_method:
            lines.append(f"Preparation method: {passage.preparation_method}")
        if passage.how_to_take:
            lines.append(f"How to take/apply: {passage.how_to_take}")
        if passage.general_disclaimer:
            lines.append(f"Disclaimer: {passage.general_disclaimer}")
    if passage.source:
        lines.append(f"Source: {passage.source}")

    return "\n".join(lines)


def build_context_block(passages: list[RetrievedPassage], question: str = "") -> str:
    if not passages:
        return NO_RELEVANT_CONTEXT_TEXT
    include_preparation = is_preparation_question(question)
    return "\n\n".join(
        format_passage(p, i + 1, include_preparation=include_preparation)
        for i, p in enumerate(passages)
    )


def build_user_prompt(question: str, passages: list[RetrievedPassage]) -> str:
    """Build the final prompt sent to the LLM: retrieved context + question.

    IMPORTANT: keep the literal "Context:" / "Question:" markers -- both
    OpenAIProvider and MockLLMProvider (see llm/generator.py) rely on this
    exact structure.
    """
    context_block = build_context_block(passages, question)
    return (
        f"Context:\n{context_block}\n\n"
        f"Question:\n{question}\n\n"
        "Answer the question using ONLY the context above. If the context is "
        "insufficient, say so explicitly using the required fallback sentence."
    )
