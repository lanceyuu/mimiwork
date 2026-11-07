"""Is this record the paper the entry cites? (spec 2026-11-07, step 4)

A false match drives a wrong fix into a researcher's file; a missed match only shows as
"not found" with a link to look it up. So every rule here leans towards no match.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Optional

from .. import scholarly

PUBLISHED = frozenset(
    {
        "journal-article",
        "proceedings-article",
        "book",
        "book-chapter",
        "monograph",
        "edited-book",
        "reference-book",
        "report",
    }
)
BOOKS = frozenset({"book", "monograph", "edited-book", "reference-book"})

_QUOTES = str.maketrans(
    {"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'", "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"'}
)
# Every dash, hyphen and minus with the spaces around it: PDF line-end hyphenation
# ("self-\nregulation") and spaced page ranges ("12 – 15") must compare equal to the way a
# model copies them.
_DASH = re.compile(r"\s*[\-­‐-―−﹘﹣－]\s*")
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")


def loose(text: Any) -> str:
    """The form model output is compared with file text in."""
    t = unicodedata.normalize("NFKC", str(text or "")).casefold().translate(_QUOTES)
    return " ".join(_DASH.sub("", t).split())


# What may follow a DOI that has ended: closing punctuation, then a space, a quote, a
# bracket of markup or the end. Anything else continues it, so a DOI the model cut short
# ("…74.5" of "…74.5.1252") is not found in the text and never stands for the printed one.
_DOI_END = r"""(?=[.,;:)\]]*(?:[\s"'<>“”‘’«»]|$))"""


def find_doi(doi: str, text: str) -> Optional[re.Match[str]]:
    """The printed DOI in `text`, whole, case-insensitively; a PDF line break may sit
    anywhere inside it."""
    body = r"\s*".join(re.escape(ch) for ch in doi)
    return re.search(body + _DOI_END, text, re.I) if doi else None


def norm(text: Any) -> str:
    """The form titles and names are matched in: accents gone, letters and digits of every
    script kept, everything else a space."""
    t = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", str(text or "")).casefold())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in t).split())


def ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0


def words_present(title: Any, text: Any, share: float = 0.9) -> bool:
    words = norm(title).split()
    if not words:
        return False
    body = norm(text)
    have = set(body.split())
    # Scripts written without spaces arrive as one long "word"; a substring test covers them.
    hits = sum(1 for w in words if w in have or (len(w) > 3 and w in body))
    return hits / len(words) >= share


def split_title(title: Any) -> tuple[str, str, bool]:
    """(full, main title, has a subtitle), splitting at the first colon."""
    full = scholarly.clean(title)
    main, colon, _ = full.partition(":")
    return full, (main.strip() if colon else full), bool(colon)


def is_short(title_norm: str) -> bool:
    """A title generic enough ("Editorial", "Reply") that a title match proves nothing."""
    if _CJK.search(title_norm):
        return len(title_norm.replace(" ", "")) <= 6
    return len(title_norm.split()) <= 3


@dataclass
class Candidate:
    source: str  # "crossref" | "agency" (DataCite and other agencies) | "openalex"
    doi: Optional[str]
    title: str
    main: str
    has_subtitle: bool
    authors: list[tuple[str, str]]  # (family, given)
    years: list[int]
    type: str
    cites: int = 0
    link: str = ""
    retraction: dict[str, Any] = field(default_factory=lambda: {"status": "none", "year": None, "notice": None})
    agency: str = ""

    @property
    def published(self) -> bool:
        """Only a published Crossref record may supply a fix: a posted copy (the Vaswani
        case), an OpenAlex or a DataCite record can show a paper exists, nothing more."""
        return self.source == "crossref" and self.type in PUBLISHED


def _years(*dates: Any) -> list[int]:
    out = set()
    for date in dates:
        parts = ((date or {}).get("date-parts") or [[None]])[0] or [None]
        if isinstance(parts[0], int):
            out.add(parts[0])
    return sorted(out)


def from_crossref(record: dict[str, Any]) -> Candidate:
    title, main, has_sub = scholarly.record_title(record)
    doi = scholarly.normalise_doi(record.get("DOI"))
    return Candidate(
        source="crossref",
        doi=doi,
        title=title,
        main=main,
        has_subtitle=has_sub,
        authors=[
            (str(a.get("family") or a.get("name") or ""), str(a.get("given") or ""))
            for a in record.get("author") or []
        ],
        years=_years(record.get("issued"), record.get("published-print"), record.get("published-online")),
        type=str(record.get("type") or ""),
        cites=int(record.get("is-referenced-by-count") or 0),
        link=f"https://doi.org/{doi}" if doi else "",
        retraction=scholarly.retraction(record),
    )


def from_csl(record: dict[str, Any], agency: str) -> Candidate:
    raw = record.get("title")
    title, main, has_sub = split_title(raw[0] if isinstance(raw, list) and raw else raw)
    doi = scholarly.normalise_doi(record.get("DOI"))
    return Candidate(
        source="agency",
        doi=doi,
        title=title,
        main=main,
        has_subtitle=has_sub,
        authors=[(str(a.get("family") or a.get("literal") or ""), str(a.get("given") or "")) for a in record.get("author") or []],
        years=_years(record.get("issued")),
        type=str(record.get("type") or ""),
        link=f"https://doi.org/{doi}" if doi else "",
        retraction={"status": "unknown", "year": None, "notice": None},
        agency=agency,
    )


def from_openalex(work: dict[str, Any]) -> Candidate:
    title, main, has_sub = split_title(work.get("display_name") or work.get("title"))
    doi = scholarly.normalise_doi(work.get("doi"))
    authors = []
    for authorship in work.get("authorships") or []:
        words = str((authorship.get("author") or {}).get("display_name") or "").split()
        if words:
            authors.append((words[-1], " ".join(words[:-1])))
    year = work.get("publication_year")
    return Candidate(
        source="openalex",
        doi=doi,
        title=title,
        main=main,
        has_subtitle=has_sub,
        authors=authors,
        years=[year] if isinstance(year, int) else [],
        type=str(work.get("type") or ""),
        cites=int(work.get("cited_by_count") or 0),
        link=f"https://doi.org/{doi}" if doi else str(work.get("id") or ""),
        retraction={"status": "retracted" if work.get("is_retracted") else "none", "year": None, "notice": None},
    )


@dataclass
class Match:
    cand: Candidate
    kind: str  # "full": whole titles agree; "main": only the part before the subtitle
    ratio: float
    d: Optional[int]  # smallest year distance, None when either side has no year


def title_test(entry_title: Any, cand: Candidate) -> Optional[tuple[str, float, str]]:
    """(kind, ratio, the record title that matched, normalised), or None."""
    full, main, has_sub = split_title(entry_title)
    ef, rf = norm(full), norm(cand.title)
    if not ef or not rf:
        return None
    r = ratio(ef, rf)
    if r >= 0.9:
        return "full", r, rf
    if has_sub and cand.has_subtitle:
        return None  # two different subtitles under one main title are two papers
    em, rm = norm(main), norm(cand.main)
    r = ratio(em, rm)
    return ("main", r, rm) if r >= 0.9 else None


def author_test(surname: Any, cand: Candidate) -> bool:
    s = norm(surname)
    if not s or not cand.authors:
        return False
    if ratio(s, norm(cand.authors[0][0])) >= 0.85:
        return True
    # Names stored in swapped order, or the entry citing a later author first.
    return any(s in norm(family).split() or s in norm(given).split() for family, given in cand.authors)


def exact_surname(surname: Any, cand: Candidate) -> bool:
    s = norm(surname)
    return bool(s) and any(s in norm(family).split() for family, _ in cand.authors)


def year_distance(year: Optional[int], cand: Candidate) -> Optional[int]:
    if year is None or not cand.years:
        return None
    return min(abs(year - y) for y in cand.years)


def title_match(entry: Any, cand: Candidate) -> Optional[Match]:
    """The record a printed DOI leads to: the title alone decides, because some records
    have no authors and some works carry two DOIs."""
    t = title_test(entry.title, cand)
    return Match(cand, t[0], t[1], year_distance(entry.year, cand)) if t else None


def same_paper(entry: Any, cand: Candidate) -> Optional[Match]:
    t = title_test(entry.title, cand)
    if t is None:
        return None
    kind, r, matched = t
    d = year_distance(entry.year, cand)
    near = d is not None and d <= 1
    if cand.authors and norm(entry.surname):
        if not author_test(entry.surname, cand):
            return None
    elif not (r >= 0.95 and near):
        return None
    if is_short(matched) and not (exact_surname(entry.surname, cand) and near):
        return None
    return Match(cand, kind, r, d)


def best(matches: list[Match]) -> Match:
    """How well a record matches always outranks how often it is cited."""
    return max(
        matches,
        key=lambda m: (
            m.kind == "full",
            round(m.ratio, 3),
            m.d is not None and m.d <= 1,
            m.cand.published,
            m.cand.cites,
        ),
    )
