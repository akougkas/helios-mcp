"""Declared artifacts: the global CLAUDE.md plus the active output style."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helios_mcp.importer import active_output_style, declared_sources, import_declared
from helios_mcp.taxonomy import list_dimensions

STYLE = """---
name: Peer Engineer
description: Prose over structure, conclusions over hedging.
---

## Voice

Say the thing. No flattery, no recaps.
"""


def _home(tmp_path: Path, style_setting: str | None = "Peer Engineer") -> Path:
    home = tmp_path / "home"
    (home / "output-styles").mkdir(parents=True)
    (home / "output-styles" / "peer-engineer.md").write_text(STYLE)
    (home / "CLAUDE.md").write_text("# Rules\n\nDirect. Opinionated.\n")
    if style_setting is not None:
        (home / "settings.json").write_text(json.dumps({"outputStyle": style_setting}))
    return home


@pytest.mark.parametrize("setting", ["Peer Engineer", "peer-engineer", "peer engineer"])
def test_style_resolves_by_frontmatter_name_or_stem(tmp_path, setting):
    home = _home(tmp_path, setting)
    assert active_output_style(home) == home / "output-styles" / "peer-engineer.md"


@pytest.mark.parametrize("setting", [None, "default", "Explanatory", "No Such Style"])
def test_builtin_missing_or_unknown_style_gives_none(tmp_path, setting):
    assert active_output_style(_home(tmp_path, setting)) is None


def test_project_settings_and_styles_take_precedence(tmp_path):
    home = _home(tmp_path)
    project = tmp_path / "proj"
    styles = project / ".claude" / "output-styles"
    styles.mkdir(parents=True)
    (styles / "terse.md").write_text("---\nname: Terse\n---\nOne line answers.\n")
    (project / ".claude" / "settings.local.json").write_text('{"outputStyle": "Terse"}')
    (project / ".claude" / "settings.json").write_text('{"outputStyle": "Peer Engineer"}')
    assert active_output_style(home, project) == styles / "terse.md"


class _Recorder:
    def __init__(self) -> None:
        self.prompt = ""

    def complete_json(self, system, prompt, schema):
        self.prompt = prompt
        return None  # falls back to keyword projection


def test_import_declared_projects_both_artifacts_in_one_call(tmp_path):
    home = _home(tmp_path)
    sources = declared_sources(home)
    assert [p.name for p in sources] == ["CLAUDE.md", "peer-engineer.md"]

    client = _Recorder()
    profile = import_declared(sources, name="founder", client=client)
    assert "Opinionated" in client.prompt
    assert "Prose over structure" in client.prompt
    assert "no recaps" in client.prompt.lower()
    assert "name: Peer Engineer" not in client.prompt
    assert profile.agent_id == "founder"
    assert profile.level == "user"
    assert set(profile.distributions) == set(list_dimensions())


def test_import_declared_without_sources_fails(tmp_path):
    with pytest.raises(ValueError):
        import_declared([])
