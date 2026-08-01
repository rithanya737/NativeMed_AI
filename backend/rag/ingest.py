"""
Ingestion: SQLite (plants.db) -> embeddings -> ChromaDB.

Run directly to (re)build the vector index:

    python -m rag.ingest

Workflow (per the NativeMed AI spec):

    CSV/Excel -> SQLite -> Embedding generation -> Vector database -> Retriever -> LLM

This script performs the "Embedding generation -> Vector database" step.
SQLite remains the single source of truth; re-running this script simply
wipes and rebuilds the ChromaDB collection from whatever is currently in
plants.db, so it's always safe to re-run after re-importing data.
"""

from __future__ import annotations

from database.database import fetch_all_documents_for_ingestion
from rag.embeddings import embed_documents
from utils.config import get_settings
from utils.logger import logger


def _document_to_text(doc: dict) -> str:
    """Build the plain-text representation of a plant that gets embedded.

    Includes every searchable field so that a query about a disease, a
    medicinal property, a traditional use, or even a common-name synonym
    can all surface this document.
    """
    parts = [
        f"Plant: {doc['common_name']}",
    ]
    if doc.get("botanical_name"):
        parts.append(f"Botanical name: {doc['botanical_name']}")
    if doc.get("synonyms"):
        parts.append(f"Also known as: {', '.join(doc['synonyms'])}")
    if doc.get("diseases_treated"):
        parts.append(f"Diseases treated: {doc['diseases_treated']}")
    if doc.get("medicinal_properties"):
        parts.append(f"Medicinal properties: {doc['medicinal_properties']}")
    if doc.get("traditional_uses"):
        parts.append(f"Traditional uses: {doc['traditional_uses']}")
    if doc.get("cultural_significance"):
        parts.append(f"Cultural significance: {doc['cultural_significance']}")
    if doc.get("preparation_method"):
        parts.append(f"Preparation method: {doc['preparation_method']}")
    if doc.get("how_to_take"):
        parts.append(f"How to take/apply: {doc['how_to_take']}")
    if doc.get("general_disclaimer"):
        parts.append(f"Disclaimer: {doc['general_disclaimer']}")

    return "\n".join(parts)


def _document_to_metadata(doc: dict) -> dict:
    """Flatten a document into ChromaDB-compatible metadata (str/int/float/bool only)."""
    return {
        "plant_id": doc["plant_id"],
        "common_name": doc["common_name"] or "",
        "botanical_name": doc.get("botanical_name") or "",
        "medicinal_properties": doc.get("medicinal_properties") or "",
        "traditional_uses": doc.get("traditional_uses") or "",
        "cultural_significance": doc.get("cultural_significance") or "",
        "diseases_treated": doc.get("diseases_treated") or "",
        "preparation_method": doc.get("preparation_method") or "",
        "how_to_take": doc.get("how_to_take") or "",
        "general_disclaimer": doc.get("general_disclaimer") or "",
        # ChromaDB metadata values must be scalars, so synonyms are joined
        # with "|" and split back out again in rag/retriever.py.
        "synonyms": "|".join(doc.get("synonyms") or []),
    }


def run_ingestion(db_path: str | None = None, batch_size: int = 64) -> int:
    """Fetch all plant documents from SQLite, embed them, and (re)build the
    persistent ChromaDB collection. Returns the number of documents indexed.
    """
    settings = get_settings()

    documents = fetch_all_documents_for_ingestion(db_path)
    if not documents:
        logger.warning(
            "No documents found in plants.db to ingest. Run "
            "`python -m database.import_data` first."
        )
        return 0

    import chromadb

    client = chromadb.PersistentClient(path=str(settings.resolved_vectorstore_path))

    # Drop and recreate so re-running this script always reflects the
    # current contents of plants.db (no stale/duplicate entries).
    try:
        client.delete_collection(settings.collection_name)
        logger.info(f"Dropped existing collection '{settings.collection_name}'.")
    except Exception:
        pass  # collection didn't exist yet -- that's fine

    collection = client.create_collection(
        name=settings.collection_name,
        metadata={"hnsw:space": "l2"},
    )

    total_indexed = 0
    for start in range(0, len(documents), batch_size):
        batch = documents[start : start + batch_size]

        ids = [doc["doc_id"] for doc in batch]
        texts = [_document_to_text(doc) for doc in batch]
        metadatas = [_document_to_metadata(doc) for doc in batch]
        embeddings = embed_documents(texts)

        collection.add(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
        total_indexed += len(batch)
        logger.info(f"Indexed {total_indexed}/{len(documents)} documents...")

    logger.info(
        f"Ingestion complete: {total_indexed} plant documents embedded into "
        f"collection '{settings.collection_name}' at '{settings.resolved_vectorstore_path}'."
    )
    return total_indexed


if __name__ == "__main__":
    run_ingestion()
