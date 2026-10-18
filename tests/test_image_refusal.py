"""Switching to Mimi Hound after an image turn failed every message (owner report
2026-10-18): the gateway sent the history, image included, to an inference host that
answered "unsupported multimodal content: image_url". The model claims vision through
the service, so the capability check let the image through. The engine now retries the
step once with images as placeholders and keeps doing that for the model."""

from __future__ import annotations

import asyncio

from coworker.engine import TurnEngine
from coworker.events import EventType
from coworker.permissions import PermissionEngine
from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient, StreamChunk
from coworker.tools.registry import ToolRegistry

_REFUSAL = (
    "Error code: 424 - {'detail': \"upstream provider error: do-inference: Error code: 400 - "
    "{'error': {'message': 'unsupported multimodal content: image_url', 'type': "
    "'invalid_request_error'}}\"}"
)
_IMAGE = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}


class _RefusesImages(ProviderClient):
    def __init__(self):
        self.seen: list[list[dict]] = []

    def complete(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def capabilities(self, model):
        return ModelCapabilities(vision=True)  # what the service claims

    def stream(self, *, model, messages, tools=None, **settings):
        self.seen.append(list(messages))
        if any(
            isinstance(p, dict) and p.get("type") == "image_url"
            for m in messages
            if isinstance(m.get("content"), list)
            for p in m["content"]
        ):
            raise RuntimeError(_REFUSAL)
        yield StreamChunk(text_delta="ABS 3.")
        yield StreamChunk(turn=AssistantTurn(text="ABS 3.", finish_reason="stop"))


def _engine(tmp_path, provider):
    engine = TurnEngine(
        provider=provider,
        registry=ToolRegistry(),
        permissions=PermissionEngine(workspace_root=tmp_path),
        model="qualitati:mimi-hound",
    )
    engine.messages.append({"role": "user", "content": [{"type": "text", "text": "draw a cat"}, _IMAGE]})
    engine.messages.append({"role": "assistant", "content": "Here it is."})
    return engine


def _run(engine, text):
    async def go():
        return [e async for e in engine.run(text)]

    return asyncio.run(go())


def test_a_model_that_refuses_images_still_answers_with_placeholders(tmp_path):
    provider = _RefusesImages()
    engine = _engine(tmp_path, provider)
    events = _run(engine, "What is JPPM's ABS rating?")
    assert events[-1].type == EventType.TURN_END and events[-1].data["status"] == "completed"
    assert not [e for e in events if e.type == EventType.ERROR]
    assert any(e.type == EventType.NOTICE and e.data.get("kind") == "images_dropped" for e in events)
    assert "not viewable" in str(provider.seen[-1])

    # The next message goes straight to placeholders: no second refusal round-trip.
    calls = len(provider.seen)
    events = _run(engine, "And its impact factor?")
    assert events[-1].data["status"] == "completed"
    assert len(provider.seen) == calls + 1


def test_other_errors_are_not_mistaken_for_an_image_refusal(tmp_path):
    from coworker.providers.errors import is_image_refusal

    assert is_image_refusal(RuntimeError(_REFUSAL))
    assert not is_image_refusal(RuntimeError("Error code: 400 - context length exceeded"))
    assert not is_image_refusal(RuntimeError("Error code: 401 - invalid api key"))
