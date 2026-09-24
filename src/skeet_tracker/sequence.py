"""ISSF sequence maps: qualification 25-target round and 2026 Final (36 targets)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class SequenceSlot:
    """Canonical metadata for one target in an ISSF sequence."""

    sequence_order: int
    station: int
    target_house: str  # 'high' | 'low'
    is_double: bool
    pair_position: int  # 0=Single, 1=First, 2=Second
    stage: int = 0  # finals elimination stage (0 for qual rounds)


def _slot(
    order: int,
    station: int,
    house: str,
    is_double: bool,
    pair_position: int,
    stage: int = 0,
) -> SequenceSlot:
    return SequenceSlot(
        sequence_order=order,
        station=station,
        target_house=house,
        is_double=is_double,
        pair_position=pair_position,
        stage=stage,
    )


def _regular_double(order: int, station: int, stage: int = 0) -> tuple[SequenceSlot, SequenceSlot]:
    """High then Low."""
    return (
        _slot(order, station, "high", True, 1, stage),
        _slot(order + 1, station, "low", True, 2, stage),
    )


def _reverse_double(order: int, station: int, stage: int = 0) -> tuple[SequenceSlot, SequenceSlot]:
    """Low then High."""
    return (
        _slot(order, station, "low", True, 1, stage),
        _slot(order + 1, station, "high", True, 2, stage),
    )


def _station_block_12(start: int, stage: int) -> tuple[SequenceSlot, ...]:
    """
    One finals block (12 targets): regular + reverse on stations 3, 4, and 5.
    ISSF Rule 9.17.4.2 (2026).
    """
    slots: list[SequenceSlot] = []
    order = start
    for station in (3, 4, 5):
        slots.extend(_regular_double(order, station, stage))
        order += 2
        slots.extend(_reverse_double(order, station, stage))
        order += 2
    return tuple(slots)


# Official ISSF 25-Target Round Mapping (qualification / practice)
ISSF_SEQUENCE: tuple[SequenceSlot, ...] = (
    _slot(1, 1, "high", False, 0),
    *_regular_double(2, 1),
    _slot(4, 2, "high", False, 0),
    *_regular_double(5, 2),
    _slot(7, 3, "high", False, 0),
    *_regular_double(8, 3),
    _slot(10, 4, "high", False, 0),
    _slot(11, 4, "low", False, 0),
    _slot(12, 5, "low", False, 0),
    *_reverse_double(13, 5),  # Low/High on stations 5–7
    _slot(15, 6, "low", False, 0),
    *_reverse_double(16, 6),
    *_reverse_double(18, 7),
    *_regular_double(20, 4),  # Station 4 Pass 2 reverse double 1 = High/Low
    *_reverse_double(22, 4),  # Reverse double 2 = Low/High
    _slot(24, 8, "high", False, 0),
    _slot(25, 8, "low", False, 0),
)

# Wait - I may have broken the original sequence. Let me check original:
# Station 5 double was Low/High - yes reverse
# Station 6 double Low/High - reverse
# Station 7 Double Low/High - reverse
# Station 4 Pass 2: Reverse Double 1 High/Low, Reverse Double 2 Low/High
# Original said:
# 20-21 Station 4 Reverse Double 1 High/Low
# 22-23 Station 4 Reverse Double 2 Low/High
# So 20-21 is High then Low = regular_double, 22-23 is Low then High = reverse_double
# Good.

assert len(ISSF_SEQUENCE) == 25
assert all(s.sequence_order == i for i, s in enumerate(ISSF_SEQUENCE, start=1))

# ISSF 2026 Skeet Final — 36 targets (Rule 9.17.4.2)
# Stage 1 (1–12): 8 athletes; eliminate 7th & 8th
# Stage 2 (13–24): 6 athletes; eliminate 5th & 6th
# Stage 3 (25–28): 4 athletes; St3 only; eliminate 4th
# Stage 4 (29–32): 3 athletes; St4 only; bronze
# Stage 5 (33–36): 2 athletes; St5 only; gold/silver
ISSF_FINAL_36: tuple[SequenceSlot, ...] = (
    *_station_block_12(1, stage=1),
    *_station_block_12(13, stage=2),
    *_regular_double(25, 3, stage=3),
    *_reverse_double(27, 3, stage=3),
    *_regular_double(29, 4, stage=4),
    *_reverse_double(31, 4, stage=4),
    *_regular_double(33, 5, stage=5),
    *_reverse_double(35, 5, stage=5),
)

assert len(ISSF_FINAL_36) == 36
assert all(s.sequence_order == i for i, s in enumerate(ISSF_FINAL_36, start=1))

# Elimination checkpoints (targets completed when places are decided)
FINAL_ELIMINATION_TARGETS = (12, 24, 28, 32, 36)

FORMAT_ISSF_25 = "issf_25"
FORMAT_ISSF_FINAL_36 = "issf_final_36"
FORMAT_DRILL = "drill"

_BY_ORDER_25: dict[int, SequenceSlot] = {s.sequence_order: s for s in ISSF_SEQUENCE}
_BY_ORDER_36: dict[int, SequenceSlot] = {s.sequence_order: s for s in ISSF_FINAL_36}


def get_sequence(format_id: str) -> tuple[SequenceSlot, ...]:
    if format_id == FORMAT_ISSF_25:
        return ISSF_SEQUENCE
    if format_id == FORMAT_ISSF_FINAL_36:
        return ISSF_FINAL_36
    raise ValueError(f"No fixed sequence for format {format_id!r}")


def get_slot(sequence_order: int, format_id: str = FORMAT_ISSF_25) -> SequenceSlot:
    if format_id == FORMAT_ISSF_25:
        try:
            return _BY_ORDER_25[sequence_order]
        except KeyError as exc:
            raise ValueError(f"sequence_order must be 1–25, got {sequence_order}") from exc
    if format_id == FORMAT_ISSF_FINAL_36:
        try:
            return _BY_ORDER_36[sequence_order]
        except KeyError as exc:
            raise ValueError(f"sequence_order must be 1–36, got {sequence_order}") from exc
    raise ValueError(f"No slot lookup for format {format_id!r}")


def validate_against_sequence(
    sequence_order: int,
    station: int,
    target_house: str,
    is_double: bool,
    pair_position: int,
    format_id: str = FORMAT_ISSF_25,
) -> None:
    """Raise ValueError if shot metadata does not match the chosen sequence."""
    slot = get_slot(sequence_order, format_id)
    house = target_house.lower()
    mismatches: list[str] = []
    if station != slot.station:
        mismatches.append(f"station={station} (expected {slot.station})")
    if house != slot.target_house:
        mismatches.append(f"target_house={target_house!r} (expected {slot.target_house!r})")
    if bool(is_double) != slot.is_double:
        mismatches.append(f"is_double={is_double} (expected {slot.is_double})")
    if pair_position != slot.pair_position:
        mismatches.append(f"pair_position={pair_position} (expected {slot.pair_position})")
    if mismatches:
        raise ValueError(
            f"Shot sequence_order={sequence_order} does not match {format_id}: "
            + "; ".join(mismatches)
        )


def enrich_from_sequence(
    sequence_order: int,
    format_id: str = FORMAT_ISSF_25,
) -> SequenceSlot:
    return get_slot(sequence_order, format_id)


def all_slots(format_id: str = FORMAT_ISSF_25) -> Sequence[SequenceSlot]:
    return get_sequence(format_id)


def slots_for_station(station: int) -> tuple[SequenceSlot, ...]:
    """Qualification-round slots for one station (for drill presets), re-indexed from 1."""
    if not 1 <= station <= 8:
        raise ValueError("station must be 1–8")
    raw = [s for s in ISSF_SEQUENCE if s.station == station]
    return tuple(
        SequenceSlot(
            sequence_order=i,
            station=s.station,
            target_house=s.target_house,
            is_double=s.is_double,
            pair_position=s.pair_position,
            stage=0,
        )
        for i, s in enumerate(raw, start=1)
    )


def finals_block_12() -> tuple[SequenceSlot, ...]:
    """Single 12-target finals block (St 3/4/5 regular+reverse) as a drill preset."""
    return tuple(
        SequenceSlot(
            sequence_order=i,
            station=s.station,
            target_house=s.target_house,
            is_double=s.is_double,
            pair_position=s.pair_position,
            stage=1,
        )
        for i, s in enumerate(_station_block_12(1, stage=1), start=1)
    )
