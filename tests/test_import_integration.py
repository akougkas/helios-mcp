"""Tests for import_profile MCP tool and CLI import command (Tasks 2.3, 2.4)."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from helios_mcp.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def helios_dir(tmp_path):
    d = tmp_path / "helios"
    (d / "base").mkdir(parents=True)
    return d


@pytest.fixture
def claude_md(tmp_path):
    path = tmp_path / "CLAUDE.md"
    path.write_text("""# CLAUDE.md

## Tone
Direct. Opinionated. Push back when wrong.
Every word earns its place. Be concise and terse.

## Style
Technical language. Expert reader assumed.
""")
    return path


@pytest.fixture
def soul_md(tmp_path):
    path = tmp_path / "soul.md"
    path.write_text("""# SoulSpec

## Identity
A thorough and careful assistant that checks before acting.

## Communication
Comprehensive and detailed explanations.
""")
    return path


# ---------------------------------------------------------------------------
# CLI import command
# ---------------------------------------------------------------------------


class TestCLIImport:
    def test_import_claude_md(self, runner, helios_dir, claude_md):
        result = runner.invoke(
            main,
            ["import", str(claude_md), "--helios-dir", str(helios_dir)],
        )
        assert result.exit_code == 0
        assert "Imported from:" in result.output
        assert "Saved to:" in result.output
        persona_file = helios_dir / "personas" / "claude.yaml"
        assert persona_file.exists()

    def test_import_with_custom_persona(self, runner, helios_dir, claude_md):
        result = runner.invoke(
            main,
            ["import", str(claude_md), "--persona", "mybot",
             "--helios-dir", str(helios_dir)],
        )
        assert result.exit_code == 0
        assert "mybot" in result.output
        assert (helios_dir / "personas" / "mybot.yaml").exists()

    def test_import_with_explicit_format(self, runner, helios_dir, claude_md):
        result = runner.invoke(
            main,
            ["import", str(claude_md), "--format", "claude",
             "--helios-dir", str(helios_dir)],
        )
        assert result.exit_code == 0

    def test_import_soul_md(self, runner, helios_dir, soul_md):
        result = runner.invoke(
            main,
            ["import", str(soul_md), "--helios-dir", str(helios_dir)],
        )
        assert result.exit_code == 0
        assert (helios_dir / "personas" / "soul.yaml").exists()

    def test_import_shows_distributions(self, runner, helios_dir, claude_md):
        result = runner.invoke(
            main,
            ["import", str(claude_md), "--helios-dir", str(helios_dir)],
        )
        assert "epistemic_style" in result.output
        assert "interaction_agency" in result.output
        assert "communication_register" in result.output
        assert "risk_caution" in result.output

    def test_import_nonexistent_file(self, runner, helios_dir, tmp_path):
        result = runner.invoke(
            main,
            ["import", str(tmp_path / "nope.md"), "--helios-dir", str(helios_dir)],
        )
        # Click validates path exists before invoking
        assert result.exit_code != 0

    def test_import_generic_md(self, runner, helios_dir, tmp_path):
        md = tmp_path / "config.md"
        md.write_text("Be cautious and verify everything before acting.")
        result = runner.invoke(
            main,
            ["import", str(md), "--helios-dir", str(helios_dir)],
        )
        assert result.exit_code == 0
