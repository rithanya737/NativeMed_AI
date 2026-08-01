"""
Shared sentence-embedding model wrapper (BAAI/bge-small-en-v1.5 by default).

Both rag/ingest.py (embedding documents) and rag/retriever.py (embedding
queries) go through this module so the model is loaded exactly once (it's
~130MB and takes a moment to load) and so the BGE-recommended query prefix
is applied consistently.
"""

from __future__ import annotations

from functools import lru_cache

from utils.config import get_settings
from utils.logger import logger

# BAAI/bge-* models recommend prefixing *queries* (but not documents) with
# this instruction for asymmetric retrieval -- it measurably improves
# retrieval quality for these models.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


@lru_cache
def _load_model():
    from sentence_transformers import SentenceTransformer

    settings = get_settings()
    logger.info(f"Loading embedding model '{settings.embedding_model}' (first call only)...")
    model = SentenceTransformer(settings.embedding_model)
    logger.info("Embedding model loaded.")
    return model


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch of documents (no query instruction prefix)."""
    model = _load_model()
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return embeddings.tolist()


def embed_query(text: str) -> list[float]:
    """Embed a single user query (with the BGE query instruction prefix)."""
    model = _load_model()
    embedding = model.encode(
        BGE_QUERY_INSTRUCTION + text, normalize_embeddings=True, show_progress_bar=False
    )
    return embedding.tolist()
