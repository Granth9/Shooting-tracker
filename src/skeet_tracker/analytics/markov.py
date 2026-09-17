"""Markov chain dynamics for doubles (T1 -> T2 transitions)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DoublePair:
    """Outcome of a double: first target then second target."""

    t1_hit: bool
    t2_hit: bool


@dataclass(frozen=True, slots=True)
class MarkovDoublesResult:
    """Empirical transition matrix and derived metrics."""

    n_hh: int
    n_hm: int
    n_mh: int
    n_mm: int
    p_h_given_h: float
    p_m_given_h: float
    p_h_given_m: float
    p_m_given_m: float
    e_t: float  # second-target transition efficiency
    d_f: float  # first-shot dependency index
    or_double: float | None  # conditional odds ratio (None if undefined)

    @property
    def transition_matrix(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return (
            (self.p_h_given_h, self.p_m_given_h),
            (self.p_h_given_m, self.p_m_given_m),
        )

    @property
    def total_doubles(self) -> int:
        return self.n_hh + self.n_hm + self.n_mh + self.n_mm


def pairs_from_shots(shots: Sequence[Mapping[str, Any]]) -> list[DoublePair]:
    """
    Extract double pairs from shot rows.

    Groups by (round_id, station, consecutive pair_position 1 then 2).
    Expects keys: round_id, station, pair_position, is_hit, sequence_order.
    """
    # Collect first and second targets keyed for pairing
    by_round: dict[str, list[Mapping[str, Any]]] = {}
    for s in shots:
        if not s.get("is_double"):
            continue
        rid = str(s["round_id"])
        by_round.setdefault(rid, []).append(s)

    pairs: list[DoublePair] = []
    for rid, round_shots in by_round.items():
        ordered = sorted(round_shots, key=lambda x: int(x["sequence_order"]))
        i = 0
        while i < len(ordered) - 1:
            a, b = ordered[i], ordered[i + 1]
            if (
                int(a["pair_position"]) == 1
                and int(b["pair_position"]) == 2
                and int(a["station"]) == int(b["station"])
            ):
                pairs.append(
                    DoublePair(
                        t1_hit=bool(a["is_hit"]),
                        t2_hit=bool(b["is_hit"]),
                    )
                )
                i += 2
            else:
                i += 1
    return pairs


def compute_markov(pairs: Iterable[DoublePair]) -> MarkovDoublesResult:
    """Compute P_double, E_t, D_f, and OR_double from observed pairs."""
    n_hh = n_hm = n_mh = n_mm = 0
    for p in pairs:
        if p.t1_hit and p.t2_hit:
            n_hh += 1
        elif p.t1_hit and not p.t2_hit:
            n_hm += 1
        elif not p.t1_hit and p.t2_hit:
            n_mh += 1
        else:
            n_mm += 1

    total = n_hh + n_hm + n_mh + n_mm
    after_h = n_hh + n_hm
    after_m = n_mh + n_mm

    def _safe_div(num: float, den: float) -> float:
        return num / den if den > 0 else 0.0

    p_h_given_h = _safe_div(n_hh, after_h)
    p_m_given_h = _safe_div(n_hm, after_h)
    p_h_given_m = _safe_div(n_mh, after_m)
    p_m_given_m = _safe_div(n_mm, after_m)

    e_t = _safe_div(n_hh + n_mh, total)
    d_f = p_m_given_m - p_m_given_h

    # OR = (P(H|H)/P(M|H)) / (P(H|M)/P(M|M))
    or_double: float | None
    try:
        odds_h = p_h_given_h / p_m_given_h
        odds_m = p_h_given_m / p_m_given_m
        or_double = odds_h / odds_m
    except ZeroDivisionError:
        or_double = None

    return MarkovDoublesResult(
        n_hh=n_hh,
        n_hm=n_hm,
        n_mh=n_mh,
        n_mm=n_mm,
        p_h_given_h=p_h_given_h,
        p_m_given_h=p_m_given_h,
        p_h_given_m=p_h_given_m,
        p_m_given_m=p_m_given_m,
        e_t=e_t,
        d_f=d_f,
        or_double=or_double,
    )
