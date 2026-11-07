"""Finding a reference list and having the model split it into entries (spec 2026-11-07,
steps 1 and 2).

The model only locates entries and reads their parts. Every part it returns is checked
against the file's own text and dropped when it is not there, so a title or DOI the model
filled in from memory never drives a verdict.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .. import scholarly
from ..code_explain import _loads
from .matching import find_doi, loose, words_present

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

HEADINGS = frozenset(
    h.casefold()
    for h in (
        "References", "Reference", "Reference list", "Bibliography", "Works cited",
        "Literature cited", "Sources", "Literatur", "Literaturverzeichnis", "Références",
        "Bibliographie", "Referanser", "Litteratur", "Litteraturliste", "Kilder",
        "Referencias", "Bibliografía", "Bibliografia", "Referências", "Literatuur",
        "参考文献", "참고문헌", "Список литературы", "المراجع",
    )
)
_NUMBERED = re.compile(r"^(?:\d+(?:\.\d+)*|[ivxlcdm]+)[.)]?\s+", re.I)

WORD_BATCH = 60
PDF_BATCH = 150  # PDF "paragraphs" are lines; 60 lines hold only about 15 entries
MAX_CALLS = 8
MAX_ENTRIES = 300
WORD_CAP = 400
WORD_TAIL = 300
PDF_CAP = 60_000

# Fields that build a bibliography. In-text citation fields (ZOTERO_ITEM, EN.CITE) are not
# the list, so they never mark it as managed.
_FIELD_TOOLS = (
    ("MENDELEY", "Mendeley"),
    ("ZOTERO_BIBL", "Zotero"),
    ("EN.REFLIST", "EndNote"),
    ("CITAVI", "Citavi"),
    ("PAPERPILE", "Paperpile"),
    ("RW.", "RefWorks"),
    ("BIBLIOGRAPHY", "Word's bibliography"),
)
_IN_TEXT = ("ZOTERO_ITEM", "EN.CITE", "CSL_CITATION")


def is_heading(text: str) -> bool:
    t = text.strip().rstrip(":：").strip()
    t = _NUMBERED.sub("", t, count=1).strip()
    return t.casefold() in HEADINGS


@dataclass
class Para:
    text: str  # reading text: tabs and breaks as spaces
    index: Optional[int] = None  # read_document's block index; None inside a content control
    obj: Any = None  # the python-docx Paragraph, for direct body paragraphs


@dataclass
class Listing:
    kind: str  # "docx" | "pdf"
    paras: list[Para]
    heading_found: bool = True
    managed: Optional[str] = None
    cut: bool = False
    scan: bool = False


def reading_text(p_el: Any) -> str:
    out = []
    for el in p_el.iter():
        if el.tag == W + "t":
            out.append(el.text or "")
        elif el.tag in (W + "tab", W + "br", W + "cr"):
            out.append(" ")
    return "".join(out)


def _field_tool(p_el: Any) -> Optional[str]:
    for el in p_el.iter(W + "instrText", W + "fldSimple"):
        instr = (el.text or "") if el.tag == W + "instrText" else (el.get(W + "instr") or "")
        upper = instr.upper()
        if any(key in upper for key in _IN_TEXT):
            continue
        for key, name in _FIELD_TOOLS:
            if key in upper:
                return name
        if "ADDIN" in upper:
            return "a citation tool"
    return None


def _sdt_tool(sdt: Any) -> Optional[str]:
    pr = sdt.find(W + "sdtPr")
    if pr is None:
        return None
    gallery = pr.find(f"{W}docPartObj/{W}docPartGallery")
    if gallery is not None and (gallery.get(W + "val") or "").lower() == "bibliographies":
        return "Word's bibliography"
    names = " ".join((el.get(W + "val") or "") for el in pr.iter(W + "tag", W + "alias")).lower()
    for key, name in (("mendeley", "Mendeley"), ("zotero", "Zotero"), ("citavi", "Citavi"), ("endnote", "EndNote")):
        if key in names:
            return name
    return None


def load_docx(path: Path) -> Listing:
    import docx

    from ..tools.office.docx_tools import _indexed_blocks

    document = docx.Document(str(path))
    index_of = {p._element: (i, p) for i, p in enumerate(_indexed_blocks(document)) if p is not None}
    items: list[tuple[Para, Optional[str]]] = []
    for child in document.element.body.iterchildren():
        if child.tag == W + "p":
            i, p = index_of.get(child, (None, None))
            items.append((Para(reading_text(child), i, p), _field_tool(child)))
        elif child.tag == W + "sdt":
            # _indexed_blocks skips content controls, so these paragraphs can be read and
            # checked but never written: they carry no index.
            holder = _sdt_tool(child)
            for p_el in child.iter(W + "p"):
                items.append((Para(reading_text(p_el)), holder or _field_tool(p_el)))
    heads = [k for k, (para, _) in enumerate(items) if is_heading(para.text)]
    region = items[heads[-1] + 1 : heads[-1] + 1 + WORD_CAP] if heads else items[-WORD_TAIL:]
    region = [(p, tool) for p, tool in region if p.text.strip()]
    return Listing(
        "docx",
        [p for p, _ in region],
        heading_found=bool(heads),
        managed=next((tool for _, tool in region if tool), None),
    )


def load_pdf(path: Path) -> Listing:
    import pypdf

    reader = pypdf.PdfReader(str(path))
    if getattr(reader, "is_encrypted", False):
        reader.decrypt("")  # "protected but not secret"; a real password raises
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    if not any(text.strip() for text in pages):
        return Listing("pdf", [], scan=True)
    lines = [
        (pno, lno, line.strip())
        for pno, text in enumerate(pages)
        for lno, line in enumerate(l for l in text.splitlines() if l.strip())
    ]
    hits = [k for k, (_, _, text) in enumerate(lines) if is_heading(text)]
    found = bool(hits)
    if hits:
        j = len(hits) - 1
        # A heading at the top of the next page is a running head: step back to the
        # page where the list really starts.
        while j > 0:
            (pa, _, _), (pb, lb, _) = lines[hits[j - 1]], lines[hits[j]]
            if pb == pa + 1 and lb < 3:
                j -= 1
            else:
                break
        start = hits[j] + 1
        heads = {k for k in hits[j:]}
    else:
        first_page = (len(pages) * 2) // 3
        start = next((k for k, line in enumerate(lines) if line[0] >= first_page), 0)
        heads = set()
    region: list[Para] = []
    size, cut = 0, False
    for k in range(start, len(lines)):
        if k in heads:
            continue
        text = lines[k][2]
        if size + len(text) > PDF_CAP:
            cut = True
            break
        region.append(Para(text))
        size += len(text) + 1
    return Listing("pdf", region, heading_found=found, cut=cut)


SYSTEM = """You split a reference list into its entries. You get numbered paragraphs of a \
document, written [n] text. The list may go on past the last paragraph shown, and it may \
end before it: tables, figures and appendices often follow a reference list.

Return ONLY this JSON, nothing else:
{"style": "apa", "entries": [{"first": 3, "last": 3, "text": "...", "title": "...", \
"surname": "...", "year": "2017a", "doi": null}]}

Rules:
- One item per reference, in the order printed. first and last are the numbers of the \
paragraphs the entry starts and ends in.
- text: the entry exactly as printed, without the [n] numbers.
- title: the cited work's own title (the article or chapter, not the journal or book it \
appeared in). surname: the first author's family name. year: as printed, or "n.d.". \
doi: only when the entry prints one.
- Copy what is printed, never correct it: do not fix spelling, fill in missing parts or \
add a DOI that is not printed. Use null for anything the entry does not print.
- style: the list's citation style: apa, chicago-author-date, harvard-cite-them-right, \
modern-language-association, american-sociological-association, ieee, \
american-medical-association, nature, or other.
- Skip anything that is not a reference: headings, notes, captions, page numbers."""

NO_HEADING = (
    "\n\nThis text may hold no reference list at all. If it holds none, return "
    '{"style": "other", "entries": []}.'
)


class ReadFailed(Exception):
    """No reply from the model could be read at all."""


@dataclass
class Entry:
    id: str
    first: int
    last: int
    text: str  # as printed (the model's copy, confirmed against the file)
    title: Optional[str]
    surname: Optional[str]
    year: Optional[int]
    doi: Optional[str]
    has_doi_pattern: bool


@dataclass
class Reading:
    entries: list[Entry] = field(default_factory=list)
    unread: int = 0  # entries whose text the file does not contain
    not_checked: int = 0  # paragraphs past the call cap, plus entries past the entry cap
    style: str = "other"


def _items(data: Any, lo: int, hi: int) -> list[dict[str, Any]]:
    raw = data.get("entries") if isinstance(data, dict) else None
    out = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        first, last = item.get("first"), item.get("last")
        if isinstance(first, int) and isinstance(last, int) and lo <= first <= last < hi:
            out.append(item)
    return sorted(out, key=lambda item: item["first"])


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _entry(n: int, item: dict[str, Any], listing: Listing) -> Optional[Entry]:
    printed = _text(item.get("text"))
    slack = 1 if listing.kind == "pdf" else 0  # a model's line numbers in a PDF can be one off
    lo, hi = max(0, item["first"] - slack), item["last"] + 1 + slack
    within = loose(" ".join(p.text for p in listing.paras[lo:hi]))
    if not loose(printed) or loose(printed) not in within:
        return None
    doi = scholarly.normalise_doi(item.get("doi"))
    if doi and not find_doi(doi, printed):
        doi = None
    raw = item.get("year")
    raw_year = str(raw) if isinstance(raw, int) else _text(raw)  # models often send 1998, not "1998"
    year_match = re.fullmatch(r"(\d{4})[a-z]?", raw_year)
    year = int(year_match.group(1)) if year_match and raw_year in printed else None
    surname = _text(item.get("surname"))
    if not loose(surname) or loose(surname) not in loose(printed):
        surname = ""
    title = _text(item.get("title"))
    if not words_present(title, printed):
        title = ""
    return Entry(
        id=f"e{n}",
        first=item["first"],
        last=item["last"],
        text=printed,
        title=title or None,
        surname=surname or None,
        year=year,
        doi=doi,
        has_doi_pattern=bool(re.search(r"10\.\d{4,9}/", printed)),
    )


def read_entries(listing: Listing, complete: Callable[[str, str], str]) -> Reading:
    paras = listing.paras
    n = len(paras)
    size = WORD_BATCH if listing.kind == "docx" else PDF_BATCH
    system = SYSTEM + ("" if listing.heading_found else NO_HEADING)
    out = Reading()
    kept: list[dict[str, Any]] = []
    start = calls = 0
    parsed = False
    while start < n and calls < MAX_CALLS:
        end = min(start + size, n)
        raw = complete(system, "\n".join(f"[{k}] {paras[k].text}" for k in range(start, end)))
        calls += 1
        data = _loads(raw or "")
        if isinstance(data, dict):
            parsed = True
            if out.style == "other" and isinstance(data.get("style"), str):
                out.style = data["style"].strip().lower() or "other"
        items = _items(data, start, end)
        if not items:
            start = end
            continue
        if end < n:
            # The last entry may be cut off by the batch's end: read it again, whole, in
            # the next batch. When it starts the batch, keeping it is the only way forward.
            tail = items[-1]
            if tail["first"] == start:
                start = max(tail["last"] + 1, start + 1)
            else:
                items = items[:-1]
                start = tail["first"]
        else:
            start = end
        for item in items:
            if kept and item["first"] <= kept[-1]["last"]:
                continue
            kept.append(item)
    if calls and not parsed:
        raise ReadFailed("the model's replies could not be read")
    out.not_checked = max(0, n - start) if start < n else 0
    for item in kept:
        if len(out.entries) >= MAX_ENTRIES:
            out.not_checked += 1
            continue
        entry = _entry(len(out.entries) + out.unread + 1, item, listing)
        if entry is None:
            out.unread += 1
        else:
            out.entries.append(entry)
    return out
