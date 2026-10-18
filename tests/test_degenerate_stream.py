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


# --- the three loop shapes from the owner report of 2026-10-18 (Mimi Puppy) -----------
# Each one slipped past the old check, which only knew a single line repeated 25 times.

_REPLY = (
    "Shashank Dubey（HEC Paris 市场营销博士）的学术情况，给你结论：\n\n"
    "研究领域\n计算量化营销——强化学习、大语言模型、贝叶斯方法。\n\n"
    "已发表论文\n期刊一作：JPPM 2025, 44(3)，DOI 10.1177/07439156241311300\n\n"
    "需要我把论文摘要译成中文吗？说一声就行。😊\n\n"
)


class _Loops(ProviderClient):
    """Streams `garbage` for ever on every call listed in `bad_calls`, else answers."""

    def __init__(self, garbage: str, *, bad_calls=(1,), thinking=False, loops=400):
        self.calls = 0
        self.chunks_read = 0
        self.garbage, self.bad_calls, self.thinking, self.loops = garbage, bad_calls, thinking, loops

    def complete(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def capabilities(self, model):
        return ModelCapabilities()

    def stream(self, *, model, messages, tools=None, **settings):
        self.calls += 1
        if self.calls in self.bad_calls:
            for _ in range(self.loops):
                self.chunks_read += 1
                yield (StreamChunk(reasoning_delta=self.garbage) if self.thinking
                       else StreamChunk(text_delta=self.garbage))
                time.sleep(0.002)  # a network stream has pacing; a list does not
            yield StreamChunk(turn=AssistantTurn(text="never used", finish_reason="stop"))
            return
        yield StreamChunk(text_delta="Done.")
        yield StreamChunk(turn=AssistantTurn(text="Done.", finish_reason="stop"))


def _breakdown(events):
    return next(e for e in events if e.type == EventType.NOTICE and e.data.get("kind") == "degenerate")


def test_a_whole_reply_repeated_is_cut_to_one_copy(tmp_path):
    provider = _Loops(_REPLY, loops=60)
    engine = _engine(tmp_path, provider)
    events = _run(engine)
    assert "repeating itself" in _breakdown(events).data["text"]
    assert provider.chunks_read < 20
    first = [m for m in engine.messages if m.get("role") == "assistant"][0]["content"]
    assert first.count("DOI 10.1177/07439156241311300") == 1
    assert events[-1].data["status"] == "completed"


def test_short_lines_taking_turns_are_caught():
    import random

    random.seed(3)
    tail = "".join(random.choice(["好。😊\n\n", "收。😊\n\n", "嗯。😊\n\n"]) for _ in range(600))
    from coworker.engine import _degenerate_reason

    assert _degenerate_reason(tail[-4000:]) == "loop"


def test_a_loop_with_no_line_breaks_is_caught_and_cut(tmp_path):
    provider = _Loops("好。😊收。😊", loops=800)
    engine = _engine(tmp_path, provider)
    events = _run(engine)
    _breakdown(events)
    assert provider.chunks_read < 400
    assert _strip_degenerate("我就此收工。" + "好。😊收。😊" * 300) == "我就此收工。"


def test_looping_thinking_is_caught_too(tmp_path):
    provider = _Loops("Let me reconsider. ", thinking=True, loops=600)
    engine = _engine(tmp_path, provider)
    events = _run(engine)
    _breakdown(events)
    assert provider.chunks_read < 300
    assert events[-1].data["status"] == "completed"


def test_a_redo_that_breaks_down_again_ends_the_turn(tmp_path):
    provider = _Loops("好。😊收。😊", bad_calls=(1, 2, 3), loops=800)
    engine = _engine(tmp_path, provider)
    events = _run(engine)
    assert events[-1].type == EventType.TURN_END
    assert events[-1].data["status"] == "repetition_stop"
    assert provider.calls == 2


def test_long_tables_and_prose_are_not_mistaken_for_a_loop():
    import random
    from pathlib import Path

    from coworker.engine import _degenerate_reason

    random.seed(1)
    table = "| id | name | score | group |\n|---|---|---|---|\n" + "".join(
        f"| {i} | P{i:03d} | {random.randint(1, 7)} | {random.choice('AB')} |\n" for i in range(300)
    )
    assert _degenerate_reason(table[-4000:]) is None
    code = Path(__file__).resolve().parents[1].joinpath("coworker", "engine.py").read_text()
    assert _degenerate_reason(code[:4000]) is None
    assert _degenerate_reason(_REPLY) is None
