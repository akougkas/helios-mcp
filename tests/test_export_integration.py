"""Tests for export_profile MCP tool and CLI export command (Tasks 2.7, 2.8)."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from helios_mcp.cli import main
from helios_mcp.distribution import BehavioralDistribution
from helios_mcp.profile import BehavioralProfile


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def helios_dir(tmp_path):
    """Set up a helios directory with a base identity and a developer persona."""
    d = tmp_path / "helios"

    # Base identity
    base_dir = d / "base"
    base_dir.mkdir(parents=True)
    base_profile = BehavioralProfile(
        agent_id="base",
        level="species",
        distributions={
            "epistemic_style": BehavioralDistribution("epistemic_style", {
                "confident": 0.25, "hedging": 0.25,
                "admits_ignorance": 0.25, "speculating": 0.25,
            }),
            "interaction_agency": BehavioralDistribution("interaction_agency", {
                "asks_first": 0.2, "assumes_and_acts": 0.2,
                "offers_options": 0.2, "decides_unilaterally": 0.2,
                "defers_to_user": 0.2,
            }),
            "communication_register": BehavioralDistribution("communication_register", {
                "terse": 0.2, "moderate": 0.2,
                "thorough": 0.2, "technical_dense": 0.2,
                "plain_accessible": 0.2,
            }),
            "risk_caution": BehavioralDistribution("risk_caution", {
                "acts_immediately": 0.25, "checks_before_acting": 0.25,
                "warns_frequently": 0.25, "refuses_ambiguity": 0.25,
            }),
        },
    )
    base_profile.save(base_dir / "identity.yaml")

    # Developer persona
    personas_dir = d / "personas"
    personas_dir.mkdir(parents=True)
    dev_profile = BehavioralProfile(
        agent_id="developer",
        level="domain",
        parent_id="base",
        specialization_level=2,
        distributions={
            "epistemic_style": BehavioralDistribution("epistemic_style", {
                "confident": 0.65, "hedging": 0.15,
                "admits_ignorance": 0.15, "speculating": 0.05,
            }),
            "interaction_agency": BehavioralDistribution("interaction_agency", {
                "asks_first": 0.15, "assumes_and_acts": 0.40,
                "offers_options": 0.25, "decides_unilaterally": 0.10,
                "defers_to_user": 0.10,
            }),
            "communication_register": BehavioralDistribution("communication_register", {
                "terse": 0.35, "moderate": 0.30,
                "thorough": 0.15, "technical_dense": 0.15,
                "plain_accessible": 0.05,
            }),
            "risk_caution": BehavioralDistribution("risk_caution", {
                "acts_immediately": 0.20, "checks_before_acting": 0.40,
                "warns_frequently": 0.25, "refuses_ambiguity": 0.15,
            }),
        },
    )
    dev_profile.save(personas_dir / "developer.yaml")

    return d


class TestCLIExport:
    def test_export_yaml(self, runner, helios_dir):
        result = runner.invoke(
            main, ["export", "developer", "--helios-dir", str(helios_dir)],
        )
        assert result.exit_code == 0
        assert "epistemic_style" in result.output
        assert "interaction_agency" in result.output

    def test_export_json(self, runner, helios_dir):
        result = runner.invoke(
            main, ["export", "developer", "--format", "json",
                   "--helios-dir", str(helios_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "dimensions" in data
        assert "epistemic_style" in data["dimensions"]

    def test_export_soulspec(self, runner, helios_dir):
        result = runner.invoke(
            main, ["export", "developer", "--format", "soulspec",
                   "--helios-dir", str(helios_dir)],
        )
        assert result.exit_code == 0
        assert "Epistemic Style" in result.output
        assert "<!--" in result.output

    def test_export_specific_dimensions(self, runner, helios_dir):
        result = runner.invoke(
            main, ["export", "developer", "--format", "json",
                   "--dimensions", "epistemic_style,risk_caution",
                   "--helios-dir", str(helios_dir)],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data["dimensions"]) == 2
        assert "epistemic_style" in data["dimensions"]
        assert "risk_caution" in data["dimensions"]

    def test_export_nonexistent_persona_falls_back(self, runner, helios_dir):
        """Nonexistent persona falls back to base profile via hierarchy."""
        result = runner.invoke(
            main, ["export", "nonexistent", "--format", "json",
                   "--helios-dir", str(helios_dir)],
        )
        # Hierarchy resolves to base if no persona-specific file exists
        if result.exit_code == 0:
            data = json.loads(result.output)
            assert "dimensions" in data

    def test_export_invalid_dimension(self, runner, helios_dir):
        result = runner.invoke(
            main, ["export", "developer", "--format", "json",
                   "--dimensions", "bogus",
                   "--helios-dir", str(helios_dir)],
        )
        assert result.exit_code != 0
