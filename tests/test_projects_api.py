"""PROJECTS — a project is a real workspace folder with display metadata, its own
instructions (AGENTS.md, already injected as 'Project conventions') and its own memory
(the workspace scope the `remember` tool writes to). These tests pin the REST surface the
sidebar Projects band and the Project page stand on."""

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
    """A saved conversation in that folder — enough for the delete paths to see it."""
    from coworker.conversations import SessionRecord

    manager.session_store.save(
        SessionRecord(
            session_id=session_id,
            workspace=str(workspace.resolve()),
            model="m",
            mode="interactive",
            messages=[{"role": "user", "content": "hi"}],
            title="hi",
        )
    )


def _open(client, path):
    assert client.post("/v1/workspaces/open", json={"path": str(path)}).json()["ok"]


def test_projects_list_excludes_scratch_and_carries_metadata(tmp_path):
    client, manager = _fixture(tmp_path)
    proj = tmp_path / "thesis"
    proj.mkdir()
    _open(client, proj)
    # A per-conversation scratch dir is a workspace to the store but never a project.
    scratch = manager.scratch_base() / "abc123"
    scratch.mkdir(parents=True, exist_ok=True)
    _open(client, scratch)

    rows = client.get("/v1/projects").json()["projects"]
    paths = [r["path"] for r in rows]
    assert str(proj.resolve()) in paths
    assert all(not p.startswith(str(manager.scratch_base().resolve())) for p in paths)
    row = next(r for r in rows if r["path"] == str(proj.resolve()))
    assert row["name"] == "thesis" and row["emoji"] == "" and row["exists"] is True
    assert row["pinned"] is False and row["archived"] is False
    assert row["sessions"] == 0 and row["has_instructions"] is False


def test_rename_emoji_pin_archive_round_trip(tmp_path):
    client, _ = _fixture(tmp_path)
    proj = tmp_path / "grant"
    proj.mkdir()
    _open(client, proj)

    r = client.patch(
        "/v1/projects",
        json={"path": str(proj), "name": "ERC grant 2027", "emoji": "🎯", "pinned": True},
    ).json()
    assert r["ok"] and r["project"]["name"] == "ERC grant 2027"
    assert r["project"]["emoji"] == "🎯" and r["project"]["pinned"] is True

    rows = client.get("/v1/projects").json()["projects"]
    assert rows[0]["path"] == str(proj.resolve())  # pinned sorts first

    r = client.patch("/v1/projects", json={"path": str(proj), "archived": True}).json()
    assert r["project"]["archived"] is True
    # Unknown folders are refused — metadata can't be attached to arbitrary paths.
    bad = client.patch("/v1/projects", json={"path": str(tmp_path / "nope"), "name": "x"}).json()
    assert bad["ok"] is False


def test_instructions_write_read_and_clear(tmp_path):
    client, _ = _fixture(tmp_path)
    proj = tmp_path / "paper"
    proj.mkdir()
    _open(client, proj)

    r = client.put(
        "/v1/projects/instructions",
        json={"path": str(proj), "text": "Cite in APA 7. Never touch data/raw."},
    ).json()
    assert r["ok"]
    assert (proj / "AGENTS.md").read_text(encoding="utf-8") == "Cite in APA 7. Never touch data/raw.\n"

    detail = client.get("/v1/projects/detail", params={"path": str(proj)}).json()
    assert detail["ok"] and detail["instructions"].startswith("Cite in APA 7")
    assert detail["project"]["has_instructions"] is True
    assert detail["instructions_file"].endswith("AGENTS.md")

    # Emptying the editor removes the file rather than leaving a blank conventions block.
    client.put("/v1/projects/instructions", json={"path": str(proj), "text": "  \n"})
    assert not (proj / "AGENTS.md").exists()
    # And writing outside a known project is refused.
    assert client.put(
        "/v1/projects/instructions", json={"path": str(tmp_path / "else"), "text": "x"}
    ).json()["ok"] is False


def test_project_memory_is_the_workspace_scope(tmp_path):
    client, _ = _fixture(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _open(client, a)
    _open(client, b)
    client.post("/v1/memory", json={"content": "likes tables", "scope": "global"})
    client.post("/v1/memory", json={"content": "A uses Stata", "scope": "workspace", "workspace": str(a)})
    client.post("/v1/memory", json={"content": "B uses R", "scope": "workspace", "workspace": str(b)})

    mem_a = client.get("/v1/memory", params={"workspace": str(a.resolve())}).json()["memory"]
    assert [m["content"] for m in mem_a] == ["A uses Stata"]
    assert mem_a[0]["workspace"] == str(a.resolve())
    detail = client.get("/v1/projects/detail", params={"path": str(a)}).json()
    assert [m["content"] for m in detail["memory"]] == ["A uses Stata"]
    # The unfiltered screen still shows everything.
    assert len(client.get("/v1/memory").json()["memory"]) == 3


def test_canonicalize_keeps_project_metadata(tmp_path):
    _, manager = _fixture(tmp_path)
    proj = tmp_path / "keep"
    proj.mkdir()
    store = manager.session_store
    store.touch_workspace(str(proj.resolve()))
    store.set_workspace_meta(str(proj.resolve()), name="Keep me", emoji="📌", pinned=True)
    store.canonicalize_workspaces()
    meta = store.workspace_meta(str(proj.resolve()))
    assert meta["name"] == "Keep me" and meta["emoji"] == "📌" and meta["pinned"] is True


def test_deleting_a_project_forgets_it_but_never_touches_the_folder(tmp_path):
    """Delete = bookkeeping. The project's identity, memory and conversations go; the
    folder and its files (AGENTS.md included) are the user's and stay put."""
    client, manager = _fixture(tmp_path)
    proj = tmp_path / "old-study"
    proj.mkdir()
    (proj / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    _open(client, proj)
    client.patch("/v1/projects", json={"path": str(proj), "name": "Old study", "emoji": "📚"})
    client.put("/v1/projects/instructions", json={"path": str(proj), "text": "Cite APA."})
    client.post(
        "/v1/memory",
        json={
            "content": "the pilot ran in March",
            "scope": "workspace",
            "workspace": str(proj.resolve()),
        },
    )

    r = client.request("DELETE", "/v1/projects", params={"path": str(proj)}).json()
    assert r["ok"] and r["forgotten_memories"] == 1

    assert str(proj.resolve()) not in [p["path"] for p in client.get("/v1/projects").json()["projects"]]
    assert manager.list_memory(workspace=str(proj.resolve())) == []
    # The folder is untouched — files and the instructions file are still there.
    assert (proj / "data.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"
    assert (proj / "AGENTS.md").is_file()
    # Unknown afterwards: a second delete is a clean no-op, not a crash.
    assert client.request("DELETE", "/v1/projects", params={"path": str(proj)}).json() == {
        "ok": False,
        "error": "unknown project",
    }


def test_deleting_a_project_takes_its_conversations_unless_asked_to_keep_them(tmp_path):
    client, manager = _fixture(tmp_path)
    keep = tmp_path / "keeper"
    keep.mkdir()
    _open(client, keep)
    _session(manager, "s-keep-1", keep)
    r = client.request(
        "DELETE", "/v1/projects", params={"path": str(keep), "delete_sessions": "false"}
    ).json()
    assert r["ok"] and r["deleted_sessions"] == 0
    assert manager.session_store.load("s-keep-1") is not None

    drop = tmp_path / "dropper"
    drop.mkdir()
    _open(client, drop)
    _session(manager, "s-drop-1", drop)
    r = client.request("DELETE", "/v1/projects", params={"path": str(drop)}).json()
    assert r["ok"] and r["deleted_sessions"] == 1
    assert manager.session_store.load("s-drop-1") is None


def test_a_running_conversation_blocks_the_delete(tmp_path):
    client, manager = _fixture(tmp_path)
    proj = tmp_path / "busy"
    proj.mkdir()
    _open(client, proj)
    _session(manager, "s-busy-1", proj)
    manager.mark_running("s-busy-1")
    r = client.request("DELETE", "/v1/projects", params={"path": str(proj)}).json()
    assert not r["ok"] and "running" in r["error"]
    assert manager.session_store.load("s-busy-1") is not None
    assert str(proj.resolve()) in [p["path"] for p in client.get("/v1/projects").json()["projects"]]
