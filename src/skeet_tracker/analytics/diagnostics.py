"""Diagnostic performance deltas: pressure, fatigue, wind."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DiagnosticDeltas:
    delta_p: float | None  # practice - qualification
    delta_fatigue: float | None  # early rounds (1-2) - late (4-5)
    delta_wind: float | None  # calm (<=5) - high wind (>12)
    practice_rate: float | None
    qualification_rate: float | None
    early_rate: float | None
    late_rate: float | None
    calm_rate: float | None
    windy_rate: float | None


def _hit_rate(shots: Sequence[Mapping[str, Any]]) -> float | None:
    if not shots:
        return None
    return sum(1 for s in shots if s["is_hit"]) / len(shots)


def compute_diagnostics(shots: Sequence[Mapping[str, Any]]) -> DiagnosticDeltas:
    """
    Delta_p = X_practice - X_qualification
    Delta_Fatigue = hit_rate(rounds 1,2) - hit_rate(rounds 4,5)
    Delta_Wind = X_calm(<=5 mph) - X_high(>12 mph)
    """
    practice = [s for s in shots if s.get("event_type") == "practice"]
    qualification = [s for s in shots if s.get("event_type") == "qualification"]

    early = [
        s
        for s in shots
        if s.get("round_number") is not None and int(s["round_number"]) in (1, 2)
    ]
    late = [
        s
        for s in shots
        if s.get("round_number") is not None and int(s["round_number"]) in (4, 5)
    ]

    calm = [
        s
        for s in shots
        if s.get("wind_speed_mph") is not None and int(s["wind_speed_mph"]) <= 5
    ]
    windy = [
        s
        for s in shots
        if s.get("wind_speed_mph") is not None and int(s["wind_speed_mph"]) > 12
    ]

    p_rate = _hit_rate(practice)
    q_rate = _hit_rate(qualification)
    early_rate = _hit_rate(early)
    late_rate = _hit_rate(late)
    calm_rate = _hit_rate(calm)
    windy_rate = _hit_rate(windy)

    def _diff(a: float | None, b: float | None) -> float | None:
        if a is None or b is None:
            return None
        return a - b

    return DiagnosticDeltas(
        delta_p=_diff(p_rate, q_rate),
        delta_fatigue=_diff(early_rate, late_rate),
        delta_wind=_diff(calm_rate, windy_rate),
        practice_rate=p_rate,
        qualification_rate=q_rate,
        early_rate=early_rate,
        late_rate=late_rate,
        calm_rate=calm_rate,
        windy_rate=windy_rate,
    )
