"""Regression tests for the `helios-mcp negotiate` accept/reject flow.

The `negotiate` CLI command used to print "Changes accepted." on the
[A]ccept branch without ever calling NegotiationEngine.apply_update() —
no YAML write, no git commit. These tests prove the fix mirrors the
`negotiate_update` MCP tool in server.py:

- Accepting (via the new non-interactive --yes flag) persists the
  observed distributions to the persona YAML and creates a git commit.
- Rejecting (via the interactive prompt) leaves the persona YAML and
  git history untouched.
- A failure (accepting for a persona with no dedicated persona YAML)
  is reported with a nonzero exit instead of silently claiming success.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from helios_mcp.bootstrap import BootstrapManager
from helios_mcp.cli import main
from helios_mcp.observer import BehavioralObserver


def _terse_confident_messages() -> list[dict]:
    """A short, confident, no-hedging conversation — biases distributions
    away from the declared 'developer' persona defaults, guaranteeing
    that accepting a negotiation actually changes the persisted YAML.
    """
    return [
        {"role": "user", "content": "Refactor this function."},
        {"role": "assistant", "content": "Done. I rewrote it using list comprehension."},
        {"role": "user", "content": "Great."},
        {"role": "assistant", "content": "I will update the tests next."},
    ]


def _seed_observations(helios_dir: Path, persona: str, count: int = 25) -> None:
    """Persist `count` biased text observations for persona."""
    observer = BehavioralObserver(helios_dir)
    messages = _terse_confident_messages()
    for _ in range(count):
        observer.observe(persona, messages)


def _git_log(helios_dir: Path) -> list[str]:
    """Return the git log (oneline) for helios_dir, oldest-safe empty list."""
    result = subprocess.run(
        ["git", "-C", str(helios_dir), "log", "--oneline"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip().splitlines()


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def bootstrapped_helios_dir(tmp_path: Path) -> Path:
    """A freshly bootstrapped ~/.helios with git enabled and a 'developer' persona."""
    helios_dir = tmp_path / "helios"
    BootstrapManager(helios_dir, git_enabled=True).bootstrap_installation()
    assert (helios_dir / "base" / "identity.yaml").exists()
    assert (helios_dir / "personas" / "developer.yaml").exists()
    return helios_dir


class TestNegotiateAccept:
    """Accepting a negotiation must call NegotiationEngine.apply_update()."""

    def test_accept_persists_distributions_and_commits(
        self, runner: CliRunner, bootstrapped_helios_dir: Path
    ) -> None:
        persona = "developer"
        persona_path = bootstrapped_helios_dir / "personas" / f"{persona}.yaml"
        _seed_observations(bootstrapped_helios_dir, persona)

        before_yaml = yaml.safe_load(persona_path.read_text())
        commits_before = len(_git_log(bootstrapped_helios_dir))

        result = runner.invoke(
            main,
            ["negotiate", persona, "--helios-dir", str(bootstrapped_helios_dir), "--yes"],
        )

        assert result.exit_code == 0, result.output
        assert "Changes accepted" in result.output
        assert "Committed to git" in result.output

        after_yaml = yaml.safe_load(persona_path.read_text())
        assert (
            after_yaml["behavioral_distributions"]
            != before_yaml["behavioral_distributions"]
        ), "Accepting should persist the observed distributions to the persona YAML"

        commits_after = len(_git_log(bootstrapped_helios_dir))
        assert commits_after > commits_before, "Accepting should create a git commit"

        newest_commit = _git_log(bootstrapped_helios_dir)[0].lower()
        assert persona in newest_commit or "behavioral evolution" in newest_commit

    def test_accept_reports_updated_dimensions(
        self, runner: CliRunner, bootstrapped_helios_dir: Path
    ) -> None:
        persona = "developer"
        _seed_observations(bootstrapped_helios_dir, persona)

        result = runner.invoke(
            main,
            ["negotiate", persona, "--helios-dir", str(bootstrapped_helios_dir), "--yes"],
        )

        assert result.exit_code == 0, result.output
        # All 4 dimensions are proposed and accepted by default.
        for dim in (
            "epistemic_style",
            "interaction_agency",
            "communication_register",
            "risk_caution",
        ):
            assert dim in result.output


class TestNegotiateReject:
    """Rejecting a negotiation must not touch the persona YAML or git history."""

    def test_reject_leaves_yaml_and_history_unchanged(
        self, runner: CliRunner, bootstrapped_helios_dir: Path
    ) -> None:
        persona = "developer"
        persona_path = bootstrapped_helios_dir / "personas" / f"{persona}.yaml"
        _seed_observations(bootstrapped_helios_dir, persona)

        before_yaml = persona_path.read_text()
        commits_before = len(_git_log(bootstrapped_helios_dir))

        result = runner.invoke(
            main,
            ["negotiate", persona, "--helios-dir", str(bootstrapped_helios_dir)],
            input="R\n",
        )

        assert result.exit_code == 0, result.output
        assert "Changes rejected" in result.output

        after_yaml = persona_path.read_text()
        assert after_yaml == before_yaml, "Rejecting must not modify the persona YAML"

        commits_after = len(_git_log(bootstrapped_helios_dir))
        assert commits_after == commits_before, "Rejecting must not create a git commit"

    def test_quit_leaves_yaml_unchanged(
        self, runner: CliRunner, bootstrapped_helios_dir: Path
    ) -> None:
        persona = "developer"
        persona_path = bootstrapped_helios_dir / "personas" / f"{persona}.yaml"
        _seed_observations(bootstrapped_helios_dir, persona)

        before_yaml = persona_path.read_text()

        result = runner.invoke(
            main,
            ["negotiate", persona, "--helios-dir", str(bootstrapped_helios_dir)],
            input="Q\n",
        )

        assert result.exit_code == 0, result.output
        assert "No action taken." in result.output
        assert persona_path.read_text() == before_yaml


class TestNegotiateFailure:
    """A failure during accept must be reported, not silently swallowed."""

    def test_missing_persona_yaml_reports_error_on_accept(
        self, runner: CliRunner, bootstrapped_helios_dir: Path
    ) -> None:
        # "ghost" has observations (so the drift report renders) but no
        # dedicated personas/ghost.yaml — hierarchy.resolve() falls back
        # to the species base, so the report succeeds, but
        # NegotiationEngine.apply_update() must fail trying to load
        # personas/ghost.yaml directly.
        persona = "ghost"
        persona_path = bootstrapped_helios_dir / "personas" / f"{persona}.yaml"
        assert not persona_path.exists()

        _seed_observations(bootstrapped_helios_dir, persona, count=1)
        commits_before = len(_git_log(bootstrapped_helios_dir))

        result = runner.invoke(
            main,
            ["negotiate", persona, "--helios-dir", str(bootstrapped_helios_dir), "--yes"],
        )

        assert result.exit_code != 0, result.output
        assert "Failed to apply update" in result.output
        assert not persona_path.exists(), "A failed accept must not create a persona file"

        commits_after = len(_git_log(bootstrapped_helios_dir))
        assert commits_after == commits_before, "A failed accept must not create a git commit"
