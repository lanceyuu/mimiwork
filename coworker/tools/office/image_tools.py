"""Image editing — the last mile of a visual deliverable.

Knowledge work generates images constantly: a chart the analysis produced, a screenshot to
annotate, a logo to place, a photo that is 8 MB when the deck needs 300 KB. Without these
tools the agent can only pass images around unchanged.

Two design points.

*Never edit in place by default.* An edit writes to a new path unless the caller explicitly
opts into overwriting. The user's original screenshot or chart is frequently irreplaceable,
and a destructive default turns one wrong argument into lost work.

*Report the result.* Every operation returns the new dimensions and file size, because the
reason for the edit is usually a constraint ("fit this slide", "under 1 MB") that the model
otherwise has no way to verify it met.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ._common import decorate, guard, require
from .paths import context_roots, display_path, resolve_read, resolve_write

# Bound the output of a single operation: a resize to 40000px would exhaust memory, and
# Pillow's own decompression-bomb guard only covers what it reads, not what we ask it to make.
_MAX_DIMENSION = 20_000
_MAX_PIXELS = 80_000_000

_INFO_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_image_info",
        "description": (
            "Read an image's dimensions, format, colour mode, and file size — without loading "
            "the pixels into the conversation. Check this before editing, so a resize or crop "
            "is based on the real dimensions rather than a guess. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The image file to inspect."}
            },
            "required": ["path"],
        },
    },
}

_EDIT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "edit_image",
        "description": (
            "Transform an image: resize, crop, rotate, flip, convert format, adjust quality, "
            "or convert to greyscale. Operations apply in the order listed here. Writes to "
            "'output' — the original is never modified unless output is the same path. Use "
            "this to fit a chart to a slide, shrink an oversized photo, or crop a screenshot."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Source image."},
                "output": {
                    "type": "string",
                    "description": "Destination path. Extension sets the output format.",
                },
                "width": {
                    "type": "integer",
                    "description": "Target width in pixels. With only one of width/height, "
                    "the aspect ratio is preserved.",
                },
                "height": {"type": "integer", "description": "Target height in pixels."},
                "max_width": {
                    "type": "integer",
                    "description": "Shrink to fit this width, keeping aspect ratio. Never enlarges.",
                },
                "max_height": {
                    "type": "integer",
                    "description": "Shrink to fit this height, keeping aspect ratio.",
                },
                "crop": {
                    "type": "array",
                    "description": "Crop box as [left, top, right, bottom] in pixels.",
                    "items": {"type": "integer"},
                },
                "rotate": {
                    "type": "integer",
                    "description": "Rotate clockwise by this many degrees.",
                },
                "flip": {
                    "type": "string",
                    "enum": ["horizontal", "vertical"],
                    "description": "Mirror the image.",
                },
                "grayscale": {"type": "boolean", "description": "Convert to greyscale."},
                "quality": {
                    "type": "integer",
                    "description": "JPEG/WebP quality 1-95 (default 85). Lower means smaller files.",
                },
            },
            "required": ["path", "output"],
        },
    },
}

_ANNOTATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "annotate_image",
        "description": (
            "Draw callouts on an image: labelled boxes, arrows, text, and highlights. Use this "
            "to point at what matters in a screenshot or chart before putting it in a document "
            "or deck. Coordinates are pixels from the top-left; check read_image_info first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Source image."},
                "output": {"type": "string", "description": "Destination path."},
                "annotations": {
                    "type": "array",
                    "description": "Marks to draw, in order.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {
                                "type": "string",
                                "enum": ["box", "arrow", "text", "highlight", "line"],
                                "description": "Mark kind.",
                            },
                            "box": {
                                "type": "array",
                                "description": "[left, top, right, bottom] for box/highlight.",
                                "items": {"type": "integer"},
                            },
                            "from": {
                                "type": "array",
                                "description": "[x, y] start point for arrow/line.",
                                "items": {"type": "integer"},
                            },
                            "to": {
                                "type": "array",
                                "description": "[x, y] end point for arrow/line.",
                                "items": {"type": "integer"},
                            },
                            "at": {
                                "type": "array",
                                "description": "[x, y] anchor for text.",
                                "items": {"type": "integer"},
                            },
                            "text": {"type": "string", "description": "Label to draw."},
                            "color": {
                                "type": "string",
                                "description": "Colour name or #RRGGBB (default red).",
                            },
                            "width": {
                                "type": "integer",
                                "description": "Stroke width in pixels (default 3).",
                            },
                            "font_size": {
                                "type": "integer",
                                "description": "Text size in pixels (default 20).",
                            },
                        },
                        "required": ["type"],
                    },
                },
            },
            "required": ["path", "output", "annotations"],
        },
    },
}

_COMPOSE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "combine_images",
        "description": (
            "Combine several images into one — side by side, stacked, or in a grid. Use this "
            "for before/after comparisons and small-multiple figures that belong on a single "
            "slide or page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "description": "Source images, in order.",
                    "items": {"type": "string"},
                },
                "output": {"type": "string", "description": "Destination path."},
                "layout": {
                    "type": "string",
                    "enum": ["horizontal", "vertical", "grid"],
                    "description": "Arrangement (default horizontal).",
                },
                "columns": {
                    "type": "integer",
                    "description": "Grid layout only: images per row (default 2).",
                },
                "spacing": {
                    "type": "integer",
                    "description": "Gap between images in pixels (default 10).",
                },
                "background": {
                    "type": "string",
                    "description": "Background colour (default white).",
                },
            },
            "required": ["paths", "output"],
        },
    },
}


def _open(module: Any, target: Path) -> Any:
    try:
        image = module.open(target)
        image.load()
        return image
    except Exception as exc:
        raise ValueError(f"could not read the image: {exc}") from exc


def _guard_size(width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid target size {width}x{height}")
    if width > _MAX_DIMENSION or height > _MAX_DIMENSION:
        raise ValueError(
            f"target {width}x{height} exceeds the {_MAX_DIMENSION}px limit per side"
        )
    if width * height > _MAX_PIXELS:
        raise ValueError(f"target {width}x{height} exceeds the {_MAX_PIXELS:,} pixel limit")


def _prepare_for_save(image: Any, target: Path) -> Any:
    """JPEG has no alpha channel; saving RGBA to .jpg raises deep inside Pillow."""
    if target.suffix.lower() in {".jpg", ".jpeg"} and image.mode in {"RGBA", "LA", "P"}:
        converted = image.convert("RGBA")
        from PIL import Image as _Image

        flattened = _Image.new("RGB", converted.size, (255, 255, 255))
        flattened.paste(converted, mask=converted.split()[-1])
        return flattened
    if target.suffix.lower() in {".jpg", ".jpeg"} and image.mode not in {"RGB", "L"}:
        return image.convert("RGB")
    return image


def _save(image: Any, target: Path, quality: Optional[int] = None) -> dict[str, Any]:
    target.parent.mkdir(parents=True, exist_ok=True)
    prepared = _prepare_for_save(image, target)
    options: dict[str, Any] = {}
    if target.suffix.lower() in {".jpg", ".jpeg", ".webp"}:
        options["quality"] = max(1, min(int(quality or 85), 95))
        options["optimize"] = True
    try:
        prepared.save(target, **options)
    except (OSError, KeyError, ValueError) as exc:
        raise ValueError(f"could not write {target.suffix or 'image'}: {exc}") from exc
    return {"width": prepared.width, "height": prepared.height, "bytes": target.stat().st_size}


def _color(value: Any, default: str = "red") -> Any:
    return str(value) if value else default


def _font(size: int) -> Any:
    """A truetype font if one is findable, else Pillow's bitmap default (which ignores size)."""
    from PIL import ImageFont

    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except (OSError, ValueError):
            continue
    return ImageFont.load_default()


def _xy(value: Any, name: str, length: int = 2) -> list:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(f"'{name}' must be a list of {length} numbers")
    return [int(v) for v in value]


def image_tools(context: Any) -> list:
    roots = context_roots(context)

    @guard
    def read_image_info(path: str) -> dict[str, Any]:
        module = require("PIL.Image", "Pillow", extra="office")
        target = resolve_read(path, roots)
        if not target.is_file():
            raise FileNotFoundError(display_path(target, roots))

        image = _open(module, target)
        info: dict[str, Any] = {
            "path": display_path(target, roots),
            "width": image.width,
            "height": image.height,
            "format": image.format or target.suffix.lstrip(".").upper(),
            "mode": image.mode,
            "bytes": target.stat().st_size,
            "aspect_ratio": round(image.width / image.height, 3) if image.height else None,
        }
        if image.mode in {"RGBA", "LA", "P"}:
            info["has_transparency"] = True
        return info

    @guard
    def edit_image(
        path: str,
        output: str,
        width: int = 0,
        height: int = 0,
        max_width: int = 0,
        max_height: int = 0,
        crop: Any = None,
        rotate: int = 0,
        flip: str = "",
        grayscale: bool = False,
        quality: int = 85,
    ) -> dict[str, Any]:
        module = require("PIL.Image", "Pillow", extra="office")
        source = resolve_read(path, roots)
        if not source.is_file():
            raise FileNotFoundError(display_path(source, roots))
        destination = resolve_write(output, roots)

        image = _open(module, source)
        original = (image.width, image.height)
        applied: list[str] = []

        if crop:
            box = _xy(crop, "crop", 4)
            left, top, right, bottom = box
            if right <= left or bottom <= top:
                raise ValueError("crop must be [left, top, right, bottom] with right>left, bottom>top")
            # Clamp to the image rather than failing: a model's box is often a few pixels out.
            box = [
                max(0, left),
                max(0, top),
                min(image.width, right),
                min(image.height, bottom),
            ]
            image = image.crop(tuple(box))
            applied.append(f"crop{tuple(box)}")

        if width or height:
            target_w = int(width) if width else 0
            target_h = int(height) if height else 0
            if target_w and not target_h:
                target_h = max(1, round(image.height * target_w / image.width))
            elif target_h and not target_w:
                target_w = max(1, round(image.width * target_h / image.height))
            _guard_size(target_w, target_h)
            image = image.resize((target_w, target_h), module.LANCZOS)
            applied.append(f"resize({target_w}x{target_h})")
        elif max_width or max_height:
            limit_w = int(max_width) if max_width else image.width
            limit_h = int(max_height) if max_height else image.height
            _guard_size(limit_w, limit_h)
            # thumbnail only ever shrinks, which is what "max" means.
            image.thumbnail((limit_w, limit_h), module.LANCZOS)
            applied.append(f"fit({image.width}x{image.height})")

        if rotate:
            image = image.rotate(-int(rotate), expand=True, fillcolor=None)
            applied.append(f"rotate({int(rotate)})")

        if flip:
            direction = str(flip).lower()
            if direction == "horizontal":
                image = image.transpose(module.FLIP_LEFT_RIGHT)
            elif direction == "vertical":
                image = image.transpose(module.FLIP_TOP_BOTTOM)
            else:
                raise ValueError("flip must be 'horizontal' or 'vertical'")
            applied.append(f"flip({direction})")

        if grayscale:
            image = image.convert("L")
            applied.append("grayscale")

        saved = _save(image, destination, quality)
        return {
            "path": display_path(destination, roots),
            "original_size": f"{original[0]}x{original[1]}",
            "size": f"{saved['width']}x{saved['height']}",
            "bytes": saved["bytes"],
            "operations": applied or ["convert"],
        }

    @guard
    def annotate_image(path: str, output: str, annotations: list) -> dict[str, Any]:
        module = require("PIL.Image", "Pillow", extra="office")
        from PIL import ImageDraw

        source = resolve_read(path, roots)
        if not source.is_file():
            raise FileNotFoundError(display_path(source, roots))
        destination = resolve_write(output, roots)
        if not isinstance(annotations, list) or not annotations:
            raise ValueError("'annotations' must be a non-empty list")

        image = _open(module, source).convert("RGBA")
        overlay = module.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        drawn = 0

        for mark in annotations:
            if not isinstance(mark, dict):
                raise ValueError("each annotation must be an object with a 'type'")
            kind = str(mark.get("type") or "").lower()
            color = _color(mark.get("color"))
            stroke = int(mark.get("width") or 3)

            if kind == "box":
                box = _xy(mark.get("box"), "box", 4)
                draw.rectangle(box, outline=color, width=stroke)
                if mark.get("text"):
                    font = _font(int(mark.get("font_size") or 20))
                    draw.text((box[0], max(0, box[1] - int(mark.get("font_size") or 20) - 4)),
                              str(mark["text"]), fill=color, font=font)
            elif kind == "highlight":
                box = _xy(mark.get("box"), "box", 4)
                # Translucent fill on the overlay, so the content stays readable underneath.
                fill = mark.get("color") or "#ffe066"
                draw.rectangle(box, fill=_rgba(fill, 90))
            elif kind in {"arrow", "line"}:
                start = _xy(mark.get("from"), "from")
                end = _xy(mark.get("to"), "to")
                draw.line([tuple(start), tuple(end)], fill=color, width=stroke)
                if kind == "arrow":
                    _arrow_head(draw, start, end, color, stroke)
            elif kind == "text":
                at = _xy(mark.get("at"), "at")
                text = str(mark.get("text") or "")
                if not text:
                    raise ValueError("a 'text' annotation needs a 'text' value")
                draw.text(tuple(at), text, fill=color, font=_font(int(mark.get("font_size") or 20)))
            else:
                raise ValueError(
                    f"unknown annotation type {kind!r}; expected box, arrow, line, text, highlight"
                )
            drawn += 1

        composed = module.alpha_composite(image, overlay)
        saved = _save(composed, destination)
        return {
            "path": display_path(destination, roots),
            "size": f"{saved['width']}x{saved['height']}",
            "bytes": saved["bytes"],
            "annotations_drawn": drawn,
        }

    @guard
    def combine_images(
        paths: list,
        output: str,
        layout: str = "horizontal",
        columns: int = 2,
        spacing: int = 10,
        background: str = "white",
    ) -> dict[str, Any]:
        module = require("PIL.Image", "Pillow", extra="office")
        if not isinstance(paths, list) or len(paths) < 2:
            raise ValueError("'paths' needs at least two images to combine")
        destination = resolve_write(output, roots)

        images = []
        for item in paths:
            source = resolve_read(str(item), roots)
            if not source.is_file():
                raise FileNotFoundError(display_path(source, roots))
            images.append(_open(module, source).convert("RGB"))

        gap = max(0, int(spacing))
        arrangement = str(layout or "horizontal").lower()
        if arrangement == "horizontal":
            cols, rows = len(images), 1
        elif arrangement == "vertical":
            cols, rows = 1, len(images)
        elif arrangement == "grid":
            cols = max(1, int(columns or 2))
            rows = (len(images) + cols - 1) // cols
        else:
            raise ValueError("layout must be 'horizontal', 'vertical', or 'grid'")

        cell_w = max(i.width for i in images)
        cell_h = max(i.height for i in images)
        total_w = cols * cell_w + (cols - 1) * gap
        total_h = rows * cell_h + (rows - 1) * gap
        _guard_size(total_w, total_h)

        canvas = module.new("RGB", (total_w, total_h), str(background or "white"))
        for index, image in enumerate(images):
            col, row = index % cols, index // cols
            # Centre each image in its cell so mixed sizes don't look ragged.
            x = col * (cell_w + gap) + (cell_w - image.width) // 2
            y = row * (cell_h + gap) + (cell_h - image.height) // 2
            canvas.paste(image, (x, y))

        saved = _save(canvas, destination)
        return {
            "path": display_path(destination, roots),
            "size": f"{saved['width']}x{saved['height']}",
            "bytes": saved["bytes"],
            "combined": len(images),
            "layout": arrangement,
        }

    return [
        decorate(read_image_info, name="read_image_info", schema=_INFO_SCHEMA),
        decorate(
            edit_image,
            name="edit_image",
            schema=_EDIT_SCHEMA,
            risk="medium",
            capabilities=["write"],
        ),
        decorate(
            annotate_image,
            name="annotate_image",
            schema=_ANNOTATE_SCHEMA,
            risk="medium",
            capabilities=["write"],
        ),
        decorate(
            combine_images,
            name="combine_images",
            schema=_COMPOSE_SCHEMA,
            risk="medium",
            capabilities=["write"],
        ),
    ]


def _rgba(color: Any, alpha: int) -> tuple:
    """Resolve a colour name/hex to RGBA with the given alpha."""
    from PIL import ImageColor

    try:
        r, g, b = ImageColor.getrgb(str(color))[:3]
    except ValueError:
        r, g, b = (255, 224, 102)
    return (r, g, b, max(0, min(alpha, 255)))


def _arrow_head(draw: Any, start: list, end: list, color: Any, stroke: int) -> None:
    """A filled triangle at `end`, pointing along start→end."""
    import math

    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    size = max(8, stroke * 4)
    # Base centre, then two points perpendicular to the direction of travel.
    bx, by = end[0] - ux * size, end[1] - uy * size
    px, py = -uy, ux
    draw.polygon(
        [
            (end[0], end[1]),
            (bx + px * size * 0.5, by + py * size * 0.5),
            (bx - px * size * 0.5, by - py * size * 0.5),
        ],
        fill=color,
    )
