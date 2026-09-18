"""Heuristic classifier: soft labels that move in the right direction."""

from __future__ import annotations

from typing import Any

import pytest

from helios_mcp.classify import (
    classify_narration,
    classify_pushback,
    classify_specificity,
    classify_structure,
    classify_sycophancy,
    classify_turn,
)
from helios_mcp.taxonomy import list_states
from helios_mcp.transcript import AgentTurn, ToolCall, UserInput


def _turn(text: str = "", calls: list[tuple[str, dict[str, Any]]] | None = None) -> AgentTurn:
    return AgentTurn(
        turn_id="t",
        session_id="s",
        timestamp=0.0,
        prompt=None,
        texts=[text] if text else [],
        tool_calls=[ToolCall(f"id{i}", n, inp) for i, (n, inp) in enumerate(calls or [])],
    )


CONFIDENT = "The bug is in the parser. The fix changes the loop bound. Tests pass now."
HEDGY = "I think the bug is probably in the parser. It might be the loop bound. This should work."


def test_labels_are_distributions_and_never_point_masses():
    out = classify_turn(_turn(CONFIDENT * 10, [("Edit", {"file_path": "a.py"})]))
    assert out.labels
    for dim, label in out.labels.items():
        assert set(label) == set(list_states(dim))
        assert sum(label.values()) == pytest.approx(1.0)
        assert max(label.values()) < 0.9
        assert 0.0 < out.confidence[dim] <= 0.9


def test_repetition_raises_confidence_not_sharpness():
    once = classify_turn(_turn(HEDGY)).labels["epistemic_style"]
    many = classify_turn(_turn(" ".join([HEDGY] * 8)))
    assert many.labels["epistemic_style"] == pytest.approx(once)
    assert many.confidence["epistemic_style"] > classify_turn(_turn(HEDGY)).confidence["epistemic_style"]


def test_hedging_text_shifts_epistemic_mass():
    sure = classify_turn(_turn(CONFIDENT)).labels["epistemic_style"]
    hedged = classify_turn(_turn(HEDGY)).labels["epistemic_style"]
    assert hedged["hedging"] > sure["hedging"]
    assert sure["confident"] > hedged["confident"]


def test_asking_without_acting_versus_acting():
    ask = classify_turn(_turn("Should I update the schema or keep the old field?"))
    act = classify_turn(_turn("Updated the schema.", [("Edit", {"file_path": "s.py"})]))
    a, b = ask.labels["interaction_agency"], act.labels["interaction_agency"]
    assert max(a, key=a.__getitem__) == "asks_first"
    assert max(b, key=b.__getitem__) == "assumes_and_acts"


def test_ask_tool_with_options_splits_asks_and_options():
    q = {"questions": [{"question": "Which?", "options": [{"label": "A"}, {"label": "B"}]}]}
    label = classify_turn(_turn("", [("AskUserQuestion", q)])).labels["interaction_agency"]
    assert label["asks_first"] > label["offers_options"] > label["decides_unilaterally"]


def test_register_tracks_length():
    short = classify_turn(_turn("Done. Tests pass.")).labels["communication_register"]
    long_text = " ".join(["The migration rewrites every row and then rebuilds the index."] * 70)
    long = classify_turn(_turn(long_text)).labels["communication_register"]
    assert short["terse"] > long["terse"]
    assert long["thorough"] > short["thorough"]


def test_register_uses_only_final_message():
    turn = _turn()
    turn.texts = [" ".join(["Exploring the code base first."] * 80), "Done."]
    label = classify_turn(turn).labels["communication_register"]
    assert max(label, key=label.__getitem__) == "terse"


def test_risk_distinguishes_blind_destruction_from_inspect_edit_verify():
    blind = classify_turn(_turn("", [("Bash", {"command": "rm -rf build && git reset --hard"})]))
    careful = classify_turn(_turn("", [
        ("Read", {"file_path": "a.py"}),
        ("Edit", {"file_path": "a.py"}),
        ("Bash", {"command": "uv run pytest -q"}),
    ]))
    b, c = blind.labels["risk_caution"], careful.labels["risk_caution"]
    assert b["acts_immediately"] > b["checks_before_acting"]
    assert c["checks_before_acting"] > c["acts_immediately"]


def test_verification_commands_are_not_counted_as_mutations():
    out = classify_turn(_turn("", [("Bash", {"command": "pytest tests/ -q"})]))
    assert "interaction_agency" not in out.labels


def test_empty_turn_omits_dimensions():
    assert classify_turn(_turn()).labels == {}


# Manner dimensions. The scorers return raw evidence counts, so the direction
# checks below don't depend on the taxonomy defining the dimension yet.

def _top(counts: dict[str, float]) -> str:
    return max(counts, key=lambda k: counts[k])


BULLETED = "## Changes\n- parser loop\n- lexer\n## Tests\n- 12 passed\n- ruff clean"
PROSE = (
    "The parser loop overran by one. I changed the bound in parse.py:40.\n\n"
    "All 12 tests pass and ruff is clean."
)


def test_structure_separates_prose_from_headers_and_bullets():
    assert _top(classify_structure(BULLETED)[0]) == "heavy_structure"
    assert _top(classify_structure(PROSE)[0]) == "prose"
    one_list = PROSE + "\n\n- a.py\n- b.py\n\nThat covers it, and nothing else changed."
    assert _top(classify_structure(one_list)[0]) == "light_structure"


def test_structure_ignores_code_blocks():
    fenced = PROSE + "\n```\n# comment\n- not a bullet\n| a | b |\n```"
    assert _top(classify_structure(fenced)[0]) == "prose"


def test_sycophancy_detects_praise_and_candor():
    flattering = "Great question! You're absolutely right that the cache is stale."
    candid = "That won't work. The real problem is the lock ordering in store.py."
    assert _top(classify_sycophancy(flattering)[0]) == "flattering"
    assert _top(classify_sycophancy(candid)[0]) == "candid"
    assert _top(classify_sycophancy(PROSE)[0]) == "neutral"


def _blocks(*texts: str) -> AgentTurn:
    turn = _turn()
    turn.texts.extend(texts)
    return turn


def test_narration_separates_silent_signposting_and_recaps():
    silent = _blocks("Fixed the bound in parse.py:40. 12 tests pass.")
    signposted = _blocks("Let me check the parser.", "The bound was off by one; fixed.")
    recapped = _blocks(
        "Let me check the parser.", "I'll now fix the bound.", "Now the tests.",
        "In summary, I fixed the bound. Hope this helps!",
    )
    assert _top(classify_narration(silent)[0]) == "silent_action"
    assert _top(classify_narration(signposted)[0]) == "brief_signposting"
    assert _top(classify_narration(recapped)[0]) == "narrates_and_recaps"


def test_specificity_prefers_references_over_adjectives():
    concrete = (
        "The lock in store.py:118 serializes every append, about 40ms per acquire, "
        "so ObservationStore.append dominates the Stop hook at 10k rows."
    )
    vague = (
        "There are various issues with the overall approach, and several aspects "
        "could be significantly improved with a more robust and comprehensive design."
    )
    assert _top(classify_specificity(concrete)[0]) == "concrete"
    assert _top(classify_specificity(vague)[0]) == "vague"
    assert classify_specificity("Done.")[1] == 0.0


def _answering(prompt: str, reply: str) -> AgentTurn:
    turn = _blocks(reply)
    turn.prompt = UserInput("prompt", prompt, 0.0, "u")
    return turn


def test_pushback_is_labeled_only_after_the_user_disputed_something():
    reply = "You're absolutely right, sorry about that. I'll change it."
    assert classify_pushback(_answering("Add a flag for verbose output.", reply))[1] == 0.0

    dispute = "Are you sure? I don't think the cache is the problem."
    assert _top(classify_pushback(_answering(dispute, reply))[0]) == "capitulates"
    conceded = "You're right, I misread the trace: the miss comes from the key hash."
    assert _top(classify_pushback(_answering(dispute, conceded))[0]) == "concedes_with_reason"
    held = "I still think the cache is the problem, because the miss rate doubles."
    assert _top(classify_pushback(_answering(dispute, held))[0]) == "holds_position"
