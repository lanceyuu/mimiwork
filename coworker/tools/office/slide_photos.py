"""Find reusable Commons photographs and save a selected original with its provenance."""

from __future__ import annotations

import re
from html import unescape
from io import BytesIO

import httpx

from ._common import decorate, guard, require
from .paths import context_roots, resolve_write

_HEADERS = {"User-Agent": "MimiWork/0.6 (https://github.com/lanceyuu/mimiwork)"}
_LIMIT = 20 * 1024 * 1024
_FORMATS = {"image/jpeg": ".jpg", "image/png": ".png"}


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
            "id": page["pageid"],
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
        }


def slide_photo_tools(context):
    roots = context_roots(context)
    found = {}

    @guard
    def search_slide_photos(query: str) -> dict:
        """Search Wikimedia Commons for high-resolution CC0 or public-domain slide photos. Choose by subject, rights and crop; save the chosen ID using save_slide_photo."""
        if not query.strip():
            raise ValueError("Describe the subject of the photograph.")
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
            "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl",
        }
        try:
            response = httpx.get(
                "https://commons.wikimedia.org/w/api.php",
                params=params,
                headers=_HEADERS,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                raise ValueError(data["error"].get("info", "Commons search failed."))
        except httpx.HTTPError as exc:
            return {
                "error": f"Commons search unavailable: {exc}. Try another open image collection."
            }
        photos = list(_candidates(data.get("query", {}).get("pages", [])))[:10]
        found.update({p["id"]: p for p in photos})
        return (
            {"photos": photos}
            if photos
            else {"photos": [], "note": "Try a shorter subject or another open collection."}
        )

    @guard
    def save_slide_photo(id: int, output: str) -> dict:
        """Save a photo from search_slide_photos by its ID, using its listed extension and a new workspace filename. Returns the actual dimensions and the attribution for the slide notes."""
        photo = found.get(id)
        if not photo:
            raise ValueError("Search for the photo first and use an ID from those results.")
        path = resolve_write(output, roots)
        if path.suffix.lower() != photo["extension"]:
            raise ValueError(f"Use the original extension {photo['extension']}.")
        try:
            # Only the fixed Commons upload host above is allowed. Never follow a redirect.
            with httpx.stream(
                "GET", photo["original"], headers=_HEADERS, timeout=30, follow_redirects=False
            ) as r:
                r.raise_for_status()
                raw = bytearray()
                for chunk in r.iter_bytes(64 * 1024):
                    if len(raw) + len(chunk) > _LIMIT:
                        raise ValueError("The original exceeds 20 MB. Select another photograph.")
                    raw.extend(chunk)
        except httpx.HTTPError as exc:
            return {"error": f"Photo download failed: {exc}. Choose another candidate."}
        img = require("PIL.Image", "Pillow")
        with img.open(BytesIO(raw)) as im:
            if im.format != ("JPEG" if photo["extension"] == ".jpg" else "PNG") or im.size != (
                photo["width"],
                photo["height"],
            ):
                raise ValueError("The downloaded image does not match its Commons record.")
            im.verify()
        with path.open("xb") as f:
            f.write(raw)
        return {**photo, "path": str(path)}

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
