"""QualiTaTi project tools — the coworker works on the user's QualiTaTi research.

Two layers, matching how much surface each needs:

- ``qualitati_projects`` lists the signed-in account's research projects
  directly from the REST API (read-only).
- ``qualitati_mimi`` hands a request to **Mimi, QualiTaTi's own research
  agent**, server-side (`/api/assistant/.../chat`). Mimi has the full project
  toolset there — read transcripts, run statistics on survey data, edit
  survey questions, run ThemeLens, create projects — with QualiTaTi's own
  confirmation gates and billing. Delegating beats re-implementing 47 tools
  against private endpoints: MimiWork stays a thin, honest client and server
  policy (limits, confirmation, credit costs) applies unchanged.

Auth: the QualiTaTi sign-in (Settings → Models) stores a JWT (14-day) and a
personal API key in the SecretStore. Projects prefer the API key (never
expires); the assistant endpoint is JWT-only. A 401 tells the user to sign in
again rather than guessing.
"""

from __future__ import annotations

import json
from typing import Any, Optional
from urllib import error, request

import aisuite as ai

_TIMEOUT = 180.0  # Mimi turns can chain many tools server-side


def _load_auth() -> dict[str, Any]:
    from ..qualitati import AUTH_PROFILE, DEFAULT_BASE, PROVIDER_PROFILE
    from ..secrets import SecretStore

    secrets = SecretStore()
    auth = secrets.get(AUTH_PROFILE) or {}
    provider = secrets.get(PROVIDER_PROFILE) or {}
    return {
        "base": (auth.get("base_url") or DEFAULT_BASE).rstrip("/"),
        "jwt": auth.get("access_token"),
        "api_key": provider.get("api_key") if isinstance(provider, dict) else None,
    }


_NOT_SIGNED_IN = {
    "error": "Not signed in to QualiTaTi. Ask the user to sign in from Settings → Models → QualiTaTi account."
}
_EXPIRED = {
    "error": "The QualiTaTi sign-in has expired. Ask the user to sign in again from Settings → Models → QualiTaTi account."
}


def _call(
    method: str,
    url: str,
    headers: dict[str, str],
    body: Optional[dict] = None,
) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(url, data=data, method=method, headers={
        **headers,
        **({"Content-Type": "application/json"} if data else {}),
    })
    try:
        with request.urlopen(req, timeout=_TIMEOUT) as r:
            return r.status, json.load(r)
    except error.HTTPError as e:
        try:
            detail = json.load(e)
        except Exception:
            detail = {"detail": e.reason}
        return e.code, detail
    except Exception as e:  # DNS, timeout, refused
        return 0, {"detail": f"QualiTaTi unreachable: {e}"}


_PROJECTS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "qualitati_projects",
        "description": (
            "List the signed-in user's QualiTaTi research projects (AI interviews and "
            "surveys): names, ids, and types. Use this first to find the project the "
            "user means, then hand project work to `qualitati_mimi`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_type": {
                    "type": "string",
                    "enum": ["interview", "survey"],
                    "description": "Optional filter by project type.",
                }
            },
        },
    },
}

_MIMI_SCHEMA = {
    "type": "function",
    "function": {
        "name": "qualitati_mimi",
        "description": (
            "Ask Mimi — QualiTaTi's own research agent — to work on the user's QualiTaTi "
            "projects, server-side. Mimi can read interview transcripts and coded segments, "
            "run real statistics on survey responses (descriptives, reliability, t-test/"
            "ANOVA, chi-square, correlation, regression, moderation/mediation), edit survey "
            "questions and interview outlines, check data quality, run ThemeLens analysis, "
            "and create new projects. Write one clear request per call; pass project_uuid "
            "when the user has named a project (find it with `qualitati_projects`). The "
            "conversation persists across calls in this session, so follow-ups can build on "
            "earlier answers. Destructive or credit-consuming actions are confirmation-gated "
            "server-side — relay Mimi's confirmation question to the user before repeating "
            "the request with the user's explicit yes."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "The request for Mimi, in plain language.",
                },
                "project_uuid": {
                    "type": "string",
                    "description": "UUID of the QualiTaTi project this is about (optional).",
                },
                "new_conversation": {
                    "type": "boolean",
                    "description": "Start a fresh Mimi conversation instead of continuing this session's.",
                },
            },
            "required": ["message"],
        },
    },
}


def qualitati_tools() -> list:
    # One Mimi conversation per MimiWork session (this factory is built per session).
    state: dict[str, Any] = {"conversation_id": None}

    def qualitati_projects(project_type: Optional[str] = None) -> dict[str, Any]:
        auth = _load_auth()
        key, jwt = auth["api_key"], auth["jwt"]
        if not (key or jwt):
            return dict(_NOT_SIGNED_IN)
        headers = {"X-API-Key": key} if key else {"Authorization": f"Bearer {jwt}"}
        url = auth["base"] + "/api/projects"
        if project_type in ("interview", "survey"):
            url += f"?project_type={project_type}"
        status, body = _call("GET", url, headers)
        if status == 401:
            return dict(_EXPIRED)
        if status != 200:
            return {"error": f"QualiTaTi /api/projects returned {status}", "detail": body}
        projects = body if isinstance(body, list) else body.get("projects") or []
        slim = []
        for p in projects:
            if not isinstance(p, dict):
                continue
            slim.append(
                {
                    k: p.get(k)
                    for k in (
                        "id",
                        "uuid",
                        "name",
                        "project_type",
                        "interview_type",
                        "created_at",
                    )
                    if p.get(k) is not None
                }
            )
        return {"count": len(slim), "projects": slim}

    def qualitati_mimi(
        message: str,
        project_uuid: Optional[str] = None,
        new_conversation: bool = False,
        _retried: bool = False,
    ) -> dict[str, Any]:
        auth = _load_auth()
        jwt = auth["jwt"]
        if not jwt:
            return dict(_NOT_SIGNED_IN)
        headers = {"Authorization": f"Bearer {jwt}"}
        base = auth["base"]

        if new_conversation:
            state["conversation_id"] = None
        if state["conversation_id"] is None:
            status, body = _call(
                "POST", base + "/api/assistant/conversations", headers, {"title": "MimiWork"}
            )
            if status == 401:
                return dict(_EXPIRED)
            if status not in (200, 201) or not isinstance(body, dict) or body.get("id") is None:
                return {"error": f"could not open a Mimi conversation ({status})", "detail": body}
            state["conversation_id"] = body["id"]

        payload: dict[str, Any] = {"message": str(message or "")}
        if project_uuid:
            payload["project_uuid"] = project_uuid
            payload["source_type"] = "project"
        status, body = _call(
            "POST",
            f"{base}/api/assistant/conversations/{state['conversation_id']}/chat",
            headers,
            payload,
        )
        if status == 401:
            return dict(_EXPIRED)
        if status == 404 and not _retried:
            # Conversation deleted server-side — recover once with a fresh one.
            state["conversation_id"] = None
            return qualitati_mimi(message, project_uuid=project_uuid, _retried=True)
        if status == 429:
            return {"error": "Mimi's daily usage limit is reached on this QualiTaTi account.", "detail": body}
        if status != 200 or not isinstance(body, dict):
            return {"error": f"Mimi returned {status}", "detail": body}

        reply = (body.get("assistant_message") or {}).get("content") or ""
        actions = [e.get("name") for e in body.get("tool_events") or [] if isinstance(e, dict)]
        out: dict[str, Any] = {"reply": reply}
        if actions:
            out["actions_taken"] = actions
        return out

    qualitati_projects.__name__ = "qualitati_projects"
    qualitati_projects.__doc__ = _PROJECTS_SCHEMA["function"]["description"]
    qualitati_projects.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="qualitati_projects",
        category="qualitati",
        risk_level="low",
        capabilities=["read"],
        requires_approval=False,
    )
    qualitati_projects.__coworker_schema__ = _PROJECTS_SCHEMA

    qualitati_mimi.__name__ = "qualitati_mimi"
    qualitati_mimi.__doc__ = _MIMI_SCHEMA["function"]["description"]
    qualitati_mimi.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="qualitati_mimi",
        category="qualitati",
        risk_level="medium",
        capabilities=["read", "write"],
        requires_approval=False,
    )
    qualitati_mimi.__coworker_schema__ = _MIMI_SCHEMA

    return [qualitati_projects, qualitati_mimi]
