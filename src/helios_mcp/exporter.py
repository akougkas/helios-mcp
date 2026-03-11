"""Profile export engine for Helios v2.

Three export modes:
1. export_dimensions — per-dimension slice of a profile
2. export_context — context-tagged behavioral subset (future)
3. export_diff — behavioral changelog from observation history

All return serializable dicts suitable for YAML/JSON output.
"""

from __future__ import annotations

from typing import Any

from .distribution import BehavioralDistribution
from .profile import BehavioralProfile
from .taxonomy import (
    DIMENSION_DESCRIPTIONS,
    STATE_LABELS,
    list_dimensions,
    list_states,
)


# ---------------------------------------------------------------------------
# Per-dimension export
# ---------------------------------------------------------------------------

def export_dimensions(
    profile: BehavioralProfile,
    dimensions: list[str] | None = None,
) -> dict[str, Any]:
    """Export specific dimensions from a behavioral profile.

    Args:
        profile: The BehavioralProfile to export.
        dimensions: List of dimension names to include.
            None means all dimensions.

    Returns:
        Serializable dict with dimension distributions and metadata.

    Raises:
        ValueError: If a requested dimension doesn't exist.
    """
    dims = dimensions or list_dimensions()
    for d in dims:
        if d not in profile.distributions:
            raise ValueError(f"Dimension '{d}' not found in profile '{profile.agent_id}'")

    result: dict[str, Any] = {
        "agent_id": profile.agent_id,
        "level": profile.level,
        "dimensions": {},
    }

    for dim in dims:
        dist = profile.distributions[dim]
        result["dimensions"][dim] = {
            "description": DIMENSION_DESCRIPTIONS.get(dim, ""),
            "dominant_state": dist.most_likely(),
            "entropy": round(dist.normalized_entropy(), 4),
            "distribution": {s: round(p, 4) for s, p in zip(dist.states, dist.probs)},
        }

    return result


# ---------------------------------------------------------------------------
# Per-context export (placeholder for future context-tagging)
# ---------------------------------------------------------------------------

def export_context(
    profile: BehavioralProfile,
    context_tag: str,
) -> dict[str, Any]:
    """Export behaviors relevant to a specific context.

    Context tagging is a future feature. For now, returns the full
    profile with the context tag as metadata.

    Args:
        profile: The BehavioralProfile to export.
        context_tag: A context label (e.g., "python_coding", "reviewing").

    Returns:
        Serializable dict with context-filtered distributions.
    """
    result = export_dimensions(profile)
    result["context"] = context_tag
    return result


# ---------------------------------------------------------------------------
# Diff-based export
# ---------------------------------------------------------------------------

def export_diff(
    current: BehavioralProfile,
    previous: BehavioralProfile,
) -> dict[str, Any]:
    """Export the behavioral difference between two profiles.

    Computes the per-dimension KL-divergence and state-level probability
    changes between two profile versions.

    Args:
        current: The current (newer) profile.
        previous: The previous (older) profile.

    Returns:
        Serializable dict describing what changed and by how much.
    """
    result: dict[str, Any] = {
        "agent_id": current.agent_id,
        "change_summary": {},
        "total_kl": 0.0,
    }

    total_kl = 0.0
    for dim in list_dimensions():
        curr_dist = current.distributions.get(dim)
        prev_dist = previous.distributions.get(dim)

        if not curr_dist or not prev_dist:
            continue

        kl = curr_dist.kl_divergence(prev_dist)
        total_kl += kl

        # Compute state-level deltas
        deltas: dict[str, float] = {}
        for state in list_states(dim):
            delta = curr_dist[state] - prev_dist[state]
            if abs(delta) > 0.001:
                deltas[state] = round(delta, 4)

        curr_dominant = curr_dist.most_likely()
        prev_dominant = prev_dist.most_likely()

        result["change_summary"][dim] = {
            "kl_divergence": round(kl, 4),
            "dominant_before": prev_dominant,
            "dominant_after": curr_dominant,
            "dominant_changed": curr_dominant != prev_dominant,
            "state_deltas": deltas,
        }

    result["total_kl"] = round(total_kl, 4)
    return result


# ---------------------------------------------------------------------------
# SoulSpec-compatible export (Task 2.6)
# ---------------------------------------------------------------------------

def export_soulspec(profile: BehavioralProfile) -> str:
    """Export a BehavioralProfile as a SoulSpec-compatible SOUL.md file.

    Maps probability distributions back to natural language personality
    descriptions. Includes metadata comments showing the underlying
    distribution values.

    Args:
        profile: The BehavioralProfile to export.

    Returns:
        String containing SoulSpec-compatible markdown.
    """
    lines: list[str] = []
    lines.append(f"# {profile.agent_id}")
    lines.append("")
    lines.append(f"> {profile.description}")
    lines.append("")

    for dim in list_dimensions():
        dist = profile.distributions.get(dim)
        if not dist:
            continue

        dim_desc = DIMENSION_DESCRIPTIONS.get(dim, dim)
        dominant = dist.most_likely()
        dominant_label = STATE_LABELS.get(dim, {}).get(dominant, dominant)

        lines.append(f"## {_dim_title(dim)}")
        lines.append("")

        # Natural language description from dominant + secondary states
        lines.append(_describe_distribution(dist, dim))
        lines.append("")

        # Metadata comment with actual distribution values
        lines.append("<!--")
        lines.append(f"  helios:{dim}")
        for state in list_states(dim):
            lines.append(f"    {state}: {dist[state]:.4f}")
        lines.append("-->")
        lines.append("")

    return "\n".join(lines)


def _dim_title(dim: str) -> str:
    """Convert dimension_name to Title Case."""
    return dim.replace("_", " ").title()


def _describe_distribution(dist: BehavioralDistribution, dim: str) -> str:
    """Generate a natural language sentence describing a distribution."""
    sorted_states = sorted(
        zip(dist.states, dist.probs),
        key=lambda x: x[1],
        reverse=True,
    )

    primary = sorted_states[0]
    secondary = sorted_states[1] if len(sorted_states) > 1 else None

    primary_label = STATE_LABELS.get(dim, {}).get(primary[0], primary[0])

    if primary[1] > 0.6:
        desc = f"Strongly: {primary_label} ({primary[1]:.0%} weight)."
    elif primary[1] > 0.35:
        desc = f"Primarily: {primary_label} ({primary[1]:.0%} weight)."
    else:
        desc = f"Tends toward: {primary_label} ({primary[1]:.0%} weight)."

    if secondary and secondary[1] > 0.15:
        secondary_label = STATE_LABELS.get(dim, {}).get(secondary[0], secondary[0])
        desc += f" Also: {secondary_label} ({secondary[1]:.0%} weight)."

    return desc
