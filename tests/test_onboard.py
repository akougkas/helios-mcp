"""`helios-mcp init` onboarding: import CLAUDE.md into a persona's user level."""

import pytest
from click.testing import CliRunner

from helios_mcp.cli import main
from helios_mcp.hierarchy import IdentityHierarchy
from helios_mcp.onboard import onboard
from helios_mcp.profile import BehavioralProfile
from helios_mcp.service import HeliosService

CLAUDE_MD = "# CLAUDE.md\n\n## Style\n\nBe terse and direct. Verify before acting.\n"


def _write_source(tmp_path, text=CLAUDE_MD):
    source = tmp_path / "CLAUDE.md"
    source.write_text(text, encoding="utf-8")
    return source


def test_onboard_defaults_to_developer_and_sets_it_default(tmp_path):
    helios_dir = tmp_path / ".helios"
    source = _write_source(tmp_path)
    service = HeliosService(helios_dir)

    result = onboard(service, source=source)

    assert result["persona"] == "developer"
    assert service.persona(None) == "developer"
    path = helios_dir / "personas" / "developer_user.yaml"
    assert path.exists()
    profile = BehavioralProfile.load(path)
    assert profile.inherit_weight == 0.0
    assert profile.level == "user"
    assert profile.parent_id == "developer"
    assert set(result["distributions"]) == set(profile.distributions)


def test_onboard_is_authoritative_on_resolve(tmp_path):
    helios_dir = tmp_path / ".helios"
    source = _write_source(tmp_path)
    service = HeliosService(helios_dir)
    onboard(service, source=source)

    resolved = IdentityHierarchy(helios_dir).resolve("developer")
    on_disk = BehavioralProfile.load(helios_dir / "personas" / "developer_user.yaml")
    for dim, dist in on_disk.distributions.items():
        for state, prob in zip(dist.states, dist.probs, strict=True):
            i = resolved.distributions[dim].states.index(state)
            assert resolved.distributions[dim].probs[i] == pytest.approx(prob)


def test_onboard_rerun_overwrites_without_duplicating(tmp_path):
    helios_dir = tmp_path / ".helios"
    source = _write_source(tmp_path)
    service = HeliosService(helios_dir)

    onboard(service, source=source)
    _write_source(tmp_path, CLAUDE_MD + "\nAlways ask before acting.\n")
    onboard(service, source=source)

    personas_dir = helios_dir / "personas"
    assert sorted(p.name for p in personas_dir.glob("developer_user*")) == \
        ["developer_user.yaml"]


def test_onboard_explicit_persona_overrides_default(tmp_path):
    helios_dir = tmp_path / ".helios"
    source = _write_source(tmp_path)
    service = HeliosService(helios_dir)

    result = onboard(service, persona="writer", source=source)

    assert result["persona"] == "writer"
    assert service.persona(None) == "writer"
    assert (helios_dir / "personas" / "writer_user.yaml").exists()
    assert not (helios_dir / "personas" / "developer_user.yaml").exists()


def test_onboard_missing_source_raises(tmp_path):
    helios_dir = tmp_path / ".helios"
    service = HeliosService(helios_dir)
    missing = tmp_path / "nope.md"

    try:
        onboard(service, source=missing)
    except FileNotFoundError as e:
        assert str(missing) in str(e)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_init_cli_end_to_end(tmp_path):
    helios_dir = tmp_path / ".helios"
    source = _write_source(tmp_path)
    runner = CliRunner()

    result = runner.invoke(main, ["--helios-dir", str(helios_dir), "init",
                                  "--source", str(source)])

    assert result.exit_code == 0, result.output
    assert "Persona: developer (default)" in result.output
    assert (helios_dir / "personas" / "developer_user.yaml").exists()
    assert (helios_dir / "rendered" / "developer.md").exists()


def test_init_cli_reports_missing_source(tmp_path):
    helios_dir = tmp_path / ".helios"
    runner = CliRunner()

    result = runner.invoke(main, ["--helios-dir", str(helios_dir), "init",
                                  "--source", str(tmp_path / "nope.md")])

    assert result.exit_code != 0
    assert "no personality file at" in result.output
