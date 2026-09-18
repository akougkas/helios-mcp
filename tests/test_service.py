"""The engine through its two front doors: MCP tools and the CLI."""

from dataclasses import replace

import pytest
from click.testing import CliRunner
from fastmcp import Client

from helios_mcp.cli import main
from helios_mcp.security import SecurityError
from helios_mcp.server import create_server
from helios_mcp.service import HeliosService
from helios_mcp.store import TurnObservation

DIM = "communication_register"


def terse_turns(n, persona="developer"):
    return [TurnObservation(persona=persona, session_id="s", turn_id=f"t{i}",
                            timestamp=float(i), source="heuristic",
                            labels={DIM: {"terse": 0.8, "moderate": 0.2}},
                            endorsement=1.0)
            for i in range(n)]


async def call(client, tool, **args):
    result = await client.call_tool(tool, args)
    return result.structured_content


async def test_mcp_cycle_proposes_accepts_converges_and_renders(tmp_path):
    mcp = await create_server(tmp_path)
    HeliosService(tmp_path).record(terse_turns(60), "developer")
    rendered = tmp_path / "rendered" / "developer.md"
    before = rendered.read_text()

    async with Client(mcp) as client:
        report = await call(client, "get_drift_report", persona_name="developer")
        assert report["status"] == "success"
        assert report["negotiation_recommended"]
        assert DIM in report["endorsed"] and DIM in report["fingerprint"]
        pid = report["proposal_id"]

        # Reading the report twice keeps the same proposal.
        again = await call(client, "get_drift_report", persona_name="developer")
        assert again["proposal_id"] == pid

        decided = await call(client, "negotiate_update", persona_name="developer",
                             proposal_id=pid, decision="accept")
        assert decided["decision"] == "accepted" and decided["commit"]

        after = await call(client, "get_drift_report", persona_name="developer")
        assert not after["negotiation_recommended"]
        assert after["proposal_id"] is None

        stale = await call(client, "negotiate_update", persona_name="developer",
                           proposal_id=pid, decision="reject")
        assert stale["status"] == "error"

    assert rendered.read_text() != before


@pytest.mark.parametrize("tool,args", [
    ("get_behavioral_context", {}),
    ("get_drift_report", {}),
    ("export_profile", {}),
    ("observe_interaction", {"messages": [{"role": "assistant", "content": "x"}]}),
    ("negotiate_update", {"proposal_id": "x", "decision": "accept"}),
])
async def test_every_persona_tool_rejects_traversal(tmp_path, tool, args):
    helios = tmp_path / "helios"
    mcp = await create_server(helios)
    async with Client(mcp) as client:
        result = await call(client, tool, persona_name="../../escape", **args)
    assert result["status"] == "error"
    assert not list(tmp_path.glob("escape*"))
    assert not list(tmp_path.rglob("escape*"))


def test_observation_count_counts_turns_not_label_rows(tmp_path):
    service = HeliosService(tmp_path)
    heuristic = terse_turns(1)[0]
    service.record([heuristic, replace(heuristic, source="llm")], "developer")
    assert service.context("developer")["observation_count"] == 1


def test_cli_group_helios_dir_reaches_subcommands(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["--helios-dir", str(tmp_path), "persona",
                                  "default", "writer"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "default_persona").read_text().strip() == "writer"

    result = runner.invoke(main, ["--helios-dir", str(tmp_path), "render"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "rendered" / "writer.md").exists()

    bad = runner.invoke(main, ["--helios-dir", str(tmp_path), "persona",
                               "default", "../x"])
    assert bad.exit_code != 0


def test_cli_ingest_of_missing_transcript_is_a_quiet_noop(tmp_path):
    result = CliRunner().invoke(main, [
        "ingest", "--persona", "developer", "--session-id", "s",
        "--transcript", str(tmp_path / "nope.jsonl"), "--helios-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert result.output == ""


def test_rendered_context_counters_each_models_own_tendencies(tmp_path):
    service = HeliosService(tmp_path)
    bullets = {"structure": {"heavy_structure": 1.0}}
    declared = service.negotiator.declared("developer")["structure"]
    turns = [TurnObservation(persona="developer", session_id="s", turn_id=f"a{i}",
                             timestamp=float(i), source="heuristic", labels=bullets,
                             model="model-a")
             for i in range(40)]
    turns += [TurnObservation(persona="developer", session_id="s", turn_id=f"b{i}",
                              timestamp=float(i), source="heuristic",
                              labels={"structure": declared}, model="model-b")
              for i in range(60)]
    service.record(turns, "developer")

    # The fingerprint is diagnostics only: nothing here is endorsed evidence.
    assert service.drift_report("developer")["proposal_id"] is None
    rendered = (tmp_path / "rendered" / "developer.md").read_text()
    assert "If you are model-a:" in rendered
    assert "headers and bullet points" in rendered
    assert "model-b" not in rendered
    assert "If you are model-a:" in service.context("developer", "model-a")[
        "behavioral_context"]
    assert "model-a" not in service.context("developer", "model-b")[
        "behavioral_context"]
    printed = CliRunner().invoke(main, ["--helios-dir", str(tmp_path), "render",
                                        "developer", "--model", "model-a"])
    assert "Tendencies to counter" in printed.output


def test_import_validates_the_persona_before_reading_the_source(tmp_path):
    service = HeliosService(tmp_path)
    with pytest.raises(SecurityError):
        service.import_profile(tmp_path / "missing.md", "../escape")


def test_cli_status_shows_the_observed_posterior_next_to_the_declared(tmp_path):
    HeliosService(tmp_path).record(terse_turns(60), "developer")
    result = CliRunner().invoke(main, ["--helios-dir", str(tmp_path), "status"])
    assert result.exit_code == 0, result.output
    line = next(ln for ln in result.output.splitlines() if DIM in ln)
    assert "declared moderate" in line
    assert "-> observed terse" in line
    assert "strong" in line


def test_cli_negotiate_accepts_pending_proposal(tmp_path):
    HeliosService(tmp_path).record(terse_turns(60), "developer")
    runner = CliRunner()
    result = runner.invoke(main, ["--helios-dir", str(tmp_path), "negotiate",
                                  "developer", "--yes"])
    assert result.exit_code == 0, result.output
    assert "Accepted communication_register" in result.output
    again = runner.invoke(main, ["--helios-dir", str(tmp_path), "negotiate",
                                 "developer"])
    assert "No credible drift" in again.output
