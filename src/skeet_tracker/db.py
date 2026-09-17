"""SQLite connection helpers and schema initialization."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("skeet.db")

_PACKAGE_SCHEMA = Path(__file__).resolve().with_name("schema.sql")
_REPO_SCHEMA = Path(__file__).resolve().parents[2] / "relational_skeet_schema.sql"


def _load_schema() -> str:
    if _PACKAGE_SCHEMA.is_file():
        return _PACKAGE_SCHEMA.read_text(encoding="utf-8")
    if _REPO_SCHEMA.is_file():
        return _REPO_SCHEMA.read_text(encoding="utf-8")
    raise FileNotFoundError("Could not locate relational skeet schema SQL")


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled and row factory set."""
    path = Path(db_path)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    """Create tables from relational_skeet_schema.sql if they do not exist."""
    path = Path(db_path)
    schema = _load_schema()
    with get_connection(path) as conn:
        conn.executescript(schema)
        conn.commit()
    return path


def schema_sql() -> str:
    """Return the schema SQL text (for inspection / packaging)."""
    return _load_schema()
