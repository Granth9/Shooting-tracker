"""Tests for ballistic kinematics."""

import math

from skeet_tracker.ballistics import (
    BallisticParams,
    angular_swing_speed_deg,
    clay_distance,
    clay_velocity,
    lead_distance,
    shot_time_of_flight,
)


def test_clay_velocity_at_t0():
    p = BallisticParams(v0=25.0, k_drag=0.05)
    assert clay_velocity(0.0, p) == 25.0


def test_clay_velocity_decay():
    p = BallisticParams(v0=25.0, k_drag=0.05)
    v = clay_velocity(1.0, p)
    assert abs(v - 25.0 * math.exp(-0.05)) < 1e-9


def test_clay_distance_formula():
    p = BallisticParams(v0=25.0, k_drag=0.05)
    t = 2.0
    expected = (25.0 / 0.05) * (1 - math.exp(-0.05 * t))
    assert abs(clay_distance(t, p) - expected) < 1e-9


def test_time_of_flight():
    p = BallisticParams(v_shot_avg=350.0)
    assert abs(shot_time_of_flight(35.0, p) - 0.1) < 1e-12


def test_lead_distance_perpendicular():
    p = BallisticParams(v0=25.0, k_drag=0.05, v_shot_avg=350.0)
    # At t=0, theta=90°, R=35 → L = 25 * 1 * (35/350) = 2.5
    L = lead_distance(0.0, 35.0, math.pi / 2, p)
    assert abs(L - 2.5) < 1e-9


def test_angular_swing_speed():
    p = BallisticParams(v0=25.0, k_drag=0.05)
    # t=0, theta=90°, R=25 → omega = (25/25)*(180/pi) = 180/pi
    omega = angular_swing_speed_deg(0.0, 25.0, math.pi / 2, p)
    assert abs(omega - (180.0 / math.pi)) < 1e-9
