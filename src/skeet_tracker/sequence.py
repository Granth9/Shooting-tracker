"""Official ISSF 25-target International Skeet sequence mapping."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class SequenceSlot:
    """Canonical metadata for one target in the ISSF 25-target round."""

    sequence_order: int
    station: int
    target_house: str  # 'high' | 'low'
    is_double: bool
    pair_position: int  # 0=Single, 1=First, 2=Second


def _slot(
    order: int,
    station: int,
    house: str,
    is_double: bool,
    pair_position: int,
) -> SequenceSlot:
    return SequenceSlot(
        sequence_order=order,
        station=station,
        target_house=house,
        is_double=is_double,
        pair_position=pair_position,
    )


# Official ISSF 25-Target Round Mapping
ISSF_SEQUENCE: tuple[SequenceSlot, ...] = (
    # Station 1: Single High, then Double High/Low
    _slot(1, 1, "high", False, 0),
    _slot(2, 1, "high", True, 1),
    _slot(3, 1, "low", True, 2),
    # Station 2: Single High, then Double High/Low
    _slot(4, 2, "high", False, 0),
    _slot(5, 2, "high", True, 1),
    _slot(6, 2, "low", True, 2),
    # Station 3: Single High, then Double High/Low
    _slot(7, 3, "high", False, 0),
    _slot(8, 3, "high", True, 1),
    _slot(9, 3, "low", True, 2),
    # Station 4 Pass 1: Single High, Single Low
    _slot(10, 4, "high", False, 0),
    _slot(11, 4, "low", False, 0),
    # Station 5: Single Low, then Double Low/High
    _slot(12, 5, "low", False, 0),
    _slot(13, 5, "low", True, 1),
    _slot(14, 5, "high", True, 2),
    # Station 6: Single Low, then Double Low/High
    _slot(15, 6, "low", False, 0),
    _slot(16, 6, "low", True, 1),
    _slot(17, 6, "high", True, 2),
    # Station 7: Double Low/High only
    _slot(18, 7, "low", True, 1),
    _slot(19, 7, "high", True, 2),
    # Station 4 Pass 2: Reverse Double High/Low, then Low/High
    _slot(20, 4, "high", True, 1),
    _slot(21, 4, "low", True, 2),
    _slot(22, 4, "low", True, 1),
    _slot(23, 4, "high", True, 2),
    # Station 8: Single High, Single Low
    _slot(24, 8, "high", False, 0),
    _slot(25, 8, "low", False, 0),
)

assert len(ISSF_SEQUENCE) == 25
assert all(s.sequence_order == i for i, s in enumerate(ISSF_SEQUENCE, start=1))

_BY_ORDER: dict[int, SequenceSlot] = {s.sequence_order: s for s in ISSF_SEQUENCE}


def get_slot(sequence_order: int) -> SequenceSlot:
    """Return the canonical slot for a 1-based sequence order."""
    try:
        return _BY_ORDER[sequence_order]
    except KeyError as exc:
        raise ValueError(f"sequence_order must be 1–25, got {sequence_order}") from exc


def validate_against_sequence(
    sequence_order: int,
    station: int,
    target_house: str,
    is_double: bool,
    pair_position: int,
) -> None:
    """Raise ValueError if shot metadata does not match the official sequence."""
    slot = get_slot(sequence_order)
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
            f"Shot sequence_order={sequence_order} does not match ISSF sequence: "
            + "; ".join(mismatches)
        )


def enrich_from_sequence(
    sequence_order: int,
) -> SequenceSlot:
    """Lookup canonical metadata for a sequence order (used during JSON ingest)."""
    return get_slot(sequence_order)


def all_slots() -> Sequence[SequenceSlot]:
    return ISSF_SEQUENCE
