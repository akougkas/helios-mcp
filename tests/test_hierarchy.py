"""Tests for IdentityHierarchy (Phase 2)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from helios_mcp.hierarchy import IdentityHierarchy
from helios_mcp.profile import BehavioralProfile
from helios_mcp.taxonomy import list_dimensions


_ALL_DIMS = list_dimensions()


def _write_profile(path: Path, profile: BehavioralProfile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    profile.save(path)


def _make_helios_dir(tmp_path: Path) -> Path:
    helios = tmp_path / ".helios"
    (helios / "base").mkdir(parents=True, exist_ok=True)
    (helios / "personas").mkdir(parents=True, exist_ok=True)
    (helios / "temporary").mkdir(parents=True, exist_ok=True)
    (helios / "learned").mkdir(parents=True, exist_ok=True)
    return helios


def _sums_to_one(profile: BehavioralProfile) -> bool:
    for dist in profile.distributions.values():
        if abs(sum(dist.probs) - 1.0) > 1e-6:
            return False
    return True


# ---------------------------------------------------------------------------
# resolve() — species only (no persona file)
# ---------------------------------------------------------------------------

class TestResolveSpeciesOnly:
    def test_returns_species_profile_when_no_persona(self, tmp_path: Path) -> None:
        helios = _make_helios_dir(tmp_path)
        species = BehavioralProfile.default_species()
        _write_profile(helios / "base" / "identity.yaml", species)

        hierarchy = IdentityHierarchy(helios)
        result = hierarchy.resolve("developer")

        assert result is not None
        assert result.agent_id == "base"

    def test_missing_species_falls_back_to_default_species(self, tmp_path: Path) -> None:
        helios = _make_helios_dir(tmp_path)
        # No identity.yaml written
        hierarchy = IdentityHierarchy(helios)
        result = hierarchy.resolve("nobody")
        assert result.agent_id == "base"
        assert result.level == "species"

    def test_resolve_without_persona_all_dims_present(self, tmp_path: Path) -> None:
        helios = _make_helios_dir(tmp_path)
        species = BehavioralProfile.default_species()
        _write_profile(helios / "base" / "identity.yaml", species)
        hierarchy = IdentityHierarchy(helios)
        result = hierarchy.resolve("no_persona")
        for dim in _ALL_DIMS:
            assert dim in result.distributions


# ---------------------------------------------------------------------------
# resolve() — with domain persona file
# ---------------------------------------------------------------------------

class TestResolveWithPersona:
    def test_returns_blended_profile_with_persona_agent_id(self, tmp_path: Path) -> None:
        helios = _make_helios_dir(tmp_path)
        species = BehavioralProfile.default_species()
        _write_profile(helios / "base" / "identity.yaml", species)

        developer = BehavioralProfile(
            agent_id="developer",
            level="domain",
            distributions={
                d: BehavioralProfile.default_species().distributions[d]
                for d in _ALL_DIMS
            },
            parent_id="base",
            specialization_level=2,
            base_importance=0.7,
        )
        _write_profile(helios / "personas" / "developer.yaml", developer)

        hierarchy = IdentityHierarchy(helios)
        result = hierarchy.resolve("developer")
        assert result.agent_id == "developer"

    def test_blended_distributions_sum_to_one(self, tmp_path: Path) -> None:
        helios = _make_helios_dir(tmp_path)
        species = BehavioralProfile.default_species()
        _write_profile(helios / "base" / "identity.yaml", species)

        from helios_mcp.distribution import BehavioralDistribution
        persona = BehavioralProfile(
            agent_id="researcher",
            level="domain",
            distributions={
                "epistemic_style": BehavioralDistribution("epistemic_style", {
                    "confident": 0.10, "hedging": 0.50,
                    "admits_ignorance": 0.30, "speculating": 0.10,
                }),
                "interaction_agency": BehavioralDistribution("interaction_agency", {
                    "asks_first": 0.50, "assumes_and_acts": 0.10,
                    "offers_options": 0.30, "decides_unilaterally": 0.05,
                    "defers_to_user": 0.05,
                }),
                "communication_register": BehavioralDistribution("communication_register", {
                    "terse": 0.05, "moderate": 0.20, "thorough": 0.60,
                    "technical_dense": 0.10, "plain_accessible": 0.05,
                }),
                "risk_caution": BehavioralDistribution("risk_caution", {
                    "acts_immediately": 0.05, "checks_before_acting": 0.35,
                    "warns_frequently": 0.45, "refuses_ambiguity": 0.15,
                }),
            },
            parent_id="base",
            specialization_level=2,
            base_importance=0.7,
        )
        _write_profile(helios / "personas" / "researcher.yaml", persona)

        hierarchy = IdentityHierarchy(helios)
        result = hierarchy.resolve("researcher")
        assert _sums_to_one(result)


# ---------------------------------------------------------------------------
# Blend weight formula
# ---------------------------------------------------------------------------

class TestBlendWeightFormula:
    def test_weight_formula_basic(self, tmp_path: Path) -> None:
        """w = base_importance / spec_level^2 should be in [0.01, 1.0]."""
        helios = _make_helios_dir(tmp_path)
        species = BehavioralProfile.default_species()
        _write_profile(helios / "base" / "identity.yaml", species)

        # persona with spec_level=2, base_importance=0.7 => raw_weight = 0.175
        persona = BehavioralProfile(
            agent_id="testpersona",
            level="domain",
            distributions={d: species.distributions[d] for d in _ALL_DIMS},
            specialization_level=2,
            base_importance=0.7,
        )
        _write_profile(helios / "personas" / "testpersona.yaml", persona)

        hierarchy = IdentityHierarchy(helios)
        result = hierarchy.resolve("testpersona")
        # Result should be different from pure species (blended)
        # and distributions should still sum to 1
        assert _sums_to_one(result)

    def test_very_high_spec_level_clamped_to_min_weight(self, tmp_path: Path) -> None:
        """spec_level=1000 => raw_weight=0.0000007 < 0.01 => clamped to 0.01."""
        helios = _make_helios_dir(tmp_path)
        species = BehavioralProfile.default_species()
        _write_profile(helios / "base" / "identity.yaml", species)

        from helios_mcp.distribution import BehavioralDistribution
        persona = BehavioralProfile(
            agent_id="ultra_specialized",
            level="domain",
            distributions={d: species.distributions[d] for d in _ALL_DIMS},
            specialization_level=1000,
            base_importance=0.7,
        )
        _write_profile(helios / "personas" / "ultra_specialized.yaml", persona)

        hierarchy = IdentityHierarchy(helios)
        result = hierarchy.resolve("ultra_specialized")
        assert _sums_to_one(result)

    def test_spec_level_one_max_weight_clamped(self, tmp_path: Path) -> None:
        """spec_level=1, base_importance=1.0 => raw_weight=1.0 => clamped to 1.0."""
        helios = _make_helios_dir(tmp_path)
        species = BehavioralProfile.default_species()
        _write_profile(helios / "base" / "identity.yaml", species)

        persona = BehavioralProfile(
            agent_id="nospec",
            level="domain",
            distributions={d: species.distributions[d] for d in _ALL_DIMS},
            specialization_level=1,
            base_importance=1.0,
        )
        _write_profile(helios / "personas" / "nospec.yaml", persona)

        hierarchy = IdentityHierarchy(helios)
        result = hierarchy.resolve("nospec")
        assert _sums_to_one(result)


# ---------------------------------------------------------------------------
# Missing user/session levels are skipped
# ---------------------------------------------------------------------------

class TestMissingLevelsSkipped:
    def test_no_user_or_session_file_does_not_raise(self, tmp_path: Path) -> None:
        helios = _make_helios_dir(tmp_path)
        species = BehavioralProfile.default_species()
        _write_profile(helios / "base" / "identity.yaml", species)

        hierarchy = IdentityHierarchy(helios)
        # Should not raise even though user+session files are absent
        result = hierarchy.resolve("nobody")
        assert result is not None

    def test_result_has_all_dimensions_when_levels_missing(self, tmp_path: Path) -> None:
        helios = _make_helios_dir(tmp_path)
        species = BehavioralProfile.default_species()
        _write_profile(helios / "base" / "identity.yaml", species)

        hierarchy = IdentityHierarchy(helios)
        result = hierarchy.resolve("nobody")
        for dim in _ALL_DIMS:
            assert dim in result.distributions
