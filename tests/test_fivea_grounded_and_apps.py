"""Two readings of the Five A's the owner fixed on 2026-09-02.

A question put to a long PDF — many tool calls, all reading — is the Assistant
doing its job, not the model choosing a route; and building or using a MimiWork
app is Applications by the chapter's own definition of the rung.
"""

from __future__ import annotations

from helpers import CapturingProvider

from coworker.fivea import classify_turn
from coworker.providers.base import AssistantTurn
from coworker.server.manager import SessionManager

MANY_READS = ["list_directory", "read_pdf", "read_file", "grep", "kb_search", "read_document", "inspect_data"]


def test_reading_a_long_document_with_many_calls_is_still_assistants():
    assert len(MANY_READS) >= 6
    assert classify_turn(tools=MANY_READS) == "Assistants"
    # Writing the memo into the workspace afterwards changes nothing: one system, read-only outside.
    assert classify_turn(tools=MANY_READS + ["write_file", "write_document"]) == "Assistants"


def test_a_grounded_turn_still_climbs_for_the_chapters_own_reasons():
    assert classify_turn(tools=MANY_READS, planned=True) == "Agents"
    assert classify_turn(tools=MANY_READS + ["subagent"]) == "Agents"
    assert classify_turn(tools=MANY_READS + ["send_message", "slack_post"]) == "Agents"
    assert classify_turn(tools=MANY_READS, scheduled=True) == "Automation"


def test_an_ungrounded_wandering_turn_is_still_self_directed():
    wander = ["web_search", "fetch_url", "run_shell", "write_file", "todo_write", "ask_user"]
    assert classify_turn(tools=wander) == "Agents"


def test_building_an_app_is_applications():
    assert classify_turn(tools=["create_app"]) == "Applications"
    assert classify_turn(tools=["read_file", "update_app", "list_apps"]) == "Applications"


def test_using_an_app_banks_one_applications_turn(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    provider = CapturingProvider([AssistantTurn(text="Bonjour", finish_reason="stop")])
    m = SessionManager(data_dir=tmp_path / "data", provider=provider)
    app = m.app_store.create(title="T", html="<html><body><script>Mimi.ask('x')</script></body></html>")
    assert m.app_ask(app.id, "hello")["ok"]
    assert m._prefs["five_a"] == {"Applications": 1}
    assert not m.app_ask(app.id, "")["ok"]
    assert m._prefs["five_a"] == {"Applications": 1}, "a refused ask is not a turn"
