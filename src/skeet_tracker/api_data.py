"""Structured JSON payloads for the web UI (wraps existing analytics)."""

from __future__ import annotations

import sqlite3
from typing import Any

from skeet_tracker.analytics.diagnostics import compute_diagnostics
from skeet_tracker.analytics.markov import compute_markov, pairs_from_shots
from skeet_tracker.analytics.periodization import (
    BanisterParams,
    acwr_series,
    banister_performance,
    compute_prs,
    daily_workload_series,
    round_hit_rates,
)
from skeet_tracker.analytics.stations import compute_sdi
from skeet_tracker.competitions import competition_timeline, results_payload
from skeet_tracker.drills import (
    build_payload,
    compose_payload,
    list_block_kinds,
    list_patterns,
    list_presets,
    list_templates,
)
from skeet_tracker.ingest import fetch_all_shots, fetch_rounds, fetch_training_loads
from skeet_tracker.sequence import (
    FORMAT_ISSF_25,
    FORMAT_ISSF_FINAL_36,
    FINAL_ELIMINATION_TARGETS,
    get_sequence,
)


def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def _slot_label(s) -> str:
    house = s.target_house.capitalize()
    if s.pair_position == 0:
        kind = "Single"
    elif s.pair_position == 1:
        kind = "1st"
    else:
        kind = "2nd"
    label = f"St {s.station} · {house} · {kind}"
    if getattr(s, "stage", 0):
        label += f" · stage {s.stage}"
    return label


def sequence_payload(format_id: str = FORMAT_ISSF_25) -> dict[str, Any]:
    slots = get_sequence(format_id)
    return {
        "format": format_id,
        "target_count": len(slots),
        "elimination_targets": (
            list(FINAL_ELIMINATION_TARGETS)
            if format_id == FORMAT_ISSF_FINAL_36
            else None
        ),
        "slots": [
            {
                "sequence_order": s.sequence_order,
                "station": s.station,
                "target_house": s.target_house,
                "is_double": s.is_double,
                "pair_position": s.pair_position,
                "stage": s.stage,
                "label": _slot_label(s),
            }
            for s in slots
        ],
    }


def drills_payload(conn: sqlite3.Connection | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "presets": list_presets(),
        "patterns": list_patterns(),
        "block_kinds": list_block_kinds(),
        "stations": list(range(1, 9)),
        "max_targets": 100,
        "templates": [],
    }
    if conn is not None:
        payload["templates"] = list_templates(conn)
    return payload


def build_drill_payload(station: int, target_count: int, pattern: str) -> dict[str, Any]:
    return build_payload(station, target_count, pattern)


def compose_drill_payload(
    blocks: list[dict[str, Any]], name: str | None = None
) -> dict[str, Any]:
    return compose_payload(blocks, name=name)


def dashboard_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    rounds = fetch_rounds(conn)
    shots = _rows(fetch_all_shots(conn))
    loads = fetch_training_loads(conn)

    if not rounds:
        return {
            "empty": True,
            "rounds": 0,
            "overall": None,
            "recent_form": None,
            "by_event": {},
            "diagnostics": None,
            "readiness": None,
            "recent_rounds": [],
            "competition_timeline": competition_timeline(conn),
        }

    # Overall excludes drills so competition form stays clean; include all for volume
    comp = [r for r in rounds if r["event_type"] != "drill"]
    drill_rounds = [r for r in rounds if r["event_type"] == "drill"]

    def _rate(rows: list) -> tuple[int, int, float | None]:
        h = sum(int(r["hits"]) for r in rows)
        s = sum(int(r["shots"]) for r in rows)
        return h, s, (h / s if s else None)

    total_hits, total_shots, overall = _rate(list(comp) if comp else list(rounds))
    drill_hits, drill_shots, drill_rate = _rate(drill_rounds)

    by_event: dict[str, dict[str, Any]] = {}
    for r in rounds:
        et = r["event_type"]
        bucket = by_event.setdefault(et, {"hits": 0, "shots": 0, "n": 0})
        bucket["hits"] += int(r["hits"])
        bucket["shots"] += int(r["shots"])
        bucket["n"] += 1
    for et, b in by_event.items():
        b["rate"] = b["hits"] / b["shots"] if b["shots"] else None

    # Form uses competition sessions only (practice / qual / final)
    rates = round_hit_rates(comp if comp else rounds)
    recent = rates[-5:] if rates else []
    recent_form = sum(recent) / len(recent) if recent else None

    # Diagnostics from competition shots only
    comp_shots = [s for s in shots if s.get("event_type") != "drill"]
    diag = compute_diagnostics(comp_shots)

    days, workloads = daily_workload_series(_rows(loads))
    last_acwr = None
    last_p = None
    if workloads:
        last_acwr = acwr_series(workloads)[-1]
        last_p = banister_performance(workloads, BanisterParams())[-1]
    prs = compute_prs(rates, acwr=last_acwr, banister_p=last_p)

    recent_rounds = []
    for r in list(rounds)[-10:][::-1]:
        shots_n = int(r["shots"])
        hits = int(r["hits"])
        recent_rounds.append(
            {
                "round_id": r["round_id"],
                "event_type": r["event_type"],
                "format": r["format"] if "format" in r.keys() else "issf_25",
                "drill_name": r["drill_name"] if "drill_name" in r.keys() else None,
                "timestamp": r["timestamp"],
                "hits": hits,
                "shots": shots_n,
                "rate": hits / shots_n if shots_n else None,
                "location": r["location"],
                "round_number": r["round_number"],
                "wind_speed_mph": r["wind_speed_mph"],
            }
        )

    return {
        "empty": False,
        "rounds": len(rounds),
        "competition_sessions": len(comp),
        "drill_sessions": len(drill_rounds),
        "overall": overall,
        "overall_hits": total_hits,
        "overall_shots": total_shots,
        "drill_rate": drill_rate,
        "drill_hits": drill_hits,
        "drill_shots": drill_shots,
        "recent_form": recent_form,
        "by_event": by_event,
        "diagnostics": {
            "delta_p": diag.delta_p,
            "delta_fatigue": diag.delta_fatigue,
            "delta_wind": diag.delta_wind,
            "practice_rate": diag.practice_rate,
            "qualification_rate": diag.qualification_rate,
            "early_rate": diag.early_rate,
            "late_rate": diag.late_rate,
            "calm_rate": diag.calm_rate,
            "windy_rate": diag.windy_rate,
        },
        "readiness": {
            "prs": prs.prs,
            "rfr": prs.rfr,
            "slope_form": prs.slope_form,
            "phi_taper": prs.phi_taper,
            "acwr": prs.acwr,
            "acwr_zone": prs.acwr_zone,
            "short_term_rate": prs.short_term_rate,
            "long_term_rate": prs.long_term_rate,
            "banister_p": prs.banister_p,
            "load_days": len(days),
        },
        "recent_rounds": recent_rounds,
        "competition_timeline": competition_timeline(conn),
    }


def competitions_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    return results_payload(conn)


def stations_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    shots = _rows(fetch_all_shots(conn))
    if not shots:
        return {
            "stations": [],
            "by_volume": [],
            "most_shot": None,
            "least_shot": None,
            "total_shots": 0,
        }

    results = compute_sdi(shots)
    # Hit counts per station from raw shots
    hits_by_st: dict[int, int] = {i: 0 for i in range(1, 9)}
    n_by_st: dict[int, int] = {i: 0 for i in range(1, 9)}
    for s in shots:
        st = int(s["station"])
        n_by_st[st] = n_by_st.get(st, 0) + 1
        if s["is_hit"]:
            hits_by_st[st] = hits_by_st.get(st, 0) + 1

    stations = []
    for s in results:
        n = s.n_single + s.n_double_1 + s.n_double_2
        hits = hits_by_st.get(s.station, 0)
        stations.append(
            {
                "station": s.station,
                "sdi": s.sdi,
                "hit_rate_single": s.hit_rate_single,
                "hit_rate_double_1": s.hit_rate_double_1,
                "hit_rate_double_2": s.hit_rate_double_2,
                "n_single": s.n_single,
                "n_double_1": s.n_double_1,
                "n_double_2": s.n_double_2,
                "n": n,
                "hits": hits,
                "hit_rate": (hits / n) if n else None,
            }
        )

    total = sum(s["n"] for s in stations)
    by_volume = sorted(stations, key=lambda s: (-s["n"], s["station"]))
    with_shots = [s for s in by_volume if s["n"] > 0]
    most = with_shots[0] if with_shots else None
    # Least among stations that have been shot at least once; if some never shot, those are least
    never = [s for s in stations if s["n"] == 0]
    if never:
        least = min(never, key=lambda s: s["station"])
        least = {**least, "never_shot": True}
    elif with_shots:
        least = min(with_shots, key=lambda s: (s["n"], s["station"]))
        least = {**least, "never_shot": False}
    else:
        least = None

    ranked_sdi = sorted(stations, key=lambda s: s["sdi"], reverse=True)
    return {
        "stations": ranked_sdi,
        "by_volume": by_volume,
        "most_shot": most,
        "least_shot": least,
        "total_shots": total,
    }


def doubles_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    shots = _rows(fetch_all_shots(conn))
    pairs = pairs_from_shots(shots)
    if not pairs:
        return {"empty": True}
    m = compute_markov(pairs)
    return {
        "empty": False,
        "total_doubles": m.total_doubles,
        "counts": {"hh": m.n_hh, "hm": m.n_hm, "mh": m.n_mh, "mm": m.n_mm},
        "p_h_given_h": m.p_h_given_h,
        "p_m_given_h": m.p_m_given_h,
        "p_h_given_m": m.p_h_given_m,
        "p_m_given_m": m.p_m_given_m,
        "e_t": m.e_t,
        "d_f": m.d_f,
        "or_double": m.or_double,
    }


def readiness_payload(conn: sqlite3.Connection) -> dict[str, Any]:
    loads = fetch_training_loads(conn)
    rounds = fetch_rounds(conn)
    # PRS form from competition sessions
    comp = [r for r in rounds if r["event_type"] != "drill"]
    rates = round_hit_rates(comp if comp else rounds)
    days, workloads = daily_workload_series(_rows(loads))
    last_acwr = None
    last_p = None
    series: list[dict[str, Any]] = []
    if workloads:
        p_series = banister_performance(workloads, BanisterParams())
        acwrs = acwr_series(workloads)
        last_p = p_series[-1]
        last_acwr = acwrs[-1]
        for d, w, p, a in list(zip(days, workloads, p_series, acwrs))[-21:]:
            series.append(
                {
                    "date": d.isoformat(),
                    "workload": w,
                    "banister_p": p,
                    "acwr": a,
                }
            )
    prs = compute_prs(rates, acwr=last_acwr, banister_p=last_p)
    return {
        "prs": prs.prs,
        "rfr": prs.rfr,
        "slope_form": prs.slope_form,
        "phi_taper": prs.phi_taper,
        "acwr": prs.acwr,
        "acwr_zone": prs.acwr_zone,
        "short_term_rate": prs.short_term_rate,
        "long_term_rate": prs.long_term_rate,
        "banister_p": prs.banister_p,
        "series": series,
        "has_loads": bool(workloads),
    }
