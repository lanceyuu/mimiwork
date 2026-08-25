"""The look of a MimiWork deck: one design system, applied to every slide.

Before this module, `write_presentation` handed python-pptx's stock `default.pptx` back to
the user: a **4:3** canvas, Calibri, and the Office 2007 accent palette (that blue, that
brick red, that olive). Every deck arrived letterboxed on a modern screen and looked a
decade old before a word of content landed. Nothing here is decoration — it is the
difference between a file someone presents and a file someone apologises for.

Three decisions worth knowing:

* **16:9, always.** A 4:3 deck is the single loudest "this is old" signal a slide can send.
* **Fonts that are actually installed.** In HTML you can load any face you like; in a
  `.pptx` an unavailable font is silently substituted on the recipient's machine, which
  looks worse than a plain one. Georgia and Arial ship with Windows, macOS and Office, so
  the deck looks the same on the reviewer's laptop as it did here. The character comes from
  scale, colour and space instead — the parts that travel.
* **Their template wins.** When the user passes their organisation's `.potx`, `read_theme`
  pulls the fonts and colours out of it and this system defers: our geometry, their brand.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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

    heading: str = "Georgia"
    body: str = "Arial"

    # Colours as RRGGBB ints — python-pptx's RGBColor takes the same.
    ink: int = 0x111827  # near-black with a hint of blue; pure #000 reads harsh
    body_ink: int = 0x374151
    muted: int = 0x6B7280
    accent: int = 0x0F766E  # deep teal: professional, and nobody's default
    accent_soft: int = 0xE6F4F1
    rule: int = 0xD8DEE6
    bg: int = 0xFFFFFF

    # Type scale (points). One ratio, applied everywhere.
    size_deck_title: int = 40
    size_section: int = 34
    size_slide_title: int = 28
    size_statement: int = 32
    size_stat: int = 66
    size_stat_label: int = 14
    size_body: int = 18
    size_body_sub: int = 15
    size_quote: int = 28
    size_caption: int = 13
    size_footer: int = 10

    # Geometry (inches). Generous margins are most of what "designed" means.
    margin_x: float = 0.85
    title_top: float = 0.52
    content_top: float = 1.62
    content_bottom: float = 6.75

    @property
    def content_width(self) -> float:
        return 13.333 - (2 * self.margin_x)


NEUTRAL_MODERN = Theme()


def bullet_size(theme: Theme, level: int) -> int:
    """Bullets step down with depth, but never below readable-from-the-back."""
    return max(theme.size_body - (3 * max(level, 0)), 13)


def read_theme(deck: Any) -> Theme:
    """The theme carried by a user-supplied template, falling back to ours per field.

    A house template is the one thing that outranks our design system: the whole point of
    passing `template=` is that the deck comes out in the organisation's brand.
    """
    try:
        part = deck.slide_masters[0].part.part_related_by(_THEME_REL)
        xml = part.blob.decode("utf-8", "ignore")
    except Exception:
        return NEUTRAL_MODERN

    def _font(tag: str) -> Optional[str]:
        block = re.search(rf"<a:{tag}>(.*?)</a:{tag}>", xml, re.S)
        if not block:
            return None
        face = re.search(r'<a:latin[^>]*typeface="([^"]*)"', block.group(1))
        name = (face.group(1) if face else "").strip()
        # "+mj-lt" and friends are references, not faces; an empty typeface means "inherit".
        return name if name and not name.startswith("+") else None

    def _color(tag: str) -> Optional[int]:
        block = re.search(rf"<a:{tag}>(.*?)</a:{tag}>", xml, re.S)
        if not block:
            return None
        value = re.search(r'val="([0-9A-Fa-f]{6})"', block.group(1))
        return int(value.group(1), 16) if value else None

    base = NEUTRAL_MODERN
    return Theme(
        heading=_font("majorFont") or base.heading,
        body=_font("minorFont") or base.body,
        ink=_color("dk1") or base.ink,
        body_ink=_color("dk1") or base.body_ink,
        accent=_color("accent1") or base.accent,
        muted=base.muted,
        accent_soft=base.accent_soft,
        rule=base.rule,
        bg=_color("lt1") or base.bg,
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


def apply_theme_fonts(deck: Any, theme: Theme) -> None:
    """Rewrite the deck's theme fonts so anything the USER adds later matches the deck.

    Text this module writes carries explicit fonts already; this is for the text box a
    person adds in PowerPoint afterwards, which inherits from the theme.
    """
    try:
        part = deck.slide_masters[0].part.part_related_by(_THEME_REL)
        xml = part.blob.decode("utf-8")
    except Exception:
        return

    def _swap(tag: str, face: str, source: str) -> str:
        block = re.search(rf"(<a:{tag}>)(.*?)(</a:{tag}>)", source, re.S)
        if not block:
            return source
        inner = re.sub(
            r'(<a:latin[^>]*typeface=")[^"]*(")', rf"\g<1>{face}\g<2>", block.group(2)
        )
        return source[: block.start()] + block.group(1) + inner + block.group(3) + source[block.end() :]

    xml = _swap("majorFont", theme.heading, xml)
    xml = _swap("minorFont", theme.body, xml)
    try:
        part._blob = xml.encode("utf-8")
    except Exception:
        return
