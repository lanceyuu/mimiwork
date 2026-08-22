"""Shared test helpers: provider stubs, turn factories, and deadline polling.

Imported by test modules as `from helpers import ...` (pytest's default
`prepend` import mode puts this directory on sys.path).
"""

import asyncio
import time

from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient, ToolCall

# -- turn factories -----------------------------------------------------------


def text_turn(text: str) -> AssistantTurn:
    return AssistantTurn(text=text, finish_reason="stop")


def tool_turn(name: str, args: dict, call_id: str = "call_1") -> AssistantTurn:
    return AssistantTurn(
        tool_calls=[ToolCall(id=call_id, name=name, arguments=args)],
        finish_reason="tool_calls",
    )


# -- provider stubs ------------------------------------------------------------


class ScriptedProvider(ProviderClient):
    """Returns queued AssistantTurns (popping one per call).

    `loop=True` replays the first turn forever instead of exhausting the queue.
    `calls` counts complete() invocations.
    """

    def __init__(self, turns=None, *, loop=False):
        self._turns = list(turns or [])
        self._loop = loop
        self.calls = 0

    def complete(self, *, model, messages, tools=None, **settings):
        self.calls += 1
        return self._turns[0] if self._loop else self._turns.pop(0)

    def capabilities(self, model):
        return ModelCapabilities()


class CapturingProvider(ProviderClient):
    """Like ScriptedProvider but records a copy of the messages of every call,
    and falls back to a bare "ok" turn once the script runs dry."""

    def __init__(self, turns=()):
        self._turns = list(turns)
        self.calls: list[list[dict]] = []

    def complete(self, *, model, messages, tools=None, **settings):
        self.calls.append([dict(m) for m in messages])
        return (
            self._turns.pop(0)
            if self._turns
            else AssistantTurn(text="ok", finish_reason="stop")
        )

    def capabilities(self, model):
        return ModelCapabilities()


# -- deadline polling -----------------------------------------------------------


async def wait_until(predicate, *, timeout: float = 8.0, interval: float = 0.02):
    """Poll an async context until `predicate()` returns truthy (or timeout);
    returns the last value so callers can assert on it for a clear failure."""
    deadline = time.monotonic() + timeout
    val = predicate()
    while not val and time.monotonic() < deadline:
        await asyncio.sleep(interval)
        val = predicate()
    return val


def wait_until_sync(predicate, *, timeout: float = 5.0, interval: float = 0.02):
    """Thread-context sibling of wait_until for non-async tests."""
    deadline = time.monotonic() + timeout
    val = predicate()
    while not val and time.monotonic() < deadline:
        time.sleep(interval)
        val = predicate()
    return val
