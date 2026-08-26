"""PowerPoint decks — read and write .pptx deliverables.

Slides are written from a small IR for the same reason Word is: the model produces
structured JSON reliably and OOXML not at all. The IR deliberately offers more than
bullets — ``statement``, ``stat``, ``quote``, ``two_column``, ``comparison`` — because a
deck made only of bullet lists is a deck nobody wants to sit through, and a tool that can
only emit bullet lists guarantees one.

The look lives in ``deck_theme`` / ``deck_render``: 16:9, a real type scale, and fonts that
are installed on the recipient's machine. Until 2026-08-25 this wrote python-pptx's stock
4:3 template in Calibri and the Office 2007 palette — the reason decks came out looking a
decade old whatever the content said. A user-supplied ``template`` still wins outright.

Speaker notes are a first-class field, not an afterthought. A deck handed over without notes
is not a finished deliverable — the person presenting it has to reconstruct the argument from
bullet fragments.

``read_presentation`` returns per-slide title, bullets, and notes so an existing deck can be
revised rather than regenerated from scratch.
"""

from __future__ import annotations

from typing import Any

from ... import deliverable_check
from . import deck_render, deck_theme
from ._common import clip, decorate, guard, require
from .paths import context_roots, display_path, resolve_read, resolve_write

_SLIDE_SHAPE = {
    "type": "object",
    "properties": {
        "layout": {
            "type": "string",
            "enum": list(deck_render.LAYOUTS),
            "description": (
                "Slide kind. 'title' (deck opener) · 'section' (divider) · 'bullets' "
                "(title + up to ~6 bullets) · 'statement' (ONE claim, large, no bullets — "
                "use for the argument's turning points) · 'stat' (1-3 big numbers with "
                "labels) · 'two_column' (two side-by-side lists) · 'comparison' (two "
                "tinted cards, e.g. before/after) · 'quote' (someone's own words) · "
                "'image' (a chart or picture, full width) · 'blank'. Vary them: a deck of "
                "nothing but 'bullets' is the one thing every audience dreads."
            ),
        },
        "title": {
            "type": "string",
            "description": (
                "Slide title. Make it the TAKEAWAY, not the topic: 'Churn is concentrated "
                "in month two', not 'Churn analysis'."
            ),
        },
        "subtitle": {"type": "string", "description": "Supporting line (title/section/statement)."},
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
            "description": "Path to a PNG/JPG to place on the slide (image layout).",
        },
        "caption": {
            "type": "string",
            "description": "For 'image': one line under the picture saying what it shows.",
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
            "Create or overwrite a PowerPoint (.pptx) deck from structured slides. Text is "
            "auto-fitted to its frame; if the result carries layout_warnings, those slides "
            "hold more than fits — rewrite or split them and call again. Produces a "
            "designed 16:9 deck — vary the slide layouts (statement / stat / quote / "
            "two_column / comparison / image), do not make every slide a bullet list, and "
            "write titles that state the takeaway rather than name the topic. Always include "
            "speaker notes — a deck without notes is not a finished deliverable. Use this for "
            "any slide deliverable; do NOT write a script to do it. Pass append=true to add "
            "slides to an existing deck."
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
            "Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The .pptx file to read."},
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
        path: str, slides: list, append: bool = False, template: str = ""
    ) -> dict[str, Any]:
        pptx = require("pptx", "python-pptx")

        target = resolve_write(path, roots)
        if not isinstance(slides, list):
            raise ValueError("'slides' must be a list of slide objects")

        if append and target.is_file():
            deck = pptx.Presentation(str(target))
        elif template:
            deck = pptx.Presentation(str(resolve_read(template, roots)))
        else:
            deck = pptx.Presentation()

        # A house template carries the brand; ours only applies when there isn't one.
        # Appending never restyles what is already there — someone else's deck is not
        # ours to reflow.
        theme = deck_theme.read_theme(deck) if template else deck_theme.NEUTRAL_MODERN
        widened = deck_theme.apply_slide_size(deck)
        if not template and not append:
            deck_theme.apply_theme_fonts(deck, theme)

        existing = len(deck.slides)
        layout_warnings: list[str] = []
        for offset, entry in enumerate(slides):
            if not isinstance(entry, dict):
                raise ValueError(f"each slide must be an object, got {type(entry).__name__}")

            def _picture(rel: str) -> str:
                found = resolve_read(rel, roots)
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
            "widescreen": widened or deck.slide_width == deck_theme.SLIDE_WIDTH_EMU,
            "bytes": target.stat().st_size,
        }
        if layout_warnings:
            # The deck IS saved — text was shrunk to its floor — but these slides hold
            # more than fits. There is no renderer here to screenshot-and-verify with,
            # so this estimate is the layout check; the model must act on it.
            result["layout_warnings"] = layout_warnings
            result["action_required"] = (
                "Rewrite the flagged slides with fewer/shorter bullets or split each "
                "into two slides, then call write_presentation again."
            )
        return deliverable_check.attach(result, target)

    @guard
    def read_presentation(path: str) -> dict[str, Any]:
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

        return {
            "path": display_path(target, roots),
            "total_slides": len(slides),
            "slides": slides,
        }

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
