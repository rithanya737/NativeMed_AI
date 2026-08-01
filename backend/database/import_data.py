"""
Excel (.xlsx) -> SQLite importer for NativeMed AI's real dataset.

Reads:
    data/Cleaned_Medicinal_Plants_Dataset.xlsx   (source of truth for plants)
    data/synonym_mapping.xlsx                     (alt/common names -> canonical botanical name)

and loads them into the `plants.db` schema created by `create_db.py`.

Note on `Plant_Dataset.xlsx`: this is the raw, pre-cleaning export (145 rows,
some inconsistent capitalization/duplicate-ish entries vs. the 130-row
cleaned version). It is intentionally NOT imported -- the cleaned dataset is
treated as the single source of truth. If you want the raw file imported
too (e.g. to compare or recover dropped rows), tell me and I'll add a
`--include-raw` flag.

xlsx files are NEVER read at chatbot-inference time. This script is a
one-off (or re-run-on-demand) ETL step:

    xlsx files  --(this script)-->  SQLite (plants.db)

Expected columns
----------------
Cleaned_Medicinal_Plants_Dataset.xlsx:
    Plant Id, Plant Name, Botanical Name, Medicinal Properties,
    Traditional Uses, Cultural Significance, Diseases Treated,
    Preparation Method, How To Take / Apply, General Disclaimer

synonym_mapping.xlsx:
    Plant Name (Synonym), Botanical Name (Canonical)

Usage:
    python -m database.import_data --data-dir data
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

from database.create_db import create_database
from utils.config import get_settings
from utils.exceptions import CSVImportError
from utils.logger import logger

PLANTS_FILE = "Cleaned_Medicinal_Plants_Dataset.xlsx"
SYNONYMS_FILE = "synonym_mapping.xlsx"

PLANTS_REQUIRED_COLUMNS = {
    "Plant Id": "plant_id",
    "Plant Name": "common_name",
    "Botanical Name": "botanical_name",
    "Medicinal Properties": "medicinal_properties",
    "Traditional Uses": "traditional_uses",
    "Cultural Significance": "cultural_significance",
    "Diseases Treated": "diseases_treated",
    "Preparation Method": "preparation_method",
    "How To Take / Apply": "how_to_take",
    "General Disclaimer": "general_disclaimer",
}

SYNONYMS_REQUIRED_COLUMNS = {
    "Plant Name (Synonym)": "synonym_name",
    "Botanical Name (Canonical)": "canonical_botanical_name",
}


def _read_excel(path: Path, required_columns: dict[str, str]) -> pd.DataFrame:
    if not path.exists():
        raise CSVImportError(f"Required data file not found: {path}")
    try:
        df = pd.read_excel(path)
    except Exception as exc:  # corrupt file, wrong format, missing engine, etc.
        raise CSVImportError(f"Failed to read Excel file '{path}': {exc}") from exc

    missing = [c for c in required_columns if c not in df.columns]
    if missing:
        raise CSVImportError(
            f"'{path.name}' is missing required column(s) {missing}. "
            f"Found columns: {list(df.columns)}"
        )

    df = df.rename(columns=required_columns)
    return df[list(required_columns.values())]


def import_plants(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    cursor = conn.cursor()
    inserted = 0
    for _, row in df.iterrows():
        values = {
            "plant_id": int(row["plant_id"]),
            "common_name": str(row["common_name"]).strip(),
            "botanical_name": _clean(row["botanical_name"]),
            "medicinal_properties": _clean(row["medicinal_properties"]),
            "traditional_uses": _clean(row["traditional_uses"]),
            "cultural_significance": _clean(row["cultural_significance"]),
            "diseases_treated": _clean(row["diseases_treated"]),
            "preparation_method": _clean(row["preparation_method"]),
            "how_to_take": _clean(row["how_to_take"]),
            "general_disclaimer": _clean(row["general_disclaimer"]),
        }
        cursor.execute(
            """
            INSERT INTO plants
                (plant_id, common_name, botanical_name, medicinal_properties,
                 traditional_uses, cultural_significance, diseases_treated,
                 preparation_method, how_to_take, general_disclaimer)
            VALUES
                (:plant_id, :common_name, :botanical_name, :medicinal_properties,
                 :traditional_uses, :cultural_significance, :diseases_treated,
                 :preparation_method, :how_to_take, :general_disclaimer)
            """,
            values,
        )
        inserted += 1

    conn.commit()
    logger.info(f"Imported {inserted} rows into 'plants'.")
    return inserted


def import_synonyms(conn: sqlite3.Connection, df: pd.DataFrame) -> tuple[int, int]:
    """Insert botanical_synonyms rows, resolving each to a plant_id by
    matching canonical_botanical_name (case-insensitive) against
    plants.botanical_name. Unresolved synonyms are still stored (with
    plant_id = NULL) but logged as warnings, since they may still be useful
    once matching plant data is added later.
    """
    cursor = conn.cursor()
    resolved, unresolved = 0, 0

    for _, row in df.iterrows():
        synonym_name = str(row["synonym_name"]).strip()
        canonical_name = str(row["canonical_botanical_name"]).strip()

        match = conn.execute(
            "SELECT plant_id FROM plants WHERE LOWER(botanical_name) = LOWER(?)",
            (canonical_name,),
        ).fetchone()
        plant_id = match[0] if match else None

        if plant_id is None:
            unresolved += 1
            logger.warning(
                f"Synonym '{synonym_name}' -> '{canonical_name}' did not match any "
                "plant's botanical_name; storing with plant_id=NULL."
            )
        else:
            resolved += 1

        cursor.execute(
            """
            INSERT INTO botanical_synonyms (synonym_name, canonical_botanical_name, plant_id)
            VALUES (?, ?, ?)
            """,
            (synonym_name, canonical_name, plant_id),
        )

    conn.commit()
    logger.info(f"Imported {resolved + unresolved} synonyms ({resolved} resolved to a plant_id, {unresolved} unresolved).")
    return resolved, unresolved


def _clean(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def import_all(data_dir: str = "data", db_path: str | None = None) -> dict[str, int]:
    """Full ETL: create schema (if needed), then import plants + synonyms."""
    settings = get_settings()
    resolved_db_path = db_path or str(settings.resolved_database_path)
    data_path = Path(data_dir)

    logger.info(f"Starting data import from '{data_path}' into '{resolved_db_path}'")
    create_database(resolved_db_path)

    conn = sqlite3.connect(resolved_db_path)
    stats = {"plants": 0, "synonyms_resolved": 0, "synonyms_unresolved": 0}
    try:
        conn.execute("PRAGMA foreign_keys = ON;")

        plants_df = _read_excel(data_path / PLANTS_FILE, PLANTS_REQUIRED_COLUMNS)
        stats["plants"] = import_plants(conn, plants_df)

        synonyms_path = data_path / SYNONYMS_FILE
        if synonyms_path.exists():
            synonyms_df = _read_excel(synonyms_path, SYNONYMS_REQUIRED_COLUMNS)
            resolved, unresolved = import_synonyms(conn, synonyms_df)
            stats["synonyms_resolved"] = resolved
            stats["synonyms_unresolved"] = unresolved
        else:
            logger.warning(f"'{SYNONYMS_FILE}' not found; skipping synonym import.")

        logger.info(f"Data import complete: {stats}")
        return stats
    finally:
        conn.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import NativeMed AI Excel data into SQLite.")
    parser.add_argument("--data-dir", default="data", help="Directory containing the .xlsx files.")
    parser.add_argument("--db-path", default=None, help="Override the SQLite database path.")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    import_all(data_dir=args.data_dir, db_path=args.db_path)
