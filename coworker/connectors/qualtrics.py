"""Qualtrics helpers — pure functions shared by the descriptor and the tools.

No network and no secrets live here, so `descriptors.py` (which validates a pasted token)
and `integration_tools.py` (which runs the tools) can agree on the same base URL and the
same payload shapes without importing each other.

Two things are worth knowing about the Qualtrics API before reading the rest:

* **The datacenter is part of the host.** Every account lives at
  `https://{datacenter}.qualtrics.com/API/v3` (`fra1`, `iad1`, `syd1`, …). The API token
  rides in an `X-API-TOKEN` header on every call, so `base_url` refuses to build a URL for
  anything that isn't a qualtrics.com host — a typo must not hand someone's token to a
  stranger.
* **Responses come out asynchronously.** Export is start → poll → download a zip; the
  unzipping happens here (`unpack`), with archive members reduced to their basename so a
  zip can never choose a path on this disk.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePosixPath
from typing import Any, Callable, Optional
from urllib.parse import urlsplit

API = "/API/v3"

#: Formats the export tool accepts, mapped to the suffix the saved file should carry.
#: `spss` is a real `.sav` — variable and value labels intact, which is the whole point
#: of handing it to the analysis tools rather than a bare CSV.
EXPORT_SUFFIX = {
    "csv": ".csv",
    "tsv": ".tsv",
    "spss": ".sav",
    "json": ".json",
    "ndjson": ".ndjson",
}
EXPORT_FORMATS = tuple(EXPORT_SUFFIX)

_MAX_QUESTIONS = 150
_MAX_COLUMNS = 400
_MAX_CHOICES = 15
_MAX_MEMBER_BYTES = 512 * 1024 * 1024  # a survey export, not an archive dump
_TAG = re.compile(r"<[^>]+>")
_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?")


def base_url(value: str) -> str:
    """`fra1` → `https://fra1.qualtrics.com`. A pasted host or full URL works too.

    Returns "" for anything outside qualtrics.com: the caller turns that into "check the
    datacenter ID" rather than sending the token somewhere unintended.
    """
    raw = (value or "").strip().rstrip("/")
    if not raw:
        return ""
    if "://" in raw:
        host = urlsplit(raw).netloc
    elif "." in raw or "/" in raw:
        host = raw.split("/")[0]
    else:
        host = f"{raw}.qualtrics.com"
    host = host.split("@")[-1].split(":")[0].strip().lower()
    if not host or not (host == "qualtrics.com" or host.endswith(".qualtrics.com")):
        return ""
    # Every label must be a real DNS label: "fra 1!" ends in .qualtrics.com too, and
    # would otherwise become a URL that fails later as an unreadable DNS error instead
    # of "check the datacenter ID".
    if not all(_LABEL.fullmatch(label) for label in host.split(".")):
        return ""
    return f"https://{host}"


def api(value: str, path: str = "") -> str:
    """Full API URL for a datacenter/base and an `/API/v3`-relative path ("" for none)."""
    base = base_url(value)
    return f"{base}{API}{path}" if base else ""


def same_host(url: str, value: str) -> bool:
    """True when a URL the API handed back (`nextPage`) still points at our own host."""
    base = base_url(value)
    return bool(base) and url.startswith(base + "/")


def _plain(text: Any, clean: Optional[Callable[[str], str]] = None) -> str:
    """Question text arrives as HTML. Flatten it to one readable line."""
    raw = str(text or "")
    flat = clean(raw) if clean else _TAG.sub(" ", raw)
    return re.sub(r"\s+", " ", flat).strip()


def _values(node: Any) -> list[tuple[str, dict]]:
    if isinstance(node, dict):
        return [(str(k), v) for k, v in node.items() if isinstance(v, dict)]
    if isinstance(node, list):
        return [(str(i), v) for i, v in enumerate(node) if isinstance(v, dict)]
    return []


def _label(entry: dict, clean: Optional[Callable[[str], str]]) -> str:
    for key in ("choiceText", "description", "text", "recode"):
        if entry.get(key):
            return _plain(entry[key], clean)[:200]
    return ""


def export_body(
    fmt: str,
    *,
    use_labels: bool = True,
    start_date: str = "",
    end_date: str = "",
    limit: int = 0,
) -> dict[str, Any]:
    """The POST body for starting an export. `useLabels` gives "Strongly agree" instead
    of `5` — the readable default for anyone reading the file, and switchable for anyone
    who wants to run the numbers."""
    body: dict[str, Any] = {"format": fmt, "useLabels": bool(use_labels)}
    if start_date:
        body["startDate"] = start_date
    if end_date:
        body["endDate"] = end_date
    if limit and int(limit) > 0:
        body["limit"] = int(limit)
    return body


def summarize_survey(
    result: dict[str, Any], clean: Optional[Callable[[str], str]] = None
) -> dict[str, Any]:
    """A survey's questionnaire, small enough to put in a turn.

    The raw payload carries the flow, the blocks and every piece of display logic — tens
    of thousands of tokens for a long survey. What a reader actually needs is what each
    question asks and which column in the export it becomes, which is what this returns.
    """
    raw_questions = result.get("questions") or {}
    pairs = _values(raw_questions)
    truncated = len(pairs) > _MAX_QUESTIONS

    questions: list[dict[str, Any]] = []
    text_by_qid: dict[str, str] = {}
    sub_by_qid: dict[str, dict[str, str]] = {}
    for qid, q in pairs[:_MAX_QUESTIONS]:
        qtype = q.get("questionType") or {}
        kind = " / ".join(str(qtype.get(k)) for k in ("type", "selector") if qtype.get(k))
        text = _plain(q.get("questionText"), clean)[:400]
        choices = [_label(c, clean) for _, c in _values(q.get("choices"))]
        subs = {k: _label(s, clean) for k, s in _values(q.get("subQuestions"))}
        text_by_qid[qid] = text
        if subs:
            sub_by_qid[qid] = subs
        entry: dict[str, Any] = {
            "qid": qid,
            "name": str(q.get("questionName") or q.get("questionLabel") or ""),
            "text": text,
            "type": kind,
        }
        if choices:
            entry["choices"] = [c for c in choices[:_MAX_CHOICES] if c]
            if len(choices) > _MAX_CHOICES:
                entry["choices_total"] = len(choices)
        if subs:
            picked = [s for s in list(subs.values())[:_MAX_CHOICES] if s]
            entry["sub_questions"] = picked
            if len(subs) > _MAX_CHOICES:
                entry["sub_questions_total"] = len(subs)
        questions.append(entry)

    columns, columns_truncated = codebook(result, text_by_qid, sub_by_qid, clean)
    summary: dict[str, Any] = {
        "survey_id": result.get("id") or "",
        "name": result.get("name") or "",
        "is_active": bool(result.get("isActive")),
        "last_modified": result.get("lastModifiedDate") or result.get("lastModified") or "",
        "response_counts": result.get("responseCounts") or {},
        "question_count": len(pairs),
        "questions": questions,
    }
    if truncated:
        summary["questions_truncated"] = True
    if columns:
        summary["columns"] = columns
        if columns_truncated:
            summary["columns_truncated"] = True
    return summary


def codebook(
    result: dict[str, Any],
    text_by_qid: dict[str, str],
    sub_by_qid: dict[str, dict[str, str]],
    clean: Optional[Callable[[str], str]] = None,
) -> tuple[dict[str, str], bool]:
    """Export column → what that column actually asks.

    This is the Qualtrics equivalent of an SPSS variable label: without it `Q4_1` is a
    column of numbers nobody can interpret, and a summary written from it is guesswork.
    """
    mapping = result.get("exportColumnMap")
    if not isinstance(mapping, dict):
        return {}, False
    out: dict[str, str] = {}
    truncated = False
    for column, spec in mapping.items():
        if len(out) >= _MAX_COLUMNS:
            truncated = True
            break
        if not isinstance(spec, dict):
            continue
        qid = str(spec.get("question") or "")
        text = text_by_qid.get(qid)
        if not text:
            continue  # metadata columns (StartDate, Finished…) describe themselves
        sub_key = str(spec.get("subQuestion") or "")
        sub = sub_by_qid.get(qid, {}).get(sub_key, "")
        out[str(column)] = f"{text} — {sub}" if sub else text
    return out, truncated


def safe_name(name: str, fmt: str, fallback: str = "qualtrics-export") -> str:
    """A filename this app is willing to write: no path, no control characters, and the
    suffix the chosen format actually is."""
    base = PurePosixPath(str(name or "").replace("\\", "/")).name
    base = re.sub(r'[\x00-\x1f<>:"|?*]', "_", base).strip(". ")
    if not base:
        base = fallback
    suffix = EXPORT_SUFFIX.get(fmt, "")
    if suffix and not base.lower().endswith(suffix):
        base += suffix
    return base


def unpack(payload: bytes) -> list[tuple[str, bytes]]:
    """The export downloads as a zip holding one file. Return [(name, bytes)] with every
    member reduced to its basename — an archive does not get to pick a path on this disk.

    Returns [] when the payload isn't a zip, which is the caller's cue to save the bytes
    as they arrived.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            out: list[tuple[str, bytes]] = []
            for info in archive.infolist():
                if info.is_dir() or info.file_size > _MAX_MEMBER_BYTES:
                    continue
                name = PurePosixPath(info.filename).name or "export"
                out.append((name, archive.read(info)))
            return out
    except (zipfile.BadZipFile, OSError, RuntimeError):
        return []
