"""Behavioral taxonomy for Helios v2.

Defines the four core behavioral dimensions and their discrete state spaces.
This is the scientific foundation — everything else (distributions, drift,
inheritance, observation) references these definitions.

The four dimensions cover the fundamental axes of AI agent behavior:
- Epistemic style: how the agent handles uncertainty and knowledge boundaries
- Interaction agency: how autonomous and directive the agent is
- Communication register: the formality, density, and structure of outputs
- Risk and caution: how the agent weighs safety vs speed
"""

from __future__ import annotations

from typing import Final


# ---------------------------------------------------------------------------
# Core taxonomy definition
# ---------------------------------------------------------------------------

BEHAVIORAL_TAXONOMY: Final[dict[str, list[str]]] = {
    "epistemic_style": [
        "confident",        # States things directly, minimal hedging
        "hedging",          # Frequently qualifies claims with uncertainty markers
        "admits_ignorance", # Readily says "I don't know" and stops there
        "speculating",      # Engages openly with hypotheticals and unknowns
    ],
    "interaction_agency": [
        "asks_first",           # Gathers information before acting
        "assumes_and_acts",     # Makes reasonable assumptions and proceeds
        "offers_options",       # Presents alternatives and lets user decide
        "decides_unilaterally", # Makes choices without checking
        "defers_to_user",       # Minimizes own judgment, maximizes user control
    ],
    "communication_register": [
        "terse",             # Minimal words, maximum signal density
        "moderate",          # Balanced length, neither too short nor too long
        "thorough",          # Comprehensive coverage, explains context and reasoning
        "technical_dense",   # Domain-specific jargon, assumes expert reader
        "plain_accessible",  # Plain language, assumes non-expert reader
    ],
    "risk_caution": [
        "acts_immediately",      # Proceeds without warnings or confirmation
        "checks_before_acting",  # Confirms intent before consequential actions
        "warns_frequently",      # Surfaces risks and caveats proactively
        "refuses_ambiguity",     # Stops and asks when situation is unclear
    ],
}

# Human-readable descriptions for each dimension (used in negotiation summaries)
DIMENSION_DESCRIPTIONS: Final[dict[str, str]] = {
    "epistemic_style": (
        "how the agent handles uncertainty — whether it states things "
        "confidently, hedges frequently, admits ignorance readily, or "
        "speculates openly"
    ),
    "interaction_agency": (
        "how autonomous the agent is — whether it asks before acting, "
        "makes assumptions and proceeds, offers options, decides alone, "
        "or defers fully to the user"
    ),
    "communication_register": (
        "the structure and density of outputs — from terse and minimal "
        "to thorough and comprehensive, technical-dense or plain-accessible"
    ),
    "risk_caution": (
        "how the agent weighs safety vs speed — whether it acts immediately, "
        "checks before consequential actions, warns proactively, or "
        "refuses to proceed under ambiguity"
    ),
}

# Human-readable labels for each state (used in rendered system prompts)
STATE_LABELS: Final[dict[str, dict[str, str]]] = {
    "epistemic_style": {
        "confident":        "state things directly and confidently",
        "hedging":          "qualify claims with uncertainty markers when appropriate",
        "admits_ignorance": "say clearly when you do not know something",
        "speculating":      "engage openly with hypotheticals and explore unknowns",
    },
    "interaction_agency": {
        "asks_first":           "ask clarifying questions before acting",
        "assumes_and_acts":     "make reasonable assumptions and proceed",
        "offers_options":       "present alternatives and let the user decide",
        "decides_unilaterally": "make decisions autonomously without checking",
        "defers_to_user":       "minimize your own judgment and maximize user control",
    },
    "communication_register": {
        "terse":            "be concise — minimal words, maximum information density",
        "moderate":         "use balanced response length appropriate to the question",
        "thorough":         "be comprehensive — explain context, reasoning, and implications",
        "technical_dense":  "use domain-specific terminology, assume an expert reader",
        "plain_accessible": "use plain language, assume a non-expert reader",
    },
    "risk_caution": {
        "acts_immediately":     "proceed without additional warnings or confirmation",
        "checks_before_acting": "confirm intent before consequential or irreversible actions",
        "warns_frequently":     "proactively surface risks, caveats, and potential issues",
        "refuses_ambiguity":    "stop and ask for clarification when the situation is unclear",
    },
}


# ---------------------------------------------------------------------------
# Validation utilities
# ---------------------------------------------------------------------------

def list_dimensions() -> list[str]:
    """Return the names of all behavioral dimensions.

    Returns:
        List of dimension names in canonical order.
    """
    return list(BEHAVIORAL_TAXONOMY.keys())


def list_states(dimension: str) -> list[str]:
    """Return the valid states for a behavioral dimension.

    Args:
        dimension: Name of the behavioral dimension.

    Returns:
        List of valid state names for that dimension.

    Raises:
        ValueError: If the dimension is not in the taxonomy.
    """
    if dimension not in BEHAVIORAL_TAXONOMY:
        raise ValueError(
            f"Unknown behavioral dimension '{dimension}'. "
            f"Valid dimensions: {list_dimensions()}"
        )
    return list(BEHAVIORAL_TAXONOMY[dimension])


def validate_dimension(dimension: str) -> str:
    """Validate that a dimension name exists in the taxonomy.

    Args:
        dimension: Dimension name to validate.

    Returns:
        The validated dimension name (unchanged).

    Raises:
        ValueError: If the dimension is not recognized.
    """
    if dimension not in BEHAVIORAL_TAXONOMY:
        raise ValueError(
            f"Unknown behavioral dimension '{dimension}'. "
            f"Valid dimensions: {list_dimensions()}"
        )
    return dimension


def validate_state(dimension: str, state: str) -> str:
    """Validate that a state name is valid for a given dimension.

    Args:
        dimension: The behavioral dimension.
        state: The state to validate.

    Returns:
        The validated state name (unchanged).

    Raises:
        ValueError: If the dimension is unknown or the state is not valid
                    for that dimension.
    """
    valid_states = list_states(dimension)  # also validates dimension
    if state not in valid_states:
        raise ValueError(
            f"Unknown state '{state}' for dimension '{dimension}'. "
            f"Valid states: {valid_states}"
        )
    return state


def get_dimension_description(dimension: str) -> str:
    """Return a human-readable description of a behavioral dimension.

    Args:
        dimension: The dimension name.

    Returns:
        Natural language description of what this dimension captures.

    Raises:
        ValueError: If the dimension is not recognized.
    """
    validate_dimension(dimension)
    return DIMENSION_DESCRIPTIONS[dimension]


def get_state_label(dimension: str, state: str) -> str:
    """Return a human-readable instruction label for a behavioral state.

    Used when rendering behavioral profiles into system prompt text.

    Args:
        dimension: The behavioral dimension.
        state: The specific state.

    Returns:
        Natural language instruction string for this state.

    Raises:
        ValueError: If the dimension or state is not recognized.
    """
    validate_state(dimension, state)
    return STATE_LABELS[dimension][state]


def uniform_distribution(dimension: str) -> dict[str, float]:
    """Return a uniform probability distribution over a dimension's states.

    Useful as a neutral starting point or for testing.

    Args:
        dimension: The behavioral dimension.

    Returns:
        Dict mapping each state to equal probability (1/n_states).
    """
    states = list_states(dimension)
    prob = 1.0 / len(states)
    return {state: prob for state in states}
