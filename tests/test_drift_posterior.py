"""Invariants of the Dirichlet posterior drift math."""

import math

from hypothesis import given
from hypothesis import strategies as st

from helios_mcp.drift import (
    LN2,
    DriftConfig,
    assess,
    assess_dimension,
    js_divergence,
    smooth,
)

DIM = "communication_register"
DECLARED = {"terse": 0.2, "moderate": 0.45, "thorough": 0.2,
            "technical_dense": 0.1, "plain_accessible": 0.05}

probs = st.lists(st.floats(0, 1), min_size=5, max_size=5).filter(
    lambda xs: sum(xs) > 1e-6).map(lambda xs: [x / sum(xs) for x in xs])


@given(probs, probs)
def test_js_is_symmetric_bounded_and_finite(p, q):
    d = js_divergence(p, q)
    assert math.isfinite(d)
    assert 0.0 <= d <= LN2 + 1e-12
    assert math.isclose(d, js_divergence(q, p), abs_tol=1e-12)
    assert js_divergence(p, p) < 1e-12


def test_js_of_disjoint_point_masses_is_ln2():
    assert math.isclose(js_divergence([1, 0], [0, 1]), LN2)


@given(probs)
def test_smooth_is_never_degenerate(p):
    s = smooth(p, 0.005)
    assert math.isclose(sum(s), 1.0)
    assert min(s) >= 0.005 / (1 + 0.005 * len(p)) - 1e-12


def scaled(dist, n):
    return {k: v * n for k, v in dist.items()}


def test_no_evidence_is_neither_drift_nor_auto_accept():
    r = assess_dimension(DIM, DECLARED, {})
    assert not r.drifted and not r.auto_accept
    assert r.divergence < 1e-12


def test_stationary_evidence_does_not_drift_and_gets_tighter():
    few = assess_dimension(DIM, DECLARED, scaled(DECLARED, 10))
    many = assess_dimension(DIM, DECLARED, scaled(DECLARED, 500))
    assert not few.drifted and not many.drifted
    assert many.credibility <= few.credibility


def test_sustained_shift_drifts_and_target_is_posterior_mean():
    observed = {"terse": 0.7, "moderate": 0.1, "thorough": 0.1,
                "technical_dense": 0.05, "plain_accessible": 0.05}
    cfg = DriftConfig()
    r = assess_dimension(DIM, DECLARED, scaled(observed, 100), cfg)
    assert r.drifted
    w = 100 / (100 + cfg.prior_strength)
    for state, p in r.posterior_mean.items():
        expected = (1 - w) * r.declared[state] + w * observed[state]
        assert math.isclose(p, expected, rel_tol=1e-9)


def test_small_but_well_supported_move_auto_accepts():
    nudged = {"terse": 0.3, "moderate": 0.35, "thorough": 0.2,
              "technical_dense": 0.1, "plain_accessible": 0.05}
    r = assess_dimension(DIM, DECLARED, scaled(nudged, 2000))
    assert r.auto_accept and not r.drifted


def test_assessment_is_deterministic_and_covers_declared_dims():
    declared = {DIM: DECLARED}
    counts = {DIM: scaled(DECLARED, 30)}
    assert assess(declared, counts) == assess(declared, counts)
    assert set(assess(declared, counts).dimensions) == {DIM}


def _simulate(true, seed, turns, every=5):
    """First turn at which the calibrated defaults flag drift, or None."""
    import random

    rng = random.Random(seed)
    counts: dict[str, float] = {}
    for t in range(1, turns + 1):
        state = rng.choices(list(true), weights=list(true.values()))[0]
        counts[state] = counts.get(state, 0) + 1
        if t % every == 0 and assess_dimension(DIM, DECLARED, counts).drifted:
            return t
    return None


def test_calibrated_defaults_hold_on_stationary_behavior():
    assert all(_simulate(DECLARED, seed, 200) is None for seed in range(5))


def test_calibrated_defaults_detect_a_03_mass_shift_early():
    shifted = dict(DECLARED, moderate=0.15, terse=0.5)
    detected = [_simulate(shifted, seed, 200) for seed in range(5)]
    assert all(t is not None and t <= 80 for t in detected)
