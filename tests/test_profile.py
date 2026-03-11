"""Tests for BehavioralProfile (Phase 1)."""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from helios_mcp.profile import BehavioralProfile, SCHEMA_VERSION
from helios_mcp.distribution import BehavioralDistribution
from helios_mcp.taxonomy import list_dimensions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_DIMS = list_dimensions()


def _profile_sums_to_one(profile: BehavioralProfile) -> bool:
    """Return True if every distribution in the profile sums to 1.0."""
    for dim, dist in profile.distributions.items():
        total = sum(dist.probs)
        if abs(total - 1.0) > 1e-6:
            return False
    return True


# ---------------------------------------------------------------------------
# default_species()
# ---------------------------------------------------------------------------

class TestDefaultSpecies:
    def test_has_all_four_dimensions(self) -> None:
        profile = BehavioralProfile.default_species()
        for dim in _ALL_DIMS:
            assert dim in profile.distributions, f"Missing dimension: {dim}"

    def test_all_distributions_sum_to_one(self) -> None:
        profile = BehavioralProfile.default_species()
        assert _profile_sums_to_one(profile)

    def test_level_is_species(self) -> None:
        profile = BehavioralProfile.default_species()
        assert profile.level == "species"

    def test_agent_id_is_base(self) -> None:
        profile = BehavioralProfile.default_species()
        assert profile.agent_id == "base"

    def test_schema_version(self) -> None:
        profile = BehavioralProfile.default_species()
        assert profile.schema_version == SCHEMA_VERSION

    def test_distributions_are_behavioral_distribution_instances(self) -> None:
        profile = BehavioralProfile.default_species()
        for dim, dist in profile.distributions.items():
            assert isinstance(dist, BehavioralDistribution), f"Wrong type for {dim}"


# ---------------------------------------------------------------------------
# to_yaml_dict / from_yaml_dict round-trip
# ---------------------------------------------------------------------------

class TestYamlRoundTrip:
    def test_round_trip_preserves_agent_id(self) -> None:
        profile = BehavioralProfile.default_species()
        data = profile.to_yaml_dict()
        restored = BehavioralProfile.from_yaml_dict(data)
        assert restored.agent_id == profile.agent_id

    def test_round_trip_preserves_level(self) -> None:
        profile = BehavioralProfile.default_species()
        data = profile.to_yaml_dict()
        restored = BehavioralProfile.from_yaml_dict(data)
        assert restored.level == profile.level

    def test_round_trip_preserves_base_importance(self) -> None:
        profile = BehavioralProfile.default_species()
        data = profile.to_yaml_dict()
        restored = BehavioralProfile.from_yaml_dict(data)
        assert abs(restored.base_importance - profile.base_importance) < 1e-9

    def test_round_trip_preserves_specialization_level(self) -> None:
        profile = BehavioralProfile.default_species()
        data = profile.to_yaml_dict()
        restored = BehavioralProfile.from_yaml_dict(data)
        assert restored.specialization_level == profile.specialization_level

    def test_round_trip_preserves_distributions(self) -> None:
        profile = BehavioralProfile.default_species()
        data = profile.to_yaml_dict()
        restored = BehavioralProfile.from_yaml_dict(data)
        for dim in _ALL_DIMS:
            orig = profile.distributions[dim]
            rest = restored.distributions[dim]
            for s, p in zip(orig.states, orig.probs):
                assert abs(rest[s] - p) < 1e-6, f"Mismatch in {dim}/{s}"

    def test_round_trip_restored_sums_to_one(self) -> None:
        profile = BehavioralProfile.default_species()
        restored = BehavioralProfile.from_yaml_dict(profile.to_yaml_dict())
        assert _profile_sums_to_one(restored)

    def test_parent_id_present_in_dict_when_set(self) -> None:
        profile = BehavioralProfile.default_species()
        profile.parent_id = "some_parent"
        data = profile.to_yaml_dict()
        assert "parent_id" in data
        assert data["parent_id"] == "some_parent"

    def test_parent_id_absent_when_none(self) -> None:
        profile = BehavioralProfile.default_species()
        assert profile.parent_id is None
        data = profile.to_yaml_dict()
        assert "parent_id" not in data

    def test_schema_version_in_dict(self) -> None:
        profile = BehavioralProfile.default_species()
        data = profile.to_yaml_dict()
        assert data["schema_version"] == SCHEMA_VERSION


# ---------------------------------------------------------------------------
# save() / load() round-trip
# ---------------------------------------------------------------------------

class TestFileRoundTrip:
    def test_save_then_load_preserves_agent_id(self, tmp_path: Path) -> None:
        profile = BehavioralProfile.default_species()
        p = tmp_path / "profile.yaml"
        profile.save(p)
        loaded = BehavioralProfile.load(p)
        assert loaded.agent_id == profile.agent_id

    def test_save_then_load_preserves_distributions(self, tmp_path: Path) -> None:
        profile = BehavioralProfile.default_species()
        p = tmp_path / "profile.yaml"
        profile.save(p)
        loaded = BehavioralProfile.load(p)
        for dim in _ALL_DIMS:
            orig = profile.distributions[dim]
            rest = loaded.distributions[dim]
            for s, prob in zip(orig.states, orig.probs):
                assert abs(rest[s] - prob) < 1e-6

    def test_save_creates_file(self, tmp_path: Path) -> None:
        profile = BehavioralProfile.default_species()
        p = tmp_path / "subdir" / "profile.yaml"
        profile.save(p)
        assert p.exists()

    def test_load_restored_sums_to_one(self, tmp_path: Path) -> None:
        profile = BehavioralProfile.default_species()
        p = tmp_path / "profile.yaml"
        profile.save(p)
        loaded = BehavioralProfile.load(p)
        assert _profile_sums_to_one(loaded)

    def test_save_then_load_preserves_specialization_level(self, tmp_path: Path) -> None:
        profile = BehavioralProfile.default_species()
        profile.specialization_level = 3
        p = tmp_path / "profile.yaml"
        profile.save(p)
        loaded = BehavioralProfile.load(p)
        assert loaded.specialization_level == 3

    def test_save_then_load_preserves_base_importance(self, tmp_path: Path) -> None:
        profile = BehavioralProfile.default_species()
        profile.base_importance = 0.42
        p = tmp_path / "profile.yaml"
        profile.save(p)
        loaded = BehavioralProfile.load(p)
        assert abs(loaded.base_importance - 0.42) < 1e-6


# ---------------------------------------------------------------------------
# Missing dimensions fallback
# ---------------------------------------------------------------------------

class TestMissingDimensionFallback:
    def test_missing_dimension_gets_uniform_distribution(self) -> None:
        data = {
            "agent_id": "test",
            "level": "domain",
            "behavioral_distributions": {
                "epistemic_style": {
                    "confident": 0.25,
                    "hedging": 0.25,
                    "admits_ignorance": 0.25,
                    "speculating": 0.25,
                }
                # other 3 dimensions deliberately absent
            },
        }
        profile = BehavioralProfile.from_yaml_dict(data)
        for dim in _ALL_DIMS:
            assert dim in profile.distributions
            dist = profile.distributions[dim]
            assert abs(sum(dist.probs) - 1.0) < 1e-6

    def test_missing_dimension_is_uniform(self) -> None:
        data = {
            "agent_id": "test",
            "level": "domain",
            "behavioral_distributions": {},
        }
        profile = BehavioralProfile.from_yaml_dict(data)
        for dim in _ALL_DIMS:
            dist = profile.distributions[dim]
            expected_prob = 1.0 / len(dist.states)
            for p in dist.probs:
                assert abs(p - expected_prob) < 1e-6
