"""Qualtrics: reach the account's surveys, read what the questions actually ask, and pull
responses down as a real file — with the download, and only the download, asking first.

The line this file protects: survey *metadata* is a free read, respondent *answers* are
not. `qualtrics_export_responses` is registered as a write, so the permission engine stops
on it — same rule the owner set for QualiTaTi research data.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

import pytest

from coworker.connectors import qualtrics as qt
from coworker.risk import RiskClass, classify, is_consequential
from coworker.roots import RootDir
from coworker.secrets import SecretStore

DC = "fra1"
BASE = "https://fra1.qualtrics.com/API/v3"


# --------------------------------------------------------------------------- helpers


def _tools(tmp_path, monkeypatch, calls, *, responses=None, payload=b"", writable=True):
    """Connected Qualtrics + every HTTP call recorded instead of made."""
    import coworker.connectors.integration_tools as it

    secrets = SecretStore(tmp_path / "secrets.json")
    secrets.put(
        "qualtrics:default",
        {"datacenter": DC, "api_token": "qt-token", "enabled": True},
    )
    queued = list(responses or [])

    def fake_request(method, url, *, headers=None, params=None, json=None, auth=None):
        calls.append(
            {
                "method": method,
                "url": url,
                "headers": headers or {},
                "params": params,
                "json": json,
            }
        )
        if queued:
            return queued.pop(0)
        return {"ok": True, "data": {"result": {}}}

    def fake_download(url, *, headers=None, timeout=120.0):
        calls.append({"method": "GET", "url": url, "headers": headers or {}, "download": True})
        return payload, None

    monkeypatch.setattr(it, "_request", fake_request)
    monkeypatch.setattr(it, "_download_bytes", fake_download)
    monkeypatch.setattr(it.time, "sleep", lambda _s: None)
    scratch = tmp_path / "session"
    scratch.mkdir(exist_ok=True)
    roots = [RootDir(path=scratch, writable=writable)]
    tools = {
        t.__name__: t
        for t in it.make_integration_tools(secrets, roots=roots)
        if t.__name__.startswith("qualtrics_")
    }
    return tools, scratch


def _ok(result: Any) -> dict:
    return {"ok": True, "data": {"result": result}}


def _zip(name: str, body: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr(name, body)
    return buf.getvalue()


# ------------------------------------------------------------------- the base URL


@pytest.mark.parametrize(
    "value,expected",
    [
        ("fra1", "https://fra1.qualtrics.com"),
        ("  IAD1 ", "https://iad1.qualtrics.com"),
        ("syd1.qualtrics.com", "https://syd1.qualtrics.com"),
        ("https://fra1.qualtrics.com/API/v3", "https://fra1.qualtrics.com"),
        ("acme.eu.qualtrics.com", "https://acme.eu.qualtrics.com"),
    ],
)
def test_the_datacenter_can_be_a_code_a_host_or_a_pasted_url(value, expected):
    assert qt.base_url(value) == expected


@pytest.mark.parametrize(
    "value",
    ["", "   ", "evil.example.com", "https://qualtrics.com.attacker.net", "http://x"],
)
def test_a_host_that_is_not_qualtrics_gets_no_url_at_all(value):
    """The API token rides in a header on every call — a typo'd or hostile base must not
    be where it gets sent."""
    assert qt.base_url(value) == ""


def test_a_next_page_url_is_only_followed_on_the_accounts_own_host():
    assert qt.same_host("https://fra1.qualtrics.com/API/v3/surveys?offset=100", DC)
    assert not qt.same_host("https://attacker.example/API/v3/surveys", DC)


# ------------------------------------------------------------- reading a questionnaire


SURVEY = {
    "id": "SV_1",
    "name": "Onboarding study",
    "isActive": True,
    "lastModifiedDate": "2026-08-01T10:00:00Z",
    "responseCounts": {"auditable": 412, "generated": 0, "deleted": 3},
    "questions": {
        "QID4": {
            "questionName": "Q4",
            "questionText": "<span style='font-size:14px'>How satisfied were you with…</span>",
            "questionType": {"type": "Matrix", "selector": "Likert"},
            "choices": {
                "1": {"choiceText": "Very dissatisfied"},
                "5": {"choiceText": "Very satisfied"},
            },
            "subQuestions": {
                "1": {"choiceText": "Speed of setup"},
                "2": {"choiceText": "Clarity of the guide"},
            },
        },
        "QID9": {
            "questionName": "Q9",
            "questionText": "Anything else?",
            "questionType": {"type": "TE", "selector": "ESTB"},
        },
    },
    "exportColumnMap": {
        "Q4_1": {"question": "QID4", "subQuestion": "1"},
        "Q4_2": {"question": "QID4", "subQuestion": "2"},
        "Q9": {"question": "QID9"},
        "StartDate": {"question": "startDate"},
    },
    "flow": [{"huge": "x" * 5000}],
}


def test_the_questionnaire_comes_back_readable_and_without_the_flow():
    got = qt.summarize_survey(SURVEY)
    assert got["name"] == "Onboarding study" and got["response_counts"]["auditable"] == 412
    q4 = next(q for q in got["questions"] if q["qid"] == "QID4")
    assert q4["text"] == "How satisfied were you with…"  # html stripped
    assert q4["choices"] == ["Very dissatisfied", "Very satisfied"]
    assert q4["sub_questions"] == ["Speed of setup", "Clarity of the guide"]
    assert "flow" not in got


def test_every_export_column_says_what_it_asks():
    """Without this, Q4_1 is a column of numbers and any summary written from it is a
    guess — the Qualtrics equivalent of a missing SPSS variable label."""
    columns = qt.summarize_survey(SURVEY)["columns"]
    assert columns["Q4_1"] == "How satisfied were you with… — Speed of setup"
    assert columns["Q9"] == "Anything else?"
    assert "StartDate" not in columns  # metadata columns describe themselves


def test_a_survey_with_hundreds_of_questions_is_capped_and_says_so():
    big = {"questions": {f"QID{i}": {"questionText": f"Q{i}"} for i in range(400)}}
    got = qt.summarize_survey(big)
    assert got["question_count"] == 400
    assert len(got["questions"]) == 150 and got["questions_truncated"] is True


# ------------------------------------------------------------------ the downloaded zip


def test_the_archive_cannot_choose_a_path_on_this_disk():
    members = qt.unpack(_zip("../../evil.csv", b"col\n1\n"))
    assert members == [("evil.csv", b"col\n1\n")]


def test_a_payload_that_is_not_a_zip_is_handed_back_as_it_arrived():
    assert qt.unpack(b"col,val\n1,2\n") == []


# ------------------------------------------------------------------------- the tools


def test_reads_carry_the_token_and_hit_the_accounts_datacenter(tmp_path, monkeypatch):
    calls: list[dict] = []
    tools, _ = _tools(
        tmp_path,
        monkeypatch,
        calls,
        responses=[
            _ok({"elements": [{"id": "SV_1", "name": "Onboarding study", "isActive": True}]})
        ],
    )
    got = tools["qualtrics_list_surveys"]()
    assert got["surveys"] == [{"id": "SV_1", "name": "Onboarding study", "isActive": True}]
    assert calls[-1]["url"] == f"{BASE}/surveys"
    assert calls[-1]["headers"]["X-API-TOKEN"] == "qt-token"


def test_listing_follows_paging_but_only_on_its_own_host(tmp_path, monkeypatch):
    calls: list[dict] = []
    tools, _ = _tools(
        tmp_path,
        monkeypatch,
        calls,
        responses=[
            _ok(
                {
                    "elements": [{"id": "SV_1", "name": "Wave 1"}],
                    "nextPage": f"{BASE}/surveys?offset=100",
                }
            ),
            _ok(
                {
                    "elements": [{"id": "SV_2", "name": "Wave 2"}],
                    "nextPage": "https://attacker.example/x",
                }
            ),
        ],
    )
    got = tools["qualtrics_list_surveys"]()
    assert [s["id"] for s in got["surveys"]] == ["SV_1", "SV_2"]
    assert calls[1]["url"] == f"{BASE}/surveys?offset=100"
    assert got["more"] is False  # the off-host nextPage was dropped, not followed


def test_listing_can_filter_by_name(tmp_path, monkeypatch):
    calls: list[dict] = []
    tools, _ = _tools(
        tmp_path,
        monkeypatch,
        calls,
        responses=[
            _ok({"elements": [{"id": "SV_1", "name": "Wave 1"}, {"id": "SV_2", "name": "Pilot"}]})
        ],
    )
    got = tools["qualtrics_list_surveys"](name_contains="pilot")
    assert [s["id"] for s in got["surveys"]] == ["SV_2"]


def test_reading_a_survey_summarizes_it(tmp_path, monkeypatch):
    calls: list[dict] = []
    tools, _ = _tools(tmp_path, monkeypatch, calls, responses=[_ok(SURVEY)])
    got = tools["qualtrics_get_survey"]("SV_1")
    assert calls[-1]["url"] == f"{BASE}/surveys/SV_1"
    assert got["columns"]["Q4_2"].endswith("Clarity of the guide")


def test_distributions_report_fielding_without_reading_answers(tmp_path, monkeypatch):
    calls: list[dict] = []
    tools, _ = _tools(
        tmp_path,
        monkeypatch,
        calls,
        responses=[
            _ok(
                {
                    "elements": [
                        {
                            "id": "EMD_1",
                            "requestStatus": "Done",
                            "stats": {"sent": 500, "finished": 412},
                        }
                    ]
                }
            )
        ],
    )
    got = tools["qualtrics_list_distributions"]("SV_1")
    assert calls[-1]["params"] == {"surveyId": "SV_1"}
    assert got["distributions"][0]["stats"]["finished"] == 412


def test_ids_are_required(tmp_path, monkeypatch):
    tools, _ = _tools(tmp_path, monkeypatch, [])
    assert "required" in tools["qualtrics_get_survey"]("  ")["error"]
    assert "required" in tools["qualtrics_list_distributions"]("")["error"]
    assert "required" in tools["qualtrics_export_responses"]("")["error"]


# ------------------------------------------------------------------------ the export


def test_the_export_starts_polls_downloads_and_saves_a_real_file(tmp_path, monkeypatch):
    calls: list[dict] = []
    tools, scratch = _tools(
        tmp_path,
        monkeypatch,
        calls,
        responses=[
            _ok({"progressId": "ES_9", "percentComplete": 0, "status": "inProgress"}),
            _ok({"percentComplete": 50, "status": "inProgress"}),
            _ok({"percentComplete": 100, "status": "complete", "fileId": "FL_2"}),
        ],
        payload=_zip("Onboarding study.csv", b"Q4_1,Q9\n5,fine\n"),
    )
    got = tools["qualtrics_export_responses"]("SV_1", fmt="csv")
    assert got["ok"] is True
    assert calls[0]["method"] == "POST"
    assert calls[0]["url"] == f"{BASE}/surveys/SV_1/export-responses"
    assert calls[0]["json"] == {"format": "csv", "useLabels": True}
    assert calls[1]["url"] == f"{BASE}/surveys/SV_1/export-responses/ES_9"
    assert calls[-1]["url"] == f"{BASE}/surveys/SV_1/export-responses/FL_2/file"
    saved = scratch / "Onboarding study.csv"
    assert saved.read_bytes() == b"Q4_1,Q9\n5,fine\n" and got["path"] == str(saved)


def test_the_window_and_the_codes_switch_reach_the_request(tmp_path, monkeypatch):
    calls: list[dict] = []
    tools, _ = _tools(
        tmp_path,
        monkeypatch,
        calls,
        responses=[
            _ok({"progressId": "ES_9"}),
            _ok({"status": "complete", "fileId": "FL_2"}),
        ],
        payload=_zip("x.csv", b"a\n"),
    )
    tools["qualtrics_export_responses"](
        "SV_1", use_labels=False, start_date="2026-01-01T00:00:00Z", limit=100
    )
    assert calls[0]["json"] == {
        "format": "csv",
        "useLabels": False,
        "startDate": "2026-01-01T00:00:00Z",
        "limit": 100,
    }


def test_spss_saves_as_a_sav_so_the_analyst_gets_the_labels(tmp_path, monkeypatch):
    tools, scratch = _tools(
        tmp_path,
        monkeypatch,
        [],
        responses=[_ok({"progressId": "ES_9"}), _ok({"status": "complete", "fileId": "FL_2"})],
        payload=b"not-a-zip",
    )
    got = tools["qualtrics_export_responses"]("SV_1", fmt="spss", filename="wave1")
    assert got["path"] == str(scratch / "wave1.sav")
    assert (scratch / "wave1.sav").read_bytes() == b"not-a-zip"


def test_a_second_export_does_not_overwrite_the_first(tmp_path, monkeypatch):
    for _ in range(2):
        tools, scratch = _tools(
            tmp_path,
            monkeypatch,
            [],
            responses=[_ok({"progressId": "E"}), _ok({"status": "complete", "fileId": "F"})],
            payload=_zip("responses.csv", b"a\n"),
        )
        tools["qualtrics_export_responses"]("SV_1")
    assert (scratch / "responses.csv").exists() and (scratch / "responses-1.csv").exists()


def test_an_export_that_never_finishes_says_how_far_it_got(tmp_path, monkeypatch):
    tools, _ = _tools(
        tmp_path,
        monkeypatch,
        [],
        responses=[_ok({"progressId": "ES_9"})]
        + [_ok({"percentComplete": 40, "status": "inProgress"})] * 40,
    )
    got = tools["qualtrics_export_responses"]("SV_1", max_wait_seconds=5)
    assert "still running" in got["error"] and "40%" in got["error"]


def test_a_failed_export_is_reported_not_retried_forever(tmp_path, monkeypatch):
    tools, _ = _tools(
        tmp_path,
        monkeypatch,
        [],
        responses=[_ok({"progressId": "ES_9"}), _ok({"status": "failed"})],
    )
    assert "could not build" in tools["qualtrics_export_responses"]("SV_1")["error"]


def test_an_unknown_format_is_refused_before_anything_is_requested(tmp_path, monkeypatch):
    calls: list[dict] = []
    tools, _ = _tools(tmp_path, monkeypatch, calls)
    assert "fmt must be" in tools["qualtrics_export_responses"]("SV_1", fmt="parquet")["error"]
    assert calls == []


def test_a_read_only_session_folder_is_not_written_to(tmp_path, monkeypatch):
    calls: list[dict] = []
    tools, _ = _tools(tmp_path, monkeypatch, calls, writable=False)
    assert "writable" in tools["qualtrics_export_responses"]("SV_1")["error"]
    assert calls == []


# ------------------------------------------------------------- connection and consent


def test_signed_out_says_so_instead_of_calling_anything(tmp_path, monkeypatch):
    import coworker.connectors.integration_tools as it

    def boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("not connected must not reach the network")

    monkeypatch.setattr(it, "_request", boom)
    secrets = SecretStore(tmp_path / "secrets.json")
    tools = {t.__name__: t for t in it.make_integration_tools(secrets)}
    assert "not connected" in tools["qualtrics_list_surveys"]()["error"]


def test_a_stored_datacenter_that_is_not_qualtrics_stops_before_the_call(tmp_path, monkeypatch):
    import coworker.connectors.integration_tools as it

    def boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("a bad host must not receive the token")

    monkeypatch.setattr(it, "_request", boom)
    secrets = SecretStore(tmp_path / "secrets.json")
    secrets.put("qualtrics:default", {"datacenter": "evil.example.com", "api_token": "t"})
    tools = {t.__name__: t for t in it.make_integration_tools(secrets)}
    assert "qualtrics.com" in tools["qualtrics_list_surveys"]()["error"]


def test_only_the_download_of_answers_asks_the_user_first(tmp_path, monkeypatch):
    """Metadata is a free read; other people's answers moving onto this machine is the
    user's call, every time."""
    tools, _ = _tools(tmp_path, monkeypatch, [])
    export = tools["qualtrics_export_responses"]
    meta = export.__aisuite_tool_metadata__
    assert meta.requires_approval is True
    assert is_consequential(classify("qualtrics_export_responses", meta))
    for name in ("qualtrics_list_surveys", "qualtrics_get_survey", "qualtrics_list_distributions"):
        read_meta = tools[name].__aisuite_tool_metadata__
        assert read_meta.requires_approval is False
        assert classify(name, read_meta) is not RiskClass.EXTERNAL


def test_the_descriptor_asks_for_both_halves_of_the_credential():
    from coworker.connectors.descriptors import get_descriptor

    d = get_descriptor("qualtrics")
    assert d is not None and d.available and d.logo == "qualtrics"
    fields = {f.key: f for f in d.fields}
    assert set(fields) == {"datacenter", "api_token"}
    assert fields["api_token"].secret and not fields["datacenter"].secret


def test_validation_names_the_datacenter_instead_of_calling_a_stranger(monkeypatch):
    import httpx

    from coworker.connectors.descriptors import get_descriptor

    def boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("validation must not call a non-qualtrics host")

    monkeypatch.setattr(httpx, "request", boom)
    d = get_descriptor("qualtrics")
    got = d.validate({"datacenter": "not a datacenter!", "api_token": "t"})
    assert got.ok is False and "Datacenter" in got.error
