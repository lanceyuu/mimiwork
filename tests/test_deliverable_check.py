"""Deliverable self-check: reopen what a tool wrote and report what's wrong."""

import pytest

from coworker import deliverable_check as dc


def test_missing_and_empty_files_are_flagged(tmp_path):
    assert dc.check(tmp_path / "nope.md")["issues"] == ["the file does not exist after writing"]
    empty = tmp_path / "empty.md"
    empty.write_bytes(b"")
    assert dc.check(empty)["issues"] == ["the file is empty (0 bytes)"]


def test_placeholders_in_text_deliverables(tmp_path):
    f = tmp_path / "memo.md"
    f.write_text("# Memo\n\nTODO write intro. [Insert figure 2 here] Lorem ipsum dolor.\n")
    report = dc.check(f)
    assert not report["ok"]
    (issue,) = report["issues"]
    assert "placeholder" in issue
    assert "TODO" in issue and "[Insert figure 2 here]" in issue and "Lorem ipsum" in issue


def test_clean_text_passes(tmp_path):
    f = tmp_path / "memo.md"
    f.write_text("# Memo\n\nAll findings are final. The todo-list app shipped.\n")
    assert dc.check(f) == {"ok": True, "issues": []}  # 'todo-list' ≠ TODO token


def test_unknown_types_are_ignored(tmp_path):
    f = tmp_path / "blob.bin"
    f.write_bytes(b"\x00\x01TODO")
    assert dc.check(f)["ok"]


def test_docx_structure_and_placeholders(tmp_path):
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_paragraph("Just one line [insert conclusion]")
    p = tmp_path / "draft.docx"
    d.save(str(p))
    report = dc.check(p)
    assert not report["ok"]
    assert any("single paragraph" in i for i in report["issues"])
    assert any("placeholder" in i for i in report["issues"])

    d = docx.Document()
    d.add_heading("Results", 1)
    d.add_paragraph("Revenue grew 12%.")
    p2 = tmp_path / "good.docx"
    d.save(str(p2))
    assert dc.check(p2)["ok"]


def test_unparsable_docx_is_reported(tmp_path):
    pytest.importorskip("docx")
    p = tmp_path / "broken.docx"
    p.write_bytes(b"this is not a zip")
    report = dc.check(p)
    assert not report["ok"] and "could not be opened" in report["issues"][0]


def test_attach_only_adds_verification_when_needed(tmp_path):
    good = tmp_path / "ok.md"
    good.write_text("# Fine\n\nDone.\n")
    assert dc.attach({"path": "ok.md"}, good) == {"path": "ok.md"}
    bad = tmp_path / "bad.md"
    bad.write_text("TBD")
    out = dc.attach({"path": "bad.md"}, bad)
    assert out["verification"]["ok"] is False
    assert "Fix these" in out["verification"]["instruction"]
