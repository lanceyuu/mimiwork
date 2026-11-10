"""Prepare one email for the screen: its HTML, its text, and its attachment list.

Nothing here tries to make the HTML safe. An email is untrusted and stays untrusted;
confining it is the reader's job (`disarm.ts` and the sandboxed frame), where the
browser's own parser does the work. This only chooses the parts to show and brings the
email's own inline images along, so the reader need not load anything.

An attached email (a forward, a bounce's original) is one attachment. Its insides are
never walked: not for the body, not for the text, not for the attachment list.
"""

from __future__ import annotations

import base64
import email as email_lib
import mimetypes
import re
from html import escape
from typing import Any, Iterator
from urllib.parse import unquote

from ..connectors.email_tools import (
    _BODY_CHAR_LIMIT,
    _decode_payload,
    _strip_html,
    decode_mime_header,
)

Message = email_lib.message.Message

# All of one message's inline images together. Past this they are left out, so a single
# email cannot make the cache or the page enormous.
_INLINE_LIMIT = 5 * 1024 * 1024
# Only where an image's address goes. The letters "cid:" also turn up in ordinary text
# and inside other addresses, and those must be left as they are.
_CID_SRC = re.compile(r"(\bsrc\s*=\s*[\"']?)cid:([^\"'\s>]+)", re.IGNORECASE)
_PLAIN_STYLE = "white-space:pre-wrap;font:14px/1.5 system-ui,sans-serif;margin:0"


def _whole(msg: Message) -> Message:
    """The email to show. One that is nothing but a forwarded email is shown as that
    email; `render_message` and `attachments` both start here, so they always agree."""
    if msg.get_content_type() == "message/rfc822" and msg.is_multipart():
        return msg.get_payload(0)
    return msg


def _is_attachment(part: Message) -> bool:
    """Every part is one of three things: the sender's words, a picture placed inside
    them, or a file that came with them. This is the third, so nothing in an email is
    ever neither shown nor listed."""
    if part.get_content_maintype() == "message":
        return True
    if part.is_multipart():
        return False
    if part.get_content_disposition() == "attachment":
        return True
    if part.get_content_type() in ("text/html", "text/plain"):
        return False
    return not (part.get_content_maintype() == "image" and part.get("Content-ID"))


def _own_parts(msg: Message) -> Iterator[Message]:
    """The message's own leaf parts, with an attached email counting as one leaf."""
    if msg.is_multipart() and msg.get_content_maintype() != "message":
        for part in msg.get_payload():
            yield from _own_parts(part)
    else:
        yield msg


def _body_parts(msg: Message, prefer: str) -> list[Message]:
    """What the sender wrote, in order: every text part that is not an attachment. Where
    the email offers the same thing two ways (`multipart/alternative`), the `prefer` kind."""
    if _is_attachment(msg):
        return []
    if not msg.is_multipart():
        return [msg] if msg.get_content_type() in ("text/html", "text/plain") else []
    children = msg.get_payload()
    if msg.get_content_subtype() == "alternative":
        other = "text/plain" if prefer == "text/html" else "text/html"
        for kind in (prefer, other):
            for child in reversed(children):  # the richest version comes last
                found = _body_parts(child, prefer)
                if any(part.get_content_type() == kind for part in found):
                    return found
        return []
    # Mixed, related, signed: everything in turn. A mail app that puts an attachment in
    # the middle of the text sends the text as two parts, and both are the message.
    return [part for child in children for part in _body_parts(child, prefer)]


def attachments(msg: Message) -> list[tuple[str, Message]]:
    """(name, part) for each attachment, in order. `render_message` lists them and
    `MailService.save_attachment` saves by place in this same list."""
    out = []
    for part in _own_parts(_whole(msg)):
        if not _is_attachment(part):
            continue
        name = decode_mime_header(part.get_filename() or "")
        if not name and part.get_content_type() == "message/rfc822" and part.is_multipart():
            # A bounce carries the original with no file name; name it after its subject.
            subject = decode_mime_header(part.get_payload(0).get("Subject", "")).strip()
            name = f"{subject or 'Attached message'}.eml"
        if not name:
            name = "attachment" + (mimetypes.guess_extension(part.get_content_type()) or "")
        out.append((name, part))
    return out


def attachment_bytes(part: Message) -> bytes:
    """An attachment's content. An attached email is a message inside a part, not a payload."""
    if part.get_content_maintype() == "message" and part.is_multipart():
        return part.get_payload(0).as_bytes()
    return part.get_payload(decode=True) or b""


def render_message(msg: Message) -> dict[str, Any]:
    msg = _whole(msg)
    inline = {
        str(part.get("Content-ID", "")).strip("<> "): part
        for part in _own_parts(msg)
        if part.get("Content-ID") and part.get_content_maintype() == "image" and not _is_attachment(part)
    }
    left = _INLINE_LIMIT

    def embed(match: re.Match) -> str:
        nonlocal left
        part = inline.get(unquote(match.group(2)))
        payload = (part.get_payload(decode=True) or b"") if part is not None else b""
        if not payload or len(payload) > left:
            return match.group(1)
        left -= len(payload)
        data = base64.b64encode(payload).decode()
        return f"{match.group(1)}data:{part.get_content_type()};base64,{data}"

    shown = []
    for part in _body_parts(msg, "text/html"):
        if part.get_content_type() == "text/html":
            shown.append(_CID_SRC.sub(embed, _decode_payload(part)))
        else:
            # Plain text has no look of its own, so it gets the app's plain one.
            shown.append(f'<pre style="{_PLAIN_STYLE}">{escape(_decode_payload(part))}</pre>')

    words = [
        _decode_payload(part) if part.get_content_type() == "text/plain" else _strip_html(_decode_payload(part))
        for part in _body_parts(msg, "text/plain")
    ]
    text = "\n\n".join(piece.strip() for piece in words if piece.strip())
    if len(text) > _BODY_CHAR_LIMIT:
        text = text[:_BODY_CHAR_LIMIT] + "\n…[truncated]"

    return {
        "html": "\n".join(shown),
        "text": text,
        "attachments": [
            {"filename": name, "content_type": part.get_content_type(), "size": len(attachment_bytes(part))}
            for name, part in attachments(msg)
        ],
    }
