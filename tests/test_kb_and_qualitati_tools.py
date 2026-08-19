"""Mimi's offline knowledge base (`kb_search`) and the QualiTaTi project tools.

The KB tests hit the real bundled corpus — 4,000 entries load in ~0.1s, so no
fixture corpus is needed and the tests double as a bundle-integrity check.
The QualiTaTi tools are tested against a faked HTTP layer + SecretStore: these
must prove auth handling and the Mimi-delegation contract, not the server.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from coworker import kb
from coworker.tools.kb import kb_tools
from coworker.tools import qualitati_tools as qt_mod
from coworker.tools.qualitati_tools import qualitati_tools


# ── knowledge base ───────────────────────────────────────────────────────────


def test_kb_corpus_is_bundled_and_indexed():
    idx = kb._get_index()
    assert len(idx.docs) == 4000
    assert set(d.get("collection") for d in idx.docs) == set(kb.COLLECTIONS)


def test_kb_search_finds_methodology_answers():
    hits = kb.search("member checking credibility qualitative")
    assert hits and hits[0]["score"] > 0
    top_text = (hits[0]["title"] + hits[0]["content"]).lower()
    assert "member" in top_text or "credib" in top_text


def test_kb_collection_filter():
    hits = kb.search("brand loyalty", collection="interview_questions", k=3)
    assert hits and all(h["collection"] == "interview_questions" for h in hits)


def test_kb_search_tool_shape_and_caveat():
    tool = kb_tools()[0]
    assert tool.__name__ == "kb_search"
    out = tool("what is thematic analysis?")
    assert out["count"] == 5
    first = out["results"][0]
    assert set(first) >= {"id", "collection", "title", "content"}
    assert len(first["content"]) <= 701  # 700 + ellipsis
    # The corpus flags itself as citation-unverified; the caveat must surface.
    assert any("caveat" in r for r in out["results"])


def test_kb_search_tool_rejects_unknown_collection():
    tool = kb_tools()[0]
    assert "error" in tool("anything", collection="nope")


def test_kb_no_match_suggests_fallback():
    tool = kb_tools()[0]
    out = tool("zzzzqqqxxx")
    assert out["count"] == 0 and "web search" in out["note"]


# ── qualitati tools ──────────────────────────────────────────────────────────


@pytest.fixture()
def fake_gateway(monkeypatch):
    """Fake _load_auth + _call so tools run against a scripted server."""
    calls: list[tuple[str, str, dict, Any]] = []
    responses: list[tuple[int, Any]] = []

    def load_auth():
        return {"base": "https://q.example", "jwt": "jwt-token", "api_key": "qt_key"}

    def call(method, url, headers, body=None):
        calls.append((method, url, headers, body))
        return responses.pop(0)

    monkeypatch.setattr(qt_mod, "_load_auth", load_auth)
    monkeypatch.setattr(qt_mod, "_call", call)
    return type("G", (), {"calls": calls, "responses": responses})


def test_projects_prefers_api_key_and_slims_fields(fake_gateway):
    fake_gateway.responses.append(
        (200, [{"id": 1, "uuid": "u-1", "name": "Churn study", "project_type": "interview",
                "outline": "SECRET-LONG-TEXT", "created_at": "2026-08-01"}])
    )
    projects_tool, _ = qualitati_tools()
    out = projects_tool(project_type="interview")
    method, url, headers, _ = fake_gateway.calls[0]
    assert headers == {"X-API-Key": "qt_key"}
    assert url.endswith("/api/projects?project_type=interview")
    assert out["count"] == 1
    assert out["projects"][0]["name"] == "Churn study"
    assert "outline" not in out["projects"][0]  # slimmed — the model asks Mimi for detail


def test_mimi_creates_a_conversation_once_and_relays_reply(fake_gateway):
    fake_gateway.responses.extend(
        [
            (201, {"id": 77, "title": "MimiWork"}),
            (200, {"assistant_message": {"content": "3 interviews mention pricing."},
                   "tool_events": [{"name": "search_transcripts"}]}),
            (200, {"assistant_message": {"content": "Done."}, "tool_events": []}),
        ]
    )
    _, mimi = qualitati_tools()
    out = mimi("search my transcripts for pricing complaints", project_uuid="u-1")
    assert out == {"reply": "3 interviews mention pricing.", "actions_taken": ["search_transcripts"]}
    # Conversation reused on the second call — no second create.
    out2 = mimi("summarize them")
    assert out2["reply"] == "Done."
    urls = [u for _, u, _, _ in fake_gateway.calls]
    assert urls[0].endswith("/api/assistant/conversations")
    assert urls[1].endswith("/conversations/77/chat")
    assert urls[2].endswith("/conversations/77/chat")
    # project_uuid rode along as a project source
    assert fake_gateway.calls[1][3]["project_uuid"] == "u-1"
    assert fake_gateway.calls[1][3]["source_type"] == "project"


def test_mimi_uses_jwt_bearer(fake_gateway):
    fake_gateway.responses.extend(
        [(201, {"id": 1}), (200, {"assistant_message": {"content": "hi"}, "tool_events": []})]
    )
    _, mimi = qualitati_tools()
    mimi("hello")
    assert fake_gateway.calls[0][2] == {"Authorization": "Bearer jwt-token"}


def test_mimi_recovers_once_from_a_deleted_conversation(fake_gateway):
    fake_gateway.responses.extend(
        [
            (201, {"id": 5}),
            (404, {"detail": "gone"}),          # chat on deleted conversation
            (201, {"id": 6}),                   # fresh conversation
            (200, {"assistant_message": {"content": "recovered"}, "tool_events": []}),
        ]
    )
    _, mimi = qualitati_tools()
    assert mimi("hello")["reply"] == "recovered"


def test_daily_limit_is_reported_not_retried(fake_gateway):
    fake_gateway.responses.extend(
        [(201, {"id": 9}), (429, {"detail": {"code": "DAILY_LIMIT_REACHED"}})]
    )
    _, mimi = qualitati_tools()
    out = mimi("hello")
    assert "daily usage limit" in out["error"]
    assert len(fake_gateway.calls) == 2  # no retry loop on a limit


def test_signed_out_is_an_instruction_not_a_crash(monkeypatch):
    monkeypatch.setattr(
        qt_mod, "_load_auth", lambda: {"base": "https://q.example", "jwt": None, "api_key": None}
    )
    projects_tool, mimi = qualitati_tools()
    assert "sign in" in projects_tool()["error"]
    assert "sign in" in mimi("hello")["error"]


def test_expired_jwt_asks_for_reauth(fake_gateway):
    fake_gateway.responses.append((401, {"detail": "expired"}))
    _, mimi = qualitati_tools()
    assert "expired" in mimi("hello")["error"]
