"""Find photographs free of copyright for slides and save a chosen one with its credit.

Two libraries are searched. Openverse is asked for photographs marked CC0 or public domain,
which is where stock photography of ordinary subjects lives (a meeting, a classroom, a
desk). Wikimedia Commons, under the same two marks, follows: it is strong on named places,
objects and history and weak on everyday scenes, where it answered "remote team meeting"
with a FEMA rescue briefing (real decks, 2026-11-19).
"""

from __future__ import annotations

import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from io import BytesIO
from pathlib import Path

import httpx

from ...web import guard
from ._common import decorate, require
from ._common import guard as reports
from .paths import context_roots, resolve_write

_HEADERS = {"User-Agent": "MimiWork/0.6 (https://github.com/lanceyuu/mimiwork)"}
_LIMIT = 20 * 1024 * 1024
_FORMATS = {"image/jpeg": ".jpg", "image/png": ".png"}
_OPENVERSE = "https://api.openverse.org/v1/images/"
_COMMONS = "https://commons.wikimedia.org/w/api.php"
_RIGHTS = {"cc0": "CC0", "pdm": "Public domain"}
# Narrower than this and a photograph is soft even on half a slide.
_MIN_WIDTH = 900
_THUMB_HOSTS = ("https://api.openverse.org/", "https://upload.wikimedia.org/", "https://thumb.wikimedia.org/")


def _stock(query: str):
    """Photographs marked CC0 or public domain in Openverse's index."""
    response = httpx.get(
        _OPENVERSE,
        params={
            "q": query[:200],
            "license": "cc0,pdm",
            "category": "photograph",
            "aspect_ratio": "wide",
            "size": "large",
            "page_size": 20,
            "mature": "false",
        },
        headers=_HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    for item in response.json().get("results", []):
        # The search is filtered already; a result is still taken on its own marks, not the query's.
        rights = _RIGHTS.get(str(item.get("license") or "").lower())
        url, landing = str(item.get("url") or ""), str(item.get("foreign_landing_url") or "")
        extension = {"jpg": ".jpg", "jpeg": ".jpg", "png": ".png"}.get(str(item.get("filetype") or "").lower())
        if not rights or not extension or not url.startswith("https://") or not landing.startswith("https://"):
            continue
        yield {
            "title": str(item.get("title") or "Untitled")[:200],
            "creator": str(item.get("creator") or "")[:500],
            "source": landing,
            "rights": rights,
            "license_url": item.get("license_url") or landing,
            "width": item.get("width") or 0,
            "height": item.get("height") or 0,
            "extension": extension,
            "original": url,
            "collection": str(item.get("source") or "openverse"),
            "thumbnail": str(item.get("thumbnail") or ""),
        }


def _candidates(pages):
    for page in sorted(pages, key=lambda p: p.get("index", 999)):
        info = next(iter(page.get("imageinfo", [])), {})
        meta = info.get("extmetadata", {})
        rights = meta.get("LicenseShortName", {}).get("value", "")
        if rights.lower() not in {"cc0", "public domain", "cc0 1.0"}:
            continue
        mime, url = info.get("mime"), info.get("url", "")
        if mime not in _FORMATS or not url.startswith("https://upload.wikimedia.org/"):
            continue
        width, height = info.get("width", 0), info.get("height", 0)
        if min(width, height) < 720 or max(width, height) < 1280 or width * height > 80_000_000:
            continue
        if not 0 < info.get("size", 0) <= _LIMIT or not info.get("descriptionurl"):
            continue
        author = meta.get("Artist", {}).get("value", "")
        yield {
            "title": page["title"],
            "creator": unescape(re.sub("<[^>]*>", "", author))[:500],
            "source": info["descriptionurl"],
            "rights": rights,
            "license_url": meta.get("LicenseUrl", {}).get("value")
            or info["descriptionurl"] + "#Licensing",
            "width": width,
            "height": height,
            "extension": _FORMATS[mime],
            "original": url,
            "collection": "wikimedia",
            "thumbnail": info.get("thumburl", ""),
        }


def _commons(query: str) -> list:
    params = {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "generator": "search",
        "gsrnamespace": 6,
        "gsrlimit": 35,
        "gsrsearch": query[:250] + " filetype:bitmap haslicense:unrestricted",
        "prop": "imageinfo",
        "iiprop": "url|size|mime|extmetadata",
        "iiurlwidth": 640,
        "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl",
    }
    response = httpx.get(_COMMONS, params=params, headers=_HEADERS, timeout=20)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        raise ValueError(data["error"].get("info", "Commons search failed."))
    return list(_candidates(data.get("query", {}).get("pages", [])))


def _shorter(query: str) -> list[str]:
    """A subject of many words finds nothing in a stock library ("remote team video
    meeting": 0, "team meeting": 139), so it is asked again as its last two words, then
    its first two."""
    words = query.split()
    if len(words) <= 2:
        return []
    return list(dict.fromkeys([" ".join(words[-2:]), " ".join(words[:2])]))


def _thumbnail(url: str):
    if not url.startswith(_THUMB_HOSTS):
        return None
    try:
        response = httpx.get(url, headers=_HEADERS, timeout=10, follow_redirects=False)
        response.raise_for_status()
        picture = require("PIL.Image", "Pillow").open(BytesIO(response.content))
        picture.load()
        return picture.convert("RGB")
    except Exception:
        return None  # a candidate without a preview is still listed by its title


def _sheet(photos: list[dict]) -> str:
    """The candidates on one picture, each under its number, so a photograph is chosen by
    how it looks and not by its title. Empty when no preview could be fetched."""
    with ThreadPoolExecutor(max_workers=6) as pool:
        previews = list(pool.map(_thumbnail, [p.get("thumbnail", "") for p in photos]))
    if not any(previews):
        return ""
    image = require("PIL.Image", "Pillow")
    draw_module = require("PIL.ImageDraw", "Pillow")
    tile_w, tile_h, band, across = 320, 200, 26, 5
    down = -(-len(photos) // across)
    sheet = image.new("RGB", (across * tile_w, down * (tile_h + band)), "#FFFFFF")
    draw = draw_module.Draw(sheet)
    for index, (photo, preview) in enumerate(zip(photos, previews)):
        x, y = (index % across) * tile_w, (index // across) * (tile_h + band)
        draw.text((x + 6, y + 6), f"{photo['id']}  {photo['collection']}", fill="#111111")
        if preview is not None:
            preview.thumbnail((tile_w - 8, tile_h - 8))
            sheet.paste(preview, (x + 4, y + band + 4))
    folder = Path(tempfile.gettempdir()) / "mimiwork-slide-pictures"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "photo-candidates.jpg"
    sheet.save(target, "JPEG", quality=80)
    return str(target)


def _fetch_original(url: str) -> bytes:
    """A stock photograph from the host its library names. That host is whatever the
    catalogue says, so every hop is checked like a link the model chose."""
    with httpx.Client(follow_redirects=False, timeout=30, headers=_HEADERS) as client:
        response = guard.get_checked(client, url)
    response.raise_for_status()
    # ponytail: read whole, then measured; stream with a running count if a library is ever
    # seen to serve files far past the limit.
    if len(response.content) > _LIMIT:
        raise ValueError("The original exceeds 20 MB. Select another photograph.")
    return response.content


def slide_photo_tools(context):
    roots = context_roots(context)
    found = {}

    @reports
    def search_slide_photos(query: str) -> dict:
        """Search for slide photographs that are free of copyright (CC0 or public domain): stock photography first, then Wikimedia Commons. Name the subject in one to three words, such as 'team meeting' or 'heat pump'. A picture of the candidates follows with a number on each: choose by look, then save the chosen ID using save_slide_photo."""
        query = " ".join((query or "").split())
        if not query:
            raise ValueError("Describe the subject of the photograph.")
        stock, used = [], query
        try:
            for attempt in [query, *_shorter(query)]:
                stock = list(_stock(attempt))[:6]
                if stock:
                    used = attempt
                    break
        except (httpx.HTTPError, ValueError):
            stock = []  # turned away or over its daily allowance: Commons still answers
        try:
            older, failure = _commons(query), None
        except (httpx.HTTPError, ValueError) as exc:
            older, failure = [], exc
        photos = [*stock, *older][:10]
        if not photos:
            if failure is not None and not stock:
                return {"error": f"Photo search unavailable: {failure}. Try another open image collection."}
            return {"photos": [], "note": "Try a shorter subject or another open collection."}
        listed = []
        for photo in photos:
            number = len(found) + 1
            found[number] = photo
            listed.append({"id": number, **{k: v for k, v in photo.items() if k not in ("original", "thumbnail")}})
        result: dict = {"photos": listed}
        if used != query:
            result["searched_for"] = used
        sheet = _sheet([{**p, "thumbnail": found[p["id"]]["thumbnail"]} for p in listed])
        if sheet:
            result["_images"] = [sheet]
            result["sheet"] = (
                "The picture that follows shows these candidates, each under its number. "
                "Choose by look: a clear subject that fits the slide, natural light, room for a title."
            )
        return result

    @reports
    def save_slide_photo(id: int, output: str) -> dict:
        """Save a photo from search_slide_photos by its ID, using its listed extension and a new workspace filename. Returns the actual dimensions and a credit line for the slide notes and the credits slide."""
        photo = found.get(id)
        if not photo:
            raise ValueError("Search for the photo first and use an ID from those results.")
        path = resolve_write(output, roots)
        if path.suffix.lower() != photo["extension"]:
            raise ValueError(f"Use the original extension {photo['extension']}.")
        stock = photo["collection"] != "wikimedia"
        try:
            if stock:
                raw = _fetch_original(photo["original"])
            else:
                # Only the fixed Commons upload host is allowed here. Never follow a redirect.
                with httpx.stream(
                    "GET", photo["original"], headers=_HEADERS, timeout=30, follow_redirects=False
                ) as r:
                    r.raise_for_status()
                    raw = bytearray()
                    for chunk in r.iter_bytes(64 * 1024):
                        if len(raw) + len(chunk) > _LIMIT:
                            raise ValueError("The original exceeds 20 MB. Select another photograph.")
                        raw.extend(chunk)
        except (httpx.HTTPError, PermissionError, RuntimeError) as exc:
            return {"error": f"Photo download failed: {exc}. Choose another candidate."}
        img = require("PIL.Image", "Pillow")
        with img.open(BytesIO(raw)) as im:
            if im.format != ("JPEG" if photo["extension"] == ".jpg" else "PNG"):
                raise ValueError("The downloaded image does not match its record.")
            size = im.size
            # A stock library lists the size of its original and serves a smaller copy, so
            # what arrived is measured. Commons serves the original, which must match.
            if stock and size[0] < _MIN_WIDTH:
                raise ValueError(f"This copy is too small for a slide ({size[0]} pixels wide). Choose another candidate.")
            if not stock and size != (photo["width"], photo["height"]):
                raise ValueError("The downloaded image does not match its Commons record.")
            im.verify()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as f:
            f.write(raw)
        credit = ", ".join(part for part in (
            f"{photo['title']} by {photo['creator']}" if photo["creator"] else photo["title"],
            photo["rights"], photo["source"],
        ) if part)
        saved = {k: v for k, v in photo.items() if k not in ("original", "thumbnail")}
        return {**saved, "id": id, "width": size[0], "height": size[1], "credit": credit,
                "path": str(path), "_images": [str(path)]}

    def register(fn, properties, **kwargs):
        schema = {
            "type": "function",
            "function": {
                "name": fn.__wrapped__.__name__,
                "description": fn.__wrapped__.__doc__,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                },
            },
        }
        return decorate(fn, name=schema["function"]["name"], schema=schema, **kwargs)

    return [
        register(search_slide_photos, {"query": {"type": "string"}}),
        register(
            save_slide_photo,
            {"id": {"type": "integer"}, "output": {"type": "string"}},
            risk="medium",
            capabilities=["write"],
        ),
    ]
