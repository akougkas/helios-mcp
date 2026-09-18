"""`helios-mcp init` onboarding: import declared sources into a persona's
user level."""

import pytest
from click.testing import CliRunner

from helios_mcp.cli import main
from helios_mcp.hierarchy import IdentityHierarchy
from helios_mcp.onboard import onboard
from helios_mcp.profile import BehavioralProfile
from helios_mcp.service import HeliosService
from helios_mcp.store import TurnObservation

CLAUDE_MD = "# CLAUDE.md\n\n## Style\n\nBe terse and direct. Verify before acting.\n"


def _home(tmp_path, text=CLAUDE_MD):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    (home / "CLAUDE.md").write_text(text, encoding="utf-8")
    return home


def test_onboard_defaults_to_developer_and_sets_it_default(tmp_path):
    helios_dir = tmp_path / ".helios"
    home = _home(tmp_path)
    service = HeliosService(helios_dir)

    result = onboard(service, home=home)

    assert result["persona"] == "developer"
    assert service.persona(None) == "developer"
    path = helios_dir / "personas" / "developer_user.yaml"
    assert path.exists()
    profile = BehavioralProfile.load(path)
    assert profile.inherit_weight == 0.0
    assert profile.level == "user"
    assert profile.parent_id == "developer"
    assert set(result["distributions"]) == set(profile.distributions)
    assert result["sources"] == [str(home / "CLAUDE.md")]


def test_onboard_is_authoritative_on_resolve(tmp_path):
    helios_dir = tmp_path / ".helios"
    home = _home(tmp_path)
    service = HeliosService(helios_dir)
    onboard(service, home=home)

    resolved = IdentityHierarchy(helios_dir).resolve("developer")
    on_disk = BehavioralProfile.load(helios_dir / "personas" / "developer_user.yaml")
    for dim, dist in on_disk.distributions.items():
        for state, prob in zip(dist.states, dist.probs, strict=True):
            i = resolved.distributions[dim].states.index(state)
            assert resolved.distributions[dim].probs[i] == pytest.approx(prob)


def test_onboard_rerun_overwrites_without_duplicating(tmp_path):
    helios_dir = tmp_path / ".helios"
    home = _home(tmp_path)
    service = HeliosService(helios_dir)

    onboard(service, home=home)
    (home / "CLAUDE.md").write_text(CLAUDE_MD + "\nAlways ask before acting.\n")
    onboard(service, home=home)

    personas_dir = helios_dir / "personas"
    assert sorted(p.name for p in personas_dir.glob("developer_user*")) == \
        ["developer_user.yaml"]


def test_onboard_rerun_keeps_accepted_dimensions(tmp_path, monkeypatch):
    monkeypatch.setenv("HELIOS_LLM", "0")
    service = HeliosService(tmp_path / ".helios")
    home = _home(tmp_path, "Be thorough and explain your reasoning in detail.\n")
    onboard(service, home=home)
    dim = "communication_register"
    service.ledger.append(
        TurnObservation("developer", "s", f"t{i}", float(i), "heuristic",
                        {dim: {"terse": 1.0}}, endorsement=1.0)
        for i in range(120))
    service.accept("developer", service.drift_report("developer")["proposal_id"])
    accepted = service.negotiator.declared("developer")

    result = onboard(service, home=home)
    assert result["kept_accepted"] == [dim]
    after = service.negotiator.declared("developer")
    assert after[dim] == pytest.approx(accepted[dim])
    assert after[dim]["terse"] > 0.5


def test_onboard_marks_the_dimensions_its_text_addressed(tmp_path, monkeypatch):
    monkeypatch.setenv("HELIOS_LLM", "0")
    helios_dir = tmp_path / ".helios"
    result = onboard(HeliosService(helios_dir), home=_home(tmp_path))
    declared = result["declared_dimensions"]
    assert "communication_register" in declared
    assert "sycophancy" not in declared  # the text says nothing about it

    status = CliRunner().invoke(main, ["--helios-dir", str(helios_dir), "status"])
    block = status.output.split("\ndeveloper:")[1].split("\n\n")[0]
    lines = {line.split()[0]: line for line in block.splitlines()
             if line.startswith("  ")}
    assert "explicit signals only" in lines["communication_register"]
    assert "explicit signals only" not in lines["sycophancy"]


def test_onboard_includes_active_output_style(tmp_path):
    import json

    helios_dir = tmp_path / ".helios"
    home = _home(tmp_path)
    (home / "output-styles").mkdir()
    (home / "output-styles" / "peer-engineer.md").write_text(
        "---\nname: Peer Engineer\ndescription: Prose over structure.\n---\n"
        "\n## Voice\n\nSay the thing. No flattery, no recaps.\n"
    )
    (home / "settings.json").write_text(json.dumps({"outputStyle": "Peer Engineer"}))
    service = HeliosService(helios_dir)

    result = onboard(service, home=home)

    assert result["sources"] == [
        str(home / "CLAUDE.md"), str(home / "output-styles" / "peer-engineer.md"),
    ]


def test_onboard_explicit_persona_overrides_default(tmp_path):
    helios_dir = tmp_path / ".helios"
    home = _home(tmp_path)
    service = HeliosService(helios_dir)

    result = onboard(service, persona="writer", home=home)

    assert result["persona"] == "writer"
    assert service.persona(None) == "writer"
    assert (helios_dir / "personas" / "writer_user.yaml").exists()
    assert not (helios_dir / "personas" / "developer_user.yaml").exists()


def test_onboard_missing_sources_raises(tmp_path):
    helios_dir = tmp_path / ".helios"
    service = HeliosService(helios_dir)
    empty_home = tmp_path / "empty_home"
    empty_home.mkdir()

    with pytest.raises(FileNotFoundError, match=str(empty_home)):
        onboard(service, home=empty_home)


def test_init_cli_end_to_end(tmp_path):
    helios_dir = tmp_path / ".helios"
    home = _home(tmp_path)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    runner = CliRunner()

    result = runner.invoke(main, ["--helios-dir", str(helios_dir), "init",
                                  "--home", str(home),
                                  "--project-dir", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert "Persona: developer (default)" in result.output
    assert (helios_dir / "personas" / "developer_user.yaml").exists()
    assert (helios_dir / "rendered" / "developer.md").exists()


def test_init_cli_reports_missing_sources(tmp_path):
    helios_dir = tmp_path / ".helios"
    empty_home = tmp_path / "empty_home"
    empty_home.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    runner = CliRunner()

    result = runner.invoke(main, ["--helios-dir", str(helios_dir), "init",
                                  "--home", str(empty_home),
                                  "--project-dir", str(project_dir)])

    assert result.exit_code != 0
    assert "no declared preferences under" in result.output


def test_config_llm_false_keeps_declared_text_local(tmp_path, monkeypatch):
    # With the env opt-out absent and a claude binary on PATH, only config.yaml
    # stands between the user's CLAUDE.md and the model subprocess.
    import helios_mcp.llm as llm

    monkeypatch.delenv("HELIOS_LLM", raising=False)
    monkeypatch.delenv("HELIOS_DISABLE", raising=False)
    monkeypatch.setattr(llm.shutil, "which", lambda _: "/usr/bin/claude")
    spawned = []
    monkeypatch.setattr(llm.ClaudeCLIClient, "complete_json",
                        lambda self, *a: spawned.append(a))
    helios_dir = tmp_path / ".helios"
    service = HeliosService(helios_dir)
    (helios_dir / "config.yaml").write_text("llm: false\n", encoding="utf-8")

    onboard(service, home=_home(tmp_path))
    service.import_profile(tmp_path / "home" / "CLAUDE.md", name="imported")

    assert spawned == []
