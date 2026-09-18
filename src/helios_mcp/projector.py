"""LLM-assisted projection for Helios v2.

Constructs a prompt that asks a model to map natural language personality
descriptions to probability distributions over behavioral dimensions. The
importer falls back to keyword heuristics when no model is available.

The projection prompt includes the full taxonomy with state descriptions
and asks for float weights summing to 1.0 per dimension.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor

from .distribution import BehavioralDistribution
from .llm import LLMClient, build_taxonomy_description, projection_schema
from .profile import BehavioralProfile
from .taxonomy import list_dimensions, list_states

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a behavioral scientist mapping personality descriptions to "
    "probability distributions.\n"
    "\n"
    "Given text describing an agent's personality, style, or behavioral "
    "preferences, produce probability distributions over these behavioral "
    "dimensions:\n"
    "\n"
    "{taxonomy_description}\n"
    "\n"
    "Rules:\n"
    "- Each dimension's probabilities MUST sum to exactly 1.0\n"
    "- No probability can be negative\n"
    "- Every state must have a value (use 0.01 minimum for unlikely states)\n"
    "- Base your estimates on the text provided, not assumptions\n"
    "- If the text is ambiguous for a dimension, use a spread distribution "
    "(closer to uniform)\n"
    "- Project the preferences the text states, not how the text itself is "
    "written: a rules file written as bullets does not ask for bullets\n"
    "- Each distribution says how often the agent should behave each way. A "
    "behavior the text allows only in narrow cases (\"ask only at real design "
    "forks\") is a minority state; the default the text implies for everything "
    "else is the majority\n"
    "\n"
    "Respond with ONLY a JSON object mapping every dimension name to an object "
    "of state probabilities.\n"
    "\n"
    "No explanation. No markdown. Just the JSON object."
)


def build_projection_prompt(text_blocks: list[str]) -> tuple[str, str]:
    """Build the system and user prompts for LLM-assisted projection.

    Args:
        text_blocks: Personality-relevant text blocks extracted from a file.

    Returns:
        Tuple of (system_prompt, user_prompt).
    """
    taxonomy_desc = build_taxonomy_description()
    system = _SYSTEM_PROMPT.format(taxonomy_description=taxonomy_desc)

    user_text = "\n\n---\n\n".join(text_blocks)
    user = (
        "Map the following personality description to behavioral "
        f"distributions:\n\n{user_text}"
    )

    return system, user


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def parse_projection_response(response_text: str) -> dict[str, dict[str, float]]:
    """Parse the LLM response into raw distribution dicts.

    Extracts JSON from the response, handling possible markdown code fences.

    Args:
        response_text: Raw LLM response text.

    Returns:
        Dict mapping dimension → state → probability.

    Raises:
        ValueError: If the response cannot be parsed or validated.
    """
    # Strip markdown code fences if present
    cleaned = response_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse LLM response as JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object, got {type(data).__name__}")

    # Dimensions the reply omits fall back to species defaults later, but a
    # reply that covers none of them carries no projection at all.
    present = [dim for dim in list_dimensions() if dim in data]
    if not present:
        raise ValueError("Reply covers no known dimension")
    for dim in present:
        if not isinstance(data[dim], dict):
            raise ValueError(
                f"Dimension {dim} must be a dict, got {type(data[dim]).__name__}"
            )

        states = list_states(dim)
        for state in states:
            if state not in data[dim]:
                raise ValueError(f"Missing state {state} in dimension {dim}")
            val = data[dim][state]
            if not isinstance(val, int | float):
                raise ValueError(
                    f"State {dim}.{state} must be numeric, "
                    f"got {type(val).__name__}"
                )
            if val < 0:
                raise ValueError(f"State {dim}.{state} is negative: {val}")

    return data


def validate_and_normalize(
    raw: dict[str, dict[str, float]],
) -> dict[str, BehavioralDistribution]:
    """Validate and normalize raw projection data into BehavioralDistribution objects.

    Normalizes each dimension's probabilities to sum to exactly 1.0
    and enforces minimum probability for all states. Dimensions missing from
    ``raw`` take the species default.

    Args:
        raw: Dict mapping dimension → state → probability.

    Returns:
        Dict mapping dimension → BehavioralDistribution.
    """
    dists: dict[str, BehavioralDistribution] = {}
    min_prob = 0.001  # floor to prevent zero mass
    species = BehavioralProfile.default_species().distributions

    for dim in list_dimensions():
        if dim not in raw:
            dists[dim] = species[dim]
            continue
        states = list_states(dim)
        weights = {}
        for state in states:
            w = max(raw.get(dim, {}).get(state, 0.0), min_prob)
            weights[state] = w

        total = sum(weights.values())
        normalized = {s: v / total for s, v in weights.items()}
        dists[dim] = BehavioralDistribution(dim, normalized)

    return dists


# ---------------------------------------------------------------------------
# Main projection function
# ---------------------------------------------------------------------------

# One projection call is noisy: the same file can swing a state by 0.4 between
# calls. The mean of a few independent calls is what gets stored.
PROJECTION_SAMPLES = 3


def _project_once(
    system: str, user: str, client: LLMClient
) -> dict[str, BehavioralDistribution] | None:
    """One projection, holding only the dimensions the model actually gave."""
    data = client.complete_json(system, user, projection_schema())
    if data is None:
        return None
    try:
        raw = parse_projection_response(json.dumps(data))
    except ValueError:
        return None
    full = validate_and_normalize(raw)
    return {dim: dist for dim, dist in full.items() if dim in raw}


def project_with_llm(
    text_blocks: list[str], client: LLMClient, samples: int = PROJECTION_SAMPLES
) -> dict[str, BehavioralDistribution] | None:
    """Mean of ``samples`` model projections, or None if every call failed."""
    if not any(block.strip() for block in text_blocks):
        return None
    system, user = build_projection_prompt(text_blocks)
    with ThreadPoolExecutor(max_workers=max(samples, 1)) as pool:
        runs = [
            r for r in pool.map(
                lambda _: _project_once(system, user, client), range(max(samples, 1))
            ) if r is not None
        ]
    if not runs:
        return None
    # A dimension one run omitted is averaged over the runs that gave it, so
    # the species default does not dilute it. Only a dimension no run gave
    # takes the default.
    species = BehavioralProfile.default_species().distributions
    out: dict[str, BehavioralDistribution] = {}
    for dim in list_dimensions():
        given = [run[dim] for run in runs if dim in run]
        if not given:
            out[dim] = species[dim]
            continue
        out[dim] = BehavioralDistribution(dim, {
            state: sum(d[state] for d in given) / len(given)
            for state in list_states(dim)
        })
    return out
