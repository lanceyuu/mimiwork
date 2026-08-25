"""An automation's own model and permission level.

Two settings a session has always had and an automation didn't: which model
answers, and how much the run may do without asking. Both belong on the task —
"summarise the inbox every morning" and "post the weekly report to Slack" should
not be forced to the same level of trust, and a nightly job has no reason to
spend the expensive model.

The default stays the asking level. An unattended task that can do anything is a
decision the user makes, never one they inherit.
"""

from __future__ import annotations

import pytest

from coworker.automation.models import (
    DEFAULT_TASK_MODE,
    Schedule,
    ScheduledTask,
    normalize_mode,
)
from coworker.permissions import Mode
from coworker.server.manager import SessionManager


def _manager(tmp_path, monkeypatch) -> SessionManager:
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    return SessionManager(data_dir=tmp_path / "data")


def _create(manager, **extra):
    payload = {
        "title": "Morning briefing",
        "instructions": "Write the briefing.",
        "cron": "0 8 * * *",
    }
    payload.update(extra)
    return manager.create_automation(payload)


# ── the value itself ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "given,expected",
    [
        ("auto", "auto"),
        ("PLAN", "plan"),
        ("interactive", "interactive"),
        ("full", "auto"),  # the composer's own word for it
        ("ask", "interactive"),
    ],
)
def test_a_recognised_level_is_kept(given, expected):
    assert normalize_mode(given) == expected


@pytest.mark.parametrize("junk", ["", "   ", None, "yolo", "discuss", 7])
def test_anything_unrecognised_falls_back_to_asking(junk):
    """A typo in an imported blueprint must not cost the user their automation —
    and must never resolve to the permissive level."""
    assert normalize_mode(junk) == DEFAULT_TASK_MODE == "interactive"


def test_a_record_written_before_levels_existed_still_loads(tmp_path, monkeypatch):
    task = ScheduledTask(
        title="t", instructions="i", schedule=Schedule("cron", "0 9 * * *"), workspace=str(tmp_path)
    )
    stored = task.to_dict()
    stored.pop("mode")  # what an older record looks like
    assert ScheduledTask.from_dict(stored).mode == "interactive"


# ── creating ─────────────────────────────────────────────────────────────────


def test_the_default_is_ask_and_the_app_default_model(tmp_path, monkeypatch):
    task = _create(_manager(tmp_path, monkeypatch))["task"]
    assert task["mode"] == "interactive"
    assert task["model"] is None  # follow the app default, whatever it becomes


def test_a_chosen_model_and_level_are_stored_and_reported(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    out = _create(manager, model="qualitati:mimi-wolf", mode="auto")
    assert out["task"]["model"] == "qualitati:mimi-wolf"
    assert out["task"]["mode"] == "auto"
    saved = manager.task_store.get(out["task"]["id"])
    assert saved.model == "qualitati:mimi-wolf" and saved.mode == "auto"


def test_a_nonsense_level_at_creation_becomes_ask(tmp_path, monkeypatch):
    assert _create(_manager(tmp_path, monkeypatch), mode="whatever")["task"]["mode"] == "interactive"


# ── editing ──────────────────────────────────────────────────────────────────


def test_both_can_be_changed_later(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task_id = _create(manager)["task"]["id"]
    out = manager.update_automation(task_id, {"model": "qualitati:mimi-hound", "mode": "plan"})
    assert out["task"]["model"] == "qualitati:mimi-hound" and out["task"]["mode"] == "plan"
    assert manager.task_store.get(task_id).mode == "plan"


def test_clearing_the_model_returns_it_to_the_app_default(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task_id = _create(manager, model="qualitati:mimi-wolf")["task"]["id"]
    assert manager.update_automation(task_id, {"model": ""})["task"]["model"] is None


def test_an_unrelated_edit_leaves_the_level_alone(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task_id = _create(manager, mode="auto")["task"]["id"]
    out = manager.update_automation(task_id, {"title": "Renamed"})
    assert out["task"]["mode"] == "auto"


def test_a_bad_level_in_an_edit_keeps_the_one_already_set(tmp_path, monkeypatch):
    """Falling back to "ask" here would silently downgrade a deliberate choice, so
    an unreadable edit keeps what the automation already had."""
    manager = _manager(tmp_path, monkeypatch)
    task_id = _create(manager, mode="auto")["task"]["id"]
    assert manager.update_automation(task_id, {"mode": "nonsense"})["task"]["mode"] == "auto"


# ── running ──────────────────────────────────────────────────────────────────


def test_the_run_engine_is_built_at_the_tasks_level_and_model(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task_id = _create(manager, model="qualitati:mimi-wolf", mode="auto")["task"]["id"]
    task = manager.task_store.get(task_id)

    seen: dict = {}

    def fake_build(**kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop here — the arguments are the assertion")

    import coworker.server.manager as manager_mod

    monkeypatch.setattr(manager_mod, "build_engine", fake_build)
    with pytest.raises(RuntimeError):
        manager._build_task_engine(task, session_id="__run__x")
    assert seen["mode"] is Mode.AUTO
    assert seen["model"] == "qualitati:mimi-wolf"


def test_asking_is_still_the_mode_when_nothing_was_chosen(tmp_path, monkeypatch):
    manager = _manager(tmp_path, monkeypatch)
    task = manager.task_store.get(_create(manager)["task"]["id"])
    seen: dict = {}

    def fake_build(**kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop")

    import coworker.server.manager as manager_mod

    monkeypatch.setattr(manager_mod, "build_engine", fake_build)
    with pytest.raises(RuntimeError):
        manager._build_task_engine(task, session_id="__run__y")
    assert seen["mode"] is Mode.INTERACTIVE
    assert seen["model"] == manager.model  # the app default, resolved at run time


def test_run_now_opens_the_session_at_the_automations_own_settings(tmp_path, monkeypatch):
    """The same automation must not behave differently by hand than on schedule:
    "Run now" opens a live session, and that session takes the task's model and
    permission level rather than the app defaults."""
    manager = _manager(tmp_path, monkeypatch)
    task_id = _create(manager, model="qualitati:mimi-wolf", mode="auto")["task"]["id"]
    run = manager.prepare_manual_run(task_id)
    assert run["ok"] is True

    seen: dict = {}

    def fake_build(**kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop")

    import coworker.server.manager as manager_mod

    monkeypatch.setattr(manager_mod, "build_engine", fake_build)
    with pytest.raises(RuntimeError):
        manager.get_engine(run["session_id"], workspace=str(tmp_path))
    assert seen["mode"] is Mode.AUTO
    assert seen["model"] == "qualitati:mimi-wolf"
