"""Tests for profile export engine (Tasks 2.5, 2.6).

Covers all three export modes, SoulSpec format, and round-trip behavior.
"""

import pytest

from helios_mcp.distribution import BehavioralDistribution
from helios_mcp.exporter import (
    export_context,
    export_diff,
    export_dimensions,
    export_soulspec,
)
from helios_mcp.profile import BehavioralProfile
from helios_mcp.taxonomy import list_dimensions, list_states


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_profile(agent_id: str = "test", confident: float = 0.6) -> BehavioralProfile:
    """Create a test profile with configurable epistemic_style bias."""
    remaining = 1.0 - confident
    n_other = 3
    other = remaining / n_other

    return BehavioralProfile(
        agent_id=agent_id,
        level="user",
        distributions={
            "epistemic_style": BehavioralDistribution("epistemic_style", {
                "confident": confident, "hedging": other,
                "admits_ignorance": other, "speculating": other,
            }),
            "interaction_agency": BehavioralDistribution("interaction_agency", {
                "asks_first": 0.2, "assumes_and_acts": 0.3,
                "offers_options": 0.25, "decides_unilaterally": 0.15,
                "defers_to_user": 0.1,
            }),
            "communication_register": BehavioralDistribution("communication_register", {
                "terse": 0.35, "moderate": 0.3,
                "thorough": 0.15, "technical_dense": 0.15,
                "plain_accessible": 0.05,
            }),
            "risk_caution": BehavioralDistribution("risk_caution", {
                "acts_immediately": 0.2, "checks_before_acting": 0.4,
                "warns_frequently": 0.25, "refuses_ambiguity": 0.15,
            }),
        },
    )


# ---------------------------------------------------------------------------
# export_dimensions
# ---------------------------------------------------------------------------


class TestExportDimensions:
    def test_all_dimensions(self):
        profile = _make_profile()
        result = export_dimensions(profile)
        assert result["agent_id"] == "test"
        assert len(result["dimensions"]) == 4

    def test_specific_dimensions(self):
        profile = _make_profile()
        result = export_dimensions(profile, dimensions=["epistemic_style", "risk_caution"])
        assert len(result["dimensions"]) == 2
        assert "epistemic_style" in result["dimensions"]
        assert "risk_caution" in result["dimensions"]
        assert "interaction_agency" not in result["dimensions"]

    def test_single_dimension(self):
        profile = _make_profile()
        result = export_dimensions(profile, dimensions=["epistemic_style"])
        dim_data = result["dimensions"]["epistemic_style"]
        assert "dominant_state" in dim_data
        assert "entropy" in dim_data
        assert "distribution" in dim_data
        assert "description" in dim_data

    def test_distribution_values_present(self):
        profile = _make_profile()
        result = export_dimensions(profile, dimensions=["epistemic_style"])
        dist = result["dimensions"]["epistemic_style"]["distribution"]
        assert "confident" in dist
        assert "hedging" in dist
        assert dist["confident"] == 0.6

    def test_invalid_dimension_raises(self):
        profile = _make_profile()
        with pytest.raises(ValueError, match="not found"):
            export_dimensions(profile, dimensions=["nonexistent"])

    def test_entropy_in_range(self):
        profile = _make_profile()
        result = export_dimensions(profile)
        for dim_data in result["dimensions"].values():
            assert 0.0 <= dim_data["entropy"] <= 1.0


# ---------------------------------------------------------------------------
# export_context
# ---------------------------------------------------------------------------


class TestExportContext:
    def test_includes_context_tag(self):
        profile = _make_profile()
        result = export_context(profile, "python_coding")
        assert result["context"] == "python_coding"

    def test_includes_all_dimensions(self):
        profile = _make_profile()
        result = export_context(profile, "reviewing")
        assert len(result["dimensions"]) == 4


# ---------------------------------------------------------------------------
# export_diff
# ---------------------------------------------------------------------------


class TestExportDiff:
    def test_no_change(self):
        profile = _make_profile()
        result = export_diff(profile, profile)
        assert result["total_kl"] == 0.0
        for dim_data in result["change_summary"].values():
            assert dim_data["kl_divergence"] == 0.0
            assert dim_data["dominant_changed"] is False

    def test_different_profiles(self):
        old = _make_profile(confident=0.4)
        new = _make_profile(confident=0.8)
        result = export_diff(new, old)
        assert result["total_kl"] > 0.0
        ep = result["change_summary"]["epistemic_style"]
        assert ep["kl_divergence"] > 0.0
        assert ep["dominant_after"] == "confident"

    def test_state_deltas_present(self):
        old = _make_profile(confident=0.4)
        new = _make_profile(confident=0.8)
        result = export_diff(new, old)
        deltas = result["change_summary"]["epistemic_style"]["state_deltas"]
        assert "confident" in deltas
        assert deltas["confident"] > 0  # increased

    def test_dominant_changed_flag(self):
        old = _make_profile(confident=0.25)  # hedging/admits_ignorance might dominate
        new = _make_profile(confident=0.9)
        result = export_diff(new, old)
        # With 0.9 confident, dominant should be confident
        assert result["change_summary"]["epistemic_style"]["dominant_after"] == "confident"


# ---------------------------------------------------------------------------
# export_soulspec
# ---------------------------------------------------------------------------


class TestExportSoulspec:
    def test_produces_markdown(self):
        profile = _make_profile()
        md = export_soulspec(profile)
        assert md.startswith("# test")
        assert "##" in md

    def test_includes_all_dimensions(self):
        profile = _make_profile()
        md = export_soulspec(profile)
        assert "Epistemic Style" in md
        assert "Interaction Agency" in md
        assert "Communication Register" in md
        assert "Risk Caution" in md

    def test_includes_metadata_comments(self):
        profile = _make_profile()
        md = export_soulspec(profile)
        assert "<!--" in md
        assert "helios:" in md
        assert "-->" in md

    def test_includes_distribution_values(self):
        profile = _make_profile()
        md = export_soulspec(profile)
        assert "confident:" in md
        assert "0.6000" in md

    def test_includes_description(self):
        profile = _make_profile()
        profile.description = "Test agent for export"
        md = export_soulspec(profile)
        assert "Test agent for export" in md

    def test_natural_language_labels(self):
        profile = _make_profile()
        md = export_soulspec(profile)
        # Should contain natural language from STATE_LABELS
        assert "%" in md  # percentage in description


# ---------------------------------------------------------------------------
# Round-trip: import → export → import
# ---------------------------------------------------------------------------


class TestRoundTrip:
    def test_export_import_dimensions_stable(self):
        """Exported dimension data should reflect original profile values."""
        profile = _make_profile()
        exported = export_dimensions(profile)

        for dim in list_dimensions():
            dim_data = exported["dimensions"][dim]
            original_dist = profile.distributions[dim]
            assert dim_data["dominant_state"] == original_dist.most_likely()
            for state in list_states(dim):
                assert abs(dim_data["distribution"][state] - original_dist[state]) < 0.001

    def test_diff_is_zero_for_same_profile(self):
        profile = _make_profile()
        diff = export_diff(profile, profile)
        assert diff["total_kl"] == 0.0
        for dim_data in diff["change_summary"].values():
            assert len(dim_data["state_deltas"]) == 0
