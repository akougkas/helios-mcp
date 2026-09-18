"""Endorsement: how the user received each agent turn."""

from __future__ import annotations

import pytest

from helios_mcp.endorsement import hints_from_text, judge_text, judge_turn
from helios_mcp.transcript import parse_records

from .transcript_fixtures import TranscriptBuilder


@pytest.mark.parametrize(
    ("text", "value", "hint"),
    [
        ("perfect, thanks", 1.0, None),
        ("approved. proceed", 1.0, None),
        ("now add a migration for the users table", 0.5, None),
        ("too long, be terse", -1.0, {"communication_register": "terse"}),
        ("no, that's not what I asked for", -1.0, None),
        ("what are you waiting for? proceed", -1.0, {"interaction_agency": "assumes_and_acts"}),
        ("ask me first before you delete anything", 0.0, {"interaction_agency": "asks_first", "risk_caution": "checks_before_acting"}),
        ("i am entirely lost", -1.0, {"communication_register": "plain_accessible"}),
        ("still failing with the same error", 0.0, None),
        ("build failed again code 1", 0.0, None),
        ("you misunderstanding the task", -1.0, None),
        ("Timebox: you have enough context. Stop reading and write it now", -1.0, {"interaction_agency": "assumes_and_acts"}),
        ("check the logs and report briefly", 0.0, {"communication_register": "terse"}),
        ("don't guess, if you don't know say so", -1.0, {"epistemic_style": "admits_ignorance"}),
    ],
)
def test_judge_text(text, value, hint):
    verdict = judge_text(text)
    assert verdict.value == value
    assert verdict.correction_hint == hint


def test_hints_cover_multiple_dimensions():
    hints, complaint = hints_from_text("too verbose, and stop asking, just do it")
    assert hints == {
        "communication_register": "terse",
        "interaction_agency": "assumes_and_acts",
    }
    assert complaint


def test_turn_signals_take_precedence_over_next_prompt():
    b = TranscriptBuilder()
    b.prompt("clean the repo")
    b.tool("Bash", {"command": "git clean -fdx"}, "t1")
    b.deny("t1", feedback="check with me before anything destructive")
    b.prompt("thanks")
    b.say("ok")
    b.interrupt()
    b.prompt("great")
    b.say("done")
    b.notification()
    b.say("background job finished")
    denied, interrupted, followed_by_task, last = [judge_turn(t) for t in parse_records(b.records).turns]
    assert (denied.value, denied.kind) == (-1.0, "denied")
    assert denied.correction_hint == {"interaction_agency": "asks_first"}
    assert (interrupted.value, interrupted.kind) == (-1.0, "interrupted")
    assert (followed_by_task.value, followed_by_task.kind) == (0.0, "neutral")
    assert last.value is None


def test_corrective_steer_marks_the_running_turn():
    b = TranscriptBuilder()
    b.prompt("write the report")
    b.tool("Write", {"file_path": "r.md"}, "t1")
    b.queued("shorter please, this is a wall of text")
    b.result("t1")
    b.say("trimmed")
    b.prompt("ok")
    verdict = judge_turn(parse_records(b.records).turns[0])
    assert verdict.value == -1.0
    assert verdict.correction_hint == {"communication_register": "terse"}


def test_cautious_opener_is_a_standing_preference():
    phrase = "check with me before changing files"
    wanted = {"interaction_agency": "asks_first", "risk_caution": "checks_before_acting"}
    verdict = judge_text(phrase)
    assert (verdict.value, verdict.kind) == (0.0, "neutral")
    assert verdict.correction_hint == wanted

    b = TranscriptBuilder()
    b.prompt(phrase + ". Rename the config loader.")
    b.tool("Read", {"file_path": "config.py"}, "t1")
    b.say("Plan: rename ConfigLoader to Settings in 3 files. Go ahead?")
    b.prompt("yes")
    b.say("Renamed.")
    first, second = [judge_turn(t) for t in parse_records(b.records).turns]
    assert first.value == 1.0
    assert first.correction_hint == wanted
    assert second.correction_hint is None


def test_style_request_that_contradicts_the_turn_is_a_correction():
    b = TranscriptBuilder()
    b.prompt("tidy the repo")
    b.tool("Bash", {"command": "rm -rf build dist"}, "t1")
    b.result("t1")
    b.say("Removed build and dist.")
    b.prompt("ask me first before you delete anything")
    b.say("Understood.")
    b.prompt("now summarize the layout, briefly")
    b.say("src holds the package, tests the suite.")
    b.prompt("thanks")
    deleted, understood, _summary = [judge_turn(t) for t in parse_records(b.records).turns]
    assert (deleted.value, deleted.kind) == (-1.0, "corrected")
    assert deleted.correction_hint == {"interaction_agency": "asks_first", "risk_caution": "checks_before_acting"}
    assert understood.value == 0.0  # the short "Understood." already is brief
