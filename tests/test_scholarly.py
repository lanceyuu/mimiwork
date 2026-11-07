"""Every network call for paper search and reference checks, against a fake transport."""

from __future__ import annotations

import logging
import threading
import time

import httpx
import pytest

from coworker import scholarly
from coworker.secrets import SecretStore


@pytest.fixture(autouse=True)
def _fresh_pace(monkeypatch):
    # Each test gets its own limiter so a slowed-down one never leaks into the next.
    monkeypatch.setattr(scholarly, "pace", scholarly._Pace(limit=3, interval=0.0))
    monkeypatch.setattr(scholarly, "_sleep", lambda s: None)
    yield
    scholarly.set_transport(None)


def _serve(handler):
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    scholarly.set_transport(httpx.MockTransport(wrapped))
    return seen


POLITE = {"x-api-pool": "polite-array"}
WORK = {
    "DOI": "10.1037/0033-295X.84.2.191",
    "type": "journal-article",
    "title": ["Self-efficacy"],
    "subtitle": ["Toward a unifying theory of behavioral change"],
    "author": [{"family": "Bandura", "given": "Albert"}],
    "issued": {"date-parts": [[1977]]},
}


def test_every_crossref_request_carries_the_project_contact_never_a_user_address():
    seen = _serve(lambda r: httpx.Response(200, json={"message": WORK}, headers=POLITE))
    scholarly.crossref_work("10.1037/0033-295X.84.2.191")
    assert seen[0].url.params["mailto"] == "contact@qualitati.com"
    assert "mailto:contact@qualitati.com" in seen[0].headers["user-agent"]


@pytest.mark.parametrize(
    "raw, doi",
    [
        ("https://doi.org/10.1037/0033-295X.84.2.191", "10.1037/0033-295x.84.2.191"),
        ("http://dx.doi.org/10.1037/abc.", "10.1037/abc"),
        ("DOI: 10.1037/abc;", "10.1037/abc"),
        ("10.1016/S0140-6736(97)11096-0", "10.1016/s0140-6736(97)11096-0"),
        ("10.1016/S0140-6736(97)11096-0)", "10.1016/s0140-6736(97)11096-0"),
        ("10.1037/ab\nc", "10.1037/abc"),
        ("see the paper", None),
        ("10.12/too-short-prefix", None),
    ],
)
def test_dois_are_normalised_the_way_people_print_them(raw, doi):
    assert scholarly.normalise_doi(raw) == doi


def test_a_crossref_404_on_a_datacite_doi_is_outside_crossref_not_missing():
    def handler(r):
        if r.url.host == "api.crossref.org":
            return httpx.Response(404, headers=POLITE)
        return httpx.Response(200, json=[{"DOI": "10.48550/arXiv.1706.03762", "RA": "DataCite"}])

    _serve(handler)
    assert scholarly.crossref_work("10.48550/arxiv.1706.03762") == {
        "ok": False,
        "error": "outside_crossref",
        "agency": "DataCite",
    }


def test_a_doi_that_exists_nowhere_is_no_such_doi():
    def handler(r):
        if r.url.host == "api.crossref.org":
            return httpx.Response(404, headers=POLITE)
        return httpx.Response(200, json=[{"DOI": "10.1234/x", "status": "DOI does not exist"}])

    _serve(handler)
    assert scholarly.crossref_work("10.1234/x")["error"] == "no_such_doi"


def test_a_failed_agency_lookup_is_lookup_failed_never_no_such_doi():
    def handler(r):
        if r.url.host == "api.crossref.org":
            return httpx.Response(404, headers=POLITE)
        return httpx.Response(503)

    _serve(handler)
    assert scholarly.crossref_work("10.1234/x")["error"] == "lookup_failed"


def test_a_network_failure_is_lookup_failed():
    def handler(r):
        raise httpx.ConnectError("offline")

    _serve(handler)
    assert scholarly.crossref_search("anything")["error"] == "lookup_failed"


def test_a_busy_reply_is_retried_once_after_its_retry_after():
    waits: list[float] = []
    replies = [httpx.Response(429, headers={"retry-after": "30"}), httpx.Response(200, json={"message": {"items": []}}, headers=POLITE)]
    scholarly._sleep = waits.append
    _serve(lambda r: replies.pop(0))
    assert scholarly.crossref_search("x") == {"ok": True, "items": []}
    assert waits == [10.0]  # capped: a stuck service must not stall a check for minutes


def test_at_most_three_crossref_requests_are_in_flight():
    lock = threading.Lock()
    state = {"now": 0, "peak": 0}

    def handler(r):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.02)
        with lock:
            state["now"] -= 1
        return httpx.Response(200, json={"message": {"items": []}}, headers=POLITE)

    _serve(handler)
    threads = [threading.Thread(target=scholarly.crossref_search, args=("x",)) for _ in range(9)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert state["peak"] == 3


def test_requests_start_no_faster_than_the_interval(monkeypatch):
    # A fake clock: wall-clock gaps measured in a handler are at the mercy of CI load.
    now = [100.0]
    monkeypatch.setattr(scholarly, "_clock", lambda: now[0])
    monkeypatch.setattr(scholarly, "_sleep", lambda s: now.__setitem__(0, now[0] + s))
    monkeypatch.setattr(scholarly, "pace", scholarly._Pace(limit=3, interval=0.5))
    starts: list[float] = []

    def handler(r):
        starts.append(now[0])
        return httpx.Response(200, json={"message": {"items": []}}, headers=POLITE)

    _serve(handler)
    for _ in range(4):
        scholarly.crossref_search("x")
    assert [b - a for a, b in zip(starts, starts[1:])] == [0.5, 0.5, 0.5]


def test_a_doi_org_redirect_off_the_registries_is_never_followed():
    # A DOI's registrant chooses where it resolves; the sidecar must never fetch a local
    # or private address because a reference list or a model named that DOI.
    def handler(r):
        if r.url.host == "doi.org":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:8765/v1/secret"})
        return httpx.Response(200, text="internal reply", headers={"content-type": "text/x-bibliography"})

    _serve(handler)
    assert scholarly.formatted("10.1000/x", "apa")["error"] == "cannot_format"


def test_a_doi_org_redirect_to_crossref_is_followed():
    def handler(r):
        if r.url.host == "doi.org":
            return httpx.Response(302, headers={"location": "https://api.crossref.org/v1/works/10.1000%2Fx/transform"})
        return httpx.Response(200, text="Author (2000). X.", headers={"content-type": "text/x-bibliography", **POLITE})

    _serve(handler)
    assert scholarly.formatted("10.1000/x", "apa") == {"ok": True, "text": "Author (2000). X."}


def test_a_reply_of_the_wrong_type_is_not_a_reference():
    _serve(lambda r: httpx.Response(200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"}))
    assert scholarly.formatted("10.1000/x", "apa")["error"] == "cannot_format"


def test_a_csl_record_comes_from_doi_org():
    _serve(lambda r: httpx.Response(200, json={"title": "Attention Is All You Need"}, headers={"content-type": "application/vnd.citationstyles.csl+json"}))
    assert scholarly.csl_record("10.48550/arxiv.1706.03762") == {"ok": True, "record": {"title": "Attention Is All You Need"}}


def test_leaving_the_polite_pool_slows_to_one_request_a_second():
    _serve(lambda r: httpx.Response(200, json={"message": {"items": []}}, headers={"x-api-pool": "public"}))
    scholarly.crossref_search("x")
    assert (scholarly.pace.limit, scholarly.pace.interval) == (1, 1.0)


def test_the_openalex_key_is_read_at_every_call_so_a_new_key_works_at_once():
    seen = _serve(lambda r: httpx.Response(200, json={"results": []}))
    store = SecretStore()
    scholarly.openalex_search("x", secrets=store)
    store.put("openalex:default", {"api_key": "k-123"})
    scholarly.openalex_search("x", secrets=store)
    assert "api_key" not in seen[0].url.params
    assert seen[1].url.params["api_key"] == "k-123"


def test_a_refused_openalex_key_is_an_error_not_a_quiet_fallback():
    store = SecretStore()
    store.put("openalex:default", {"api_key": "bad"})
    _serve(lambda r: httpx.Response(403))
    assert scholarly.openalex_search("x", secrets=store)["error"] == "openalex_key_refused"


def test_a_spent_openalex_budget_is_the_limit_error_without_waiting():
    waits: list[float] = []
    scholarly._sleep = waits.append
    _serve(lambda r: httpx.Response(429, headers={"retry-after": "40000"}))
    assert scholarly.openalex_title("x")["error"] == "openalex_limit"
    assert waits == []  # the budget resets daily; waiting would only stall the check


def test_no_request_url_with_a_key_reaches_the_log(caplog):
    store = SecretStore()
    store.put("openalex:default", {"api_key": "secret-key"})
    _serve(lambda r: httpx.Response(200, json={"results": []}))
    with caplog.at_level(logging.INFO):
        scholarly.openalex_search("x", secrets=store)
    assert "secret-key" not in caplog.text


def test_a_formatted_reference_arrives_as_plain_text():
    _serve(lambda r: httpx.Response(200, text="Vaswani, A., &amp; Polosukhin, I. (2017). <i>Attention Is All You Need</i>.", headers={"content-type": "text/x-bibliography"}))
    assert scholarly.formatted("10.48550/arxiv.1706.03762", "apa") == {
        "ok": True,
        "text": "Vaswani, A., & Polosukhin, I. (2017). Attention Is All You Need.",
    }


def test_only_a_404_means_a_doi_does_not_exist_when_formatting():
    _serve(lambda r: httpx.Response(406, text="style-not-found"))
    assert scholarly.formatted("10.1000/x", "apa")["error"] == "cannot_format"
    _serve(lambda r: httpx.Response(200, text="<html>landing page</html>", headers={"content-type": "text/html"}))
    assert scholarly.bibtex("10.1000/x")["error"] == "cannot_format"
    _serve(lambda r: httpx.Response(404))
    assert scholarly.formatted("10.1000/x", "apa")["error"] == "no_such_doi"


def test_a_record_title_joins_its_subtitle_and_drops_markup_and_a_retraction_prefix():
    assert scholarly.record_title(WORK) == (
        "Self-efficacy: Toward a unifying theory of behavioral change",
        "Self-efficacy",
        True,
    )
    assert scholarly.record_title({"title": ["RETRACTED: Ileal-lymphoid-nodular hyperplasia"]}) == (
        "Ileal-lymphoid-nodular hyperplasia",
        "Ileal-lymphoid-nodular hyperplasia",
        False,
    )
    assert scholarly.record_title({"title": ["H<sub>2</sub>O &amp; ice: a review"]}) == ("H2O & ice: a review", "H2O & ice", True)


def test_retraction_status_reads_the_strongest_notice_and_ignores_corrections():
    wakefield = {"updated-by": [
        {"type": "correction", "DOI": "10.1000/c", "updated": {"date-parts": [[2004, 3, 6]]}},
        {"type": "retraction", "DOI": "10.1016/s0140-6736(10)60175-4", "updated": {"date-parts": [[2010, 2, 6]]}},
    ]}
    assert scholarly.retraction(wakefield) == {"status": "retracted", "year": 2010, "notice": "10.1016/s0140-6736(10)60175-4"}
    assert scholarly.retraction({"updated-by": [{"type": "expression-of-concern", "updated": {"date-parts": [[2019]]}}]})["status"] == "concern"
    assert scholarly.retraction({"updated-by": [{"type": "partial_retraction", "updated": {"date-parts": [[2019]]}}]})["status"] == "partly_retracted"
    assert scholarly.retraction({"updated-by": [{"type": "correction"}]})["status"] == "none"
