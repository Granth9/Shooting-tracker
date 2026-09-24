"""Tests for competition meet archive and Pathway seed."""

from __future__ import annotations

import json

from skeet_tracker.competitions import (
    delete_meet,
    ensure_pathway_seed,
    parse_rounds_text,
    results_payload,
    save_meet,
)
from skeet_tracker.db import get_connection, init_db


def test_parse_rounds_text():
    assert parse_rounds_text("24 22 23 23 23") == [24, 22, 23, 23, 23]
    assert parse_rounds_text("24,22,23") == [24, 22, 23]
    assert parse_rounds_text("") is None
    assert parse_rounds_text(None) is None


def test_parse_rounds_rejects_out_of_range():
    try:
        parse_rounds_text("26")
        assert False
    except ValueError:
        pass


def test_pathway_seed_inserts_once(tmp_path):
    db = tmp_path / "c.db"
    init_db(db)
    with get_connection(db) as conn:
        n1 = ensure_pathway_seed(conn)
        before = conn.execute("SELECT COUNT(*) AS c FROM competition_meets").fetchone()[
            "c"
        ]
        assert before >= 10
        assert n1 >= 10
        # Mutate a seeded row
        conn.execute(
            "UPDATE competition_meets SET name = 'EDITED' WHERE meet_id = '2025-jo-gold'"
        )
        conn.commit()
        ensure_pathway_seed(conn)
        row = conn.execute(
            "SELECT name FROM competition_meets WHERE meet_id = '2025-jo-gold'"
        ).fetchone()
        assert row["name"] == "EDITED"
        after = conn.execute("SELECT COUNT(*) AS c FROM competition_meets").fetchone()[
            "c"
        ]
        assert after == before


def test_results_payload_seasons(tmp_path):
    db = tmp_path / "c.db"
    init_db(db)
    with get_connection(db) as conn:
        payload = results_payload(conn)
    assert not payload["empty"]
    assert payload["totals"]["gold"] >= 1
    years = {s["year"] for s in payload["seasons"]}
    assert 2025 in years
    assert any(p["score"] == 113 for p in payload["timeline"])


def test_save_and_delete_meet(tmp_path):
    db = tmp_path / "c.db"
    init_db(db)
    with get_connection(db) as conn:
        saved = save_meet(
            conn,
            {
                "name": "Test Cup",
                "year": 2026,
                "qualification_score": 120,
                "rounds_text": "24 24 24 24 24",
                "medal": "silver",
                "placing": 2,
            },
        )
        assert saved["meet_id"]
        assert saved["rounds"] == [24, 24, 24, 24, 24]
        assert saved["medal"] == "silver"
        mid = saved["meet_id"]
        delete_meet(conn, mid)
        try:
            delete_meet(conn, mid)
            assert False
        except KeyError:
            pass


def test_save_updates_existing(tmp_path):
    db = tmp_path / "c.db"
    init_db(db)
    with get_connection(db) as conn:
        save_meet(
            conn,
            {
                "meet_id": "custom-1",
                "name": "Custom",
                "year": 2024,
                "qualification_score": 100,
            },
        )
        save_meet(
            conn,
            {
                "meet_id": "custom-1",
                "name": "Custom Updated",
                "year": 2024,
                "qualification_score": 110,
                "rounds": [22, 22, 22, 22, 22],
            },
        )
        row = conn.execute(
            "SELECT name, qualification_score, rounds_json FROM competition_meets WHERE meet_id = 'custom-1'"
        ).fetchone()
        assert row["name"] == "Custom Updated"
        assert row["qualification_score"] == 110
        assert json.loads(row["rounds_json"]) == [22, 22, 22, 22, 22]
