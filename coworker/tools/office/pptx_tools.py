"""PowerPoint decks — read and write .pptx deliverables.

Slides are written from a small IR for the same reason Word is: the model produces
structured JSON reliably and OOXML not at all. The IR deliberately offers more than
bullets — ``statement``, ``stat``, ``quote``, ``two_column``, ``comparison`` — because a
deck made only of bullet lists is a deck nobody wants to sit through, and a tool that can
only emit bullet lists guarantees one.

New decks use the QualiTaTi editorial theme. Existing decks and templates carry their own theme.

Speaker notes are a first-class field, not an afterthought. A deck handed over without notes
is not a finished deliverable — the person presenting it has to reconstruct the argument from
bullet fragments.

``read_presentation`` returns per-slide title, bullets, and notes so an existing deck can be
revised rather than regenerated from scratch.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from ... import deliverable_check
from ...secrets import state_dir
from . import deck_render, deck_theme
from ._common import clip, decorate, guard, require
from .paths import PathError, context_roots, display_path, resolve_read, resolve_write
from .pdf_tools import MAX_PAGE_PICTURES, render_pages

_PICTURE_TYPES = (".png", ".jpg", ".jpeg")
_NO_RENDERER = (
    "This computer has nothing to draw slides with, so they cannot be shown. "
    "Installing LibreOffice (free) makes it possible."
)
# Seen on a real run: LibreOffice drew Courier New but replaced Chalkboard SE, a font the
# Mac has. A model told nothing would "fix" a typeface that is right in PowerPoint.
_FONT_CAVEAT = (
    "They are drawn by LibreOffice, which replaces fonts it does not have: judge layout, "
    "colour, pictures and overflow from them, not the typeface."
)
# A packaged app does not inherit the shell's PATH, so the usual install places are named.
_SOFFICE_PLACES = (
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/opt/homebrew/bin/soffice",
    "/usr/local/bin/soffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
)


def _soffice() -> str:
    return shutil.which("soffice") or next((p for p in _SOFFICE_PLACES if os.path.exists(p)), "")


def slide_pictures(deck: Path, numbers: list[int]) -> list[str]:
    """Pictures of the numbered slides as they really render, or nothing when this
    computer has no LibreOffice to draw them with. Never raises: a deck that saved
    correctly must not fail because it could not also be pictured."""
    exe = _soffice()
    if not exe or not numbers:
        return []
    # ponytail: one shared folder, pictures replaced per deck name; clear it if it ever grows.
    work = Path(tempfile.gettempdir()) / "mimiwork-slide-pictures"
    flat = work / f"{deck.stem}.pdf"
    try:
        work.mkdir(parents=True, exist_ok=True)
        # Its own settings folder, so a LibreOffice the user has open cannot block this one.
        subprocess.run(
            [exe, f"-env:UserInstallation={(work / 'settings').as_uri()}", "--headless",
             "--convert-to", "pdf", "--outdir", str(work), str(deck)],
            check=True, capture_output=True, timeout=120,
        )
        return [str(p) for p in render_pages(flat, numbers, work, deck.stem)]
    except Exception:
        return []
    finally:
        flat.unlink(missing_ok=True)

_SLIDE_SHAPE = {
    "type": "object",
    "properties": {
        "layout": {
            "type": "string",
            "enum": list(deck_render.LAYOUTS),
            "description": (
                "Use title or section for an opening, statement for a claim, stat for values "
                "with their labels, two_column or comparison for alternatives, quote for a "
                "speaker's words, image for a complete figure, photo_split for a cropped "
                "photograph beside a title and subtitle, bullets for a list, or blank."
            ),
        },
        "title": {
            "type": "string",
            "description": (
                "State the idea in the title, e.g. 'Churn is concentrated in month two'."
            ),
        },
        "subtitle": {"type": "string", "description": "Supporting line for title, section, statement or photo_split."},
        "bullets": {
            "type": "array",
            "description": "Body bullets. Use {'text': ..., 'level': 1} for sub-bullets.",
            "items": {},
        },
        "statement": {
            "type": "string",
            "description": "The single claim on a 'statement' slide (falls back to title).",
        },
        "stats": {
            "type": "array",
            "description": "For 'stat': [{'value': '68%', 'label': 'finished the survey'}], 1-3 of them.",
            "items": {
                "type": "object",
                "properties": {
                    "value": {"type": "string", "description": "The number, short: '68%', '3.4x', '412'."},
                    "label": {"type": "string", "description": "What it measures, in plain words."},
                },
            },
        },
        "columns": {
            "type": "array",
            "description": (
                "For 'two_column'/'comparison': exactly two "
                "[{'heading': ..., 'bullets': [...]}, {...}]."
            ),
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "bullets": {"type": "array", "items": {}},
                },
            },
        },
        "quote": {"type": "string", "description": "For 'quote': the quoted words themselves."},
        "attribution": {"type": "string", "description": "For 'quote': who said it."},
        "image": {
            "type": "string",
            "description": "PNG/JPG in a granted folder for image or photo_split.",
        },
        "photo_focus": {
            "type": "number", "minimum": 0, "maximum": 1,
            "description": "For photo_split, place the crop toward the start (0), center (0.5) or end (1) of the cropped axis.",
        },
        "caption": {
            "type": "string",
            "description": "For 'image': one line under the picture saying what it shows.",
        },
        "background": {
            "type": "string",
            "description": (
                "PNG/JPG that fills this slide behind its text, e.g. a textured or "
                "illustrated page. Overrides style.background."
            ),
        },
        "notes": {
            "type": "string",
            "description": "Speaker notes — what the presenter should say on this slide.",
        },
    },
}

_WRITE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_presentation",
        "description": (
            "Write an editable PowerPoint (.pptx) from structured slides. A new deck uses "
            "the QualiTaTi theme. Use the audience, purpose and constraints from the brief "
            "to choose the sequence and layouts. Include useful speaker notes. Resolve "
            "layout_warnings by reflowing or splitting slides. Pass a supplied template to "
            "inherit its theme or append=true to add slides to an existing deck. To follow "
            "a visual style the layouts cannot draw (textures, hand-drawn shapes, "
            "illustrated pages), put that look in a background picture and keep the words "
            "as editable text on top. When pictures of the finished slides come back, "
            "compare them with the brief or reference and rewrite what does not match."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Destination .pptx path."},
                "slides": {
                    "type": "array",
                    "description": "Slides, in order.",
                    "items": _SLIDE_SHAPE,
                },
                "append": {
                    "type": "boolean",
                    "description": "Append to an existing deck (default false = overwrite).",
                },
                "style": {
                    "type": "object",
                    "description": "Explicit typefaces or palette for a new deck. A template or existing deck takes precedence.",
                    "properties": {
                        "heading": {"type": "string", "description": "Title font family."},
                        "body": {"type": "string", "description": "Body font family."},
                        "ink": {"type": "string", "description": "Text colour, e.g. #111C1B."},
                        "bg": {"type": "string", "description": "Paper colour, e.g. #FAFAF7."},
                        "accent": {"type": "string", "description": "Accent colour, e.g. #0B7C72."},
                        "background": {
                            "type": "string",
                            "description": "PNG/JPG that fills every slide behind its text.",
                        },
                    },
                    "additionalProperties": False,
                },
                "template": {
                    "type": "string",
                    "description": (
                        "Optional .pptx/.potx to inherit theme, fonts, and branding from. "
                        "Use the organisation's template when there is one."
                    ),
                },
            },
            "required": ["path", "slides"],
        },
    },
}

_READ_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_presentation",
        "description": (
            "Read a PowerPoint (.pptx) deck as numbered slides with their titles, bullet text, "
            "and speaker notes — so an existing deck can be revised rather than rebuilt. "
            "This returns words only: pass show_slides to also LOOK at chosen slides as "
            "pictures, which is the only way to judge or imitate a design. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The .pptx file to read."},
                "show_slides": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": f"Slide numbers to see as pictures, 1-based, at most {MAX_PAGE_PICTURES}.",
                },
            },
            "required": ["path"],
        },
    },
}


def _bullet_entry(item: Any) -> tuple[str, int]:
    if isinstance(item, dict):
        level = item.get("level", 0)
        return str(item.get("text") or ""), level if isinstance(level, int) and level > 0 else 0
    return str(item), 0


def _set_notes(slide: Any, notes: str) -> None:
    if notes:
        slide.notes_slide.notes_text_frame.text = notes


def pptx_tools(context: Any) -> list:
    roots = context_roots(context)

    @guard
    def write_presentation(
        path: str, slides: list, append: bool = False, template: str = "",
        style: dict | None = None,
    ) -> dict[str, Any]:
        pptx = require("pptx", "python-pptx")

        target = resolve_write(path, roots)
        if not isinstance(slides, list):
            raise ValueError("'slides' must be a list of slide objects")

        extending = append and target.is_file()
        if extending:
            deck = pptx.Presentation(str(target))
        elif template:
            deck = pptx.Presentation(str(resolve_read(template, roots)))
        else:
            deck = pptx.Presentation()

        if extending or template:
            theme = deck_theme.read_theme(deck)
        else:
            theme = deck_theme.custom_theme(style or {})
            deck_theme.apply_slide_size(deck)
            deck_theme.apply_theme(deck, theme)
        theme = replace(theme, canvas_width=deck.slide_width.inches)

        existing = len(deck.slides)
        layout_warnings: list[str] = []
        for offset, entry in enumerate(slides):
            if not isinstance(entry, dict):
                raise ValueError(f"each slide must be an object, got {type(entry).__name__}")

            def _picture(rel: str) -> str:
                try:
                    found = resolve_read(rel, roots)
                except PathError:
                    # A style skill keeps its own pictures (backgrounds, marks) in the
                    # user's skills folder. Pictures there, and nothing else, may be placed.
                    found = Path(rel).expanduser().resolve()
                    skills = (state_dir() / "skills").resolve()
                    if skills not in found.parents or found.suffix.lower() not in _PICTURE_TYPES:
                        raise
                if not found.is_file():
                    raise FileNotFoundError(display_path(found, roots))
                return str(found)

            slide, slide_warnings = deck_render.paint(
                deck,
                entry,
                theme,
                number=existing + offset + 1,
                resolve_image=_picture,
            )
            backdrop = str(entry.get("background") or (style or {}).get("background") or "")
            if backdrop:
                deck_render.paint_background(
                    slide, _picture(backdrop), deck.slide_width, deck.slide_height
                )
            _set_notes(slide, str(entry.get("notes") or ""))
            for w in slide_warnings:
                layout_warnings.append(f"slide {existing + offset + 1}: {w}")

        target.parent.mkdir(parents=True, exist_ok=True)
        deck.save(str(target))
        result: dict[str, Any] = {
            "path": display_path(target, roots),
            "slides_written": len(slides),
            "total_slides": len(list(deck.slides)),
            "appended": bool(append),
            "widescreen": deck.slide_width * 9 == deck.slide_height * 16,
            "bytes": target.stat().st_size,
        }
        if not (extending or template or (style and "body" in style)):
            result["font_note"] = "The PowerPoint deck uses Arial, the portable body-font fallback for DM Sans."
        if layout_warnings:
            # The deck IS saved — text was shrunk to its floor — but these slides hold
            # more than fits. Most computers have no renderer to picture the slides with,
            # so this estimate is the layout check; the model must act on it.
            result["layout_warnings"] = layout_warnings
            result["action_required"] = (
                "Rewrite the flagged slides with fewer/shorter bullets or split each "
                "into two slides, then call write_presentation again."
            )
        shown = range(existing + 1, existing + min(len(slides), MAX_PAGE_PICTURES) + 1)
        pictures = slide_pictures(target, list(shown))
        if pictures:
            result["_images"] = pictures
            result["shown"] = (
                f"Pictures of slides {shown[0]}-{shown[-1]} follow this step. Look at them "
                "against the brief and any reference before saying the deck is ready. "
                + _FONT_CAVEAT
            )
        return deliverable_check.attach(result, target)

    @guard
    def read_presentation(path: str, show_slides: list | None = None) -> dict[str, Any]:
        pptx = require("pptx", "python-pptx")
        target = resolve_read(path, roots)
        if not target.is_file():
            raise FileNotFoundError(display_path(target, roots))

        deck = pptx.Presentation(str(target))
        slides: list[dict[str, Any]] = []
        for index, slide in enumerate(deck.slides):
            title = ""
            if slide.shapes.title is not None:
                title = slide.shapes.title.text.strip()

            bullets: list[str] = []
            for shape in slide.shapes:
                if not shape.has_text_frame or shape == slide.shapes.title:
                    continue
                if shape.name == deck_render.FOOTER_SHAPE_NAME:
                    continue  # the printed slide number is chrome, not content
                for para in shape.text_frame.paragraphs:
                    text = "".join(run.text for run in para.runs).strip()
                    if text:
                        bullets.append(clip(("  " * para.level) + text))

            notes = ""
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame.text.strip()

            slides.append(
                {
                    "index": index,
                    "title": clip(title),
                    "bullets": bullets,
                    "notes": clip(notes),
                }
            )

        result: dict[str, Any] = {
            "path": display_path(target, roots),
            "total_slides": len(slides),
            "slides": slides,
        }
        wanted = sorted({n for n in show_slides or [] if isinstance(n, int) and 1 <= n <= len(slides)})
        if wanted:
            pictures = slide_pictures(target, wanted[:MAX_PAGE_PICTURES])
            result["show_slides_note"] = _FONT_CAVEAT if pictures else _NO_RENDERER
            if pictures:
                result["_images"] = pictures
        return result

    return [
        decorate(
            write_presentation,
            name="write_presentation",
            schema=_WRITE_SCHEMA,
            risk="medium",
            capabilities=["write"],
        ),
        decorate(read_presentation, name="read_presentation", schema=_READ_SCHEMA),
    ]
