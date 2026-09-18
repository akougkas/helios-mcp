"""`helios-mcp init`: import the founder's own CLAUDE.md as the authoritative
user-level preference for a persona, and make that persona the default.

Idempotent: rerunning overwrites the target persona's user-level file rather
than blending with or duplicating it, so onboarding can be repeated safely
whenever CLAUDE.md changes. Output-style import lands once observe's O9
projector exists; ``onboard`` is the hook point for adding that as a second
declared source alongside CLAUDE.md.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic_ops import git_commit
from .importer import import_from_markdown
from .profile import BehavioralProfile
from .security import persona_path
from .service import HeliosService

DEFAULT_SOURCE = Path.home() / ".claude" / "CLAUDE.md"
DEFAULT_ONBOARD_PERSONA = "developer"


def onboard(service: HeliosService, persona: str | None = None,
           source: Path | None = None) -> dict[str, Any]:
    """Import ``source`` (default ``~/.claude/CLAUDE.md``) into a persona's
    user level and set that persona as the default.

    When ``persona`` is omitted, the currently configured default persona is
    reused if one is already set up; otherwise onboarding falls back to
    ``developer`` so a fresh install has somewhere authoritative to land.
    """
    if persona:
        target = service.persona(persona)
    else:
        current = service.persona(None)
        target = current if current in service.list_personas() \
            else DEFAULT_ONBOARD_PERSONA

    claude_md = source or DEFAULT_SOURCE
    if not claude_md.is_file():
        raise FileNotFoundError(f"no personality file at {claude_md}")

    imported = import_from_markdown(claude_md, format="claude")
    user = BehavioralProfile(
        agent_id=f"{target}_user",
        level="user",
        distributions=dict(imported.distributions),
        parent_id=target,
        specialization_level=3,
        inherit_weight=0.0,
        description=f"Onboarded from {claude_md.name}",
    )
    path = persona_path(service.helios_dir / "personas", target, "_user.yaml")
    user.save(path)
    commit = git_commit(service.helios_dir, [path],
                        f"{target}: onboarded from {claude_md.name}")
    service.set_default_persona(target)
    rendered = service.render(target)

    return {
        "persona": target,
        "source": str(claude_md),
        "saved_to": str(path),
        "rendered_to": str(rendered),
        "commit": commit,
        "distributions": {
            dim: {"dominant": d.most_likely(),
                  "entropy": round(d.normalized_entropy(), 3)}
            for dim, d in user.distributions.items()
        },
    }
