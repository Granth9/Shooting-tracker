"""Tests for multi-station drill composer."""

from skeet_tracker.db import init_db, get_connection
from skeet_tracker.drills import compose_payload, list_templates, parse_blocks


def test_compose_user_style_12678():
    blocks = [
        {"station": 1, "kind": "high_single", "reps": 1},
        {"station": 1, "kind": "low_single", "reps": 1},
        {"station": 1, "kind": "regular_pair", "reps": 2},
        {"station": 2, "kind": "high_single", "reps": 1},
        {"station": 2, "kind": "low_single", "reps": 1},
        {"station": 2, "kind": "regular_pair", "reps": 2},
        {"station": 6, "kind": "high_single", "reps": 1},
        {"station": 6, "kind": "low_single", "reps": 1},
        {"station": 6, "kind": "regular_pair", "reps": 2},
        {"station": 7, "kind": "regular_pair", "reps": 2},
        {"station": 8, "kind": "high_single", "reps": 2},
        {"station": 8, "kind": "low_single", "reps": 2},
    ]
    # per station 1/2/6: 1+1+4 = 6 → 18; st7: 4; st8: 4 → 26
    out = compose_payload(blocks, name="12678")
    assert out["target_count"] == 26
    assert out["slots"][0]["station"] == 1
    assert out["slots"][-1]["station"] == 8


def test_compose_finals_prep_3454():
    blocks = [
        {"station": 3, "kind": "high_single", "reps": 1},
        {"station": 3, "kind": "low_single", "reps": 1},
        {"station": 3, "kind": "high_pair", "reps": 2},
        {"station": 3, "kind": "low_pair", "reps": 2},
        {"station": 4, "kind": "high_single", "reps": 1},
        {"station": 4, "kind": "low_single", "reps": 1},
        {"station": 4, "kind": "high_single", "reps": 1},
        {"station": 4, "kind": "low_single", "reps": 1},
        {"station": 5, "kind": "high_single", "reps": 1},
        {"station": 5, "kind": "low_single", "reps": 1},
        {"station": 5, "kind": "high_pair", "reps": 2},
        {"station": 5, "kind": "low_pair", "reps": 2},
        {"station": 4, "kind": "high_pair", "reps": 2},
        {"station": 4, "kind": "low_pair", "reps": 2},
    ]
    out = compose_payload(blocks, name="3454")
    # st3: 1+1+4+4=10; st4: 4; st5: 10; st4: 4+4=8 → 32
    assert out["target_count"] == 32


def test_init_db_does_not_seed_starters(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    with get_connection(db) as conn:
        templates = list_templates(conn)
    assert templates == []


def test_parse_rejects_empty():
    try:
        parse_blocks([])
        assert False
    except ValueError:
        pass
