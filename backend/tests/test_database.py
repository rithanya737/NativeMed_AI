"""
Unit tests for database/create_db.py, database/import_data.py and
database/database.py.

These tests generate tiny synthetic .xlsx files on the fly (in pytest's
tmp_path) purely to verify the import/query logic works end-to-end. They
are NOT NativeMed's real plant data -- that lives in backend/data/ as
Cleaned_Medicinal_Plants_Dataset.xlsx and synonym_mapping.xlsx.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from database import database as db
from database.create_db import create_database
from database.import_data import import_all
from utils.exceptions import CSVImportError, PlantNotFoundError


@pytest.fixture()
def sample_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    plants = pd.DataFrame(
        [
            {
                "Plant Id": 1,
                "Plant Name": "Tulsi",
                "Botanical Name": "Ocimum tenuiflorum",
                "Medicinal Properties": "Antibacterial, Anti-inflammatory",
                "Traditional Uses": "Boiled into herbal tea for coughs and colds",
                "Cultural Significance": "Sacred plant in many South Asian households",
                "Diseases Treated": "Cough and cold, Respiratory infections",
                "Preparation Method": "Steep the leaves in hot water for 5-10 minutes like a tea, strain, and drink warm.",
                "How To Take / Apply": "Oral (taken by mouth)",
                "General Disclaimer": "Traditional/folk use only - not a verified medical treatment.",
            },
            {
                "Plant Id": 2,
                "Plant Name": "Neem",
                "Botanical Name": "Azadirachta indica",
                "Medicinal Properties": "Antibacterial, Antifungal",
                "Traditional Uses": "Leaf paste applied topically for skin conditions",
                "Cultural Significance": "Widely used in traditional Ayurvedic medicine",
                "Diseases Treated": "Skin infections, Acne",
                "Preparation Method": "Crush fresh leaves into a paste with a little water.",
                "How To Take / Apply": "Topical (applied to skin)",
                "General Disclaimer": "Traditional/folk use only - not a verified medical treatment.",
            },
        ]
    )
    plants.to_excel(data_dir / "Cleaned_Medicinal_Plants_Dataset.xlsx", index=False)

    synonyms = pd.DataFrame(
        [
            {"Plant Name (Synonym)": "Holy Basil", "Botanical Name (Canonical)": "Ocimum tenuiflorum"},
            {"Plant Name (Synonym)": "OcimumTenuiflorum", "Botanical Name (Canonical)": "Ocimum tenuiflorum"},
            {"Plant Name (Synonym)": "Margosa", "Botanical Name (Canonical)": "Azadirachta indica"},
            {"Plant Name (Synonym)": "Unknown Plant X", "Botanical Name (Canonical)": "Nonexistent species"},
        ]
    )
    synonyms.to_excel(data_dir / "synonym_mapping.xlsx", index=False)

    return data_dir


def test_create_database_creates_all_tables(tmp_path: Path):
    db_path = tmp_path / "plants.db"
    create_database(str(db_path))

    conn = sqlite3.connect(str(db_path))
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()

    assert {"plants", "botanical_synonyms"} <= tables


def test_import_all_loads_plants_and_synonyms(sample_data_dir: Path, tmp_path: Path):
    db_path = tmp_path / "plants.db"
    stats = import_all(data_dir=str(sample_data_dir), db_path=str(db_path))

    assert stats["plants"] == 2
    assert stats["synonyms_resolved"] == 3
    assert stats["synonyms_unresolved"] == 1

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    plants = conn.execute("SELECT * FROM plants ORDER BY plant_id").fetchall()
    assert len(plants) == 2
    assert plants[0]["common_name"] == "Tulsi"
    assert plants[0]["diseases_treated"] == "Cough and cold, Respiratory infections"

    synonyms = conn.execute("SELECT * FROM botanical_synonyms").fetchall()
    assert len(synonyms) == 4
    conn.close()


def test_import_missing_plants_file_raises(tmp_path: Path):
    empty_dir = tmp_path / "empty_data"
    empty_dir.mkdir()

    with pytest.raises(CSVImportError):
        import_all(data_dir=str(empty_dir), db_path=str(tmp_path / "plants.db"))


def test_import_missing_required_column_raises(tmp_path: Path):
    data_dir = tmp_path / "bad_data"
    data_dir.mkdir()
    # Missing "Diseases Treated" column
    bad_df = pd.DataFrame(
        [{"Plant Id": 1, "Plant Name": "X", "Botanical Name": "Y",
          "Medicinal Properties": "Z", "Traditional Uses": "W", "Cultural Significance": "V"}]
    )
    bad_df.to_excel(data_dir / "Cleaned_Medicinal_Plants_Dataset.xlsx", index=False)

    with pytest.raises(CSVImportError):
        import_all(data_dir=str(data_dir), db_path=str(tmp_path / "plants.db"))


def test_get_plant_by_id_returns_synonyms_and_split_lists(sample_data_dir: Path, tmp_path: Path):
    db_path = tmp_path / "plants.db"
    import_all(data_dir=str(sample_data_dir), db_path=str(db_path))

    plant = db.get_plant_by_id(1, db_path=str(db_path))
    assert plant["common_name"] == "Tulsi"
    assert plant["diseases_treated_list"] == ["Cough and cold", "Respiratory infections"]
    assert plant["medicinal_properties_list"] == ["Antibacterial", "Anti-inflammatory"]
    assert set(plant["synonyms"]) == {"Holy Basil", "OcimumTenuiflorum"}
    assert plant["preparation_method"].startswith("Steep the leaves")
    assert plant["how_to_take"] == "Oral (taken by mouth)"
    assert "not a verified medical treatment" in plant["general_disclaimer"]


def test_get_plant_by_id_raises_for_missing_plant(sample_data_dir: Path, tmp_path: Path):
    db_path = tmp_path / "plants.db"
    import_all(data_dir=str(sample_data_dir), db_path=str(db_path))

    with pytest.raises(PlantNotFoundError):
        db.get_plant_by_id(9999, db_path=str(db_path))


def test_find_plant_by_botanical_name_direct_match(sample_data_dir: Path, tmp_path: Path):
    db_path = tmp_path / "plants.db"
    import_all(data_dir=str(sample_data_dir), db_path=str(db_path))

    plant = db.find_plant_by_botanical_name("azadirachta indica", db_path=str(db_path))
    assert plant is not None
    assert plant["common_name"] == "Neem"


def test_find_plant_by_botanical_name_via_synonym(sample_data_dir: Path, tmp_path: Path):
    db_path = tmp_path / "plants.db"
    import_all(data_dir=str(sample_data_dir), db_path=str(db_path))

    plant = db.find_plant_by_botanical_name("Margosa", db_path=str(db_path))
    assert plant is not None
    assert plant["common_name"] == "Neem"


def test_find_plant_by_botanical_name_no_match_returns_none(sample_data_dir: Path, tmp_path: Path):
    db_path = tmp_path / "plants.db"
    import_all(data_dir=str(sample_data_dir), db_path=str(db_path))

    plant = db.find_plant_by_botanical_name("Totally Unknown Plant", db_path=str(db_path))
    assert plant is None


def test_fetch_all_documents_for_ingestion_shapes_data(sample_data_dir: Path, tmp_path: Path):
    db_path = tmp_path / "plants.db"
    import_all(data_dir=str(sample_data_dir), db_path=str(db_path))

    documents = db.fetch_all_documents_for_ingestion(db_path=str(db_path))
    assert len(documents) == 2
    doc = next(d for d in documents if d["common_name"] == "Tulsi")
    assert doc["doc_id"] == "plant_1"
    assert doc["diseases_treated"] == "Cough and cold, Respiratory infections"
    assert set(doc["synonyms"]) == {"Holy Basil", "OcimumTenuiflorum"}
    assert doc["preparation_method"].startswith("Steep the leaves")
    assert doc["how_to_take"] == "Oral (taken by mouth)"
