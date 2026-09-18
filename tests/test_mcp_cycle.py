"""End-to-end MCP protocol cycle through a real in-memory fastmcp.Client.

Every call here goes through the actual MCP tool-call wire shape (arguments
as a plain dict in, a CallToolResult out), not HeliosService directly, so a
gap between what server.py exposes and what service.py actually does would
show up here even if each side's own unit tests pass. server.py and
service.py are core's files; defects found here get reported to core as
BUGs rather than fixed in this repo.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client

from helios_mcp.server import create_server

# A reply the heuristic classifier reads as thorough/verbose, paired with a
# correction endorsement.py maps straight to communication_register=terse
# (the same "too long, be terse" pattern T1's lab driver scripts).
VERBOSE_REPLY = (
    "Let me walk you through this in detail. First, I'll explain the background "
    "context, then the reasoning, then the implementation approach, then caveats, "
    "then alternatives, then a summary of everything discussed so far in depth."
)
TERSE_CORRECTION = "too long, be terse"

# Empirically converges in 6-12 turns against the current calibration
# (C8: prior strength 25, JS threshold 0.0125). Generous headroom so a
# future recalibration doesn't make this test flaky.
MAX_CORRECTION_TURNS = 25

TRAVERSAL_PERSONA_NAMES = ["../../etc/passwd", "..", ".", "a/b", "~root"]


async def _client(helios_dir: Path) -> Client:
    server = await create_server(helios_dir)
    return Client(server)


def _turn(assistant_text: str, user_text: str) -> list[dict[str, str]]:
    return [
        {"role": "assistant", "content": assistant_text},
        {"role": "user", "content": user_text},
    ]


async def _drive_to_proposal(
    client: Client, persona: str, session_id: str
) -> tuple[str, list[dict[str, str]]]:
    """Send scripted correction turns until observe_interaction reports a
    proposal, or fail the test if it never does within MAX_CORRECTION_TURNS."""
    messages: list[dict[str, str]] = []
    for _ in range(MAX_CORRECTION_TURNS):
        messages += _turn(VERBOSE_REPLY, TERSE_CORRECTION)
        result = await client.call_tool(
            "observe_interaction",
            {"messages": messages, "persona_name": persona, "session_id": session_id},
        )
        sc = result.structured_content
        assert sc["status"] == "success", sc
        if sc["proposal_id"]:
            return sc["proposal_id"], messages
    pytest.fail(
        f"no proposal after {MAX_CORRECTION_TURNS} corrected turns for {persona!r}"
    )


class TestFullMCPCycle:
    """The happy-path cycle: list -> observe -> drift report -> accept ->
    context reflects the accepted target -> export -> import."""

    async def test_full_cycle_accept(self, tmp_path):
        helios_dir = tmp_path / "helios"
        async with await _client(helios_dir) as client:
            personas = (await client.call_tool("list_personas", {})).structured_content
            assert personas["status"] == "success"
            assert "developer" in personas["personas"]

            proposal_id, _ = await _drive_to_proposal(client, "developer", "cycle-accept")

            report = (
                await client.call_tool("get_drift_report", {"persona_name": "developer"})
            ).structured_content
            assert report["status"] == "success"
            assert report["proposal_id"] == proposal_id
            assert "communication_register" in report["per_dimension"]
            assert "communication_register" in report["endorsed"]

            accepted = (
                await client.call_tool(
                    "negotiate_update",
                    {
                        "proposal_id": proposal_id,
                        "decision": "accept",
                        "persona_name": "developer",
                    },
                )
            ).structured_content
            assert accepted["status"] == "success"
            assert accepted["decision"] == "accepted"
            assert "communication_register" in accepted["dimensions"]
            assert accepted["commit"], "accept must git-commit the profile change"

            context = (
                await client.call_tool(
                    "get_behavioral_context", {"persona_name": "developer"}
                )
            ).structured_content
            assert context["status"] == "success"
            # The renderer describes the "terse" state in prose ("be
            # concise: minimal words, maximum information density") rather
            # than printing the state name, so check the rendered text
            # loosely here and confirm the actual target precisely below,
            # via export_profile's structured dominant state.
            assert "concise" in context["behavioral_context"].lower()

            exported_check = (
                await client.call_tool(
                    "export_profile", {"persona_name": "developer", "format": "json"}
                )
            ).structured_content
            assert exported_check["status"] == "success"
            register = exported_check["dimensions"]["communication_register"]
            assert register["dominant_state"] == "terse", register

            # A second drift report on the same ledger must not re-propose
            # the dimension just accepted: the resolved profile now equals
            # the target, so there's nothing left to drift toward.
            settled = (
                await client.call_tool("get_drift_report", {"persona_name": "developer"})
            ).structured_content
            assert settled["status"] == "success"
            assert settled["proposal_id"] is None
            assert settled["negotiation_recommended"] is False

            exported = (
                await client.call_tool(
                    "export_profile",
                    {"persona_name": "developer", "format": "soulspec"},
                )
            ).structured_content
            assert exported["status"] == "success"
            assert exported["content"].startswith("# developer")

            import_dir = tmp_path / "import_src"
            import_dir.mkdir()
            soul_file = import_dir / "soul.md"
            soul_file.write_text(exported["content"])
            imported = (
                await client.call_tool(
                    "import_profile",
                    {
                        "source_path": str(soul_file),
                        "persona_name": "developer-clone",
                    },
                )
            ).structured_content
            assert imported["status"] == "success"
            assert imported["persona"] == "developer-clone"
            assert set(imported["distributions"]) == {
                "epistemic_style",
                "interaction_agency",
                "communication_register",
                "risk_caution",
            }
            assert (helios_dir / "personas" / "developer-clone.yaml").is_file()


class TestRejectPathAndCooldown:
    async def test_reject_records_decision_and_suppresses_reproposal(self, tmp_path):
        helios_dir = tmp_path / "helios"
        async with await _client(helios_dir) as client:
            proposal_id, _ = await _drive_to_proposal(
                client, "researcher", "cycle-reject"
            )

            rejected = (
                await client.call_tool(
                    "negotiate_update",
                    {
                        "proposal_id": proposal_id,
                        "decision": "reject",
                        "persona_name": "researcher",
                        "reason": "test rejection",
                    },
                )
            ).structured_content
            assert rejected["status"] == "success"
            assert rejected["decision"] == "rejected"
            assert rejected["reason"] == "test rejection"
            assert "communication_register" in rejected["dimensions"]

            # Re-evaluating the same ledger right after a reject must not
            # immediately produce a new proposal for the rejected
            # dimension. Whether that's a time-based cooldown or the
            # rejection's pseudo-counts pulling the posterior back toward
            # declared is an implementation detail; what must hold is that
            # rejecting doesn't just get silently overridden next call.
            after = (
                await client.call_tool(
                    "get_drift_report", {"persona_name": "researcher"}
                )
            ).structured_content
            assert after["status"] == "success"
            assert after["negotiation_recommended"] is False
            assert after["proposal_id"] is None

    async def test_unknown_proposal_id_errors_cleanly(self, tmp_path):
        helios_dir = tmp_path / "helios"
        async with await _client(helios_dir) as client:
            result = await client.call_tool(
                "negotiate_update",
                {
                    "proposal_id": "does-not-exist",
                    "decision": "accept",
                    "persona_name": "developer",
                },
            )
            sc = result.structured_content
            assert sc["status"] == "error"
            assert sc["message"]

    async def test_unknown_decision_errors_cleanly(self, tmp_path):
        helios_dir = tmp_path / "helios"
        async with await _client(helios_dir) as client:
            result = await client.call_tool(
                "negotiate_update",
                {
                    "proposal_id": "irrelevant",
                    "decision": "maybe",
                    "persona_name": "developer",
                },
            )
            sc = result.structured_content
            assert sc["status"] == "error"


class TestPathTraversalPersonaNames:
    """Every tool that accepts a persona_name must reject a traversal
    attempt cleanly (status: error) and must never write outside
    helios_dir while doing it."""

    @pytest.fixture
    async def sandboxed_client(self, tmp_path):
        helios_dir = tmp_path / "helios"
        async with await _client(helios_dir) as client:
            yield client, helios_dir, tmp_path

    @staticmethod
    def _assert_contained(tmp_path: Path, helios_dir: Path) -> None:
        """Every file under tmp_path must be inside helios_dir (or the
        fixed import_src scratch dir this class never uses), proving a
        malicious persona_name never escaped HELIOS_DIR."""
        for p in tmp_path.rglob("*"):
            if p.is_file():
                assert p.is_relative_to(helios_dir), f"escaped write: {p}"

    @pytest.mark.parametrize("bad_name", TRAVERSAL_PERSONA_NAMES)
    async def test_get_behavioral_context(self, sandboxed_client, bad_name):
        client, helios_dir, tmp_path = sandboxed_client
        result = await client.call_tool(
            "get_behavioral_context", {"persona_name": bad_name}
        )
        assert result.structured_content["status"] == "error"
        self._assert_contained(tmp_path, helios_dir)

    @pytest.mark.parametrize("bad_name", TRAVERSAL_PERSONA_NAMES)
    async def test_observe_interaction(self, sandboxed_client, bad_name):
        client, helios_dir, tmp_path = sandboxed_client
        result = await client.call_tool(
            "observe_interaction",
            {
                "messages": [{"role": "user", "content": "hello"}],
                "persona_name": bad_name,
            },
        )
        assert result.structured_content["status"] == "error"
        self._assert_contained(tmp_path, helios_dir)

    @pytest.mark.parametrize("bad_name", TRAVERSAL_PERSONA_NAMES)
    async def test_get_drift_report(self, sandboxed_client, bad_name):
        client, helios_dir, tmp_path = sandboxed_client
        result = await client.call_tool(
            "get_drift_report", {"persona_name": bad_name}
        )
        assert result.structured_content["status"] == "error"
        self._assert_contained(tmp_path, helios_dir)

    @pytest.mark.parametrize("bad_name", TRAVERSAL_PERSONA_NAMES)
    async def test_negotiate_update(self, sandboxed_client, bad_name):
        client, helios_dir, tmp_path = sandboxed_client
        result = await client.call_tool(
            "negotiate_update",
            {"proposal_id": "x", "decision": "accept", "persona_name": bad_name},
        )
        assert result.structured_content["status"] == "error"
        self._assert_contained(tmp_path, helios_dir)

    @pytest.mark.parametrize("bad_name", TRAVERSAL_PERSONA_NAMES)
    async def test_export_profile(self, sandboxed_client, bad_name):
        client, helios_dir, tmp_path = sandboxed_client
        result = await client.call_tool(
            "export_profile", {"persona_name": bad_name}
        )
        assert result.structured_content["status"] == "error"
        self._assert_contained(tmp_path, helios_dir)

    @pytest.mark.parametrize("bad_name", TRAVERSAL_PERSONA_NAMES)
    async def test_import_profile(self, sandboxed_client, bad_name):
        client, helios_dir, tmp_path = sandboxed_client
        source_dir = tmp_path / "import_src"
        source_dir.mkdir(exist_ok=True)
        source_file = source_dir / f"src-{abs(hash(bad_name))}.md"
        source_file.write_text("# a persona\n\nDirect and confident.\n")
        result = await client.call_tool(
            "import_profile",
            {"source_path": str(source_file), "persona_name": bad_name},
        )
        assert result.structured_content["status"] == "error"
        # import_profile legitimately writes outside helios_dir (the
        # source file the test itself just planted), so contain the check
        # to helios_dir's own subtree rather than reusing _assert_contained.
        for p in helios_dir.rglob("*"):
            if p.is_file():
                assert "etc" not in p.parts and "passwd" not in p.name

    async def test_empty_persona_name_falls_back_to_default(self, sandboxed_client):
        """Not a traversal case, but the boundary right next to it: an
        empty string must resolve to the configured default, not error."""
        client, _helios_dir, _tmp_path = sandboxed_client
        result = await client.call_tool("get_behavioral_context", {"persona_name": ""})
        sc = result.structured_content
        assert sc["status"] == "success"
        assert sc["persona"] == "default"
