"""Drawing a picture from a description.

The models that answer a conversation read images; none of them makes one. The QualiTaTi
gateway does (`POST /api/llm/v1/images/generations`, one image slot per region and tier),
so this tool is a thin client of it: the description goes out with the tier of the model
answering the turn, and the picture comes back as bytes and is saved into the session's
folder like any other deliverable.

Two rules shape it.

*Refuse before asking.* A picture costs one of the day's free images, or credits. Every
reason not to save it — a file already there, a place outside the granted folders, a
description the content rules forbid — is checked before the gateway is called, so nothing
is spent on a picture that cannot be kept.

*Say what it cost.* The gateway reports the charge in its response headers; the result
carries it, because the user is the one paying.
"""

from __future__ import annotations

import base64
import binascii
import io
from typing import Any

import httpx

from ..content_policy import REFUSAL, prohibited_request
from ..qualitati import MIMI_TIERS, SITES, site_credentials, site_for_model, tool_site
from .context import tool_model
from .office._common import decorate, guard, require
from .office.image_tools import _save
from .office.paths import context_roots, display_path, resolve_write

# The three sizes the gateway takes, under names a request can be matched to.
_SHAPES = {"square": "1024x1024", "landscape": "1536x1024", "portrait": "1024x1536"}
_QUALITIES = ("low", "medium", "high")
_TYPES = (".png", ".jpg", ".jpeg", ".webp")
_FREE_TIER = MIMI_TIERS[0]
_MAX_PROMPT_CHARS = 8000  # the gateway's own limit
_TIMEOUT = 150.0  # the gateway gives the provider 120 s; outlast it to hear its answer

_SIGNED_OUT = (
    "Not signed in to QualiTaTi, which draws the pictures. Open Settings ▸ Models and "
    "sign in with the QualiTaTi account, then try again."
)
_KEY_REFUSED = (
    "QualiTaTi no longer accepts this app's sign-in. Open Settings ▸ Models and sign in "
    "again, then try again."
)
_TOO_OLD = "This QualiTaTi server cannot draw pictures yet."

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "generate_image",
        "description": (
            "Draw a new picture from a description and save it into the session's folder: "
            "a photograph-style product shot, a study stimulus, an illustration for a deck. "
            "Describe the subject, setting, light and style in plain sentences; say so "
            "when the picture must contain no text or logos. One picture per call. Each "
            "one uses the user's daily free images or their credits, so draw what was "
            "asked for rather than several variants. To change a picture that already "
            "exists, use `edit_image`, `annotate_image` or `combine_images` instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "What the picture shows."},
                "output": {
                    "type": "string",
                    "description": "Where to save it, e.g. 'figures/dog-ad.png'. PNG, JPEG or WebP.",
                },
                "shape": {"type": "string", "enum": list(_SHAPES), "description": "Default square."},
                "quality": {
                    "type": "string",
                    "enum": list(_QUALITIES),
                    "description": "Default medium. The free tiers draw at medium at most.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Replace a file already at `output`. Default false.",
                },
            },
            "required": ["prompt", "output"],
        },
    },
}


def _tier() -> str:
    """The Mimi tier that pays: the one answering the turn, else the free one."""
    model = str(tool_model.get() or "")
    name = model.split(":", 1)[-1]
    return name if site_for_model(model) and name in MIMI_TIERS else _FREE_TIER


def _refusal(reply: Any) -> str:
    """Why the gateway did not draw, in its own words where it has any."""
    if reply.status_code in (401, 403):
        return _KEY_REFUSED
    try:
        detail = reply.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    if reply.status_code == 404 and detail == "Not Found":
        return _TOO_OLD
    said = detail.get("message") if isinstance(detail, dict) else detail
    said = str(said or f"the server answered {reply.status_code}")[:400]
    return f"QualiTaTi did not draw the picture: {said}"


def _count(headers: Any, name: str) -> Any:
    try:
        return int(headers.get(name))
    except (TypeError, ValueError):
        return None


def image_generation_tools(secrets: Any, context: Any) -> list:
    """`generate_image`, or nothing while no QualiTaTi account can pay for a picture —
    an unusable tool in the catalog is a lie to the model."""
    if not any(site_credentials(secrets, site)["api_key"] for site in SITES):
        return []
    roots = context_roots(context)

    @guard
    def generate_image(
        prompt: str,
        output: str,
        shape: str = "square",
        quality: str = "medium",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        prompt = str(prompt or "").strip()
        if not prompt:
            raise ValueError("'prompt' must describe the picture")
        if len(prompt) > _MAX_PROMPT_CHARS:
            raise ValueError(f"'prompt' is limited to {_MAX_PROMPT_CHARS} characters")
        if prohibited_request(prompt):
            return {"error": REFUSAL}

        destination = resolve_write(output, roots)
        if not destination.suffix:
            destination = destination.with_suffix(".png")
        if destination.suffix.lower() not in _TYPES:
            raise ValueError(f"'output' must end in one of {', '.join(_TYPES)}")
        if destination.exists() and not overwrite:
            return {
                "error": (
                    f"{display_path(destination, roots)} already exists. Save under another "
                    "name, or pass overwrite=true if the user asked to replace it."
                )
            }
        module = require("PIL.Image", "Pillow", extra="office")

        creds = site_credentials(secrets, tool_site(secrets))
        if not creds["api_key"]:
            return {"error": _SIGNED_OUT}
        tier = _tier()
        try:
            reply = httpx.post(
                f"{creds['base']}/api/llm/v1/images/generations",
                headers={"Authorization": f"Bearer {creds['api_key']}"},
                json={
                    "model": tier,
                    "prompt": prompt,
                    "size": _SHAPES.get(str(shape).lower(), _SHAPES["square"]),
                    "quality": quality if quality in _QUALITIES else "medium",
                    "n": 1,
                },
                timeout=_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            return {"error": f"QualiTaTi could not be reached ({type(exc).__name__}). Nothing was drawn or charged."}
        if reply.status_code != 200:
            return {"error": _refusal(reply)}

        try:
            raw = base64.b64decode(reply.json()["data"][0]["b64_json"], validate=True)
            picture = module.open(io.BytesIO(raw))
            picture.load()
        except (KeyError, IndexError, TypeError, ValueError, binascii.Error, OSError):
            return {"error": "QualiTaTi answered, but not with a picture that can be opened. Nothing was saved."}
        saved = _save(picture, destination)

        result: dict[str, Any] = {
            "path": display_path(destination, roots),
            "size": f"{saved['width']}x{saved['height']}",
            "bytes": saved["bytes"],
            "drawn_by": tier,
            "credits_charged": _count(reply.headers, "X-Credits-Charged") or 0,
        }
        for key, header in (
            ("free_images_left_today", "X-Free-Images-Remaining"),
            ("credits_left", "X-Credits-Remaining"),
        ):
            left = _count(reply.headers, header)
            if left is not None:
                result[key] = left
        return result

    return [
        decorate(
            generate_image,
            name="generate_image",
            schema=_SCHEMA,
            risk="medium",
            capabilities=["write"],
        )
    ]
