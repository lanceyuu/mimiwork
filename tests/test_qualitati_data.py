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
    _stub(monkeypatch, [{"uuid": "p1", "name": "Onboarding study", "project_type": "survey"}], seen=seen)
    got = _tools(SIGNED_IN)["qualitati_projects"]()
    assert got["projects"][0]["name"] == "Onboarding study"
    url, headers = seen[0]
    assert url == "https://qt.example/api/projects"
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


# ── surveys: listing is per project, and building them (owner ask 2026-09-04) ──────


class _Server:
    """A fake QualiTaTi: answers GETs from a route table and records every write."""

    def __init__(self, routes: dict[str, Any]):
        self.routes = routes
        self.writes: list[tuple[str, str, dict | None]] = []
        self.fail: dict[str, tuple[int, Any]] = {}
        self._ids = 100

    def install(self, monkeypatch):
        server = self

        class _Resp:
            def __init__(self, status, payload):
                self.status_code, self._payload = status, payload
                self.content = b"{}"
                self.text = str(payload)

            def json(self):
                return self._payload

        def get(url, headers=None, params=None, timeout=None):
            path = url.replace("https://qt.example", "")
            key = path + ("?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else "")
            if key in server.routes:
                return _Resp(200, server.routes[key])
            if path in server.routes:
                return _Resp(200, server.routes[path])
            return _Resp(404, {"detail": "Not found"})

        def write(method):
            def call(url, headers=None, json=None, files=None, timeout=None):
                path = url.replace("https://qt.example", "")
                server.writes.append((method, path, json if json is not None else ({"files": list(files)} if files else None)))
                if path in server.fail:
                    status, payload = server.fail[path]
                    return _Resp(status, payload)
                server._ids += 1
                if path.endswith("/publish"):
                    return _Resp(200, {"status": "published", "share_url": "https://qualitati.com/s/7?t=tok"})
                if path.endswith("/upload-image"):
                    return _Resp(200, {"url": f"/api/surveys/images/img{server._ids}"})
                return _Resp(200, {"id": server._ids})

            return call

        monkeypatch.setattr(httpx, "get", get)
        for m in ("post", "put", "delete"):
            monkeypatch.setattr(httpx, m, write(m))
        return self


def test_surveys_are_listed_per_survey_project_not_from_the_bare_endpoint(monkeypatch):
    """GET /api/surveys demands a project_id (422 without one — the whole bug); the
    tool walks the survey-type projects and gathers, with the links a person needs."""
    server = _Server({
        "/api/projects?project_type=survey": [{"id": 5, "name": "Luxury study"}, {"id": 6, "name": "Empty"}],
        "/api/surveys?project_id=5": [
            {"id": 9, "title": "Gucci on Amazon", "status": "published", "share_token": "abc", "response_count": 12, "questions": [{}, {}]},
        ],
        "/api/surveys?project_id=6": [],
    }).install(monkeypatch)
    got = _tools(SIGNED_IN)["qualitati_surveys"]()
    assert got["count"] == 1
    row = got["surveys"][0]
    assert row["title"] == "Gucci on Amazon" and row["project"] == "Luxury study"
    assert row["share_url"] == "https://qualitati.com/s/9?t=abc"
    assert row["builder_url"] == "https://qualitati.com/survey/5/9/builder"
    assert row["questions"] == 2 and row["responses"] == 12
    assert server.writes == []


def test_one_survey_comes_back_with_its_questions_and_blocks(monkeypatch):
    _Server({
        "/api/surveys/9": {
            "id": 9, "project_id": 5, "title": "T", "status": "draft",
            "blocks": [{"id": 1, "title": "Conditions", "is_randomizer": True, "children": []}],
            "questions": [{"id": 40, "type": "matrix", "prompt": "Rate", "options_json": ["1", "7"], "rows": ["a"], "columns": ["1", "7"], "block_id": 1}],
        },
    }).install(monkeypatch)
    got = _tools(SIGNED_IN)["qualitati_surveys"](survey_id="9")
    q = got["survey"]["questions"][0]
    assert q["id"] == 40 and q["rows"] == ["a"] and q["block_id"] == 1
    assert got["survey"]["blocks"][0]["title"] == "Conditions"


def test_a_422_says_what_the_server_wanted(monkeypatch):
    class _Resp:
        status_code = 422
        content = b"x"
        text = "raw"

        def json(self):
            return {"detail": [{"loc": ["query", "project_id"], "msg": "Field required"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())
    got = _tools(SIGNED_IN)["qualitati_surveys"](project_id="5")
    assert got["error"] == "QualiTaTi returned 422: project_id: Field required"


def test_create_builds_project_survey_blocks_and_questions_in_order(monkeypatch, tmp_path):
    (tmp_path / "stimulus_A.png").write_bytes(b"\x89PNG fake")
    server = _Server({"/api/surveys/101": {"blocks": []}}).install(monkeypatch)
    tool = _tools(SIGNED_IN, workspace=tmp_path)["qualitati_create_survey"]
    got = tool(
        title="Gucci channel study",
        description="Handbag on Amazon vs flagship",
        questions=[
            {"type": "scenario", "prompt": "Imagine…", "image": "stimulus_A.png", "block": "Condition A"},
            {"type": "likert", "prompt": "Gucci is luxurious", "min": 1, "max": 7, "min_label": "Strongly disagree", "max_label": "Strongly agree", "variable_name": "lux 1"},
            {"type": "grid", "prompt": "Rate the brand", "rows": ["exclusive", "elite"], "columns": ["1", "2", "3"]},
            {"type": "bipolar", "prompt": "Bad — Good", "min_label": "Bad", "max_label": "Good"},
            {"type": "checkbox", "prompt": "Pick", "options": ["a", "b"]},
            {"type": "number", "prompt": "Age", "min": 18, "max": 99},
        ],
        blocks=[{"title": "Conditions", "randomizer": True, "children": ["Condition A", "Condition B"]}],
        language="en",
    )
    assert got["ok"] is True and got["problems"] == [], got
    assert got["questions_added"] == 6
    assert got["builder_url"] == f"https://qualitati.com/survey/{got['project_id']}/{got['survey_id']}/builder"

    calls = [(m, p) for m, p, _ in server.writes]
    bodies = {p: b for _, p, b in server.writes}
    # 1. the study project, survey-typed — an interview project cannot host a survey
    assert calls[0] == ("post", "/api/projects")
    project = server.writes[0][2]
    assert project["project_type"] == "survey" and project["name"] == "Gucci channel study"
    assert project["interview_language"] == "ENGLISH"
    # 2. the survey inside it
    assert calls[1] == ("post", "/api/surveys")
    assert server.writes[1][2]["project_id"] == 101 and server.writes[1][2]["language_default"] == "en"
    sid = got["survey_id"]
    # 3. blocks: the randomizer, then its children under it
    blocks = [b for m, p, b in server.writes if p == f"/api/surveys/{sid}/blocks"]
    assert blocks[0] == {"title": "Conditions", "is_randomizer": True, "randomizer_pick_count": 1}
    assert blocks[1]["title"] == "Condition A" and blocks[1]["parent_block_id"] == got["blocks"]["Conditions"]
    # 4. the stimulus image went up first, then the question carries its URL and lands in its block
    assert ("post", "/api/surveys/upload-image") in calls
    questions = [b for m, p, b in server.writes if p == f"/api/surveys/{sid}/questions"]
    assert questions[0]["type"] == "info_text" and questions[0]["prompt_image_url"].startswith("/api/surveys/images/")
    assert questions[0]["required"] is False
    # Every question carries a variable name (the server insists): given, else derived.
    assert questions[0]["variable_name"] == "imagine"
    assert questions[2]["variable_name"] == "rate_the_brand"
    moves = [(p, b) for m, p, b in server.writes if p.endswith("/move")]
    assert moves == [(f"/api/surveys/{sid}/questions/{got['questions'][0]['id']}/move", {"block_id": got["blocks"]["Condition A"]})]
    # 5. the shapes QualiTaTi stores
    likert = questions[1]
    assert likert["type"] == "rating_scale" and likert["options_json"] == ["1", "2", "3", "4", "5", "6", "7"]
    assert likert["validation_json"] == {"min": 1, "max": 7, "min_label": "Strongly disagree", "max_label": "Strongly agree"}
    assert likert["variable_name"] == "lux_1"
    assert questions[2]["type"] == "matrix" and questions[2]["rows"] == ["exclusive", "elite"] and questions[2]["columns"] == ["1", "2", "3"]
    assert questions[3]["type"] == "bipolar_scale" and questions[3]["options_json"] == ["Bad", "Good"]
    assert questions[3]["validation_json"] == {"min": 1, "max": 7}
    assert questions[4]["type"] == "multi_choice" and questions[4]["options_json"] == ["a", "b"]
    assert questions[5]["validation_json"] == {"min": 18, "max": 99}
    assert bodies  # touched


def test_create_refuses_bad_questions_before_writing_anything(monkeypatch, tmp_path):
    server = _Server({}).install(monkeypatch)
    tool = _tools(SIGNED_IN, workspace=tmp_path)["qualitati_create_survey"]
    got = tool(title="T", questions=[{"type": "hologram", "prompt": "x"}, {"type": "choice", "prompt": "y", "options": ["only one"]}, {"type": "text"}])
    assert "error" in got
    assert got["problems"][0].startswith("question 1: unknown question type 'hologram'")
    assert "at least two options" in got["problems"][1]
    assert "needs a prompt" in got["problems"][2]
    assert server.writes == []


def test_images_come_only_from_the_workspace(monkeypatch, tmp_path):
    server = _Server({}).install(monkeypatch)
    tool = _tools(SIGNED_IN, workspace=tmp_path)["qualitati_create_survey"]
    got = tool(title="T", questions=[{"type": "info_text", "prompt": "x", "image": "../../etc/passwd"}])
    assert "inside the session" in got["problems"][0]
    assert server.writes == []


def test_publish_runs_the_preflight_and_stops_on_errors(monkeypatch):
    server = _Server({
        "/api/surveys/9/preflight": {"status": "errors", "findings": [{"severity": "error", "message": "no questions"}]},
    }).install(monkeypatch)
    got = _tools(SIGNED_IN)["qualitati_publish_survey"]("9")
    assert "pre-publish check" in got["error"] and got["findings"][0]["message"] == "no questions"
    assert server.writes == []

    server.routes["/api/surveys/9/preflight"] = {"status": "ready", "findings": [{"severity": "warning", "message": "short"}]}
    got = _tools(SIGNED_IN)["qualitati_publish_survey"]("9")
    assert got["ok"] is True and got["share_url"] == "https://qualitati.com/s/7?t=tok"
    assert got["warnings"][0]["message"] == "short"
    assert server.writes == [("post", "/api/surveys/9/publish", None)]


def test_edit_deletes_and_adds_into_existing_blocks(monkeypatch):
    server = _Server({
        "/api/surveys/9": {"blocks": [{"id": 3, "title": "Demographics", "children": [{"id": 4, "title": "Inner"}]}]},
    }).install(monkeypatch)
    got = _tools(SIGNED_IN)["qualitati_edit_survey"](
        survey_id="9", title="New title", delete_question_ids=[40], add_questions=[{"type": "yes_no", "prompt": "Ok?", "block": "Inner"}]
    )
    assert got["ok"] is True and got["deleted_question_ids"] == [40] and got["added"][0]["block"] == "Inner"
    assert ("put", "/api/surveys/9", {"title": "New title"}) in server.writes
    assert ("delete", "/api/surveys/9/questions/40", None) in server.writes
    assert any(p.endswith("/move") and b == {"block_id": 4} for _, p, b in server.writes)


def test_variable_names_are_unique_within_a_survey(monkeypatch):
    server = _Server({"/api/surveys/101": {"blocks": []}}).install(monkeypatch)
    _tools(SIGNED_IN)["qualitati_create_survey"](
        title="T", questions=[{"type": "text", "prompt": "Why?"}, {"type": "text", "prompt": "Why?"}, {"type": "text", "prompt": "Why?", "variable_name": "why"}]
    )
    names = [b["variable_name"] for _, p, b in server.writes if p.endswith("/questions")]
    assert names == ["why", "why_2", "why_3"]


def test_writes_are_gated_like_the_reads():
    tools = _tools(SIGNED_IN)
    for name in ("qualitati_create_survey", "qualitati_edit_survey", "qualitati_publish_survey"):
        meta = tools[name].__aisuite_tool_metadata__
        assert meta.requires_approval is True and "qualitati_write" in meta.capabilities
