"""Behavioral observation engine for Helios v2.

Extracts behavioral signals from raw agent conversation messages
and maintains observed behavioral distributions per persona.

Four signal types (all used simultaneously):
1. Structural — measurable text properties (length, lists, questions, hedges, code)
2. Semantic intent — per-response intent classification from linguistic features
3. Decision points — moments where agent chose to act vs ask
4. User signals — re-prompts, corrections, acceptances inferred from conversation flow
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .distribution import BehavioralDistribution
from .taxonomy import list_dimensions, list_states

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HEDGE_WORDS: list[str] = [
    "probably", "perhaps", "might", "may", "could",
    "i think", "i believe", "not sure", "unclear", "possibly",
]

_CAVEAT_PHRASES: list[str] = [
    "however", "but note", "warning", "caution",
    "be careful", "important:", "note:",
]

_IGNORANCE_PHRASES: list[str] = [
    "i don't know", "i'm not sure", "i cannot", "i don't have", "unknown",
]

_SPECULATE_PHRASES: list[str] = [
    "perhaps", "imagine", "what if", "could be", "might mean", "hypothesis",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _assistant_messages(messages: list[dict]) -> list[str]:
    """Return content strings for all assistant messages."""
    return [m["content"] for m in messages if m.get("role") == "assistant"]


def _normalize_dict(d: dict[str, float]) -> dict[str, float]:
    """Normalize a dict of floats to sum to 1.0."""
    total = sum(d.values())
    if total <= 0.0:
        # Fall back to uniform
        n = len(d)
        return {k: 1.0 / n for k in d}
    return {k: v / total for k, v in d.items()}


def _contains_any(text: str, phrases: list[str]) -> bool:
    lower = text.lower()
    return any(phrase in lower for phrase in phrases)


def _has_list(text: str) -> bool:
    """True if any line starts with - or *."""
    return any(line.lstrip().startswith(("-", "*")) for line in text.splitlines())


def _has_code(text: str) -> bool:
    """True if response contains ``` or 4-space indented blocks."""
    if "```" in text:
        return True
    return any(line.startswith("    ") for line in text.splitlines())


def _word_count(text: str) -> int:
    return len(text.split())


# ---------------------------------------------------------------------------
# Signal extraction functions
# ---------------------------------------------------------------------------

def extract_structural(messages: list[dict]) -> dict[str, float]:
    """Compute scalar structural features from assistant messages.

    Args:
        messages: Conversation messages with 'role' and 'content' keys.

    Returns:
        Dict of scalar features: avg_length, list_rate, question_rate,
        hedge_rate, code_rate, caveat_rate.
    """
    assistant_msgs = _assistant_messages(messages)

    if not assistant_msgs:
        return {
            "avg_length": 0.0,
            "list_rate": 0.0,
            "question_rate": 0.0,
            "hedge_rate": 0.0,
            "code_rate": 0.0,
            "caveat_rate": 0.0,
        }

    n = len(assistant_msgs)
    total_words = sum(_word_count(m) for m in assistant_msgs)
    list_count = sum(1 for m in assistant_msgs if _has_list(m))
    question_count = sum(1 for m in assistant_msgs if "?" in m)
    hedge_count = sum(1 for m in assistant_msgs if _contains_any(m, _HEDGE_WORDS))
    code_count = sum(1 for m in assistant_msgs if _has_code(m))
    caveat_count = sum(1 for m in assistant_msgs if _contains_any(m, _CAVEAT_PHRASES))

    return {
        "avg_length": total_words / n,
        "list_rate": list_count / n,
        "question_rate": question_count / n,
        "hedge_rate": hedge_count / n,
        "code_rate": code_count / n,
        "caveat_rate": caveat_count / n,
    }


def extract_semantic(messages: list[dict]) -> list[str]:
    """Classify the dominant epistemic intent of each assistant message.

    Args:
        messages: Conversation messages with 'role' and 'content' keys.

    Returns:
        List of classification strings, one per assistant message.
        Values: "confident" | "hedging" | "admits_ignorance" | "speculating"
    """
    results: list[str] = []
    for m in messages:
        if m.get("role") != "assistant":
            continue
        content = m["content"]
        lower = content.lower()

        if _contains_any(content, _IGNORANCE_PHRASES):
            results.append("admits_ignorance")
        elif any(phrase in lower for phrase in ["perhaps", "imagine", "what if", "could be", "might mean", "hypothesis"]):
            results.append("speculating")
        elif _contains_any(content, _HEDGE_WORDS):
            results.append("hedging")
        else:
            results.append("confident")

    return results


def extract_decision_points(messages: list[dict]) -> list[str]:
    """Classify the agency pattern of each assistant message.

    Args:
        messages: Conversation messages with 'role' and 'content' keys.

    Returns:
        List of classification strings, one per assistant message.
        Values: "asks_first" | "offers_options" | "assumes_and_acts" |
                "decides_unilaterally" | "defers_to_user"
    """
    results: list[str] = []
    for m in messages:
        if m.get("role") != "assistant":
            continue
        content = m["content"]
        lower = content.lower()

        # Check defers_to_user first (explicit deference phrases)
        if any(phrase in lower for phrase in ["up to you", "your call", "whatever you prefer", "as you wish"]):
            results.append("defers_to_user")
        # Check decides_unilaterally
        elif any(phrase in lower for phrase in ["i will", "i'm going to", "i've decided", "i'll just"]):
            results.append("decides_unilaterally")
        # Check offers_options (options keywords or numbered list)
        elif any(phrase in lower for phrase in ["option", "alternative", "you could", "or you could"]) or (
            "1." in content and "2." in content
        ):
            results.append("offers_options")
        # Check asks_first: ends with ? or multiple questions
        elif content.rstrip().endswith("?") or content.count("?") >= 2:
            results.append("asks_first")
        # Default: assumes_and_acts
        else:
            results.append("assumes_and_acts")

    return results


def extract_user_signals(messages: list[dict]) -> list[str]:
    """Classify user messages that follow assistant messages.

    Args:
        messages: Conversation messages with 'role' and 'content' keys.

    Returns:
        List of classification strings, one per user message that follows
        an assistant message.
        Values: "correction" | "re_prompt" | "acceptance" | "elaboration_request"
    """
    results: list[str] = []
    prev_role: str | None = None

    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        lower = content.lower().strip()

        if role == "user" and prev_role == "assistant":
            # correction
            if any(lower.startswith(prefix) for prefix in [
                "no", "actually", "that's wrong", "incorrect", "not quite", "wait"
            ]):
                results.append("correction")
            # elaboration_request
            elif any(phrase in lower for phrase in [
                "more detail", "can you expand", "tell me more", "elaborate"
            ]):
                results.append("elaboration_request")
            # re_prompt: short message + clarification request
            elif _word_count(content) < 10 and any(phrase in lower for phrase in [
                "what do you mean", "can you explain", "huh?", "what?"
            ]):
                results.append("re_prompt")
            # acceptance: forward-moving signals
            elif any(phrase in lower for phrase in [
                "thanks", "ok", "got it", "great", "perfect", "let's"
            ]):
                results.append("acceptance")
            else:
                results.append("acceptance")  # default: moving forward

        prev_role = role

    return results


# ---------------------------------------------------------------------------
# Signal-to-distribution conversion
# ---------------------------------------------------------------------------

def signals_to_distributions(
    structural: dict[str, float],
    semantic_intents: list[str],
    decision_points: list[str],
    user_signals: list[str],
) -> dict[str, BehavioralDistribution]:
    """Convert extracted signals into one BehavioralDistribution per dimension.

    Args:
        structural: Output of extract_structural().
        semantic_intents: Output of extract_semantic().
        decision_points: Output of extract_decision_points().
        user_signals: Output of extract_user_signals().

    Returns:
        Dict mapping dimension name → BehavioralDistribution.
    """
    dists: dict[str, BehavioralDistribution] = {}

    # ------------------------------------------------------------------
    # epistemic_style
    # ------------------------------------------------------------------
    ep_states = list_states("epistemic_style")
    ep_counts: dict[str, float] = {s: 0.0 for s in ep_states}
    for intent in semantic_intents:
        if intent in ep_counts:
            ep_counts[intent] += 1.0
    # Add structural hedge_rate as extra weight toward "hedging"
    ep_counts["hedging"] += structural.get("hedge_rate", 0.0)
    # Ensure at least a tiny base to avoid all-zero
    for s in ep_states:
        ep_counts[s] = max(ep_counts[s], 1e-6)
    dists["epistemic_style"] = BehavioralDistribution(
        "epistemic_style", _normalize_dict(ep_counts)
    )

    # ------------------------------------------------------------------
    # interaction_agency
    # ------------------------------------------------------------------
    ag_states = list_states("interaction_agency")
    ag_counts: dict[str, float] = {s: 0.0 for s in ag_states}
    for dp in decision_points:
        if dp in ag_counts:
            ag_counts[dp] += 1.0
    for s in ag_states:
        ag_counts[s] = max(ag_counts[s], 1e-6)
    dists["interaction_agency"] = BehavioralDistribution(
        "interaction_agency", _normalize_dict(ag_counts)
    )

    # ------------------------------------------------------------------
    # communication_register
    # ------------------------------------------------------------------
    reg_states = list_states("communication_register")
    reg_weights: dict[str, float] = {s: 0.0 for s in reg_states}

    avg_len = structural.get("avg_length", 0.0)
    code_rate = structural.get("code_rate", 0.0)
    list_rate = structural.get("list_rate", 0.0)

    if avg_len > 200:
        reg_weights["thorough"] += 3.0
    elif avg_len < 50:
        reg_weights["terse"] += 3.0
    else:
        reg_weights["moderate"] += 3.0

    if code_rate > 0.5:
        reg_weights["technical_dense"] += 2.0

    if list_rate > 0.5 and avg_len > 100:
        reg_weights["thorough"] += 1.0

    # plain_accessible gets a small base
    reg_weights["plain_accessible"] += 0.1

    for s in reg_states:
        reg_weights[s] = max(reg_weights[s], 1e-6)
    dists["communication_register"] = BehavioralDistribution(
        "communication_register", _normalize_dict(reg_weights)
    )

    # ------------------------------------------------------------------
    # risk_caution
    # ------------------------------------------------------------------
    rc_states = list_states("risk_caution")
    rc_weights: dict[str, float] = {s: 0.0 for s in rc_states}

    caveat_rate = structural.get("caveat_rate", 0.0)
    question_rate = structural.get("question_rate", 0.0)

    correction_count = user_signals.count("correction")
    acceptance_count = user_signals.count("acceptance")

    if caveat_rate > 0.5:
        rc_weights["warns_frequently"] += 3.0
    if correction_count > acceptance_count:
        rc_weights["refuses_ambiguity"] += 2.0
    if question_rate > 0.5:
        rc_weights["checks_before_acting"] += 2.0
    if all(v == 0.0 for v in rc_weights.values()):
        rc_weights["acts_immediately"] += 3.0

    for s in rc_states:
        rc_weights[s] = max(rc_weights[s], 1e-6)
    dists["risk_caution"] = BehavioralDistribution(
        "risk_caution", _normalize_dict(rc_weights)
    )

    return dists


# ---------------------------------------------------------------------------
# BehavioralObserver class
# ---------------------------------------------------------------------------

class BehavioralObserver:
    """Extracts behavioral signals from conversations and persists observations per persona.

    Observations are stored to ~/.helios/observations/{persona}.json atomically so
    they accumulate across MCP tool calls (which each create a fresh instance).
    """

    def __init__(self, helios_dir: Path | None = None) -> None:
        self._helios_dir = helios_dir
        self._observations: dict[str, list[dict]] = {}

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _obs_path(self, persona_name: str) -> Path | None:
        if self._helios_dir is None:
            return None
        return self._helios_dir / "observations" / f"{persona_name}.json"

    def _load(self, persona_name: str) -> None:
        """Load persisted observations for a persona into memory."""
        path = self._obs_path(persona_name)
        if path is None or not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                self._observations[persona_name] = data
        except Exception:
            pass  # Corrupt file: start fresh

    def _save(self, persona_name: str) -> None:
        """Atomically write observations for a persona to disk."""
        path = self._obs_path(persona_name)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._observations.get(persona_name, [])).encode()
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            os.write(fd, payload)
            os.fsync(fd)
            os.close(fd)
            os.replace(tmp, path)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def observe(
        self, persona_name: str, messages: list[dict]
    ) -> dict[str, BehavioralDistribution]:
        """Process a conversation, persist the observation, and return distributions.

        Args:
            persona_name: Name of the persona being observed.
            messages: List of dicts with 'role' and 'content' keys.

        Returns:
            Dict mapping dimension name → BehavioralDistribution.
        """
        # Load existing observations from disk before appending
        if persona_name not in self._observations:
            self._load(persona_name)
        if persona_name not in self._observations:
            self._observations[persona_name] = []

        structural = extract_structural(messages)
        semantic = extract_semantic(messages)
        decisions = extract_decision_points(messages)
        user_sigs = extract_user_signals(messages)
        dists = signals_to_distributions(structural, semantic, decisions, user_sigs)

        self._observations[persona_name].append({
            "structural": structural,
            "semantic": semantic,
            "decisions": decisions,
            "user_signals": user_sigs,
        })

        self._save(persona_name)
        return dists

    def get_observation_count(self, persona_name: str) -> int:
        """Return the number of conversations observed for a persona."""
        if persona_name not in self._observations:
            self._load(persona_name)
        return len(self._observations.get(persona_name, []))

    def get_accumulated_distributions(
        self, persona_name: str
    ) -> dict[str, BehavioralDistribution]:
        """Merge all stored observations into a single set of distributions."""
        if persona_name not in self._observations:
            self._load(persona_name)

        obs_list = self._observations.get(persona_name, [])

        if not obs_list:
            return {
                dim: BehavioralDistribution.uniform(dim)
                for dim in list_dimensions()
            }

        acc_structural: dict[str, float] = {}
        acc_semantic: list[str] = []
        acc_decisions: list[str] = []
        acc_user_signals: list[str] = []

        for obs in obs_list:
            for key, val in obs["structural"].items():
                acc_structural[key] = acc_structural.get(key, 0.0) + val
            acc_semantic.extend(obs["semantic"])
            acc_decisions.extend(obs["decisions"])
            acc_user_signals.extend(obs["user_signals"])

        n = len(obs_list)
        avg_structural = {k: v / n for k, v in acc_structural.items()}

        return signals_to_distributions(
            avg_structural, acc_semantic, acc_decisions, acc_user_signals
        )
