"""Finding the reference list in Word and PDF files, and checking what the model read."""

from __future__ import annotations

import json
import re

import pytest

from coworker.refcheck import reading
from coworker.refcheck.reading import (
    Listing,
    Para,
    ReadFailed,
    is_heading,
    load_docx,
    load_pdf,
    read_entries,
)

docx = pytest.importorskip("docx")


def _save(tmp_path, paragraphs, name="paper.docx"):
    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    path = tmp_path / name
    document.save(path)
    return path, document


def _field(paragraph, instr):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    begin = OxmlElement("w:r")
    char = OxmlElement("w:fldChar")
    char.set(qn("w:fldCharType"), "begin")
    begin.append(char)
    code = OxmlElement("w:r")
    text = OxmlElement("w:instrText")
    text.text = instr
    code.append(text)
    paragraph._p.insert(0, code)
    paragraph._p.insert(0, begin)


def _fake_model(spans, texts=None):
    """A model that reports the given (first, last) spans that start inside each batch,
    cut at the batch's end like a real model seeing half an entry."""
    calls = []

    def complete(system, user):
        numbers = [int(n) for n in re.findall(r"^\[(\d+)\]", user, re.M)]
        lo, hi = min(numbers), max(numbers) + 1
        lines = dict(re.findall(r"^\[(\d+)\] (.*)$", user, re.M))
        calls.append((lo, hi, system))
        entries = []
        for first, last in spans:
            if lo <= first < hi:
                last = min(last, hi - 1)
                text = " ".join(lines[str(k)] for k in range(first, last + 1))
                entries.append({"first": first, "last": last, "text": (texts or {}).get(first, text), "title": None, "surname": None, "year": None, "doi": None})
        return json.dumps({"style": "apa", "entries": entries})

    return complete, calls


def _listing(n):
    return Listing("docx", [Para(f"Author{k}, A. ({1990 + k % 30}). Title number {k}.") for k in range(n)])


@pytest.mark.parametrize("text", ["References", "7. References", "VII. Bibliography:", "Literaturverzeichnis", "参考文献", "Works Cited"])
def test_reference_headings_are_recognised_with_numbers_and_in_other_languages(text):
    assert is_heading(text)


def test_a_sentence_mentioning_references_is_not_a_heading():
    assert not is_heading("References to earlier work are in section 2.")


def test_the_list_starts_after_the_last_heading_and_skips_empty_paragraphs(tmp_path):
    path, _ = _save(tmp_path, ["Intro", "References", "Old list", "Appendix", "References", "", "A, B. (2001). One.", "C, D. (2002). Two."])
    listing = load_docx(path)
    assert [p.text for p in listing.paras] == ["A, B. (2001). One.", "C, D. (2002). Two."]
    assert listing.heading_found and listing.managed is None
    assert listing.paras[0].index is not None and listing.paras[0].obj is not None


def test_with_no_heading_the_model_is_told_there_may_be_no_list(tmp_path):
    path, _ = _save(tmp_path, ["Just a memo.", "Nothing cited here."])
    listing = load_docx(path)
    assert not listing.heading_found
    complete, calls = _fake_model([])
    read_entries(listing, complete)
    assert "may hold no reference list" in calls[0][2]


def test_a_zotero_bibliography_field_marks_the_list_as_managed(tmp_path):
    document = docx.Document()
    document.add_paragraph("References")
    first = document.add_paragraph("A, B. (2001). One.")
    _field(first, ' ADDIN ZOTERO_BIBL {"uncited":[]} CSL_BIBLIOGRAPHY ')
    path = tmp_path / "z.docx"
    document.save(path)
    assert load_docx(path).managed == "Zotero"


def test_a_list_inside_a_bibliography_content_control_is_found_and_managed(tmp_path):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    document = docx.Document()
    document.add_paragraph("Text")
    sdt = OxmlElement("w:sdt")
    pr = OxmlElement("w:sdtPr")
    part = OxmlElement("w:docPartObj")
    gallery = OxmlElement("w:docPartGallery")
    gallery.set(qn("w:val"), "Bibliographies")
    part.append(gallery)
    pr.append(part)
    content = OxmlElement("w:sdtContent")
    sdt.append(pr)
    sdt.append(content)
    for text in ("Bibliography", "A, B. (2001). One."):
        p = document.add_paragraph(text)
        content.append(p._p)
    document.element.body.insert(1, sdt)
    path = tmp_path / "w.docx"
    document.save(path)
    listing = load_docx(path)
    assert [p.text for p in listing.paras] == ["A, B. (2001). One."]
    assert listing.managed == "Word's bibliography"
    assert listing.paras[0].index is None


class _Page:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


class _Reader:
    def __init__(self, pages):
        self.pages = [_Page(t) for t in pages]
        self.is_encrypted = False


def test_a_pdf_running_head_does_not_cut_the_list_to_its_last_page(monkeypatch, tmp_path):
    pages = [
        "Body text\nmore body\nmore\nmore\nmore\nReferences\nA, B. (2001). One. J.",
        "References\nC, D. (2002). Two. J.",
        "References\nE, F. (2003). Three. J.",
    ]
    monkeypatch.setattr("pypdf.PdfReader", lambda path: _Reader(pages))
    listing = load_pdf(tmp_path / "p.pdf")
    texts = [p.text for p in listing.paras]
    assert texts[0] == "A, B. (2001). One. J." and "E, F. (2003). Three. J." in texts


def test_a_scanned_pdf_is_reported_as_a_scan(monkeypatch, tmp_path):
    monkeypatch.setattr("pypdf.PdfReader", lambda path: _Reader(["", "  "]))
    assert load_pdf(tmp_path / "s.pdf").scan


def test_a_pdf_list_longer_than_the_cap_says_it_was_cut(monkeypatch, tmp_path):
    monkeypatch.setattr("pypdf.PdfReader", lambda path: _Reader(["References\n" + "\n".join("x" * 100 for _ in range(700))]))
    assert load_pdf(tmp_path / "l.pdf").cut


def test_quotes_dashes_and_ligatures_in_the_file_still_match_the_models_copy():
    listing = Listing("docx", [Para("Baumeister, R. (1998). The self‐regulation “ﬁeld”. J.")])
    complete, _ = _fake_model([(0, 0)], texts={0: 'Baumeister, R. (1998). The self-regulation "field". J.'})
    assert len(read_entries(listing, complete).entries) == 1


def test_an_entry_the_file_does_not_contain_is_dropped_and_counted():
    listing = Listing("docx", [Para("A, B. (2001). One.")])
    complete, _ = _fake_model([(0, 0)], texts={0: "Invented, X. (1999). Never printed."})
    result = read_entries(listing, complete)
    assert result.entries == [] and result.unread == 1


def test_fields_the_entry_does_not_print_are_discarded():
    listing = Listing("docx", [Para("Baumeister, R. (1998). Ego depletion. Journal, 74, 1252.")])

    def complete(system, user):
        return json.dumps({"entries": [{"first": 0, "last": 0, "text": "Baumeister, R. (1998). Ego depletion. Journal, 74, 1252.", "title": "Ego depletion: Is the active self a limited resource?", "surname": "Baumeister", "year": "1999", "doi": "10.1037/0022-3514.74.5.1252"}]})

    (e,) = read_entries(listing, complete).entries
    assert e.doi is None and e.year is None
    assert e.title is None  # the subtitle the model added is not in the entry
    assert e.surname == "Baumeister"


def test_an_entry_across_a_batch_seam_is_read_once_and_whole():
    listing = _listing(130)
    spans = [(k, k) for k in range(130) if k not in (59, 60)] + [(59, 60)]
    spans.sort()
    complete, _ = _fake_model(spans)
    entries = read_entries(listing, complete).entries
    assert [(e.first, e.last) for e in entries if e.first in (58, 59, 61)] == [(58, 58), (59, 60), (61, 61)]
    assert len(entries) == 129


def test_the_final_batch_keeps_its_last_entry():
    listing = _listing(10)
    complete, _ = _fake_model([(k, k) for k in range(10)])
    assert read_entries(listing, complete).entries[-1].first == 9


def test_a_batch_whose_only_entry_starts_at_its_first_paragraph_still_moves_on():
    listing = _listing(130)
    complete, calls = _fake_model([(0, 129)])
    read_entries(listing, complete)
    assert [c[0] for c in calls] == [0, 60, 120]


def test_empty_batches_move_on_and_calls_stop_at_eight_with_the_rest_counted():
    listing = _listing(600)
    complete, calls = _fake_model([])
    result = read_entries(listing, complete)
    assert len(calls) == 8 and result.not_checked == 120


def test_replies_that_are_never_json_fail_the_read():
    with pytest.raises(ReadFailed):
        read_entries(_listing(3), lambda s, u: "I cannot help with that.")


def test_the_list_style_comes_from_the_model_and_defaults_to_other():
    complete, _ = _fake_model([(0, 0)])
    assert read_entries(_listing(1), complete).style == "apa"
    assert read_entries(_listing(1), lambda s, u: '{"entries": []}').style == "other"


def test_entries_past_the_cap_are_counted_as_not_checked(monkeypatch):
    monkeypatch.setattr(reading, "MAX_ENTRIES", 2)
    complete, _ = _fake_model([(k, k) for k in range(5)])
    result = read_entries(_listing(5), complete)
    assert len(result.entries) == 2 and result.not_checked == 3


FULL_DOI = "10.1037/0022-3514.74.5.1252"


def _one(text, doi):
    def complete(system, user):
        return json.dumps({"entries": [{"first": 0, "last": 0, "text": text, "title": "Ego depletion", "surname": "Baumeister", "year": "1998", "doi": doi}]})

    return read_entries(Listing("docx", [Para(text)]), complete).entries[0]


def test_a_doi_the_model_cut_short_is_dropped_not_kept_as_a_prefix():
    text = f"Baumeister, R. (1998). Ego depletion. https://doi.org/{FULL_DOI}"
    assert _one(text, "10.1037/0022-3514.74.5").doi is None


def test_a_doi_ending_the_entry_with_a_full_stop_or_bracket_is_kept():
    assert _one(f"Baumeister, R. (1998). Ego depletion. doi:{FULL_DOI}.", FULL_DOI).doi == FULL_DOI
    assert _one(f"Baumeister, R. (1998). Ego depletion (doi:{FULL_DOI}).", FULL_DOI).doi == FULL_DOI
