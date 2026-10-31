"""The QualiTaTi palette and type scale for new decks, with template inheritance."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Optional

# 16:9 at PowerPoint's own widescreen size (13.333in x 7.5in), in EMU.
SLIDE_WIDTH_EMU = 12192000
SLIDE_HEIGHT_EMU = 6858000

_THEME_REL = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme"
)


@dataclass(frozen=True)
class Theme:
    """Fonts, colours and the type scale, in one place so every layout agrees."""

    heading: str = "Instrument Serif"
    # PowerPoint may silently render the variable DM Sans face as Calibri.
    body: str = "Arial"

    # Colours as RRGGBB ints — python-pptx's RGBColor takes the same.
    ink: int = 0x111C1B
    body_ink: int = 0x111C1B
    muted: int = 0x65706B
    accent: int = 0x0B7C72
    bg: int = 0xFAFAF7

    # Type scale (points). One ratio, applied everywhere.
    size_deck_title: int = 48
    size_section: int = 34
    size_slide_title: int = 34
    size_statement: int = 32
    size_body: int = 18
    size_body_sub: int = 15
    size_quote: int = 28
    size_caption: int = 13
    size_footer: int = 10

    # Geometry (inches). Generous margins are most of what "designed" means.
    canvas_width: float = 13.333
    margin_x: float = 0.85
    title_top: float = 0.52
    content_top: float = 1.62
    content_bottom: float = 6.75

    @property
    def content_width(self) -> float:
        return self.canvas_width - (2 * self.margin_x)


QUALITATI = Theme()


def custom_theme(style: dict) -> Theme:
    """Apply an explicit brief to a fresh deck. Hex colours are stored in its theme too."""
    settings = {}
    for key in ("heading", "body"):
        if key in style:
            name = style[key]
            if not isinstance(name, str) or not name.strip():
                raise ValueError(f"style.{key} must be a font name")
            settings[key] = name.strip()
    for key in ("ink", "bg", "accent"):
        if key in style:
            value = style[key]
            if not isinstance(value, str) or not re.fullmatch("#?[0-9A-Fa-f]{6}", value):
                raise ValueError(f"style.{key} must be a six-digit hex colour")
            settings[key] = int(value.lstrip("#"), 16)
    if "ink" in settings or "bg" in settings:
        settings["body_ink"] = settings["muted"] = settings.get("ink", QUALITATI.ink)
    return replace(QUALITATI, **settings)


def bullet_size(theme: Theme, level: int) -> int:
    """Bullets step down with depth, but never below readable-from-the-back."""
    return max(theme.size_body - (3 * max(level, 0)), 13)


def read_theme(deck: Any) -> Theme:
    """The theme carried by a user-supplied template, falling back to ours per field.

    A house template is the one thing that outranks our design system: the whole point of
    passing `template=` is that the deck comes out in the organisation's brand.
    """
    from lxml import etree
    from pptx.oxml.ns import qn

    try:
        part = deck.slide_masters[0].part.part_related_by(_THEME_REL)
        root = etree.fromstring(part.blob)
    except (IndexError, KeyError, etree.XMLSyntaxError):
        return QUALITATI

    def _font(tag: str) -> Optional[str]:
        latin = root.find(f".//{qn('a:' + tag)}/{qn('a:latin')}")
        name = latin.get("typeface", "").strip() if latin is not None else ""
        return name if name and not name.startswith("+") else None

    def _color(tag: str, fallback: int) -> int:
        color = root.find(f".//{qn('a:clrScheme')}/{qn('a:' + tag)}/*")
        if color is not None:
            value = color.get("lastClr") or color.get("val", "")
            if re.fullmatch("[0-9A-Fa-f]{6}", value):
                return int(value, 16)
        return fallback

    base = QUALITATI
    ink = _color("dk1", base.ink)
    bg = _color("lt1", base.bg)
    return Theme(
        heading=_font("majorFont") or base.heading,
        body=_font("minorFont") or base.body,
        ink=ink,
        body_ink=ink,
        accent=_color("accent1", base.accent),
        muted=base.muted if (bg, ink) == (base.bg, base.ink) else ink,
        bg=bg,
    )


def apply_slide_size(deck: Any) -> bool:
    """Force 16:9 on a deck built from python-pptx's 4:3 default. Returns True if changed.

    Never resizes a deck that already has slides (appending to someone's 4:3 deck and
    silently reflowing every existing slide would be vandalism, not a fix).
    """
    if len(deck.slides):
        return False
    if deck.slide_width == SLIDE_WIDTH_EMU and deck.slide_height == SLIDE_HEIGHT_EMU:
        return False
    deck.slide_width = SLIDE_WIDTH_EMU
    deck.slide_height = SLIDE_HEIGHT_EMU
    return True


def apply_theme(deck: Any, theme: Theme) -> None:
    """Save the selected typefaces and palette for slides and future PowerPoint edits."""
    from lxml import etree
    from pptx.oxml.ns import qn

    part = deck.slide_masters[0].part.part_related_by(_THEME_REL)
    root = etree.fromstring(part.blob)
    for tag, face in (("majorFont", theme.heading), ("minorFont", theme.body)):
        latin = root.find(f".//{qn('a:' + tag)}/{qn('a:latin')}")
        latin.set("typeface", face)
    for tag, color in (("dk1", theme.ink), ("lt1", theme.bg), ("accent1", theme.accent)):
        slot = root.find(f".//{qn('a:clrScheme')}/{qn('a:' + tag)}")
        slot.clear()
        etree.SubElement(slot, qn("a:srgbClr"), val=f"{color:06X}")
    part._blob = etree.tostring(root, encoding="utf-8", xml_declaration=True)
