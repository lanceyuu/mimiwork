"""Feedback on one node of the flow diagram becomes new instructions.

The user clicks "Saved" (or any step) and says what they did not like; the model
rewrites the instructions and the diagram redraws from them. One round-trip, no
session — and a provider that fails leaves the text exactly as it was.
"""

from __future__ import annotations

from helpers import CapturingProvider, ScriptedProvider

from coworker.providers.base import AssistantTurn
from coworker.server.manager import SessionManager


def _manager(tmp_path, monkeypatch, provider) -> SessionManager:
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    return SessionManager(data_dir=tmp_path / "data", provider=provider)


def _task(manager):
    return manager.create_automation(
        {"title": "Briefing", "instructions": "Write the briefing.", "cron": "0 8 * * *"}
    )["task"]


def test_the_comment_and_the_current_text_reach_the_model_and_the_answer_is_saved(
    tmp_path, monkeypatch
):
    provider = CapturingProvider(
        [AssistantTurn(text="Write the briefing as a PDF.", finish_reason="stop")]
    )
    m = _manager(tmp_path, monkeypatch, provider)
    task = _task(m)

    res = m.revise_automation(task["id"], "Saved", "I want a PDF, not markdown")

    assert res["ok"] and res["task"]["instructions"] == "Write the briefing as a PDF."
    sent = provider.calls[0][-1]["content"]
    assert "Write the briefing." in sent and "Saved" in sent and "PDF, not markdown" in sent
    assert m.get_automation(task["id"])["task"]["instructions"] == "Write the briefing as a PDF."


def test_a_provider_failure_leaves_the_instructions_untouched(tmp_path, monkeypatch):
    m = _manager(tmp_path, monkeypatch, ScriptedProvider([]))  # pops an empty queue → raises
    task = _task(m)
    res = m.revise_automation(task["id"], "Saved", "make it shorter")
    assert not res["ok"] and res["error"]
    assert m.get_automation(task["id"])["task"]["instructions"] == "Write the briefing."


def test_an_empty_comment_is_not_a_revision(tmp_path, monkeypatch):
    m = _manager(tmp_path, monkeypatch, ScriptedProvider([]))
    task = _task(m)
    assert not m.revise_automation(task["id"], "Saved", "   ")["ok"]
    assert not m.revise_automation("nope", "Saved", "x")["ok"]
