"""Legacy MySQL connection helper.

NOT USED by the current frontend/app.py -- all plant data is now served by
the FastAPI backend (see backend_client.py / config.py), which is backed by
SQLite (backend/database/plants.db). This module is kept only for backward
compatibility with any old scripts that might still import it, and its
credentials must never be hardcoded.

Configure via environment variables (e.g. in a `.env` file loaded by
python-dotenv) instead of editing this file:
    MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
"""

from __future__ import annotations

import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    host = os.environ.get("MYSQL_HOST", "localhost")
    user = os.environ.get("MYSQL_USER", "root")
    password = os.environ.get("MYSQL_PASSWORD","rith737")
    database = os.environ.get("MYSQL_DATABASE", "nativemed_ai")

    if not password:
        raise RuntimeError(
            "MYSQL_PASSWORD is not set. This legacy module requires MySQL "
            "credentials to be supplied via environment variables -- it no "
            "longer has a hardcoded fallback password. (Note: the active "
            "frontend does not use this module; see backend_client.py.)"
        )

    return mysql.connector.connect(
        host=host,
        user=user,
        password=password,
        database=database,
    )
