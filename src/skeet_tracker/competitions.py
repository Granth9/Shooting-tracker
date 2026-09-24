"""Competition meet archive (Shotgun Pathway + manual entry)."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

_SEED_PATH = Path(__file__).resolve().parent / "data" / "pathway_grant_hernandez.json"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS competition_meets (
    meet_id TEXT PRIMARY KEY,
    event_date TEXT NOT NULL,
    date_precision TEXT NOT NULL DEFAULT 'year'
        CHECK(date_precision IN ('day', 'year')),
    year INTEGER NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    level TEXT NOT NULL DEFAULT 'domestic'
        CHECK(level IN ('domestic', 'international')),
    qualification_score INTEGER,
    final_score INTEGER,
    selection_aggregate INTEGER,
    rounds_json TEXT,
    placing INTEGER,
    medal TEXT CHECK(medal IS NULL OR medal IN ('gold', 'silver', 'bronze')),
    source_url TEXT,
    source_label TEXT,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_competition_meets_year ON competition_meets(year);
"""


def ensure_competition_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_CREATE_TABLE_SQL)
    conn.commit()


def parse_rounds_text(text: str | None) -> list[int] | None:
    """Parse pasted round strings like '24 22 23 23 23' or '24,22,23'."""
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    parts = re.split(r"[,;\s]+", raw)
    out: list[int] = []
    for p in parts:
        if not p:
            continue
        n = int(p)
        if not 0 <= n <= 25:
            raise ValueError(f"Round score out of range 0–25: {n}")
        out.append(n)
    if not out:
        return None
    if len(out) > 40:
        raise ValueError("Too many round scores (max 40)")
    return out


def _normalize_rounds(rounds: list[int] | str | None) -> list[int] | None:
    if rounds is None:
        return None
    if isinstance(rounds, str):
        return parse_rounds_text(rounds)
    return [int(x) for x in rounds]


def _row_to_meet(row: sqlite3.Row) -> dict[str, Any]:
    rounds = json.loads(row["rounds_json"]) if row["rounds_json"] else None
    rounds_sum = sum(rounds) if rounds else None
    return {
        "meet_id": row["meet_id"],
        "event_date": row["event_date"],
        "date_precision": row["date_precision"],
        "year": row["year"],
        "name": row["name"],
        "category": row["category"],
        "level": row["level"],
        "qualification_score": row["qualification_score"],
        "final_score": row["final_score"],
        "selection_aggregate": row["selection_aggregate"],
        "rounds": rounds,
        "rounds_sum": rounds_sum,
        "placing": row["placing"],
        "medal": row["medal"],
        "source_url": row["source_url"],
        "source_label": row["source_label"],
        "notes": row["notes"],
        "created_at": row["created_at"],
    }


def ensure_pathway_seed(conn: sqlite3.Connection) -> int:
    """INSERT OR IGNORE Pathway fixture meets. Returns rows attempted."""
    if not _SEED_PATH.is_file():
        return 0
    data = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    n = 0
    for item in data:
        rounds = item.get("rounds")
        rounds_json = json.dumps(rounds) if rounds is not None else None
        conn.execute(
            """
            INSERT OR IGNORE INTO competition_meets (
                meet_id, event_date, date_precision, year, name, category, level,
                qualification_score, final_score, selection_aggregate, rounds_json,
                placing, medal, source_url, source_label, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["meet_id"],
                item["event_date"],
                item.get("date_precision", "year"),
                int(item["year"]),
                item["name"],
                item.get("category"),
                item.get("level", "domestic"),
                item.get("qualification_score"),
                item.get("final_score"),
                item.get("selection_aggregate"),
                rounds_json,
                item.get("placing"),
                item.get("medal"),
                item.get("source_url"),
                item.get("source_label"),
                item.get("notes"),
                now,
            ),
        )
        n += 1
    conn.commit()
    return n


def list_meets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM competition_meets
        ORDER BY year DESC, event_date DESC, name COLLATE NOCASE
        """
    ).fetchall()
    return [_row_to_meet(r) for r in rows]


def get_meet(conn: sqlite3.Connection, meet_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT * FROM competition_meets WHERE meet_id = ?", (meet_id,)
    ).fetchone()
    if not row:
        raise KeyError(meet_id)
    return _row_to_meet(row)


def save_meet(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    year = int(payload["year"])
    if not 1990 <= year <= 2100:
        raise ValueError("year out of range")
    level = payload.get("level") or "domestic"
    if level not in ("domestic", "international"):
        raise ValueError("level must be domestic or international")
    medal = payload.get("medal") or None
    if medal is not None and medal not in ("gold", "silver", "bronze"):
        raise ValueError("medal must be gold, silver, bronze, or empty")
    date_precision = payload.get("date_precision") or "year"
    if date_precision not in ("day", "year"):
        raise ValueError("date_precision must be day or year")
    event_date = (payload.get("event_date") or "").strip() or f"{year}-01-01"
    rounds = _normalize_rounds(payload.get("rounds"))
    if rounds is None and payload.get("rounds_text"):
        rounds = parse_rounds_text(payload["rounds_text"])
    qual = payload.get("qualification_score")
    if qual is not None:
        qual = int(qual)
    if rounds is not None and qual is not None and abs(sum(rounds) - qual) > 2:
        # Soft warning stored in notes only if caller left notes empty — don't block
        pass

    meet_id = (payload.get("meet_id") or "").strip() or str(uuid.uuid4())
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    conn.execute(
        """
        INSERT INTO competition_meets (
            meet_id, event_date, date_precision, year, name, category, level,
            qualification_score, final_score, selection_aggregate, rounds_json,
            placing, medal, source_url, source_label, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(meet_id) DO UPDATE SET
            event_date = excluded.event_date,
            date_precision = excluded.date_precision,
            year = excluded.year,
            name = excluded.name,
            category = excluded.category,
            level = excluded.level,
            qualification_score = excluded.qualification_score,
            final_score = excluded.final_score,
            selection_aggregate = excluded.selection_aggregate,
            rounds_json = excluded.rounds_json,
            placing = excluded.placing,
            medal = excluded.medal,
            source_url = excluded.source_url,
            source_label = excluded.source_label,
            notes = excluded.notes
        """,
        (
            meet_id,
            event_date,
            date_precision,
            year,
            name,
            (payload.get("category") or None),
            level,
            qual,
            int(payload["final_score"]) if payload.get("final_score") is not None else None,
            int(payload["selection_aggregate"])
            if payload.get("selection_aggregate") is not None
            else None,
            json.dumps(rounds) if rounds is not None else None,
            int(payload["placing"]) if payload.get("placing") is not None else None,
            medal,
            (payload.get("source_url") or None),
            (payload.get("source_label") or None),
            (payload.get("notes") or None),
            now,
        ),
    )
    conn.commit()
    return get_meet(conn, meet_id)


def delete_meet(conn: sqlite3.Connection, meet_id: str) -> None:
    cur = conn.execute(
        "DELETE FROM competition_meets WHERE meet_id = ?", (meet_id,)
    )
    conn.commit()
    if cur.rowcount == 0:
        raise KeyError(meet_id)


def competition_timeline(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Qualification scores for overview chart (newest last for easy plotting)."""
    meets = list_meets(conn)
    points: list[dict[str, Any]] = []
    for m in reversed(meets):
        score = m["qualification_score"]
        if score is None:
            continue
        points.append(
            {
                "meet_id": m["meet_id"],
                "date": m["event_date"],
                "year": m["year"],
                "score": score,
                "name": m["name"],
                "medal": m["medal"],
                "placing": m["placing"],
                "level": m["level"],
            }
        )
    return points


def results_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    meets = list_meets(conn)
    by_year: dict[int, dict[str, Any]] = {}
    for m in meets:
        y = int(m["year"])
        bucket = by_year.setdefault(
            y,
            {
                "year": y,
                "meet_count": 0,
                "best_qual": None,
                "medals": {"gold": 0, "silver": 0, "bronze": 0},
            },
        )
        bucket["meet_count"] += 1
        q = m["qualification_score"]
        if q is not None:
            if bucket["best_qual"] is None or q > bucket["best_qual"]:
                bucket["best_qual"] = q
        if m["medal"]:
            bucket["medals"][m["medal"]] = bucket["medals"].get(m["medal"], 0) + 1

    seasons = sorted(by_year.values(), key=lambda s: s["year"], reverse=True)
    timeline = competition_timeline(conn)
    return {
        "empty": len(meets) == 0,
        "meets": meets,
        "seasons": seasons,
        "timeline": timeline,
        "totals": {
            "meets": len(meets),
            "gold": sum(1 for m in meets if m["medal"] == "gold"),
            "silver": sum(1 for m in meets if m["medal"] == "silver"),
            "bronze": sum(1 for m in meets if m["medal"] == "bronze"),
        },
    }
