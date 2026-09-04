"""The signed-in user's own QualiTaTi data — projects, interviews, surveys, responses —
and, since 2026-09-04, building surveys there directly (owner ask: "create a survey
directly to qualitati" produced only 422s, because the listing needed a project and
nothing could write).

Signing in to QualiTaTi already buys model credits; this is the other half the owner asked
for (2026-08-23): the research data that lives in the same account should be usable here,
so "analyse my December interviews" doesn't start with a manual export.

Two rules shape the whole module:

* **Nothing is fetched without a yes.** Every tool declares ``requires_approval=True``, so
  ``risk.classify`` calls it EXTERNAL: the permission engine asks before each retrieval and
  Plan/Discuss modes refuse outright. Fetching someone's interview transcripts is not a
  read of the local workspace — it pulls personal data off a server, and the user says when.
* **The account's own credential, nothing else.** Calls carry the JWT that the Settings
  sign-in stored; signed out, the tools say so instead of prompting for anything.

Payload shapes are whatever the QualiTaTi API returns (its OpenAPI leaves them open), so
lists are capped and long text is trimmed rather than reshaped — the model gets the data,
the context window survives.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import aisuite as ai
import httpx

from ..qualitati import AUTH_PROFILE, DEFAULT_BASE

_TIMEOUT = 30.0
_SITE = "https://qualitati.com"  # where the builder and respondent links live
_IMAGE_LIMIT = 2 * 1024 * 1024  # the upload endpoint's cap
_IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
# QualiTaTi's question types (backend SurveyQuestionType), plus the words a model
# reaches for instead. Anything else is refused with the list, not guessed.
_TYPES = {
    "short_text", "long_text", "single_choice", "multi_choice", "number", "date", "ranking",
    "bipolar_scale", "info_text", "slider", "dropdown", "nps", "matrix", "ai_interview",
    "rating_scale", "yes_no", "email", "phone", "image_choice", "file_upload", "constant_sum",
    "section_break", "page_break",
}
_TYPE_ALIASES = {
    "text": "short_text", "short": "short_text", "open": "long_text", "open_ended": "long_text",
    "paragraph": "long_text", "long": "long_text", "essay": "long_text",
    "choice": "single_choice", "single": "single_choice", "radio": "single_choice",
    "multiple_choice": "single_choice", "mc": "single_choice",
    "multi": "multi_choice", "checkbox": "multi_choice", "multiple": "multi_choice",
    "multi_select": "multi_choice", "select_all": "multi_choice",
    "likert": "rating_scale", "scale": "rating_scale", "rating": "rating_scale", "agreement": "rating_scale",
    "semantic_differential": "bipolar_scale", "bipolar": "bipolar_scale",
    "grid": "matrix", "likert_matrix": "matrix", "table": "matrix",
    "info": "info_text", "instruction": "info_text", "instructions": "info_text", "stimulus": "info_text",
    "scenario": "info_text", "consent": "info_text", "image": "info_text",
    "page": "page_break", "break": "page_break", "section": "section_break",
    "select": "dropdown", "yesno": "yes_no", "boolean": "yes_no", "yes/no": "yes_no",
    "numeric": "number", "integer": "number", "age": "number",
    "interview": "ai_interview", "ai": "ai_interview",
    "rank": "ranking", "order": "ranking", "allocation": "constant_sum", "points": "constant_sum",
    "images": "image_choice", "image_options": "image_choice", "picture_choice": "image_choice",
}
_LAYOUT_TYPES = {"info_text", "page_break", "section_break"}
_LANGUAGE_NAMES = {
    "en": "ENGLISH", "fr": "FRENCH", "zh": "CHINESE", "de": "GERMAN", "es": "SPANISH",
    "it": "ITALIAN", "nl": "DUTCH", "pt": "PORTUGUESE", "ja": "JAPANESE", "ko": "KOREAN",
    "no": "NORWEGIAN", "nb": "NORWEGIAN", "sv": "SWEDISH", "da": "DANISH", "ar": "ARABIC",
}
_MAX_ROWS = 50  # per list call — more is a paging problem, not a context problem
_MAX_TEXT = 40_000  # characters of transcript-ish payload per call
_SIGNED_OUT = (
    "Not signed in to QualiTaTi. Open Settings ▸ Models and sign in with the "
    "QualiTaTi account, then try again."
)


def _auth(secrets: Any) -> tuple[Optional[str], str]:
    profile = secrets.get(AUTH_PROFILE) or {}
    if not isinstance(profile, dict):
        return None, DEFAULT_BASE
    token = str(profile.get("access_token") or "").strip() or None
    base = str(profile.get("base_url") or DEFAULT_BASE).rstrip("/")
    return token, base


def _trim(value: Any, budget: int = _MAX_TEXT) -> Any:
    """Cap a payload without changing its shape: long lists lose their tail, long strings
    lose their end, and both say so."""
    if isinstance(value, str):
        return value if len(value) <= budget else value[:budget] + "\n…[trimmed]"
    if isinstance(value, list):
        rows = [_trim(v, budget // 4) for v in value[:_MAX_ROWS]]
        if len(value) > _MAX_ROWS:
            rows.append(f"…[{len(value) - _MAX_ROWS} more not shown]")
        return rows
    if isinstance(value, dict):
        return {k: _trim(v, budget // 2) for k, v in value.items()}
    return value


def _detail(r: Any) -> str:
    """What the server said went wrong, in one line — a 422 names the missing field,
    and the model can act on that where "returned 422" left it guessing."""
    try:
        body = r.json()
    except ValueError:
        return (getattr(r, "text", "") or "")[:300]
    d = body.get("detail") if isinstance(body, dict) else body
    if isinstance(d, list):
        parts = []
        for item in d[:5]:
            if isinstance(item, dict):
                loc = ".".join(str(x) for x in (item.get("loc") or []) if x not in ("body", "query"))
                parts.append(f"{loc}: {item.get('msg')}" if loc else str(item.get("msg")))
            else:
                parts.append(str(item))
        return "; ".join(parts)[:300]
    return str(d or body)[:300]


def _survey_row(s: dict, base_project: Optional[int] = None) -> dict:
    pid = s.get("project_id") or base_project
    token = s.get("share_token")
    return {
        "id": s.get("id"),
        "project_id": pid,
        "title": s.get("title"),
        "status": s.get("status"),
        "responses": s.get("response_count", 0),
        "questions": len(s.get("questions") or []),
        "builder_url": f"{_SITE}/survey/{pid}/{s.get('id')}/builder" if pid else None,
        "share_url": f"{_SITE}/s/{s.get('id')}?t={token}" if token and s.get("status") == "published" else None,
    }


def _question_row(q: dict) -> dict:
    row = {
        "id": q.get("id"),
        "type": q.get("type"),
        "prompt": q.get("prompt"),
        "variable_name": q.get("variable_name"),
        "required": q.get("required"),
        "block_id": q.get("block_id"),
    }
    for src, dst in (("options_json", "options"), ("rows", "rows"), ("columns", "columns"), ("validation_json", "validation"), ("prompt_image_url", "image")):
        if q.get(src):
            row[dst] = q[src]
    return row


def _variable_name(raw: Any) -> Optional[str]:
    import re

    name = re.sub(r"[^a-zA-Z0-9_]+", "_", str(raw or "")).strip("_")
    if not name:
        return None
    if name[0].isdigit():
        name = "q_" + name
    return name[:60]


def _unique_variable(q: dict, t: str, prompt: str, used: set[str]) -> str:
    """Every question needs a variable_name (the server insists, whatever its schema
    says — live 400s, 2026-09-04): the model's own, else the prompt's first words, else
    the type; made unique within the survey with a numeric suffix."""
    base = _variable_name(q.get("variable_name") or q.get("name") or q.get("variable"))
    if not base:
        base = _variable_name("_".join(prompt.lower().split()[:4])) or t
        base = base[:40].rstrip("_") or t
    name, n = base, 1
    while name.lower() in used:
        n += 1
        name = f"{base}_{n}"
    used.add(name.lower())
    return name


def _build_question(q: Any, upload, used: Optional[set[str]] = None) -> tuple[Optional[dict], Optional[str]]:
    """One question as the model wrote it → the body QualiTaTi's QuestionCreate accepts,
    or the reason it cannot be. Shapes follow the backend's canonical storage: choice
    options in options_json, matrix rows/columns as their own fields, scale bounds and
    pole labels in validation_json, rating points spelled out as options."""
    if not isinstance(q, dict):
        return None, "each question must be an object with at least a prompt"
    raw_type = str(q.get("type") or "short_text").strip().lower().replace("-", "_").replace(" ", "_")
    t = _TYPE_ALIASES.get(raw_type, raw_type)
    if t not in _TYPES:
        return None, f"unknown question type {q.get('type')!r} — use one of: {', '.join(sorted(_TYPES))}"
    prompt = str(q.get("prompt") or q.get("text") or q.get("question") or "").strip()
    if not prompt and t not in ("page_break", "section_break"):
        return None, "every question needs a prompt"
    body: dict[str, Any] = {
        "type": t,
        "prompt": prompt,
        "required": bool(q.get("required", t not in _LAYOUT_TYPES)),
        "ai_follow_up_intensity": str(q.get("follow_up") or q.get("ai_follow_up_intensity") or "none").lower(),
    }
    if body["ai_follow_up_intensity"] not in ("none", "light", "deep"):
        body["ai_follow_up_intensity"] = "none"
    body["variable_name"] = _unique_variable(q, t, prompt, used if used is not None else set())
    options = [str(o).strip() for o in (q.get("options") or q.get("options_json") or []) if str(o).strip()]
    validation: dict[str, Any] = {
        k: q[k] for k in ("min", "max", "min_label", "max_label", "step", "labels", "total") if q.get(k) not in (None, "")
    }
    if t in ("single_choice", "multi_choice", "dropdown", "ranking", "constant_sum"):
        if len(options) < 2:
            return None, f"{t} needs at least two options"
        body["options_json"] = options
    elif t == "matrix":
        rows = [str(r).strip() for r in (q.get("rows") or q.get("statements") or []) if str(r).strip()]
        cols = [str(c).strip() for c in (q.get("columns") or q.get("scale") or options) if str(c).strip()]
        if not rows or not cols:
            return None, "matrix needs rows (the statements) and columns (the scale points)"
        body["rows"], body["columns"] = rows, cols
    elif t == "rating_scale":
        labels = q.get("labels") if isinstance(q.get("labels"), list) else None
        lo = int(q.get("min") or 1)
        hi = int(q.get("max") or (len(labels) if labels else 7))
        if hi <= lo:
            return None, "rating_scale needs max greater than min"
        body["options_json"] = [str(i) for i in range(lo, hi + 1)]
        validation.update({"min": lo, "max": hi})
    elif t == "bipolar_scale":
        poles = q.get("poles") if isinstance(q.get("poles"), list) else [q.get("min_label"), q.get("max_label")]
        poles = [str(p).strip() for p in (poles or []) if p and str(p).strip()]
        if len(poles) != 2:
            return None, "bipolar_scale needs its two poles: min_label and max_label (or poles: [left, right])"
        body["options_json"] = poles
        validation.update({"min": int(q.get("min") or 1), "max": int(q.get("max") or 7)})
        validation.pop("min_label", None)
        validation.pop("max_label", None)
    elif t == "image_choice":
        urls = []
        for path in options:
            url, err = upload(path)
            if err:
                return None, err
            urls.append(url)
        if len(urls) < 2:
            return None, "image_choice needs at least two image files (workspace paths) as options"
        body["options_json"] = urls
        validation["allowMultiple"] = bool(q.get("multiple"))
    if validation:
        body["validation_json"] = validation
    if q.get("randomize_options"):
        body["randomize_options"] = True
    image = q.get("image") or q.get("image_path")
    if image:
        url, err = upload(str(image))
        if err:
            return None, err
        body["prompt_image_url"] = url
    return body, None


_QUESTION_ITEM = {
    "type": "object",
    "description": (
        "One question. `type` is one of QualiTaTi's: short_text, long_text, single_choice, "
        "multi_choice, dropdown, yes_no, number, date, email, phone, rating_scale (min/max, "
        "min_label/max_label or labels), bipolar_scale (min_label/max_label poles, min/max), "
        "nps, slider, matrix (rows = statements, columns = scale points), ranking, "
        "constant_sum, image_choice (options = image paths), info_text (a stimulus or "
        "instruction; `image` shows a workspace image), page_break, section_break, "
        "ai_interview. Everyday words (likert, checkbox, grid, scenario…) are accepted."
    ),
    "properties": {
        "type": {"type": "string"},
        "prompt": {"type": "string", "description": "The question text, or the passage for info_text."},
        "options": {"type": "array", "items": {"type": "string"}, "description": "Choice options; image paths for image_choice."},
        "rows": {"type": "array", "items": {"type": "string"}, "description": "matrix: the statements down the side."},
        "columns": {"type": "array", "items": {"type": "string"}, "description": "matrix: the scale points across the top."},
        "min": {"type": "integer"},
        "max": {"type": "integer"},
        "min_label": {"type": "string"},
        "max_label": {"type": "string"},
        "labels": {"type": "array", "items": {"type": "string"}, "description": "rating_scale: one label per point."},
        "required": {"type": "boolean", "description": "Default true, except layout items."},
        "variable_name": {"type": "string", "description": "Column name in the export (letters, digits, underscores)."},
        "image": {"type": "string", "description": "Workspace path of a PNG/JPEG/GIF/WebP (≤ 2 MB) shown above the prompt."},
        "block": {"type": "string", "description": "Title of the block this question belongs to (see `blocks`)."},
        "randomize_options": {"type": "boolean"},
        "follow_up": {"type": "string", "description": "AI follow-up probing on open answers: none, light or deep."},
    },
    "required": ["type", "prompt"],
}
_BLOCK_ITEM = {
    "type": "object",
    "description": (
        "A block groups questions. A randomizer block shows `pick` of its `children` "
        "blocks to each respondent — the between-subjects design: put each condition's "
        "stimulus and questions in a child block named for the condition."
    ),
    "properties": {
        "title": {"type": "string"},
        "randomizer": {"type": "boolean"},
        "pick": {"type": "integer", "description": "How many children a respondent sees (default 1)."},
        "children": {"type": "array", "items": {"type": "string"}, "description": "Titles of the child blocks (conditions)."},
    },
    "required": ["title"],
}
_CREATE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "qualitati_create_survey",
        "description": (
            "Build a survey on QualiTaTi in one call: a study project (unless project_id "
            "names an existing survey project), the survey, its blocks and its questions, "
            "with stimulus images uploaded from the workspace. Returns the builder link; "
            "the survey stays a draft until qualitati_publish_survey. Design the "
            "questionnaire and show it to the user before calling this."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "questions": {"type": "array", "items": _QUESTION_ITEM, "description": "In order of appearance."},
                "description": {"type": "string", "description": "Shown to respondents on the first page."},
                "project_id": {"type": "string", "description": "An existing survey-type project id from qualitati_projects; omit to create one named after the survey."},
                "language": {"type": "string", "description": "ISO code of the survey language, default en."},
                "blocks": {"type": "array", "items": _BLOCK_ITEM},
            },
            "required": ["title", "questions"],
        },
    },
}
_EDIT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "qualitati_edit_survey",
        "description": (
            "Change a QualiTaTi survey: retitle it, add questions (same shape as in "
            "qualitati_create_survey, optionally into a block by title), delete questions "
            "by id, or add blocks. Read the current state with qualitati_surveys first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "survey_id": {"type": "string"},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "add_questions": {"type": "array", "items": _QUESTION_ITEM},
                "delete_question_ids": {"type": "array", "items": {"type": "integer"}},
                "blocks": {"type": "array", "items": _BLOCK_ITEM},
            },
            "required": ["survey_id"],
        },
    },
}


def qualitati_data_tools(secrets: Any, workspace: Optional[str | Path] = None) -> list:
    """The read tools, all approval-gated. `workspace` is where an export may be saved."""

    def _get(path: str, params: Optional[dict[str, Any]] = None) -> Any:
        token, base = _auth(secrets)
        if not token:
            return {"error": _SIGNED_OUT}
        try:
            r = httpx.get(
                f"{base}{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params or None,
                timeout=_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            return {"error": f"QualiTaTi unreachable: {exc}"}
        if r.status_code == 401:
            return {"error": "QualiTaTi rejected the stored sign-in — sign in again in Settings."}
        if r.status_code == 404:
            return {"error": "No such item in this QualiTaTi account."}
        if r.status_code >= 400:
            return {"error": f"QualiTaTi returned {r.status_code}: {_detail(r)}"}
        try:
            return r.json()
        except ValueError:
            return {"error": "QualiTaTi returned something that isn't JSON."}

    def _send(method: str, path: str, **kw: Any) -> Any:
        """A write (post/put/delete) with the same credential and error mapping as _get."""
        token, base = _auth(secrets)
        if not token:
            return {"error": _SIGNED_OUT}
        try:
            r = getattr(httpx, method)(
                f"{base}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=_TIMEOUT, **kw
            )
        except httpx.HTTPError as exc:
            return {"error": f"QualiTaTi unreachable: {exc}"}
        if r.status_code == 401:
            return {"error": "QualiTaTi rejected the stored sign-in — sign in again in Settings."}
        if r.status_code == 404:
            return {"error": "No such item in this QualiTaTi account."}
        if r.status_code >= 400:
            return {"error": f"QualiTaTi returned {r.status_code}: {_detail(r)}"}
        if not r.content:
            return {}
        try:
            return r.json()
        except ValueError:
            return {"error": "QualiTaTi returned something that isn't JSON."}

    def _upload(path: str, dry: bool = False) -> tuple[Optional[str], Optional[str]]:
        """A workspace image → the short URL QualiTaTi stores on a question. (url, error).
        ``dry`` runs every check without sending — the create tool validates the whole
        questionnaire before it writes a thing."""
        if workspace is None:
            return None, "this session has no workspace folder to read images from"
        root = Path(workspace).expanduser().resolve()
        target = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        if root not in target.parents and target != root:
            return None, f"{path}: images must be inside the session's folder"
        if not target.is_file():
            return None, f"{path}: no such image in the workspace"
        mime = _IMAGE_TYPES.get(target.suffix.lower())
        if not mime:
            return None, f"{path}: only PNG, JPEG, GIF or WebP images can be shown in a survey"
        if target.stat().st_size > _IMAGE_LIMIT:
            return None, f"{path}: larger than 2 MB — shrink it first (edit_image)"
        if dry:
            return "pending", None
        res = _send("post", "/api/surveys/upload-image", files={"file": (target.name, target.read_bytes(), mime)})
        if "error" in res:
            return None, f"{path}: {res['error']}"
        return res.get("url"), None

    def _create_blocks(sid: int, blocks: Any, problems: list[str]) -> dict[str, int]:
        """Blocks by title → id. Parents first, then the children of randomizers."""
        ids: dict[str, int] = {}
        for b in blocks or []:
            if not isinstance(b, dict) or not str(b.get("title") or "").strip():
                problems.append("a block without a title was skipped")
                continue
            title = str(b["title"]).strip()
            res = _send(
                "post",
                f"/api/surveys/{sid}/blocks",
                json={
                    "title": title,
                    "is_randomizer": bool(b.get("randomizer")),
                    "randomizer_pick_count": int(b.get("pick") or 1),
                },
            )
            if "error" in res or not res.get("id"):
                problems.append(f"block {title!r}: {res.get('error', 'not created')}")
                continue
            ids[title] = res["id"]
            for child in b.get("children") or []:
                ctitle = str(child).strip()
                cres = _send(
                    "post",
                    f"/api/surveys/{sid}/blocks",
                    json={"title": ctitle, "is_randomizer": False, "randomizer_pick_count": 1, "parent_block_id": res["id"]},
                )
                if "error" in cres or not cres.get("id"):
                    problems.append(f"block {ctitle!r}: {cres.get('error', 'not created')}")
                else:
                    ids[ctitle] = cres["id"]
        return ids

    def _add_questions(sid: int, questions: Any, block_ids: dict[str, int], problems: list[str], used: Optional[set[str]] = None) -> list[dict]:
        added: list[dict] = []
        used = set() if used is None else used
        for i, q in enumerate(questions or []):
            body, err = _build_question(q, _upload, used)
            if err:
                problems.append(f"question {i + 1}: {err}")
                continue
            res = _send("post", f"/api/surveys/{sid}/questions", json=body)
            if "error" in res:
                problems.append(f"question {i + 1} ({body['prompt'][:40]!r}): {res['error']}")
                continue
            row = {"id": res.get("id"), "type": body["type"], "prompt": body["prompt"][:80]}
            block = str(q.get("block") or "").strip() if isinstance(q, dict) else ""
            if block:
                bid = block_ids.get(block)
                if bid is None:
                    problems.append(f"question {i + 1}: no block titled {block!r} — left outside the blocks")
                else:
                    mv = _send("put", f"/api/surveys/{sid}/questions/{res.get('id')}/move", json={"block_id": bid})
                    if "error" in mv:
                        problems.append(f"question {i + 1}: could not move into {block!r}: {mv['error']}")
                    else:
                        row["block"] = block
            added.append(row)
        return added

    def _existing_blocks(sid: int) -> tuple[dict[str, int], set[str]]:
        """Block ids by title, and the variable names already taken."""
        detail = _get(f"/api/surveys/{sid}")
        ids: dict[str, int] = {}
        used: set[str] = set()

        def walk(blocks: Any) -> None:
            for b in blocks or []:
                if isinstance(b, dict) and b.get("title") and b.get("id"):
                    ids[str(b["title"])] = int(b["id"])
                    walk(b.get("children"))

        if isinstance(detail, dict):
            walk(detail.get("blocks"))
            used = {str(q.get("variable_name") or "").lower() for q in detail.get("questions") or [] if isinstance(q, dict)}
        return ids, used

    def qualitati_projects(project_type: str = "") -> dict:
        """List the projects in the user's QualiTaTi account (id, uuid, name, type). Start
        here when the user refers to "my project" / "my study" on QualiTaTi. Args:
        project_type (str): "interview" or "survey" to filter; empty for all."""
        params = {"project_type": project_type.strip()} if (project_type or "").strip() in ("interview", "survey") else None
        data = _get("/api/projects", params)
        if isinstance(data, dict) and "error" in data:
            return data
        rows = [
            {
                "id": p.get("id"),
                "uuid": p.get("uuid") or p.get("project_uuid"),
                "name": p.get("name"),
                "type": p.get("project_type") or "interview",
                **({"shared_by": p.get("owner_username")} if p.get("is_owner") is False else {}),
            }
            for p in (data if isinstance(data, list) else [])
            if isinstance(p, dict)
        ]
        return {"count": len(rows), "projects": _trim(rows)}

    def qualitati_interviews(project_uuid: str) -> dict:
        """List the interviews inside one QualiTaTi project. Args: project_uuid (str): the
        project's uuid from qualitati_projects."""
        if not (project_uuid or "").strip():
            return {"error": "project_uuid is required"}
        data = _get(f"/api/interview/projects/{project_uuid.strip()}/live-interviews")
        return (
            data
            if isinstance(data, dict) and "error" in data
            else {"project_uuid": project_uuid, "interviews": _trim(data)}
        )

    def qualitati_interview_transcript(interview_uuid: str) -> dict:
        """Fetch one interview's conversation (the transcript) from QualiTaTi. Args:
        interview_uuid (str): from qualitati_interviews."""
        if not (interview_uuid or "").strip():
            return {"error": "interview_uuid is required"}
        data = _get(f"/api/interview/interviews/{interview_uuid.strip()}/conversation")
        return (
            data
            if isinstance(data, dict) and "error" in data
            else {"interview_uuid": interview_uuid, "conversation": _trim(data)}
        )

    def qualitati_surveys(project_id: str = "", survey_id: str = "") -> dict:
        """List the surveys in the user's QualiTaTi account (id, title, status, responses,
        links), or read one survey in full. Args: project_id (str): limit to one survey
        project. survey_id (str): return this survey's questions and blocks instead."""
        sid = (survey_id or "").strip()
        if sid:
            data = _get(f"/api/surveys/{sid}")
            if isinstance(data, dict) and "error" in data:
                return data
            return {
                "survey": {
                    **_survey_row(data),
                    "description": data.get("description"),
                    "language": data.get("language_default"),
                    "blocks": _trim(data.get("blocks") or []),
                    "questions": _trim([_question_row(q) for q in data.get("questions") or []]),
                }
            }
        pid = (project_id or "").strip()
        if pid:
            data = _get("/api/surveys", {"project_id": pid})
            if isinstance(data, dict) and "error" in data:
                return data
            return {"surveys": _trim([_survey_row(s, base_project=int(pid) if pid.isdigit() else None) for s in data])}
        # The endpoint is per project: walk the survey projects (the ones the Survey
        # Hub shows) and gather. Interview projects never hold surveys.
        projects = _get("/api/projects", {"project_type": "survey"})
        if isinstance(projects, dict) and "error" in projects:
            return projects
        rows: list[dict] = []
        for p in (projects if isinstance(projects, list) else [])[:40]:
            data = _get("/api/surveys", {"project_id": p.get("id")})
            if isinstance(data, list):
                rows.extend({**_survey_row(s, base_project=p.get("id")), "project": p.get("name")} for s in data)
        return {"count": len(rows), "surveys": _trim(rows)}

    def qualitati_create_survey(
        title: str,
        questions: list,
        description: str = "",
        project_id: str = "",
        language: str = "en",
        blocks: Optional[list] = None,
    ) -> dict:
        """Build a survey on QualiTaTi: project (unless given), survey, blocks, questions."""
        title = (title or "").strip()
        if not title:
            return {"error": "title is required"}
        if not isinstance(questions, list) or not questions:
            return {"error": "questions must be a non-empty list"}
        lang = (language or "en").strip().lower()[:5] or "en"
        problems: list[str] = []
        # Validate every question BEFORE anything is created: a half-built survey
        # with a typo'd type in question 7 is worse than a clear refusal.
        used: set[str] = set()
        for i, q in enumerate(questions):
            _, err = _build_question(q, lambda p: _upload(p, dry=True), used)
            if err:
                problems.append(f"question {i + 1}: {err}")
        if problems:
            return {"error": "fix these before the survey is created", "problems": problems}
        pid_text = (project_id or "").strip()
        if pid_text:
            if not pid_text.isdigit():
                return {"error": "project_id must be the numeric id from qualitati_projects"}
            pid = int(pid_text)
        else:
            project = _send(
                "post",
                "/api/projects",
                json={
                    "name": title[:100],
                    "outline": (description or title)[:2000],
                    "interview_type": "SEMI_STRUCTURED",
                    "interview_language": _LANGUAGE_NAMES.get(lang[:2], "ENGLISH"),
                    "project_type": "survey",
                },
            )
            if "error" in project:
                return {"error": f"could not create the study project: {project['error']}"}
            pid = int(project.get("id"))
        survey = _send(
            "post",
            "/api/surveys",
            json={"project_id": pid, "title": title, "description": (description or None), "language_default": lang},
        )
        if "error" in survey:
            return {"error": f"could not create the survey: {survey['error']}", "project_id": pid}
        sid = int(survey["id"])
        block_ids = _create_blocks(sid, blocks, problems)
        added = _add_questions(sid, questions, block_ids, problems)
        return {
            "ok": True,
            "survey_id": sid,
            "project_id": pid,
            "title": title,
            "status": "draft",
            "questions_added": len(added),
            "questions": added,
            "blocks": block_ids,
            "problems": problems,
            "builder_url": f"{_SITE}/survey/{pid}/{sid}/builder",
            "next": "Review it in the builder, then qualitati_publish_survey to get the respondent link.",
        }

    def qualitati_edit_survey(
        survey_id: str,
        title: str = "",
        description: str = "",
        add_questions: Optional[list] = None,
        delete_question_ids: Optional[list] = None,
        blocks: Optional[list] = None,
    ) -> dict:
        """Retitle a survey, add or delete questions, add blocks."""
        sid_text = (survey_id or "").strip()
        if not sid_text.isdigit():
            return {"error": "survey_id must be the numeric id from qualitati_surveys"}
        sid = int(sid_text)
        problems: list[str] = []
        changed: dict[str, Any] = {}
        meta = {k: v for k, v in (("title", (title or "").strip()), ("description", (description or "").strip())) if v}
        if meta:
            res = _send("put", f"/api/surveys/{sid}", json=meta)
            if "error" in res:
                return res
            changed.update(meta)
        deleted = []
        for qid in delete_question_ids or []:
            res = _send("delete", f"/api/surveys/{sid}/questions/{int(qid)}")
            if "error" in res:
                problems.append(f"question {qid}: {res['error']}")
            else:
                deleted.append(int(qid))
        if deleted:
            changed["deleted_question_ids"] = deleted
        if add_questions or blocks:
            block_ids, used = _existing_blocks(sid)
            block_ids.update(_create_blocks(sid, blocks, problems))
            added = _add_questions(sid, add_questions, block_ids, problems, used)
            if added:
                changed["added"] = added
        if not changed and not problems:
            return {"error": "nothing to change: give a title, description, add_questions, delete_question_ids or blocks"}
        return {"ok": not problems or bool(changed), "survey_id": sid, **changed, "problems": problems}

    def qualitati_publish_survey(survey_id: str) -> dict:
        """Run QualiTaTi's pre-publish check and, if it passes, publish the survey and
        return the link respondents open. Args: survey_id (str): from qualitati_surveys."""
        sid_text = (survey_id or "").strip()
        if not sid_text.isdigit():
            return {"error": "survey_id must be the numeric id from qualitati_surveys"}
        sid = int(sid_text)
        pre = _get(f"/api/surveys/{sid}/preflight")
        if isinstance(pre, dict) and "error" in pre:
            return pre
        findings = pre.get("findings") if isinstance(pre, dict) else None
        if isinstance(pre, dict) and pre.get("status") not in (None, "ready"):
            return {
                "error": "QualiTaTi's pre-publish check found problems — fix them (qualitati_edit_survey) and publish again",
                "findings": _trim(findings or pre),
            }
        res = _send("post", f"/api/surveys/{sid}/publish")
        if "error" in res:
            return res
        return {
            "ok": True,
            "survey_id": sid,
            "status": res.get("status", "published"),
            "share_url": res.get("share_url"),
            "warnings": _trim(findings) if findings else [],
        }

    def qualitati_survey_responses(survey_id: str, analytics: bool = False) -> dict:
        """Fetch one survey's individual responses — or its aggregate analytics instead.
        Args: survey_id (str): from qualitati_surveys. analytics (bool): true returns the
        computed summary rather than raw responses."""
        if not (survey_id or "").strip():
            return {"error": "survey_id is required"}
        sid = survey_id.strip()
        data = _get(f"/api/surveys/{sid}/{'analytics' if analytics else 'responses'}")
        if isinstance(data, dict) and "error" in data:
            return data
        return {"survey_id": sid, ("analytics" if analytics else "responses"): _trim(data)}

    def qualitati_export_survey(survey_id: str, filename: str = "", fmt: str = "csv") -> dict:
        """Download a survey's responses into the workspace as a real file, ready for the
        analysis tools. Args: survey_id (str): from qualitati_surveys. filename (str):
        optional name for the saved file. fmt (str): "csv" or "xlsx"."""
        sid = (survey_id or "").strip()
        if not sid:
            return {"error": "survey_id is required"}
        fmt = (fmt or "csv").strip().lower()
        if fmt not in ("csv", "xlsx"):
            return {"error": "fmt must be 'csv' or 'xlsx'"}
        if workspace is None:
            return {"error": "this session has no workspace folder to save into"}
        token, base = _auth(secrets)
        if not token:
            return {"error": _SIGNED_OUT}
        try:
            r = httpx.get(
                f"{base}/api/surveys/{sid}/export/{fmt}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=_TIMEOUT * 2,
            )
        except httpx.HTTPError as exc:
            return {"error": f"QualiTaTi unreachable: {exc}"}
        if r.status_code >= 400:
            return {"error": f"QualiTaTi returned {r.status_code}."}
        name = (filename or f"qualitati-survey-{sid}.{fmt}").strip()
        safe = Path(name).name  # never let a filename walk out of the workspace
        target = Path(workspace).expanduser().resolve() / safe
        try:
            target.write_bytes(r.content)
        except OSError as exc:
            return {"error": f"could not save the export: {exc}"}
        return {"ok": True, "path": str(target), "bytes": len(r.content)}

    def _wrap(fn, capability: str):
        return ai.tool(
            fn,
            metadata=ai.ToolMetadata(
                name=fn.__name__,
                category="qualitati",
                risk_level="medium",
                capabilities=[capability],
                # The point of the whole module: personal research data is never pulled
                # without the user saying yes to that specific retrieval.
                requires_approval=True,
            ),
        )

    # Arrays of objects are beyond the signature-derived schema: hand-written ones.
    qualitati_create_survey.__coworker_schema__ = _CREATE_SCHEMA  # type: ignore[attr-defined]
    qualitati_edit_survey.__coworker_schema__ = _EDIT_SCHEMA  # type: ignore[attr-defined]
    return [
        _wrap(qualitati_projects, "qualitati_read"),
        _wrap(qualitati_interviews, "qualitati_read"),
        _wrap(qualitati_interview_transcript, "qualitati_read"),
        _wrap(qualitati_surveys, "qualitati_read"),
        _wrap(qualitati_survey_responses, "qualitati_read"),
        _wrap(qualitati_export_survey, "qualitati_read"),
        _wrap(qualitati_create_survey, "qualitati_write"),
        _wrap(qualitati_edit_survey, "qualitati_write"),
        _wrap(qualitati_publish_survey, "qualitati_write"),
    ]
