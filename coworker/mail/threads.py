"""Which conversation a message belongs to: a pure function of its headers."""

from __future__ import annotations

import hashlib
import re
from typing import Any

_ID = re.compile(r"<[^<>\s]+>")


def _first_id(value: Any) -> str:
    text = " ".join(str(value or "").split())
    found = _ID.search(text)
    return found.group(0) if found else text


def thread_key(headers: Any, *, account: str = "", folder: str = "", uid: int = 0) -> str:
    """The conversation's key: 16 hex characters, the same for every message in it.

    The root is the first id in References, else In-Reply-To, else the message's own id,
    else a made-up one. It is hashed because a Message-ID can hold any character,
    including "/", and the key travels in URLs.
    """
    # ponytail: References root only; no subject matching.
    # Add a subject fallback if split threads are seen in real mailboxes.
    root = (
        _first_id(headers.get("References"))
        or _first_id(headers.get("In-Reply-To"))
        or _first_id(headers.get("Message-ID"))
        or f"{account}/{folder}/{uid}"
    )
    return hashlib.sha256(root.encode("utf-8", "replace")).hexdigest()[:16]
