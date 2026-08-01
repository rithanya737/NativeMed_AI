"""
Retriever: embeds a user query, runs semantic search against ChromaDB, and
returns the top-K most relevant plant documents with similarity scores.

Workflow (per the NativeMed AI spec):

    User Question -> Embedding -> Semantic Search -> Top K documents

The SQLite database (plants.db) remains the source of truth; ChromaDB only
stores embeddings + a denormalized copy of each plant's text fields for
fast semantic search and for rendering retrieved passages without an extra
SQLite round-trip.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from utils.config import get_settings
from utils.exceptions import RetrievalError
from utils.logger import logger


@dataclass
class RetrievedPassage:
    """One retrieved plant document, plus its retrieval metadata."""

    plant_id: int
    common_name: str
    botanical_name: str | None
    medicinal_properties: str | None
    traditional_uses: str | None
    cultural_significance: str | None
    diseases_treated: str | None
    preparation_method: str | None = None
    how_to_take: str | None = None
    general_disclaimer: str | None = None
    synonyms: list[str] = field(default_factory=list)
    similarity_score: float = 0.0
    source: str = "NativeMed AI plant knowledge base"


def _get_collection():
    """Lazily open (not create) the persistent ChromaDB collection.

    Raises RetrievalError with a clear message if `rag.ingest.run_ingestion()`
    hasn't been run yet, instead of silently returning an empty collection.
    """
    import chromadb

    settings = get_settings()
    client = chromadb.PersistentClient(path=str(settings.resolved_vectorstore_path))

    try:
        collection = client.get_collection(settings.collection_name)
    except Exception as exc:
        raise RetrievalError(
            f"Vector store collection '{settings.collection_name}' not found. "
            "Run `python -m rag.ingest` first to embed and index the plant "
            "data before querying the retriever."
        ) from exc

    return collection


def retrieve(question: str, top_k: int | None = None) -> list[RetrievedPassage]:
    """Embed `question` and return the top-K most similar plant documents
    whose similarity score meets the configured minimum threshold.

    Returns an empty list (NOT an error) if nothing meets the threshold --
    the caller (rag/prompts.py + llm/generator.py) is responsible for
    surfacing the "not enough verified information" fallback in that case.
    """
    from rag.embeddings import embed_query

    settings = get_settings()
    k = top_k or settings.top_k_results

    if not question or not question.strip():
        raise RetrievalError("Cannot retrieve results for an empty question.")

    collection = _get_collection()

    try:
        query_embedding = embed_query(question)
    except Exception as exc:
        raise RetrievalError(
            f"Failed to embed the question for semantic search: {exc}"
        ) from exc

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k,
        include=["metadatas", "distances", "documents"],
    )

    ids = results.get("ids", [[]])[0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]

    passages: list[RetrievedPassage] = []
    for doc_id, distance, metadata in zip(ids, distances, metadatas):
        # ChromaDB's default space is squared-L2 for un-normalized vectors,
        # but rag/embeddings.py L2-normalizes all vectors, so cosine
        # similarity = 1 - (distance / 2) is the correct conversion here.
        similarity = max(0.0, 1.0 - (distance / 2.0))

        if similarity < settings.min_similarity_score:
            logger.debug(
                f"Dropping '{doc_id}' (similarity={similarity:.3f} < "
                f"threshold={settings.min_similarity_score})."
            )
            continue

        synonyms_raw = metadata.get("synonyms", "")
        passages.append(
            RetrievedPassage(
                plant_id=int(metadata.get("plant_id", -1)),
                common_name=metadata.get("common_name", "Unknown"),
                botanical_name=metadata.get("botanical_name") or None,
                medicinal_properties=metadata.get("medicinal_properties") or None,
                traditional_uses=metadata.get("traditional_uses") or None,
                cultural_significance=metadata.get("cultural_significance") or None,
                diseases_treated=metadata.get("diseases_treated") or None,
                preparation_method=metadata.get("preparation_method") or None,
                how_to_take=metadata.get("how_to_take") or None,
                general_disclaimer=metadata.get("general_disclaimer") or None,
                synonyms=[s for s in synonyms_raw.split("|") if s] if synonyms_raw else [],
                similarity_score=round(similarity, 4),
            )
        )

    logger.info(
        f"Retrieved {len(passages)}/{len(ids)} passages above threshold "
        f"{settings.min_similarity_score} for question: {question[:80]!r}"
    )
    return passages
