"""
SQLite connection helpers and read/write data-access functions.

SQLite is treated as the single source of truth for structured plant data.
The RAG pipeline (rag/ingest.py) reads from here to build the vector index,
but never writes back to it.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from utils.config import get_settings
from utils.exceptions import DatabaseError, PlantNotFoundError
from utils.logger import logger


def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    fields = [column[0] for column in cursor.description]
    return dict(zip(fields, row))


@contextmanager
def get_connection(db_path: str | None = None) -> Iterator[sqlite3.Connection]:
    """Context-managed SQLite connection with foreign keys enabled.

    Usage:
        with get_connection() as conn:
            conn.execute(...)
    """
    settings = get_settings()
    path = db_path or str(settings.resolved_database_path)

    if not Path(path).exists():
        raise DatabaseError(
            f"Database not found at '{path}'. Run `python -m database.create_db` "
            "and `python -m database.import_data` first."
        )

    conn = sqlite3.connect(path)
    conn.row_factory = _dict_factory
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        yield conn
    except sqlite3.Error as exc:
        logger.error(f"SQLite error: {exc}")
        raise DatabaseError(str(exc)) from exc
    finally:
        conn.close()


def _split_list_field(value: str | None) -> list[str]:
    """Split a comma-separated free-text field (e.g. 'Gingivitis, Diarrhea,
    Eczema') into a clean list of individual items."""
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def get_plant_by_id(plant_id: int, db_path: str | None = None) -> dict[str, Any]:
    """Fetch a single plant plus its known name synonyms, and split its
    comma-separated fields into lists for easier API consumption.
    """
    with get_connection(db_path) as conn:
        plant = conn.execute(
            "SELECT * FROM plants WHERE plant_id = ?", (plant_id,)
        ).fetchone()

        if plant is None:
            raise PlantNotFoundError(f"No plant found with plant_id={plant_id}")

        synonyms = conn.execute(
            "SELECT synonym_name, canonical_botanical_name FROM botanical_synonyms "
            "WHERE plant_id = ?",
            (plant_id,),
        ).fetchall()

        return {
            **plant,
            "medicinal_properties_list": _split_list_field(plant.get("medicinal_properties")),
            "diseases_treated_list": _split_list_field(plant.get("diseases_treated")),
            "synonyms": [s["synonym_name"] for s in synonyms],
        }


def find_plant_by_botanical_name(name: str, db_path: str | None = None) -> dict[str, Any] | None:
    """Look up a plant by exact (case-insensitive) botanical name match, or
    via the botanical_synonyms table if the name is a known synonym/alias.
    Used to resolve output from an external plant-identification model.
    """
    normalized = name.strip().lower()
    with get_connection(db_path) as conn:
        plant = conn.execute(
            "SELECT * FROM plants WHERE LOWER(botanical_name) = ?", (normalized,)
        ).fetchone()
        if plant:
            return plant

        synonym = conn.execute(
            "SELECT plant_id FROM botanical_synonyms WHERE LOWER(synonym_name) = ? "
            "AND plant_id IS NOT NULL",
            (normalized,),
        ).fetchone()
        if synonym:
            return conn.execute(
                "SELECT * FROM plants WHERE plant_id = ?", (synonym["plant_id"],)
            ).fetchone()

        return None


def _normalize_name(name: str) -> str:
    """Normalize a plant name for fuzzy matching: lowercase, collapse
    underscores/hyphens to spaces, collapse repeated whitespace."""
    return " ".join(name.replace("_", " ").replace("-", " ").split()).strip().lower()


def find_plant_by_any_name(name: str, db_path: str | None = None) -> dict[str, Any] | None:
    """Resolve a plant-identification-model label (e.g. 'AloeVera',
    'Aquatic-Ginger', 'Tulsi') to a full plant record.

    Tries, in order: exact common-name match, exact botanical-name match,
    exact synonym match, then the same three again after normalizing
    underscores/hyphens/whitespace/case (to handle model label variants
    like 'Aquatic-Ginger' vs. a dataset entry of 'Aquatic Ginger'), and
    finally falls back to a loose substring match on common_name.
    Returns None if nothing reasonably matches.
    """
    if not name or not name.strip():
        return None

    with get_connection(db_path) as conn:

        def _by_common(value: str) -> dict[str, Any] | None:
            return conn.execute(
                "SELECT * FROM plants WHERE LOWER(common_name) = LOWER(?)", (value,)
            ).fetchone()

        def _by_botanical(value: str) -> dict[str, Any] | None:
            return conn.execute(
                "SELECT * FROM plants WHERE LOWER(botanical_name) = LOWER(?)", (value,)
            ).fetchone()

        def _by_synonym(value: str) -> dict[str, Any] | None:
            row = conn.execute(
                "SELECT plant_id FROM botanical_synonyms WHERE LOWER(synonym_name) = LOWER(?) "
                "AND plant_id IS NOT NULL",
                (value,),
            ).fetchone()
            if not row:
                return None
            return conn.execute(
                "SELECT * FROM plants WHERE plant_id = ?", (row["plant_id"],)
            ).fetchone()

        for candidate in (name, _normalize_name(name)):
            plant = _by_common(candidate) or _by_botanical(candidate) or _by_synonym(candidate)
            if plant:
                return plant

        # Last resort: loose substring match either direction.
        normalized = _normalize_name(name)
        loose = conn.execute(
            "SELECT * FROM plants WHERE LOWER(common_name) LIKE ? OR ? LIKE '%' || LOWER(common_name) || '%'",
            (f"%{normalized}%", normalized),
        ).fetchone()
        return loose


def list_plants(limit: int = 100, offset: int = 0, db_path: str | None = None) -> list[dict[str, Any]]:
    """List plants (paginated), used for admin/debug and RAG ingestion."""
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM plants ORDER BY plant_id LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return rows


def search_plants(
    query: str | None = None,
    limit: int = 500,
    offset: int = 0,
    db_path: str | None = None,
) -> list[dict[str, Any]]:
    """List/search plants for frontend features (Explore Herb gallery, the
    dashboard's herb count, and the search box).

    With no `query`, returns every plant (used to populate the Explore Herb
    gallery / dashboard stats). With a `query`, performs a case-insensitive
    substring match across common name, botanical name, medicinal
    properties, traditional uses and diseases treated -- as well as any
    known synonym -- so a search for a disease or a common misspelling
    still surfaces the right plant.
    """
    with get_connection(db_path) as conn:
        if not query or not query.strip():
            rows = conn.execute(
                "SELECT * FROM plants ORDER BY common_name LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        else:
            like = f"%{query.strip()}%"
            rows = conn.execute(
                """
                SELECT DISTINCT p.* FROM plants p
                LEFT JOIN botanical_synonyms s ON s.plant_id = p.plant_id
                WHERE p.common_name LIKE ? COLLATE NOCASE
                   OR p.botanical_name LIKE ? COLLATE NOCASE
                   OR p.medicinal_properties LIKE ? COLLATE NOCASE
                   OR p.traditional_uses LIKE ? COLLATE NOCASE
                   OR p.diseases_treated LIKE ? COLLATE NOCASE
                   OR s.synonym_name LIKE ? COLLATE NOCASE
                ORDER BY p.common_name
                LIMIT ? OFFSET ?
                """,
                (like, like, like, like, like, like, limit, offset),
            ).fetchall()

        return [
            {
                **row,
                "medicinal_properties_list": _split_list_field(row.get("medicinal_properties")),
                "diseases_treated_list": _split_list_field(row.get("diseases_treated")),
            }
            for row in rows
        ]


def fetch_all_documents_for_ingestion(db_path: str | None = None) -> list[dict[str, Any]]:
    """Build one RAG document per plant, including its known synonyms.

    This is exactly what rag/ingest.py embeds and stores in ChromaDB.
    One document per plant (rather than one per disease) matches the grain
    of the real dataset, where medicinal properties/uses/diseases are
    comma-separated free text on a single plant row.
    """
    with get_connection(db_path) as conn:
        plants = conn.execute("SELECT * FROM plants ORDER BY plant_id").fetchall()
        documents: list[dict[str, Any]] = []

        for plant in plants:
            synonyms = conn.execute(
                "SELECT synonym_name FROM botanical_synonyms WHERE plant_id = ?",
                (plant["plant_id"],),
            ).fetchall()

            documents.append(
                {
                    "doc_id": f"plant_{plant['plant_id']}",
                    "plant_id": plant["plant_id"],
                    "common_name": plant["common_name"],
                    "botanical_name": plant["botanical_name"],
                    "medicinal_properties": plant["medicinal_properties"],
                    "traditional_uses": plant["traditional_uses"],
                    "cultural_significance": plant["cultural_significance"],
                    "diseases_treated": plant["diseases_treated"],
                    "preparation_method": plant.get("preparation_method"),
                    "how_to_take": plant.get("how_to_take"),
                    "general_disclaimer": plant.get("general_disclaimer"),
                    "synonyms": [s["synonym_name"] for s in synonyms],
                }
            )

        return documents
