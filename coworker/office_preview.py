"""Reading-quality previews of Word and PowerPoint files, and Word comments.

The GUI cannot render Office binaries itself, and until 2026-09-02 a .docx Mimi had
just written opened in Word or not at all. python-docx and python-pptx are already
in the sidecar for writing them, so they read them back too: headings, paragraphs,
lists, tables, pictures — the reading order, not the page layout. Every body
paragraph carries its index (``data-p``) and every slide its number
(``data-slide``), so a click in the preview can say exactly where a comment goes —
to Mimi as "paragraph 12, starting …", or into the file as a real Word comment.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path
from typing import Any

# Pictures are inlined as data URLs; past this much the preview would choke the
# JSON channel, so the remaining pictures become a placeholder.
MAX_INLINE_IMAGE_BYTES = 12 * 1024 * 1024


def _esc(text: str) -> str:
    return html.escape(text or "", quote=False)


class _Images:
    def __init__(self) -> None:
        self.used = 0

    def tag(self, blob: bytes, content_type: str, alt: str = "") -> str:
        if not blob:
            return ""
        if self.used + len(blob) > MAX_INLINE_IMAGE_BYTES:
            return '<span class="doc-img-skipped">[picture not shown — too large for the preview]</span>'
        self.used += len(blob)
        data = base64.b64encode(blob).decode("ascii")
        return f'<img src="data:{content_type or "image/png"};base64,{data}" alt="{_esc(alt)}">'


# -- Word ---------------------------------------------------------------------------


def _run_html(run: Any, doc: Any, images: _Images) -> str:
    from docx.oxml.ns import qn

    parts: list[str] = []
    for blip in run._r.iter(qn("a:blip")):
        rid = blip.get(qn("r:embed"))
        part = doc.part.related_parts.get(rid) if rid else None
        if part is not None:
            parts.append(images.tag(part.blob, getattr(part, "content_type", "")))
    text = _esc(run.text)
    if text:
        if run.bold:
            text = f"<b>{text}</b>"
        if run.italic:
            text = f"<i>{text}</i>"
        if run.underline:
            text = f"<u>{text}</u>"
        parts.append(text)
    return "".join(parts)


def _paragraph_html(p: Any, doc: Any, images: _Images, index: int | None) -> tuple[str, str]:
    """(kind, html) — kind is 'h', 'li' or 'p', so consecutive list items can be grouped."""
    style = (p.style.name if p.style is not None else "") or ""
    inner = "".join(_run_html(r, doc, images) for r in p.runs) or _esc(p.text)
    attr = f' data-p="{index}"' if index is not None else ""
    if style.startswith("Heading"):
        level = "".join(ch for ch in style if ch.isdigit()) or "1"
        n = min(4, max(1, int(level)))
        return "h", f"<h{n}{attr}>{inner}</h{n}>"
    if style == "Title":
        return "h", f"<h1{attr}>{inner}</h1>"
    numbered = p._p.pPr is not None and p._p.pPr.numPr is not None
    if numbered or "List" in style:
        return "li", f"<li{attr}>{inner}</li>"
    if not inner.strip():
        return "p", ""
    return "p", f"<p{attr}>{inner}</p>"


def _table_html(table: Any, doc: Any, images: _Images) -> str:
    rows: list[str] = []
    for r, row in enumerate(table.rows):
        cells: list[str] = []
        for cell in row.cells:
            # Cell text stays inline (one line per paragraph): a <p> per cell paragraph
            # made every table twice as tall as Word shows it.
            lines = [
                "".join(_run_html(run, doc, images) for run in p.runs) or _esc(p.text)
                for p in cell.paragraphs
            ]
            inner = "<br>".join(line for line in lines if line.strip()) or _esc(cell.text)
            tag = "th" if r == 0 else "td"
            cells.append(f"<{tag}>{inner}</{tag}>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "<table>" + "".join(rows) + "</table>"


def docx_to_html(path: str | Path) -> dict[str, Any]:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(str(path))
    images = _Images()
    out: list[str] = []
    in_list = False
    index = 0
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            kind, h = _paragraph_html(Paragraph(child, doc), doc, images, index)
            index += 1
        elif child.tag == qn("w:tbl"):
            kind, h = "p", _table_html(Table(child, doc), doc, images)
        else:
            continue
        if kind == "li" and not in_list:
            out.append("<ul>")
            in_list = True
        elif kind != "li" and in_list:
            out.append("</ul>")
            in_list = False
        if h:
            out.append(h)
    if in_list:
        out.append("</ul>")
    return {"html": "\n".join(out), "paragraphs": index}


def add_word_comment(
    path: str | Path, paragraph: int, text: str, author: str = "MimiWork"
) -> dict[str, Any]:
    """A real Word comment on body paragraph `paragraph` (0-based), saved in place."""
    from docx import Document

    doc = Document(str(path))
    paras = doc.paragraphs
    if not 0 <= paragraph < len(paras):
        raise ValueError(f"no paragraph {paragraph + 1} — the document has {len(paras)}")
    p = paras[paragraph]
    runs = list(p.runs) or [p.add_run("")]
    initials = "".join(w[0] for w in author.split()[:2]).upper() or "M"
    doc.add_comment(runs, text=text, author=author, initials=initials)
    doc.save(str(path))
    return {"paragraph": paragraph, "comments": len(list(doc.comments))}


# -- PowerPoint ---------------------------------------------------------------------


def pptx_to_html(path: str | Path) -> dict[str, Any]:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    prs = Presentation(str(path))
    images = _Images()
    out: list[str] = []
    n = 0
    for n, slide in enumerate(prs.slides, 1):
        title_shape = slide.shapes.title
        parts: list[str] = [f'<section class="slide" data-slide="{n}"><div class="slide-no">Slide {n}</div>']
        for shape in slide.shapes:
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                try:
                    parts.append(images.tag(shape.image.blob, shape.image.content_type))
                except Exception:
                    continue
                continue
            if getattr(shape, "has_table", False) and shape.has_table:
                rows = []
                for r, row in enumerate(shape.table.rows):
                    tag = "th" if r == 0 else "td"
                    rows.append("<tr>" + "".join(f"<{tag}>{_esc(c.text)}</{tag}>" for c in row.cells) + "</tr>")
                parts.append("<table>" + "".join(rows) + "</table>")
                continue
            if not getattr(shape, "has_text_frame", False) or not shape.has_text_frame:
                continue
            if title_shape is not None and shape.shape_id == title_shape.shape_id:
                parts.append(f"<h2>{_esc(shape.text_frame.text)}</h2>")
                continue
            for para in shape.text_frame.paragraphs:
                text = "".join(r.text for r in para.runs) or para.text
                if not text.strip():
                    continue
                indent = f' style="margin-left:{para.level * 16}px"' if para.level else ""
                parts.append(f"<p{indent}>{_esc(text)}</p>")
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                parts.append(f'<aside class="slide-notes">Notes: {_esc(notes)}</aside>')
        parts.append("</section>")
        out.append("".join(parts))
    return {"html": "\n".join(out), "slides": n}
