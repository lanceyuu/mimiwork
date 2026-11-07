"""What each lookup means for an entry, and the fixes code makes from it."""

from __future__ import annotations

import re

from coworker.refcheck.reading import Entry
from coworker.refcheck.verdicts import (
    Lookups,
    doi_form,
    group_of,
    look_up,
    make_fixes,
    mark_missing_dois,
)

DOI = "10.1037/0022-3514.74.5.1252"
TITLE = "Ego depletion: Is the active self a limited resource?"


def entry(text=None, title=TITLE, surname="Baumeister", year=1998, doi=None):
    text = text or f"Baumeister, R. F. (1998). {title}. JPSP, 74, 1252."
    return Entry("e1", 0, 0, text, title, surname, year, doi, bool(re.search(r"10\.\d{4,9}/", text)))


def cr(doi=DOI, title=TITLE, family="Baumeister", year=1998, kind="journal-article", updated=None, cites=5000, authors=None):
    record = {
        "DOI": doi,
        "title": [title],
        "type": kind,
        "issued": {"date-parts": [[year]]},
        "is-referenced-by-count": cites,
        "author": authors if authors is not None else [{"family": family, "given": "Roy F."}],
    }
    if updated:
        record["updated-by"] = updated
    return record


def lookups(works=None, search=None, csl=None, openalex=None):
    works = works or {}
    return Lookups(
        crossref_work=lambda doi: works.get(doi, {"ok": False, "error": "no_such_doi"}),
        crossref_search=lambda text: search if isinstance(search, dict) else {"ok": True, "items": search or []},
        csl_record=lambda doi: csl or {"ok": False, "error": "lookup_failed"},
        openalex_title=lambda title: openalex or {"ok": True, "results": []},
        formatted=lambda doi, style: {"ok": True, "text": f"[{style}] {doi}"},
    )


def codes(outcome):
    return [c["code"] for c in outcome.codes]


def test_an_entry_found_by_search_with_nothing_wrong_is_verified():
    out = look_up(entry(), lookups(search=[cr()]))
    assert codes(out) == [] and group_of(out.codes) == "verified"


def test_a_retracted_paper_is_retracted_with_its_year_and_notice():
    record = cr(updated=[{"type": "retraction", "DOI": "10.1000/notice", "updated": {"date-parts": [[2010]]}}])
    out = look_up(entry(), lookups(search=[record]))
    assert out.codes[0] == {"code": "retracted", "params": {"year": 2010, "notice": "10.1000/notice", "via": "crossref"}}
    assert group_of(out.codes) == "retracted"


def test_a_partly_retracted_paper_and_a_concern_are_told_apart():
    partly = cr(updated=[{"type": "partial_retraction", "updated": {"date-parts": [[2019]]}}])
    concern = cr(updated=[{"type": "expression_of_concern", "updated": {"date-parts": [[2019]]}}])
    assert codes(look_up(entry(), lookups(search=[partly]))) == ["partly_retracted"]
    out = look_up(entry(), lookups(search=[concern]))
    assert codes(out) == ["concern"] and group_of(out.codes) == "verified"


def test_a_doi_leading_to_another_paper_is_replaced_from_the_right_record():
    wrong = cr(doi="10.1000/other", title="A study of something else entirely")
    out = look_up(entry(doi="10.1000/other", text=f"Baumeister, R. F. (1998). {TITLE}. https://doi.org/10.1000/other"), lookups(works={"10.1000/other": {"ok": True, "record": wrong}}, search=[cr()]))
    assert out.codes[0]["code"] == "doi_other_paper"
    assert out.codes[0]["params"]["title"] == "A study of something else entirely"


def test_a_doi_that_does_not_exist_is_replaced_when_a_published_record_matches():
    out = look_up(entry(doi="10.1000/gone", text=f"Baumeister (1998). {TITLE}. doi:10.1000/gone"), lookups(search=[cr()]))
    assert codes(out) == ["doi_not_found"]


def test_a_wrong_doi_with_only_a_posted_copy_found_cannot_be_fixed():
    copy = cr(doi="10.65215/copy", kind="posted-content", year=2025)
    out = look_up(entry(doi="10.1000/gone", text=f"Baumeister (1998). {TITLE}. doi:10.1000/gone"), lookups(search=[copy]))
    assert codes(out) == ["found_copy", "doi_unfixable"]


def test_the_vaswani_copy_verifies_the_paper_and_never_supplies_a_doi():
    title = "Attention is all you need"
    copy = cr(doi="10.65215/r5bs2d54", title="Attention Is All You Need", family="Vaswani", year=2025, kind="posted-content")
    e = entry(text="Vaswani, A., et al. (2017). Attention is all you need. NeurIPS.", title=title, surname="Vaswani", year=2017)
    out = look_up(e, lookups(search=[copy]))
    assert codes(out) == ["found_copy"]
    assert make_fixes(e, out, e.text, "https://doi.org/") == []


def test_a_datacite_doi_for_the_same_paper_is_verified_as_found_elsewhere():
    csl = {"ok": True, "record": {"title": "Attention Is All You Need", "author": [{"family": "Vaswani", "given": "Ashish"}], "issued": {"date-parts": [[2017]]}, "type": "article"}}
    e = entry(text="Vaswani (2017). Attention is all you need. arXiv. 10.48550/arXiv.1706.03762", title="Attention is all you need", surname="Vaswani", year=2017, doi="10.48550/arxiv.1706.03762")
    lk = lookups(works={"10.48550/arxiv.1706.03762": {"ok": False, "error": "outside_crossref", "agency": "DataCite"}}, csl=csl)
    out = look_up(e, lk)
    assert out.codes == [{"code": "outside_crossref", "params": {"agency": "DataCite"}}]


def test_a_second_doi_for_the_same_work_is_not_called_wrong():
    twin = cr(doi="10.1000/twin", authors=[])
    out = look_up(entry(doi="10.1000/twin", text=f"Baumeister (1998). {TITLE}. 10.1000/twin"), lookups(works={"10.1000/twin": {"ok": True, "record": twin}}))
    assert codes(out) == []


def test_a_chapter_printed_with_its_books_doi_is_not_called_wrong():
    book = cr(doi="10.1000/book", title="Handbook of self-regulation", kind="edited-book")
    chapter = cr(doi="10.1000/chapter", kind="book-chapter")
    text = f"Baumeister, R. F. (1998). {TITLE}. In Handbook of self-regulation. 10.1000/book"
    out = look_up(entry(text=text, doi="10.1000/book"), lookups(works={"10.1000/book": {"ok": True, "record": book}}, search=[chapter]))
    assert codes(out) == ["chapter_doi"] and group_of(out.codes) == "verified"


def test_a_misspelled_first_author_is_fixed_but_a_different_author_order_is_not():
    misspelled = entry(text=f"Baumiester, R. F. (1998). {TITLE}.", surname="Baumiester")
    out = look_up(misspelled, lookups(search=[cr()]))
    assert out.codes == [{"code": "surname_differs", "params": {"surname": "Baumeister"}}]
    second = cr(authors=[{"family": "Baumeister", "given": "Roy"}, {"family": "Tice", "given": "Dianne"}])
    reordered = entry(text=f"Tice, D. (1998). {TITLE}.", surname="Tice")
    assert codes(look_up(reordered, lookups(search=[second]))) == []


def test_a_title_that_differs_slightly_gets_a_suggestion_in_the_lists_style():
    out = look_up(entry(title="Ego depletion: Is the active mind a limited resource?"), lookups(search=[cr()]), style="ieee")
    assert codes(out) == ["title_differs"]
    assert out.suggestion == f"[ieee] {DOI.lower()}"


def test_a_subtitle_left_out_raises_no_title_difference():
    record = cr(title="Self-efficacy")
    record["subtitle"] = ["Toward a unifying theory of behavioral change"]
    e = entry(text="Bandura, A. (1977). Self-efficacy. Psych Review.", title="Self-efficacy", surname="Bandura", year=1977)
    record["author"] = [{"family": "Bandura", "given": "Albert"}]
    record["issued"] = {"date-parts": [[1977]]}
    assert codes(look_up(e, lookups(search=[record]))) == []


def test_years_one_apart_are_a_note_and_further_apart_an_edition_question():
    assert codes(look_up(entry(year=1999), lookups(search=[cr()]))) == ["year_differs"]
    out = look_up(entry(year=2005), lookups(search=[cr()]))
    assert codes(out) == ["edition"] and out.suggestion
    book = cr(kind="book", year=1998)
    out = look_up(entry(year=2005), lookups(search=[book]))
    assert codes(out) == ["edition"] and out.codes[0]["params"]["book"] and out.suggestion is None


def test_an_entry_found_only_on_openalex_is_verified_with_a_note():
    work = {"display_name": TITLE, "publication_year": 1998, "authorships": [{"author": {"display_name": "Roy F. Baumeister"}}], "type": "article"}
    assert codes(look_up(entry(), lookups(openalex={"ok": True, "results": [work]}))) == ["found_openalex"]


def test_openalex_says_retracted_only_when_the_surname_is_the_first_authors():
    work = {"display_name": TITLE, "publication_year": 1998, "is_retracted": True, "authorships": [{"author": {"display_name": "Roy F. Baumeister"}}, {"author": {"display_name": "Dianne Tice"}}]}
    assert codes(look_up(entry(), lookups(openalex={"ok": True, "results": [work]}))) == ["retracted", "found_openalex"]
    looser = entry(text=f"Tice, D. (1998). {TITLE}.", surname="Tice")
    assert codes(look_up(looser, lookups(openalex={"ok": True, "results": [work]}))) == ["retracted_maybe", "found_openalex"]


def test_nothing_found_is_not_found_never_fake():
    out = look_up(entry(), lookups())
    assert codes(out) == ["not_found"] and group_of(out.codes) == "not_found"


def test_a_failed_lookup_a_missing_title_and_a_spent_budget_are_couldnt_check():
    assert codes(look_up(entry(), lookups(search={"ok": False, "error": "lookup_failed"}))) == ["lookup_failed"]
    assert codes(look_up(entry(title=None), lookups())) == ["no_title"]
    out = look_up(entry(), lookups(openalex={"ok": False, "error": "openalex_limit"}))
    assert codes(out) == ["openalex_limit"] and group_of(out.codes) == "couldnt"


def test_an_entry_with_several_codes_sits_in_the_first_group_in_order():
    record = cr(updated=[{"type": "retraction", "updated": {"date-parts": [[2010]]}}])
    out = look_up(entry(text=f"Baumiester (1998). {TITLE}.", surname="Baumiester"), lookups(search=[record]))
    assert set(codes(out)) == {"retracted", "surname_differs"} and group_of(out.codes) == "retracted"


def test_a_missing_doi_is_added_only_when_half_the_list_prints_dois():
    with_doi = [entry(text=f"A (1998). {TITLE}. https://doi.org/{DOI}", doi=DOI.lower()) for _ in range(2)]
    bare = entry()
    entries = with_doi + [bare]
    outcomes = [look_up(e, lookups(works={DOI.lower(): {"ok": True, "record": cr()}}, search=[cr()])) for e in entries]
    mark_missing_dois(entries, outcomes)
    assert codes(outcomes[2]) == ["doi_missing"]
    few = [bare, entry(), entry(text=f"A (1998). {TITLE}. https://doi.org/{DOI}", doi=DOI.lower())]
    outs = [look_up(e, lookups(works={DOI.lower(): {"ok": True, "record": cr()}}, search=[cr()])) for e in few]
    mark_missing_dois(few, outs)
    assert codes(outs[0]) == []


def test_a_missing_doi_is_never_added_when_the_entry_prints_a_doi_pattern():
    e = entry(text=f"Baumeister (1998). {TITLE}. 10.1037/broken text", doi=None)
    others = [entry(text=f"A (1998). {TITLE}. https://doi.org/{DOI}", doi=DOI.lower()) for _ in range(2)]
    entries = [e] + others
    outs = [look_up(x, lookups(works={DOI.lower(): {"ok": True, "record": cr()}}, search=[cr()])) for x in entries]
    mark_missing_dois(entries, outs)
    assert "doi_missing" not in codes(outs[0])


def test_a_replaced_doi_keeps_its_printed_prefix():
    text = f"Baumeister (1998). {TITLE}. https://doi.org/10.1000/GONE"
    e = entry(text=text, doi="10.1000/gone")
    out = look_up(e, lookups(search=[cr()]))
    (fix,) = make_fixes(e, out, text, "https://doi.org/")
    assert fix["kind"] == "replace_doi"
    assert fix["after"] == f"Baumeister (1998). {TITLE}. https://doi.org/{DOI.lower()}"


def test_an_added_doi_takes_the_form_the_list_uses():
    listing = [entry(text="A. doi:10.1000/a"), entry(text="B. doi:10.1000/b"), entry(text="C. https://doi.org/10.1000/c")]
    assert doi_form(listing) == "doi:"
    assert doi_form([entry()]) == "https://doi.org/"


def test_the_first_surname_occurrence_is_replaced_in_the_lists_casing():
    text = f"BAUMIESTER, R. F. (1998). {TITLE}. Baumiester again."
    e = entry(text=text, surname="BAUMIESTER")
    out = look_up(e, lookups(search=[cr(family="BAUMEISTER")]))
    (fix,) = make_fixes(e, out, text, "https://doi.org/")
    assert fix["after"] == f"BAUMEISTER, R. F. (1998). {TITLE}. Baumiester again."
    lower = f"Baumiester, R. F. (1998). {TITLE}."
    e2 = entry(text=lower, surname="Baumiester")
    (fix2,) = make_fixes(e2, look_up(e2, lookups(search=[cr(family="BAUMEISTER")])), lower, "https://doi.org/")
    assert fix2["new"] == "Baumeister"


def test_a_doi_that_is_only_the_start_of_the_printed_one_is_never_replaced_into_it():
    text = f"Baumeister, R. F. (1998). {TITLE}. https://doi.org/{DOI}"
    e = entry(text=text, doi="10.1037/0022-3514.74.5")
    out = look_up(e, lookups(search=[cr()]))
    assert all(not f["after"].endswith(".1252.1252") for f in make_fixes(e, out, text, "https://doi.org/"))
    assert make_fixes(e, out, text, "https://doi.org/") == []
