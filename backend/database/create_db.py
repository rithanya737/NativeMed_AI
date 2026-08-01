"""
Creates the SQLite schema for NativeMed AI (plants.db).

Run directly to (re)create the database:

    python -m database.create_db

Schema
------
This schema was adapted to match NativeMed's actual source data (an Excel
export with one row per plant, where medicinal properties/traditional
uses/diseases are comma-separated free text) rather than the fully
normalized "one row per use" design originally sketched out. See
database/import_data.py for the ETL that populates these tables.

    plants
        plant_id                INTEGER PRIMARY KEY
        common_name              TEXT NOT NULL
        botanical_name           TEXT
        medicinal_properties     TEXT   -- comma-separated, e.g. "Antimicrobial, Astringent"
        traditional_uses         TEXT
        cultural_significance    TEXT
        diseases_treated         TEXT   -- comma-separated, e.g. "Gingivitis, Diarrhea"
        preparation_method       TEXT   -- how each traditional use is prepared (may be multi-line)
        how_to_take               TEXT   -- route/administration, e.g. "Oral (taken by mouth)"
        general_disclaimer       TEXT   -- standard traditional-use/not-medical-advice disclaimer

    botanical_synonyms
        synonym_id                  INTEGER PRIMARY KEY
        synonym_name                TEXT NOT NULL   -- alternate/common spelling, e.g. "AloeVera"
        canonical_botanical_name    TEXT NOT NULL   -- e.g. "Aloe barbadensis"
        plant_id                    INTEGER  -> plants.plant_id (nullable if unresolved)

    botanical_synonyms lets a plant-identification model (which typically
    outputs a botanical/scientific name guess) resolve name variants and
    misspellings back to a canonical plant_id for retrieval.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from utils.config import get_settings
from utils.logger import logger

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS plants (
        plant_id                INTEGER PRIMARY KEY,
        common_name              TEXT NOT NULL,
        botanical_name           TEXT,
        medicinal_properties     TEXT,
        traditional_uses         TEXT,
        cultural_significance    TEXT,
        diseases_treated         TEXT,
        preparation_method       TEXT,
        how_to_take              TEXT,
        general_disclaimer       TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS botanical_synonyms (
        synonym_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        synonym_name                TEXT NOT NULL,
        canonical_botanical_name    TEXT NOT NULL,
        plant_id                    INTEGER,
        FOREIGN KEY (plant_id) REFERENCES plants (plant_id) ON DELETE SET NULL
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_plants_botanical_name ON plants (botanical_name);",
    "CREATE INDEX IF NOT EXISTS idx_synonyms_synonym_name ON botanical_synonyms (synonym_name);",
    "CREATE INDEX IF NOT EXISTS idx_synonyms_plant_id ON botanical_synonyms (plant_id);",
]


def create_database(db_path: str | None = None) -> None:
    """Create plants.db and all tables/indexes if they don't already exist."""
    settings = get_settings()
    path = db_path or str(settings.resolved_database_path)

    logger.info(f"Creating/verifying SQLite schema at: {path}")
    if _ensure_parent_dir(path):
        logger.debug(f"Created parent directory for: {path}")

    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        cursor = conn.cursor()
        for statement in SCHEMA_STATEMENTS:
            cursor.execute(statement)
        conn.commit()
        logger.info("Schema created successfully (plants, botanical_synonyms).")
    finally:
        conn.close()


def _ensure_parent_dir(path: str) -> bool:
    parent = Path(path).parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=True)
        return True
    return False


if __name__ == "__main__":
    create_database()
