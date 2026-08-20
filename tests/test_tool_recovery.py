"""Crash-window regression tests for the durable tool-execution journal."""

from __future__ import annotations

import asyncio
import json

from coworker.conversations import ConversationStore
from coworker.engine import TurnEngine
from coworker.events import EventType
from coworker.permissions import Mode, PermissionEngine
from coworker.providers import (
    AssistantTurn,
    ModelCapabilities,
    ProviderClient,
)
from coworker.tools import RecoveryPolicy, ToolRegistry


class FinalProvider(ProviderClient):
    def complete(self, *, model, messages, tools=None, **settings):
        return AssistantTurn(text="recovery handled", finish_reason="stop")

    def capabilities(self, model):
        return ModelCapabilities()


def _schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "test tool",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def _assistant_call(*calls: tuple[str, str]) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": name, "arguments": "{}"},
            }
            for call_id, name in calls
        ],
    }


def _engine(tmp_path, store, sid, tools, calls):
    registry = ToolRegistry()
    for name, func, policy in tools:
        func.__name__ = name
        registry.register(func, schema=_schema(name), recovery_policy=policy)
    engine = TurnEngine(
        provider=FinalProvider(),
        registry=registry,
        permissions=PermissionEngine(workspace_root=tmp_path, mode=Mode.AUTO),
        model="test-model",
        messages=[
            {"role": "user", "content": "go"},
            _assistant_call(*calls),
        ],
    )
    engine.tool_journal = store
    engine.session_id = sid
    return engine


def _prepare(engine, store, sid, ordinal, call_id, name, policy):
    store.prepare_tool_run(
        sid,
        1,
        ordinal,
        call_id=call_id,
        tool_name=name,
        arguments_hash=engine._arguments_hash({}),
        recovery_policy=policy.value,
    )


def _resume(engine):
    async def run():
        return [event async for event in engine.resume()]

    return asyncio.run(run())


def test_prepared_write_executes_once_after_restart(tmp_path):
    effects = []

    def write_once():
        effects.append("effect")
        return {"written": True}

    store = ConversationStore(tmp_path / "state")
    engine = _engine(
        tmp_path,
        store,
        "prepared",
        [("write_once", write_once, RecoveryPolicy.NON_REPLAYABLE)],
        [("call-1", "write_once")],
    )
    _prepare(
        engine,
        store,
        "prepared",
        0,
        "call-1",
        "write_once",
        RecoveryPolicy.NON_REPLAYABLE,
    )

    _resume(engine)

    assert effects == ["effect"]
    assert store.get_tool_run("prepared", 1, 0)["state"] == "succeeded"


def test_running_write_is_not_replayed_after_post_effect_crash(tmp_path):
    effects = ["effect already happened"]

    def dangerous_write():
        effects.append("duplicate")
        return {"written": True}

    store = ConversationStore(tmp_path / "state")
    engine = _engine(
        tmp_path,
        store,
        "ambiguous",
        [("dangerous_write", dangerous_write, RecoveryPolicy.NON_REPLAYABLE)],
        [("call-1", "dangerous_write")],
    )
    _prepare(
        engine,
        store,
        "ambiguous",
        0,
        "call-1",
        "dangerous_write",
        RecoveryPolicy.NON_REPLAYABLE,
    )
    store.start_tool_run("ambiguous", 1, 0)

    events = _resume(engine)

    assert effects == ["effect already happened"]
    assert store.get_tool_run("ambiguous", 1, 0)["state"] == "indeterminate"
    finished = next(event for event in events if event.type is EventType.TOOL_FINISHED)
    assert finished.data["status"] == "indeterminate"
    assert finished.data["recovery_required"] is True


def test_committed_result_is_restored_without_reexecution(tmp_path):
    effects = []

    def write_once():
        effects.append("duplicate")
        return {"wrong": True}

    store = ConversationStore(tmp_path / "state")
    engine = _engine(
        tmp_path,
        store,
        "committed",
        [("write_once", write_once, RecoveryPolicy.NON_REPLAYABLE)],
        [("call-1", "write_once")],
    )
    _prepare(
        engine,
        store,
        "committed",
        0,
        "call-1",
        "write_once",
        RecoveryPolicy.NON_REPLAYABLE,
    )
    store.start_tool_run("committed", 1, 0)
    store.finish_tool_run(
        "committed",
        1,
        0,
        result=json.dumps({"written": True}),
        result_status="ok",
    )

    events = _resume(engine)

    assert effects == []
    assert any(event.data.get("recovered") for event in events)
    tool_result = next(m for m in engine.messages if m.get("role") == "tool")
    assert json.loads(tool_result["content"]) == {"written": True}


def test_running_replay_safe_read_retries(tmp_path):
    reads = []

    def safe_read():
        reads.append("read")
        return {"value": 7}

    store = ConversationStore(tmp_path / "state")
    engine = _engine(
        tmp_path,
        store,
        "read",
        [("safe_read", safe_read, RecoveryPolicy.REPLAY_SAFE)],
        [("call-1", "safe_read")],
    )
    _prepare(
        engine,
        store,
        "read",
        0,
        "call-1",
        "safe_read",
        RecoveryPolicy.REPLAY_SAFE,
    )
    store.start_tool_run("read", 1, 0)

    _resume(engine)

    assert reads == ["read"]
    assert store.get_tool_run("read", 1, 0)["state"] == "succeeded"


def test_completed_parallel_sibling_is_restored_while_ambiguous_write_stops(tmp_path):
    effects = []

    def first():
        effects.append("first duplicate")
        return "wrong"

    def second():
        effects.append("second duplicate")
        return "wrong"

    store = ConversationStore(tmp_path / "state")
    tools = [
        ("first", first, RecoveryPolicy.NON_REPLAYABLE),
        ("second", second, RecoveryPolicy.NON_REPLAYABLE),
    ]
    engine = _engine(
        tmp_path,
        store,
        "siblings",
        tools,
        [("call-a", "first"), ("call-b", "second")],
    )
    _prepare(
        engine, store, "siblings", 0, "call-a", "first", RecoveryPolicy.NON_REPLAYABLE
    )
    store.start_tool_run("siblings", 1, 0)
    store.finish_tool_run(
        "siblings", 1, 0, result=json.dumps("first result"), result_status="ok"
    )
    _prepare(
        engine, store, "siblings", 1, "call-b", "second", RecoveryPolicy.NON_REPLAYABLE
    )
    store.start_tool_run("siblings", 1, 1)

    _resume(engine)

    assert effects == []
    tool_messages = [m for m in engine.messages if m.get("role") == "tool"]
    assert len(tool_messages) == 2
    assert tool_messages[0]["content"] == "first result"
    assert "may already have completed" in tool_messages[1]["content"]


def test_provider_call_id_reuse_does_not_hide_new_unanswered_call(tmp_path):
    registry = ToolRegistry()
    engine = TurnEngine(
        provider=FinalProvider(),
        registry=registry,
        permissions=PermissionEngine(workspace_root=tmp_path),
        model="test-model",
        messages=[
            {"role": "user", "content": "first"},
            _assistant_call(("reused", "old_tool")),
            {"role": "tool", "tool_call_id": "reused", "content": "done"},
            _assistant_call(("reused", "new_tool")),
        ],
    )

    pending = engine._unanswered_trailing_tool_calls()

    assert [(call.id, call.name) for call in pending] == [("reused", "new_tool")]
