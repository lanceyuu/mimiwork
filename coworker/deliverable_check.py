"""Deliverable self-check — reopen what a tool just wrote and say what's wrong with it.

Deterministic and cheap (no model call). Called by the file-producing tools right after
they save (`write_document`, `write_presentation`, `write_workbook`) and by the engine
for `write_file` text deliverables. Findings ride back on the tool result under
``verification`` so the model fixes them in the SAME turn instead of announcing a
finished deliverable that is empty, unparsable, or still full of placeholders.

Never raises and never blocks: a checker that can't run (optional dependency missing)
simply reports nothing.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

# Placeholder tokens a model leaves behind when it "finishes" a draft it didn't finish.
_PLACEHOLDERS = re.compile(
    r"\[(?:insert|add|your|placeholder|tbd|todo)[^\]]{0,60}\]"
    r"|\blorem ipsum\b"
    r"|<<[^>]{1,60}>>",
    re.IGNORECASE,
)
# Bare markers only count in SHOUTING case — "todo-list app" is prose, "TODO" is a stub.
_MARKERS = re.compile(r"\bTODO\b|\bTBD\b|\bXXX\b")
TEXT_SUFFIXES = {".md", ".txt", ".html", ".htm", ".csv", ".json", ".rst"}
CHECKED_SUFFIXES = TEXT_SUFFIXES | {".docx", ".pptx", ".xlsx"}


def check(path: str | Path) -> dict[str, Any]:
    """Return ``{"ok": bool, "issues": [..]}`` for a freshly written deliverable."""
    target = Path(path)
    issues: list[str] = []
    if not target.is_file():
        return {"ok": False, "issues": ["the file does not exist after writing"]}
    if target.stat().st_size == 0:
        return {"ok": False, "issues": ["the file is empty (0 bytes)"]}
    suffix = target.suffix.lower()
    text: Optional[str] = None
    try:
        if suffix == ".docx":
            text, structural = _docx(target)
        elif suffix == ".pptx":
            text, structural = _pptx(target)
        elif suffix == ".xlsx":
            text, structural = _xlsx(target)
        elif suffix in TEXT_SUFFIXES:
            text = target.read_text(encoding="utf-8", errors="replace")
            structural = [] if text.strip() else ["the file has no text content"]
        else:
            return {"ok": True, "issues": []}  # not a deliverable type we understand
    except _MissingDep:
        return {"ok": True, "issues": []}
    except Exception as exc:  # unparsable → the strongest signal we can give
        return {"ok": False, "issues": [f"the file could not be opened by its reader: {exc}"]}
    issues.extend(structural)
    if text:
        found = sorted(
            {m.group(0).strip() for m in _PLACEHOLDERS.finditer(text)}
            | {m.group(0) for m in _MARKERS.finditer(text)}
        )
        if found:
            shown = ", ".join(f"“{f}”" for f in found[:4])
            more = f" (+{len(found) - 4} more)" if len(found) > 4 else ""
            issues.append(f"placeholder text left in the file: {shown}{more}")
    return {"ok": not issues, "issues": issues}


class _MissingDep(Exception):
    pass


def _need(module: str) -> Any:
    try:
        return __import__(module)
    except ImportError as exc:  # optional [office] extra absent → skip, don't fail
        raise _MissingDep(module) from exc


def _docx(target: Path) -> tuple[str, list[str]]:
    docx = _need("docx")
    document = docx.Document(str(target))
    paragraphs = [p for p in document.paragraphs if p.text.strip()]
    headings = [p for p in paragraphs if (p.style.name or "").lower().startswith(("heading", "title"))]
    tables = list(document.tables)
    text = "\n".join(p.text for p in paragraphs)
    for table in tables:
        for row in table.rows:
            text += "\n" + " ".join(cell.text for cell in row.cells)
    issues: list[str] = []
    if not paragraphs and not tables:
        issues.append("the document has no text")
    elif not headings and len(paragraphs) < 2:
        issues.append("the document is a single paragraph with no headings — is it complete?")
    return text, issues


def _pptx(target: Path) -> tuple[str, list[str]]:
    pptx = _need("pptx")
    deck = pptx.Presentation(str(target))
    slides = list(deck.slides)
    chunks: list[str] = []
    for slide in slides:
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                chunks.append(shape.text_frame.text)
    issues: list[str] = []
    if not slides:
        issues.append("the presentation has no slides")
    elif not chunks:
        issues.append("the slides contain no text")
    return "\n".join(chunks), issues


def _xlsx(target: Path) -> tuple[str, list[str]]:
    openpyxl = _need("openpyxl")
    book = openpyxl.load_workbook(str(target), read_only=True, data_only=False)
    chunks: list[str] = []
    filled = 0
    for ws in book.worksheets:
        for row in ws.iter_rows(values_only=True):
            for value in row:
                if value is None or str(value).strip() == "":
                    continue
                filled += 1
                if isinstance(value, str):
                    chunks.append(value)
    book.close()
    issues = ["the workbook has no filled cells"] if filled == 0 else []
    return "\n".join(chunks), issues


def attach(result: dict[str, Any], target: str | Path) -> dict[str, Any]:
    """Add ``verification`` to a write-tool result when the check finds issues."""
    report = check(target)
    if not report["ok"]:
        result["verification"] = {
            "ok": False,
            "issues": report["issues"],
            "instruction": "Fix these before telling the user the deliverable is ready.",
        }
    return result
