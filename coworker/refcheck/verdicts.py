"""What each entry's lookups mean, and the fixes code can make from them (spec
2026-11-07, steps 3, 5 and 6).

No fix text comes from the model: each fix is one exact span of the entry's own text,
replaced by a value from a published Crossref record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Callable, Optional

from .. import scholarly
from ..secrets import SecretStore
from ..tools.papers import STYLES
from .matching import (
    BOOKS,
    Match,
    best,
    find_doi,
    from_crossref,
    from_csl,
    from_openalex,
    loose,
    norm,
    printed_match,
    ratio,
    same_name,
    same_paper,
    title_match,
    words_present,
)

GROUP_ORDER = ("retracted", "fix", "not_found", "couldnt", "verified")
_GROUPS = {
    "retracted": "retracted",
    "partly_retracted": "retracted",
    "doi_other_paper": "fix",
    "doi_not_found": "fix",
    "doi_unfixable": "fix",
    "doi_missing": "fix",
    "surname_differs": "fix",
    "title_differs": "fix",
    "edition": "fix",
    "not_found": "not_found",
    "lookup_failed": "couldnt",
    "no_title": "couldnt",
    "openalex_limit": "couldnt",
}
# Every other code (year_differs, year_other_work, concern, outside_crossref, found_openalex, found_copy,
# retracted_maybe, chapter_doi) is a note on a verified entry.

REASONS = {
    "replace_doi": "Corrected the DOI to match the Crossref record.",
    "add_doi": "Added the DOI from the Crossref record.",
    "replace_surname": "Corrected the first author's surname to match the Crossref record.",
}


@dataclass
class Lookups:
    crossref_work: Callable[[str], dict[str, Any]]
    crossref_search: Callable[[str], dict[str, Any]]
    csl_record: Callable[[str], dict[str, Any]]
    openalex_title: Callable[[str], dict[str, Any]]
    formatted: Callable[[str, str], dict[str, Any]]


def live_lookups(secrets: Optional[SecretStore] = None) -> Lookups:
    return Lookups(
        crossref_work=scholarly.crossref_work,
        crossref_search=scholarly.crossref_search,
        csl_record=scholarly.csl_record,
        openalex_title=lambda title: scholarly.openalex_title(title, secrets=secrets),
        formatted=scholarly.formatted,
    )


@dataclass
class Outcome:
    codes: list[dict[str, Any]]
    match: Optional[Match] = None
    wrong: Optional[dict[str, Any]] = None  # the printed DOI is wrong: {"why", "title"}
    suggestion: Optional[str] = None  # the record's formatted reference, for Copy


def code(name: str, **params: Any) -> dict[str, Any]:
    return {"code": name, "params": params}


def group_of(codes: list[dict[str, Any]]) -> str:
    present = {_GROUPS.get(c["code"], "verified") for c in codes}
    return next(g for g in GROUP_ORDER if g in present or g == "verified")


def look_up(entry: Any, lk: Lookups, style: str = "apa") -> Outcome:
    if not norm(entry.title):
        return Outcome([code("no_title")])
    match: Optional[Match] = None
    wrong: Optional[dict[str, Any]] = None
    book_doi = False
    if entry.doi:
        work = lk.crossref_work(entry.doi)
        if work.get("ok"):
            cand = from_crossref(work["record"])
            match = title_match(entry, cand) or printed_match(entry, cand)
            if match is None:
                # A chapter cited with its book's DOI is a defensible reference.
                if cand.type in BOOKS and words_present(cand.title, entry.text):
                    book_doi = True
                else:
                    wrong = {"why": "other", "title": cand.title}
        elif work.get("error") == "outside_crossref":
            record = lk.csl_record(entry.doi)
            if not record.get("ok"):
                return Outcome([code("lookup_failed")])
            cand = from_csl(record["record"], str(work.get("agency") or ""))
            # As for a Crossref DOI: DataCite records often lack authors or carry a later
            # version's year, and the printed DOI already ties the record to the entry.
            match = title_match(entry, cand)
            if match is None:
                wrong = {"why": "other", "title": cand.title}
        elif work.get("error") == "no_such_doi":
            wrong = {"why": "missing", "title": None}
        else:
            return Outcome([code("lookup_failed")])
    if match is None:
        found = lk.crossref_search(entry.text)
        if not found.get("ok"):
            return Outcome([code("lookup_failed")])
        hits = [m for m in (same_paper(entry, from_crossref(r)) for r in found["items"]) if m]
        match = best(hits) if hits else None
    if match is None:
        found = lk.openalex_title(entry.title)
        if not found.get("ok"):
            limit = found.get("error") == "openalex_limit"
            return Outcome([code("openalex_limit" if limit else "lookup_failed")])
        hits = [m for m in (same_paper(entry, from_openalex(w)) for w in found["results"]) if m]
        match = best(hits) if hits else None
    if match is None:
        return Outcome([code("not_found", title=wrong["title"] if wrong else None)])
    codes = _codes(entry, match, wrong, book_doi)
    return Outcome(codes, match, wrong, _suggestion(match, codes, lk, style))


def _codes(entry: Any, m: Match, wrong: Optional[dict[str, Any]], book_doi: bool) -> list[dict[str, Any]]:
    c = m.cand
    out: list[dict[str, Any]] = []
    fixable = c.published and bool(c.doi)
    status = c.retraction.get("status")
    if c.source == "openalex" and status == "retracted":
        # A false red Retracted is the worst mistake the panel can make, so a looser
        # OpenAlex match only earns a note.
        first = norm(c.authors[0][0]) if c.authors else ""
        if entry.surname and norm(entry.surname) == first:
            out.append(code("retracted", year=None, notice=None, via="openalex"))
        else:
            out.append(code("retracted_maybe"))
    elif status in ("retracted", "partly_retracted"):
        out.append(code(status, year=c.retraction.get("year"), notice=c.retraction.get("notice"), via="crossref"))
    elif status == "concern":
        out.append(code("concern", year=c.retraction.get("year")))
    if c.source == "agency":
        out.append(code("outside_crossref", agency=c.agency))
    elif c.source == "openalex":
        out.append(code("found_openalex"))
    elif not c.published:
        out.append(code("found_copy"))
    if wrong:
        if fixable:
            kind = "doi_other_paper" if wrong["why"] == "other" else "doi_not_found"
            out.append(code(kind, title=wrong["title"], doi=c.doi))
        else:
            out.append(code("doi_unfixable", title=wrong["title"]))
    if book_doi and c.doi and c.doi != entry.doi:
        out.append(code("chapter_doi", doi=c.doi))
    if not fixable:
        return out
    if entry.surname and c.authors:
        family = c.authors[0][0]
        s = norm(entry.surname)
        r = ratio(s, norm(family))
        reordered = any(s in norm(f).split() or s in norm(g).split() for f, g in c.authors)
        if 0.85 <= r < 1 and not reordered and not same_name(entry.surname, family):
            out.append(code("surname_differs", surname=family))
    if m.kind == "full" and m.ratio < 0.98:
        out.append(code("title_differs", title=c.title))
    if m.d is not None and m.d > 1:
        if c.type not in BOOKS and c.container and loose(c.container) not in loose(entry.text):
            # A book that only a review of it lists (Bandura 1997, reviewed in a journal in
            # 1999): the record is another work under the same title, so its year proves
            # nothing. Rejecting it would make a real book Not found; a note is safe.
            out.append(code("year_other_work", years=c.years, container=c.container))
        else:
            out.append(code("edition", years=c.years, book=c.type in BOOKS))
    elif m.d == 1:
        out.append(code("year_differs", years=c.years))
    return out


def _suggestion(m: Match, codes: list[dict[str, Any]], lk: Lookups, style: str) -> Optional[str]:
    wanted = any(
        x["code"] == "title_differs" or (x["code"] == "edition" and not x["params"].get("book"))
        for x in codes
    )
    if not wanted or not m.cand.doi:
        return None
    reference = lk.formatted(m.cand.doi, style if style in STYLES else "apa")
    return reference["text"] if reference.get("ok") else m.cand.title


def mark_missing_dois(entries: list[Any], outcomes: list[Outcome]) -> None:
    """A missing DOI is a problem only in a list where most entries print one."""
    matched = [(e, o) for e, o in zip(entries, outcomes) if o.match]
    if not matched or sum(1 for e, _ in matched if e.doi) * 2 < len(matched):
        return
    for e, o in matched:
        c = o.match.cand
        other_work = any(x["code"] == "year_other_work" for x in o.codes)
        if not e.doi and not e.has_doi_pattern and not o.wrong and not other_work and c.published and c.doi:
            o.codes.append(code("doi_missing", doi=c.doi))


def doi_form(entries: list[Any]) -> str:
    url = sum(1 for e in entries if "doi.org/" in e.text.lower())
    bare = sum(1 for e in entries if re.search(r"\bdoi:\s*10\.", e.text, re.I))
    return "doi:" if bare > url else "https://doi.org/"


def _fix(entry: Any, kind: str, start: int, end: int, new: str, text: str) -> dict[str, Any]:
    return {
        "id": f"{entry.id}.{kind}",
        "kind": kind,
        "start": start,
        "end": end,
        "new": new,
        "after": text[:start] + new + text[end:],
        "writable": False,
        "ticked": False,
    }


def make_fixes(entry: Any, outcome: Outcome, text: str, form: str) -> list[dict[str, Any]]:
    """Spans in `text` (the paragraph's own text when it can be written, else the entry as
    printed). A fix with no exact span to replace is left as a note only."""
    if outcome.match is None:
        return []
    params = {c["code"]: c["params"] for c in outcome.codes}
    cand = outcome.match.cand
    fixes: list[dict[str, Any]] = []
    if entry.doi and ("doi_other_paper" in params or "doi_not_found" in params):
        # Matched in the original text: offsets taken from text.lower() drift wherever
        # lowercasing changes a character's length (Turkish İ), and the fix would land
        # in the wrong place.
        found = find_doi(entry.doi, text)
        if found:
            fixes.append(_fix(entry, "replace_doi", found.start(), found.end(), cand.doi, text))
    if "doi_missing" in params:
        end = len(text.rstrip())
        fixes.append(_fix(entry, "add_doi", end, len(text), f" {form}{cand.doi}", text))
    if entry.surname and "surname_differs" in params:
        found = re.search(rf"(?<!\w){re.escape(entry.surname)}(?!\w)", text, re.I)
        if found:
            family = params["surname_differs"]["surname"]
            old = found.group(0)
            new = _recase(family, old)
            fixes.append(_fix(entry, "replace_surname", found.start(), found.end(), new, text))
    return sorted(fixes, key=lambda f: f["start"])


def _recase(family: str, printed: str) -> str:
    """The record's family name in the list's casing. A name stored in capitals takes the
    printed name's casing letter by letter, since .title() makes "McDonald" "Mcdonald" and
    "de la Cruz" "De La Cruz"; a letter the printed name lacks is lower case, or upper
    case where a word starts."""
    if printed.isupper() and len(printed) > 1:
        return family.upper()
    if not family.isupper():
        return family
    if len(printed.lower()) != len(printed) or len(family.lower()) != len(family):
        return family.title()  # a letter that lowercases to two (Turkish İ) breaks the alignment
    out = list(family.lower())
    for k in range(len(out)):
        if k == 0 or not out[k - 1].isalpha():
            out[k] = out[k].upper()
    for a, b, size in SequenceMatcher(None, printed.lower(), family.lower(), autojunk=False).get_matching_blocks():
        out[b : b + size] = printed[a : a + size]
    return "".join(out)


def apply_spans(text: str, fixes: list[dict[str, Any]]) -> Optional[str]:
    """All fixes applied right to left; None when two spans overlap."""
    out = text
    limit = len(text)
    for fix in sorted(fixes, key=lambda f: f["start"], reverse=True):
        if fix["end"] > limit:
            return None
        out = out[: fix["start"]] + fix["new"] + out[fix["end"] :]
        limit = fix["start"]
    return out


def describe(name: str, params: Optional[dict[str, Any]] = None) -> str:
    """The English sentence for a code, for the chat tool; the panel has a translated table."""
    p = params or {}
    years = ", ".join(str(y) for y in p.get("years") or [])
    when = f" in {p['year']}" if p.get("year") else ""
    return {
        "retracted": "Retracted (OpenAlex)." if p.get("via") == "openalex" else f"Retracted{when}.",
        "partly_retracted": f"Partly retracted{when}.",
        "doi_other_paper": f"The DOI leads to a different paper: {p.get('title')}. The right DOI is {p.get('doi')}.",
        "doi_not_found": f"The DOI does not exist. The right DOI is {p.get('doi')}.",
        "doi_unfixable": "The DOI is wrong, and no published record was found to take the right one from.",
        "doi_missing": f"No DOI. The Crossref record has one: {p.get('doi')}.",
        "surname_differs": f"The first author is spelled {p.get('surname')} in the record.",
        "title_differs": f"The title differs from the record: {p.get('title')}.",
        "year_other_work": (
            f"A record with this title and author is from {years} in {p.get('container')}, "
            "perhaps a review or another edition; the year was not compared."
        ),
        "edition": f"The record's year is {years}" + (": possibly another edition." if p.get("book") else "."),
        "year_differs": f"The record's year is {years}, often a preprint or online-first year.",
        "concern": f"The journal published an expression of concern{when}.",
        "outside_crossref": f"Found on {p.get('agency') or 'another registry'}.",
        "found_openalex": "Found on OpenAlex.",
        "found_copy": "Found as a preprint or posted version; details not compared with a published record.",
        "retracted_maybe": "OpenAlex lists a retracted paper with this title.",
        "chapter_doi": f"The DOI is the book's. The chapter has its own: {p.get('doi')}.",
        "not_found": "Not found in Crossref or OpenAlex. Books, reports and work in some languages are often not listed there.",
        "lookup_failed": "The lookup failed. Check again later.",
        "no_title": "No title to look up.",
        "openalex_limit": "OpenAlex's free daily limit was reached before this entry.",
    }.get(name, name)
