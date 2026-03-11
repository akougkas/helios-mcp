"""Tests for auto-accept small drift (Task 1.6).

Verifies that small drift (KL < 0.05 per dimension) is auto-accepted
silently, while larger drift requires negotiation.
"""

import pytest

from helios_mcp.config import HeliosConfig
from helios_mcp.drift import DriftDetector, DriftResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def detector():
    return DriftDetector()


def _make_result(
    per_dimension: dict[str, float],
    observation_count: int = 25,
) -> DriftResult:
    """Create a DriftResult with given per-dimension KL values."""
    total = sum(per_dimension.values())
    detector = DriftDetector()
    return DriftResult(
        total_drift=total,
        per_dimension=per_dimension,
        exceeds_total_threshold=total >= detector.TOTAL_THRESHOLD,
        dimensions_exceeding_threshold=[
            d for d, kl in per_dimension.items()
            if kl >= detector.PER_DIM_THRESHOLD
        ],
        observation_count=observation_count,
        sufficient_observations=observation_count >= detector.MIN_OBSERVATIONS,
        timestamp="2026-03-11T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# should_auto_accept
# ---------------------------------------------------------------------------


class TestShouldAutoAccept:
    def test_small_drift_auto_accepted(self, detector):
        result = _make_result({
            "epistemic_style": 0.02,
            "interaction_agency": 0.01,
            "communication_register": 0.03,
            "risk_caution": 0.01,
        })
        assert detector.should_auto_accept(result) is True

    def test_zero_drift_auto_accepted(self, detector):
        result = _make_result({
            "epistemic_style": 0.0,
            "interaction_agency": 0.0,
            "communication_register": 0.0,
            "risk_caution": 0.0,
        })
        assert detector.should_auto_accept(result) is True

    def test_large_drift_not_auto_accepted(self, detector):
        result = _make_result({
            "epistemic_style": 0.15,
            "interaction_agency": 0.08,
            "communication_register": 0.03,
            "risk_caution": 0.01,
        })
        assert detector.should_auto_accept(result) is False

    def test_one_dimension_above_threshold(self, detector):
        result = _make_result({
            "epistemic_style": 0.06,  # above 0.05
            "interaction_agency": 0.01,
            "communication_register": 0.02,
            "risk_caution": 0.01,
        })
        assert detector.should_auto_accept(result) is False

    def test_insufficient_observations_not_auto_accepted(self, detector):
        result = _make_result(
            per_dimension={
                "epistemic_style": 0.01,
                "interaction_agency": 0.01,
                "communication_register": 0.01,
                "risk_caution": 0.01,
            },
            observation_count=5,  # below MIN_OBSERVATIONS
        )
        assert detector.should_auto_accept(result) is False

    def test_exactly_at_threshold_not_auto_accepted(self, detector):
        result = _make_result({
            "epistemic_style": 0.05,  # exactly at threshold
            "interaction_agency": 0.01,
            "communication_register": 0.01,
            "risk_caution": 0.01,
        })
        # >= threshold means NOT auto-accepted (strict <)
        assert detector.should_auto_accept(result) is False

    def test_just_below_threshold_auto_accepted(self, detector):
        result = _make_result({
            "epistemic_style": 0.049,
            "interaction_agency": 0.049,
            "communication_register": 0.049,
            "risk_caution": 0.049,
        })
        assert detector.should_auto_accept(result) is True

    def test_custom_threshold(self, detector):
        detector.AUTO_ACCEPT_THRESHOLD = 0.10
        result = _make_result({
            "epistemic_style": 0.08,
            "interaction_agency": 0.07,
            "communication_register": 0.06,
            "risk_caution": 0.05,
        })
        assert detector.should_auto_accept(result) is True


# ---------------------------------------------------------------------------
# auto_accept_dimensions
# ---------------------------------------------------------------------------


class TestAutoAcceptDimensions:
    def test_all_below_threshold(self, detector):
        result = _make_result({
            "epistemic_style": 0.02,
            "interaction_agency": 0.01,
            "communication_register": 0.03,
            "risk_caution": 0.01,
        })
        dims = detector.auto_accept_dimensions(result)
        assert set(dims) == {
            "epistemic_style", "interaction_agency",
            "communication_register", "risk_caution",
        }

    def test_some_above_threshold(self, detector):
        result = _make_result({
            "epistemic_style": 0.15,
            "interaction_agency": 0.02,
            "communication_register": 0.08,
            "risk_caution": 0.01,
        })
        dims = detector.auto_accept_dimensions(result)
        assert "interaction_agency" in dims
        assert "risk_caution" in dims
        assert "epistemic_style" not in dims
        assert "communication_register" not in dims

    def test_none_below_threshold(self, detector):
        result = _make_result({
            "epistemic_style": 0.15,
            "interaction_agency": 0.12,
            "communication_register": 0.08,
            "risk_caution": 0.06,
        })
        dims = detector.auto_accept_dimensions(result)
        assert len(dims) == 0

    def test_insufficient_observations_returns_empty(self, detector):
        result = _make_result(
            per_dimension={
                "epistemic_style": 0.01,
                "interaction_agency": 0.01,
                "communication_register": 0.01,
                "risk_caution": 0.01,
            },
            observation_count=5,
        )
        assert detector.auto_accept_dimensions(result) == []


# ---------------------------------------------------------------------------
# HeliosConfig auto_accept_threshold
# ---------------------------------------------------------------------------


class TestHeliosConfigAutoAccept:
    def test_default_threshold(self):
        config = HeliosConfig.default()
        assert config.auto_accept_threshold == 0.05

    def test_custom_threshold(self, tmp_path):
        config = HeliosConfig(
            base_path=tmp_path / "base",
            personas_path=tmp_path / "personas",
            learned_path=tmp_path / "learned",
            temporary_path=tmp_path / "temporary",
            auto_accept_threshold=0.10,
        )
        assert config.auto_accept_threshold == 0.10


# ---------------------------------------------------------------------------
# Integration: auto-accept vs negotiate decision
# ---------------------------------------------------------------------------


class TestAutoAcceptVsNegotiate:
    def test_small_drift_auto_accept_large_negotiate(self, detector):
        """Verify the decision boundary between auto-accept and negotiate."""
        small = _make_result({
            "epistemic_style": 0.02,
            "interaction_agency": 0.01,
            "communication_register": 0.03,
            "risk_caution": 0.01,
        })
        large = _make_result({
            "epistemic_style": 0.12,
            "interaction_agency": 0.08,
            "communication_register": 0.15,
            "risk_caution": 0.03,
        })

        assert detector.should_auto_accept(small) is True
        assert detector.should_auto_accept(large) is False
        assert detector.exceeds_threshold(large) is True

    def test_medium_drift_neither_auto_nor_threshold(self, detector):
        """Drift above auto-accept but below negotiation threshold."""
        medium = _make_result({
            "epistemic_style": 0.06,
            "interaction_agency": 0.04,
            "communication_register": 0.03,
            "risk_caution": 0.02,
        })
        assert detector.should_auto_accept(medium) is False
        assert detector.exceeds_threshold(medium) is False
