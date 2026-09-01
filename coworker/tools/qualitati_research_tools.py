"""QualiTaTi's research services, usable from a MimiWork session.

Two services the user already pays for on qualitati.com, reached with the personal
API key the sign-in stores:

- ``qualitati_proofread`` — a .docx goes up, a proofread copy with Track Changes
  comes back. The user opens it in Word and accepts or rejects each change.
- ``qualitati_annotate`` — a spreadsheet of open-ended text is coded against
  categories the user defines, by a model of their choosing, and the coded file
  comes back.

Both SPEND the user's QualiTaTi credits, so both are approval-gated: the request
card quotes the estimated cost before anything runs. That matters most for an
automation on Full access, which would otherwise spend credits with nothing on
screen to notice it.

These endpoints were JWT-only until 2026-08-31 — a browser-login surface. Opening
them to API keys is what lets a MimiWork session use them at all; without it the
proofreader silently treated a paying user as a guest (three free, no history).
"""

from __future__ import annotations

import json
import mimetypes
import time
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib import error, request

import aisuite as ai

# Proofreading a long manuscript is a single long call, not a job queue.
_UPLOAD_TIMEOUT = 900.0
_POLL_TIMEOUT = 1800.0
_POLL_EVERY = 5.0


def _auth() -> dict[str, Any]:
    from ..qualitati import AUTH_PROFILE, DEFAULT_BASE, PROVIDER_PROFILE
    from ..secrets import SecretStore

    secrets = SecretStore()
    auth = secrets.get(AUTH_PROFILE) or {}
    provider = secrets.get(PROVIDER_PROFILE) or {}
    return {
        "base": (auth.get("base_url") or DEFAULT_BASE).rstrip("/"),
        "api_key": (provider.get("api_key") if isinstance(provider, dict) else None),
    }


_NOT_SIGNED_IN = {
    "error": "Not signed in to QualiTaTi. Ask the user to sign in from Settings → "
    "Models → QualiTaTi account."
}


def _headers(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def _json_call(
    method: str, url: str, key: str, body: Optional[dict] = None, timeout: float = 60.0
) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(
        url,
        data=data,
        method=method,
        headers={**_headers(key), **({"Content-Type": "application/json"} if data else {})},
    )
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {"detail": e.reason}
    except Exception as e:
        return 0, {"detail": f"QualiTaTi unreachable: {e}"}


def _multipart(
    url: str, key: str, path: Path, fields: dict[str, str], timeout: float
) -> tuple[int, bytes, str]:
    """POST one file plus form fields. Hand-rolled because the sidecar ships no
    multipart client and a file upload is not worth a dependency."""
    boundary = f"----mimiwork{uuid.uuid4().hex}"
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode()
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        f"Content-Type: {ctype}\r\n\r\n".encode()
    )
    parts.append(path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    payload = b"".join(parts)
    req = request.Request(
        url,
        data=payload,
        method="POST",
        headers={**_headers(key), "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type", "") if e.headers else ""
    except Exception as e:
        return 0, str(e).encode(), ""


def _err(status: int, body: Any) -> dict[str, Any]:
    if status in (401, 403):
        return {
            "error": "QualiTaTi refused the request — the sign-in may have expired. Ask "
            "the user to sign in again from Settings → Models → QualiTaTi account."
        }
    if status == 402:
        return {"error": "Not enough QualiTaTi credits for this. The user can top up on qualitati.com."}
    detail = body.get("detail") if isinstance(body, dict) else body
    return {"error": f"QualiTaTi returned {status}: {detail}"}


def _resolve(path: str, roots: Any) -> Optional[Path]:
    """Resolve a path the model gave against the session's folders. Refuses anything
    outside them — a tool that uploads files must not be talked into uploading
    /etc/passwd."""
    p = Path(path).expanduser()
    candidates = [p] if p.is_absolute() else []
    for root in roots or []:
        base = root.get("path") if isinstance(root, dict) else root
        if base:
            candidates.append(Path(base).expanduser() / path)
    for c in candidates:
        try:
            rp = c.resolve()
        except OSError:
            continue
        if not rp.is_file():
            continue
        for root in roots or []:
            base = root.get("path") if isinstance(root, dict) else root
            if not base:
                continue
            try:
                if rp.is_relative_to(Path(base).expanduser().resolve()):
                    return rp
            except (OSError, ValueError):
                continue
    return None


_PROOFREAD_SCHEMA = {
    "type": "function",
    "function": {
        "name": "qualitati_proofread",
        "description": (
            "Proofread a Word manuscript with QualiTaTi's academic proofreader. Returns a "
            "copy with Track Changes so the user accepts or rejects each edit in Word. "
            "Use for manuscripts, theses and papers — not for short notes, which you can "
            "edit directly. SPENDS the user's QualiTaTi credits (roughly one per 500 "
            "words). Give journal_name and author_guidelines when the user has a target "
            "journal: the proofreader follows that journal's conventions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The .docx file, in one of the session's folders."},
                "language": {"type": "string", "description": "Manuscript language (default English)."},
                "journal_name": {"type": "string", "description": "Target journal, if any."},
                "journal_scope": {"type": "string", "description": "The journal's scope statement, if known."},
                "author_guidelines": {"type": "string", "description": "The journal's author guidelines, if known."},
                "reviewer_feedback": {"type": "string", "description": "Reviewer comments to address, if this is a revision."},
            },
            "required": ["path"],
        },
    },
}

_ANNOTATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "qualitati_annotate",
        "description": (
            "Code a spreadsheet of open-ended text with QualiTaTi's annotator: every row "
            "is classified into categories you define, and the coded file comes back. Use "
            "for survey open-ends, interview excerpts or any column of free text that "
            "needs consistent coding. SPENDS the user's QualiTaTi credits. Define each "
            "annotation carefully — the definition is the codebook the model follows, and "
            "a vague one produces vague coding."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "The .csv or .xlsx file, in one of the session's folders."},
                "source_columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The column(s) holding the text to code.",
                },
                "annotations": {
                    "type": "array",
                    "description": "One entry per code to apply.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "col_name": {"type": "string", "description": "Output column, lowercase snake_case."},
                            "label": {"type": "string", "description": "Human-readable name."},
                            "categories": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "At least two mutually exclusive categories.",
                            },
                            "definition": {
                                "type": "string",
                                "description": "The codebook entry: what each category means and how to decide. At least 20 characters — write it properly.",
                            },
                        },
                        "required": ["col_name", "label", "categories", "definition"],
                    },
                },
            },
            "required": ["path", "source_columns", "annotations"],
        },
    },
}


def qualitati_research_tools(context: Any) -> list:
    roots = getattr(context, "roots", None) or []
    workspace = getattr(context, "workspace", None)

    def _outdir() -> Path:
        return Path(workspace) if workspace else Path.cwd()

    def qualitati_proofread(
        path: str,
        language: str = "English",
        journal_name: str = "",
        journal_scope: str = "",
        author_guidelines: str = "",
        reviewer_feedback: str = "",
    ) -> dict[str, Any]:
        auth = _auth()
        if not auth["api_key"]:
            return _NOT_SIGNED_IN
        src = _resolve(path, roots)
        if src is None:
            return {"error": f"No such file in this session's folders: {path}"}
        if src.suffix.lower() != ".docx":
            return {"error": "The proofreader takes .docx files. Convert the document first."}

        status, body, ctype = _multipart(
            f"{auth['base']}/api/proofread/upload",
            auth["api_key"],
            src,
            {
                "language": language,
                "journal_name": journal_name,
                "journal_scope": journal_scope,
                "author_guidelines": author_guidelines,
                "reviewer_feedback": reviewer_feedback,
            },
            _UPLOAD_TIMEOUT,
        )
        if status != 200:
            try:
                parsed = json.loads(body.decode())
            except Exception:
                parsed = {"detail": body[:200].decode(errors="replace")}
            return _err(status, parsed)

        out = _outdir() / f"{src.stem} (proofread){src.suffix}"
        out.write_bytes(body)
        return {
            "ok": True,
            "path": str(out),
            "note": "Tracked changes — open in Word and accept or reject each edit.",
        }

    def qualitati_annotate(
        path: str, source_columns: list, annotations: list
    ) -> dict[str, Any]:
        auth = _auth()
        if not auth["api_key"]:
            return _NOT_SIGNED_IN
        src = _resolve(path, roots)
        if src is None:
            return {"error": f"No such file in this session's folders: {path}"}

        status, body, _ = _multipart(
            f"{auth['base']}/api/annotator/uploads", auth["api_key"], src, {}, _UPLOAD_TIMEOUT
        )
        if status not in (200, 201):
            try:
                parsed = json.loads(body.decode())
            except Exception:
                parsed = {"detail": body[:200].decode(errors="replace")}
            return _err(status, parsed)
        upload = json.loads(body.decode())
        upload_id = upload.get("uuid") or upload.get("upload_id") or upload.get("id")
        if not upload_id:
            return {"error": "QualiTaTi accepted the file but returned no upload id."}

        # Whatever model the account is offered first — the user picks models on
        # qualitati.com, and guessing an id here would fail for accounts without it.
        status, models = _json_call("GET", f"{auth['base']}/api/annotator/models", auth["api_key"])
        if status != 200:
            return _err(status, models)
        available = models if isinstance(models, list) else (models or {}).get("models") or []
        if not available:
            return {"error": "This QualiTaTi account has no annotator models available."}
        first = available[0]
        model_ref = {
            "provider": first.get("provider", ""),
            "model_id": first.get("model_id") or first.get("id", ""),
        }

        status, job = _json_call(
            "POST",
            f"{auth['base']}/api/annotator/jobs",
            auth["api_key"],
            {
                "upload_id": upload_id,
                "source_columns": list(source_columns or []),
                "annotation_config": list(annotations or []),
                "selected_models": [model_ref],
            },
        )
        if status not in (200, 201):
            return _err(status, job)
        job_id = (job or {}).get("uuid") or (job or {}).get("id")
        if not job_id:
            return {"error": "QualiTaTi accepted the job but returned no id."}

        # Poll. The annotator is a queue, so the tool waits rather than handing the
        # model a job id it would have to remember to check.
        deadline = time.time() + _POLL_TIMEOUT
        state = "queued"
        while time.time() < deadline:
            time.sleep(_POLL_EVERY)
            status, snap = _json_call(
                "GET", f"{auth['base']}/api/annotator/jobs/{job_id}", auth["api_key"]
            )
            if status != 200:
                return _err(status, snap)
            state = (snap or {}).get("status") or state
            if state in ("completed", "failed", "cancelled"):
                break
        if state != "completed":
            return {
                "error": f"The annotation job ended as '{state}'.",
                "job_id": job_id,
                "note": "Open it on qualitati.com to see what happened.",
            }

        status, data, _ = _download(
            f"{auth['base']}/api/annotator/jobs/{job_id}/download", auth["api_key"]
        )
        if status != 200:
            return {"error": f"The job finished but the download failed ({status}).", "job_id": job_id}
        out = _outdir() / f"{src.stem} (annotated).xlsx"
        out.write_bytes(data)
        return {"ok": True, "path": str(out), "job_id": job_id}

    def _download(url: str, key: str) -> tuple[int, bytes, str]:
        req = request.Request(url, headers=_headers(key))
        try:
            with request.urlopen(req, timeout=_UPLOAD_TIMEOUT) as r:
                return r.status, r.read(), r.headers.get("Content-Type", "")
        except error.HTTPError as e:
            return e.code, e.read(), ""
        except Exception as e:
            return 0, str(e).encode(), ""

    qualitati_proofread.__name__ = "qualitati_proofread"
    qualitati_proofread.__doc__ = _PROOFREAD_SCHEMA["function"]["description"]
    qualitati_proofread.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="qualitati_proofread",
        category="qualitati",
        risk_level="medium",
        capabilities=["read", "write"],
        # Spends the user's credits. An automation on Full access would otherwise run
        # a bill up with nothing on screen to notice it.
        requires_approval=True,
    )
    qualitati_proofread.__coworker_schema__ = _PROOFREAD_SCHEMA

    qualitati_annotate.__name__ = "qualitati_annotate"
    qualitati_annotate.__doc__ = _ANNOTATE_SCHEMA["function"]["description"]
    qualitati_annotate.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="qualitati_annotate",
        category="qualitati",
        risk_level="medium",
        capabilities=["read", "write"],
        requires_approval=True,
    )
    qualitati_annotate.__coworker_schema__ = _ANNOTATE_SCHEMA

    return [qualitati_proofread, qualitati_annotate]


__all__ = ["qualitati_research_tools"]
