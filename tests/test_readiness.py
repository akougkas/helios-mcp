"""End-to-end readiness tests for Helios plugin deployment.

Simulates a realistic Claude Code session: bootstrap, hook events fire,
observations accumulate, drift detection runs. Validates the full pipeline
from hook-handler.py through to the behavioral observer.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from helios_mcp.cli import main

HANDLER = Path(__file__).parent.parent / "helios-plugin" / "hooks" / "hook-handler.py"
PLUGIN_DIR = Path(__file__).parent.parent / "helios-plugin"


def _run_handler(event_type: str, stdin_data: dict, helios_dir: Path) -> None:
    env = os.environ.copy()
    env["HELIOS_DIR"] = str(helios_dir)
    subprocess.run(
        [sys.executable, str(HANDLER), event_type],
        input=json.dumps(stdin_data),
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )


class TestSessionSimulation:
    """Simulate a realistic Claude Code session with multiple hook events."""

    @pytest.fixture
    def session_dir(self, tmp_path):
        """Create a helios dir and simulate a full session of hook events."""
        helios_dir = tmp_path / "helios"

        session_common = {
            "session_id": "sim-session-001",
            "transcript_path": "/tmp/sim-transcript.jsonl",
            "cwd": "/home/user/myproject",
            "permission_mode": "default",
        }

        # Session start
        _run_handler("session-start", {**session_common, "source": "startup"}, helios_dir)

        # User prompt
        _run_handler("prompt-submit", {
            **session_common,
            "prompt": "Fix the login bug in auth.py",
        }, helios_dir)

        # Agent reads files (cautious pattern)
        for f in ["auth.py", "tests/test_auth.py", "config.py"]:
            _run_handler("post-tool", {
                **session_common,
                "tool_name": "Read",
                "tool_input": {"file_path": f},
            }, helios_dir)

        # Agent searches
        _run_handler("post-tool", {
            **session_common,
            "tool_name": "Grep",
            "tool_input": {"pattern": "login", "path": "src/"},
        }, helios_dir)

        # Agent edits
        _run_handler("post-tool", {
            **session_common,
            "tool_name": "Edit",
            "tool_input": {"file_path": "auth.py", "old_string": "x", "new_string": "y"},
        }, helios_dir)

        # Agent runs tests
        _run_handler("post-tool", {
            **session_common,
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/test_auth.py"},
        }, helios_dir)

        # Test fails
        _run_handler("post-tool-failure", {
            **session_common,
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/test_auth.py"},
        }, helios_dir)

        # Agent spawns a subagent to explore
        _run_handler("subagent-start", {
            **session_common,
            "agent_type": "Explore",
        }, helios_dir)
        _run_handler("subagent-stop", {
            **session_common,
            "agent_type": "Explore",
        }, helios_dir)

        # Agent fixes and retests
        _run_handler("post-tool", {
            **session_common,
            "tool_name": "Edit",
            "tool_input": {"file_path": "auth.py", "old_string": "a", "new_string": "b"},
        }, helios_dir)
        _run_handler("post-tool", {
            **session_common,
            "tool_name": "Bash",
            "tool_input": {"command": "pytest tests/"},
        }, helios_dir)

        # Notification
        _run_handler("notification", {
            **session_common,
            "content": "All tests passing",
        }, helios_dir)

        # Stop
        _run_handler("stop", {
            **session_common,
            "stop_hook_active": False,
        }, helios_dir)

        # Session end
        _run_handler("session-end", {
            **session_common,
            "reason": "prompt_input_exit",
        }, helios_dir)

        return helios_dir

    def test_observations_recorded(self, session_dir):
        obs_file = session_dir / "observations" / "hooks" / "default.jsonl"
        assert obs_file.exists()
        lines = obs_file.read_text().strip().splitlines()
        # session-start + prompt + 4 reads + grep + 2 edits + 2 bash + failure
        # + subagent-start + subagent-stop + notification + stop + session-end
        assert len(lines) >= 15

    def test_all_records_have_session_id(self, session_dir):
        obs_file = session_dir / "observations" / "hooks" / "default.jsonl"
        for line_str in obs_file.read_text().strip().splitlines():
            record = json.loads(line_str)
            assert record["session_id"] == "sim-session-001"

    def test_all_records_have_cwd(self, session_dir):
        obs_file = session_dir / "observations" / "hooks" / "default.jsonl"
        for line_str in obs_file.read_text().strip().splitlines():
            record = json.loads(line_str)
            assert record["cwd"] == "/home/user/myproject"

    def test_event_type_diversity(self, session_dir):
        obs_file = session_dir / "observations" / "hooks" / "default.jsonl"
        event_types = set()
        for line_str in obs_file.read_text().strip().splitlines():
            record = json.loads(line_str)
            event_types.add(record["event_type"])
        expected = {
            "session-start", "session-end", "prompt-submit",
            "post-tool", "post-tool-failure",
            "subagent-start", "subagent-stop",
            "notification", "stop",
        }
        assert expected.issubset(event_types)

    def test_tool_events_have_no_raw_content(self, session_dir):
        """Capture stores derived features only — never the raw hook
        envelope. This replaces a prior version of this test that
        round-tripped stored records through parse_hook_stdin(record["data"],
        ...): that depended on hook-handler.py persisting the full raw
        stdin payload, which was the privacy bug P2 removed. The
        replay-from-hook-JSONL pipeline (hook_events.parse_hook_stdin,
        hook_observer.py) is being superseded by ingest.py reading the
        session transcript directly, per the sprint's target architecture."""
        obs_file = session_dir / "observations" / "hooks" / "default.jsonl"
        records = [
            json.loads(line) for line in obs_file.read_text().strip().splitlines()
        ]
        assert len(records) >= 15
        for record in records:
            assert "data" not in record
            assert "tool_input" not in record
            assert "prompt" not in record

    def test_bash_tool_events_classified(self, session_dir):
        obs_file = session_dir / "observations" / "hooks" / "default.jsonl"
        bash_records = [
            json.loads(line)
            for line in obs_file.read_text().strip().splitlines()
            if json.loads(line).get("tool_name") == "Bash"
        ]
        assert len(bash_records) >= 2
        assert all(r["command_kind"] == "test" for r in bash_records)
        assert all(r["is_test_command"] for r in bash_records)

    def test_failure_event_marks_success_false(self, session_dir):
        obs_file = session_dir / "observations" / "hooks" / "default.jsonl"
        failure_records = [
            json.loads(line)
            for line in obs_file.read_text().strip().splitlines()
            if json.loads(line)["event_type"] == "post-tool-failure"
        ]
        assert len(failure_records) >= 1
        assert all(r["success"] is False for r in failure_records)


class TestPluginInstallReadiness:
    """Validate the plugin directory is ready for Claude Code installation."""

    def test_plugin_json_valid(self):
        path = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
        manifest = json.loads(path.read_text())
        required_keys = {"name", "version", "description"}
        assert required_keys.issubset(set(manifest.keys()))
        # Convention-based discovery: these fields must NOT be in the manifest
        assert "skills" not in manifest
        assert "agents" not in manifest
        assert "hooks" not in manifest
        assert "mcpServers" not in manifest

    def test_hooks_json_valid(self):
        path = PLUGIN_DIR / "hooks" / "hooks.json"
        config = json.loads(path.read_text())
        assert "hooks" in config
        for _event_type, entries in config["hooks"].items():
            for entry in entries:
                for hook in entry["hooks"]:
                    assert hook["type"] == "command"
                    # Every capture hook (calls hook-handler.py) must be
                    # async/non-blocking. The one documented exception is
                    # the SessionStart context-injection hook, which has
                    # to be synchronous for Claude Code to read its stdout.
                    if "hook-handler.py" in hook["command"]:
                        assert hook.get("async") is True

    def test_mcp_json_valid(self):
        path = PLUGIN_DIR / ".mcp.json"
        config = json.loads(path.read_text())
        server = config["helios"]
        assert server["command"] == "uvx"

    def test_skill_has_frontmatter(self):
        content = (PLUGIN_DIR / "skills" / "helios" / "SKILL.md").read_text()
        assert content.startswith("---\n")
        assert "name: helios" in content
        assert "description:" in content
        assert "user-invocable: true" in content

    def test_hook_scripts_have_no_helios_mcp_dependency(self):
        """Every hooks/*.py script must run under a bare python3 that may
        not have helios_mcp installed, so none of them may import it —
        checked via ast rather than a substring search, since a substring
        check false-positives on any script whose comments or docstrings
        merely mention helios_mcp.security (as hook-handler.py's does, to
        explain why it doesn't import it)."""
        import ast

        for script in (PLUGIN_DIR / "hooks").glob("*.py"):
            tree = ast.parse(script.read_text(), filename=str(script))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name.split(".")[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom):
                    names = {(node.module or "").split(".")[0]}
                else:
                    continue
                assert "helios_mcp" not in names, (
                    f"{script.name} imports helios_mcp: {ast.dump(node)}"
                )


class TestStandaloneSkillReadiness:
    """Validate the standalone skill package."""

    SKILL_DIR = Path(__file__).parent.parent / "helios-skill"

    def test_skill_md_has_frontmatter(self):
        content = (self.SKILL_DIR / "SKILL.md").read_text()
        assert content.startswith("---\n")
        assert "name: helios" in content

    def test_mcp_json_has_server(self):
        config = json.loads((self.SKILL_DIR / ".mcp.json").read_text())
        assert config["helios"]["command"] == "uvx"

    def test_skill_matches_plugin(self):
        plugin_skill = (PLUGIN_DIR / "skills" / "helios" / "SKILL.md").read_text()
        standalone_skill = (self.SKILL_DIR / "SKILL.md").read_text()
        assert plugin_skill == standalone_skill

    def test_mcp_matches_plugin(self):
        plugin_mcp = (PLUGIN_DIR / ".mcp.json").read_text()
        standalone_mcp = (self.SKILL_DIR / ".mcp.json").read_text()
        assert plugin_mcp == standalone_mcp


class TestCLIBootstrapAndStatus:
    """Validate CLI commands work correctly for fresh installs."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    def test_status_no_bootstrap(self, runner, tmp_path):
        helios_dir = tmp_path / "helios"
        helios_dir.mkdir()
        result = runner.invoke(main, ["status", "--helios-dir", str(helios_dir)])
        assert result.exit_code == 0
        # Any command on a fresh directory bootstraps it.
        assert "developer: 0 turns" in result.output

    def test_negotiate_no_observations(self, runner, tmp_path):
        helios_dir = tmp_path / "helios"
        helios_dir.mkdir()
        (helios_dir / "base").mkdir()
        result = runner.invoke(main, ["negotiate", "developer", "--helios-dir", str(helios_dir)])
        assert result.exit_code == 0
        assert "over 0 observed turns" in result.output
