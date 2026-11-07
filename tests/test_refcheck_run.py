"""A whole check of a Word file: writability, saved results, one run at a time, and
planning the fixes a click writes."""

from __future__ import annotations

import json
import os
import threading
import time

import pytest

from coworker.refcheck import check_file, plan_fixes, prune
from coworker.refcheck.verdicts import Lookups
from coworker.tools.office.docx_tools import _indexed_blocks, _para_text, apply_tracked_revisions

docx = pytest.importorskip("docx")

TITLE = "Ego depletion: Is the active self a limited resource?"
DOI = "10.1037/0022-3514.74.5.1252"
RECORD = {"DOI": DOI, "title": [TITLE], "type": "journal-article", "issued": {"date-parts": [[1998]]}, "author": [{"family": "Baumeister", "given": "Roy"}]}


def lookups(record=RECORD, retracted=False):
    if retracted:
        record = {**record, "updated-by": [{"type": "retraction", "updated": {"date-parts": [[2010]]}}]}
    return Lookups(
        crossref_work=lambda doi: {"ok": False, "error": "no_such_doi"},
        crossref_search=lambda text: {"ok": True, "items": [record]},
        csl_record=lambda doi: {"ok": False, "error": "lookup_failed"},
        openalex_title=lambda title: {"ok": True, "results": []},
        formatted=lambda doi, style: {"ok": True, "text": "Formatted."},
    )


class Model:
    """Reads every non-empty paragraph as one entry by Baumiester (misspelled)."""

    def __init__(self, spans=None):
        self.calls = 0
        self.spans = spans

    def __call__(self, system, user):
        self.calls += 1
        lines = [line.split("] ", 1) for line in user.splitlines()]
        entries = []
        for number, text in lines:
            k = int(number.strip("["))
            if self.spans and k not in self.spans:
                continue
            printed = self.spans[k] if self.spans else text
            entries.append({"first": k, "last": k, "text": printed, "title": TITLE, "surname": "Baumiester", "year": "1998", "doi": None})
        return json.dumps({"style": "apa", "entries": entries})


def _doc(tmp_path, entries, name="paper.docx", link=False):
    document = docx.Document()
    document.add_paragraph("References")
    for text in entries:
        p = document.add_paragraph(text)
        if link:
            from docx.oxml import OxmlElement

            h = OxmlElement("w:hyperlink")
            r = OxmlElement("w:r")
            t = OxmlElement("w:t")
            t.text = " https://example.org"
            r.append(t)
            h.append(r)
            p._p.append(h)
    path = tmp_path / name
    document.save(path)
    return path


ENTRY = f"Baumiester, R. (1998). {TITLE}. JPSP, 74, 1252."


def run(path, tmp_path, model=None, lk=None, **kw):
    return check_file(path, complete=model or Model(), lookups=lk or lookups(), cache_dir=tmp_path / "cache", **kw)


def test_a_fix_in_a_plain_paragraph_is_writable_and_ticked(tmp_path):
    result = run(_doc(tmp_path, [ENTRY]), tmp_path)
    (row,) = result["entries"]
    assert row["group"] == "fix" and row["paragraph"] == 1
    (fix,) = row["fixes"]
    assert fix["kind"] == "replace_surname" and fix["writable"] and fix["ticked"]
    assert result["counts"] == {"total": 1, "verified": 0, "fix": 1, "not_found": 0, "retracted": 0, "couldnt": 0}


def test_a_fix_on_a_retracted_entry_is_shown_unticked(tmp_path):
    (row,) = run(_doc(tmp_path, [ENTRY]), tmp_path, lk=lookups(retracted=True))["entries"]
    assert row["group"] == "retracted"
    assert row["fixes"][0]["writable"] and not row["fixes"][0]["ticked"]


def test_an_entry_holding_a_link_is_suggestion_only(tmp_path):
    (row,) = run(_doc(tmp_path, [ENTRY], link=True), tmp_path)["entries"]
    assert not row["fixes"][0]["writable"] and row["layout"]


def test_two_entries_sharing_a_paragraph_are_suggestion_only(tmp_path):
    second = f"Baumiester, R. (1998). {TITLE}. Again."
    path = _doc(tmp_path, [f"{ENTRY} {second}"])

    def complete(system, user):
        return json.dumps({"entries": [
            {"first": 0, "last": 0, "text": ENTRY, "title": TITLE, "surname": "Baumiester", "year": "1998"},
            {"first": 0, "last": 0, "text": second, "title": TITLE, "surname": "Baumiester", "year": "1998"},
        ]})

    rows = check_file(path, complete=complete, lookups=lookups(), cache_dir=tmp_path / "cache")["entries"]
    assert all(not f["writable"] for r in rows for f in r["fixes"])
    assert all(r["layout"] for r in rows)


def test_a_list_made_by_a_citation_tool_is_never_writable(tmp_path, monkeypatch):
    from coworker.refcheck import reading

    real = reading.load_docx

    def managed(path):
        listing = real(path)
        listing.managed = "Zotero"
        return listing

    monkeypatch.setattr(reading, "load_docx", managed)
    result = run(_doc(tmp_path, [ENTRY]), tmp_path)
    assert result["managed"] == "Zotero"
    assert not result["entries"][0]["fixes"][0]["writable"]


def test_a_second_check_of_the_same_file_uses_the_saved_result(tmp_path):
    path = _doc(tmp_path, [ENTRY])
    model = Model()
    run(path, tmp_path, model=model)
    again = run(path, tmp_path, model=model)
    assert again["ok"] and model.calls == 1
    assert run(path, tmp_path, model=model, fresh=True)["ok"] and model.calls == 2


def test_asking_only_for_a_saved_result_never_calls_the_model(tmp_path):
    model = Model()
    assert run(_doc(tmp_path, [ENTRY]), tmp_path, model=model, cached_only=True) == {"ok": False, "cached": False}
    assert model.calls == 0


def test_two_checks_at_once_make_one_run(tmp_path):
    path = _doc(tmp_path, [ENTRY])
    gate = threading.Event()
    model = Model()

    def slow(system, user):
        gate.wait(2)
        return model(system, user)

    results = []
    threads = [threading.Thread(target=lambda: results.append(run(path, tmp_path, model=slow))) for _ in range(2)]
    for t in threads:
        t.start()
    time.sleep(0.1)
    gate.set()
    for t in threads:
        t.join()
    assert model.calls == 1 and all(r["ok"] for r in results)


def test_a_file_with_no_list_and_a_failed_read_are_errors_not_crashes(tmp_path):
    path = _doc(tmp_path, [ENTRY])
    assert run(path, tmp_path, model=lambda s, u: '{"entries": []}')["error"] == "no_list"
    assert run(path, tmp_path, model=lambda s, u: "no idea", fresh=True)["error"] == "read_failed"

    def broken(system, user):
        raise RuntimeError("gateway down")

    assert run(path, tmp_path, model=broken, fresh=True)["error"] == "read_failed"


def test_planning_refuses_a_file_that_changed_since_the_check(tmp_path):
    path = _doc(tmp_path, [ENTRY])
    result = run(path, tmp_path)
    path.write_bytes(path.read_bytes() + b" ")
    assert plan_fixes(path, [result["entries"][0]["fixes"][0]["id"]], result["hash"], cache_dir=tmp_path / "cache")["error"] == "changed"


def test_a_surname_and_a_doi_fix_on_one_paragraph_both_land_as_tracked_changes(tmp_path):
    text = f"Baumiester, R. (1998). {TITLE}. https://doi.org/10.1000/gone"

    def complete(system, user):
        return json.dumps({"entries": [{"first": 0, "last": 0, "text": text, "title": TITLE, "surname": "Baumiester", "year": "1998", "doi": "10.1000/gone"}]})

    path = _doc(tmp_path, [text])
    result = check_file(path, complete=complete, lookups=lookups(), cache_dir=tmp_path / "cache")
    ids = [f["id"] for f in result["entries"][0]["fixes"]]
    assert len(ids) == 2
    plan = plan_fixes(path, ids, result["hash"], cache_dir=tmp_path / "cache")
    assert plan["ok"] and plan["count"] == 2
    apply_tracked_revisions(path, plan["edits"])
    para = _indexed_blocks(docx.Document(str(path)))[1]
    assert _para_text(para) == f"Baumeister, R. (1998). {TITLE}. https://doi.org/{DOI.lower()}"


def test_planning_refuses_a_fix_that_is_not_writable(tmp_path):
    path = _doc(tmp_path, [ENTRY], link=True)
    result = run(path, tmp_path)
    fix_id = result["entries"][0]["fixes"][0]["id"]
    assert plan_fixes(path, [fix_id], result["hash"], cache_dir=tmp_path / "cache")["error"] == "not_writable"


def test_results_older_than_ninety_days_are_pruned(tmp_path):
    folder = tmp_path / "cache"
    folder.mkdir()
    old, new = folder / "old.json", folder / "new.json"
    old.write_text("{}")
    new.write_text("{}")
    past = time.time() - 91 * 86400
    os.utime(old, (past, past))
    prune(folder)
    assert not old.exists() and new.exists()


def test_a_doi_the_model_cut_short_leaves_the_correct_printed_doi_alone(tmp_path):
    text = f"Baumeister, R. (1998). {TITLE}. https://doi.org/{DOI}"

    def complete(system, user):
        return json.dumps({"entries": [{"first": 0, "last": 0, "text": text, "title": TITLE, "surname": "Baumeister", "year": "1998", "doi": "10.1037/0022-3514.74.5"}]})

    found = {**RECORD, "author": [{"family": "Baumeister", "given": "Roy"}]}
    lk = Lookups(
        crossref_work=lambda doi: {"ok": True, "record": found} if doi == DOI.lower() else {"ok": False, "error": "no_such_doi"},
        crossref_search=lambda t: {"ok": True, "items": [found]},
        csl_record=lambda d: {"ok": False},
        openalex_title=lambda t: {"ok": True, "results": []},
        formatted=lambda d, s: {"ok": True, "text": "x"},
    )
    (row,) = check_file(_doc(tmp_path, [text]), complete=complete, lookups=lk, cache_dir=tmp_path / "cache")["entries"]
    assert row["group"] == "verified" and row["fixes"] == []


def _saved(tmp_path, result):
    return tmp_path / "cache" / f"{result['hash']}.json"


def test_a_result_saved_by_an_older_version_is_checked_again(tmp_path):
    path = _doc(tmp_path, [ENTRY])
    model = Model()
    saved = _saved(tmp_path, run(path, tmp_path, model=model))
    data = json.loads(saved.read_text())
    data.pop("version")
    saved.write_text(json.dumps(data))
    assert run(path, tmp_path, model=model)["ok"] and model.calls == 2


def test_a_saved_result_without_counts_is_checked_again_not_a_crash(tmp_path):
    path = _doc(tmp_path, [ENTRY])
    model = Model()
    saved = _saved(tmp_path, run(path, tmp_path, model=model))
    data = json.loads(saved.read_text())
    data.pop("counts")
    saved.write_text(json.dumps(data))
    assert run(path, tmp_path, model=model)["ok"] and model.calls == 2


def test_a_saved_result_holding_couldnt_check_entries_is_not_reused(tmp_path):
    path = _doc(tmp_path, [ENTRY])
    model = Model()
    offline = Lookups(
        crossref_work=lambda doi: {"ok": False, "error": "lookup_failed"},
        crossref_search=lambda text: {"ok": False, "error": "lookup_failed"},
        csl_record=lambda doi: {"ok": False, "error": "lookup_failed"},
        openalex_title=lambda title: {"ok": False, "error": "lookup_failed"},
        formatted=lambda doi, style: {"ok": False},
    )
    first = run(path, tmp_path, model=model, lk=offline)
    assert first["counts"]["couldnt"] == 1
    assert run(path, tmp_path, model=model, cached_only=True)["hash"] == first["hash"]
    assert run(path, tmp_path, model=model)["counts"]["couldnt"] == 0 and model.calls == 2


def test_a_save_cut_short_is_pruned_with_the_old_results(tmp_path):
    folder = tmp_path / "cache"
    folder.mkdir()
    tmp = folder / "abc.tmp"
    tmp.write_text("{")
    past = time.time() - 91 * 86400
    os.utime(tmp, (past, past))
    prune(folder)
    assert not tmp.exists()


def test_a_password_protected_pdf_is_an_error_of_its_own(tmp_path, monkeypatch):
    from coworker.refcheck import reading
    from coworker.refcheck.reading import Listing

    monkeypatch.setattr(reading, "load_pdf", lambda path: Listing("pdf", [], password=True))
    path = tmp_path / "locked.pdf"
    path.write_bytes(b"%PDF-1.7")
    assert run(path, tmp_path)["error"] == "password"


def test_planning_refuses_an_id_the_saved_result_does_not_hold(tmp_path):
    path = _doc(tmp_path, [ENTRY])
    result = run(path, tmp_path)
    real = result["entries"][0]["fixes"][0]["id"]
    assert plan_fixes(path, [real, "e0000000000.replace_doi"], result["hash"], cache_dir=tmp_path / "cache")["error"] == "changed"


def test_a_span_ending_past_the_text_is_refused():
    from coworker.refcheck.verdicts import apply_spans

    assert apply_spans("abc", [{"start": 2, "end": 4, "new": "x"}]) is None
    assert apply_spans("abc", [{"start": 2, "end": 3, "new": "x"}]) == "abx"


def test_the_file_text_of_an_entry_is_its_paragraphs_own_text_or_nothing():
    from collections import Counter
    from types import SimpleNamespace

    from coworker.refcheck.reading import Listing, Para
    from coworker.refcheck.run import _file_text

    paras = [Para("Baumeister, R. (1998). “Ego”"), Para("depletion. JPSP.")]
    e = SimpleNamespace(first=0, last=1, text='Baumeister, R. (1998). "Ego" depletion. JPSP.')
    assert _file_text(e, Listing("docx", paras), Counter([0, 1])) == "Baumeister, R. (1998). “Ego” depletion. JPSP."
    assert _file_text(e, Listing("docx", paras), Counter([0, 1, 1])) is None  # a paragraph two entries share
    assert _file_text(e, Listing("pdf", paras), Counter([0, 1])) is None
    other = SimpleNamespace(first=0, last=1, text="Someone else entirely.")
    assert _file_text(other, Listing("docx", paras), Counter([0, 1])) is None


def test_a_list_made_by_a_citation_tool_offers_one_text_with_every_fix_applied(tmp_path, monkeypatch):
    from coworker.refcheck import reading

    real = reading.load_docx

    def managed(path):
        listing = real(path)
        listing.managed = "Zotero"
        return listing

    monkeypatch.setattr(reading, "load_docx", managed)
    printed = f"{ENTRY} https://doi.org/10.9999/wrong"

    def complete(system, user):
        return json.dumps({"style": "apa", "entries": [
            {"first": 0, "last": 0, "text": printed, "title": TITLE, "surname": "Baumiester", "year": "1998", "doi": "10.9999/wrong"},
        ]})

    (row,) = check_file(_doc(tmp_path, [printed]), complete=complete, lookups=lookups(), cache_dir=tmp_path / "cache")["entries"]
    assert sorted(f["kind"] for f in row["fixes"]) == ["replace_doi", "replace_surname"]
    # Each fix's own copy undoes the other; the combined one carries both.
    assert row["fixed_text"] == f"Baumeister, R. (1998). {TITLE}. JPSP, 74, 1252. https://doi.org/{DOI}"


def test_a_writable_entry_or_a_single_fix_has_no_combined_text(tmp_path):
    (row,) = run(_doc(tmp_path, [ENTRY]), tmp_path)["entries"]
    assert "fixed_text" not in row
    (row,) = run(_doc(tmp_path, [ENTRY], name="link.docx", link=True), tmp_path)["entries"]
    assert len(row["fixes"]) == 1 and "fixed_text" not in row
