"""Tests for round ingest and sequence validation."""

import sqlite3

import pytest

from skeet_tracker.db import init_db
from skeet_tracker.ingest import (
    IngestError,
    insert_round,
    resolve_shot,
    validate_round,
)
from skeet_tracker.models import RoundInput, ShotInput


def _perfect_shots() -> list[ShotInput]:
    return [ShotInput(sequence_order=i, is_hit=True) for i in range(1, 26)]


def test_resolve_shot_fills_sequence():
    shot = resolve_shot(ShotInput(sequence_order=13, is_hit=False))
    assert shot.station == 5
    assert shot.target_house == "low"
    assert shot.is_double is True
    assert shot.pair_position == 1
    assert shot.miss_direction == "unknown"


def test_reject_wrong_house_override():
    with pytest.raises(IngestError, match="target_house"):
        resolve_shot(
            ShotInput(
                sequence_order=1,
                is_hit=True,
                target_house="low",  # should be high
            )
        )


def test_validate_requires_25_unique():
    shots = _perfect_shots()[:-1]
    with pytest.raises(IngestError, match="25"):
        validate_round(
            RoundInput(round_id="x", event_type="practice", shots=shots)
        )


def test_insert_round_persists(tmp_path):
    db = tmp_path / "test.db"
    init_db(db)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    rid = insert_round(
        conn,
        RoundInput(
            round_id="r-test",
            event_type="practice",
            shots=_perfect_shots(),
            round_number=1,
            wind_speed_mph=3,
        ),
    )
    assert rid == "r-test"
    n = conn.execute("SELECT COUNT(*) AS c FROM shots WHERE round_id = ?", (rid,)).fetchone()[
        "c"
    ]
    assert n == 25
    hits = conn.execute(
        "SELECT SUM(is_hit) AS h FROM shots WHERE round_id = ?", (rid,)
    ).fetchone()["h"]
    assert hits == 25
    conn.close()
