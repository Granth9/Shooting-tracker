"""Dataclasses for rounds, shots, drills, and training loads."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

EventType = Literal["practice", "qualification", "final", "drill"]
SessionFormat = Literal["issf_25", "issf_final_36", "drill"]
MissDirection = Literal["behind", "above", "below", "ahead", "unknown"]


@dataclass(slots=True)
class ShotInput:
    """Shot fields supplied by the user."""

    sequence_order: int
    is_hit: bool
    miss_direction: Optional[MissDirection] = None
    # Optional — filled from sequence for ISSF formats; required for freeform drills
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
    """Session metadata plus shot outcomes (25, up to 36, or drill N)."""

    round_id: str
    event_type: EventType
    shots: list[ShotInput]
    format: SessionFormat = "issf_25"
    drill_name: Optional[str] = None
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
    format: SessionFormat = "issf_25"
    shots: list[ShotRecord] = field(default_factory=list)
    drill_name: Optional[str] = None
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
