"""SQLite connection helpers, schema init, and migration."""

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


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def _needs_migration(conn: sqlite3.Connection) -> bool:
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "rounds" not in tables:
        return False
    cols = _table_columns(conn, "rounds")
    if "format" not in cols:
        return True
    # Detect old CHECK that rejected 'drill' by trying a rollback insert is heavy;
    # rebuild if shots sequence_order check still caps at 25 via table SQL text.
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='shots'"
    ).fetchone()
    if sql and sql[0] and "BETWEEN 1 AND 25" in sql[0]:
        return True
    return False


def _migrate_v2(conn: sqlite3.Connection) -> None:
    """Rebuild rounds/shots to support finals (36) and drills."""
    conn.executescript(
        """
        ALTER TABLE rounds RENAME TO rounds_old;
        ALTER TABLE shots RENAME TO shots_old;
        """
    )
    conn.executescript(_load_schema())
    round_cols = _table_columns(conn, "rounds_old")
    # Copy rounds with defaults for new columns
    conn.execute(
        """
        INSERT INTO rounds (
            round_id, timestamp, event_type, format, drill_name,
            location, round_number, weather_condition, wind_speed_mph,
            choke_used, notes
        )
        SELECT
            round_id,
            timestamp,
            event_type,
            CASE WHEN event_type = 'final' THEN 'issf_final_36' ELSE 'issf_25' END,
            NULL,
            location,
            round_number,
            weather_condition,
            wind_speed_mph,
            choke_used,
            notes
        FROM rounds_old
        """
    )
    # Old finals were stored as 25-target — keep as issf_25 if they have 25 shots
    # Fix format based on actual shot count after copy
    conn.execute(
        """
        INSERT INTO shots (
            round_id, sequence_order, station, target_house,
            is_double, pair_position, is_hit, miss_direction
        )
        SELECT
            round_id, sequence_order, station, target_house,
            is_double, pair_position, is_hit, miss_direction
        FROM shots_old
        """
    )
    # Prefer issf_25 for migrated 'final' rows that were logged as 25-target
    conn.execute(
        """
        UPDATE rounds
        SET format = 'issf_25'
        WHERE event_type = 'final'
          AND (
            SELECT COUNT(*) FROM shots s WHERE s.round_id = rounds.round_id
          ) <= 25
        """
    )
    conn.execute("DROP TABLE shots_old")
    conn.execute("DROP TABLE rounds_old")
    conn.commit()


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> Path:
    """Create tables and migrate older schemas when needed."""
    path = Path(db_path)
    schema = _load_schema()
    with get_connection(path) as conn:
        if _needs_migration(conn):
            _migrate_v2(conn)
        else:
            conn.executescript(schema)
            conn.commit()
        # Always ensure templates + competition tables; seed Pathway meets once
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS drill_templates (
                template_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                blocks_json TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        from skeet_tracker.competitions import (
            ensure_competition_table,
            ensure_pathway_seed,
        )
        from skeet_tracker.drills import normalize_saved_template_kinds

        normalize_saved_template_kinds(conn)
        ensure_competition_table(conn)
        ensure_pathway_seed(conn)
    return path


def schema_sql() -> str:
    """Return the schema SQL text (for inspection / packaging)."""
    return _load_schema()
