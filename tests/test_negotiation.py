"""Tests for NegotiationEngine — Phase 5 of Helios v2."""
from __future__ import annotations

from pathlib import Path

import pytest

from helios_mcp.distribution import BehavioralDistribution
from helios_mcp.drift import DriftResult
from helios_mcp.negotiation import NegotiationEngine, NegotiationProposal
from helios_mcp.profile import BehavioralProfile
from helios_mcp.taxonomy import list_dimensions, list_states


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_DIMS = list_dimensions()


def make_uniform_profile(agent_id: str = "test_persona") -> BehavioralProfile:
    """Return a BehavioralProfile with uniform distributions."""
    return BehavioralProfile(
        agent_id=agent_id,
        level="domain",
        distributions={dim: BehavioralDistribution.uniform(dim) for dim in _ALL_DIMS},
    )


def make_point_mass_dists(state_map: dict[str, str]) -> dict[str, BehavioralDistribution]:
    """Return point-mass distributions for stated dims, uniform for the rest."""
    dists = {dim: BehavioralDistribution.uniform(dim) for dim in _ALL_DIMS}
    for dim, state in state_map.items():
        dists[dim] = BehavioralDistribution.point_mass(dim, state)
    return dists


def make_drift_result(
    total_drift: float = 0.5,
    observation_count: int = 25,
    dims_exceeding: list[str] | None = None,
) -> DriftResult:
    """Construct a DriftResult for testing."""
    per_dim = {dim: total_drift / len(_ALL_DIMS) for dim in _ALL_DIMS}
    return DriftResult(
        total_drift=total_drift,
        per_dimension=per_dim,
        exceeds_total_threshold=total_drift >= 0.30,
        dimensions_exceeding_threshold=dims_exceeding or [],
        observation_count=observation_count,
        sufficient_observations=observation_count >= 20,
        timestamp="2026-03-11T00:00:00+00:00",
    )


def make_drift_result_with_exceeding(dims: list[str]) -> DriftResult:
    """Make a DriftResult where specified dims exceed per-dim threshold."""
    per_dim = {dim: (0.15 if dim in dims else 0.02) for dim in _ALL_DIMS}
    total = sum(per_dim.values())
    return DriftResult(
        total_drift=total,
        per_dimension=per_dim,
        exceeds_total_threshold=total >= 0.30,
        dimensions_exceeding_threshold=dims,
        observation_count=25,
        sufficient_observations=True,
        timestamp="2026-03-11T00:00:00+00:00",
    )


def write_persona_yaml(path: Path, profile: BehavioralProfile) -> None:
    """Write a BehavioralProfile to a YAML file at the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    profile.save(path)


# ---------------------------------------------------------------------------
# generate_summary tests
# ---------------------------------------------------------------------------


class TestGenerateSummary:
    def test_returns_negotiation_proposal(self) -> None:
        engine = NegotiationEngine()
        profile = make_uniform_profile()
        observed = {dim: BehavioralDistribution.uniform(dim) for dim in _ALL_DIMS}
        drift_result = make_drift_result(dims_exceeding=["epistemic_style"])
        proposal = engine.generate_summary("developer", profile, observed, drift_result)
        assert isinstance(proposal, NegotiationProposal)

    def test_summary_is_non_empty_string(self) -> None:
        engine = NegotiationEngine()
        profile = make_uniform_profile()
        observed = {dim: BehavioralDistribution.uniform(dim) for dim in _ALL_DIMS}
        drift_result = make_drift_result(dims_exceeding=["epistemic_style"])
        proposal = engine.generate_summary("developer", profile, observed, drift_result)
        assert isinstance(proposal.summary, str)
        assert len(proposal.summary) > 0

    def test_summary_contains_persona_name(self) -> None:
        engine = NegotiationEngine()
        profile = make_uniform_profile()
        observed = {dim: BehavioralDistribution.uniform(dim) for dim in _ALL_DIMS}
        drift_result = make_drift_result(dims_exceeding=[])
        proposal = engine.generate_summary("my_agent", profile, observed, drift_result)
        assert "my_agent" in proposal.summary

    def test_summary_contains_observation_count(self) -> None:
        engine = NegotiationEngine()
        profile = make_uniform_profile()
        observed = {dim: BehavioralDistribution.uniform(dim) for dim in _ALL_DIMS}
        drift_result = make_drift_result(observation_count=42)
        proposal = engine.generate_summary("developer", profile, observed, drift_result)
        assert "42" in proposal.summary

    def test_per_dimension_summary_has_all_four_dimensions(self) -> None:
        engine = NegotiationEngine()
        profile = make_uniform_profile()
        observed = {dim: BehavioralDistribution.uniform(dim) for dim in _ALL_DIMS}
        drift_result = make_drift_result()
        proposal = engine.generate_summary("developer", profile, observed, drift_result)
        for dim in _ALL_DIMS:
            assert dim in proposal.per_dimension_summary, f"Missing dim: {dim}"

    def test_proposed_distributions_has_all_four_dimensions(self) -> None:
        engine = NegotiationEngine()
        profile = make_uniform_profile()
        observed = {dim: BehavioralDistribution.uniform(dim) for dim in _ALL_DIMS}
        drift_result = make_drift_result()
        proposal = engine.generate_summary("developer", profile, observed, drift_result)
        for dim in _ALL_DIMS:
            assert dim in proposal.proposed_distributions, f"Missing dim: {dim}"

    def test_proposed_distributions_sum_to_one(self) -> None:
        engine = NegotiationEngine()
        profile = make_uniform_profile()
        observed = {dim: BehavioralDistribution.uniform(dim) for dim in _ALL_DIMS}
        drift_result = make_drift_result()
        proposal = engine.generate_summary("developer", profile, observed, drift_result)
        for dim, dist_dict in proposal.proposed_distributions.items():
            total = sum(dist_dict.values())
            assert abs(total - 1.0) < 1e-6, f"Dim {dim} sums to {total}"

    def test_proposed_at_is_iso_timestamp(self) -> None:
        engine = NegotiationEngine()
        profile = make_uniform_profile()
        observed = {dim: BehavioralDistribution.uniform(dim) for dim in _ALL_DIMS}
        drift_result = make_drift_result()
        proposal = engine.generate_summary("developer", profile, observed, drift_result)
        assert isinstance(proposal.proposed_at, str)
        assert len(proposal.proposed_at) > 10

    def test_summary_fallback_when_no_dims_exceeding(self) -> None:
        engine = NegotiationEngine()
        profile = make_uniform_profile()
        observed = {dim: BehavioralDistribution.uniform(dim) for dim in _ALL_DIMS}
        drift_result = make_drift_result(dims_exceeding=[])
        proposal = engine.generate_summary("developer", profile, observed, drift_result)
        assert "Multiple dimensions" in proposal.summary


# ---------------------------------------------------------------------------
# generate_per_dimension_summary tests
# ---------------------------------------------------------------------------


class TestGeneratePerDimensionSummary:
    def _make_declared_observed(
        self, dim: str, d_state: str, o_state: str
    ) -> tuple[BehavioralDistribution, BehavioralDistribution]:
        declared = BehavioralDistribution.point_mass(dim, d_state)
        observed = BehavioralDistribution.point_mass(dim, o_state)
        return declared, observed

    def test_stable_case_kl_below_0_05(self) -> None:
        engine = NegotiationEngine()
        dim = "epistemic_style"
        declared = BehavioralDistribution.uniform(dim)
        observed = BehavioralDistribution.uniform(dim)
        result = engine.generate_per_dimension_summary(dim, declared, observed, kl=0.02)
        assert "Stable" in result
        assert "well-aligned" in result

    def test_minor_drift_case_kl_between_0_05_and_0_10(self) -> None:
        engine = NegotiationEngine()
        dim = "epistemic_style"
        declared = BehavioralDistribution.uniform(dim)
        observed = BehavioralDistribution.uniform(dim)
        result = engine.generate_per_dimension_summary(dim, declared, observed, kl=0.07)
        assert "Minor drift" in result

    def test_significant_drift_case_kl_at_or_above_0_10(self) -> None:
        engine = NegotiationEngine()
        dim = "epistemic_style"
        states = list_states(dim)
        declared = BehavioralDistribution.point_mass(dim, states[0])
        # Use a high-probability but not point-mass to avoid zero-division in formatting
        observed_dict = {s: (0.9 if s == states[1] else 0.1 / (len(states) - 1)) for s in states}
        observed = BehavioralDistribution(dim, observed_dict)
        result = engine.generate_per_dimension_summary(dim, declared, observed, kl=0.15)
        assert "Significant drift" in result
        assert "%" in result

    def test_minor_drift_contains_observed_most_likely(self) -> None:
        engine = NegotiationEngine()
        dim = "risk_caution"
        states = list_states(dim)
        declared = BehavioralDistribution.uniform(dim)
        # make observed skew toward states[2]
        obs_dict = {s: (0.7 if s == states[2] else 0.3 / (len(states) - 1)) for s in states}
        observed = BehavioralDistribution(dim, obs_dict)
        result = engine.generate_per_dimension_summary(dim, declared, observed, kl=0.07)
        assert states[2] in result


# ---------------------------------------------------------------------------
# reject_update tests
# ---------------------------------------------------------------------------


class TestRejectUpdate:
    def test_returns_status_rejected(self, tmp_path: Path) -> None:
        engine = NegotiationEngine()
        result = engine.reject_update("developer", "Not convinced", tmp_path)
        assert result["status"] == "rejected"

    def test_returns_persona_name(self, tmp_path: Path) -> None:
        engine = NegotiationEngine()
        result = engine.reject_update("writer", "wrong drift", tmp_path)
        assert result["persona"] == "writer"

    def test_returns_reason(self, tmp_path: Path) -> None:
        engine = NegotiationEngine()
        reason = "The observed behavior was a fluke"
        result = engine.reject_update("developer", reason, tmp_path)
        assert result["reason"] == reason


# ---------------------------------------------------------------------------
# apply_update tests
# ---------------------------------------------------------------------------


def _make_minimal_persona_yaml(tmp_path: Path, persona_name: str) -> Path:
    """Create a minimal valid persona YAML under tmp_path/personas/."""
    profile = make_uniform_profile(agent_id=persona_name)
    persona_path = tmp_path / "personas" / f"{persona_name}.yaml"
    write_persona_yaml(persona_path, profile)
    return persona_path


class TestApplyUpdate:
    def _make_proposal(
        self,
        persona_name: str,
        dims_to_propose: list[str] | None = None,
    ) -> NegotiationProposal:
        """Create a NegotiationProposal with point-mass observed distributions."""
        dims = dims_to_propose or _ALL_DIMS
        engine = NegotiationEngine()
        profile = make_uniform_profile(agent_id=persona_name)
        observed: dict[str, BehavioralDistribution] = {}
        for dim in _ALL_DIMS:
            if dim in dims:
                # Use point mass on last state to differ from uniform declared
                observed[dim] = BehavioralDistribution.point_mass(dim, list_states(dim)[-1])
            else:
                observed[dim] = BehavioralDistribution.uniform(dim)

        drift_result = make_drift_result(dims_exceeding=dims)
        return engine.generate_summary(persona_name, profile, observed, drift_result)

    def test_returns_status_applied(self, tmp_path: Path) -> None:
        persona_name = "developer"
        _make_minimal_persona_yaml(tmp_path, persona_name)
        proposal = self._make_proposal(persona_name)
        engine = NegotiationEngine()
        result = engine.apply_update(persona_name, proposal, tmp_path)
        assert result["status"] == "applied"

    def test_profile_file_exists_after_apply(self, tmp_path: Path) -> None:
        persona_name = "developer"
        persona_path = _make_minimal_persona_yaml(tmp_path, persona_name)
        proposal = self._make_proposal(persona_name)
        engine = NegotiationEngine()
        engine.apply_update(persona_name, proposal, tmp_path)
        assert persona_path.exists()

    def test_updated_dimensions_in_result(self, tmp_path: Path) -> None:
        persona_name = "developer"
        _make_minimal_persona_yaml(tmp_path, persona_name)
        proposal = self._make_proposal(persona_name)
        engine = NegotiationEngine()
        result = engine.apply_update(persona_name, proposal, tmp_path)
        assert isinstance(result["updated_dimensions"], list)
        assert len(result["updated_dimensions"]) > 0

    def test_commit_message_in_result(self, tmp_path: Path) -> None:
        persona_name = "developer"
        _make_minimal_persona_yaml(tmp_path, persona_name)
        proposal = self._make_proposal(persona_name)
        engine = NegotiationEngine()
        result = engine.apply_update(persona_name, proposal, tmp_path)
        assert "developer" in result["commit_message"]
        assert "Behavioral evolution" in result["commit_message"]

    def test_apply_with_accepted_dimensions_subset(self, tmp_path: Path) -> None:
        persona_name = "developer"
        _make_minimal_persona_yaml(tmp_path, persona_name)
        proposal = self._make_proposal(persona_name)
        engine = NegotiationEngine()
        # Only accept the first two dimensions
        subset = _ALL_DIMS[:2]
        result = engine.apply_update(
            persona_name, proposal, tmp_path, accepted_dimensions=subset
        )
        assert result["status"] == "applied"
        assert set(result["updated_dimensions"]) == set(subset)

    def test_subset_only_changes_accepted_dimensions(self, tmp_path: Path) -> None:
        persona_name = "developer"
        persona_path = _make_minimal_persona_yaml(tmp_path, persona_name)
        proposal = self._make_proposal(persona_name)
        engine = NegotiationEngine()

        # Read original profile for unaccepted dims
        original_profile = BehavioralProfile.load(persona_path)

        subset = [_ALL_DIMS[0]]  # only accept the first dimension
        engine.apply_update(persona_name, proposal, tmp_path, accepted_dimensions=subset)

        updated_profile = BehavioralProfile.load(persona_path)

        # The accepted dimension should have changed (point mass vs uniform)
        accepted_dim = _ALL_DIMS[0]
        original_dist = original_profile.distributions[accepted_dim]
        updated_dist = updated_profile.distributions[accepted_dim]
        # They should differ since proposed is point_mass, original is uniform
        assert updated_dist != original_dist

        # The non-accepted dimensions should be unchanged
        for dim in _ALL_DIMS[1:]:
            orig = original_profile.distributions[dim]
            updated = updated_profile.distributions[dim]
            assert orig == updated, f"Dimension {dim} should not have changed"
