"""Tool-loop reliability: transient-retry, wrap-up nudge, write_file self-check."""

import asyncio

import aisuite as ai

from coworker.engine import ApprovalOutcome, PermissionRequest, TurnEngine
from coworker.events import EventType
from coworker.permissions import PermissionEngine
from coworker.providers.base import AssistantTurn, ModelCapabilities, ProviderClient, ToolCall
from coworker.providers.errors import is_transient, retry_after_seconds
from coworker.tools.registry import ToolRegistry


class FlakyProvider(ProviderClient):
    """Raises the queued exceptions first, then returns the queued turns."""

    def __init__(self, failures, turns):
        self.failures = list(failures)
        self.turns = list(turns)
        self.calls = 0

    def complete(self, *, model, messages, tools=None, **settings):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return self.turns.pop(0)

    def capabilities(self, model):
        return ModelCapabilities()


class _Resp:
    def __init__(self, status, headers=None):
        self.status_code = status
        self.headers = headers or {}


class RateLimited(Exception):
    def __init__(self, retry_after=None):
        super().__init__("429 Too Many Requests: rate limit exceeded")
        self.status_code = 429
        self.response = _Resp(429, {"retry-after": retry_after} if retry_after else {})


async def _allow(_req: PermissionRequest):
    return ApprovalOutcome.ONCE


def _engine(tmp_path, provider, max_iterations=12):
    registry = ToolRegistry()
    registry.register_all(ai.toolkits.files(root=str(tmp_path), allow_write=True))
    engine = TurnEngine(
        provider=provider,
        registry=registry,
        permissions=PermissionEngine(workspace_root=tmp_path),
        model="gpt-5.5",
        max_iterations=max_iterations,
        approver=_allow,
    )
    engine.retry_delays = (0, 0, 0)
    return engine


def _run(engine, text):
    async def go():
        return [e async for e in engine.run(text)]

    return asyncio.run(go())


def test_transient_errors_are_retried_then_succeed(tmp_path):
    provider = FlakyProvider(
        [RateLimited(), ConnectionError("connection reset by peer")],
        [AssistantTurn(text="hello")],
    )
    engine = _engine(tmp_path, provider)
    events = _run(engine, "hi")
    notices = [e for e in events if e.type == EventType.NOTICE]
    assert [n.data["attempt"] for n in notices] == [1, 2]
    assert provider.calls == 3
    assert events[-1].type == EventType.TURN_END and events[-1].data["status"] == "completed"
    assert not [e for e in events if e.type == EventType.ERROR]


def test_retry_budget_is_finite(tmp_path):
    provider = FlakyProvider([RateLimited()] * 4, [AssistantTurn(text="never")])
    engine = _engine(tmp_path, provider)
    events = _run(engine, "hi")
    assert provider.calls == 4  # first try + 3 retries
    assert events[-1].type == EventType.ERROR


def test_non_transient_errors_are_not_retried(tmp_path):
    provider = FlakyProvider([RuntimeError("insufficient_quota")], [AssistantTurn(text="x")])
    engine = _engine(tmp_path, provider)
    events = _run(engine, "hi")
    assert provider.calls == 1
    assert events[-1].type == EventType.ERROR


def test_retry_after_header_is_honored():
    assert retry_after_seconds(RateLimited("2")) == 2.0
    assert retry_after_seconds(RateLimited("900")) == 30.0  # capped
    assert retry_after_seconds(RateLimited()) is None
    assert is_transient(RateLimited())
    assert is_transient(TimeoutError("read timed out"))
    assert not is_transient(RuntimeError("You exceeded your current quota"))
    assert not is_transient(ValueError("bad request"))


def test_wrap_up_nudge_lands_on_the_last_step(tmp_path):
    def tool_turn(i):
        return AssistantTurn(
            tool_calls=[ToolCall(id=f"c{i}", name="list_files", arguments={"path": "."})],
            finish_reason="tool_calls",
        )

    provider = FlakyProvider([], [tool_turn(1), tool_turn(2), AssistantTurn(text="done")])
    engine = _engine(tmp_path, provider, max_iterations=3)
    events = _run(engine, "go")
    nudges = [e for e in events if e.type == EventType.NOTICE and e.data["kind"] == "wrap_up"]
    assert len(nudges) == 1
    steer = [m for m in engine.messages if m.get("steering") == "wrap_up"]
    assert len(steer) == 1 and "Finish now" in steer[0]["content"]
    # The provider saw the nudge as a user message on its final call, without the sidecar key.
    sent = engine._outbound_messages()
    assert any("Finish now" in str(m.get("content")) for m in sent if m["role"] == "user")
    assert all("steering" not in m for m in sent)
    assert events[-1].data["status"] == "completed"


def test_write_file_gets_a_self_check(tmp_path):
    write = AssistantTurn(
        tool_calls=[
            ToolCall(
                id="w1",
                name="write_file",
                arguments={"path": "memo.md", "content": "# Memo\n\nTODO write this"},
            )
        ],
        finish_reason="tool_calls",
    )
    provider = FlakyProvider([], [write, AssistantTurn(text="ok")])
    engine = _engine(tmp_path, provider)
    _run(engine, "write it")
    tool_msgs = [m for m in engine.messages if m.get("role") == "tool"]
    assert tool_msgs and "placeholder" in str(tool_msgs[0].get("content"))
    assert "Fix these" in str(tool_msgs[0].get("content"))
