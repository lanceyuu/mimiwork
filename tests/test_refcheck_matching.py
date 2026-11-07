"""Is this record the paper the entry cites? A false match writes a wrong fix, so the
tests below mostly prove the matcher says no."""

from __future__ import annotations

from types import SimpleNamespace

from coworker.refcheck.matching import best, from_crossref, from_openalex, loose, norm, same_paper


def entry(title, surname="Baumeister", year=1998):
    return SimpleNamespace(title=title, surname=surname, year=year)


def cr(title, family="Baumeister", given="Roy F.", year=1998, subtitle=None, kind="journal-article", cites=10, doi="10.1000/a", authors=None):
    record = {
        "DOI": doi,
        "title": [title],
        "type": kind,
        "issued": {"date-parts": [[year]]},
        "is-referenced-by-count": cites,
        "author": authors if authors is not None else [{"family": family, "given": given}],
    }
    if subtitle:
        record["subtitle"] = [subtitle]
    return from_crossref(record)


def test_loose_form_ignores_quotes_dashes_ligatures_and_pdf_hyphenation():
    assert loose("The self‐regulation “ﬁeld”, pp. 12 – 15") == loose('The self-regulation "field", pp. 12–15')
    assert loose("self-\nregulation") == loose("selfregulation")


def test_matching_form_strips_accents_and_keeps_letters_in_every_script():
    assert norm("Ölander’s café: 消费者") == "olander s cafe 消费者"


def test_an_exact_entry_matches_its_record():
    m = same_paper(entry("Ego depletion: Is the active self a limited resource?"), cr("Ego depletion: Is the active self a limited resource?"))
    assert m is not None and m.kind == "full" and m.ratio == 1.0 and m.d == 0


def test_an_entry_that_leaves_out_the_subtitle_matches_on_the_main_title():
    m = same_paper(entry("Self-efficacy", "Bandura", 1977), cr("Self-efficacy", "Bandura", "Albert", 1977, subtitle="Toward a unifying theory of behavioral change"))
    assert m is not None and m.kind == "main"


def test_two_papers_sharing_a_main_title_with_different_subtitles_do_not_match():
    assert same_paper(entry("Brand love: Antecedents and outcomes", "Batra", 2012), cr("Brand love", "Batra", "R.", 2012, subtitle="Consequences for loyalty")) is None


LONG = "Ego depletion: Is the active self a limited resource?"


def test_a_misspelled_first_author_still_matches():
    assert same_paper(entry(LONG, "Baumiester"), cr(LONG)) is not None


def test_a_name_stored_in_swapped_order_matches():
    record = cr("Consumer trust in online shopping platforms", family="Wei", given="Zhang", year=2015)
    assert same_paper(entry("Consumer trust in online shopping platforms", "Zhang", 2015), record) is not None


def test_a_different_first_author_does_not_match():
    assert same_paper(entry(LONG, "Smith"), cr(LONG)) is None


def test_a_chinese_title_matches_its_record():
    record = cr("消费者信任的形成机制研究", family="王", given="伟", year=2019)
    assert same_paper(entry("消费者信任的形成机制研究", "王", 2019), record) is not None


def test_an_empty_title_never_matches():
    assert same_paper(entry(""), cr("")) is None


def test_a_generic_short_title_needs_the_exact_surname_and_a_near_year():
    assert same_paper(entry("Editorial", "Smith", 2020), cr("Editorial", family="Smith", year=2020)) is not None
    assert same_paper(entry("Editorial", "Smyth", 2020), cr("Editorial", family="Smith", year=2020)) is None
    assert same_paper(entry("Editorial", "Smith", 2015), cr("Editorial", family="Smith", year=2020)) is None


def test_a_record_with_no_authors_needs_a_near_identical_title_and_year():
    record = cr("Annual review of consumer research trends", year=2020, authors=[])
    assert same_paper(entry("Annual review of consumer research trends", year=2020), record) is not None
    assert same_paper(entry("Annual review of consumer research trends", year=2016), record) is None


def test_the_exact_record_outranks_a_more_cited_sibling():
    exact = same_paper(entry("Brand love and loyalty"), cr("Brand love and loyalty", cites=3, doi="10.1000/exact"))
    sibling = same_paper(entry("Brand love and loyalty"), cr("Brand love and loyalties", cites=900, doi="10.1000/sib"))
    assert exact and sibling
    assert best([sibling, exact]).cand.doi == "10.1000/exact"


def test_an_openalex_author_matches_on_the_last_word_of_the_display_name():
    work = {"display_name": "Attention Is All You Need", "publication_year": 2017, "type": "preprint", "authorships": [{"author": {"display_name": "Ashish Vaswani"}}], "doi": "https://doi.org/10.48550/arxiv.1706.03762"}
    assert same_paper(entry("Attention is all you need", "Vaswani", 2017), from_openalex(work)) is not None


def test_a_retracted_crossref_title_matches_without_its_prefix():
    record = from_crossref({"DOI": "10.1000/w", "type": "journal-article", "title": ["RETRACTED: Ileal-lymphoid-nodular hyperplasia"], "author": [{"family": "Wakefield"}], "issued": {"date-parts": [[1998]]}})
    m = same_paper(entry("Ileal-lymphoid-nodular hyperplasia", "Wakefield", 1998), record)
    assert m is not None and m.ratio == 1.0
