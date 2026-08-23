"""The signed-in account's own QualiTaTi data: reachable, capped, and never fetched
without the user's yes (every tool is approval-gated, which `risk.classify` reads as
EXTERNAL — the class the permission engine stops on)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from coworker.qualitati import AUTH_PROFILE
from coworker.risk import RiskClass, classify, is_consequential
from coworker.tools.qualitati_data import qualitati_data_tools


class _Secrets:
    def __init__(self, profile: dict[str, Any] | None) -> None:
        self._profile = profile

    def get(self, key: str) -> Any:
        return self._profile if key == AUTH_PROFILE else None


def _tools(secrets, workspace=None) -> dict[str, Any]:
    return {t.__name__: t for t in qualitati_data_tools(secrets, workspace=workspace)}


SIGNED_IN = _Secrets({"access_token": "jwt-123", "base_url": "https://qt.example"})


def test_every_tool_needs_the_users_approval_before_it_fetches_anything():
    for name, tool in _tools(SIGNED_IN).items():
        meta = getattr(tool, "__aisuite_tool_metadata__", None)
        assert getattr(meta, "requires_approval", False) is True, name
        risk = classify(name, meta)
        assert risk is RiskClass.EXTERNAL and is_consequential(risk), name


def test_signed_out_says_so_instead_of_calling_anything(monkeypatch):
    def _boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("signed out must not reach the network")

    monkeypatch.setattr(httpx, "get", _boom)
    got = _tools(_Secrets(None))["qualitati_projects"]()
    assert "Settings ▸ Models" in got["error"]


def _stub(monkeypatch, payload: Any, *, status: int = 200, seen: list | None = None):
    class _Resp:
        status_code = status
        content = b"col\n1\n"

        def json(self):
            return payload

    def fake_get(url, headers=None, params=None, timeout=None):
        if seen is not None:
            seen.append((url, headers))
        return _Resp()

    monkeypatch.setattr(httpx, "get", fake_get)


def test_it_carries_the_stored_sign_in_and_returns_the_account_s_projects(monkeypatch):
    seen: list = []
    _stub(monkeypatch, [{"uuid": "p1", "title": "Onboarding study"}], seen=seen)
    got = _tools(SIGNED_IN)["qualitati_projects"]()
    assert got["projects"][0]["title"] == "Onboarding study"
    url, headers = seen[0]
    assert url == "https://qt.example/api/interview/projects"
    assert headers["Authorization"] == "Bearer jwt-123"


def test_a_long_transcript_is_trimmed_rather_than_flooding_the_turn(monkeypatch):
    _stub(monkeypatch, {"turns": "x" * 100_000})
    got = _tools(SIGNED_IN)["qualitati_interview_transcript"]("i-1")
    assert "[trimmed]" in got["conversation"]["turns"]
    assert len(got["conversation"]["turns"]) < 100_000


def test_a_huge_response_list_keeps_its_head_and_says_what_it_dropped(monkeypatch):
    _stub(monkeypatch, [{"n": i} for i in range(200)])
    rows = _tools(SIGNED_IN)["qualitati_survey_responses"]("s-1")["responses"]
    assert len(rows) == 51 and "150 more not shown" in rows[-1]


def test_analytics_is_the_same_call_pointed_at_the_summary(monkeypatch):
    seen: list = []
    _stub(monkeypatch, {"n": 12}, seen=seen)
    got = _tools(SIGNED_IN)["qualitati_survey_responses"]("s-1", analytics=True)
    assert got["analytics"] == {"n": 12}
    assert seen[0][0].endswith("/api/surveys/s-1/analytics")


def test_an_expired_sign_in_asks_the_user_to_sign_in_again(monkeypatch):
    _stub(monkeypatch, {}, status=401)
    assert "sign in again" in _tools(SIGNED_IN)["qualitati_surveys"]()["error"]


def test_export_saves_into_the_workspace_and_cannot_be_walked_out_of_it(monkeypatch, tmp_path):
    _stub(monkeypatch, {})
    export = _tools(SIGNED_IN, workspace=tmp_path)["qualitati_export_survey"]
    got = export("s-1", filename="../../escape.csv")
    assert got["ok"] and got["path"] == str(tmp_path / "escape.csv")
    assert (tmp_path / "escape.csv").read_bytes() == b"col\n1\n"
    assert not (tmp_path.parent.parent / "escape.csv").exists()


@pytest.mark.parametrize("bad", ["", "   "])
def test_the_id_arguments_are_required(bad):
    assert "required" in _tools(SIGNED_IN)["qualitati_interviews"](bad)["error"]
    assert "required" in _tools(SIGNED_IN)["qualitati_survey_responses"](bad)["error"]
