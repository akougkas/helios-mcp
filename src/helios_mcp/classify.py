"""Heuristic per-turn behavioral classifier.

Produces a soft label over each dimension's states for one agent turn, plus a
confidence per dimension. Labels are smoothed evidence counts, so a single
turn never collapses to a point mass. A dimension with no evidence is omitted
rather than reported as uniform, because a uniform label would drag the
estimator toward uniform on every quiet turn.

Evidence comes from the turn's visible prose (code stripped) and from the
shape of its tool calls. Everything here is a fast fallback that the LLM
labeler overrides when it runs.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from .taxonomy import list_dimensions, list_states
from .transcript import AgentTurn, ToolCall

# A label is the evidence proportions scaled to a fixed mass plus a small
# smoothing count, so a long turn is not sharper than a short one with the same
# mix. How much evidence there was goes into confidence instead, which the
# estimator uses as the observation weight.
_LABEL_MASS = 4.0
_ALPHA = 0.25
# Dimensions whose confidence falls below this are dropped from the output.
MIN_CONFIDENCE = 0.15

_READ_ONLY_TOOLS = frozenset({
    "Read", "Grep", "Glob", "LS", "WebFetch", "WebSearch", "NotebookRead",
    "TodoWrite", "TaskOutput", "ToolSearch", "ListMcpResourcesTool",
    "ReadMcpResourceTool", "Skill",
})
_MUTATING_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
_ASK_TOOLS = frozenset({"AskUserQuestion"})
_PLAN_TOOLS = frozenset({"ExitPlanMode", "EnterPlanMode"})

_READ_ONLY_CMD = re.compile(
    r"^\s*(?:cd\s+\S+\s*&&\s*)?(?:ls|cat|head|tail|less|wc|grep|rg|find|fd|tree|pwd|"
    r"echo|which|file|stat|du|df|sed\s+-n|awk|jq|diff|"
    r"git\s+(?:status|log|diff|show|branch|remote|rev-parse|blame|ls-files)|"
    r"gh\s+(?:pr|issue|run)\s+(?:view|list|diff|checks))\b"
)
_VERIFY_CMD = re.compile(
    r"\b(?:pytest|jest|vitest|mocha|cargo\s+(?:test|check|clippy)|go\s+(?:test|vet)|"
    r"npm\s+(?:run\s+)?(?:test|lint|typecheck|check)|pnpm\s+(?:test|lint)|"
    r"ruff\s+check|mypy|tsc|eslint|make\s+(?:test|check|lint))\b"
)
_DESTRUCTIVE_CMD = re.compile(
    r"\brm\s+-[a-z]*r[a-z]*f|\brm\s+-[a-z]*f[a-z]*r|git\s+push\s+(?:-f|--force)|"
    r"git\s+reset\s+--hard|git\s+clean\s+-[a-z]*f|git\s+checkout\s+--\s|"
    r"\bdrop\s+(?:table|database)\b|\bmkfs\b|\bdd\s+if=|git\s+branch\s+-D|"
    r"\bkill\s+-9\b|\bsystemctl\s+(?:stop|disable)\b",
    re.IGNORECASE,
)

_HEDGE = re.compile(
    r"\b(?:i think|i believe|probably|likely|possibly|perhaps|it seems|seems to|"
    r"appears to|might be|may be|could be|should work|i suspect|not entirely sure|"
    r"if i understand|as far as i can tell|presumably)\b",
    re.IGNORECASE,
)
_IGNORANCE = re.compile(
    r"\b(?:i don't know|i do not know|i'm not sure|i am not sure|i can't tell|"
    r"i cannot tell|i couldn't find|i could not find|i don't have (?:access|a way)|"
    r"no way to (?:verify|know|tell)|unclear to me|i can't verify|"
    r"i haven't been able to|i was unable to|i don't see)\b",
    re.IGNORECASE,
)
_SPECULATE = re.compile(
    r"\b(?:my guess|i'd guess|best guess|hypothes[ie]s|one possibility|"
    r"one explanation|what if|in theory|speculat\w*|theoretically|"
    r"my hunch|plausibl[ey])\b",
    re.IGNORECASE,
)
_ASKS = re.compile(
    r"\b(?:should i|shall i|do you want(?: me)?|would you like(?: me)?|want me to|"
    r"can you confirm|could you clarify|which (?:one|option|approach) (?:do|would) you|"
    r"let me know (?:if|whether|which)|before i (?:proceed|continue|start))\b",
    re.IGNORECASE,
)
_OPTIONS = re.compile(
    r"\b(?:option\s+(?:[a-d1-4])\b|two (?:options|ways|approaches)|"
    r"three (?:options|ways|approaches)|alternatively|the alternative|"
    r"either\b.{1,80}\bor\b|trade-?offs?|you could (?:also|either))",
    re.IGNORECASE,
)
_DEFERS = re.compile(
    r"\b(?:up to you|your call|your choice|whatever you prefer|as you prefer|"
    r"i'll wait for|waiting for your|let me know how you(?:'d| would) like|"
    r"happy to (?:go|do) (?:either|whichever))\b",
    re.IGNORECASE,
)
_ASSUMES = re.compile(
    r"\b(?:assuming|i assumed|i'll assume|i went with|i took .{1,30} to mean|"
    r"defaulting to)\b",
    re.IGNORECASE,
)
_UNILATERAL = re.compile(
    r"\b(?:i decided|i went ahead|i chose to|i also (?:went|took the liberty)|"
    r"took the liberty|while i was (?:at it|there))\b",
    re.IGNORECASE,
)
_WARN = re.compile(
    r"(?:\bwarning\b|\bcaution\b|\bcareful\b|\bheads[- ]up\b|\bcaveat\b|"
    r"\brisk(?:y|s)?\b|\birreversible\b|\bdestructive\b|\bbreaking change\b|"
    r"\bwill (?:delete|overwrite|remove)\b|\bdata loss\b|\bbe aware\b|\bnote that\b)",
    re.IGNORECASE,
)
_CLARIFY = re.compile(
    r"\b(?:unclear|ambiguous|clarify|which (?:one|file|branch|version) do you mean|"
    r"not sure what you mean|need more (?:context|information|details))\b",
    re.IGNORECASE,
)
_PLAIN = re.compile(
    r"\b(?:in other words|put simply|simply put|basically|think of it (?:as|like)|"
    r"in plain (?:terms|english)|for example|imagine)\b",
    re.IGNORECASE,
)

_FENCE = re.compile(r"```.*?(?:```|\Z)", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_TECH_TOKEN = re.compile(
    r"`[^`\n]+`|\b[\w.-]+/[\w./-]+|\b\w+\.(?:py|ts|js|rs|go|md|json|yaml|toml|sh)\b|"
    r"\b[a-z]+_[a-z_]+\b|\b[a-z]+[A-Z]\w+\b|--[a-z][\w-]+|\b\d+(?:\.\d+)?\s?(?:ms|s|MB|GB|KB)\b"
)


@dataclass(frozen=True)
class TurnLabels:
    """Soft labels and per-dimension confidence for one turn."""

    labels: dict[str, dict[str, float]]
    confidence: dict[str, float]

    @property
    def overall_confidence(self) -> float:
        if not self.confidence:
            return 0.0
        return sum(self.confidence.values()) / len(self.confidence)


def _soft(dim: str, counts: dict[str, float]) -> dict[str, float]:
    states = list_states(dim)
    clipped = {s: max(counts.get(s, 0.0), 0.0) for s in states}
    mass = sum(clipped.values()) or 1.0
    raw = {s: _LABEL_MASS * v / mass + _ALPHA for s, v in clipped.items()}
    total = sum(raw.values())
    return {s: v / total for s, v in raw.items()}


def _saturate(evidence: float, half: float) -> float:
    """Map an evidence mass to a confidence in [0, 0.9] that is 0.45 at ``half``."""
    if evidence <= 0:
        return 0.0
    return 0.9 * evidence / (evidence + half)


def prose(text: str) -> str:
    """Text with code blocks removed and inline code kept as a placeholder."""
    return _INLINE_CODE.sub("CODE", _FENCE.sub(" ", text))


def sentences(text: str) -> list[str]:
    parts = (p.strip() for p in _SENTENCE_SPLIT.split(prose(text)))
    return [s for s in parts if len(s) > 3]


def _command(call: ToolCall) -> str:
    cmd = call.input.get("command")
    return cmd if isinstance(cmd, str) else ""


def is_mutating(call: ToolCall) -> bool:
    if call.name in _MUTATING_TOOLS:
        return True
    if call.name == "Bash":
        cmd = _command(call)
        return bool(cmd) and not (
            _READ_ONLY_CMD.match(cmd) or _VERIFY_CMD.search(cmd)
        )
    return False


def is_inspection(call: ToolCall) -> bool:
    if call.name in _READ_ONLY_TOOLS:
        return True
    return call.name == "Bash" and bool(_READ_ONLY_CMD.match(_command(call)))


def is_verification(call: ToolCall) -> bool:
    return call.name == "Bash" and bool(_VERIFY_CMD.search(_command(call)))


def is_destructive(call: ToolCall) -> bool:
    return call.name == "Bash" and bool(_DESTRUCTIVE_CMD.search(_command(call)))


def classify_epistemic(text: str) -> tuple[dict[str, float], float]:
    counts = dict.fromkeys(list_states("epistemic_style"), 0.0)
    sents = sentences(text)
    for s in sents:
        if _IGNORANCE.search(s):
            counts["admits_ignorance"] += 1
        elif _SPECULATE.search(s):
            counts["speculating"] += 1
        elif _HEDGE.search(s):
            counts["hedging"] += 1
        elif not s.rstrip().endswith("?"):
            counts["confident"] += 0.5
    # Unmarked declaratives are weak evidence of confidence: absence of a hedge
    # is not as informative as the presence of one.
    return counts, _saturate(sum(counts.values()), 4.0)


def classify_agency(turn: AgentTurn) -> tuple[dict[str, float], float]:
    counts = dict.fromkeys(list_states("interaction_agency"), 0.0)
    text = prose(turn.text)
    final = prose(turn.final_text)
    acted = any(is_mutating(c) for c in turn.tool_calls)
    asked_tool = [c for c in turn.tool_calls if c.name in _ASK_TOOLS]

    for call in asked_tool:
        questions = call.input.get("questions")
        n_opts = 0
        if isinstance(questions, list):
            for q in questions:
                opts = q.get("options") if isinstance(q, dict) else None
                n_opts = max(n_opts, len(opts) if isinstance(opts, list) else 0)
        counts["asks_first"] += 1.5
        if n_opts >= 2:
            counts["offers_options"] += 1.0

    ends_with_question = final.rstrip().endswith("?")
    asks = len(_ASKS.findall(final))
    if not acted and (asks or ends_with_question):
        counts["asks_first"] += 1.0 + 0.5 * min(asks, 2)
    elif asks:
        counts["asks_first"] += 0.5

    counts["offers_options"] += min(len(_OPTIONS.findall(text)), 3) * 0.75
    counts["defers_to_user"] += min(len(_DEFERS.findall(text)), 2) * 1.0
    counts["assumes_and_acts"] += min(len(_ASSUMES.findall(text)), 2) * 1.0
    counts["decides_unilaterally"] += min(len(_UNILATERAL.findall(text)), 2) * 1.0

    if acted:
        n_mut = sum(1 for c in turn.tool_calls if is_mutating(c))
        counts["assumes_and_acts"] += 1.0 + 0.25 * math.log1p(n_mut)
    return counts, _saturate(sum(counts.values()), 2.0)


def classify_register(text: str) -> tuple[dict[str, float], float]:
    counts = dict.fromkeys(list_states("communication_register"), 0.0)
    body = text.strip()
    if not body:
        return counts, 0.0
    words = len(prose(body).split())
    # Length membership is smooth in log space so a 90-word reply sits between
    # terse and moderate instead of snapping to one of them.
    lw = math.log(max(words, 1))
    length = {
        "terse": math.exp(-((lw - math.log(25)) ** 2) / 0.6),
        "moderate": math.exp(-((lw - math.log(130)) ** 2) / 0.5),
        "thorough": math.exp(-((lw - math.log(500)) ** 2) / 0.6),
    }
    if words < 25:
        length["terse"] = 1.0
    if words > 500:
        length["thorough"] = 1.0
    ltotal = sum(length.values()) or 1.0

    tech = len(_TECH_TOKEN.findall(body)) / max(words, 1)
    tech_w = 1 / (1 + math.exp(-(tech - 0.08) / 0.025))
    plain_w = min(len(_PLAIN.findall(body)), 3) / 3 * (1 - tech_w)
    style_share = 0.4 * max(tech_w, plain_w)

    for s, v in length.items():
        counts[s] = 3.0 * (1 - style_share) * v / ltotal
    counts["technical_dense"] = 3.0 * 0.4 * tech_w if tech_w >= plain_w else 0.0
    counts["plain_accessible"] = 3.0 * 0.4 * plain_w if plain_w > tech_w else 0.0
    # Any final message is real evidence of register, even a one-liner.
    return counts, _saturate(1.0 + min(words, 400) / 40, 1.5)


def classify_risk(turn: AgentTurn) -> tuple[dict[str, float], float]:
    counts = dict.fromkeys(list_states("risk_caution"), 0.0)
    inspected = False
    verified_after_change = False
    changed = False
    for call in turn.tool_calls:
        if is_inspection(call):
            inspected = True
        elif is_verification(call):
            if changed:
                verified_after_change = True
            inspected = True
        elif is_mutating(call):
            if is_destructive(call):
                counts["acts_immediately"] += 1.5
            elif inspected:
                counts["checks_before_acting"] += 0.5
            else:
                counts["acts_immediately"] += 0.75
            changed = True
    if verified_after_change:
        counts["checks_before_acting"] += 1.0
    counts["acts_immediately"] = min(counts["acts_immediately"], 3.0)
    counts["checks_before_acting"] = min(counts["checks_before_acting"], 3.0)

    text = prose(turn.text)
    counts["warns_frequently"] += min(len(_WARN.findall(text)), 3) * 0.75
    if any(c.name in _ASK_TOOLS or c.name in _PLAN_TOOLS for c in turn.tool_calls):
        counts["checks_before_acting"] += 1.0
    final = prose(turn.final_text).rstrip()
    if not changed and final.endswith("?") and _CLARIFY.search(final):
        counts["refuses_ambiguity"] += 1.5
    return counts, _saturate(sum(counts.values()), 2.0)


Classifier = Callable[[AgentTurn], tuple[dict[str, float], float]]

# One scorer per dimension. A scorer for a dimension the taxonomy does not
# define is skipped, so dimensions can be added here ahead of the taxonomy.
CLASSIFIERS: dict[str, Classifier] = {
    "epistemic_style": lambda t: classify_epistemic(t.text),
    "interaction_agency": classify_agency,
    "communication_register": lambda t: classify_register(t.final_text),
    "risk_caution": classify_risk,
}


def classify_turn(turn: AgentTurn) -> TurnLabels:
    """Soft labels for one agent turn. Dimensions without evidence are omitted."""
    known = set(list_dimensions())
    labels: dict[str, dict[str, float]] = {}
    confidence: dict[str, float] = {}
    for dim, scorer in CLASSIFIERS.items():
        if dim not in known:
            continue
        counts, conf = scorer(turn)
        if conf < MIN_CONFIDENCE:
            continue
        labels[dim] = _soft(dim, counts)
        confidence[dim] = round(conf, 4)
    return TurnLabels(labels=labels, confidence=confidence)
