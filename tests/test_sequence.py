"""Tests for ISSF 25-target sequence mapping."""

from skeet_tracker.sequence import ISSF_SEQUENCE, get_slot, validate_against_sequence


def test_sequence_length_and_order():
    assert len(ISSF_SEQUENCE) == 25
    assert [s.sequence_order for s in ISSF_SEQUENCE] == list(range(1, 26))


def test_station_1_single_and_double():
    assert get_slot(1).station == 1
    assert get_slot(1).target_house == "high"
    assert get_slot(1).is_double is False
    assert get_slot(1).pair_position == 0
    assert get_slot(2).pair_position == 1 and get_slot(2).target_house == "high"
    assert get_slot(3).pair_position == 2 and get_slot(3).target_house == "low"


def test_station_4_pass1_singles_and_pass2_reverse_doubles():
    assert get_slot(10).target_house == "high" and not get_slot(10).is_double
    assert get_slot(11).target_house == "low" and not get_slot(11).is_double
    # Reverse double 1: High then Low
    assert get_slot(20).target_house == "high" and get_slot(20).pair_position == 1
    assert get_slot(21).target_house == "low" and get_slot(21).pair_position == 2
    # Reverse double 2: Low then High
    assert get_slot(22).target_house == "low" and get_slot(22).pair_position == 1
    assert get_slot(23).target_house == "high" and get_slot(23).pair_position == 2


def test_station_8_singles():
    assert get_slot(24).station == 8 and get_slot(24).target_house == "high"
    assert get_slot(25).station == 8 and get_slot(25).target_house == "low"


def test_validate_rejects_mismatch():
    try:
        validate_against_sequence(1, station=2, target_house="high", is_double=False, pair_position=0)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "station=2" in str(exc)
