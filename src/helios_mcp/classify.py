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

# Matched against each segment of a compound command, so "ls && rm -rf build"
# is judged by its rm and not by its leading ls.
_READ_ONLY_CMD = re.compile(
    r"^\s*(?:cd(?:\s+\S+)?\s*$|(?:ls|cat|head|tail|less|wc|grep|rg|find|fd|tree|"
    r"pwd|echo|which|file|stat|du|df|sed\s+-n|awk|jq|diff|"
    r"git\s+(?:status|log|diff|show|branch|remote|rev-parse|blame|ls-files)|"
    r"gh\s+(?:pr|issue|run)\s+(?:view|list|diff|checks))\b)"
)
_SEGMENT_SPLIT = re.compile(r"&&|\|\||[;|\n]")
# Output redirection writes a file whatever the command is; 2>&1 and
# >/dev/null do not.
_WRITE_REDIRECT = re.compile(r">>?(?!\s*(?:&|/dev/null))")
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
        return bool(cmd) and (
            _WRITE_REDIRECT.search(cmd) is not None
            or any(
                not (_READ_ONLY_CMD.match(seg) or _VERIFY_CMD.search(seg))
                for seg in _segments(cmd)
            )
        )
    return False


def _segments(cmd: str) -> list[str]:
    return [seg for seg in (s.strip() for s in _SEGMENT_SPLIT.split(cmd)) if seg]


def is_inspection(call: ToolCall) -> bool:
    if call.name in _READ_ONLY_TOOLS:
        return True
    if call.name != "Bash":
        return False
    cmd = _command(call)
    segments = _segments(cmd)
    return (
        bool(segments)
        and _WRITE_REDIRECT.search(cmd) is None
        and all(_READ_ONLY_CMD.match(seg) for seg in segments)
    )


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


# ---------------------------------------------------------------------------
# Manner dimensions: structure, sycophancy, narration, specificity, pushback
# ---------------------------------------------------------------------------

_HEADER_LINE = re.compile(r"^\s{0,3}#{1,6}\s+\S|^\s*\*\*[^*\n]{2,60}\*\*:?\s*$")
_BULLET_LINE = re.compile(r"^\s*(?:[-*+•]|\d{1,2}[.)])\s+\S")
_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")
# A paragraph that opens with a bold label, like "**Tests.** All pass".
_BOLD_LEAD = re.compile(r"^\s*\*\*[^*\n]{2,80}\*\*\s*\S")
_FENCE_OPEN = re.compile(r"^\s*```", re.MULTILINE)

_FLATTERY = re.compile(
    r"\b(?:great (?:question|point|idea|catch|call|instinct)|"
    r"(?:excellent|good|fantastic|brilliant|interesting|insightful) "
    r"(?:question|point|idea|catch|call|observation|thinking)|"
    r"you'?re (?:absolutely|totally|completely|exactly) (?:right|correct)|"
    r"you (?:are|were) (?:absolutely|totally|completely) (?:right|correct)|"
    r"what a (?:great|good|fantastic)|love (?:this|that|the) (?:idea|approach)|"
    r"(?:that'?s|this is) (?:a )?(?:great|excellent|brilliant|fantastic|smart|"
    r"clever|wonderful)|happy to help|glad (?:i could|to) help|"
    r"you'?ve (?:done|built) (?:a )?(?:great|excellent|solid|impressive))\b",
    re.IGNORECASE,
)
_CANDID = re.compile(
    r"\b(?:(?:that|this|it) (?:won'?t|will not|doesn'?t|does not) work|"
    r"(?:that|this) is (?:wrong|incorrect|a bad idea|not (?:true|right|correct))|"
    r"i disagree|i'?d push back|wrong premise|the (?:real )?problem is|"
    r"(?:that|this) (?:breaks|is broken)|i wouldn'?t|i would not|"
    r"don'?t do (?:that|this)|"
    r"(?:is|was) a mistake|the premise|isn'?t (?:true|right|correct))\b",
    re.IGNORECASE,
)
_ANNOUNCE = re.compile(
    r"^\s*(?:let me|let'?s|i'?ll (?:now |first |start |go ahead )?|"
    r"i(?: am|'m) (?:going to|gonna|now going to)|now (?:i'?ll|let me|i will)|"
    r"first,? (?:i'?ll|let me)|next,? (?:i'?ll|let me)|i will (?:now )?|"
    r"time to|okay,? (?:let me|now|i'?ll)|now\b|next,|"
    r"(?:reading|writing|starting|checking|running|looking|verifying|updating|"
    r"adding|fixing|wiring|searching|inspecting) (?:the|with|at|a|it|all|for)\b)",
    re.IGNORECASE | re.MULTILINE,
)
_RECAP = re.compile(
    r"\b(?:in summary|to summari[sz]e|to recap|in short|in conclusion|"
    r"(?:here'?s|here is) (?:a )?(?:summary|recap|what i (?:did|changed))|"
    r"summary of (?:changes|what)|i'?ve (?:now )?(?:made|completed) the following|"
    r"all (?:done|set)[.!]|overall,)|^\s*#{1,6}\s*summary\b|^\s*\*\*summary\*\*",
    re.IGNORECASE | re.MULTILINE,
)
_CLOSER = re.compile(
    r"\b(?:hope (?:this|that) helps|let me know if (?:you|there|anything)|"
    r"feel free to|(?:is there )?anything else (?:i can|you'?d like)|"
    r"happy to (?:help|adjust|make|dig)|don'?t hesitate)\b",
    re.IGNORECASE,
)
_CONCRETE = re.compile(
    r"`[^`\n]+`|\b[\w.-]+/[\w./-]+|\b[\w-]+\.(?:py|ts|tsx|js|rs|go|md|json|yaml|yml|"
    r"toml|sh|c|h|cpp|java|rb)\b(?::\d+)?|:\d+\b|\b[a-z]+_[a-z_]+\b|"
    r"\b[a-z]+[A-Z]\w+\b|\b[0-9a-f]{7,40}\b|\b\d+(?:\.\d+)?\s?(?:%|ms|s|MB|GB|KB|x)?\b"
)
_VAGUE = re.compile(
    r"\b(?:various|several|some (?:issues|problems|changes|improvements)|"
    r"significant(?:ly)?|robust|comprehensive|seamless(?:ly)?|powerful|enhanced|"
    r"improved|optimal|better|cleaner|more efficient|best practices|"
    r"a (?:number|variety|lot) of|certain|appropriate(?:ly)?|properly|"
    r"overall|generally|things|stuff|aspects?)\b",
    re.IGNORECASE,
)
_PUSHBACK = re.compile(
    r"^\s*(?:no\b|nope\b|actually\b|but\b|wrong\b)|"
    r"\b(?:are you (?:sure|blind|kidding)|i don'?t think (?:so|that'?s|this is|you)|"
    r"i think (?:you|something|that'?s (?:wrong|not)|this is (?:wrong|not))|"
    r"you(?:'re| are) (?:confusing|mistaken|missing|wrong)|"
    r"you (?:missed|forgot|ignored|misunderstood|misread)|i (?:told|asked) you|"
    r"(?:is|was) the wrong (?:call|approach|choice)|i'?m not sure (?:you|that|this)|"
    r"how (?:the heck|the hell|did you)|why (?:did|would) you|"
    r"i disagree|that'?s (?:not (?:right|true|correct)|wrong|incorrect)|"
    r"you'?re wrong|isn'?t (?:that|it) (?:wrong|the case)|i'?m not convinced|"
    r"why not just|shouldn'?t (?:it|we|you) (?:be|just)|that can'?t be right|"
    r"doesn'?t (?:that|this) (?:break|contradict))",
    re.IGNORECASE,
)
_CAPITULATE = re.compile(
    r"\b(?:you'?re (?:absolutely |totally |completely )?right|"
    r"(?:my|sincere) apologies|i apologi[sz]e|"
    r"sorry(?: about| for)? (?:that|the confusion)|"
    r"good point|fair point|i stand corrected|my (?:mistake|bad))\b",
    re.IGNORECASE,
)
_REASONED = re.compile(
    r"\b(?:because|since|the reason|which means|i missed|i misread|i overlooked|"
    r"i was wrong (?:about|to)|that changes|so the|confirmed by|the (?:log|test|output|"
    r"code|trace) shows)\b",
    re.IGNORECASE,
)
_HOLD = re.compile(
    r"\b(?:i (?:still )?(?:think|believe) (?:the|it|this|that|we) .{0,40}"
    r"(?:is|should|correct|right)|i'?d (?:still )?keep|i stand by|"
    r"respectfully|that'?s not (?:quite )?(?:right|what)|actually,? (?:it|the|this)|"
    r"the (?:current|original) (?:approach|version) is (?:right|correct)|"
    r"still (?:correct|right|holds)|not (?:a|the) (?:bug|problem))\b",
    re.IGNORECASE,
)


def pushed_back(text: str) -> bool:
    """Whether a user message disputes what the agent said or did."""
    return bool(_PUSHBACK.search(text.strip()[:400]))


def classify_structure(text: str) -> tuple[dict[str, float], float]:
    counts = {"prose": 0.0, "light_structure": 0.0, "heavy_structure": 0.0}
    lines = [ln for ln in _FENCE.sub("\n", text).splitlines() if ln.strip()]
    if not lines:
        return counts, 0.0
    headers = sum(1 for ln in lines if _HEADER_LINE.match(ln))
    bullets = sum(1 for ln in lines if _BULLET_LINE.match(ln))
    tables = sum(1 for ln in lines if _TABLE_LINE.match(ln))
    # Code blocks and bold lead-ins are light structure: they mark a response
    # up without turning it into an outline.
    light = len(_FENCE_OPEN.findall(text)) // 2 + sum(
        1 for ln in lines if _BOLD_LEAD.match(ln)
    )
    marked = headers + bullets + tables
    share = marked / len(lines)
    if marked == 0 and light:
        counts["light_structure"] = 1.0 + 0.25 * min(light, 4)
        counts["prose"] = 0.5
    elif marked == 0:
        counts["prose"] = 1.0 + 0.25 * min(len(lines), 4)
    elif headers >= 2 or tables >= 3 or share > 0.5:
        counts["heavy_structure"] = 1.5 + 0.5 * min(headers, 3)
    else:
        counts["light_structure"] = 1.0
        counts["heavy_structure"] = share
        counts["prose"] = 1 - share
    # A one-line reply says little about how the agent structures prose.
    return counts, _saturate(len(lines) + 2.0 * marked, 4.0)


def classify_sycophancy(text: str) -> tuple[dict[str, float], float]:
    counts = {"candid": 0.0, "neutral": 0.0, "flattering": 0.0}
    body = prose(text)
    counts["flattering"] = 1.5 * min(len(_FLATTERY.findall(body)), 3)
    counts["candid"] = 1.0 * min(len(_CANDID.findall(body)), 3)
    # A plain report with nothing to praise or dispute says nothing about this
    # dimension, so the label is omitted rather than defaulted to neutral.
    return counts, _saturate(sum(counts.values()), 2.0)


def classify_narration(turn: AgentTurn) -> tuple[dict[str, float], float]:
    counts = dict.fromkeys(
        ("silent_action", "brief_signposting", "narrates_and_recaps"), 0.0
    )
    blocks = [prose(t) for t in turn.texts if t.strip()]
    if not blocks:
        return counts, 0.0
    announce = sum(len(_ANNOUNCE.findall(b)) for b in blocks)
    # "Fixing:" or "Writing the redirect:" before a tool call announces it.
    announce += sum(
        1 for b in blocks[:-1] if b.rstrip().endswith(":") and len(b.strip()) < 160
    )
    recap = len(_RECAP.findall(blocks[-1]))
    closer = len(_CLOSER.findall(blocks[-1]))
    if announce + recap + closer == 0:
        counts["silent_action"] = 0.5 + 0.25 * min(len(blocks), 4)
    else:
        counts["brief_signposting"] = 0.75 * min(announce, 2)
        counts["narrates_and_recaps"] = 0.5 * max(announce - 2, 0) + 1.5 * min(
            recap + closer, 3
        )
    return counts, _saturate(sum(counts.values()), 2.0)


def classify_specificity(text: str) -> tuple[dict[str, float], float]:
    counts = {"concrete": 0.0, "mixed": 0.0, "vague": 0.0}
    body = _FENCE.sub(" ", text)
    words = len(body.split())
    if words < 12:
        return counts, 0.0
    concrete = len(_CONCRETE.findall(body)) / words
    vague = len(_VAGUE.findall(body)) / words
    # Rates per word, squashed so that about one concrete token per 12 words
    # reads as concrete and one vague word per 25 reads as vague.
    c = min(concrete / 0.08, 1.5)
    v = min(vague / 0.04, 1.5)
    counts["concrete"] = max(c - v, 0.0)
    counts["vague"] = max(v - c, 0.0)
    counts["mixed"] = min(c, v) + (0.5 if c < 0.5 and v < 0.5 else 0.0)
    return counts, _saturate(min(words, 300) / 30, 3.0)


def classify_pushback(turn: AgentTurn) -> tuple[dict[str, float], float]:
    counts = {"holds_position": 0.0, "concedes_with_reason": 0.0, "capitulates": 0.0}
    prompt = turn.prompt
    if prompt is None or prompt.kind != "prompt" or not pushed_back(prompt.text):
        return counts, 0.0
    head = " ".join(sentences(turn.text)[:4])
    if not head:
        return counts, 0.0
    gave_in = bool(_CAPITULATE.search(head))
    reasoned = bool(_REASONED.search(head))
    if _HOLD.search(head) and not gave_in:
        counts["holds_position"] = 1.5
    elif gave_in and reasoned:
        counts["concedes_with_reason"] = 1.5
    elif gave_in:
        counts["capitulates"] = 1.5
    else:
        return counts, 0.0
    return counts, 0.5


Classifier = Callable[[AgentTurn], tuple[dict[str, float], float]]

# One scorer per dimension. A scorer for a dimension the taxonomy does not
# define is skipped, so dimensions can be added here ahead of the taxonomy.
CLASSIFIERS: dict[str, Classifier] = {
    "epistemic_style": lambda t: classify_epistemic(t.text),
    "interaction_agency": classify_agency,
    "communication_register": lambda t: classify_register(t.final_text),
    "risk_caution": classify_risk,
    "structure": lambda t: classify_structure(t.final_text),
    "sycophancy": lambda t: classify_sycophancy(t.text),
    "narration": classify_narration,
    "specificity": lambda t: classify_specificity(t.final_text),
    "pushback": classify_pushback,
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
