"""Mimi draws a picture (owner report 2026-09-29: "generate an image" ended in a poster
with an empty slot, because nothing in the app could make one). The QualiTaTi gateway
draws; this tool asks it, with the tier of the model answering the turn, and saves the
picture into the session's folder."""

from __future__ import annotations

import base64
import io
import json
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from coworker.permissions import Mode, PermissionEngine
from coworker.qualitati import AUTH_PROFILE, PROVIDER_PROFILE
from coworker.risk import RiskClass, classify
from coworker.roots import RootDir
from coworker.tools.context import tool_model
from coworker.tools.image_generation import image_generation_tools

PIL = pytest.importorskip("PIL.Image")


class _Secrets:
    def __init__(self, signed_in: bool = True) -> None:
        self._profiles = (
            {
                AUTH_PROFILE: {"access_token": "jwt-123", "base_url": "https://qt.example"},
                PROVIDER_PROFILE: {"api_key": "qt_key", "base_url": "https://qt.example/api/llm/v1"},
            }
            if signed_in
            else {}
        )

    def get(self, key: str) -> Any:
        return self._profiles.get(key)


def _picture(width: int = 64, height: int = 48) -> str:
    out = io.BytesIO()
    PIL.new("RGB", (width, height), "teal").save(out, format="PNG")
    return base64.b64encode(out.getvalue()).decode("ascii")


class _Reply:
    def __init__(self, status: int, body: Any, headers: dict[str, str] | None = None) -> None:
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = json.dumps(body)

    def json(self) -> Any:
        return self._body


@pytest.fixture
def gateway(monkeypatch):
    """The gateway as the tool sees it: records each request, answers with `reply`."""
    calls: list[dict[str, Any]] = []
    box = SimpleNamespace(
        calls=calls,
        reply=_Reply(200, {"data": [{"b64_json": _picture()}]}, {"X-Credits-Charged": "0", "X-Free-Images-Remaining": "9"}),
    )

    def post(url, headers=None, json=None, timeout=None):
        calls.append({"url": url, "headers": headers, "body": json})
        return box.reply

    monkeypatch.setattr(httpx, "post", post)
    return box


@pytest.fixture
def answering(request):
    """The model answering the turn, as the engine sets it for a tool."""
    token = tool_model.set(getattr(request, "param", "qualitati:mimi-hound"))
    yield
    tool_model.reset(token)


def _draw(folder, secrets=None):
    tools = image_generation_tools(secrets or _Secrets(), SimpleNamespace(workspace=folder, roots=None))
    return {t.__name__: t for t in tools}["generate_image"]


def test_the_picture_lands_in_the_folder_and_the_answer_says_what_it_cost(tmp_path, gateway, answering):
    got = _draw(tmp_path)("a white dog beside a can of cola", "dog.png")
    assert "error" not in got, got
    saved = PIL.open(tmp_path / "dog.png")
    assert (saved.width, saved.height) == (64, 48)
    assert got["path"] == "dog.png" and got["size"] == "64x48" and got["bytes"] > 0
    assert got["credits_charged"] == 0 and got["free_images_left_today"] == 9


def test_the_request_carries_the_tier_of_the_model_answering_the_turn(tmp_path, gateway, answering):
    _draw(tmp_path)("a lighthouse", "a.png", shape="landscape", quality="high")
    sent = gateway.calls[0]
    assert sent["url"] == "https://qt.example/api/llm/v1/images/generations"
    assert sent["headers"]["Authorization"] == "Bearer qt_key"
    assert sent["body"] == {"model": "mimi-hound", "prompt": "a lighthouse", "size": "1536x1024", "quality": "high", "n": 1}


@pytest.mark.parametrize("answering", ["anthropic:claude-opus-4-8", None], indirect=True)
def test_a_conversation_on_another_model_draws_on_the_free_tier(tmp_path, gateway, answering):
    _draw(tmp_path)("a lighthouse", "a.png")
    assert gateway.calls[0]["body"]["model"] == "mimi-puppy"


def test_a_paid_tier_reports_the_credits_it_spent(tmp_path, gateway, answering):
    gateway.reply = _Reply(200, {"data": [{"b64_json": _picture()}]}, {"X-Credits-Charged": "6", "X-Credits-Remaining": "412"})
    got = _draw(tmp_path)("a lighthouse", "a.png")
    assert got["credits_charged"] == 6 and got["credits_left"] == 412
    assert "free_images_left_today" not in got


def test_a_name_without_an_ending_is_saved_as_png(tmp_path, gateway, answering):
    assert _draw(tmp_path)("a lighthouse", "figures/lighthouse")["path"] == "figures/lighthouse.png"
    assert (tmp_path / "figures" / "lighthouse.png").is_file()


def test_a_jpeg_name_gets_a_jpeg(tmp_path, gateway, answering):
    _draw(tmp_path)("a lighthouse", "a.jpg")
    assert PIL.open(tmp_path / "a.jpg").format == "JPEG"


# Every refusal below has to come BEFORE the gateway is asked: a picture that is drawn and
# then cannot be saved has still spent the day's allowance, or the account's credits.
def test_a_file_that_is_already_there_is_not_written_over(tmp_path, gateway, answering):
    (tmp_path / "dog.png").write_bytes(b"the user's own picture")
    got = _draw(tmp_path)("a dog", "dog.png")
    assert "already exists" in got["error"]
    assert gateway.calls == []
    assert (tmp_path / "dog.png").read_bytes() == b"the user's own picture"
    assert "error" not in _draw(tmp_path)("a dog", "dog.png", overwrite=True)


def test_a_place_outside_the_granted_folders_is_refused(tmp_path, gateway, answering):
    folder = tmp_path / "granted"
    folder.mkdir()
    got = _draw(folder)("a dog", str(tmp_path / "elsewhere.png"))
    assert "error" in got and gateway.calls == []
    assert not (tmp_path / "elsewhere.png").exists()


def test_a_file_type_that_is_not_a_picture_is_refused(tmp_path, gateway, answering):
    assert "error" in _draw(tmp_path)("a dog", "dog.docx")
    assert gateway.calls == []


def test_an_empty_description_is_refused(tmp_path, gateway, answering):
    assert "error" in _draw(tmp_path)("   ", "dog.png")
    assert gateway.calls == []


def test_the_content_rules_apply_to_what_is_drawn(tmp_path, gateway, answering):
    got = _draw(tmp_path)("generate a nude photo of my neighbour", "x.png")
    assert "error" in got and gateway.calls == []


def test_signed_out_there_is_no_tool_to_offer():
    assert image_generation_tools(_Secrets(signed_in=False), SimpleNamespace(workspace="/tmp", roots=None)) == []


def test_signing_out_in_the_middle_of_a_conversation_says_so(tmp_path, gateway, answering):
    secrets = _Secrets()
    draw = _draw(tmp_path, secrets)
    secrets._profiles.clear()
    got = draw("a dog", "dog.png")
    assert "sign in" in got["error"].lower() and gateway.calls == []


@pytest.mark.parametrize(
    "reply, says",
    [
        # The gateway's own sentence is already written for the user.
        (_Reply(429, {"detail": {"code": "FREE_IMAGES_EXHAUSTED", "message": "Mimi Puppy and Mimi Hound generate 10 images a day for free, and today's are used."}}), "10 images a day"),
        (_Reply(402, {"detail": {"code": "INSUFFICIENT_CREDITS", "message": "Your QualiTaTi balance is empty."}}), "balance is empty"),
        (_Reply(400, {"detail": {"code": "IMAGE_REFUSED", "message": "the request was rejected by the safety system"}}), "rejected by the safety system"),
        (_Reply(503, {"detail": "gateway slot mimiwork.eu.puppy.image names a provider that cannot generate images"}), "cannot generate images"),
        # A server from before image generation answers the path itself with Not Found.
        (_Reply(404, {"detail": "Not Found"}), "cannot draw pictures yet"),
        (_Reply(401, {"detail": "invalid key"}), "sign in"),
    ],
)
def test_a_refusal_from_the_gateway_reaches_the_user_in_words(tmp_path, gateway, answering, reply, says):
    gateway.reply = reply
    got = _draw(tmp_path)("a dog", "dog.png")
    assert says.lower() in got["error"].lower()
    assert not (tmp_path / "dog.png").exists()


def test_an_answer_that_is_not_a_picture_is_an_error_and_leaves_no_file(tmp_path, gateway, answering):
    gateway.reply = _Reply(200, {"data": [{"b64_json": base64.b64encode(b"not an image").decode()}]})
    assert "error" in _draw(tmp_path)("a dog", "dog.png")
    assert not (tmp_path / "dog.png").exists()


def test_a_server_that_cannot_be_reached_is_an_error_not_a_crash(tmp_path, monkeypatch, answering):
    def post(*a, **k):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(httpx, "post", post)
    assert "could not be reached" in _draw(tmp_path)("a dog", "dog.png")["error"]


def test_drawing_is_a_write_into_the_folder_scoped_by_where_it_saves(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = _draw(workspace)
    metadata = tool.__aisuite_tool_metadata__
    assert classify("generate_image", metadata) is RiskClass.WRITE_LOCAL
    for mode in (Mode.PLAN, Mode.DISCUSS):
        decision = PermissionEngine(workspace, mode=mode).evaluate("generate_image", {}, metadata)
        assert not decision.allowed and not decision.needs_user
    assert PermissionEngine(workspace).evaluate("generate_image", {"prompt": "x", "output": "a.png"}, metadata).needs_user
    engine = PermissionEngine(workspace, mode=Mode.AUTO, roots=[RootDir(workspace, writable=True)])
    assert engine.evaluate("generate_image", {"prompt": "x", "output": "a.png"}, metadata).allowed
    assert not engine.evaluate("generate_image", {"prompt": "x", "output": str(tmp_path / "private.png")}, metadata).allowed


def test_a_picture_it_drew_counts_as_something_the_conversation_made():
    from coworker.recovery import _DIRECT_TARGETS
    from coworker.server.manager import SessionManager

    assert "generate_image" in SessionManager._ARTIFACT_TOOLS
    assert _DIRECT_TARGETS["generate_image"] == ("output",)


def test_the_coworker_can_draw_once_the_account_has_a_gateway_key(tmp_path, monkeypatch):
    from coworker.agent import build_engine
    from coworker.agents import chat_agent, cowork_agent
    from coworker.providers import AssistantTurn
    from coworker.providers.base import ModelCapabilities
    from coworker.secrets import SecretStore

    class _Provider:
        def complete(self, **_kw):  # pragma: no cover - never invoked at build time
            return AssistantTurn()

        def capabilities(self, _model):  # pragma: no cover
            return ModelCapabilities()

    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    folder = tmp_path / "folder"
    folder.mkdir()
    secrets = SecretStore(tmp_path / "secrets.json")

    def names(agent, **kw):
        return build_engine(agent=agent, provider=_Provider(), secrets=secrets, **kw).registry.names()

    assert "generate_image" not in names(cowork_agent(), workspace=folder)
    secrets.put(PROVIDER_PROFILE, {"api_key": "qt_key", "base_url": "https://qt.example/api/llm/v1"})
    assert "generate_image" in names(cowork_agent(), workspace=folder)
    # A picture is a file in a folder; a conversation without one has nowhere to put it.
    assert "generate_image" not in names(chat_agent())
