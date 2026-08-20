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
    # emilkowalski/skills — fluid Apple-style interfaces for web deliverables
    "apple-design",
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
    }
    mgr.mark_running("s1")
    assert mgr.activity()["busy"] is True
    assert mgr.activity()["running_sessions"] == 1
    mgr.mark_idle("s1")
    assert mgr.activity()["busy"] is False


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
        }


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

