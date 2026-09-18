"""Tests for Claude Code plugin packaging (Tasks 3.1-3.7).

Validates the plugin directory layout, manifest, hooks config,
MCP config, skill definition, and agent definition.
"""

import json
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).parent.parent / "helios-plugin"
SKILL_DIR = Path(__file__).parent.parent / "helios-skill"

# Deliberately no plain "does this file/dir exist" test class here: every
# fixture below (manifest, hooks, skill_content, ...) reads the same paths
# and fails with a clear error if they're missing, so a dedicated
# existence-only test would just be a slower, less informative duplicate.


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

    def test_no_component_keys_in_manifest(self, manifest):
        """Convention-based discovery: component keys must NOT be in manifest."""
        for key in ("skills", "agents", "hooks", "mcpServers", "components"):
            assert key not in manifest


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
        assert "post-tool" in cmd

    def test_post_tool_use_failure_hook(self, hooks):
        assert "PostToolUseFailure" in hooks["hooks"]
        cmd = hooks["hooks"]["PostToolUseFailure"][0]["hooks"][0]["command"]
        assert "post-tool-failure" in cmd

    def test_user_prompt_submit_hook(self, hooks):
        assert "UserPromptSubmit" in hooks["hooks"]
        cmd = hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
        assert "prompt-submit" in cmd

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
        for _event_type, entries in hooks["hooks"].items():
            for entry in entries:
                for hook in entry["hooks"]:
                    assert hook["type"] == "command"

    def test_capture_hooks_are_async(self, hooks):
        """Every hook that invokes hook-handler.py (observation capture)
        must be async — it must never block the user's session. The
        SessionStart context-injection hook is the one deliberate
        exception: Claude Code only reads a hook's stdout as context if
        it waits for that hook to finish, so it has to be synchronous."""
        for event_type, entries in hooks["hooks"].items():
            for entry in entries:
                for hook in entry["hooks"]:
                    if "hook-handler.py" in hook["command"]:
                        assert hook.get("async") is True, (
                            f"{event_type} capture hook is not async"
                        )

    def test_session_start_context_hook_is_sync(self, hooks):
        session_start_hooks = hooks["hooks"]["SessionStart"][0]["hooks"]
        context_hooks = [
            h for h in session_start_hooks if "session-start-context.py" in h["command"]
        ]
        assert len(context_hooks) == 1
        assert context_hooks[0].get("async") is not True

    def test_hooks_use_plugin_root_variable(self, hooks):
        """Commands should reference ${CLAUDE_PLUGIN_ROOT} for portability."""
        for event_type, entries in hooks["hooks"].items():
            for entry in entries:
                for hook in entry["hooks"]:
                    assert "${CLAUDE_PLUGIN_ROOT}" in hook["command"], (
                        f"{event_type} hook does not use ${{CLAUDE_PLUGIN_ROOT}}"
                    )

    def test_hooks_use_bundled_scripts(self, hooks):
        """Commands should call a bundled hooks/*.py script, not traverse paths."""
        bundled_scripts = {p.name for p in (PLUGIN_DIR / "hooks").glob("*.py")}
        for event_type, entries in hooks["hooks"].items():
            for entry in entries:
                for hook in entry["hooks"]:
                    assert "/../" not in hook["command"], (
                        f"{event_type} hook uses path traversal"
                    )
                    assert any(script in hook["command"] for script in bundled_scripts), (
                        f"{event_type} hook does not call a bundled hooks/*.py script"
                    )

    def test_hook_handler_is_executable_python(self):
        handler = PLUGIN_DIR / "hooks" / "hook-handler.py"
        content = handler.read_text()
        assert content.startswith("#!/usr/bin/env python3")

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
        assert "helios" in mcp

    def test_uses_uvx(self, mcp):
        server = mcp["helios"]
        assert server["command"] == "uvx"
        assert "helios-mcp" in server["args"]


# ---------------------------------------------------------------------------
# 3.5 SKILL.md
# ---------------------------------------------------------------------------


class TestSkillDefinition:
    @pytest.fixture
    def skill_content(self):
        return (PLUGIN_DIR / "skills" / "helios" / "SKILL.md").read_text()

    def test_has_yaml_frontmatter(self, skill_content):
        assert skill_content.startswith("---\n")
        # Must have closing ---
        parts = skill_content.split("---\n", 2)
        assert len(parts) >= 3, "SKILL.md must have YAML frontmatter with opening and closing ---"

    def test_frontmatter_has_name(self, skill_content):
        assert "name: helios" in skill_content

    def test_frontmatter_has_description(self, skill_content):
        assert "description:" in skill_content

    def test_frontmatter_has_argument_hint(self, skill_content):
        assert "argument-hint:" in skill_content

    def test_frontmatter_has_user_invocable(self, skill_content):
        assert "user-invocable: true" in skill_content

    def test_frontmatter_has_allowed_tools(self, skill_content):
        assert "allowed-tools:" in skill_content

    def test_has_activation_triggers(self, skill_content):
        assert "/helios" in skill_content
        assert "/helios status" in skill_content
        assert "/helios drift" in skill_content

    def test_has_arguments_routing(self, skill_content):
        assert "$ARGUMENTS" in skill_content

    def test_has_dynamic_context_injection(self, skill_content):
        assert "!`helios-mcp" in skill_content

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
    def test_skill_md_matches_plugin(self):
        plugin_skill = (PLUGIN_DIR / "skills" / "helios" / "SKILL.md").read_text()
        standalone_skill = (SKILL_DIR / "SKILL.md").read_text()
        assert plugin_skill == standalone_skill

    def test_mcp_json_matches_plugin(self):
        plugin_mcp = (PLUGIN_DIR / ".mcp.json").read_text()
        standalone_mcp = (SKILL_DIR / ".mcp.json").read_text()
        assert plugin_mcp == standalone_mcp
