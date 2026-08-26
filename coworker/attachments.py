"""Build OpenAI content-parts from a user message + attachments (images, PDFs, text files).

We pass messages straight to the OpenAI SDK, which accepts `content` as either a string or an
array of parts: `{"type": "text", ...}`, `{"type": "image_url", "image_url": {"url": ...}}`
(data: URLs work, and vision models read them), and `{"type": "file", "file": {"filename",
"file_data"}}` for PDFs. So image/PDF attachments are just parts appended to the user turn —
the Anthropic/Gemini providers convert them to their own block shapes.

`build_user_content` returns a plain string when there are no attachments (back-compat with the
text-only path), else the parts list.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any, Optional

MAX_ATTACHMENTS = 8
MAX_IMAGE_CHARS = 12_000_000  # data-URL length cap (~8–9 MB decoded); keeps a turn sane
MAX_PDF_CHARS = 15_000_000  # data-URL length cap (~10 MB decoded, the GUI's pick limit)
MAX_TEXT_CHARS = 200_000  # per text file, inlined
MAX_FILE_CHARS = 15_000_000  # kind="file" data-URL cap (same decoded budget as PDFs)


def _is_data_image(url: Any) -> bool:
    return isinstance(url, str) and url.startswith("data:image/") and ";base64," in url


def _is_data_pdf(url: Any) -> bool:
    return isinstance(url, str) and url.startswith("data:application/pdf;base64,")


def _save_file_attachment(a: dict, save_dir: Path) -> Optional[Path]:
    """Decode a kind="file" attachment into save_dir; None on any invalid input.
    The filename is flattened to its basename and sanitized, so a hostile name
    can't escape the attachments folder; collisions get a numeric suffix."""
    url = a.get("data_url") or ""
    if not isinstance(url, str) or ";base64," not in url or len(url) > MAX_FILE_CHARS:
        return None
    if not url.startswith("data:"):
        return None
    try:
        raw = base64.b64decode(url.split(";base64,", 1)[1], validate=True)
    except Exception:
        return None
    if not raw:
        return None
    name = Path(str(a.get("name") or "attachment")).name
    name = re.sub(r"[^\w.\- ()]", "_", name).strip() or "attachment"
    save_dir.mkdir(parents=True, exist_ok=True)
    target = save_dir / name
    stem, suffix = target.stem, target.suffix
    n = 1
    while target.exists():
        target = save_dir / f"{stem}-{n}{suffix}"
        n += 1
    target.write_bytes(raw)
    return target


def build_user_content(
    text: Optional[str],
    attachments: Optional[list[dict]] = None,
    *,
    save_dir: Optional[str | Path] = None,
) -> Any:
    """Return `str` (no attachments) or a list of OpenAI content-parts (with attachments).

    Each attachment is `{"kind": "image"|"pdf"|"text"|"file", "name"?, "data_url"?
    (image/pdf/file), "text"? (text)}`. kind="file" (Office documents and other
    binaries the model can't ingest as a content part) is saved into `save_dir` — the
    session's own folder, so the file is visible next to the user's documents rather
    than inside a hidden temp dir — and announced to the model as a path to open with
    the reading tools; without a `save_dir` (workspace-less sessions) it is skipped
    like any invalid attachment. An existing file is never overwritten: name
    collisions get a numeric suffix.
    Invalid/oversized attachments are skipped rather than failing the turn.
    """
    text = (text or "").strip()
    attachments = attachments or []
    if not attachments:
        return text

    parts: list[dict[str, Any]] = []
    if text:
        parts.append({"type": "text", "text": text})

    added = 0  # attachment parts that actually made it in
    for a in attachments[:MAX_ATTACHMENTS]:
        if not isinstance(a, dict):
            continue
        kind = a.get("kind")
        if kind == "image":
            url = a.get("data_url") or ""
            if _is_data_image(url) and len(url) <= MAX_IMAGE_CHARS:
                parts.append({"type": "image_url", "image_url": {"url": url}})
                added += 1
        elif kind == "pdf":
            url = a.get("data_url") or ""
            if _is_data_pdf(url) and len(url) <= MAX_PDF_CHARS:
                name = str(a.get("name") or "attachment.pdf")
                parts.append(
                    {"type": "file", "file": {"filename": name, "file_data": url}}
                )
                added += 1
        elif kind == "text":
            body = str(a.get("text") or "")[:MAX_TEXT_CHARS]
            name = str(a.get("name") or "attachment")
            if body:
                parts.append(
                    {"type": "text", "text": f"[Attached file: {name}]\n{body}"}
                )
                added += 1
        elif kind == "file" and save_dir is not None:
            saved = _save_file_attachment(a, Path(save_dir))
            if saved is not None:
                parts.append(
                    {
                        "type": "text",
                        "text": (
                            f"[Attached file: {saved.name} — saved to {saved}]\n"
                            "Open it with the appropriate reading tool (Word/Excel/"
                            "PowerPoint readers, or the file tools) before answering."
                        ),
                    }
                )
                added += 1

    if added == 0:
        return text  # every attachment was invalid/empty → just the text (possibly "")
    return parts


def content_to_text(content: Any, *, image_placeholder: str = "[image]") -> str:
    """Flatten message content (string or parts) to text — for titles, previews, search.
    Images render as `image_placeholder` (pass "" to drop them, e.g. for clean titles).
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                out.append(str(part.get("text", "")))
            elif part.get("type") == "image_url" and image_placeholder:
                out.append(image_placeholder)
            elif part.get("type") == "file" and image_placeholder:
                out.append("[pdf]")
        return " ".join(out).strip()
    return ""
