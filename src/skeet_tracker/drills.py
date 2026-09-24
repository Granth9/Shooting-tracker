"""Custom multi-station drills and saved templates."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from skeet_tracker.sequence import SequenceSlot

# One "rep" expands to one or more clay targets
BLOCK_KINDS: dict[str, dict[str, Any]] = {
    "high_single": {
        "name": "High single",
        "unit": [("high", False, 0)],
        "targets_per_rep": 1,
    },
    "low_single": {
        "name": "Low single",
        "unit": [("low", False, 0)],
        "targets_per_rep": 1,
    },
    "high_pair": {
        "name": "High pair",
        "unit": [("high", True, 1), ("low", True, 2)],
        "targets_per_rep": 2,
    },
    "low_pair": {
        "name": "Low pair",
        "unit": [("low", True, 1), ("high", True, 2)],
        "targets_per_rep": 2,
    },
}

# Older saved drills may still use these ids
KIND_ALIASES = {
    "regular_pair": "high_pair",
    "reverse_pair": "low_pair",
}


def normalize_kind(kind: str) -> str:
    return KIND_ALIASES.get(kind, kind)


@dataclass(frozen=True, slots=True)
class DrillBlock:
    station: int
    kind: str
    reps: int


def list_block_kinds() -> list[dict[str, Any]]:
    return [
        {
            "id": kid,
            "name": meta["name"],
            "targets_per_rep": meta["targets_per_rep"],
        }
        for kid, meta in BLOCK_KINDS.items()
    ]


def _label(s: SequenceSlot) -> str:
    if s.pair_position == 0:
        return f"Station {s.station} · {s.target_house.capitalize()} single"
    if s.pair_position == 1:
        pair = "High pair" if s.target_house == "high" else "Low pair"
        return f"Station {s.station} · {pair} · 1st"
    pair = "High pair" if s.target_house == "low" else "Low pair"
    return f"Station {s.station} · {pair} · 2nd"


def _slot_dict(s: SequenceSlot) -> dict[str, Any]:
    return {
        "sequence_order": s.sequence_order,
        "station": s.station,
        "target_house": s.target_house,
        "is_double": s.is_double,
        "pair_position": s.pair_position,
        "label": _label(s),
    }


def parse_blocks(raw: Iterable[dict[str, Any]]) -> list[DrillBlock]:
    blocks: list[DrillBlock] = []
    for item in raw:
        station = int(item["station"])
        kind = normalize_kind(str(item["kind"]))
        reps = int(item.get("reps", 1))
        if not 1 <= station <= 8:
            raise ValueError(f"station must be 1–8, got {station}")
        if kind not in BLOCK_KINDS:
            raise ValueError(f"Unknown block kind: {kind!r}")
        if not 1 <= reps <= 40:
            raise ValueError("reps must be between 1 and 40")
        blocks.append(DrillBlock(station=station, kind=kind, reps=reps))
    if not blocks:
        raise ValueError("Add at least one block")
    return blocks


def build_from_blocks(blocks: list[DrillBlock]) -> tuple[SequenceSlot, ...]:
    slots: list[SequenceSlot] = []
    order = 1
    for block in blocks:
        meta = BLOCK_KINDS[block.kind]
        unit: list[tuple[str, bool, int]] = meta["unit"]
        for _ in range(block.reps):
            for house, is_double, pair_pos in unit:
                slots.append(
                    SequenceSlot(
                        sequence_order=order,
                        station=block.station,
                        target_house=house,
                        is_double=is_double,
                        pair_position=pair_pos,
                        stage=0,
                    )
                )
                order += 1
                if order > 101:
                    raise ValueError("Drill exceeds 100 targets — split into two sessions")
    return tuple(slots)


def compose_payload(raw_blocks: list[dict[str, Any]], name: str | None = None) -> dict[str, Any]:
    blocks = parse_blocks(raw_blocks)
    slots = build_from_blocks(blocks)
    summary = summarize_blocks(blocks)
    return {
        "name": name or "Custom drill",
        "description": summary,
        "target_count": len(slots),
        "blocks": [
            {
                "station": b.station,
                "kind": b.kind,
                "kind_name": BLOCK_KINDS[b.kind]["name"],
                "reps": b.reps,
                "targets": b.reps * BLOCK_KINDS[b.kind]["targets_per_rep"],
            }
            for b in blocks
        ],
        "slots": [_slot_dict(s) for s in slots],
    }


def summarize_blocks(blocks: list[DrillBlock]) -> str:
    parts: list[str] = []
    for b in blocks:
        label = BLOCK_KINDS[b.kind]["name"]
        parts.append(f"St{b.station}: {b.reps}× {label}")
    return " · ".join(parts)


# --- Template persistence helpers ---

def normalize_saved_template_kinds(conn: sqlite3.Connection) -> None:
    """Rewrite legacy kind ids (regular_pair / reverse_pair) in saved templates."""
    rows = conn.execute(
        "SELECT template_id, blocks_json FROM drill_templates"
    ).fetchall()
    for row in rows:
        blocks = json.loads(row["blocks_json"])
        changed = False
        for b in blocks:
            nk = normalize_kind(b.get("kind", ""))
            if nk != b.get("kind"):
                b["kind"] = nk
                changed = True
        if changed:
            conn.execute(
                "UPDATE drill_templates SET blocks_json = ? WHERE template_id = ?",
                (json.dumps(blocks), row["template_id"]),
            )
    conn.commit()


def list_templates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT template_id, name, description, blocks_json, created_at
        FROM drill_templates
        ORDER BY name COLLATE NOCASE
        """
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        blocks = json.loads(r["blocks_json"])
        composed = compose_payload(blocks, name=r["name"])
        out.append(
            {
                "template_id": r["template_id"],
                "name": r["name"],
                "description": r["description"],
                "blocks": blocks,
                "target_count": composed["target_count"],
                "created_at": r["created_at"],
            }
        )
    return out


def get_template(conn: sqlite3.Connection, template_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT template_id, name, description, blocks_json, created_at
        FROM drill_templates WHERE template_id = ?
        """,
        (template_id,),
    ).fetchone()
    if not row:
        raise KeyError(template_id)
    blocks = json.loads(row["blocks_json"])
    composed = compose_payload(blocks, name=row["name"])
    return {
        "template_id": row["template_id"],
        "name": row["name"],
        "description": row["description"],
        "blocks": blocks,
        "target_count": composed["target_count"],
        "slots": composed["slots"],
        "created_at": row["created_at"],
    }


def save_template(
    conn: sqlite3.Connection,
    name: str,
    blocks: list[dict[str, Any]],
    description: str | None = None,
    template_id: str | None = None,
) -> dict[str, Any]:
    parse_blocks(blocks)  # validate
    composed = compose_payload(blocks, name=name)
    tid = template_id or str(uuid.uuid4())
    desc = description or composed["description"]
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    conn.execute(
        """
        INSERT INTO drill_templates (template_id, name, description, blocks_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(template_id) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            blocks_json = excluded.blocks_json
        """,
        (tid, name.strip() or "Custom drill", desc, json.dumps(blocks), now),
    )
    conn.commit()
    return get_template(conn, tid)


def delete_template(conn: sqlite3.Connection, template_id: str) -> None:
    cur = conn.execute(
        "DELETE FROM drill_templates WHERE template_id = ?", (template_id,)
    )
    conn.commit()
    if cur.rowcount == 0:
        raise KeyError(template_id)


# Keep simple station builder for backwards API compatibility
def build_station_drill(station: int, target_count: int, pattern: str = "double_hl") -> tuple[SequenceSlot, ...]:
    """Legacy single-station repeating pattern (used by older /api/drills/build)."""
    pattern_to_kind = {
        "single_high": "high_single",
        "single_low": "low_single",
        "singles_hl": None,  # special
        "double_hl": "high_pair",
        "double_lh": "low_pair",
        "doubles_both": None,
    }
    if pattern == "singles_hl":
        # Alternate H/L until count
        blocks: list[DrillBlock] = []
        remaining = target_count
        while remaining > 0:
            blocks.append(DrillBlock(station, "high_single", 1))
            remaining -= 1
            if remaining <= 0:
                break
            blocks.append(DrillBlock(station, "low_single", 1))
            remaining -= 1
        return build_from_blocks(blocks)
    if pattern == "doubles_both":
        # Repeat regular+reverse until enough targets
        slots: list[SequenceSlot] = []
        while len(slots) < target_count:
            chunk = build_from_blocks(
                [
                    DrillBlock(station, "high_pair", 1),
                    DrillBlock(station, "low_pair", 1),
                ]
            )
            for s in chunk:
                if len(slots) >= target_count:
                    break
                slots.append(
                    SequenceSlot(
                        sequence_order=len(slots) + 1,
                        station=s.station,
                        target_house=s.target_house,
                        is_double=s.is_double,
                        pair_position=s.pair_position,
                    )
                )
        return tuple(slots)

    kind = pattern_to_kind.get(pattern)
    if not kind:
        raise ValueError(f"Unknown pattern: {pattern!r}")
    per = BLOCK_KINDS[kind]["targets_per_rep"]
    reps = max(1, (target_count + per - 1) // per)
    slots = build_from_blocks([DrillBlock(station, kind, reps)])
    return slots[:target_count]


def list_patterns() -> list[dict[str, str]]:
    return [
        {"id": "single_high", "name": "Singles · High only"},
        {"id": "single_low", "name": "Singles · Low only"},
        {"id": "singles_hl", "name": "Singles · High then Low (repeat)"},
        {"id": "double_hl", "name": "Doubles · High / Low (repeat)"},
        {"id": "double_lh", "name": "Doubles · Low / High (repeat)"},
        {"id": "doubles_both", "name": "Doubles · H/L then L/H (repeat)"},
    ]


def list_presets() -> list[dict[str, Any]]:
    return []


def build_payload(station: int, target_count: int, pattern: str) -> dict[str, Any]:
    slots = build_station_drill(station, target_count, pattern)
    # re-index after truncate
    slots = tuple(
        SequenceSlot(
            sequence_order=i,
            station=s.station,
            target_house=s.target_house,
            is_double=s.is_double,
            pair_position=s.pair_position,
        )
        for i, s in enumerate(slots, start=1)
    )
    return {
        "station": station,
        "pattern": pattern,
        "target_count": len(slots),
        "name": f"Station {station} · {len(slots)} targets",
        "description": f"{pattern} on station {station} ({len(slots)} targets).",
        "slots": [_slot_dict(s) for s in slots],
    }
