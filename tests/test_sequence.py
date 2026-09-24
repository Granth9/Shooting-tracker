"""Tests for ISSF 25-target and Final-36 sequence mapping."""

from skeet_tracker.sequence import (
    ISSF_FINAL_36,
    ISSF_SEQUENCE,
    FORMAT_ISSF_FINAL_36,
    get_slot,
    slots_for_station,
    validate_against_sequence,
)


def test_sequence_length_and_order():
    assert len(ISSF_SEQUENCE) == 25
    assert [s.sequence_order for s in ISSF_SEQUENCE] == list(range(1, 26))


def test_final_36_length_and_stages():
    assert len(ISSF_FINAL_36) == 36
    assert [s.sequence_order for s in ISSF_FINAL_36] == list(range(1, 37))
    # Stage 1: stations 3,4,5 — 12 targets
    assert all(s.stage == 1 for s in ISSF_FINAL_36[:12])
    assert {s.station for s in ISSF_FINAL_36[:12]} == {3, 4, 5}
    # Stage 5 gold: station 5 only
    assert all(s.station == 5 and s.stage == 5 for s in ISSF_FINAL_36[32:36])


def test_final_regular_and_reverse_pattern():
    # First four on station 3: High, Low (regular), Low, High (reverse)
    houses = [s.target_house for s in ISSF_FINAL_36[:4]]
    assert houses == ["high", "low", "low", "high"]


def test_station_1_single_and_double():
    assert get_slot(1).station == 1
    assert get_slot(1).target_house == "high"
    assert get_slot(1).is_double is False
    assert get_slot(2).pair_position == 1 and get_slot(2).target_house == "high"
    assert get_slot(3).pair_position == 2 and get_slot(3).target_house == "low"


def test_station_4_pass1_and_pass2():
    assert get_slot(10).target_house == "high" and not get_slot(10).is_double
    assert get_slot(11).target_house == "low" and not get_slot(11).is_double
    assert get_slot(20).target_house == "high" and get_slot(20).pair_position == 1
    assert get_slot(21).target_house == "low" and get_slot(21).pair_position == 2
    assert get_slot(22).target_house == "low" and get_slot(22).pair_position == 1
    assert get_slot(23).target_house == "high" and get_slot(23).pair_position == 2


def test_station_8_singles():
    assert get_slot(24).station == 8 and get_slot(24).target_house == "high"
    assert get_slot(25).station == 8 and get_slot(25).target_house == "low"


def test_validate_rejects_mismatch():
    try:
        validate_against_sequence(
            1, station=2, target_house="high", is_double=False, pair_position=0
        )
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "station=2" in str(exc)


def test_final_slot_lookup():
    s = get_slot(36, FORMAT_ISSF_FINAL_36)
    assert s.station == 5 and s.target_house == "high" and s.pair_position == 2


def test_station_drill_slots_reindexed():
    slots = slots_for_station(1)
    assert slots[0].sequence_order == 1
    assert slots[0].station == 1
    assert len(slots) == 3  # single + double
