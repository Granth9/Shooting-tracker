"""Tests for round / final / drill ingest."""

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
from skeet_tracker.sequence import ISSF_FINAL_36, ISSF_SEQUENCE


def _perfect_25() -> list[ShotInput]:
    return [ShotInput(sequence_order=i, is_hit=True) for i in range(1, 26)]


def _perfect_final(n: int = 36) -> list[ShotInput]:
    return [ShotInput(sequence_order=i, is_hit=True) for i in range(1, n + 1)]


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
            ShotInput(sequence_order=1, is_hit=True, target_house="low")
        )


def test_validate_requires_25_unique():
    shots = _perfect_25()[:-1]
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
            format="issf_25",
            shots=_perfect_25(),
            round_number=1,
            wind_speed_mph=3,
        ),
    )
    assert rid == "r-test"
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM shots WHERE round_id = ?", (rid,)
    ).fetchone()["c"]
    assert n == 25
    conn.close()


def test_insert_final_36(tmp_path):
    db = tmp_path / "final.db"
    init_db(db)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    rid = insert_round(
        conn,
        RoundInput(
            round_id="f-36",
            event_type="final",
            format="issf_final_36",
            shots=_perfect_final(36),
        ),
    )
    row = conn.execute(
        "SELECT format, event_type FROM rounds WHERE round_id = ?", (rid,)
    ).fetchone()
    assert row["format"] == "issf_final_36"
    assert row["event_type"] == "final"
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM shots WHERE round_id = ?", (rid,)
    ).fetchone()["c"]
    assert n == 36
    # Metadata matches final sequence
    first = conn.execute(
        "SELECT station, target_house FROM shots WHERE round_id=? AND sequence_order=1",
        (rid,),
    ).fetchone()
    assert first["station"] == 3 and first["target_house"] == "high"
    conn.close()


def test_insert_final_partial_12(tmp_path):
    db = tmp_path / "partial.db"
    init_db(db)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    insert_round(
        conn,
        RoundInput(
            round_id="f-12",
            event_type="final",
            format="issf_final_36",
            shots=_perfect_final(12),
        ),
    )
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM shots WHERE round_id='f-12'"
    ).fetchone()["c"]
    assert n == 12
    conn.close()


def test_insert_drill_custom_count(tmp_path):
    from skeet_tracker.drills import build_station_drill

    db = tmp_path / "drill.db"
    init_db(db)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    slots = build_station_drill(station=4, target_count=16, pattern="double_hl")
    assert len(slots) == 16
    shots = [
        ShotInput(
            sequence_order=s.sequence_order,
            is_hit=True,
            station=s.station,
            target_house=s.target_house,
            is_double=s.is_double,
            pair_position=s.pair_position,
        )
        for s in slots
    ]
    insert_round(
        conn,
        RoundInput(
            round_id="d-st4-16",
            event_type="drill",
            format="drill",
            drill_name="Station 4 · 16",
            shots=shots,
        ),
    )
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM shots WHERE round_id='d-st4-16'"
    ).fetchone()["c"]
    assert n == 16
    conn.close()


def test_sequences_cover_expected_counts():
    assert len(ISSF_SEQUENCE) == 25
    assert len(ISSF_FINAL_36) == 36
