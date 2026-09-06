"""App-wide activity (the floating Mimi companion's signal) + bundled-skill seeding."""

from __future__ import annotations

import asyncio
import json

import pytest

from coworker.skills.store import SkillStore


@pytest.fixture(autouse=True)
def _seeding_enabled(monkeypatch):
    """Seeding is globally disabled for the suite (conftest) — THIS file tests it."""
    monkeypatch.setenv("COWORKER_SEED_BUILTIN_SKILLS", "1")

BUILTIN = {
    # authored for MimiWork
    "academic-writing",
    "business-communication",
    # adapted from the user's research-skill library
    "consumer-paper-writing",
    "theory-building",
    "slide-design",
    # curated third-party (ComposioHQ/awesome-claude-skills, addyosmani/agent-skills,
    # sickn33/agentic-awesome-skills) — small, work-relevant, safety-scanned
    "file-organizer",
    "invoice-organizer",
    "meeting-insights-analyzer",
    "internal-comms",
    "content-research-writer",
    "tailored-resume-generator",
    "lead-research-assistant",
    "idea-refine",
    "planning-and-task-breakdown",
    "data-storytelling",
    "deep-research",
    "avoid-ai-writing",
    "survey-generator",
    # authored for the GenAI-for-Business teaching arc
    "agentic-architect",
    # the QualiTaTi/MimiWork brand system — teal tokens, 85 named icon assets,
    # per-medium guides (owner ask 2026-08-30: every customer-facing deliverable
    # should come out on-brand without being asked)
    "mimi-style",
    # emilkowalski/skills — fluid Apple-style interfaces for web deliverables
    "apple-design",
    # humanlayer/skills show-me, adapted: the "Visualize this task" button under a finished
    # turn force-runs it; Mermaid fences draw inline in the transcript (2026-09-06)
    "show-me",
    # One discoverable workflow per QualiTaTi tool exposed by MimiWork. These remain
    # ordinary editable skills; allowed-tools records the exact one-to-one binding.
    "qualitati-projects",
    "qualitati-mimi",
    "qualitati-interviews",
    "qualitati-interview-transcript",
    "qualitati-surveys",
    "qualitati-survey-responses",
    "qualitati-export-survey",
    "qualitati-create-survey",
    "qualitati-edit-survey",
    "qualitati-publish-survey",
}

QUALITATI_TOOL_SKILLS = {
    "qualitati-projects": "qualitati_projects",
    "qualitati-mimi": "qualitati_mimi",
    "qualitati-interviews": "qualitati_interviews",
    "qualitati-interview-transcript": "qualitati_interview_transcript",
    "qualitati-surveys": "qualitati_surveys",
    "qualitati-survey-responses": "qualitati_survey_responses",
    "qualitati-export-survey": "qualitati_export_survey",
    "qualitati-create-survey": "qualitati_create_survey",
    "qualitati-edit-survey": "qualitati_edit_survey",
    "qualitati-publish-survey": "qualitati_publish_survey",
}


# ── bundled skills ───────────────────────────────────────────────────────────


def test_bare_store_does_not_seed(tmp_path):
    store = SkillStore(tmp_path / "skills")
    assert not (tmp_path / "skills").exists() or not any((tmp_path / "skills").iterdir())
    assert {r["name"] for r in store.rows(None)} == set()


def test_seeding_installs_the_builtin_catalog(tmp_path):
    store = SkillStore(tmp_path / "skills", seed_builtin=True)
    names = {r["name"] for r in store.rows(None)}
    assert BUILTIN <= names
    # Seeded skills are ordinary global skills — folder-is-truth.
    assert (tmp_path / "skills" / "theory-building" / "SKILL.md").is_file()
    # The slide skill carries its resources, not just the manifest.
    assert (tmp_path / "skills" / "slide-design" / "STYLE_PRESETS.md").is_file()
    # The brand skill carries its ASSETS — a style guide without the icons it
    # names would send every deliverable hunting for missing files.
    assert (tmp_path / "skills" / "mimi-style" / "assets" / "tiles" / "tile-survey.png").is_file()
    assert (tmp_path / "skills" / "mimi-style" / "references" / "social.md").is_file()


def test_descriptions_survive_the_single_line_frontmatter_parser(tmp_path):
    """The bundled SKILL.md files must parse under the line-based frontmatter
    reader — a multi-line YAML description would silently come out empty."""
    from coworker.skills.base import SkillLoader

    SkillStore(tmp_path / "skills", seed_builtin=True)
    loader = SkillLoader([tmp_path / "skills"])
    for name in BUILTIN:
        skill = loader.get(name)
        assert skill is not None, name
        assert len(skill.description) > 80, name
        assert len(skill.instructions) > 500, name
    assert "Consumer behavior paper building" in loader.get("consumer-paper-writing").description
    assert loader.get("theory-building").description.startswith("Theory building")


def test_deleted_builtin_stays_deleted(tmp_path):
    import shutil

    SkillStore(tmp_path / "skills", seed_builtin=True)
    shutil.rmtree(tmp_path / "skills" / "slide-design")
    # Restart: the marker remembers it was seeded once — deletion is intent.
    store2 = SkillStore(tmp_path / "skills", seed_builtin=True)
    assert "slide-design" not in {r["name"] for r in store2.rows(None)}
    marker = json.loads((tmp_path / "skills" / ".builtin-seeded.json").read_text())
    assert "slide-design" in marker


def test_user_edits_are_never_overwritten(tmp_path):
    SkillStore(tmp_path / "skills", seed_builtin=True)
    md = tmp_path / "skills" / "academic-writing" / "SKILL.md"
    md.write_text(md.read_text() + "\nMY EDIT", encoding="utf-8")
    SkillStore(tmp_path / "skills", seed_builtin=True)
    assert md.read_text().endswith("MY EDIT")


def test_every_qualitati_tool_has_one_preinstalled_skill(tmp_path):
    from coworker.skills.base import SkillLoader
    from coworker.tools.qualitati_data import qualitati_data_tools
    from coworker.tools.qualitati_tools import qualitati_tools

    class _SignedOutSecrets:
        def get(self, _key):
            return None

    tool_names = {
        tool.__name__
        for tool in [
            *qualitati_tools(),
            *qualitati_data_tools(_SignedOutSecrets(), workspace=tmp_path),
        ]
    }
    assert set(QUALITATI_TOOL_SKILLS.values()) == tool_names

    SkillStore(tmp_path / "skills", seed_builtin=True)
    loader = SkillLoader([tmp_path / "skills"])
    for skill_name, tool_name in QUALITATI_TOOL_SKILLS.items():
        skill = loader.get(skill_name)
        assert skill is not None, skill_name
        assert skill.allowed_tools == [tool_name]
        assert f"`{tool_name}`" in skill.instructions


# ── activity ─────────────────────────────────────────────────────────────────


def _manager(tmp_path):
    from coworker.server.manager import SessionManager

    return SessionManager(workspace=tmp_path, data_dir=tmp_path / "state")


def test_activity_tracks_session_turns(tmp_path):
    mgr = _manager(tmp_path)
    assert mgr.activity() == {
        "busy": False,
        "running_sessions": 0,
        "running_automations": 0,
        "pending_input": 0,
        "detail": None,
        "items": [],
    }
    mgr.mark_running("s1")
    assert mgr.activity()["busy"] is True
    assert mgr.activity()["running_sessions"] == 1
    # Mission-control row: the running session, with a start time and a title
    # fallback (no store row yet mid-first-turn).
    (row,) = mgr.activity()["items"]
    assert row["kind"] == "session" and row["id"] == "s1"
    assert row["title"] == "New session" and row["started_at"] > 0
    mgr.mark_idle("s1")
    assert mgr.activity()["busy"] is False
    assert mgr.activity()["items"] == []


def test_activity_flip_broadcasts_once(tmp_path):
    """Only busy-boolean FLIPS reach /ws/events — two concurrent turns emit one
    'busy' frame, and the frame goes to registered event clients."""
    mgr = _manager(tmp_path)
    frames: list[dict] = []

    async def scenario():
        async def sink(message):
            frames.append(message)

        mgr.register_event_client(sink)
        mgr.mark_running("s1")
        mgr.mark_running("s2")  # still busy — no second frame
        await asyncio.sleep(0)  # let the scheduled broadcasts run
        mgr.mark_idle("s1")  # still busy (s2 running) — no frame
        mgr.mark_idle("s2")  # idle — one frame
        await asyncio.sleep(0)

    asyncio.run(scenario())
    activity = [f for f in frames if f["type"] == "activity"]
    assert [f["data"]["busy"] for f in activity] == [True, False]


def test_activity_endpoint(tmp_path):
    from fastapi.testclient import TestClient

    from coworker.server.app import create_app

    mgr = _manager(tmp_path)
    app = create_app(mgr)
    with TestClient(app) as client:
        r = client.get("/v1/activity")
        assert r.status_code == 200
        assert r.json() == {
            "busy": False,
            "running_sessions": 0,
            "running_automations": 0,
            "pending_input": 0,
            "detail": None,
            "items": [],
        }


def test_interrupt_endpoint_rejects_idle_session(tmp_path):
    from fastapi.testclient import TestClient

    from coworker.server.app import create_app

    mgr = _manager(tmp_path)
    app = create_app(mgr)
    with TestClient(app) as client:
        r = client.post("/v1/sessions/nope/interrupt")
        assert r.status_code == 200
        assert r.json()["ok"] is False


def test_fork_endpoint_round_trip(tmp_path):
    from fastapi.testclient import TestClient

    from coworker.server.app import create_app
    from coworker.sessions import SessionRecord

    mgr = _manager(tmp_path)
    mgr.session_store.save(
        SessionRecord(
            session_id="orig",
            workspace=str(tmp_path),
            model="m",
            mode="interactive",
            messages=[{"role": "user", "content": "hello"}],
        )
    )
    app = create_app(mgr)
    with TestClient(app) as client:
        r = client.post("/v1/sessions/orig/fork").json()
        assert r["ok"] is True and r["id"] != "orig"
        assert r["workspace"] == str(tmp_path)
        assert mgr.session_store.load(r["id"]).messages == [
            {"role": "user", "content": "hello"}
        ]
        assert client.post("/v1/sessions/ghost/fork").json()["ok"] is False


# ── legacy QualiTaTi model-id migration ─────────────────────────────────────


def test_legacy_qualitati_default_migrates_to_hound(tmp_path):
    import json

    from coworker.server.manager import SessionManager

    state = tmp_path / "state"
    state.mkdir()
    (state / "prefs.json").write_text(
        json.dumps({"default_model": "qualitati:mimi", "models": ["qualitati:deepseek-v4-flash"]})
    )
    mgr = SessionManager(workspace=tmp_path, data_dir=state)
    assert mgr.model == "qualitati:mimi-hound"
    menu = mgr._curated_models()
    assert "qualitati:mimi" not in menu
    assert "qualitati:mimi-hound" in menu and "qualitati:mimi-puppy" in menu
    # Persisted, so the raw-id row never comes back.
    saved = json.loads((state / "prefs.json").read_text())
    assert saved["default_model"] == "qualitati:mimi-hound"
    assert saved["models"] == ["qualitati:mimi-puppy"]


# ── automation creation: folder binding + uploaded files ────────────────────


def test_automation_binds_to_a_chosen_folder_and_saves_files(tmp_path):
    import base64

    from coworker.server.manager import SessionManager

    mgr = SessionManager(workspace=tmp_path, data_dir=tmp_path / "state")
    project = tmp_path / "course-material"
    project.mkdir()
    res = mgr.create_automation(
        {
            "title": "Weekly digest",
            "instructions": "Summarize the readings.",
            "cron": "0 9 * * 1",
            "workspace": str(project),
            "files": [{"name": "syllabus.md", "data_b64": base64.b64encode(b"# Week 1").decode()}],
        }
    )
    assert res["ok"], res
    assert res["task"]["workspace"] == str(project)
    assert (project / "attachments" / "syllabus.md").read_text() == "# Week 1"
    # The agent is told where the material lives.
    task = mgr.task_store.get(res["task"]["id"])
    assert "./attachments/" in task.instructions and "syllabus.md" in task.instructions


def test_automation_rejects_bad_folder_and_bad_files(tmp_path):
    from coworker.server.manager import SessionManager

    mgr = SessionManager(workspace=tmp_path, data_dir=tmp_path / "state")
    base = {"title": "t", "instructions": "i", "cron": "0 9 * * *"}
    assert "folder not found" in mgr.create_automation({**base, "workspace": "/no/such/dir"})["error"]
    # Path parts are stripped — a traversal name lands INSIDE attachments/, never outside.
    res = mgr.create_automation({**base, "files": [{"name": "../evil.sh", "data_b64": ""}]})
    assert res["ok"]
    from pathlib import Path

    ws = Path(res["task"]["workspace"])
    assert (ws / "attachments" / "evil.sh").exists()
    assert not (ws.parent / "evil.sh").exists()
    assert "invalid encoding" in mgr.create_automation(
        {**base, "files": [{"name": "ok.txt", "data_b64": "%%%"}]}
    )["error"]


def test_blueprint_export_is_shareable_and_leak_free(tmp_path, monkeypatch):
    from coworker.server.manager import SessionManager

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    mgr = SessionManager(workspace=tmp_path, data_dir=tmp_path / "state")
    created = mgr.create_automation(
        {"title": "Standup notes", "instructions": "Summarize.", "cron": "0 9 * * 1-5"}
    )
    res = mgr.export_automation_blueprint(created["task"]["id"])
    assert res["ok"], res
    bp = res["blueprint"]
    assert bp["mimiwork_blueprint"] == 1
    assert bp["title"] == "Standup notes" and bp["schedule"]["cron"] == "0 9 * * 1-5"
    # Nothing machine- or account-specific travels.
    assert "workspace" not in bp and "id" not in bp
    from pathlib import Path

    assert Path(res["path"]).name == "standup-notes.mimiflow.json"
    assert Path(res["path"]).is_file()


def test_pending_inbox_items_flip_the_activity_signal(tmp_path):
    """A parked approval must reach the companion as pending_input — and the
    inbox's on_change hook must announce the flip (push, not poll)."""
    import asyncio as _asyncio

    mgr = _manager(tmp_path)
    frames: list[dict] = []

    async def scenario():
        async def sink(message):
            frames.append(message)

        mgr.register_event_client(sink)
        item = mgr.inbox.add_approval("s1", "Approve: run_shell", body="rm -rf x")
        await _asyncio.sleep(0)
        assert mgr.activity()["pending_input"] == 1
        mgr.inbox.resolve(item.id, "deny")
        await _asyncio.sleep(0)
        assert mgr.activity()["pending_input"] == 0

    _asyncio.run(scenario())
    signals = [(f["data"]["busy"], f["data"]["pending_input"]) for f in frames if f["type"] == "activity"]
    assert (False, 1) in signals and (False, 0) in signals
