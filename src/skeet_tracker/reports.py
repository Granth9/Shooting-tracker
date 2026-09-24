"""Text report assembly for CLI output."""

from __future__ import annotations

import sqlite3
from typing import Optional

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
from skeet_tracker.ingest import fetch_all_shots, fetch_rounds, fetch_training_loads


def _pct(rate: float | None) -> str:
    if rate is None:
        return "n/a"
    return f"{rate * 100:.1f}%"


def _fmt(x: float | None, digits: int = 3) -> str:
    if x is None:
        return "n/a"
    return f"{x:.{digits}f}"


def _rows_as_dicts(rows: list[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def report_summary(conn: sqlite3.Connection) -> str:
    rounds = fetch_rounds(conn)
    shots = _rows_as_dicts(fetch_all_shots(conn))
    lines = ["=== Summary ===", ""]

    if not rounds:
        lines.append("No rounds recorded.")
        return "\n".join(lines)

    total_hits = sum(int(r["hits"]) for r in rounds)
    total_shots = sum(int(r["shots"]) for r in rounds)
    overall = total_hits / total_shots if total_shots else 0.0
    lines.append(f"Rounds: {len(rounds)}")
    lines.append(f"Overall: {total_hits}/{total_shots} ({_pct(overall)})")
    lines.append("")

    by_type: dict[str, list[sqlite3.Row]] = {}
    for r in rounds:
        by_type.setdefault(r["event_type"], []).append(r)
    lines.append("By event type:")
    for et in ("practice", "qualification", "final", "drill"):
        group = by_type.get(et, [])
        if not group:
            continue
        h = sum(int(r["hits"]) for r in group)
        s = sum(int(r["shots"]) for r in group)
        lines.append(f"  {et}: {h}/{s} ({_pct(h / s if s else None)})  n={len(group)}")

    rates = round_hit_rates(rounds)
    if rates:
        recent = rates[-5:]
        lines.append("")
        lines.append(
            f"Recent form (last {len(recent)} rounds): "
            f"{_pct(sum(recent) / len(recent))}"
        )

    diag = compute_diagnostics(shots)
    lines.append("")
    lines.append("Diagnostics:")
    lines.append(
        f"  Δ_p (practice − qualification): {_fmt(diag.delta_p)} "
        f"(practice {_pct(diag.practice_rate)}, qual {_pct(diag.qualification_rate)})"
    )
    lines.append(
        f"  Δ_Fatigue (rounds 1–2 − 4–5): {_fmt(diag.delta_fatigue)} "
        f"(early {_pct(diag.early_rate)}, late {_pct(diag.late_rate)})"
    )
    lines.append(
        f"  Δ_Wind (calm ≤5 − windy >12): {_fmt(diag.delta_wind)} "
        f"(calm {_pct(diag.calm_rate)}, windy {_pct(diag.windy_rate)})"
    )
    return "\n".join(lines)


def report_station(conn: sqlite3.Connection) -> str:
    shots = _rows_as_dicts(fetch_all_shots(conn))
    lines = ["=== Station Difficulty (SDI) ===", ""]
    if not shots:
        lines.append("No shots recorded.")
        return "\n".join(lines)

    results = compute_sdi(shots)
    ranked = sorted(results, key=lambda s: s.sdi, reverse=True)
    lines.append(
        f"{'St':>3}  {'SDI':>6}  {'Single':>8}  {'Dbl1':>8}  {'Dbl2':>8}  {'n':>5}"
    )
    for s in ranked:
        n = s.n_single + s.n_double_1 + s.n_double_2
        lines.append(
            f"{s.station:>3}  {s.sdi:6.3f}  {_pct(s.hit_rate_single):>8}  "
            f"{_pct(s.hit_rate_double_1):>8}  {_pct(s.hit_rate_double_2):>8}  {n:>5}"
        )
    lines.append("")
    lines.append("(Higher SDI = more difficult / lower weighted hit rate)")
    return "\n".join(lines)


def report_doubles(conn: sqlite3.Connection) -> str:
    shots = _rows_as_dicts(fetch_all_shots(conn))
    lines = ["=== Doubles Markov Analysis ===", ""]
    pairs = pairs_from_shots(shots)
    if not pairs:
        lines.append("No doubles pairs recorded.")
        return "\n".join(lines)

    m = compute_markov(pairs)
    lines.append(f"Doubles attempted: {m.total_doubles}")
    lines.append(f"Counts: HH={m.n_hh} HM={m.n_hm} MH={m.n_mh} MM={m.n_mm}")
    lines.append("")
    lines.append("Transition matrix P(T2 | T1):")
    lines.append(
        f"  P(H|H)={m.p_h_given_h:.3f}  P(M|H)={m.p_m_given_h:.3f}"
    )
    lines.append(
        f"  P(H|M)={m.p_h_given_m:.3f}  P(M|M)={m.p_m_given_m:.3f}"
    )
    lines.append("")
    lines.append(f"E_t (2nd-target efficiency): {m.e_t:.3f}")
    lines.append(f"D_f (1st-shot dependency):   {m.d_f:.3f}")
    if m.d_f > 0:
        lines.append("  → Negative spillover: miss on T1 raises T2 miss likelihood")
    elif abs(m.d_f) < 0.05:
        lines.append("  → Near-independent shot execution")
    or_str = _fmt(m.or_double) if m.or_double is not None else "undefined"
    lines.append(f"OR_double: {or_str}")
    return "\n".join(lines)


def report_readiness(
    conn: sqlite3.Connection,
    banister: Optional[BanisterParams] = None,
) -> str:
    lines = ["=== Peak Readiness ===", ""]
    loads = fetch_training_loads(conn)
    rounds = fetch_rounds(conn)
    rates = round_hit_rates(rounds)

    days, workloads = daily_workload_series(_rows_as_dicts(loads))
    if not workloads:
        lines.append("No training loads recorded. Use `skeet add-load` first.")
        lines.append("")
        # Still compute PRS with ACWR undefined if we have rounds
        prs = compute_prs(rates, acwr=None, banister_p=None)
        lines.append(f"PRS (without ACWR): {prs.prs:.1f}")
        lines.append(f"  RFR: {_fmt(prs.rfr)}")
        lines.append(f"  Slope_Form (last 10): {_fmt(prs.slope_form, 4)}")
        lines.append(f"  Short-term rate: {_pct(prs.short_term_rate)}")
        lines.append(f"  Long-term rate:  {_pct(prs.long_term_rate)}")
        return "\n".join(lines)

    params = banister or BanisterParams()
    p_series = banister_performance(workloads, params)
    acwrs = acwr_series(workloads)
    last_p = p_series[-1] if p_series else None
    last_acwr = acwrs[-1] if acwrs else None
    prs = compute_prs(rates, acwr=last_acwr, banister_p=last_p)

    lines.append(f"Load days: {days[0]} → {days[-1]} ({len(days)} days)")
    lines.append(f"Latest Banister p(t): {_fmt(last_p)}")
    lines.append(f"Latest ACWR: {_fmt(last_acwr)}  zone={prs.acwr_zone}")
    lines.append(f"Φ_Taper: {_fmt(prs.phi_taper)}")
    lines.append("")
    lines.append(f"PRS: {prs.prs:.1f} / 100")
    lines.append(f"  RFR: {_fmt(prs.rfr)}")
    lines.append(f"  Slope_Form (last 10): {_fmt(prs.slope_form, 4)}")
    lines.append(f"  Short-term (5): {_pct(prs.short_term_rate)}")
    lines.append(f"  Long-term (25): {_pct(prs.long_term_rate)}")
    return "\n".join(lines)
