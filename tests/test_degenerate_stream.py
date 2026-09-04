"""A reply that stops being a reply (owner screenshot 2026-09-04): the model wrote its
native tool-call markup as text — `<｜DSML｜invoke_code>` through the QualiTaTi gateway —
and looped on it for 37 KB, which the GUI showed as a wall of bars. The engine now cuts
the stream at the first such token (or at a run of identical lines), keeps the prose
before it, tells the model what happened, and lets it redo the step."""

from __future__ import annotations

import asyncio
import time

from coworker.engine import TurnEngine, _strip_degenerate
from coworker.events import EventType
from coworker.permissions import PermissionEngine
from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient, StreamChunk
from coworker.tools.registry import ToolRegistry


class _MarkupThenClean(ProviderClient):
    """First call: prose, then DeepSeek markup for ever. Second call: a clean answer."""

    def __init__(self, garbage: str, loops: int = 400):
        self.calls = 0
        self.chunks_read = 0
        self.garbage = garbage
        self.loops = loops
        self.seen_messages: list[list[dict]] = []

    def complete(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def capabilities(self, model):
        return ModelCapabilities()

    def stream(self, *, model, messages, tools=None, **settings):
        self.calls += 1
        self.seen_messages.append(list(messages))
        if self.calls == 1:
            yield StreamChunk(text_delta="Let me look at the files.\n\n")
            for _ in range(self.loops):
                self.chunks_read += 1
                yield StreamChunk(text_delta=self.garbage)
                time.sleep(0.002)  # a network stream has pacing; a list does not
            yield StreamChunk(turn=AssistantTurn(text="never used", finish_reason="stop"))
            return
        yield StreamChunk(text_delta="Done.")
        yield StreamChunk(turn=AssistantTurn(text="Done.", finish_reason="stop"))


def _engine(tmp_path, provider):
    return TurnEngine(
        provider=provider,
        registry=ToolRegistry(),
        permissions=PermissionEngine(workspace_root=tmp_path),
        model="qualitati:mimi-puppy",
    )


def _run(engine, text="annotate the comments"):
    async def go():
        return [e async for e in engine.run(text)]

    return asyncio.run(go())


def test_native_tool_markup_cuts_the_stream_and_the_model_redoes_the_step(tmp_path):
    provider = _MarkupThenClean("<｜DSML｜invoke_code>\n")
    engine = _engine(tmp_path, provider)
    events = _run(engine)

    types = [e.type for e in events]
    assert types[-1] == EventType.TURN_END and events[-1].data["status"] == "completed"
    notice = next(e for e in events if e.type == EventType.NOTICE and e.data.get("kind") == "degenerate")
    assert "raw tool markup" in notice.data["text"]
    # The stream is abandoned early — the provider does not get to hand over 400 laps
    # of garbage (and a gateway stops generating the moment the connection drops).
    assert provider.chunks_read < 100
    # The transcript keeps the prose, none of the markup, then the steer, then the redo.
    assistants = [m for m in engine.messages if m.get("role") == "assistant"]
    assert assistants[0]["content"] == "Let me look at the files."
    assert "DSML" not in assistants[0]["content"]
    steer = next(m for m in engine.messages if m.get("steering") == "degenerate")
    assert "raw tool-call markup" in steer["content"]
    assert assistants[-1]["content"] == "Done."
    # The model saw the steer on its second call.
    assert any("raw tool-call markup" in str(m.get("content")) for m in provider.seen_messages[1])
    # Nothing of the markup reached the live view either.
    streamed = "".join(e.data["text"] for e in events if e.type == EventType.ASSISTANT_DELTA)
    assert "DSML" not in streamed


def test_a_line_repeated_for_ever_is_cut_the_same_way(tmp_path):
    provider = _MarkupThenClean("I will now read the file.\n", loops=300)
    engine = _engine(tmp_path, provider)
    events = _run(engine)
    assert events[-1].data["status"] == "completed"
    notice = next(e for e in events if e.type == EventType.NOTICE and e.data.get("kind") == "degenerate")
    assert "repeating itself" in notice.data["text"]
    assert provider.chunks_read < 150
    first = [m for m in engine.messages if m.get("role") == "assistant"][0]["content"]
    assert first.startswith("Let me look at the files.")
    assert first.count("I will now read the file.") <= 1


def test_strip_keeps_prose_and_drops_the_breakdown():
    assert _strip_degenerate("Hello.\n\n<｜DSML｜invoke_code>\n<｜DSML｜oke_code>") == "Hello."
    assert _strip_degenerate("A\nB\nB\nB\nB\nB\nB") == "A"
    assert _strip_degenerate("A\nB\nA\nB") == "A\nB\nA\nB"
    assert _strip_degenerate("<|DSML|x>garbage") == ""
