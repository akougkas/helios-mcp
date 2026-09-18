"""`helios-mcp init`: import the founder's declared preferences, CLAUDE.md
plus the active output style, as the authoritative user-level profile for a
persona, and make that persona the default.

Idempotent: rerunning overwrites the target persona's user-level file rather
than blending with or duplicating it, so onboarding can be repeated safely
whenever CLAUDE.md or the output style changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic_ops import git_commit
from .importer import claude_home, declared_sources, import_declared
from .profile import BehavioralProfile
from .security import persona_path
from .service import HeliosService

DEFAULT_ONBOARD_PERSONA = "developer"


def onboard(service: HeliosService, persona: str | None = None,
           home: Path | None = None, project_dir: Path | None = None
           ) -> dict[str, Any]:
    """Import declared sources under ``home`` (default ``~/.claude``) into a
    persona's user level and set that persona as the default.

    When ``persona`` is omitted, the currently configured default persona is
    reused if one is already set up; otherwise onboarding falls back to
    ``developer`` so a fresh install has somewhere authoritative to land.
    ``project_dir``, when given, lets a project-local output style take
    precedence over the user-level one, matching how Claude Code itself
    resolves the active style.
    """
    if persona:
        target = service.persona(persona)
    else:
        current = service.persona(None)
        target = current if current in service.list_personas() \
            else DEFAULT_ONBOARD_PERSONA

    sources = declared_sources(home, project_dir)
    if not sources:
        raise FileNotFoundError(
            f"no declared preferences under {home or claude_home()}")

    imported = import_declared(sources, name=f"{target}_user",
                               helios_dir=service.helios_dir)
    user = BehavioralProfile(
        agent_id=f"{target}_user",
        level="user",
        distributions=dict(imported.distributions),
        parent_id=target,
        specialization_level=3,
        inherit_weight=0.0,
        description=imported.description,
    )
    path = persona_path(service.helios_dir / "personas", target, "_user.yaml")
    user.save(path)
    commit = git_commit(service.helios_dir, [path],
                        f"{target}: onboarded from "
                        + ", ".join(p.name for p in sources))
    service.set_default_persona(target)
    rendered = service.render(target)

    return {
        "persona": target,
        "sources": [str(p) for p in sources],
        "saved_to": str(path),
        "rendered_to": str(rendered),
        "commit": commit,
        "distributions": {
            dim: {"dominant": d.most_likely(),
                  "entropy": round(d.normalized_entropy(), 3)}
            for dim, d in user.distributions.items()
        },
    }
