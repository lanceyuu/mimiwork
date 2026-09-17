"""The memory vault (owner ask 2026-09-17): every memory a markdown note, MEMORY.md the
index, [[links]] rewritten so Obsidian resolves them, regenerated on every change."""

from __future__ import annotations

from coworker.memory import vault
from coworker.memory.base import Scope
from coworker.memory.sqlite_store import SQLiteMemoryStore


def test_export_writes_notes_and_an_index_with_resolved_links(tmp_path):
    store = SQLiteMemoryStore(":memory:")
    a = store.add("Rosters live in the HEC folder. #teaching", scope=Scope.GLOBAL, summary="Where the rosters are")
    b = store.add(
        "Extends [[%d]] and [[rosters|the roster note]]: column B is the email." % a.id,
        scope=Scope.WORKSPACE,
        workspace="/Users/me/Course",
        summary="Roster columns",
        key="rosters",
    )
    out = vault.export(store.list(), labels={"/Users/me/Course": "MBA course"}, where=tmp_path / "v")

    index = (out / "MEMORY.md").read_text()
    assert "## About you" in index and "## MBA course" in index and "## Tags" in index
    assert f"[[{a.id:03d}-where-the-rosters-are|Where the rosters are]]" in index
    assert "#teaching" in index
    note = (out / f"{b.id:03d}-roster-columns.md").read_text()
    assert note.startswith("---\nmimiwork: memory\nid: %d\nscope: workspace\nwhere: MBA course" % b.id)
    assert f"[[{a.id:03d}-where-the-rosters-are|Where the rosters are]]" in note
    assert f"[[{b.id:03d}-roster-columns|the roster note]]" in note  # a key link keeps its alias

    # A memory that is forgotten loses its note; the user's own files are left alone.
    (out / "my-own-note.md").write_text("mine")
    store.delete(a.id)
    vault.export(store.list(), where=out)
    assert not (out / f"{a.id:03d}-where-the-rosters-are.md").exists()
    assert (out / "my-own-note.md").exists()
    assert "Where the rosters are" not in (out / "MEMORY.md").read_text()


def test_the_store_tells_its_listeners_after_every_change():
    store = SQLiteMemoryStore(":memory:")
    calls: list[int] = []
    store.listeners.append(lambda: calls.append(1))
    store.listeners.append(lambda: 1 / 0)  # a failing mirror never breaks the store
    item = store.add("x", scope=Scope.GLOBAL)
    store.update(item.id, "y")
    store.delete(item.id)
    store.delete_all()
    assert len(calls) == 4


def test_a_manager_mirrors_its_memory_into_the_vault(tmp_path, monkeypatch):
    from coworker.server.manager import SessionManager

    monkeypatch.setenv("COWORKER_MEMORY_VAULT", str(tmp_path / "vault"))
    mgr = SessionManager(data_dir=tmp_path / "data", provider=object())
    mgr.add_memory("Prefers real photographs as stimuli", "global")
    text = (tmp_path / "vault" / "MEMORY.md").read_text()
    assert "Prefers real photographs" in text
    assert mgr.memory_vault()["path"] == str(tmp_path / "vault")
