"""Mimi's references come from real records: the two read-only paper tools."""

from __future__ import annotations

import httpx
import pytest

from coworker import scholarly
from coworker.secrets import SecretStore
from coworker.tools.papers import STYLES, paper_tools

OPENALEX_WORK = {
    "id": "https://openalex.org/W2626778328",
    "doi": "https://doi.org/10.48550/arxiv.1706.03762",
    "display_name": "Attention Is All You Need",
    "publication_year": 2017,
    "type": "preprint",
    "cited_by_count": 127852,
    "is_retracted": False,
    "authorships": [{"author": {"display_name": f"Author {i}"}} for i in range(8)],
    "primary_location": {"source": {"display_name": "arXiv (Cornell University)"}},
    "best_oa_location": {"pdf_url": "https://arxiv.org/pdf/1706.03762", "landing_page_url": "http://arxiv.org/abs/1706.03762"},
    "abstract_inverted_index": {"The": [0], "dominant": [1], "models": [2]},
}


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(scholarly, "pace", scholarly._Pace(limit=3, interval=0.0))
    monkeypatch.setattr(scholarly, "_sleep", lambda s: None)
    yield
    scholarly.set_transport(None)


def _tools():
    find, cite = paper_tools(SecretStore())
    return find, cite


def _serve(handler):
    scholarly.set_transport(httpx.MockTransport(handler))


def test_find_papers_returns_real_records_with_rebuilt_abstracts():
    _serve(lambda r: httpx.Response(200, json={"results": [OPENALEX_WORK]}))
    find, _ = _tools()
    paper = find("attention transformer")["papers"][0]
    assert paper["title"] == "Attention Is All You Need"
    assert paper["doi"] == "10.48550/arxiv.1706.03762"
    assert paper["authors"] == [f"Author {i}" for i in range(5)] + ["et al."]
    assert paper["abstract"] == "The dominant models"
    assert paper["free_to_read"] == "https://arxiv.org/pdf/1706.03762"
    assert paper["venue"] == "arXiv (Cornell University)"


def test_find_papers_falls_back_to_crossref_with_a_note_when_openalex_is_spent():
    def handler(r):
        if r.url.host == "api.openalex.org":
            return httpx.Response(429)
        return httpx.Response(200, json={"message": {"items": [{"DOI": "10.1000/a", "title": ["A paper"], "type": "journal-article", "issued": {"date-parts": [[2020]]}}]}}, headers={"x-api-pool": "polite-array"})

    _serve(handler)
    find, _ = _tools()
    out = find("a paper", from_year=2019)
    assert out["source"] == "Crossref"
    assert "free daily limit" in out["note"]
    assert out["papers"][0]["doi"] == "10.1000/a"


def test_find_papers_reports_a_refused_key_instead_of_hiding_it():
    store = SecretStore()
    store.put("openalex:default", {"api_key": "bad"})
    _serve(lambda r: httpx.Response(401))
    find, _ = paper_tools(store)
    assert "refused the saved key" in find("x")["error"]


def test_cite_paper_refuses_a_style_outside_the_list_and_names_the_list():
    _, cite = _tools()
    out = cite("10.1000/a", style="vancouver")
    assert "error" in out and all(s in out["error"] for s in STYLES)


def test_cite_paper_returns_the_reference_bibtex_and_retraction_status():
    def handler(r):
        if r.url.host == "api.crossref.org":
            return httpx.Response(200, json={"message": {"DOI": "10.1000/a", "title": ["A"], "updated-by": [{"type": "retraction", "DOI": "10.1000/n", "updated": {"date-parts": [[2010]]}}]}}, headers={"x-api-pool": "polite-array"})
        if "bibtex" in r.headers["accept"]:
            return httpx.Response(200, text="@article{a, title={A}}", headers={"content-type": "application/x-bibtex"})
        return httpx.Response(200, text="Author, A. (2000). A.", headers={"content-type": "text/x-bibliography"})

    _serve(handler)
    _, cite = _tools()
    out = cite("https://doi.org/10.1000/A")
    assert out["reference"] == "Author, A. (2000). A."
    assert out["bibtex"].startswith("@article")
    assert out["retraction"] == "retracted"
    assert "retracted" in out["warning"]


def test_cite_paper_reports_unknown_retraction_status_for_a_datacite_doi():
    def handler(r):
        if r.url.host == "api.crossref.org":
            return httpx.Response(404, headers={"x-api-pool": "polite-array"})
        if r.url.path.startswith("/ra/"):
            return httpx.Response(200, json=[{"RA": "DataCite"}])
        return httpx.Response(200, text="Vaswani (2017).", headers={"content-type": "text/x-bibliography"})

    _serve(handler)
    _, cite = _tools()
    assert cite("10.48550/arXiv.1706.03762")["retraction"] == "unknown"


def test_cite_paper_says_plainly_when_a_doi_does_not_exist():
    def handler(r):
        if r.url.host == "api.crossref.org":
            return httpx.Response(404, headers={"x-api-pool": "polite-array"})
        return httpx.Response(200, json=[{"status": "DOI does not exist"}])

    _serve(handler)
    _, cite = _tools()
    out = cite("10.1234/nope")
    assert out["error"] == "This DOI does not exist." and out["doi"] == "10.1234/nope"


def test_paper_tools_never_ask_for_approval():
    for tool in _tools():
        assert tool.__aisuite_tool_metadata__.requires_approval is False


def test_every_persona_gets_the_paper_tools_and_the_references_rule(tmp_path):
    from coworker.agent import _REPLY_GUIDANCE
    from coworker.server import SessionManager

    manager = SessionManager(workspace=tmp_path)
    engine = manager.get_engine("s1", workspace=str(tmp_path))
    names = set(engine.registry.names())
    assert {"find_papers", "cite_paper"} <= names
    assert "[source needed]" in _REPLY_GUIDANCE
    assert "Never write a reference from memory" in _REPLY_GUIDANCE


def test_the_unsourced_facts_nudge_points_at_find_papers():
    from coworker.engine import _UNSOURCED_TEXT

    assert "find_papers" in _UNSOURCED_TEXT
