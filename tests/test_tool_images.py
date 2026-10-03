"""A chart is only checked if the model can see it. Images a tool hands back reach a vision
model as a follow-up message, never as base64 inside the tool result, and never as words the
user is supposed to have said. They ride ONE request: the gateway sends any image-bearing
request to its multimodal model, so images left in history would move the whole rest of the
session onto that model."""

from __future__ import annotations

import asyncio
import base64
import json

import aisuite as ai
from helpers import CapturingProvider, text_turn, tool_turn

from coworker.compaction import extract_user_messages
from coworker.engine import TurnEngine
from coworker.permissions import PermissionEngine
from coworker.providers import ModelCapabilities
from coworker.tools import ToolRegistry

PNG_BYTES = b"\x89PNG\r\n\x1a\nchart"


class _Provider(CapturingProvider):
    def __init__(self, turns, *, vision):
        super().__init__(turns)
        self.vision = vision

    def capabilities(self, model):
        return ModelCapabilities(vision=self.vision)


def _run(tmp_path, *, vision):
    chart = tmp_path / "figures" / "figure-01.png"
    chart.parent.mkdir()
    chart.write_bytes(PNG_BYTES)

    def plot() -> dict:
        """Draw a chart."""
        return {"ok": True, "figures": ["figures/figure-01.png"], "_images": [str(chart)]}

    def note() -> dict:
        """Take a note."""
        return {"ok": True}

    registry = ToolRegistry()
    for tool in (plot, note):
        tool.__aisuite_tool_metadata__ = ai.ToolMetadata(
            name=tool.__name__, category="analysis", risk_level="low",
            capabilities=["read"], requires_approval=False,
        )
        registry.register(tool)
    provider = _Provider(
        [tool_turn("plot", {}), tool_turn("note", {}, call_id="call_2"), text_turn("done")],
        vision=vision,
    )
    engine = TurnEngine(
        provider=provider,
        registry=registry,
        permissions=PermissionEngine(workspace_root=tmp_path),
        model="any-model",
    )

    async def _go():
        return [ev async for ev in engine.run("chart it")]

    asyncio.run(_go())
    return engine, provider


def _images(messages):
    return [
        p
        for m in messages
        if isinstance(m.get("content"), list)
        for p in m["content"]
        if isinstance(p, dict) and p.get("type") == "image_url"
    ]


def test_a_vision_model_sees_the_chart_a_tool_drew(tmp_path):
    engine, provider = _run(tmp_path, vision=True)

    after_tool = provider.calls[1]
    tool_message = next(m for m in after_tool if m.get("role") == "tool")
    assert "_images" not in tool_message["content"]
    assert "figures/figure-01.png" in tool_message["content"]
    expected = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()
    assert [p["image_url"]["url"] for p in _images(after_tool)] == [expected]
    assert after_tool[-1]["role"] == "user"


def test_the_chart_rides_only_the_request_right_after_it(tmp_path):
    engine, provider = _run(tmp_path, vision=True)

    later = provider.calls[2]
    assert _images(later) == []
    assert any("figure-01.png" in str(m.get("content")) for m in later if m.get("role") == "user")
    assert "base64" not in json.dumps(engine.messages)


def test_a_model_without_vision_is_not_sent_the_chart(tmp_path):
    engine, provider = _run(tmp_path, vision=False)

    assert _images(provider.calls[1]) == []
    assert not any(m.get("steering") == "figures" for m in engine.messages)


def test_engine_nudges_are_not_kept_as_the_users_own_words():
    span = [
        {"role": "user", "content": "plot revenue by region"},
        {"role": "user", "content": [{"type": "text", "text": "the charts"}], "steering": "figures"},
    ]
    assert extract_user_messages(span) == ["plot revenue by region"]
