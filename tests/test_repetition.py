"""The repetition guard: a looping model gets one nudge, then the turn stops — before
max_iterations, and before more credits burn on identical laps. Detection adapted from
FrontierAgent (Apodex AI, Apache-2.0); see coworker/repetition.py."""

from __future__ import annotations

from test_engine import _collect, _engine, _text_turn, _tool_turn

from coworker.events import EventType
from coworker.repetition import HINT, RepetitionGuard


def _same_tool_turn(i):
    # Same tool, same args, same prose — the classic stuck loop. Long enough prose to
    # clear the guard's min_chars threshold.
    return _tool_turn(
        "read_file",
        {"path": "a.txt"},
        call_id=f"call_{i}",
    )


# -- the guard itself -----------------------------------------------------------


def test_varied_work_never_trips_the_guard():
    guard = RepetitionGuard()
    for i in range(10):
        sig = f"reading chapter {i} of the report and summarizing its main findings now"
        assert guard.observe(sig) is None


def test_identical_turns_get_one_hint_then_a_stop():
    guard = RepetitionGuard()
    sig = "searching the workspace for the quarterly report using the same query again"
    verdicts = [guard.observe(sig) for _ in range(7)]
    assert verdicts == [None, None, "hint", None, None, "stop", "stop"]


def test_near_identical_wording_still_matches():
    """The whole point of shingles over exact matching: small edits don't reset it."""
    guard = RepetitionGuard()
    a = "I will now search the project folder for the quarterly revenue report file"
    b = "I will now search the project folder for the quarterly revenue report document"
    verdicts = [guard.observe(a), guard.observe(b), guard.observe(a)]
    assert verdicts[-1] == "hint"


def test_short_acknowledgements_are_ignored():
    guard = RepetitionGuard()
    for _ in range(10):
        assert guard.observe("ok, done.") is None


# -- wired into the turn loop ---------------------------------------------------


def _looping_engine(tmp_path, n_identical, then=None):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    turns = [_same_tool_turn(i) for i in range(n_identical)]
    if then is not None:
        turns.append(then)
    return _engine(tmp_path, turns, max_iterations=20)


def test_a_looping_turn_is_hinted_then_stopped_with_its_own_status(tmp_path):
    engine, provider = _looping_engine(tmp_path, 10)
    events = _collect(engine, "find the report")
    end = [e for e in events if e.type == EventType.TURN_END][-1]
    assert end.data["status"] == "repetition_stop"
    # Stopped at the guard's threshold, not at max_iterations — laps 7..10 never ran.
    assert end.data["iterations"] < 10
    notices = [e for e in events if e.type == EventType.NOTICE and e.data.get("kind") == "repetition"]
    assert len(notices) == 2  # the nudge, then the stop
    # The hint reached the transcript as a steering message the model saw.
    steers = [m for m in engine.messages if m.get("steering") == "repetition"]
    assert len(steers) == 1 and steers[0]["content"] == HINT


def test_a_model_that_takes_the_hint_recovers(tmp_path):
    """Three identical laps, the nudge lands, the model changes course and finishes —
    no stop, status completed."""
    engine, _ = _looping_engine(tmp_path, 3, then=_text_turn("Here is the report."))
    events = _collect(engine, "find the report")
    end = [e for e in events if e.type == EventType.TURN_END][-1]
    assert end.data["status"] == "completed"
    kinds = [e.data.get("kind") for e in events if e.type == EventType.NOTICE]
    assert kinds.count("repetition") == 1  # hinted once, never stopped
