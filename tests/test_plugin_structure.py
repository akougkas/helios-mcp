"""Tests for Claude Code plugin packaging (Tasks 3.1-3.7).

Validates the plugin directory layout, manifest, hooks config,
MCP config, skill definition, and agent definition.
"""

import json
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).parent.parent / "helios-plugin"
SKILL_DIR = Path(__file__).parent.parent / "helios-skill"


# ---------------------------------------------------------------------------
# 3.1 Plugin directory layout
# ---------------------------------------------------------------------------


class TestPluginLayout:
    def test_plugin_dir_exists(self):
        assert PLUGIN_DIR.is_dir()

    def test_claude_plugin_dir(self):
        assert (PLUGIN_DIR / ".claude-plugin").is_dir()

    def test_hooks_dir(self):
        assert (PLUGIN_DIR / "hooks").is_dir()

    def test_skills_dir(self):
        assert (PLUGIN_DIR / "skills" / "helios").is_dir()

    def test_agents_dir(self):
        assert (PLUGIN_DIR / "agents").is_dir()

    def test_mcp_json_exists(self):
        assert (PLUGIN_DIR / ".mcp.json").is_file()


# ---------------------------------------------------------------------------
# 3.2 plugin.json manifest
# ---------------------------------------------------------------------------


class TestPluginManifest:
    @pytest.fixture
    def manifest(self):
        path = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
        return json.loads(path.read_text())

    def test_has_name(self, manifest):
        assert manifest["name"] == "helios"

    def test_has_version(self, manifest):
        assert "version" in manifest

    def test_has_description(self, manifest):
        assert len(manifest["description"]) > 10

    def test_has_keywords(self, manifest):
        kw = manifest["keywords"]
        assert "behavioral" in kw
        assert "personalization" in kw

    def test_has_author(self, manifest):
        assert "author" in manifest
        assert "name" in manifest["author"]

    def test_has_homepage(self, manifest):
        assert "homepage" in manifest

    def test_has_repository(self, manifest):
        assert "repository" in manifest

    def test_has_license(self, manifest):
        assert "license" in manifest

    def test_top_level_skills(self, manifest):
        assert "skills" in manifest
        assert manifest["skills"] == "skills/"

    def test_top_level_agents(self, manifest):
        assert "agents" in manifest
        assert manifest["agents"] == "agents/"

    def test_top_level_hooks(self, manifest):
        assert "hooks" in manifest
        assert manifest["hooks"] == "hooks/hooks.json"

    def test_top_level_mcp_servers(self, manifest):
        assert "mcpServers" in manifest
        assert manifest["mcpServers"] == ".mcp.json"

    def test_no_nested_components(self, manifest):
        assert "components" not in manifest


# ---------------------------------------------------------------------------
# 3.3 hooks.json
# ---------------------------------------------------------------------------


class TestHooksConfig:
    @pytest.fixture
    def hooks(self):
        path = PLUGIN_DIR / "hooks" / "hooks.json"
        return json.loads(path.read_text())

    def test_has_hooks_key(self, hooks):
        assert "hooks" in hooks

    def test_post_tool_use_hook(self, hooks):
        assert "PostToolUse" in hooks["hooks"]
        cmd = hooks["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        assert "helios-mcp hook post-tool" in cmd

    def test_post_tool_use_failure_hook(self, hooks):
        assert "PostToolUseFailure" in hooks["hooks"]
        cmd = hooks["hooks"]["PostToolUseFailure"][0]["hooks"][0]["command"]
        assert "helios-mcp hook post-tool-failure" in cmd

    def test_user_prompt_submit_hook(self, hooks):
        assert "UserPromptSubmit" in hooks["hooks"]
        cmd = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        assert "helios-mcp hook prompt-submit" in cmd

    def test_subagent_start_hook(self, hooks):
        assert "SubagentStart" in hooks["hooks"]

    def test_subagent_stop_hook(self, hooks):
        assert "SubagentStop" in hooks["hooks"]

    def test_stop_hook(self, hooks):
        assert "Stop" in hooks["hooks"]

    def test_session_start_hook(self, hooks):
        assert "SessionStart" in hooks["hooks"]

    def test_session_end_hook(self, hooks):
        assert "SessionEnd" in hooks["hooks"]

    def test_notification_hook(self, hooks):
        assert "Notification" in hooks["hooks"]

    def test_no_pre_tool_blocking(self, hooks):
        """Helios is observe-only. No PreToolUse hooks that could block."""
        assert "PreToolUse" not in hooks["hooks"]

    def test_no_permission_request_blocking(self, hooks):
        """Helios is observe-only. No PermissionRequest hooks."""
        assert "PermissionRequest" not in hooks["hooks"]

    def test_all_hooks_are_command_type(self, hooks):
        for event_type, entries in hooks["hooks"].items():
            for entry in entries:
                for hook in entry["hooks"]:
                    assert hook["type"] == "command"

    def test_all_hooks_are_async(self, hooks):
        """All observation hooks should be async (non-blocking)."""
        for event_type, entries in hooks["hooks"].items():
            for entry in entries:
                for hook in entry["hooks"]:
                    assert hook.get("async") is True, (
                        f"{event_type} hook is not async"
                    )

    def test_hooks_use_plugin_root_variable(self, hooks):
        """Commands should reference ${CLAUDE_PLUGIN_ROOT} for portability."""
        for event_type, entries in hooks["hooks"].items():
            for entry in entries:
                for hook in entry["hooks"]:
                    assert "${CLAUDE_PLUGIN_ROOT}" in hook["command"], (
                        f"{event_type} hook does not use ${{CLAUDE_PLUGIN_ROOT}}"
                    )

    def test_tool_event_matchers_are_regex(self, hooks):
        """Tool-related events should use regex matchers, not empty objects."""
        tool_events = ["PostToolUse", "PostToolUseFailure"]
        for evt in tool_events:
            if evt in hooks["hooks"]:
                matcher = hooks["hooks"][evt][0].get("matcher")
                assert isinstance(matcher, str), (
                    f"{evt} matcher should be a regex string"
                )


# ---------------------------------------------------------------------------
# 3.4 .mcp.json
# ---------------------------------------------------------------------------


class TestMCPConfig:
    @pytest.fixture
    def mcp(self):
        path = PLUGIN_DIR / ".mcp.json"
        return json.loads(path.read_text())

    def test_has_helios_server(self, mcp):
        assert "helios" in mcp["mcpServers"]

    def test_uses_uvx(self, mcp):
        server = mcp["mcpServers"]["helios"]
        assert server["command"] == "uvx"
        assert "helios-mcp" in server["args"]


# ---------------------------------------------------------------------------
# 3.5 SKILL.md
# ---------------------------------------------------------------------------


class TestSkillDefinition:
    @pytest.fixture
    def skill_content(self):
        return (PLUGIN_DIR / "skills" / "helios" / "SKILL.md").read_text()

    def test_has_activation_triggers(self, skill_content):
        assert "/helios" in skill_content
        assert "/helios status" in skill_content
        assert "/helios drift" in skill_content

    def test_has_mcp_tool_guidance(self, skill_content):
        assert "get_behavioral_context" in skill_content
        assert "observe_interaction" in skill_content
        assert "get_drift_report" in skill_content
        assert "negotiate_update" in skill_content

    def test_has_import_export_guidance(self, skill_content):
        assert "import_profile" in skill_content
        assert "export_profile" in skill_content

    def test_has_privacy_statement(self, skill_content):
        assert "local" in skill_content.lower()
        assert "git" in skill_content.lower()

    def test_has_dimension_descriptions(self, skill_content):
        assert "Epistemic Style" in skill_content
        assert "Interaction Agency" in skill_content
        assert "Communication Register" in skill_content
        assert "Risk Caution" in skill_content


# ---------------------------------------------------------------------------
# 3.6 Observer agent
# ---------------------------------------------------------------------------


class TestObserverAgent:
    @pytest.fixture
    def agent_content(self):
        return (PLUGIN_DIR / "agents" / "helios-observer.md").read_text()

    def test_has_capabilities(self, agent_content):
        assert "get_behavioral_context" in agent_content
        assert "get_drift_report" in agent_content

    def test_has_constraints(self, agent_content):
        assert "Never modify profiles directly" in agent_content

    def test_has_output_format(self, agent_content):
        assert "Stable Traits" in agent_content
        assert "Recommendations" in agent_content


# ---------------------------------------------------------------------------
# 3.7 Standalone skill package
# ---------------------------------------------------------------------------


class TestStandaloneSkill:
    def test_skill_dir_exists(self):
        assert SKILL_DIR.is_dir()

    def test_has_skill_md(self):
        assert (SKILL_DIR / "SKILL.md").is_file()

    def test_has_mcp_json(self):
        assert (SKILL_DIR / ".mcp.json").is_file()

    def test_skill_md_matches_plugin(self):
        plugin_skill = (PLUGIN_DIR / "skills" / "helios" / "SKILL.md").read_text()
        standalone_skill = (SKILL_DIR / "SKILL.md").read_text()
        assert plugin_skill == standalone_skill

    def test_mcp_json_matches_plugin(self):
        plugin_mcp = (PLUGIN_DIR / ".mcp.json").read_text()
        standalone_mcp = (SKILL_DIR / ".mcp.json").read_text()
        assert plugin_mcp == standalone_mcp
