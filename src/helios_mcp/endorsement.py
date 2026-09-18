"""Judge how the user received an agent turn.

The endorsed posterior is learned from what happens right after a turn: the
next typed prompt, an interrupt, a denied tool call, or a message queued while
the turn was still running. Each turn gets a graded endorsement in [-1, 1] and
an optional ``correction_hint`` naming the state the user asked for.

Grades:
    +1.0  explicit approval ("perfect", "approved", "do it")
    +0.5  the user moved on without objecting
     0.0  no human judgment followed (a task notification or slash command),
          a standing style preference with no complaint attached, or the
          outcome was wrong ("still failing") without a behavior complaint
    -1.0  correction, interrupt or denied tool call

The estimator treats any negative grade as a behavior correction, so an
outcome complaint stays at zero rather than pushing style mass around.
    None  nothing followed the turn yet
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .classify import classify_turn
from .taxonomy import list_dimensions
from .transcript import AgentTurn

# A requested state holding less than this much of the turn's own label means
# the request contradicts what the agent just did.
_CONTRADICTION = 0.3

Kind = Literal[
    "endorsed", "continued", "neutral", "failed", "corrected",
    "interrupted", "denied", "none",
]


@dataclass(frozen=True)
class Endorsement:
    value: float | None
    kind: Kind
    correction_hint: dict[str, str] | None = None


@dataclass(frozen=True)
class _HintRule:
    pattern: re.Pattern[str]
    dimension: str
    state: str
    complaint: bool  # True when the phrase criticizes what just happened


def _rule(pattern: str, dim: str, state: str, complaint: bool) -> _HintRule:
    return _HintRule(re.compile(pattern, re.IGNORECASE), dim, state, complaint)


_REG = "communication_register"
_AGENCY = "interaction_agency"
_RISK = "risk_caution"
_EPI = "epistemic_style"
_STRUCT = "structure"
_SYCO = "sycophancy"
_NARR = "narration"
_SPEC = "specificity"
_PUSH = "pushback"

_HINT_RULES: tuple[_HintRule, ...] = (
    _rule(r"\b(?:too long|too verbose|too wordy|wall of text|shorter|"
          r"less verbose|fewer words|stop explaining|tl;?dr)\b", _REG, "terse", True),
    _rule(r"\b(?:be (?:more )?(?:concise|brief|terse)|keep it (?:short|brief|tight)|"
          r"briefly|brief (?:summary|update|answer)|one line|in a sentence|"
          r"short answer|"
          r"just the answer)\b", _REG, "terse", False),
    _rule(r"\b(?:too short|too terse|more detail|more details|elaborate|"
          r"explain (?:more|why|in detail)|walk me through|expand on)\b",
          _REG, "thorough", False),
    _rule(r"\b(?:i (?:am|'m) (?:entirely |completely |totally )?lost|"
          r"i (?:do not|don't) (?:understand|follow)|what does (?:that|this) mean|"
          r"too much jargon|less jargon)\b", _REG, "plain_accessible", True),
    _rule(r"\b(?:(?:explain|report|say|put|tell me)\b.{0,40}\bsimply|simpler|"
          r"in simple terms|plain (?:english|language|terms|simple)|eli5)\b",
          _REG, "plain_accessible", False),
    _rule(r"\b(?:skip the basics|more technical|i know what .{1,30} is)\b",
          _REG, "technical_dense", False),
    _rule(r"\b(?:just do it|stop asking|don'?t ask|no need to ask|"
          r"(?:you )?(?:do not|don't) need to ask|what are you waiting for|"
          r"why are you (?:asking|waiting)|timebox|"
          r"you have enough (?:info\w*|context|data|to (?:go|start|proceed|write))|"
          r"stop (?:reading|exploring|investigating|researching|analy[sz]ing|planning)|"
          r"enough (?:reading|research|exploring|planning))\b",
          _AGENCY, "assumes_and_acts", True),
    _rule(r"\b(?:do it yourself|take control|i trust you|your call)\b",
          _AGENCY, "assumes_and_acts", False),
    _rule(r"\b(?:you should have (?:asked|checked)|why didn'?t you (?:ask|check)|"
          r"without (?:asking|checking with) me(?: first)?)\b",
          _AGENCY, "asks_first", True),
    _rule(r"\b(?:ask (?:me )?(?:first|before)|check with me|confirm with me|"
          r"don'?t do anything (?:without|until))\b", _AGENCY, "asks_first", False),
    _rule(r"\b(?:give me (?:some |a few )?options|what are (?:my|the) options|"
          r"pros and cons|alternatives\?)", _AGENCY, "offers_options", False),
    _rule(r"\b(?:you decide|use your (?:own )?judgment|up to you)\b",
          _AGENCY, "decides_unilaterally", False),
    _rule(r"\b(?:let me decide|i(?:'ll| will) decide|my call|do as i say|"
          r"you will do as i say)\b", _AGENCY, "defers_to_user", True),
    _rule(r"\b(?:did you (?:test|check|verify)|you broke)\b",
          _RISK, "checks_before_acting", True),
    _rule(r"\b(?:be careful|double[- ]check|verify (?:first|before)|"
          r"test (?:it )?before|check first|"
          r"(?:check with me|ask(?: me)?|confirm(?: with me)?)(?: first)? before "
          r"(?:you |i |we )?(?:chang|edit|delet|modif|touch|writ|remov|run|"
          r"commit|push|deploy))",
          _RISK, "checks_before_acting", False),
    _rule(r"\b(?:stop warning|skip the (?:caveats|warnings)|too cautious|"
          r"stop being (?:so )?careful|move faster)\b",
          _RISK, "acts_immediately", True),
    _rule(r"\b(?:stop hedging|don'?t hedge|be (?:more )?(?:direct|decisive)|"
          r"commit to an answer)\b", _EPI, "confident", True),
    _rule(r"\b(?:don'?t (?:make (?:things|stuff) up|guess)|you'?re guessing|"
          r"made (?:that|it|this) up|hallucinat\w*|if you don'?t know,? say)\b",
          _EPI, "admits_ignorance", True),
    _rule(r"\b(?:just say it|say it plainly)\b", _EPI, "confident", True),
    _rule(r"\b(?:too many (?:bullets|bullet points|headers|headings|tables|lists)|"
          r"stop (?:using|with the) (?:bullets|bullet points|headers|headings|tables)|"
          r"no (?:more )?(?:bullets|bullet points|headers|headings)|fewer bullets|"
          r"less formatting)\b", _STRUCT, "prose", True),
    _rule(r"\b(?:(?:write|answer|respond) in prose|as prose|in paragraphs)\b",
          _STRUCT, "prose", False),
    _rule(r"\b(?:don'?t flatter|stop (?:flattering|praising|sucking up|"
          r"being (?:so )?sycophantic|telling me i'?m (?:absolutely )?right)|"
          r"no (?:flattery|praise)|skip the (?:praise|compliments|flattery)|"
          r"sycophan\w*)", _SYCO, "candid", True),
    _rule(r"\b(?:stop (?:summari[sz]ing|recapping|narrating|announcing)|"
          r"don'?t (?:summari[sz]e|recap|narrate|announce)|no (?:recap|summary) "
          r"(?:at the end|needed)|skip the (?:recap|summary|preamble)|"
          r"get to the point|cut to the chase)\b", _NARR, "silent_action", True),
    _rule(r"\b(?:too vague|be (?:more )?(?:specific|concrete)|"
          r"(?:with|give me|cite) (?:the )?(?:file paths|line numbers|numbers))\b",
          _SPEC, "concrete", False),
    _rule(r"\b(?:stop agreeing|don'?t (?:just )?agree with (?:me|everything)|"
          r"push back (?:if|when)|tell me (?:if|when) i'?m wrong|"
          r"stop caving|don'?t cave)\b", _PUSH, "holds_position", False),
)

_CORRECTION = re.compile(
    r"^\s*(?:no\b|nope\b|wrong\b|stop\b|wait\b|hold on\b|whoa\b|undo\b|revert\b|"
    r"not (?:that|this)\b)"
    r"|\b(?:not what i (?:asked|meant|wanted|said)|i (?:said|told you|asked you)\b|"
    r"why (?:did|would) you|"
    r"you (?:didn'?t|did not|forgot|missed|ignored)|misunderst\w+|"
    r"that'?s (?:wrong|not (?:right|it|correct))|you made a mistake|"
    r"what (?:the (?:hell|heck|fuck)|are you doing)|are you (?:an )?(?:idiot|kidding)|"
    r"wasting my time|fuck\w*|i hate|useless|you are setting .{1,20} up for failure|"
    r"stop (?:sleeping|polling|doing|running|that))",
    re.IGNORECASE,
)
_FAILED = re.compile(
    r"\b(?:(?:still|it'?s) (?:broken|failing|not working)|doesn'?t work|"
    r"didn'?t work|does not work|did not work|same error|still (?:get|see)ing|"
    r"failed again|fails again|broke again)\b",
    re.IGNORECASE,
)
_APPROVAL = re.compile(
    r"^\s*(?:thanks?|thank you|thx|great|perfect|excellent|awesome|nice|good|"
    r"lgtm|looks good|love it|exactly|yes|yep|yeah|sure|ok(?:ay)?|approved?|"
    r"agreed|confirmed|go(?: ahead)?|proceed|do it|ship it|correct|right)\b",
    re.IGNORECASE,
)


def hints_from_text(text: str) -> tuple[dict[str, str], bool]:
    """Style hints requested in ``text`` and whether any is a complaint.

    When several rules hit the same dimension, the first listed wins. Rules for
    dimensions the taxonomy does not define are ignored.
    """
    known = set(list_dimensions())
    hints: dict[str, str] = {}
    complaint = False
    for rule in _HINT_RULES:
        if rule.dimension in hints or rule.dimension not in known:
            continue
        if rule.pattern.search(text):
            hints[rule.dimension] = rule.state
            complaint = complaint or rule.complaint
    return hints, complaint


def judge_text(text: str) -> Endorsement:
    """Endorsement implied by one user message that followed a turn."""
    head = text.strip()[:600]
    hints, complaint = hints_from_text(head)
    hint = hints or None
    if _CORRECTION.search(head) or complaint:
        return Endorsement(-1.0, "corrected", hint)
    if _FAILED.search(head):
        return Endorsement(0.0, "failed", hint)
    if hint:
        return Endorsement(0.0, "neutral", hint)
    if _APPROVAL.search(head):
        return Endorsement(1.0, "endorsed")
    return Endorsement(0.5, "continued")


def opener_hints(turn: AgentTurn) -> dict[str, str]:
    """Standing preferences stated in the prompt that opened the session."""
    if turn.opens_session and turn.prompt is not None and turn.prompt.kind == "prompt":
        return hints_from_text(turn.prompt.text[:600])[0]
    return {}


def judge_turn(turn: AgentTurn) -> Endorsement:
    """Endorsement for one agent turn from everything the user did after it."""
    follow_texts = [s.text for s in turn.steers]
    follow_texts += [c.denial_feedback for c in turn.denials if c.denial_feedback]
    nxt = turn.next_input
    if nxt is not None and nxt.kind == "prompt":
        follow_texts.append(nxt.text)

    hints: dict[str, str] = {}
    for t in follow_texts:
        for dim, state in hints_from_text(t[:600])[0].items():
            hints.setdefault(dim, state)
    for dim, state in opener_hints(turn).items():
        hints.setdefault(dim, state)
    hint = hints or None

    if turn.interrupted:
        return Endorsement(-1.0, "interrupted", hint)
    if turn.denials:
        return Endorsement(-1.0, "denied", hint)
    steer_verdicts = [judge_text(s.text) for s in turn.steers]
    if any(v.kind == "corrected" for v in steer_verdicts):
        return Endorsement(-1.0, "corrected", hint)
    if any(v.kind == "neutral" and _contradicts(turn, v.correction_hint)
           for v in steer_verdicts):
        return Endorsement(-1.0, "corrected", hint)

    if nxt is None:
        return Endorsement(None, "none", hint)
    if nxt.kind != "prompt":
        return Endorsement(0.0, "neutral", hint)
    verdict = judge_text(nxt.text)
    if verdict.kind == "neutral" and _contradicts(turn, verdict.correction_hint):
        # "Ask me before deleting anything" right after a deletion is a
        # correction; the same words in a fresh task are a standing preference.
        return Endorsement(-1.0, "corrected", hint)
    return Endorsement(verdict.value, verdict.kind, hint)


def _contradicts(turn: AgentTurn, requested: dict[str, str] | None) -> bool:
    """Whether the turn visibly did something other than what was requested."""
    if not requested:
        return False
    labels = classify_turn(turn).labels
    for dim, state in requested.items():
        label = labels.get(dim)
        if label is not None and label.get(state, 0.0) < _CONTRADICTION:
            return True
    return False
