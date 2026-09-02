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
    # Keep the production retry count while removing wall-clock waits.
    engine.retry_delays = tuple(0 for _ in engine.retry_delays)
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


def test_gateway_outage_recovers_after_more_than_three_retries(tmp_path):
    gateway_error = RuntimeError(
        "<!DOCTYPE html><html><body><p>Error code: 502</p>"
        "<h1>via_upstream (502 -)</h1>"
        "<p>App Platform failed to forward this request to the application.</p>"
        "</body></html>"
    )
    provider = FlakyProvider(
        [gateway_error] * 5,
        [AssistantTurn(text="recovered")],
    )
    engine = _engine(tmp_path, provider)

    events = _run(engine, "finish the document")

    assert provider.calls == 6
    assert events[-1].type == EventType.TURN_END
    assert not [e for e in events if e.type == EventType.ERROR]


def test_exhausted_gateway_outage_hides_raw_html_from_the_user(tmp_path):
    gateway_error = RuntimeError(
        "<!DOCTYPE html><html><body><p>Error code: 502</p>"
        "<h1>via_upstream (502 -)</h1>"
        "<p>App Platform failed to forward this request to the application.</p>"
        "</body></html>"
    )
    engine = _engine(tmp_path, FlakyProvider([gateway_error] * 20, []))

    events = _run(engine, "finish the document")
    error = next(e for e in events if e.type == EventType.ERROR)

    assert "temporarily unavailable" in error.data["error"]
    assert "automatically" in error.data["error"]
    assert "<!DOCTYPE" not in error.data["error"]
    assert "via_upstream" in error.data["raw"]


def test_retry_budget_is_finite(tmp_path):
    provider = FlakyProvider([RateLimited()] * 7, [AssistantTurn(text="never")])
    engine = _engine(tmp_path, provider)
    events = _run(engine, "hi")
    assert provider.calls == 7  # first try + 6 retries
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


# -- a key the gateway no longer accepts (owner-hit 2026-08-31) ----------------
class RevokedKey(Exception):
    """The gateway's verbatim reply to a key it cannot resolve."""

    def __init__(self):
        super().__init__("Error code: 401 - {'detail': 'Invalid or revoked API key'}")


class _RotatingProvider(FlakyProvider):
    """Fails with a rejected key until its clients are rebuilt from disk."""

    def __init__(self, turns):
        super().__init__([], turns)
        self.reloads = 0
        self._stale = True

    def complete(self, *, model, messages, tools=None, **settings):
        self.calls += 1
        if self._stale:
            raise RevokedKey()
        return self.turns.pop(0)

    def invalidate(self, name=None):
        self.reloads += 1
        self._stale = False  # the key on disk was already the good one


def test_a_rejected_key_is_reloaded_once_and_the_turn_continues(tmp_path):
    """Signing in mints a NEW key, and the router caches its client — key and all — at
    first use. The app then kept presenting the OLD key: every call 401'd, and signing
    in again did not help because the same stale client answered. Re-read the key and
    carry on; the user never asked for anything to go wrong."""
    provider = _RotatingProvider([AssistantTurn(text="done")])
    engine = _engine(tmp_path, provider)

    events = _run(engine, "hello")

    assert provider.reloads == 1, "the cached client was never rebuilt"
    assert provider.calls == 2, "the turn did not retry after reloading the key"
    assert not [e for e in events if e.type is EventType.ERROR]
    assert any(e.type is EventType.ASSISTANT_MESSAGE for e in events)


class _AlwaysRevoked(FlakyProvider):
    def __init__(self):
        super().__init__([], [])
        self.reloads = 0

    def complete(self, *, model, messages, tools=None, **settings):
        self.calls += 1
        raise RevokedKey()

    def invalidate(self, name=None):
        self.reloads += 1


def test_a_key_that_stays_rejected_says_what_to_do_and_stops(tmp_path):
    """Reloading is one attempt, not a loop — and the raw 401 tells the user nothing,
    so the message has to name the fix."""
    provider = _AlwaysRevoked()
    engine = _engine(tmp_path, provider)

    events = _run(engine, "hello")

    assert provider.reloads == 1 and provider.calls == 2, "reload must not loop"
    errors = [e for e in events if e.type is EventType.ERROR]
    assert errors, "a permanently rejected key must surface"
    text = errors[-1].data["error"]
    assert "Reconnect" in text and "QualiTaTi" in text, text
    assert "Invalid or revoked API key" not in text, "the raw 401 is not an instruction"


# -- a long turn is asked whether it is done; failing calls get a pointer, then a stop --
# (owner-hit 2026-09-02: 92 steps, the last dozen re-verifying finished files and calling
# tools that do not exist, under "Waiting for agent" for an hour)


def _tool_turn_n(i, name="list_files", args=None):
    # Each step narrates differently, so the repetition guard (identical laps) stays out
    # of these tests — they are about long turns and failing calls, not loops.
    return AssistantTurn(
        text=f"step {i}",
        tool_calls=[ToolCall(id=f"c{i}", name=name, arguments=args or {"path": "."})],
        finish_reason="tool_calls",
    )


def test_every_forty_steps_the_model_is_asked_whether_the_work_is_done(tmp_path):
    from coworker.engine import CHECKPOINT_EVERY

    turns = [_tool_turn_n(i) for i in range(CHECKPOINT_EVERY + 2)] + [AssistantTurn(text="done")]
    engine = _engine(tmp_path, FlakyProvider([], turns), max_iterations=CHECKPOINT_EVERY + 10)
    events = _run(engine, "go")
    checkpoints = [m for m in engine.messages if m.get("steering") == "checkpoint"]
    assert len(checkpoints) == 1 and f"{CHECKPOINT_EVERY} tool steps" in checkpoints[0]["content"]
    assert [e for e in events if e.type == EventType.NOTICE and e.data["kind"] == "checkpoint"]
    assert events[-1].data["status"] == "completed"


def test_unknown_tools_are_named_back_and_three_in_a_row_earn_a_pointer(tmp_path):
    turns = [_tool_turn_n(i, name="bash_tool", args={"cmd": "ls"}) for i in range(3)]
    turns.append(AssistantTurn(text="ok"))
    engine = _engine(tmp_path, FlakyProvider([], turns))
    _run(engine, "go")
    tool_msgs = [m for m in engine.messages if m.get("role") == "tool"]
    assert "unknown tool: bash_tool" in tool_msgs[0]["content"]
    assert "list_files" in tool_msgs[0]["content"], "the error names the tools that exist"
    hints = [m for m in engine.messages if m.get("steering") == "tool_failures"]
    assert len(hints) == 1 and "list_files" in hints[0]["content"]


def test_six_failed_calls_in_a_row_end_the_turn(tmp_path):
    turns = [_tool_turn_n(i, name="exec_command", args={}) for i in range(6)]
    provider = FlakyProvider([], turns)
    engine = _engine(tmp_path, provider)
    events = _run(engine, "go")
    assert events[-1].data["status"] == "tool_failure_stop"
    assert provider.calls == 6, "no seventh model call — the turn is over"


def test_a_success_resets_the_failure_streak(tmp_path):
    turns = [_tool_turn_n(0, name="nope"), _tool_turn_n(1, name="nope"), _tool_turn_n(2)]
    turns += [_tool_turn_n(3, name="nope"), _tool_turn_n(4, name="nope"), AssistantTurn(text="ok")]
    engine = _engine(tmp_path, FlakyProvider([], turns))
    events = _run(engine, "go")
    assert not [m for m in engine.messages if m.get("steering") == "tool_failures"]
    assert events[-1].data["status"] == "completed"


def test_wrong_arguments_get_the_parameter_list_back():
    registry = ToolRegistry()

    def greet(name: str, loud: bool = False) -> str:
        return name.upper() if loud else name

    registry.register(greet)
    import pytest

    with pytest.raises(TypeError) as exc:
        registry.execute("greet", {"nam": "x"})
    assert "Its parameters are: name, loud" in str(exc.value)
    assert registry.execute("greet", {"name": "x"}) == "x"
