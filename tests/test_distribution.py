"""Tests for BehavioralDistribution — the core scientific data type of Helios v2."""

import math
import pytest
from helios_mcp.distribution import (
    BehavioralDistribution,
    total_kl_divergence,
    _normalize,
)
from helios_mcp.taxonomy import list_dimensions, list_states


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_epistemic(confident: float, hedging: float,
                   admits_ignorance: float, speculating: float) -> BehavioralDistribution:
    return BehavioralDistribution("epistemic_style", {
        "confident": confident,
        "hedging": hedging,
        "admits_ignorance": admits_ignorance,
        "speculating": speculating,
    })


def confident_dist() -> BehavioralDistribution:
    return make_epistemic(0.80, 0.10, 0.05, 0.05)


def hedging_dist() -> BehavioralDistribution:
    return make_epistemic(0.10, 0.70, 0.15, 0.05)


def uniform_epistemic() -> BehavioralDistribution:
    return BehavioralDistribution.uniform("epistemic_style")


# ---------------------------------------------------------------------------
# Construction and validation
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_valid_construction(self) -> None:
        d = confident_dist()
        assert d.dimension == "epistemic_style"
        assert abs(sum(d.probs) - 1.0) < 1e-9

    def test_invalid_dimension(self) -> None:
        with pytest.raises(ValueError, match="Unknown behavioral dimension"):
            BehavioralDistribution("nonexistent", {"a": 1.0})

    def test_missing_state(self) -> None:
        with pytest.raises(ValueError, match="missing states"):
            BehavioralDistribution("epistemic_style", {
                "confident": 0.5,
                "hedging": 0.5,
                # missing admits_ignorance and speculating
            })

    def test_extra_state(self) -> None:
        with pytest.raises(ValueError, match="unknown states"):
            BehavioralDistribution("epistemic_style", {
                "confident": 0.4,
                "hedging": 0.3,
                "admits_ignorance": 0.2,
                "speculating": 0.05,
                "made_up_state": 0.05,
            })

    def test_negative_probability(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            make_epistemic(-0.1, 0.7, 0.3, 0.1)

    def test_does_not_sum_to_one(self) -> None:
        with pytest.raises(ValueError, match="sum to"):
            make_epistemic(0.5, 0.5, 0.5, 0.5)  # sums to 2.0

    def test_nearly_sums_to_one_accepted(self) -> None:
        # Floating point arithmetic can cause tiny deviations
        d = make_epistemic(0.8, 0.1, 0.05, 0.05)
        assert d is not None

    def test_states_in_canonical_taxonomy_order(self) -> None:
        d = confident_dist()
        expected_states = list_states("epistemic_style")
        assert d.states == expected_states


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------

class TestConvenienceConstructors:
    def test_uniform_sums_to_one(self) -> None:
        for dim in list_dimensions():
            d = BehavioralDistribution.uniform(dim)
            assert abs(sum(d.probs) - 1.0) < 1e-9

    def test_uniform_equal_probs(self) -> None:
        d = BehavioralDistribution.uniform("epistemic_style")
        expected = 1.0 / 4  # 4 states in epistemic_style
        for p in d.probs:
            assert abs(p - expected) < 1e-9

    def test_point_mass_full_probability(self) -> None:
        d = BehavioralDistribution.point_mass("epistemic_style", "confident")
        assert d["confident"] == pytest.approx(1.0)
        assert d["hedging"] == pytest.approx(0.0)
        assert d["admits_ignorance"] == pytest.approx(0.0)
        assert d["speculating"] == pytest.approx(0.0)

    def test_point_mass_invalid_state(self) -> None:
        with pytest.raises(ValueError):
            BehavioralDistribution.point_mass("epistemic_style", "nonexistent")


# ---------------------------------------------------------------------------
# KL-divergence
# ---------------------------------------------------------------------------

class TestKLDivergence:
    def test_kl_identical_distributions_is_zero(self) -> None:
        d = confident_dist()
        assert d.kl_divergence(d) == pytest.approx(0.0, abs=1e-9)

    def test_kl_is_nonnegative(self) -> None:
        p = confident_dist()
        q = hedging_dist()
        assert p.kl_divergence(q) >= 0.0
        assert q.kl_divergence(p) >= 0.0

    def test_kl_is_asymmetric(self) -> None:
        p = confident_dist()
        q = hedging_dist()
        kl_pq = p.kl_divergence(q)
        kl_qp = q.kl_divergence(p)
        # KL is not symmetric in general
        assert abs(kl_pq - kl_qp) > 1e-6

    def test_kl_identical_uniform_is_zero(self) -> None:
        u = uniform_epistemic()
        assert u.kl_divergence(u) == pytest.approx(0.0, abs=1e-9)

    def test_kl_different_dimensions_raises(self) -> None:
        d1 = BehavioralDistribution.uniform("epistemic_style")
        d2 = BehavioralDistribution.uniform("risk_caution")
        with pytest.raises(ValueError, match="different dimensions"):
            d1.kl_divergence(d2)

    def test_kl_point_mass_vs_uniform(self) -> None:
        point = BehavioralDistribution.point_mass("epistemic_style", "confident")
        uniform = uniform_epistemic()
        # D_KL(point || uniform): point has all mass on one state
        # = 1.0 * log(1.0 / 0.25) = log(4)
        expected = math.log(4)
        assert point.kl_divergence(uniform) == pytest.approx(expected, rel=1e-6)

    def test_kl_handles_zero_in_p(self) -> None:
        # If P(x) = 0, that term should contribute 0 to KL
        # (limit of x*log(x) as x→0 is 0)
        point = BehavioralDistribution.point_mass("epistemic_style", "confident")
        other = confident_dist()
        # Should not raise even though point has 0 probabilities
        result = point.kl_divergence(other)
        assert result >= 0.0

    def test_kl_more_similar_is_lower(self) -> None:
        # A distribution close to P should have lower KL than one far from P
        p = confident_dist()
        close = make_epistemic(0.75, 0.12, 0.07, 0.06)
        far = hedging_dist()
        assert p.kl_divergence(close) < p.kl_divergence(far)


# ---------------------------------------------------------------------------
# KL-blend (inheritance)
# ---------------------------------------------------------------------------

class TestKLBlend:
    def test_blend_weight_one_returns_self(self) -> None:
        base = confident_dist()
        persona = hedging_dist()
        blended = base.kl_blend(persona, weight=1.0)
        assert blended == base

    def test_blend_weight_zero_returns_other(self) -> None:
        base = confident_dist()
        persona = hedging_dist()
        blended = base.kl_blend(persona, weight=0.0)
        assert blended == persona

    def test_blend_sums_to_one(self) -> None:
        base = confident_dist()
        persona = hedging_dist()
        blended = base.kl_blend(persona, weight=0.3)
        assert abs(sum(blended.probs) - 1.0) < 1e-9

    def test_blend_intermediate_weight(self) -> None:
        base = confident_dist()
        persona = hedging_dist()
        blended = base.kl_blend(persona, weight=0.5)
        # At weight=0.5, blended should be between base and persona
        # confident prob should be between the two
        assert persona["confident"] <= blended["confident"] <= base["confident"]

    def test_blend_correct_formula(self) -> None:
        # M(x) = w * base(x) + (1-w) * persona(x)
        base = confident_dist()
        persona = hedging_dist()
        w = 0.3
        blended = base.kl_blend(persona, weight=w)
        for state in base.states:
            expected = w * base[state] + (1 - w) * persona[state]
            assert blended[state] == pytest.approx(expected, abs=1e-9)

    def test_blend_invalid_weight(self) -> None:
        base = confident_dist()
        persona = hedging_dist()
        with pytest.raises(ValueError, match="Blend weight"):
            base.kl_blend(persona, weight=1.5)

    def test_blend_different_dimensions_raises(self) -> None:
        d1 = BehavioralDistribution.uniform("epistemic_style")
        d2 = BehavioralDistribution.uniform("risk_caution")
        with pytest.raises(ValueError, match="different dimensions"):
            d1.kl_blend(d2, weight=0.5)

    def test_blend_dimension_preserved(self) -> None:
        base = confident_dist()
        persona = hedging_dist()
        blended = base.kl_blend(persona, weight=0.4)
        assert blended.dimension == "epistemic_style"


# ---------------------------------------------------------------------------
# Entropy
# ---------------------------------------------------------------------------

class TestEntropy:
    def test_uniform_has_maximum_entropy(self) -> None:
        uniform = uniform_epistemic()
        other = confident_dist()
        assert uniform.entropy() > other.entropy()

    def test_point_mass_has_zero_entropy(self) -> None:
        point = BehavioralDistribution.point_mass("epistemic_style", "confident")
        assert point.entropy() == pytest.approx(0.0, abs=1e-9)

    def test_entropy_nonnegative(self) -> None:
        for dim in list_dimensions():
            d = BehavioralDistribution.uniform(dim)
            assert d.entropy() >= 0.0

    def test_normalized_entropy_uniform_is_one(self) -> None:
        uniform = uniform_epistemic()
        assert uniform.normalized_entropy() == pytest.approx(1.0, abs=1e-9)

    def test_normalized_entropy_point_mass_is_zero(self) -> None:
        point = BehavioralDistribution.point_mass("epistemic_style", "confident")
        assert point.normalized_entropy() == pytest.approx(0.0, abs=1e-9)

    def test_normalized_entropy_in_range(self) -> None:
        d = confident_dist()
        h = d.normalized_entropy()
        assert 0.0 <= h <= 1.0

    def test_max_entropy_equals_log_n_states(self) -> None:
        d = uniform_epistemic()
        n = len(list_states("epistemic_style"))
        assert d.max_entropy() == pytest.approx(math.log(n), abs=1e-9)


# ---------------------------------------------------------------------------
# most_likely and sample
# ---------------------------------------------------------------------------

class TestMostLikelyAndSample:
    def test_most_likely_dominant_state(self) -> None:
        d = confident_dist()
        assert d.most_likely() == "confident"

    def test_most_likely_hedging(self) -> None:
        d = hedging_dist()
        assert d.most_likely() == "hedging"

    def test_sample_returns_valid_state(self) -> None:
        d = confident_dist()
        for _ in range(50):
            s = d.sample()
            assert s in d.states

    def test_sample_distribution_rough(self) -> None:
        # With enough samples, dominant state should appear most often
        d = BehavioralDistribution.point_mass("epistemic_style", "confident")
        samples = [d.sample() for _ in range(100)]
        assert all(s == "confident" for s in samples)


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_dict_round_trips(self) -> None:
        original = confident_dist()
        data = original.to_dict()
        restored = BehavioralDistribution.from_dict("epistemic_style", data)
        assert original == restored

    def test_to_dict_keys_are_states(self) -> None:
        d = confident_dist()
        data = d.to_dict()
        assert set(data.keys()) == set(list_states("epistemic_style"))

    def test_to_dict_values_sum_to_one(self) -> None:
        d = confident_dist()
        data = d.to_dict()
        assert abs(sum(data.values()) - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# getitem and repr
# ---------------------------------------------------------------------------

class TestAccessors:
    def test_getitem_valid_state(self) -> None:
        d = confident_dist()
        assert d["confident"] == pytest.approx(0.80)
        assert d["hedging"] == pytest.approx(0.10)

    def test_getitem_invalid_state(self) -> None:
        d = confident_dist()
        with pytest.raises(KeyError):
            _ = d["nonexistent"]

    def test_repr_contains_dimension(self) -> None:
        d = confident_dist()
        assert "epistemic_style" in repr(d)

    def test_repr_contains_dominant_state(self) -> None:
        d = confident_dist()
        assert "confident" in repr(d)

    def test_equality_same(self) -> None:
        assert confident_dist() == confident_dist()

    def test_equality_different(self) -> None:
        assert confident_dist() != hedging_dist()

    def test_equality_different_dimension(self) -> None:
        d1 = BehavioralDistribution.uniform("epistemic_style")
        d2 = BehavioralDistribution.uniform("risk_caution")
        assert d1 != d2


# ---------------------------------------------------------------------------
# total_kl_divergence
# ---------------------------------------------------------------------------

class TestTotalKLDivergence:
    def test_identical_profiles_is_zero(self) -> None:
        profile = {dim: BehavioralDistribution.uniform(dim) for dim in list_dimensions()}
        assert total_kl_divergence(profile, profile) == pytest.approx(0.0, abs=1e-9)

    def test_different_profiles_positive(self) -> None:
        observed = {
            "epistemic_style": confident_dist(),
            "risk_caution": BehavioralDistribution.uniform("risk_caution"),
        }
        declared = {
            "epistemic_style": hedging_dist(),
            "risk_caution": BehavioralDistribution.uniform("risk_caution"),
        }
        total = total_kl_divergence(observed, declared)
        assert total > 0.0

    def test_only_shared_dimensions_counted(self) -> None:
        observed = {"epistemic_style": confident_dist()}
        declared = {
            "epistemic_style": hedging_dist(),
            "risk_caution": BehavioralDistribution.uniform("risk_caution"),
        }
        # Only epistemic_style is shared — only that contributes
        total = total_kl_divergence(observed, declared)
        expected = confident_dist().kl_divergence(hedging_dist())
        assert total == pytest.approx(expected, rel=1e-6)
