"""Session ingest: ISSF 25, ISSF Final 36, and drills."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from skeet_tracker.models import (
    MissDirection,
    RoundInput,
    SessionFormat,
    ShotInput,
    ShotRecord,
    TrainingLoad,
)
from skeet_tracker.sequence import (
    FORMAT_DRILL,
    FORMAT_ISSF_25,
    FORMAT_ISSF_FINAL_36,
    enrich_from_sequence,
    validate_against_sequence,
)

VALID_EVENT_TYPES = frozenset({"practice", "qualification", "final", "drill"})
VALID_FORMATS = frozenset({FORMAT_ISSF_25, FORMAT_ISSF_FINAL_36, FORMAT_DRILL})
VALID_MISS = frozenset({"behind", "above", "below", "ahead", "unknown"})


class IngestError(ValueError):
    """Raised when session or shot data fails validation."""


def _miss_direction(shot: ShotInput) -> Optional[MissDirection]:
    if shot.is_hit:
        return None
    if shot.miss_direction is None:
        return "unknown"
    direction = shot.miss_direction.lower()  # type: ignore[union-attr]
    if direction not in VALID_MISS:
        raise IngestError(f"Invalid miss_direction: {shot.miss_direction!r}")
    return direction  # type: ignore[return-value]


def resolve_shot(
    shot: ShotInput,
    format_id: SessionFormat = FORMAT_ISSF_25,
) -> ShotRecord:
    """Resolve station/house/pair from the session format (or explicit drill fields)."""
    if format_id == FORMAT_DRILL:
        if shot.station is None or shot.target_house is None:
            raise IngestError(
                f"Drill shot {shot.sequence_order} requires station and target_house"
            )
        if shot.pair_position is None:
            raise IngestError(
                f"Drill shot {shot.sequence_order} requires pair_position (0/1/2)"
            )
        is_double = (
            bool(shot.is_double)
            if shot.is_double is not None
            else shot.pair_position in (1, 2)
        )
        if not 1 <= shot.station <= 8:
            raise IngestError("station must be 1–8")
        house = shot.target_house.lower()
        if house not in ("high", "low"):
            raise IngestError("target_house must be 'high' or 'low'")
        if shot.pair_position not in (0, 1, 2):
            raise IngestError("pair_position must be 0, 1, or 2")
        return ShotRecord(
            sequence_order=shot.sequence_order,
            station=int(shot.station),
            target_house=house,
            is_double=is_double,
            pair_position=int(shot.pair_position),
            is_hit=bool(shot.is_hit),
            miss_direction=_miss_direction(shot),
        )

    # Fixed ISSF sequences
    max_order = 25 if format_id == FORMAT_ISSF_25 else 36
    if not 1 <= shot.sequence_order <= max_order:
        raise IngestError(
            f"sequence_order must be 1–{max_order} for {format_id}, "
            f"got {shot.sequence_order}"
        )

    slot = enrich_from_sequence(shot.sequence_order, format_id)
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
            shot.sequence_order,
            station,
            target_house,
            is_double,
            pair_position,
            format_id,
        )
    except ValueError as exc:
        raise IngestError(str(exc)) from exc

    return ShotRecord(
        sequence_order=shot.sequence_order,
        station=station,
        target_house=target_house,
        is_double=is_double,
        pair_position=pair_position,
        is_hit=bool(shot.is_hit),
        miss_direction=_miss_direction(shot),
    )


def _infer_format(round_input: RoundInput) -> SessionFormat:
    if round_input.format in VALID_FORMATS:
        return round_input.format  # type: ignore[return-value]
    if round_input.event_type == "drill":
        return FORMAT_DRILL
    if round_input.event_type == "final":
        return FORMAT_ISSF_FINAL_36
    return FORMAT_ISSF_25


def validate_round(round_input: RoundInput) -> list[ShotRecord]:
    """Validate session metadata and return resolved ShotRecords."""
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

    format_id = _infer_format(round_input)
    shots_in = round_input.shots
    if not shots_in:
        raise IngestError("At least one shot is required")

    orders = [s.sequence_order for s in shots_in]
    if len(orders) != len(set(orders)):
        raise IngestError("sequence_order values must be unique")

    if format_id == FORMAT_ISSF_25:
        if round_input.event_type == "drill":
            raise IngestError("drill event_type requires format=drill")
        if len(shots_in) != 25:
            raise IngestError(f"ISSF round expects 25 shots, got {len(shots_in)}")
        if sorted(orders) != list(range(1, 26)):
            raise IngestError("shots must cover sequence_order 1–25 exactly once")

    elif format_id == FORMAT_ISSF_FINAL_36:
        if round_input.event_type not in ("final", "practice"):
            # Allow practice finals simulation
            if round_input.event_type != "qualification":
                pass
        n = len(shots_in)
        if n > 36:
            raise IngestError("ISSF final allows at most 36 shots")
        if sorted(orders) != list(range(1, n + 1)):
            raise IngestError(
                "Final shots must be a contiguous prefix 1..N "
                "(use N=12/24/28/32/36 if eliminated early)"
            )

    elif format_id == FORMAT_DRILL:
        if round_input.event_type != "drill":
            raise IngestError("format=drill requires event_type=drill")
        if n := len(shots_in):
            if sorted(orders) != list(range(1, n + 1)):
                raise IngestError("Drill shots must use contiguous sequence_order 1..N")
        if n > 100:
            raise IngestError("Drill supports at most 100 shots")

    else:
        raise IngestError(f"Unknown format: {format_id!r}")

    # Persist inferred format back for insert
    round_input.format = format_id  # type: ignore[assignment]

    return [
        resolve_shot(s, format_id)
        for s in sorted(shots_in, key=lambda x: x.sequence_order)
    ]


def insert_round(conn: sqlite3.Connection, round_input: RoundInput) -> str:
    """Validate and insert a session with shots. Returns round_id."""
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
                round_id, timestamp, event_type, format, drill_name,
                location, round_number, weather_condition, wind_speed_mph,
                choke_used, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                round_input.round_id,
                ts_str,
                round_input.event_type,
                round_input.format,
                round_input.drill_name,
                round_input.location,
                round_input.round_number,
                round_input.weather_condition,
                round_input.wind_speed_mph,
                round_input.choke_used,
                round_input.notes,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise IngestError(f"Could not insert session: {exc}") from exc

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

    fmt = data.get("format")
    if fmt is None:
        if event_type == "drill":
            fmt = FORMAT_DRILL
        elif event_type == "final":
            fmt = FORMAT_ISSF_FINAL_36
        else:
            fmt = FORMAT_ISSF_25
    if fmt not in VALID_FORMATS:
        raise IngestError(f"Invalid format: {fmt!r}")

    raw_shots = data.get("shots")
    if not isinstance(raw_shots, list):
        raise IngestError("'shots' must be a list")

    shots: list[ShotInput] = []
    for item in raw_shots:
        if not isinstance(item, dict):
            raise IngestError("Each shot must be an object")
        if "sequence_order" not in item or "is_hit" not in item:
            raise IngestError("Each shot requires sequence_order and is_hit")
        shots.append(
            ShotInput(
                sequence_order=int(item["sequence_order"]),
                is_hit=bool(item["is_hit"]),
                miss_direction=item.get("miss_direction"),
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
        format=fmt,  # type: ignore[arg-type]
        drill_name=data.get("drill_name"),
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
    """Load and parse a session JSON file."""
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise IngestError("Session JSON must be an object")
    return round_from_dict(data)


def fetch_all_shots(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Join shots with session metadata for analytics queries."""
    cur = conn.execute(
        """
        SELECT
            s.*,
            r.event_type,
            r.format,
            r.drill_name,
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
