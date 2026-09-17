"""Ballistic lead and target kinematics for ISSF Skeet."""

from __future__ import annotations

import math
from dataclasses import dataclass

# Spec defaults: ~25 m/s clay, ~400 m/s muzzle; use average pellet speed for ToF
DEFAULT_V0 = 25.0  # m/s clay launch
DEFAULT_K_DRAG = 0.05  # 1/s aerodynamic drag coefficient
DEFAULT_V_SHOT_AVG = 350.0  # m/s average pellet speed over typical engagement range


@dataclass(frozen=True, slots=True)
class BallisticParams:
    v0: float = DEFAULT_V0
    k_drag: float = DEFAULT_K_DRAG
    v_shot_avg: float = DEFAULT_V_SHOT_AVG


def clay_velocity(t: float, params: BallisticParams | None = None) -> float:
    """Target velocity under exponential drag: v_clay(t) = v0 * exp(-k_drag * t)."""
    p = params or BallisticParams()
    if t < 0:
        raise ValueError("t must be >= 0")
    if p.k_drag <= 0:
        raise ValueError("k_drag must be > 0")
    return p.v0 * math.exp(-p.k_drag * t)


def clay_distance(t: float, params: BallisticParams | None = None) -> float:
    """Distance along flight vector: d = (v0/k) * (1 - exp(-k*t))."""
    p = params or BallisticParams()
    if t < 0:
        raise ValueError("t must be >= 0")
    if p.k_drag <= 0:
        raise ValueError("k_drag must be > 0")
    return (p.v0 / p.k_drag) * (1.0 - math.exp(-p.k_drag * t))


def shot_time_of_flight(r: float, params: BallisticParams | None = None) -> float:
    """Pellet time-of-flight over slant range R: t_flight = R / v_shot_avg."""
    p = params or BallisticParams()
    if r < 0:
        raise ValueError("R must be >= 0")
    if p.v_shot_avg <= 0:
        raise ValueError("v_shot_avg must be > 0")
    return r / p.v_shot_avg


def lead_distance(
    t: float,
    r: float,
    theta_crossing_rad: float,
    params: BallisticParams | None = None,
) -> float:
    """
    Forward allowance (lead) in meters orthogonal to line of sight:
    L = (v_clay(t) * sin(theta_crossing)) * (R / v_shot_avg)
    """
    v_perp = clay_velocity(t, params) * math.sin(theta_crossing_rad)
    return v_perp * shot_time_of_flight(r, params)


def angular_swing_speed_deg(
    t: float,
    r: float,
    theta_crossing_rad: float,
    params: BallisticParams | None = None,
) -> float:
    """
    Required angular gun rate in degrees/second:
    omega = (v_clay_perp / R) * (180/pi)
    """
    if r <= 0:
        raise ValueError("R must be > 0 for angular swing speed")
    v_perp = clay_velocity(t, params) * math.sin(theta_crossing_rad)
    return (v_perp / r) * (180.0 / math.pi)


def summarize_engagement(
    t: float,
    r: float,
    theta_crossing_deg: float,
    params: BallisticParams | None = None,
) -> dict[str, float]:
    """Convenience summary of kinematics at engagement time t and range R."""
    theta = math.radians(theta_crossing_deg)
    p = params or BallisticParams()
    return {
        "v_clay_mps": clay_velocity(t, p),
        "d_clay_m": clay_distance(t, p),
        "t_flight_s": shot_time_of_flight(r, p),
        "lead_m": lead_distance(t, r, theta, p),
        "omega_gun_deg_s": angular_swing_speed_deg(t, r, theta, p),
    }
