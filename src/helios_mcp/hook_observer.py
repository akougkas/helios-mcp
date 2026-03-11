"""Hook-based signal extraction for Helios v2.

Extracts behavioral signals from Claude Code hook events and converts
them into weighted contributions to the 4 behavioral dimensions.

Four extractor functions, one per event category:
1. extract_tool_signals — tool selection patterns, diversity, ordering
2. extract_subagent_signals — delegation frequency, parallelization, types
3. extract_session_signals — session duration, interaction density
4. extract_prompt_signals — directness, specificity, question frequency
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from .distribution import BehavioralDistribution
from .hook_events import (
    ConfigChangeEvent,
    SubagentEvent,
    SessionEvent,
    ToolUseEvent,
    UserPromptEvent,
)
from .taxonomy import list_dimensions, list_states


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

# A signal result is a dict mapping dimension → state → weight contribution
SignalResult = dict[str, dict[str, float]]


# ---------------------------------------------------------------------------
# Tool signal extraction
# ---------------------------------------------------------------------------

# Tools grouped by behavioral interpretation
_READ_TOOLS = frozenset({"Read", "Glob", "Grep", "Bash"})
_WRITE_TOOLS = frozenset({"Edit", "Write", "NotebookEdit"})
_SEARCH_TOOLS = frozenset({"Read", "Glob", "Grep", "Agent"})
_TEST_TOOLS_KEYWORDS = ("test", "pytest", "jest", "cargo test", "go test")


def extract_tool_signals(events: list[ToolUseEvent]) -> SignalResult:
    """Extract behavioral signals from tool use patterns.

    Analyzes which tools the agent selects, how diverse its tool usage is,
    and whether it follows cautious patterns (read-before-write, test-before-commit).

    Args:
        events: List of ToolUseEvent from PostToolUse hooks.

    Returns:
        SignalResult mapping dimension → state → weight.
    """
    if not events:
        return _empty_signal()

    result: SignalResult = _empty_signal()
    tool_names = [e.tool_name for e in events]
    tool_counts = Counter(tool_names)
    total = len(events)

    # --- Tool diversity (Shannon entropy of tool distribution) ---
    diversity = _tool_diversity(tool_counts, total)

    # --- Read/write ratio ---
    read_count = sum(tool_counts.get(t, 0) for t in _READ_TOOLS)
    write_count = sum(tool_counts.get(t, 0) for t in _WRITE_TOOLS)
    read_heavy = read_count > write_count * 2

    # --- Test-before-commit pattern ---
    has_test_run = any(
        e.tool_name == "Bash" and any(
            kw in " ".join(e.tool_input_keys).lower()
            for kw in _TEST_TOOLS_KEYWORDS
        )
        for e in events
    )

    # --- Failure rate ---
    failure_count = sum(1 for e in events if not e.success)
    failure_rate = failure_count / total if total > 0 else 0.0

    # --- epistemic_style contributions ---
    # Read-heavy usage suggests thoroughness (confident after research)
    if read_heavy:
        result["epistemic_style"]["confident"] += 2.0
    # High tool diversity suggests exploratory/speculating approach
    if diversity > 0.7:
        result["epistemic_style"]["speculating"] += 1.5
    # Low diversity with mostly writes suggests confident approach
    if diversity < 0.3 and write_count > read_count:
        result["epistemic_style"]["confident"] += 2.0

    # --- interaction_agency contributions ---
    # Agent tool usage suggests delegation (offers_options or defers_to_user)
    agent_count = tool_counts.get("Agent", 0)
    if agent_count > 0:
        agent_ratio = agent_count / total
        if agent_ratio > 0.2:
            result["interaction_agency"]["offers_options"] += 2.0
        else:
            result["interaction_agency"]["offers_options"] += 1.0

    # Heavy Bash usage suggests assumes_and_acts
    bash_count = tool_counts.get("Bash", 0)
    if bash_count / total > 0.3:
        result["interaction_agency"]["assumes_and_acts"] += 2.0

    # --- communication_register contributions ---
    # Read-heavy implies thorough research
    if read_heavy:
        result["communication_register"]["thorough"] += 1.5
    # Write-heavy with low reads implies terse/efficient
    if write_count > read_count * 2:
        result["communication_register"]["terse"] += 1.5

    # --- risk_caution contributions ---
    # Read-before-write ordering suggests caution
    if _has_read_before_write_pattern(events):
        result["risk_caution"]["checks_before_acting"] += 2.0

    # Test-related Bash commands suggest caution
    if has_test_run:
        result["risk_caution"]["checks_before_acting"] += 2.0

    # High failure rate with retries suggests acting without checking
    if failure_rate > 0.3:
        result["risk_caution"]["acts_immediately"] += 1.5

    # No search tools used suggests acting without investigation
    search_count = sum(tool_counts.get(t, 0) for t in _SEARCH_TOOLS)
    if search_count == 0 and total > 3:
        result["risk_caution"]["acts_immediately"] += 1.5

    return result


def _tool_diversity(counts: Counter, total: int) -> float:
    """Compute normalized Shannon entropy of tool distribution."""
    if total == 0 or len(counts) <= 1:
        return 0.0
    max_entropy = math.log(len(counts))
    if max_entropy == 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log(p)
    return entropy / max_entropy


def _has_read_before_write_pattern(events: list[ToolUseEvent]) -> bool:
    """Check if reads tend to precede writes in the event sequence."""
    last_read_idx = -1
    writes_after_reads = 0
    writes_without_reads = 0

    for i, e in enumerate(events):
        if e.tool_name in _READ_TOOLS:
            last_read_idx = i
        elif e.tool_name in _WRITE_TOOLS:
            if last_read_idx >= 0:
                writes_after_reads += 1
            else:
                writes_without_reads += 1

    total_writes = writes_after_reads + writes_without_reads
    if total_writes == 0:
        return False
    return writes_after_reads / total_writes > 0.5


# ---------------------------------------------------------------------------
# Subagent signal extraction
# ---------------------------------------------------------------------------

def extract_subagent_signals(events: list[SubagentEvent]) -> SignalResult:
    """Extract behavioral signals from subagent usage patterns.

    Analyzes delegation frequency, parallelization, and agent type choices.

    Args:
        events: List of SubagentEvent from SubagentStart/Stop hooks.

    Returns:
        SignalResult mapping dimension → state → weight.
    """
    if not events:
        return _empty_signal()

    result: SignalResult = _empty_signal()

    start_events = [e for e in events if e.event_type == "start"]
    delegation_count = len(start_events)

    # --- Agent types used ---
    type_counts = Counter(e.agent_type for e in start_events if e.agent_type)

    # --- Parallelization detection ---
    # Multiple starts before any stop suggests parallel delegation
    parallel_ratio = _estimate_parallelization(events)

    # --- interaction_agency contributions ---
    # High delegation count suggests offers_options or defers_to_user
    if delegation_count >= 5:
        result["interaction_agency"]["offers_options"] += 2.5
        result["interaction_agency"]["defers_to_user"] += 1.0
    elif delegation_count >= 2:
        result["interaction_agency"]["offers_options"] += 1.5

    # No delegation suggests decides_unilaterally or assumes_and_acts
    if delegation_count == 0:
        result["interaction_agency"]["assumes_and_acts"] += 1.0

    # --- epistemic_style contributions ---
    # Using Explore agents suggests thoroughness
    if type_counts.get("Explore", 0) > 0:
        result["epistemic_style"]["confident"] += 1.0
    # Using Plan agents suggests systematic approach
    if type_counts.get("Plan", 0) > 0:
        result["epistemic_style"]["confident"] += 1.0

    # --- communication_register contributions ---
    # Heavy delegation suggests thorough approach
    if delegation_count >= 3:
        result["communication_register"]["thorough"] += 1.0

    # --- risk_caution contributions ---
    # Parallel execution suggests confidence/speed
    if parallel_ratio > 0.5:
        result["risk_caution"]["acts_immediately"] += 1.5
    # Sequential careful delegation suggests caution
    elif delegation_count >= 2 and parallel_ratio < 0.2:
        result["risk_caution"]["checks_before_acting"] += 1.5

    return result


def _estimate_parallelization(events: list[SubagentEvent]) -> float:
    """Estimate the ratio of parallel to sequential subagent usage.

    Returns a value in [0, 1] where higher means more parallelization.
    """
    active = 0
    max_concurrent = 0
    total_starts = 0

    for e in events:
        if e.event_type == "start":
            active += 1
            total_starts += 1
            max_concurrent = max(max_concurrent, active)
        elif e.event_type == "stop":
            active = max(0, active - 1)

    if total_starts <= 1:
        return 0.0
    return (max_concurrent - 1) / total_starts


# ---------------------------------------------------------------------------
# Session signal extraction
# ---------------------------------------------------------------------------

def extract_session_signals(events: list[SessionEvent]) -> SignalResult:
    """Extract behavioral signals from session patterns.

    Analyzes session duration and frequency of start/end cycles.

    Args:
        events: List of SessionEvent from SessionStart/End hooks.

    Returns:
        SignalResult mapping dimension → state → weight.
    """
    if not events:
        return _empty_signal()

    result: SignalResult = _empty_signal()

    starts = [e for e in events if e.event_type == "start"]
    ends = [e for e in events if e.event_type == "end"]

    # --- Session duration estimation ---
    durations: list[float] = []
    for start in starts:
        matching_end = next(
            (e for e in ends if e.timestamp > start.timestamp),
            None,
        )
        if matching_end:
            durations.append(matching_end.timestamp - start.timestamp)

    if durations:
        avg_duration_min = (sum(durations) / len(durations)) / 60.0

        # Long sessions suggest thorough work
        if avg_duration_min > 30:
            result["communication_register"]["thorough"] += 1.5
            result["epistemic_style"]["confident"] += 1.0
        # Short sessions suggest terse/efficient work
        elif avg_duration_min < 5:
            result["communication_register"]["terse"] += 1.5
            result["risk_caution"]["acts_immediately"] += 1.0

    # Multiple sessions suggest iterative approach
    if len(starts) > 3:
        result["risk_caution"]["checks_before_acting"] += 1.0

    return result


# ---------------------------------------------------------------------------
# Prompt signal extraction
# ---------------------------------------------------------------------------

def extract_prompt_signals(events: list[UserPromptEvent]) -> SignalResult:
    """Extract behavioral signals from user prompt patterns.

    Analyzes prompt length, question frequency, and directness
    to infer the communication style of the human-agent interaction.

    Args:
        events: List of UserPromptEvent from PromptSubmit hooks.

    Returns:
        SignalResult mapping dimension → state → weight.
    """
    if not events:
        return _empty_signal()

    result: SignalResult = _empty_signal()

    lengths = [e.length for e in events]
    questions = [e.question_count for e in events]

    avg_length = sum(lengths) / len(lengths) if lengths else 0
    total_questions = sum(questions)
    avg_questions = total_questions / len(questions) if questions else 0
    question_rate = sum(1 for q in questions if q > 0) / len(questions) if questions else 0

    # --- communication_register contributions ---
    # Short prompts from user suggest the interaction is terse
    if avg_length < 50:
        result["communication_register"]["terse"] += 2.0
    elif avg_length > 200:
        result["communication_register"]["thorough"] += 2.0
    else:
        result["communication_register"]["moderate"] += 1.5

    # --- epistemic_style contributions ---
    # High question rate from user suggests hedging/uncertainty in the interaction
    if question_rate > 0.6:
        result["epistemic_style"]["hedging"] += 1.0
    # Low question rate with long prompts suggests confident direction
    elif question_rate < 0.2 and avg_length > 100:
        result["epistemic_style"]["confident"] += 1.5

    # --- interaction_agency contributions ---
    # Many questions from user suggests asks_first dynamic
    if avg_questions > 1.5:
        result["interaction_agency"]["asks_first"] += 1.5
    # Short, directive prompts suggest user expects autonomous action
    elif avg_length < 30 and question_rate < 0.2:
        result["interaction_agency"]["assumes_and_acts"] += 1.5

    # --- risk_caution contributions ---
    # Question-heavy prompts suggest the user wants caution
    if question_rate > 0.5:
        result["risk_caution"]["checks_before_acting"] += 1.0

    return result


# ---------------------------------------------------------------------------
# Failure signal extraction (PostToolUseFailure events)
# ---------------------------------------------------------------------------

def extract_failure_signals(events: list[ToolUseEvent]) -> SignalResult:
    """Extract behavioral signals from tool failure events.

    Failure patterns indicate risk posture and epistemic style.
    Repeated failures on the same tool suggest stubbornness or
    insufficient caution. Failures after reads suggest thoroughness
    that still didn't prevent the error.

    Args:
        events: List of ToolUseEvent with phase="post_failure".

    Returns:
        SignalResult mapping dimension -> state -> weight.
    """
    if not events:
        return _empty_signal()

    result: SignalResult = _empty_signal()
    failure_count = len(events)
    tool_counts = Counter(e.tool_name for e in events)

    # Repeated failures on the same tool suggest acting without checking
    max_same_tool_failures = max(tool_counts.values()) if tool_counts else 0
    if max_same_tool_failures >= 3:
        result["risk_caution"]["acts_immediately"] += 2.0
        result["epistemic_style"]["confident"] += 1.0

    # Many distinct tool failures suggest exploratory approach
    if len(tool_counts) >= 3:
        result["epistemic_style"]["speculating"] += 1.5

    # Any failures boost warns_frequently (awareness of failure)
    if failure_count >= 2:
        result["risk_caution"]["warns_frequently"] += 1.0

    # Single failure is normal, many failures suggest lack of caution
    if failure_count >= 5:
        result["risk_caution"]["acts_immediately"] += 1.5
        result["interaction_agency"]["assumes_and_acts"] += 1.0

    return result


# ---------------------------------------------------------------------------
# Config change signal extraction
# ---------------------------------------------------------------------------

def extract_config_signals(events: list[ConfigChangeEvent]) -> SignalResult:
    """Extract behavioral signals from configuration change events.

    Config changes indicate how the agent/user manages their environment.
    Frequent changes suggest an iterative, experimental style. Changes
    to specific files can indicate caution (settings) or boldness (hooks).

    Args:
        events: List of ConfigChangeEvent from ConfigChange hooks.

    Returns:
        SignalResult mapping dimension -> state -> weight.
    """
    if not events:
        return _empty_signal()

    result: SignalResult = _empty_signal()
    change_count = len(events)

    # Frequent config changes suggest iterative/experimental approach
    if change_count >= 3:
        result["epistemic_style"]["speculating"] += 1.0
        result["interaction_agency"]["assumes_and_acts"] += 1.0

    # Any config changes suggest active environment management
    if change_count >= 1:
        result["risk_caution"]["checks_before_acting"] += 0.5

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_signal() -> SignalResult:
    """Return an empty signal result with all dimensions initialized.

    Uses defaultdict(float) so += works on missing keys.
    """
    return {
        "epistemic_style": defaultdict(float),
        "interaction_agency": defaultdict(float),
        "communication_register": defaultdict(float),
        "risk_caution": defaultdict(float),
    }


def merge_signal_results(*results: SignalResult) -> SignalResult:
    """Merge multiple signal results by summing weights per state.

    Args:
        results: Variable number of SignalResult dicts to merge.

    Returns:
        Combined SignalResult with summed weights.
    """
    merged = _empty_signal()
    for r in results:
        for dim, states in r.items():
            for state, weight in states.items():
                merged[dim][state] = merged[dim].get(state, 0.0) + weight
    return merged


# ---------------------------------------------------------------------------
# Signal-to-distribution conversion (Task 1.3)
# ---------------------------------------------------------------------------

def hook_signals_to_distributions(
    signals: SignalResult,
) -> dict[str, BehavioralDistribution]:
    """Convert merged hook signal weights into BehavioralDistribution objects.

    For each behavioral dimension, the signal weights are combined with
    a uniform prior (to avoid zero-mass states) and normalized into a
    proper probability distribution.

    Mapping rationale documented per dimension:

    epistemic_style:
        Tool selection patterns drive this. Read-heavy usage maps to
        confident (researched before acting). High tool diversity maps
        to speculating (exploratory approach). Low diversity with writes
        maps to confident (knows what to do).

    interaction_agency:
        Delegation patterns (Agent tool, subagents) drive this.
        High delegation maps to offers_options/defers_to_user.
        Heavy Bash usage maps to assumes_and_acts (direct action).

    communication_register:
        Prompt length and read/write ratio drive this.
        Short user prompts map to terse interaction style.
        Long prompts and read-heavy tool use map to thorough.

    risk_caution:
        Read-before-write patterns, test execution, and failure rates
        drive this. Test-before-commit maps to checks_before_acting.
        High failure rates without retries map to acts_immediately.

    Args:
        signals: Merged SignalResult from all extractors.

    Returns:
        Dict mapping dimension name to BehavioralDistribution.
    """
    dists: dict[str, BehavioralDistribution] = {}

    # Uniform prior weight prevents zero-mass states
    prior_weight = 0.1

    for dim in list_dimensions():
        states = list_states(dim)
        weights: dict[str, float] = {}

        dim_signals = signals.get(dim, {})

        for state in states:
            # Start with a small uniform prior
            w = prior_weight
            # Add any signal contribution for this state
            w += dim_signals.get(state, 0.0)
            weights[state] = w

        # Normalize to sum to 1.0
        total = sum(weights.values())
        if total > 0:
            weights = {s: v / total for s, v in weights.items()}
        else:
            # Fallback to uniform
            prob = 1.0 / len(states)
            weights = {s: prob for s in states}

        dists[dim] = BehavioralDistribution(dim, weights)

    return dists
