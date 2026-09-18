"""Behavioral taxonomy for Helios v2.

Defines the four core behavioral dimensions and their discrete state spaces.
This is the scientific foundation: everything else (distributions, drift,
inheritance, observation) references these definitions.

The first four dimensions cover the agent's stance:
- Epistemic style: how the agent handles uncertainty and knowledge boundaries
- Interaction agency: how autonomous and directive the agent is
- Communication register: the length and density of outputs
- Risk and caution: how the agent weighs safety vs speed

The next five cover manner, which users notice as much as stance:
- Structure: prose versus headers and bullets
- Sycophancy: praise and validation versus candor
- Narration: announcing, recapping and closing pleasantries
- Specificity: concrete references versus adjectives
- Pushback: holding a correct position versus giving in
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
    # The dimensions below are orthogonal to the four above: they describe the
    # shape and manner of a response rather than its stance.
    "structure": [
        "prose",            # Paragraphs; lists only for genuinely parallel items
        "light_structure",  # Mostly prose with an occasional list or code block
        "heavy_structure",  # Headers, bullets and tables by default
    ],
    "sycophancy": [
        "candid",      # Names problems and disagreements plainly, no praise
        "neutral",     # Neither praise nor pointed candor
        "flattering",  # Praises the user or the question, validates by reflex
    ],
    "narration": [
        "silent_action",        # Does the work and reports the result
        "brief_signposting",    # A short line of orientation where it helps
        "narrates_and_recaps",  # Announces steps, recaps, closing pleasantries
    ],
    "specificity": [
        "concrete",  # Paths, line numbers, symbols, measured numbers
        "mixed",     # Some concrete references, some general description
        "vague",     # Adjectives and generalities instead of specifics
    ],
    # Observed only on turns that answer user pushback, so evidence is sparse.
    "pushback": [
        "holds_position",        # Keeps a correct position and says why
        "concedes_with_reason",  # Changes course when shown to be wrong
        "capitulates",           # Agrees because the user objected
    ],
}

# Human-readable descriptions for each dimension (used in negotiation summaries)
DIMENSION_DESCRIPTIONS: Final[dict[str, str]] = {
    "epistemic_style": (
        "how the agent handles uncertainty: whether it states things "
        "confidently, hedges frequently, admits ignorance readily, or "
        "speculates openly"
    ),
    "interaction_agency": (
        "how autonomous the agent is: whether it asks before acting, "
        "makes assumptions and proceeds, offers options, decides alone, "
        "or defers fully to the user"
    ),
    "communication_register": (
        "the structure and density of outputs, from terse and minimal "
        "to thorough and comprehensive, technical-dense or plain-accessible"
    ),
    "risk_caution": (
        "how the agent weighs safety vs speed: whether it acts immediately, "
        "checks before consequential actions, warns proactively, or "
        "refuses to proceed under ambiguity"
    ),
    "structure": (
        "how responses are shaped: flowing prose, prose with occasional "
        "lists, or headers and bullets by default"
    ),
    "sycophancy": (
        "whether the agent praises and validates the user, stays neutral, or "
        "names problems candidly"
    ),
    "narration": (
        "how much the agent talks about its own process: announcing steps, "
        "recapping and closing pleasantries, or just doing the work"
    ),
    "specificity": (
        "whether claims come with concrete paths, symbols and numbers, or with "
        "adjectives and generalities"
    ),
    "pushback": (
        "what the agent does when the user pushes back: holds a correct "
        "position, concedes when actually wrong, or gives in"
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
        "terse":            "be concise: minimal words, maximum information density",
        "moderate":         "use balanced response length appropriate to the question",
        "thorough":         "be comprehensive: explain context, reasoning, and"
                            " implications",
        "technical_dense":  "use domain-specific terminology, assume an expert reader",
        "plain_accessible": "use plain language, assume a non-expert reader",
    },
    "risk_caution": {
        "acts_immediately":     "proceed without additional warnings or confirmation",
        "checks_before_acting": "confirm intent before consequential or irreversible"
                               " actions",
        "warns_frequently":     "proactively surface risks, caveats, and potential"
                               " issues",
        "refuses_ambiguity":    "stop and ask for clarification when the situation is"
                               " unclear",
    },
    "structure": {
        "prose":           "write in prose paragraphs; use a list only for three"
                           " or more parallel items",
        "light_structure": "write mostly prose, with a list or code block where"
                           " it helps",
        "heavy_structure": "organize responses with headers and bullet points",
    },
    "sycophancy": {
        "candid":     "skip praise and name problems and disagreements plainly",
        "neutral":    "keep a neutral tone without praise or validation",
        "flattering": "acknowledge the user's ideas warmly",
    },
    "narration": {
        "silent_action":       "do the work without announcing it, and report"
                               " the result without a recap",
        "brief_signposting":   "orient the reader in a short line when a task has"
                               " several steps",
        "narrates_and_recaps": "explain each step as you take it and summarize"
                               " at the end",
    },
    "specificity": {
        "concrete": "cite paths, line numbers, symbols and measured numbers"
                    " rather than adjectives",
        "mixed":    "combine concrete references with general description",
        "vague":    "describe things in general terms",
    },
    "pushback": {
        "holds_position":       "when the user pushes back and you are right, hold"
                                " the position and give the reason",
        "concedes_with_reason": "when the user pushes back, concede if they are"
                                " right and say what changed",
        "capitulates":          "defer to the user's objection",
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
    return dict.fromkeys(states, prob)
