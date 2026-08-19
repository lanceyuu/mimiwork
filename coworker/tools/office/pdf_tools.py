"""PDF reading — the format most real work arrives in.

Reports, papers, statements, invoices, and board packs are PDFs. Without this the agent can
only see a PDF the user manually attaches to a message; a PDF sitting in the workspace is
opaque to it.

pypdf is already a core dependency (``pdf_support.py`` uses it for attachments), so text
extraction always works. Table extraction is the optional part.

The scanned-PDF case is handled explicitly rather than left to silence. A page image with no
text layer extracts as an empty string, and an empty page looks exactly like a blank one — so
the model concludes the document is empty and answers from imagination. This tool detects that
and says so.
"""

from __future__ import annotations

from typing import Any

from ._common import MAX_TEXT_CHARS, clip, decorate, guard, require
from .paths import context_roots, display_path, resolve_read

_DEFAULT_PAGES = 10
_MAX_PAGES = 50
_MAX_PAGE_CHARS = 20_000

_READ_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_pdf",
        "description": (
            "Read a PDF's text, page by page. Long documents are windowed: pass start_page to "
            "continue where the previous read stopped. Set tables=true to also extract tables "
            "as structured rows — do that when you need numbers out of a report rather than "
            "prose. If the PDF is scanned (no text layer) this says so explicitly instead of "
            "returning empty pages. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The .pdf file to read."},
                "start_page": {
                    "type": "integer",
                    "description": "First page to read, 1-based (default 1).",
                },
                "max_pages": {
                    "type": "integer",
                    "description": f"How many pages (default {_DEFAULT_PAGES}, max {_MAX_PAGES}).",
                },
                "tables": {
                    "type": "boolean",
                    "description": "Also extract tables as rows (default false).",
                },
            },
            "required": ["path"],
        },
    },
}


def _page_tables(target: Any, first: int, last: int) -> list[dict[str, Any]]:
    """Extract tables for pages [first, last] (1-based, inclusive) via pdfplumber."""
    pdfplumber = require("pdfplumber", "pdfplumber", extra="office")
    out: list[dict[str, Any]] = []
    with pdfplumber.open(str(target)) as document:
        for number in range(first, min(last, len(document.pages)) + 1):
            page = document.pages[number - 1]
            for index, table in enumerate(page.extract_tables() or []):
                rows = [
                    [clip((cell or "").strip()) if isinstance(cell, str) else cell for cell in row]
                    for row in table
                ]
                if rows:
                    out.append({"page": number, "index": index, "rows": rows})
    return out


def pdf_tools(context: Any) -> list:
    roots = context_roots(context)

    @guard
    def read_pdf(
        path: str,
        start_page: int = 1,
        max_pages: int = _DEFAULT_PAGES,
        tables: bool = False,
    ) -> dict[str, Any]:
        pypdf = require("pypdf", "pypdf", extra="office")
        target = resolve_read(path, roots)
        if not target.is_file():
            raise FileNotFoundError(display_path(target, roots))

        try:
            reader = pypdf.PdfReader(str(target))
        except Exception as exc:  # pypdf raises a family of parse errors
            raise ValueError(f"could not read the PDF: {exc}") from exc

        if getattr(reader, "is_encrypted", False):
            # An empty-password decrypt covers the common "protected but not secret" case.
            try:
                reader.decrypt("")
            except Exception:
                return {
                    "error": (
                        "this PDF is password-protected; ask the user for the password or an "
                        "unprotected copy"
                    )
                }

        total = len(reader.pages)
        begin = start_page if isinstance(start_page, int) and start_page > 0 else 1
        count = max_pages if isinstance(max_pages, int) and max_pages > 0 else _DEFAULT_PAGES
        count = min(count, _MAX_PAGES)
        end = min(begin + count - 1, total)

        pages: list[dict[str, Any]] = []
        empty = 0
        for number in range(begin, end + 1):
            try:
                text = (reader.pages[number - 1].extract_text() or "").strip()
            except Exception:
                text = ""
            if not text:
                empty += 1
            pages.append({"page": number, "text": clip(text, _MAX_PAGE_CHARS)})

        result: dict[str, Any] = {
            "path": display_path(target, roots),
            "total_pages": total,
            "pages": pages,
        }

        meta = getattr(reader, "metadata", None)
        if meta:
            title = getattr(meta, "title", None)
            if title:
                result["title"] = clip(str(title))

        if pages and empty == len(pages):
            # Load-bearing: silent empty text is indistinguishable from a blank document, and
            # the model will confidently summarise a PDF it never actually read.
            result["warning"] = (
                "no text layer found on these pages — this is almost certainly a scanned "
                "document. Do NOT summarise it as if it were empty. Ask the user for a "
                "text-based copy, or run OCR (e.g. `ocrmypdf in.pdf out.pdf`) and read the result."
            )
            result["scanned"] = True
        elif empty:
            result["note_empty_pages"] = f"{empty} of these pages had no extractable text"

        if tables:
            found = _page_tables(target, begin, end)
            result["tables"] = found
            if not found:
                result["tables_note"] = (
                    "no ruled tables detected on these pages; the numbers may be laid out as "
                    "plain text — read the page text instead"
                )

        if end < total:
            result["note"] = (
                f"showing pages {begin}-{end} of {total}; call again with "
                f"start_page={end + 1} to continue"
            )
        return result

    return [decorate(read_pdf, name="read_pdf", schema=_READ_SCHEMA)]
