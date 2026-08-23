"""Read the signed-in user's own QualiTaTi data — projects, interviews, surveys, responses.

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
            return {"error": f"QualiTaTi returned {r.status_code}."}
        try:
            return r.json()
        except ValueError:
            return {"error": "QualiTaTi returned something that isn't JSON."}

    def qualitati_projects() -> dict:
        """List the interview projects in the user's QualiTaTi account (uuid, title, counts).
        Start here when the user refers to "my project" / "my study" on QualiTaTi."""
        data = _get("/api/interview/projects")
        return data if isinstance(data, dict) and "error" in data else {"projects": _trim(data)}

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

    def qualitati_surveys() -> dict:
        """List the surveys in the user's QualiTaTi account (id, title, response counts)."""
        data = _get("/api/surveys")
        return data if isinstance(data, dict) and "error" in data else {"surveys": _trim(data)}

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

    return [
        _wrap(qualitati_projects, "qualitati_read"),
        _wrap(qualitati_interviews, "qualitati_read"),
        _wrap(qualitati_interview_transcript, "qualitati_read"),
        _wrap(qualitati_surveys, "qualitati_read"),
        _wrap(qualitati_survey_responses, "qualitati_read"),
        _wrap(qualitati_export_survey, "qualitati_read"),
    ]
