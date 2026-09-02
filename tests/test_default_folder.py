"""The default working folder — the folder you hand Mimi once and keep.

Folder access is stored per session (`sessions.extra_roots`), so onboarding's pick
reached exactly the one conversation it created and every later one started blind.
The owner's own store showed it plainly: 139 conversations, 3 of which had ever been
granted a folder, and a standing complaint that "I already set the folder at the
beginning" (2026-09-02).

A single remembered folder fixes that without widening Mimi's reach: it is seeded into
NEW conversations only, never back-filled into old ones, and one-off grants stay one-off.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from coworker.server.app import create_app
from coworker.server.manager import SessionManager


class _Provider:
    """Never called — these tests only build engines and read roots."""


@pytest.fixture()
def mgr(tmp_path):
    return SessionManager(workspace=tmp_path / "seed", provider=_Provider())


def _paths(roots):
    return [r["path"] for r in roots]


def _extra(roots):
    return [r for r in roots if not r["primary"]]


# -- the bug -----------------------------------------------------------------------


def test_new_conversation_gets_the_default_folder(mgr, tmp_path):
    folder = tmp_path / "Thesis"
    folder.mkdir()
    assert mgr.set_default_folder(str(folder), writable=True)["ok"]

    roots = mgr.get_roots("brand-new-session")

    extra = _extra(roots)
    assert len(extra) == 1, "the remembered folder must be there before the first turn"
    assert Path(extra[0]["path"]) == folder.resolve()
    assert extra[0]["writable"] is True


def test_the_engine_the_agent_actually_runs_sees_it(mgr, tmp_path):
    """get_roots feeds the rail; the engine feeds the agent. Both must agree."""
    folder = tmp_path / "Course"
    folder.mkdir()
    mgr.set_default_folder(str(folder), writable=False)

    engine = mgr.get_engine("fresh-session")

    assert engine is not None
    granted = [Path(r.path) for r in engine.roots]
    assert folder.resolve() in granted
    assert next(r for r in engine.roots if Path(r.path) == folder.resolve()).writable is False


def test_read_only_default_stays_read_only(mgr, tmp_path):
    folder = tmp_path / "Reference"
    folder.mkdir()
    mgr.set_default_folder(str(folder), writable=False)

    assert _extra(mgr.get_roots("s1"))[0]["writable"] is False


# -- the blast radius --------------------------------------------------------------


def test_no_default_means_nothing_changes(mgr):
    roots = mgr.get_roots("s2")

    assert _extra(roots) == [], "without a default, a conversation still starts with scratch only"
    assert len(roots) == 1 and roots[0]["primary"]


def test_existing_conversations_are_not_back_filled(mgr, tmp_path):
    """A conversation that has already run keeps the folders it was given.

    "Already run" means a persisted record — that is the only thing separating an old
    conversation from a new one, since records are written after the first turn.
    """
    from coworker.conversations import SessionRecord

    folder = tmp_path / "Later"
    folder.mkdir()
    old = tmp_path / "old-workspace"
    old.mkdir()
    mgr.session_store.save(
        SessionRecord(
            session_id="old-session",
            workspace=str(old),
            model=mgr.model,
            mode=mgr.mode.value,
            messages=[{"role": "user", "content": "hi"}],
            agent="cowork",
        )
    )
    mgr.set_default_folder(str(folder), writable=True)

    assert _extra(mgr.get_roots("old-session")) == []
    mgr._engines.pop("old-session", None)
    engine = mgr.get_engine("old-session")
    assert [Path(r.path) for r in (engine.roots or [])] == [old.resolve()]


def test_a_one_off_grant_does_not_become_the_default(mgr, tmp_path):
    one_off = tmp_path / "Scratchpad"
    one_off.mkdir()
    mgr.add_root("s3", str(one_off), writable=True)

    assert mgr.default_folder() is None
    assert _extra(mgr.get_roots("s4")) == [], "another conversation must not inherit it"


def test_default_is_not_duplicated_when_already_granted(mgr, tmp_path):
    folder = tmp_path / "Shared"
    folder.mkdir()
    mgr.set_default_folder(str(folder), writable=False)
    mgr.add_root("s5", str(folder), writable=True)

    extra = _extra(mgr.get_roots("s5"))
    assert len(extra) == 1, "the same folder must appear once"
    assert extra[0]["writable"] is True, "an explicit grant wins over the default"


def test_granting_a_folder_before_the_first_turn_keeps_the_default(mgr, tmp_path):
    """The rail's first act on a fresh conversation is often a grant. add_root creates the
    record at that moment, and "no record" is how the seeding tells a new conversation
    apart — so the order of those two steps decides whether the default survives."""
    default = tmp_path / "Default"
    default.mkdir()
    other = tmp_path / "Other"
    other.mkdir()
    mgr.set_default_folder(str(default), writable=True)

    assert mgr.add_root("first-act", str(other), writable=False)["ok"]

    granted = {Path(r["path"]) for r in _extra(mgr.get_roots("first-act"))}
    assert granted == {default.resolve(), other.resolve()}
    engine = mgr.get_engine("first-act")
    assert {Path(r.path) for r in engine.roots[1:]} == {default.resolve(), other.resolve()}


# -- durability --------------------------------------------------------------------


def test_a_deleted_default_is_skipped_not_fatal(mgr, tmp_path):
    folder = tmp_path / "Gone"
    folder.mkdir()
    mgr.set_default_folder(str(folder), writable=True)
    folder.rmdir()  # user moved or deleted it between launches

    roots = mgr.get_roots("s6")  # must not raise
    assert _extra(roots) == []


def test_setting_a_missing_folder_is_refused(mgr, tmp_path):
    res = mgr.set_default_folder(str(tmp_path / "nope"), writable=True)

    assert res["ok"] is False
    assert mgr.default_folder() is None


def test_it_survives_a_restart(mgr, tmp_path):
    folder = tmp_path / "Persists"
    folder.mkdir()
    mgr.set_default_folder(str(folder), writable=True)

    reborn = SessionManager(workspace=tmp_path / "seed", provider=_Provider())

    assert reborn.default_folder() is not None
    assert Path(reborn.default_folder()["path"]) == folder.resolve()


def test_clearing_it_stops_the_seeding(mgr, tmp_path):
    folder = tmp_path / "Temporary"
    folder.mkdir()
    mgr.set_default_folder(str(folder), writable=True)
    assert mgr.clear_default_folder()["ok"]

    assert mgr.default_folder() is None
    assert _extra(mgr.get_roots("s7")) == []


# -- the wire ----------------------------------------------------------------------


def test_settings_round_trip_over_http(mgr, tmp_path):
    folder = tmp_path / "OverTheWire"
    folder.mkdir()
    client = TestClient(create_app(mgr))

    assert client.get("/v1/settings").json()["default_folder"] is None

    res = client.post(
        "/v1/settings/default-folder", json={"path": str(folder), "writable": True}
    )
    assert res.status_code == 200 and res.json()["ok"]

    shown = client.get("/v1/settings").json()["default_folder"]
    assert Path(shown["path"]) == folder.resolve()
    assert shown["writable"] is True

    assert client.post("/v1/settings/default-folder", json={"path": ""}).json()["ok"]
    assert client.get("/v1/settings").json()["default_folder"] is None
