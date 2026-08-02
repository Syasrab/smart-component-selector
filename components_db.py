import sqlite3
import json
import os

DB_FILE = "components.db"


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
    connection.execute("""
        CREATE TABLE IF NOT EXISTS project_categories (
            category TEXT PRIMARY KEY,
            search_keyword TEXT,
            requirement TEXT
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
                 quantity_available, datasheet_url, parameters)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            category,
            part["mpn"],
            part.get("manufacturer"),
            part.get("description"),
            part.get("price_usd"),
            part.get("quantity_available"),
            part.get("datasheet_url"),
            json.dumps(part.get("parameters") or {}),
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