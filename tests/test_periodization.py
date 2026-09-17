"""Tests for Banister, ACWR, and PRS."""

from skeet_tracker.analytics.periodization import (
    BanisterParams,
    acwr_series,
    acwr_zone,
    banister_performance,
    compute_prs,
    ewma_series,
    linear_slope,
    taper_factor,
)


def test_ewma_known_series():
    # w = [10, 20], lam=0.5 → EWMA0=10, EWMA1=20*0.5 + 0.5*10 = 15
    series = ewma_series([10.0, 20.0], 0.5)
    assert series == [10.0, 15.0]


def test_acwr_ratio():
    workloads = [10.0, 10.0, 10.0, 10.0]
    acwrs = acwr_series(workloads, lambda_acute=0.5, lambda_chronic=0.25)
    # Constant load → ACWR should approach 1
    assert acwrs[-1] is not None
    assert abs(acwrs[-1] - 1.0) < 1e-9


def test_banister_zero_without_prior_load():
    import math

    p = banister_performance([5.0, 5.0], BanisterParams(p0=10.0, k1=1.0, k2=2.0))
    # t=0: no prior sum → p0
    assert p[0] == 10.0
    # t=1: load from day 0 with dt=1
    expected = 10.0 + 1.0 * 5.0 * math.exp(-1 / 45) - 2.0 * 5.0 * math.exp(-1 / 15)
    assert abs(p[1] - expected) < 1e-9


def test_prs_clamped_to_0_100():
    # Extreme positive inputs still clamp
    prs = compute_prs([0.99] * 25, acwr=0.95)
    assert 0.0 <= prs.prs <= 100.0
    # Empty rates → low but valid
    prs_empty = compute_prs([], acwr=None)
    assert 0.0 <= prs_empty.prs <= 100.0


def test_taper_and_zone():
    assert abs(taper_factor(0.95) - 1.0) < 1e-9
    assert acwr_zone(1.0) == "sweet_spot"
    assert acwr_zone(1.6) == "danger"


def test_linear_slope():
    assert abs(linear_slope([1.0, 2.0, 3.0]) - 1.0) < 1e-9
    assert linear_slope([5.0]) == 0.0
