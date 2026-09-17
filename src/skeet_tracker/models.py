"""Dataclasses for rounds, shots, and training loads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

EventType = Literal["practice", "qualification", "final"]
MissDirection = Literal["behind", "above", "below", "ahead", "unknown"]


@dataclass(slots=True)
class ShotInput:
    """Minimal shot fields supplied by the user (sequence filled from ISSF map)."""

    sequence_order: int
    is_hit: bool
    miss_direction: Optional[MissDirection] = None
    # Optional overrides — validated against ISSF sequence when provided
    station: Optional[int] = None
    target_house: Optional[str] = None
    is_double: Optional[bool] = None
    pair_position: Optional[int] = None


@dataclass(slots=True)
class ShotRecord:
    """Fully resolved shot ready for persistence."""

    sequence_order: int
    station: int
    target_house: str
    is_double: bool
    pair_position: int
    is_hit: bool
    miss_direction: Optional[MissDirection] = None
    shot_id: Optional[int] = None
    round_id: Optional[str] = None


@dataclass(slots=True)
class RoundInput:
    """Round metadata plus 25 shot outcomes."""

    round_id: str
    event_type: EventType
    shots: list[ShotInput]
    location: Optional[str] = None
    round_number: Optional[int] = None
    weather_condition: Optional[str] = None
    wind_speed_mph: Optional[int] = None
    choke_used: Optional[str] = None
    notes: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass(slots=True)
class RoundRecord:
    round_id: str
    event_type: EventType
    shots: list[ShotRecord] = field(default_factory=list)
    location: Optional[str] = None
    round_number: Optional[int] = None
    weather_condition: Optional[str] = None
    wind_speed_mph: Optional[int] = None
    choke_used: Optional[str] = None
    notes: Optional[str] = None
    timestamp: Optional[datetime] = None


@dataclass(slots=True)
class TrainingLoad:
    load_date: str  # ISO date YYYY-MM-DD
    workload: float
    notes: Optional[str] = None
