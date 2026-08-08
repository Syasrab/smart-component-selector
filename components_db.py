import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_FILE = "components.db"

# Known cases where the AI has generated different category names for the
# same real-world component type across different runs. This keeps the
# database from filling up with near-duplicate categories over time.
# Extend this map as you notice new drift after running more projects.
CANONICAL_CATEGORY_MAP = {
    "rgb_status_led": "status_led",
    "status_indicator_led": "status_led",
    "lipo_charger_ic": "solar_charger_ic",
    "solar_lipo_charger_ic": "solar_charger_ic",
    "li_ion_charger_ic": "solar_charger_ic",
    "capacitive_soil_moisture_sensor": "soil_moisture_sensor",
    "voltage_regulator": "voltage_regulator_3v3",
    "voltage_regulator_ldo": "voltage_regulator_3v3",
    "buck_regulator_3v3": "voltage_regulator_3v3",
}


def normalize_category(category):
    """Lowercase/strip a category name and map known synonyms to a single
    canonical form, so the same component type doesn't fragment into
    multiple near-duplicate categories across different pipeline runs."""
    key = category.strip().lower().replace(" ", "_")
    return CANONICAL_CATEGORY_MAP.get(key, key)


def get_connection():
    connection = sqlite3.connect(DB_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_connection()
    connection.execute("""
        CREATE TABLE IF NOT EXISTS components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            mpn TEXT NOT NULL,
            manufacturer TEXT,
            description TEXT,
            price_usd REAL,
            quantity_available INTEGER,
            datasheet_url TEXT,
            parameters TEXT,
            UNIQUE(category, mpn)
        )
    """)
    # Migration for databases created before dev-board flagging was added.
    try:
        connection.execute("ALTER TABLE components ADD COLUMN is_dev_board INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # column already exists

    connection.execute("""
        CREATE TABLE IF NOT EXISTS project_categories (
            category TEXT PRIMARY KEY,
            search_keyword TEXT,
            requirement TEXT
        )
    """)
    connection.execute("""
        CREATE TABLE IF NOT EXISTS keyword_cache (
            keyword TEXT PRIMARY KEY,
            results TEXT,
            cached_at TEXT
        )
    """)
    connection.commit()
    connection.close()


def save_categories(categories):
    """categories: list of dicts with keys category, search_keyword, requirement.
    Replaces the full category set for this project."""
    connection = get_connection()
    connection.execute("DELETE FROM project_categories")
    for c in categories:
        connection.execute("""
            INSERT INTO project_categories (category, search_keyword, requirement)
            VALUES (?, ?, ?)
        """, (c["category"], c["search_keyword"], c["requirement"]))
    connection.commit()
    connection.close()


def get_categories():
    connection = get_connection()
    rows = connection.execute("SELECT * FROM project_categories").fetchall()
    connection.close()
    return [dict(row) for row in rows]


def insert_components(category, parts):
    """parts: list of dicts as returned by digikey_client.search_by_keyword()."""
    connection = get_connection()
    for part in parts:
        if not part.get("mpn"):
            continue
        connection.execute("""
            INSERT OR REPLACE INTO components
                (category, mpn, manufacturer, description, price_usd,
                 quantity_available, datasheet_url, parameters, is_dev_board)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            category,
            part["mpn"],
            part.get("manufacturer"),
            part.get("description"),
            part.get("price_usd"),
            part.get("quantity_available"),
            part.get("datasheet_url"),
            json.dumps(part.get("parameters") or {}),
            1 if part.get("is_dev_board") else 0,
        ))
    connection.commit()
    connection.close()


def get_components_by_category(category):
    connection = get_connection()
    rows = connection.execute(
        "SELECT * FROM components WHERE category = ?", (category,)
    ).fetchall()
    connection.close()
    return rows


def list_categories():
    connection = get_connection()
    rows = connection.execute("SELECT DISTINCT category FROM components").fetchall()
    connection.close()
    return [r["category"] for r in rows]


def get_cached_results(keyword, max_age_hours=24):
    """Returns cached DigiKey search results for a keyword if they exist
    and are still fresh, otherwise None. Keeps repeated runs of the same
    project spec from burning through DigiKey's rate limits."""
    connection = get_connection()
    row = connection.execute(
        "SELECT results, cached_at FROM keyword_cache WHERE keyword = ?", (keyword,)
    ).fetchone()
    connection.close()
    if not row:
        return None
    cached_at = datetime.fromisoformat(row["cached_at"])
    if datetime.utcnow() - cached_at > timedelta(hours=max_age_hours):
        return None
    return json.loads(row["results"])


def cache_results(keyword, results):
    connection = get_connection()
    connection.execute("""
        INSERT OR REPLACE INTO keyword_cache (keyword, results, cached_at)
        VALUES (?, ?, ?)
    """, (keyword, json.dumps(results), datetime.utcnow().isoformat()))
    connection.commit()
    connection.close()