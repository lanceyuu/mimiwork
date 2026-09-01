"""QualiTaTi's research services from a MimiWork session (owner ask 2026-08-31).

The proofreader turns a .docx into a tracked-changes copy; the annotator codes a
spreadsheet of open-ended text. Both spend the user's QualiTaTi credits, so both are
approval-gated — an automation on Full access must not run a bill up silently.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from coworker.tools.qualitati_research_tools import qualitati_research_tools


def _ctx(tmp_path):
    return SimpleNamespace(
        workspace=str(tmp_path), roots=[{"path": str(tmp_path), "writable": True}]
    )


def _tools(tmp_path):
    return {t.__name__: t for t in qualitati_research_tools(_ctx(tmp_path))}


def _signed_in(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "coworker.tools.qualitati_research_tools._auth",
        lambda: {"base": "https://qt.test", "api_key": "qt_key"},
    )


def test_both_tools_ask_before_spending_credits(tmp_path):
    """The one thing that must not be silent. These charge the user's account, and an
    automation on Full access never sees an approval card unless the tool demands one."""
    for name, fn in _tools(tmp_path).items():
        meta = fn.__aisuite_tool_metadata__
        assert meta.requires_approval is True, f"{name} spends credits without asking"


def test_not_signed_in_says_where_to_sign_in(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "coworker.tools.qualitati_research_tools._auth",
        lambda: {"base": "https://qt.test", "api_key": None},
    )
    out = _tools(tmp_path)["qualitati_proofread"]("paper.docx")
    assert "Settings" in out["error"] and "QualiTaTi" in out["error"]


def test_a_file_outside_the_session_folders_is_refused(tmp_path, monkeypatch):
    """A tool that uploads files must not be talked into uploading whatever it is
    handed — the model chooses this path, and the user's machine is not the workspace."""
    _signed_in(monkeypatch, tmp_path)
    sent = []
    monkeypatch.setattr(
        "coworker.tools.qualitati_research_tools._multipart",
        lambda *a, **k: (sent.append(a) or (200, b"x", "")),
    )
    out = _tools(tmp_path)["qualitati_proofread"]("/etc/hosts")
    assert "No such file" in out["error"]
    assert not sent, "the tool tried to upload a file outside the session"


def test_only_docx_reaches_the_proofreader(tmp_path, monkeypatch):
    _signed_in(monkeypatch, tmp_path)
    (tmp_path / "notes.txt").write_text("hi", encoding="utf-8")
    out = _tools(tmp_path)["qualitati_proofread"]("notes.txt")
    assert ".docx" in out["error"]


def test_a_proofread_lands_next_to_the_original_as_a_tracked_copy(tmp_path, monkeypatch):
    _signed_in(monkeypatch, tmp_path)
    (tmp_path / "Chapter 3.docx").write_bytes(b"PK-original")
    monkeypatch.setattr(
        "coworker.tools.qualitati_research_tools._multipart",
        lambda url, key, path, fields, timeout: (200, b"PK-proofread", ""),
    )
    out = _tools(tmp_path)["qualitati_proofread"]("Chapter 3.docx", journal_name="JCR")

    assert out["ok"] and "racked changes" in out["note"]
    written = tmp_path / "Chapter 3 (proofread).docx"
    assert written.read_bytes() == b"PK-proofread"
    # The original is never overwritten — the user still has what they wrote.
    assert (tmp_path / "Chapter 3.docx").read_bytes() == b"PK-original"


def test_the_journal_context_is_actually_sent(tmp_path, monkeypatch):
    """Passing a journal is the difference between generic copy-editing and editing to
    that journal's conventions; dropping it silently would be worse than not offering it."""
    _signed_in(monkeypatch, tmp_path)
    (tmp_path / "p.docx").write_bytes(b"x")
    seen = {}

    def fake(url, key, path, fields, timeout):
        seen.update(fields)
        return 200, b"out", ""

    monkeypatch.setattr("coworker.tools.qualitati_research_tools._multipart", fake)
    _tools(tmp_path)["qualitati_proofread"](
        "p.docx", journal_name="JCR", author_guidelines="APA 7", reviewer_feedback="R2 wants effect sizes"
    )
    assert seen["journal_name"] == "JCR"
    assert seen["author_guidelines"] == "APA 7"
    assert seen["reviewer_feedback"] == "R2 wants effect sizes"


def test_an_expired_sign_in_says_so_instead_of_leaking_the_status(tmp_path, monkeypatch):
    _signed_in(monkeypatch, tmp_path)
    (tmp_path / "p.docx").write_bytes(b"x")
    monkeypatch.setattr(
        "coworker.tools.qualitati_research_tools._multipart",
        lambda *a, **k: (401, json.dumps({"detail": "Invalid or revoked API key"}).encode(), ""),
    )
    out = _tools(tmp_path)["qualitati_proofread"]("p.docx")
    assert "sign in again" in out["error"]


def test_running_out_of_credits_says_what_to_do(tmp_path, monkeypatch):
    _signed_in(monkeypatch, tmp_path)
    (tmp_path / "p.docx").write_bytes(b"x")
    monkeypatch.setattr(
        "coworker.tools.qualitati_research_tools._multipart",
        lambda *a, **k: (402, json.dumps({"detail": "insufficient credits"}).encode(), ""),
    )
    out = _tools(tmp_path)["qualitati_proofread"]("p.docx")
    assert "credits" in out["error"] and "top up" in out["error"]


def test_the_annotator_uploads_creates_a_job_waits_and_saves_the_result(tmp_path, monkeypatch):
    _signed_in(monkeypatch, tmp_path)
    (tmp_path / "open-ends.csv").write_text("text\nhello", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(
        "coworker.tools.qualitati_research_tools._multipart",
        lambda url, key, path, fields, timeout: (
            calls.append("upload"),
            (200, json.dumps({"uuid": "up-1"}).encode(), ""),
        )[1],
    )

    def fake_json(method, url, key, body=None, timeout=60.0):
        calls.append(f"{method} {url.rsplit('/api/', 1)[-1]}")
        if url.endswith("/models"):
            return 200, [{"provider": "openai", "model_id": "gpt-5.6-sol"}]
        if url.endswith("/jobs"):
            assert body["upload_id"] == "up-1"
            assert body["selected_models"] == [{"provider": "openai", "model_id": "gpt-5.6-sol"}]
            return 200, {"uuid": "job-1"}
        return 200, {"status": "completed"}

    monkeypatch.setattr("coworker.tools.qualitati_research_tools._json_call", fake_json)
    monkeypatch.setattr("coworker.tools.qualitati_research_tools._POLL_EVERY", 0)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    tools = qualitati_research_tools(_ctx(tmp_path))
    annotate = {t.__name__: t for t in tools}["qualitati_annotate"]
    # The download helper is a closure inside the factory, so patch the module's opener.
    import coworker.tools.qualitati_research_tools as mod

    class _Resp:
        status = 200
        headers = {"Content-Type": "application/octet-stream"}

        def read(self):
            return b"coded-xlsx"

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.request, "urlopen", lambda *a, **k: _Resp())

    out = annotate(
        "open-ends.csv",
        ["text"],
        [
            {
                "col_name": "sentiment",
                "label": "Sentiment",
                "categories": ["positive", "negative"],
                "definition": "Positive if the respondent expresses satisfaction, negative otherwise.",
            }
        ],
    )
    assert out["ok"], out
    assert (tmp_path / "open-ends (annotated).xlsx").read_bytes() == b"coded-xlsx"
    assert "upload" in calls and any("jobs" in c for c in calls)


def test_a_failed_annotation_job_says_so_rather_than_pretending(tmp_path, monkeypatch):
    _signed_in(monkeypatch, tmp_path)
    (tmp_path / "d.csv").write_text("text\nx", encoding="utf-8")
    monkeypatch.setattr(
        "coworker.tools.qualitati_research_tools._multipart",
        lambda *a, **k: (200, json.dumps({"uuid": "up-1"}).encode(), ""),
    )

    def fake_json(method, url, key, body=None, timeout=60.0):
        if url.endswith("/models"):
            return 200, [{"provider": "openai", "model_id": "m"}]
        if url.endswith("/jobs"):
            return 200, {"uuid": "job-1"}
        return 200, {"status": "failed"}

    monkeypatch.setattr("coworker.tools.qualitati_research_tools._json_call", fake_json)
    monkeypatch.setattr("coworker.tools.qualitati_research_tools._POLL_EVERY", 0)
    monkeypatch.setattr("time.sleep", lambda _s: None)

    annotate = _tools(tmp_path)["qualitati_annotate"]
    out = annotate("d.csv", ["text"], [{"col_name": "a", "label": "A", "categories": ["x", "y"], "definition": "d" * 25}])
    assert "failed" in out["error"] and out["job_id"] == "job-1"
