"""SQLite initialization and thread-safe product persistence."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

DB_LOCK = threading.Lock()

DEFAULT_DB_NAME = "ecommerce_harvest.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS products (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    price           REAL,
    description     TEXT,
    seller_name     TEXT,
    rating          REAL,
    source_url      TEXT UNIQUE,
    harvested_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_images (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      TEXT,
    image_url       TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE(product_id, image_url)
);
"""


def get_db_path(db_name: str = DEFAULT_DB_NAME) -> Path:
    """Resolve database path relative to the project root (parent of src/)."""
    return Path(__file__).resolve().parent.parent / db_name


def init_db(db_name: str = DEFAULT_DB_NAME) -> Path:
    """Create tables if they do not exist and return the database path."""
    db_path = get_db_path(db_name)
    with DB_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
        finally:
            conn.close()
    return db_path


def get_product_count(db_name: str = DEFAULT_DB_NAME) -> int:
    """Return the number of rows in the products table."""
    db_path = get_db_path(db_name)
    with DB_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT COUNT(*) FROM products").fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()


def get_image_count(db_name: str = DEFAULT_DB_NAME) -> int:
    """Return the number of rows in the product_images table."""
    db_path = get_db_path(db_name)
    with DB_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT COUNT(*) FROM product_images").fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()


def save_product(product: dict[str, Any], db_name: str = DEFAULT_DB_NAME) -> bool:
    """
    Insert a product and its images using INSERT OR IGNORE.
    Caller must hold DB_LOCK or this function acquires it internally.
    Returns True when a new product row was inserted.
    """
    db_path = get_db_path(db_name)
    with DB_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO products
                    (id, name, price, description, seller_name, rating, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    product["product_id"],
                    product["name"],
                    product.get("price"),
                    product.get("description"),
                    product.get("seller_name"),
                    product.get("rating"),
                    product["source_url"],
                ),
            )
            inserted = cursor.rowcount > 0

            for image_url in product.get("image_urls", []):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO product_images (product_id, image_url)
                    VALUES (?, ?)
                    """,
                    (product["product_id"], image_url),
                )

            conn.commit()
            return inserted
        except sqlite3.IntegrityError:
            conn.rollback()
            return False
        finally:
            conn.close()
