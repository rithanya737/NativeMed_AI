"""Diagnostic script: confirms whether app.py is looking at the same MySQL
database/table that import_dataset.py populated.

Run this from the SAME terminal / virtual environment you use to run
`python app.py`, from inside the `frontend` folder:

    python check_mysql.py

It reuses the exact same connection logic as database.py (get_connection),
so if this script sees data, app.py will too -- and if it doesn't, we've
found the mismatch.
"""

import os

from database import get_connection

print("--- Resolved connection settings (same defaults as database.py) ---")
print("MYSQL_HOST     :", os.environ.get("MYSQL_HOST", "localhost"), (
    "(from env var)" if os.environ.get("MYSQL_HOST") else "(default)"))
print("MYSQL_USER     :", os.environ.get("MYSQL_USER", "root"), (
    "(from env var)" if os.environ.get("MYSQL_USER") else "(default)"))
print("MYSQL_DATABASE :", os.environ.get("MYSQL_DATABASE", "nativemed_ai"), (
    "(from env var)" if os.environ.get("MYSQL_DATABASE") else "(default)"))
print("MYSQL_PASSWORD :", "*** set via env var ***" if os.environ.get("MYSQL_PASSWORD") else "(using hardcoded fallback in database.py)")
print()

try:
    conn = get_connection()
except Exception as exc:
    print(f"FAILED to connect: {exc}")
    raise SystemExit(1)

cursor = conn.cursor()

cursor.execute("SELECT DATABASE();")
print("Connected to database:", cursor.fetchone()[0])

cursor.execute("SHOW TABLES;")
tables = [row[0] for row in cursor.fetchall()]
print("Tables in this database:", tables)

if "medicinal_plants" in tables:
    cursor.execute("SELECT COUNT(*) FROM medicinal_plants;")
    count = cursor.fetchone()[0]
    print(f"Row count in medicinal_plants: {count}")
    if count > 0:
        cursor.execute("SELECT plant_id, plant_name FROM medicinal_plants LIMIT 3;")
        print("Sample rows:", cursor.fetchall())
else:
    print("medicinal_plants table NOT FOUND in this database.")

cursor.close()
conn.close()
