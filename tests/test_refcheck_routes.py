"""The reference check as the panel and the chat reach it: routes, writes, the tool."""

from __future__ import annotations

import asyncio
import json
import re

import pytest
from fastapi.testclient import TestClient

from coworker import refcheck
from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient
from coworker.refcheck.verdicts import Lookups
from coworker.server import SessionManager, create_app

docx = pytest.importorskip("docx")

TITLE = "Ego depletion: Is the active self a limited resource?"
DOI = "10.1037/0022-3514.74.5.1252"
ENTRY = f"Baumiester, R. (1998). {TITLE}. JPSP, 74, 1252."
RECORD = {"DOI": DOI, "title": [TITLE], "type": "journal-article", "issued": {"date-parts": [[1998]]}, "author": [{"family": "Baumeister", "given": "Roy"}]}


class _Reader(ProviderClient):
    """Reads each numbered paragraph as one entry by the misspelled Baumiester."""

    def __init__(self):
        self.calls = 0
        self.models = []

    def complete(self, *, model, messages, tools=None, **settings):
        self.calls += 1
        self.models.append(model)
        user = messages[-1]["content"]
        entries = [
            {"first": int(n), "last": int(n), "text": text, "title": TITLE, "surname": "Baumiester", "year": "1998"}
            for n, text in re.findall(r"^\[(\d+)\] (.*)$", user, re.M)
        ]
        return AssistantTurn(text=json.dumps({"style": "apa", "entries": entries}), finish_reason="stop")

    def capabilities(self, model):
        return ModelCapabilities()


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(refcheck, "live_lookups", lambda secrets=None: Lookups(
        crossref_work=lambda doi: {"ok": False, "error": "no_such_doi"},
        crossref_search=lambda text: {"ok": True, "items": [RECORD]},
        csl_record=lambda doi: {"ok": False, "error": "lookup_failed"},
        openalex_title=lambda title: {"ok": True, "results": []},
        formatted=lambda doi, style: {"ok": True, "text": "Formatted."},
    ))
    provider = _Reader()
    manager = SessionManager(workspace=tmp_path, provider=provider)
    engine = manager.get_engine("s1", workspace=str(tmp_path))
    manager.save("s1", engine)
    document = docx.Document()
    document.add_paragraph("References")
    document.add_paragraph(ENTRY)
    document.save(tmp_path / "paper.docx")
    return manager, provider, tmp_path


def test_the_chat_tool_reports_problems_and_changes_nothing(setup):
    manager, _, ws = setup
    engine = manager.get_engine("s1")
    before = (ws / "paper.docx").read_bytes()
    out = engine.registry.execute("check_references", {"path": "paper.docx"})
    assert out["counts"]["fix"] == 1
    assert "spelled Baumeister" in out["problems"][0]["notes"][0]
    assert out["path"] == "paper.docx"
    assert (ws / "paper.docx").read_bytes() == before


def test_the_chat_tool_lists_the_checked_file_among_the_sessions_files():
    assert "check_references" in SessionManager._ARTIFACT_TOOLS


def test_the_chat_tool_uses_the_model_the_user_switched_to(setup):
    manager, provider, _ = setup
    engine = manager.get_engine("s1")
    engine.switch_model("other-model")
    engine.registry.execute("check_references", {"path": "paper.docx"})
    assert provider.models == ["other-model"]


def test_the_chat_tool_refuses_a_file_outside_the_folders(setup):
    manager, provider, _ = setup
    out = manager.get_engine("s1").registry.execute("check_references", {"path": "/etc/hosts.docx"})
    assert "error" in out and provider.calls == 0


def _client(manager):
    return TestClient(create_app(manager))


def _check(client, **body):
    return client.post("/v1/sessions/s1/artifacts/references", json={"path": "paper.docx", **body}).json()


def test_the_panel_checks_a_word_file_and_reopening_costs_nothing(setup):
    manager, provider, _ = setup
    client = _client(manager)
    assert _check(client, cached_only=True) == {"ok": False, "cached": False, "path": "paper.docx"}
    first = _check(client)
    assert first["ok"] and first["entries"][0]["fixes"][0]["writable"]
    assert _check(client, cached_only=True)["hash"] == first["hash"]
    assert provider.calls == 1


def test_only_word_and_pdf_files_are_checked(setup):
    manager, _, ws = setup
    (ws / "notes.md").write_text("# hi")
    out = _client(manager).post("/v1/sessions/s1/artifacts/references", json={"path": "notes.md"}).json()
    assert out["ok"] is False


def _write(client, result, ids=None):
    fix_ids = ids if ids is not None else [f["id"] for r in result["entries"] for f in r["fixes"] if f["ticked"]]
    return client.post("/v1/sessions/s1/artifacts/references/apply", json={"path": "paper.docx", "hash": result["hash"], "ids": fix_ids}).json()


def test_writing_fixes_lands_tracked_changes_with_their_own_undo_point(setup):
    manager, _, ws = setup
    client = _client(manager)
    result = _check(client)
    before = len(manager.list_recovery_points("s1"))
    out = _write(client, result)
    assert out == {"ok": True, "applied": 1, "path": "paper.docx"}
    from coworker.tools.office.docx_tools import _indexed_blocks, _para_text

    para = _indexed_blocks(docx.Document(str(ws / "paper.docx")))[1]
    assert _para_text(para).startswith("Baumeister, R. (1998).")
    points = manager.list_recovery_points("s1")
    assert len(points) == before + 1 and points[0]["files"][0]["name"] == "paper.docx"
    assert "s1" not in manager._running_sessions


def test_a_write_mid_turn_is_refused_and_the_claim_is_held_during_a_write(setup, monkeypatch):
    manager, _, _ = setup
    client = _client(manager)
    result = _check(client)
    assert manager.try_mark_running("s1")
    assert _write(client, result)["error"] == "busy"
    manager.release_run_claim("s1")
    seen = []
    monkeypatch.setattr(manager, "apply_reference_fixes", lambda *a: seen.append("s1" in manager._running_sessions) or {"ok": True})
    _write(client, result)
    assert seen == [True] and "s1" not in manager._running_sessions


async def test_a_wake_that_arrives_during_a_write_runs_once_the_write_ends(setup):
    manager, _, _ = setup
    assert manager.try_mark_running("s1")  # the write's claim
    await manager.deliver_to_session("s1", "Time to look at the inbox.")
    manager.release_run_claim("s1")
    engine = manager.get_engine("s1")
    for _ in range(100):
        if any(m.get("content") == "Time to look at the inbox." for m in engine.messages):
            break
        await asyncio.sleep(0.02)
    assert any(m.get("content") == "Time to look at the inbox." for m in engine.messages)
    for _ in range(100):
        if "s1" not in manager._running_sessions:
            break
        await asyncio.sleep(0.02)
    assert "s1" not in manager._running_sessions


def test_a_changed_file_is_refused(setup):
    manager, _, ws = setup
    client = _client(manager)
    result = _check(client)
    document = docx.Document(str(ws / "paper.docx"))
    document.add_paragraph("A new line.")
    document.save(ws / "paper.docx")
    assert _write(client, result)["error"] == "changed"


def test_a_file_word_has_open_is_refused(setup):
    manager, _, ws = setup
    client = _client(manager)
    result = _check(client)
    (ws / "~$per.docx").write_bytes(b"lock")  # Word shortens long names from the front
    assert _write(client, result)["error"] == "open_in_word"


def test_a_file_in_a_read_only_folder_is_refused(setup, tmp_path_factory):
    manager, _, ws = setup
    shelf = tmp_path_factory.mktemp("shelf")  # outside the session's own, writable folder
    (ws / "paper.docx").rename(shelf / "paper.docx")
    manager.add_root("s1", str(shelf), writable=False)
    client = _client(manager)
    result = client.post("/v1/sessions/s1/artifacts/references", json={"path": str(shelf / "paper.docx")}).json()
    ids = [f["id"] for r in result["entries"] for f in r["fixes"]]
    out = client.post("/v1/sessions/s1/artifacts/references/apply", json={"path": str(shelf / "paper.docx"), "hash": result["hash"], "ids": ids}).json()
    assert out["error"] == "read_only"


def test_the_openalex_key_is_saved_never_shown_and_can_be_removed(setup):
    manager, _, _ = setup
    client = _client(manager)
    assert client.get("/v1/scholarly").json() == {"has_key": False}
    assert client.post("/v1/scholarly", json={"api_key": "k-1"}).json() == {"ok": True, "has_key": True}
    assert "k-1" not in client.get("/v1/scholarly").text
    assert client.post("/v1/scholarly", json={"api_key": ""}).json() == {"ok": True, "has_key": False}
