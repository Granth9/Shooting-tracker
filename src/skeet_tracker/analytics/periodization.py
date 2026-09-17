"""Banister fitness-fatigue, ACWR, and Peak Readiness Score."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np


@dataclass(frozen=True, slots=True)
class BanisterParams:
    p0: float = 0.0
    k1: float = 1.0
    k2: float = 2.0
    tau1: float = 45.0  # fitness decay (days)
    tau2: float = 15.0  # fatigue decay (days)


LAMBDA_ACUTE = 0.25  # N=7 => 2/(7+1)=0.25
LAMBDA_CHRONIC = 0.069  # N=28 => 2/(28+1)≈0.069


def banister_performance(
    workloads: Sequence[float],
    params: BanisterParams | None = None,
) -> list[float]:
    """
    p(t) = p0 + k1 * sum_s w(s) exp(-(t-s)/tau1) - k2 * sum_s w(s) exp(-(t-s)/tau2)

    workloads[i] is load on day index i (0-based). Returns p(t) for each day t.
    """
    p = params or BanisterParams()
    n = len(workloads)
    out: list[float] = []
    for t in range(n):
        fitness = 0.0
        fatigue = 0.0
        for s in range(t):
            w = float(workloads[s])
            dt = t - s
            fitness += w * np.exp(-dt / p.tau1)
            fatigue += w * np.exp(-dt / p.tau2)
        out.append(p.p0 + p.k1 * fitness - p.k2 * fatigue)
    return out


def ewma_series(workloads: Sequence[float], lam: float) -> list[float]:
    """EWMA(t) = w(t)*lam + (1-lam)*EWMA(t-1); EWMA(0)=w(0)."""
    if not workloads:
        return []
    if not 0 < lam <= 1:
        raise ValueError("lambda must be in (0, 1]")
    series = [float(workloads[0])]
    for w in workloads[1:]:
        series.append(float(w) * lam + (1.0 - lam) * series[-1])
    return series


def acwr_series(
    workloads: Sequence[float],
    lambda_acute: float = LAMBDA_ACUTE,
    lambda_chronic: float = LAMBDA_CHRONIC,
) -> list[float | None]:
    """ACWR(t) = AW(t)/CW(t); None when chronic is zero."""
    aw = ewma_series(workloads, lambda_acute)
    cw = ewma_series(workloads, lambda_chronic)
    result: list[float | None] = []
    for a, c in zip(aw, cw):
        if c == 0:
            result.append(None)
        else:
            result.append(a / c)
    return result


def acwr_zone(acwr: float | None) -> str:
    if acwr is None:
        return "undefined"
    if 0.8 <= acwr <= 1.3:
        return "sweet_spot"
    if acwr > 1.5:
        return "danger"
    return "moderate"


def taper_factor(acwr: float | None) -> float:
    """Phi_Taper = 1 - |(ACWR - 0.95) / 0.35|; clamped conceptually for PRS."""
    if acwr is None:
        return 0.0
    return 1.0 - abs((acwr - 0.95) / 0.35)


def linear_slope(values: Sequence[float]) -> float:
    """OLS slope of values vs index 0..n-1. Returns 0 if fewer than 2 points."""
    n = len(values)
    if n < 2:
        return 0.0
    x = np.arange(n, dtype=float)
    y = np.asarray(values, dtype=float)
    # slope = cov(x,y)/var(x)
    x_mean = x.mean()
    y_mean = y.mean()
    var_x = np.sum((x - x_mean) ** 2)
    if var_x == 0:
        return 0.0
    return float(np.sum((x - x_mean) * (y - y_mean)) / var_x)


@dataclass(frozen=True, slots=True)
class PeakReadiness:
    prs: float
    rfr: float | None
    slope_form: float
    phi_taper: float
    acwr: float | None
    acwr_zone: str
    short_term_rate: float | None
    long_term_rate: float | None
    banister_p: float | None


def round_hit_rates(
    rounds: Sequence[Mapping[str, Any]],
) -> list[float]:
    """Extract hit rates from round rows with hits/shots columns."""
    rates: list[float] = []
    for r in rounds:
        shots = int(r["shots"])
        if shots <= 0:
            continue
        rates.append(int(r["hits"]) / shots)
    return rates


def compute_prs(
    round_rates: Sequence[float],
    acwr: float | None,
    banister_p: float | None = None,
) -> PeakReadiness:
    """
    PRS = min(100, max(0, (RFR*40) + (Slope_Form*20 + 20) + (Phi_Taper*20)))

    Slope_Form is the linear regression slope over the last 10 rounds (hit rates).
    RFR = short(5) / long(25).
    """
    rates = list(round_rates)
    short = rates[-5:] if rates else []
    long = rates[-25:] if rates else []
    short_rate = sum(short) / len(short) if short else None
    long_rate = sum(long) / len(long) if long else None

    rfr: float | None
    if short_rate is None or long_rate is None or long_rate == 0:
        rfr = None
        rfr_term = 0.0
    else:
        rfr = short_rate / long_rate
        rfr_term = rfr * 40.0

    window = rates[-10:]
    slope = linear_slope(window)
    phi = taper_factor(acwr)
    # Clamp phi contribution input; negative phi still allowed in formula then clamped
    raw = rfr_term + (slope * 20.0 + 20.0) + (phi * 20.0)
    prs = min(100.0, max(0.0, raw))

    return PeakReadiness(
        prs=prs,
        rfr=rfr,
        slope_form=slope,
        phi_taper=phi,
        acwr=acwr,
        acwr_zone=acwr_zone(acwr),
        short_term_rate=short_rate,
        long_term_rate=long_rate,
        banister_p=banister_p,
    )


def daily_workload_series(
    loads: Sequence[Mapping[str, Any]],
    start: date | None = None,
    end: date | None = None,
) -> tuple[list[date], list[float]]:
    """
    Build a contiguous daily workload series (0 on missing days) from load rows.
    Each row needs load_date (YYYY-MM-DD) and workload.
    """
    by_day: dict[date, float] = {}
    for row in loads:
        d = row["load_date"]
        if isinstance(d, str):
            day = date.fromisoformat(d[:10])
        elif isinstance(d, datetime):
            day = d.date()
        else:
            day = d  # type: ignore[assignment]
        by_day[day] = float(row["workload"])

    if not by_day:
        return [], []

    d0 = start or min(by_day)
    d1 = end or max(by_day)
    days: list[date] = []
    values: list[float] = []
    cur = d0
    while cur <= d1:
        days.append(cur)
        values.append(by_day.get(cur, 0.0))
        cur += timedelta(days=1)
    return days, values
