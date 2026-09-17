"""Round and training-load ingest with ISSF sequence validation."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from skeet_tracker.models import (
    EventType,
    MissDirection,
    RoundInput,
    ShotInput,
    ShotRecord,
    TrainingLoad,
)
from skeet_tracker.sequence import enrich_from_sequence, validate_against_sequence

VALID_EVENT_TYPES = frozenset({"practice", "qualification", "final"})
VALID_MISS = frozenset({"behind", "above", "below", "ahead", "unknown"})


class IngestError(ValueError):
    """Raised when round or shot data fails validation."""


def resolve_shot(shot: ShotInput) -> ShotRecord:
    """Fill ISSF metadata and validate optional overrides."""
    if not 1 <= shot.sequence_order <= 25:
        raise IngestError(f"sequence_order must be 1–25, got {shot.sequence_order}")

    slot = enrich_from_sequence(shot.sequence_order)

    station = shot.station if shot.station is not None else slot.station
    target_house = (
        shot.target_house.lower() if shot.target_house is not None else slot.target_house
    )
    is_double = shot.is_double if shot.is_double is not None else slot.is_double
    pair_position = (
        shot.pair_position if shot.pair_position is not None else slot.pair_position
    )

    try:
        validate_against_sequence(
            shot.sequence_order, station, target_house, is_double, pair_position
        )
    except ValueError as exc:
        raise IngestError(str(exc)) from exc

    miss: Optional[MissDirection] = None
    if shot.is_hit:
        miss = None
    else:
        if shot.miss_direction is None:
            miss = "unknown"
        else:
            direction = shot.miss_direction.lower()  # type: ignore[union-attr]
            if direction not in VALID_MISS:
                raise IngestError(f"Invalid miss_direction: {shot.miss_direction!r}")
            miss = direction  # type: ignore[assignment]

    return ShotRecord(
        sequence_order=shot.sequence_order,
        station=station,
        target_house=target_house,
        is_double=is_double,
        pair_position=pair_position,
        is_hit=bool(shot.is_hit),
        miss_direction=miss,
    )


def validate_round(round_input: RoundInput) -> list[ShotRecord]:
    """Validate round metadata and return 25 resolved ShotRecords."""
    if round_input.event_type not in VALID_EVENT_TYPES:
        raise IngestError(
            f"event_type must be one of {sorted(VALID_EVENT_TYPES)}, "
            f"got {round_input.event_type!r}"
        )
    if not round_input.round_id:
        raise IngestError("round_id is required")
    if round_input.round_number is not None and not (
        1 <= round_input.round_number <= 5
    ):
        raise IngestError("round_number must be between 1 and 5")
    if round_input.wind_speed_mph is not None and round_input.wind_speed_mph < 0:
        raise IngestError("wind_speed_mph must be >= 0")

    if len(round_input.shots) != 25:
        raise IngestError(f"Expected 25 shots, got {len(round_input.shots)}")

    orders = [s.sequence_order for s in round_input.shots]
    if sorted(orders) != list(range(1, 26)):
        raise IngestError("shots must cover sequence_order 1–25 exactly once")

    return [resolve_shot(s) for s in sorted(round_input.shots, key=lambda x: x.sequence_order)]


def insert_round(conn: sqlite3.Connection, round_input: RoundInput) -> str:
    """Validate and insert a round with 25 shots. Returns round_id."""
    shots = validate_round(round_input)
    ts = round_input.timestamp or datetime.now()
    if isinstance(ts, datetime):
        ts_str = ts.isoformat(sep=" ", timespec="seconds")
    else:
        ts_str = str(ts)

    try:
        conn.execute(
            """
            INSERT INTO rounds (
                round_id, timestamp, event_type, location, round_number,
                weather_condition, wind_speed_mph, choke_used, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                round_input.round_id,
                ts_str,
                round_input.event_type,
                round_input.location,
                round_input.round_number,
                round_input.weather_condition,
                round_input.wind_speed_mph,
                round_input.choke_used,
                round_input.notes,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise IngestError(f"Could not insert round: {exc}") from exc

    for shot in shots:
        conn.execute(
            """
            INSERT INTO shots (
                round_id, sequence_order, station, target_house,
                is_double, pair_position, is_hit, miss_direction
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                round_input.round_id,
                shot.sequence_order,
                shot.station,
                shot.target_house,
                int(shot.is_double),
                shot.pair_position,
                int(shot.is_hit),
                shot.miss_direction,
            ),
        )
    conn.commit()
    return round_input.round_id


def insert_training_load(conn: sqlite3.Connection, load: TrainingLoad) -> str:
    """Upsert a daily training workload. Returns load_date."""
    if load.workload < 0:
        raise IngestError("workload must be >= 0")
    conn.execute(
        """
        INSERT INTO training_loads (load_date, workload, notes)
        VALUES (?, ?, ?)
        ON CONFLICT(load_date) DO UPDATE SET
            workload = excluded.workload,
            notes = excluded.notes
        """,
        (load.load_date, load.workload, load.notes),
    )
    conn.commit()
    return load.load_date


def round_from_dict(data: dict[str, Any]) -> RoundInput:
    """Build RoundInput from a JSON-compatible dict."""
    round_id = data.get("round_id") or str(uuid.uuid4())
    event_type = data.get("event_type", "practice")
    if event_type not in VALID_EVENT_TYPES:
        raise IngestError(f"Invalid event_type: {event_type!r}")

    raw_shots = data.get("shots")
    if not isinstance(raw_shots, list):
        raise IngestError("'shots' must be a list")

    shots: list[ShotInput] = []
    for item in raw_shots:
        if not isinstance(item, dict):
            raise IngestError("Each shot must be an object")
        if "sequence_order" not in item or "is_hit" not in item:
            raise IngestError("Each shot requires sequence_order and is_hit")
        miss = item.get("miss_direction")
        shots.append(
            ShotInput(
                sequence_order=int(item["sequence_order"]),
                is_hit=bool(item["is_hit"]),
                miss_direction=miss,
                station=item.get("station"),
                target_house=item.get("target_house"),
                is_double=item.get("is_double"),
                pair_position=item.get("pair_position"),
            )
        )

    ts = data.get("timestamp")
    timestamp: Optional[datetime] = None
    if isinstance(ts, str) and ts:
        timestamp = datetime.fromisoformat(ts.replace("Z", "+00:00"))

    return RoundInput(
        round_id=str(round_id),
        event_type=event_type,  # type: ignore[arg-type]
        shots=shots,
        location=data.get("location"),
        round_number=data.get("round_number"),
        weather_condition=data.get("weather_condition"),
        wind_speed_mph=data.get("wind_speed_mph"),
        choke_used=data.get("choke_used"),
        notes=data.get("notes"),
        timestamp=timestamp,
    )


def load_round_json(path: str | Path) -> RoundInput:
    """Load and parse a round JSON file."""
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise IngestError("Round JSON must be an object")
    return round_from_dict(data)


def fetch_all_shots(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Join shots with round metadata for analytics queries."""
    cur = conn.execute(
        """
        SELECT
            s.*,
            r.event_type,
            r.round_number,
            r.wind_speed_mph,
            r.timestamp,
            r.location
        FROM shots s
        JOIN rounds r ON r.round_id = s.round_id
        ORDER BY r.timestamp, s.sequence_order
        """
    )
    return list(cur.fetchall())


def fetch_rounds(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = conn.execute(
        """
        SELECT r.*,
            (SELECT COUNT(*) FROM shots s WHERE s.round_id = r.round_id AND s.is_hit = 1) AS hits,
            (SELECT COUNT(*) FROM shots s WHERE s.round_id = r.round_id) AS shots
        FROM rounds r
        ORDER BY r.timestamp
        """
    )
    return list(cur.fetchall())


def fetch_training_loads(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cur = conn.execute(
        "SELECT load_date, workload, notes FROM training_loads ORDER BY load_date"
    )
    return list(cur.fetchall())
