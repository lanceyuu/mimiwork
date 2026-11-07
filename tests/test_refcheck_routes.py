"""The reference check as the panel and the chat reach it: routes, writes, the tool."""

from __future__ import annotations

import json
import re

import pytest

from coworker import refcheck
from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient
from coworker.refcheck.verdicts import Lookups
from coworker.server import SessionManager

docx = pytest.importorskip("docx")

TITLE = "Ego depletion: Is the active self a limited resource?"
DOI = "10.1037/0022-3514.74.5.1252"
ENTRY = f"Baumiester, R. (1998). {TITLE}. JPSP, 74, 1252."
RECORD = {"DOI": DOI, "title": [TITLE], "type": "journal-article", "issued": {"date-parts": [[1998]]}, "author": [{"family": "Baumeister", "given": "Roy"}]}


class _Reader(ProviderClient):
    """Reads each numbered paragraph as one entry by the misspelled Baumiester."""

    def __init__(self):
        self.calls = 0

    def complete(self, *, model, messages, tools=None, **settings):
        self.calls += 1
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


def test_the_chat_tool_refuses_a_file_outside_the_folders(setup):
    manager, provider, _ = setup
    out = manager.get_engine("s1").registry.execute("check_references", {"path": "/etc/hosts.docx"})
    assert "error" in out and provider.calls == 0
