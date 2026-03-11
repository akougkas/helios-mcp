"""Tests for DriftDetector — behavioral drift detection using KL-divergence."""

from __future__ import annotations

import pytest

from helios_mcp.distribution import BehavioralDistribution
from helios_mcp.drift import DriftDetector, DriftResult
from helios_mcp.taxonomy import list_dimensions, list_states


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_uniform_profile() -> dict[str, BehavioralDistribution]:
    """Return uniform distributions across all 4 dimensions."""
    return {dim: BehavioralDistribution.uniform(dim) for dim in list_dimensions()}


def make_point_mass_profile(
    dim_state_pairs: dict[str, str],
) -> dict[str, BehavioralDistribution]:
    """Return point-mass distributions for specified dim->state, uniform elsewhere."""
    profile = make_uniform_profile()
    for dim, state in dim_state_pairs.items():
        profile[dim] = BehavioralDistribution.point_mass(dim, state)
    return profile


def make_detector() -> DriftDetector:
    return DriftDetector()


# ---------------------------------------------------------------------------
# DriftDetector constants
# ---------------------------------------------------------------------------

class TestDriftDetectorConstants:
    def test_total_threshold(self) -> None:
        assert DriftDetector.TOTAL_THRESHOLD == pytest.approx(0.30)

    def test_per_dim_threshold(self) -> None:
        assert DriftDetector.PER_DIM_THRESHOLD == pytest.approx(0.10)

    def test_min_observations(self) -> None:
        assert DriftDetector.MIN_OBSERVATIONS == 20


# ---------------------------------------------------------------------------
# per_dimension_drift
# ---------------------------------------------------------------------------

class TestPerDimensionDrift:
    def test_returns_entry_for_each_dimension(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.per_dimension_drift(declared, observed)
        assert set(result.keys()) == set(list_dimensions())

    def test_identical_distributions_zero_kl(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.per_dimension_drift(declared, observed)
        for dim, kl in result.items():
            assert kl == pytest.approx(0.0, abs=1e-9), f"Expected 0 for {dim}, got {kl}"

    def test_different_distributions_positive_kl(self) -> None:
        det = make_detector()
        declared = make_point_mass_profile({"epistemic_style": "confident"})
        observed = make_point_mass_profile({"epistemic_style": "hedging"})
        result = det.per_dimension_drift(declared, observed)
        assert result["epistemic_style"] > 0.0

    def test_only_shared_dimensions_included(self) -> None:
        det = make_detector()
        declared = {"epistemic_style": BehavioralDistribution.uniform("epistemic_style")}
        observed = {
            "epistemic_style": BehavioralDistribution.uniform("epistemic_style"),
            "interaction_agency": BehavioralDistribution.uniform("interaction_agency"),
        }
        result = det.per_dimension_drift(declared, observed)
        assert "epistemic_style" in result
        assert "interaction_agency" not in result


# ---------------------------------------------------------------------------
# compute_drift
# ---------------------------------------------------------------------------

class TestComputeDrift:
    def test_returns_drift_result(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=25)
        assert isinstance(result, DriftResult)

    def test_result_has_correct_fields(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=10)
        assert hasattr(result, "total_drift")
        assert hasattr(result, "per_dimension")
        assert hasattr(result, "exceeds_total_threshold")
        assert hasattr(result, "dimensions_exceeding_threshold")
        assert hasattr(result, "observation_count")
        assert hasattr(result, "sufficient_observations")
        assert hasattr(result, "timestamp")

    def test_identical_distributions_near_zero_total(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=25)
        assert result.total_drift == pytest.approx(0.0, abs=1e-9)

    def test_different_distributions_positive_total(self) -> None:
        det = make_detector()
        declared = make_point_mass_profile({"epistemic_style": "confident"})
        observed = make_point_mass_profile({"epistemic_style": "hedging"})
        result = det.compute_drift(declared, observed, observation_count=25)
        assert result.total_drift > 0.0

    def test_per_dimension_in_result(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=5)
        assert set(result.per_dimension.keys()) == set(list_dimensions())

    def test_observation_count_stored(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=15)
        assert result.observation_count == 15

    def test_sufficient_observations_true_when_at_threshold(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=20)
        assert result.sufficient_observations is True

    def test_sufficient_observations_false_below_threshold(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=19)
        assert result.sufficient_observations is False

    def test_exceeds_total_threshold_flag(self) -> None:
        det = make_detector()
        # Create strong divergence across multiple dimensions
        declared = {dim: BehavioralDistribution.point_mass(dim, list_states(dim)[0])
                    for dim in list_dimensions()}
        observed = {dim: BehavioralDistribution.point_mass(dim, list_states(dim)[-1])
                    for dim in list_dimensions()}
        result = det.compute_drift(declared, observed, observation_count=25)
        assert result.exceeds_total_threshold is True

    def test_no_exceed_threshold_for_identical(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=25)
        assert result.exceeds_total_threshold is False

    def test_dimensions_exceeding_threshold_empty_when_identical(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=25)
        assert result.dimensions_exceeding_threshold == []

    def test_dimensions_exceeding_threshold_populated(self) -> None:
        det = make_detector()
        declared = {"epistemic_style": BehavioralDistribution.point_mass("epistemic_style", "confident")}
        observed = {"epistemic_style": BehavioralDistribution.point_mass("epistemic_style", "hedging")}
        result = det.compute_drift(declared, observed, observation_count=25)
        assert "epistemic_style" in result.dimensions_exceeding_threshold

    def test_timestamp_is_string(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=5)
        assert isinstance(result.timestamp, str)
        assert len(result.timestamp) > 0


# ---------------------------------------------------------------------------
# exceeds_threshold
# ---------------------------------------------------------------------------

class TestExceedsThreshold:
    def test_false_when_insufficient_observations(self) -> None:
        det = make_detector()
        # Use highly divergent distributions but too few observations
        declared = {dim: BehavioralDistribution.point_mass(dim, list_states(dim)[0])
                    for dim in list_dimensions()}
        observed = {dim: BehavioralDistribution.point_mass(dim, list_states(dim)[-1])
                    for dim in list_dimensions()}
        result = det.compute_drift(declared, observed, observation_count=5)
        assert det.exceeds_threshold(result) is False

    def test_true_when_high_drift_and_sufficient_observations(self) -> None:
        det = make_detector()
        declared = {dim: BehavioralDistribution.point_mass(dim, list_states(dim)[0])
                    for dim in list_dimensions()}
        observed = {dim: BehavioralDistribution.point_mass(dim, list_states(dim)[-1])
                    for dim in list_dimensions()}
        result = det.compute_drift(declared, observed, observation_count=20)
        assert det.exceeds_threshold(result) is True

    def test_false_when_low_drift_sufficient_observations(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=20)
        assert det.exceeds_threshold(result) is False

    def test_false_at_exactly_min_minus_one(self) -> None:
        det = make_detector()
        declared = {dim: BehavioralDistribution.point_mass(dim, list_states(dim)[0])
                    for dim in list_dimensions()}
        observed = {dim: BehavioralDistribution.point_mass(dim, list_states(dim)[-1])
                    for dim in list_dimensions()}
        result = det.compute_drift(declared, observed, observation_count=19)
        assert det.exceeds_threshold(result) is False


# ---------------------------------------------------------------------------
# History recording and retrieval
# ---------------------------------------------------------------------------

class TestHistory:
    def test_get_history_empty_initially(self) -> None:
        det = make_detector()
        assert det.get_history("developer") == []

    def test_record_adds_to_history(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=10)
        det.record("developer", result)
        history = det.get_history("developer")
        assert len(history) == 1
        assert history[0] is result

    def test_record_multiple_entries(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        for _ in range(3):
            result = det.compute_drift(declared, observed, observation_count=10)
            det.record("developer", result)
        assert len(det.get_history("developer")) == 3

    def test_different_personas_separate_histories(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=10)
        det.record("developer", result)
        det.record("writer", result)
        assert len(det.get_history("developer")) == 1
        assert len(det.get_history("writer")) == 1
        assert len(det.get_history("analyst")) == 0

    def test_get_history_returns_copy(self) -> None:
        det = make_detector()
        declared = make_uniform_profile()
        observed = make_uniform_profile()
        result = det.compute_drift(declared, observed, observation_count=10)
        det.record("developer", result)
        history = det.get_history("developer")
        history.append(result)  # mutate the returned list
        # Original should be unchanged
        assert len(det.get_history("developer")) == 1


# ---------------------------------------------------------------------------
# Trend detection
# ---------------------------------------------------------------------------

class TestGetTrend:
    def _make_result(self, total_drift: float, obs_count: int = 25) -> DriftResult:
        return DriftResult(
            total_drift=total_drift,
            per_dimension={},
            exceeds_total_threshold=total_drift >= 0.30,
            dimensions_exceeding_threshold=[],
            observation_count=obs_count,
            sufficient_observations=obs_count >= 20,
            timestamp="2026-01-01T00:00:00+00:00",
        )

    def test_stable_with_no_history(self) -> None:
        det = make_detector()
        assert det.get_trend("developer") == "stable"

    def test_stable_with_one_entry(self) -> None:
        det = make_detector()
        det.record("developer", self._make_result(0.1))
        assert det.get_trend("developer") == "stable"

    def test_drifting_when_increasing(self) -> None:
        det = make_detector()
        det.record("developer", self._make_result(0.1))
        det.record("developer", self._make_result(0.2))
        det.record("developer", self._make_result(0.35))
        assert det.get_trend("developer") == "drifting"

    def test_stabilizing_when_decreasing(self) -> None:
        det = make_detector()
        det.record("developer", self._make_result(0.4))
        det.record("developer", self._make_result(0.25))
        det.record("developer", self._make_result(0.1))
        assert det.get_trend("developer") == "stabilizing"

    def test_stable_when_same_drift(self) -> None:
        det = make_detector()
        det.record("developer", self._make_result(0.2))
        det.record("developer", self._make_result(0.2))
        det.record("developer", self._make_result(0.2))
        assert det.get_trend("developer") == "stable"

    def test_trend_uses_last_three_only(self) -> None:
        det = make_detector()
        # First two are high (old history) — should be ignored in trend
        det.record("developer", self._make_result(0.5))
        det.record("developer", self._make_result(0.5))
        # Last three are decreasing — should show stabilizing
        det.record("developer", self._make_result(0.4))
        det.record("developer", self._make_result(0.3))
        det.record("developer", self._make_result(0.1))
        assert det.get_trend("developer") == "stabilizing"
