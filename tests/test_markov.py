"""Tests for Markov doubles analytics."""

from skeet_tracker.analytics.markov import DoublePair, compute_markov, pairs_from_shots


def test_markov_known_contingency():
    # 8 HH, 2 HM, 1 MH, 4 MM
    pairs = (
        [DoublePair(True, True)] * 8
        + [DoublePair(True, False)] * 2
        + [DoublePair(False, True)] * 1
        + [DoublePair(False, False)] * 4
    )
    m = compute_markov(pairs)
    assert m.total_doubles == 15
    assert m.n_hh == 8 and m.n_hm == 2 and m.n_mh == 1 and m.n_mm == 4
    assert abs(m.p_h_given_h - 0.8) < 1e-9
    assert abs(m.p_m_given_h - 0.2) < 1e-9
    assert abs(m.p_h_given_m - 0.2) < 1e-9
    assert abs(m.p_m_given_m - 0.8) < 1e-9
    assert abs(m.e_t - 9 / 15) < 1e-9
    # D_f = P(M|M) - P(M|H) = 0.8 - 0.2 = 0.6
    assert abs(m.d_f - 0.6) < 1e-9
    # OR = (0.8/0.2) / (0.2/0.8) = 4 / 0.25 = 16
    assert m.or_double is not None
    assert abs(m.or_double - 16.0) < 1e-9


def test_pairs_from_shots_groups_doubles():
    shots = [
        {
            "round_id": "r1",
            "station": 1,
            "sequence_order": 2,
            "pair_position": 1,
            "is_double": 1,
            "is_hit": 1,
        },
        {
            "round_id": "r1",
            "station": 1,
            "sequence_order": 3,
            "pair_position": 2,
            "is_double": 1,
            "is_hit": 0,
        },
        {
            "round_id": "r1",
            "station": 1,
            "sequence_order": 1,
            "pair_position": 0,
            "is_double": 0,
            "is_hit": 1,
        },
    ]
    pairs = pairs_from_shots(shots)
    assert len(pairs) == 1
    assert pairs[0].t1_hit is True
    assert pairs[0].t2_hit is False
