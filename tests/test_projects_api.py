"""PROJECTS — a project GROUPS sessions and nothing else (2026-08-31).

It has no folder, no instructions file and no memory scope of its own. It used to BE a
workspace folder, which meant "file this conversation under X" and "put its files in X"
were the same act and neither could happen without the other. Now `sessions.project_id`
carries membership and `sessions.workspace` goes back to meaning only where files land.

These tests pin the REST surface the sidebar's Projects band stands on, and — most
importantly — that grouping never moves anybody's files.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from coworker.providers import ModelCapabilities, ProviderClient
from coworker.server import SessionManager, create_app


class _StubProvider(ProviderClient):
    def complete(self, **kwargs):  # pragma: no cover
        raise NotImplementedError

    def capabilities(self, model):
        return ModelCapabilities()


def _fixture(tmp_path):
    manager = SessionManager(workspace=tmp_path, provider=_StubProvider())
    return TestClient(create_app(manager)), manager


def _session(manager, session_id, workspace):
    from coworker.conversations import SessionRecord

    manager.session_store.save(
        SessionRecord(
            session_id=session_id,
            workspace=str(workspace),
            model="m",
            mode="interactive",
            messages=[{"role": "user", "content": "hi"}],
            title="hi",
        )
    )


def _make(client, name="Fieldwork", emoji=""):
    body = client.post("/v1/projects", json={"name": name, "emoji": emoji}).json()
    assert body["ok"], body
    return body["project"]["id"]


def test_a_project_needs_no_folder(tmp_path):
    """The whole point: you can group conversations without nominating a directory."""
    client, _ = _fixture(tmp_path)
    pid = _make(client, "Reading group", "📚")

    rows = client.get("/v1/projects").json()["projects"]
    row = next(r for r in rows if r["id"] == pid)
    assert row["name"] == "Reading group" and row["emoji"] == "📚"
    assert "path" not in row, "a group must not carry a folder"
    assert row["sessions"] == 0


def test_grouping_a_session_never_moves_its_files(tmp_path):
    """The one invariant worth guarding. Membership changed; the workspace — where the
    session's documents actually live — must be exactly as it was."""
    client, manager = _fixture(tmp_path)
    home = tmp_path / "Thesis chapter 3"
    home.mkdir()
    _session(manager, "s1", home)
    pid = _make(client, "Thesis")

    before = manager.session_store.load("s1").workspace
    assert client.post("/v1/sessions/s1/project", json={"project_id": pid}).json()["ok"]
    after = manager.session_store.load("s1").workspace

    assert after == before == str(home)
    assert home.is_dir(), "the folder itself must be untouched"


def test_a_grouped_session_reports_its_group_and_can_leave_it(tmp_path):
    client, manager = _fixture(tmp_path)
    _session(manager, "s1", tmp_path / "w")
    pid = _make(client)

    client.post("/v1/sessions/s1/project", json={"project_id": pid})
    row = next(s for s in client.get("/v1/sessions").json()["sessions"] if s["session_id"] == "s1")
    assert row["project_id"] == pid

    # Passing no project returns it to the flat list.
    assert client.post("/v1/sessions/s1/project", json={"project_id": None}).json()["ok"]
    row = next(s for s in client.get("/v1/sessions").json()["sessions"] if s["session_id"] == "s1")
    assert row["project_id"] is None


def test_the_group_count_reflects_its_live_members(tmp_path):
    client, manager = _fixture(tmp_path)
    for sid in ("s1", "s2"):
        _session(manager, sid, tmp_path / "w")
    pid = _make(client)
    for sid in ("s1", "s2"):
        client.post(f"/v1/sessions/{sid}/project", json={"project_id": pid})

    row = next(r for r in client.get("/v1/projects").json()["projects"] if r["id"] == pid)
    assert row["sessions"] == 2


def test_rename_emoji_pin_archive_round_trip(tmp_path):
    client, _ = _fixture(tmp_path)
    pid = _make(client, "Untitled")

    out = client.patch(
        "/v1/projects", json={"id": pid, "name": "Interview study", "emoji": "🎤", "pinned": True}
    ).json()
    assert out["ok"] and out["project"]["name"] == "Interview study"
    assert out["project"]["emoji"] == "🎤" and out["project"]["pinned"] is True

    assert client.patch("/v1/projects", json={"id": pid, "archived": True}).json()["ok"]
    row = next(r for r in client.get("/v1/projects").json()["projects"] if r["id"] == pid)
    assert row["archived"] is True


def test_deleting_a_group_returns_its_conversations_to_the_flat_list(tmp_path):
    """A group is how you file things. Removing the folder they were filed under must
    not shred the conversations — they come back to the flat list, intact."""
    client, manager = _fixture(tmp_path)
    _session(manager, "s1", tmp_path / "w")
    pid = _make(client)
    client.post("/v1/sessions/s1/project", json={"project_id": pid})

    out = client.delete(f"/v1/projects?id={pid}").json()
    assert out["ok"] and out["deleted_sessions"] == 0 and out["ungrouped"] == 1

    assert manager.session_store.load("s1") is not None, "the conversation must survive"
    row = next(s for s in client.get("/v1/sessions").json()["sessions"] if s["session_id"] == "s1")
    assert row["project_id"] is None


def test_deleting_a_group_takes_its_conversations_only_when_asked(tmp_path):
    client, manager = _fixture(tmp_path)
    _session(manager, "s1", tmp_path / "w")
    pid = _make(client)
    client.post("/v1/sessions/s1/project", json={"project_id": pid})

    out = client.delete(f"/v1/projects?id={pid}&delete_sessions=true").json()
    assert out["ok"] and out["deleted_sessions"] == 1
    assert manager.session_store.load("s1") is None


def test_a_running_conversation_blocks_a_delete_that_would_take_it(tmp_path):
    client, manager = _fixture(tmp_path)
    _session(manager, "s1", tmp_path / "w")
    pid = _make(client)
    client.post("/v1/sessions/s1/project", json={"project_id": pid})
    manager.try_mark_running("s1")

    out = client.delete(f"/v1/projects?id={pid}&delete_sessions=true").json()
    assert out["ok"] is False and "running" in out["error"]
    assert manager.session_store.load("s1") is not None

    # Ungrouping is always safe, though — nothing is destroyed, so nothing to block.
    assert client.delete(f"/v1/projects?id={pid}").json()["ok"]


def test_an_unknown_group_is_refused_not_invented(tmp_path):
    client, manager = _fixture(tmp_path)
    _session(manager, "s1", tmp_path / "w")

    assert client.patch("/v1/projects", json={"id": "grp_nope", "name": "x"}).json()["ok"] is False
    assert client.get("/v1/projects/detail?id=grp_nope").json()["ok"] is False
    out = client.post("/v1/sessions/s1/project", json={"project_id": "grp_nope"}).json()
    assert out["ok"] is False, "a session must not be filed under a group that does not exist"


def test_internal_sessions_are_never_grouped(tmp_path):
    """Automation runs and other `__`-prefixed sessions are machinery, not conversations
    the user files."""
    client, manager = _fixture(tmp_path)
    _session(manager, "__run__r1", tmp_path / "w")
    pid = _make(client)

    out = client.post("/v1/sessions/__run__r1/project", json={"project_id": pid}).json()
    assert out["ok"] is False


def _legacy_db(base, folder, session_ids):
    """A database as it looked BEFORE projects were groups: sessions carrying a
    workspace, no projects table, no project_id. Written with raw SQL because the
    store itself would migrate it on the way in — the point is to hand the new code
    genuinely old data, which is the only upgrade that will ever happen for real."""
    import sqlite3

    base.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(base / "coworker.db")
    conn.execute(
        "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, workspace TEXT, model TEXT, "
        "mode TEXT, title TEXT, agent TEXT DEFAULT 'cowork', n_msgs INTEGER DEFAULT 0, "
        "messages TEXT, extra_roots TEXT, pinned INTEGER DEFAULT 0, archived INTEGER DEFAULT 0, "
        "origin TEXT, origin_label TEXT, auto_title TEXT, renamed INTEGER DEFAULT 0, "
        "updated_at TEXT DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.execute("CREATE TABLE workspaces (path TEXT PRIMARY KEY, last_used TEXT, name TEXT, "
                 "emoji TEXT, pinned INTEGER DEFAULT 0, archived INTEGER DEFAULT 0)")
    conn.execute("INSERT INTO workspaces (path, last_used) VALUES (?, CURRENT_TIMESTAMP)",
                 (str(folder),))
    for sid in session_ids:
        conn.execute(
            "INSERT INTO sessions (session_id, workspace, model, mode, title, n_msgs, messages) "
            "VALUES (?,?,?,?,?,?,?)",
            (sid, str(folder), "m", "interactive", "hi", 1, '[{"role":"user","content":"hi"}]'),
        )
    conn.commit()
    conn.close()


def test_existing_folder_projects_become_groups_without_moving_anything(tmp_path):
    """The upgrade. Every folder that had conversations becomes a group named after it,
    its conversations land inside, and not one workspace path changes."""
    from coworker.conversations import ConversationStore

    base = tmp_path / "state"
    folder = tmp_path / "Online marketing course"
    folder.mkdir(exist_ok=True)
    _legacy_db(base, folder, ("s1", "s2"))

    store = ConversationStore(base)
    groups = store.list_projects()
    assert len(groups) == 1, groups
    assert groups[0]["name"] == "Online marketing course"
    assert groups[0]["sessions"] == 2

    for sid in ("s1", "s2"):
        rec = store.load(sid)
        assert rec.project_id == groups[0]["id"]
        assert rec.workspace == str(folder), "the upgrade must not touch where files live"
    assert folder.is_dir()

    # Idempotent: opening again must not duplicate the group.
    assert len(ConversationStore(base).list_projects()) == 1


def test_a_session_dragged_out_stays_out_across_a_restart(tmp_path):
    """The migration runs exactly once, recorded by a flag rather than inferred from
    the data. Inferring it ("no groups yet?") re-filed a session the user had
    deliberately dragged out, every single launch."""
    from coworker.conversations import ConversationStore

    base = tmp_path / "state"
    folder = tmp_path / "Fieldwork"
    folder.mkdir(exist_ok=True)
    _legacy_db(base, folder, ("s1",))

    store = ConversationStore(base)
    assert store.load("s1").project_id is not None
    store.set_session_project("s1", None)  # the user drags it out

    assert ConversationStore(base).load("s1").project_id is None, (
        "a restart re-filed a session the user removed from its group"
    )


def test_a_sessions_own_scratch_folder_never_becomes_a_group(tmp_path):
    """Found on the owner's real database. Every conversation gets a private working
    directory named after itself (`~/MimiWork/<session id>`), and an automation gets a
    `__task__…` one. Migrating those would have filled the sidebar with groups named
    after uuids — one per conversation ever held."""
    from coworker.conversations import ConversationStore

    base = tmp_path / "state"
    scratch = tmp_path / "MimiWork" / "d4df21d9-6c4"
    scratch.mkdir(parents=True)
    task_dir = tmp_path / "MimiWork" / "__task__task-61c89bc39d"
    task_dir.mkdir(parents=True)
    real = tmp_path / "ETF recruiting"
    real.mkdir()

    _legacy_db(base, real, ("s-real",))
    import sqlite3

    conn = sqlite3.connect(base / "coworker.db")
    # A conversation sitting in its own scratch dir, and an automation run in a task dir.
    conn.execute(
        "INSERT INTO sessions (session_id, workspace, model, mode, title, n_msgs, messages) "
        "VALUES (?,?,?,?,?,?,?)",
        ("d4df21d9-6c4", str(scratch), "m", "interactive", "hi", 1, "[]"),
    )
    conn.execute(
        "INSERT INTO sessions (session_id, workspace, model, mode, title, n_msgs, messages) "
        "VALUES (?,?,?,?,?,?,?)",
        ("__run__run-ce2d6d78e6", str(task_dir), "m", "interactive", "hi", 1, "[]"),
    )
    conn.commit()
    conn.close()

    names = [g["name"] for g in ConversationStore(base).list_projects()]
    assert names == ["ETF recruiting"], names


def test_a_group_keeps_standing_instructions_without_owning_a_folder(tmp_path):
    """Losing the folder must not lose the feature. A group's instructions live on the
    group row — not in a file, and emphatically not in a temp directory, which the OS
    empties out from under text somebody typed."""
    client, _ = _fixture(tmp_path)
    pid = _make(client, "Interview study")

    out = client.put(
        "/v1/projects/instructions",
        json={"id": pid, "text": "Always cite the transcript line number."},
    ).json()
    assert out["ok"]

    detail = client.get(f"/v1/projects/detail?id={pid}").json()
    assert detail["instructions"] == "Always cite the transcript line number."
    row = next(r for r in client.get("/v1/projects").json()["projects"] if r["id"] == pid)
    assert row["has_instructions"] is True

    # Cleared, not left as a blank block.
    assert client.put("/v1/projects/instructions", json={"id": pid, "text": "  "}).json()["ok"]
    row = next(r for r in client.get("/v1/projects").json()["projects"] if r["id"] == pid)
    assert row["has_instructions"] is False


def test_group_instructions_reach_the_conversations_filed_under_it(tmp_path):
    """The point of storing them: a session in the group starts with them in its
    system prompt, exactly as a folder's AGENTS.md always did."""
    from coworker.project import load_agents_md

    empty = tmp_path / "no-instruction-files"
    empty.mkdir()

    block = load_agents_md(empty, global_path=tmp_path / "none.md",
                           group_instructions="Always cite the transcript line number.")
    assert "Project conventions:" in block
    assert "Always cite the transcript line number." in block

    # No group, no folder files, nothing to say.
    assert load_agents_md(empty, global_path=tmp_path / "none.md") == ""
