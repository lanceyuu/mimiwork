"""Drag a conversation into a project: the folder becomes its primary root, the old one stays."""

from pathlib import Path

from coworker.providers.base import AssistantTurn, ModelCapabilities, ProviderClient
from coworker.server.manager import SessionManager


class EchoProvider(ProviderClient):
    def complete(self, *, model, messages, tools=None, **settings):
        return AssistantTurn(text="ok")

    def capabilities(self, model):
        return ModelCapabilities()


def _mgr(tmp_path):
    return SessionManager(workspace=tmp_path / "home", provider=EchoProvider())


def test_move_rebinds_workspace_and_keeps_the_old_folder_reachable(tmp_path):
    (tmp_path / "home").mkdir()
    project = tmp_path / "Thesis"
    project.mkdir()
    mgr = _mgr(tmp_path)
    sid = "s-move-1"
    engine = mgr.get_engine(sid, agent="cowork")  # orphan → scratch folder provisioned
    assert engine is not None
    mgr.save(sid, engine)
    before = mgr.session_store.load(sid)
    scratch = before.workspace
    assert scratch and Path(scratch).is_dir() and Path(scratch) != project

    out = mgr.move_session(sid, str(project))
    assert out["ok"], out
    after = mgr.session_store.load(sid)
    assert Path(after.workspace) == project.resolve()
    assert any(Path(r["path"]) == Path(scratch) for r in after.extra_roots)
    # Engine was evicted; the rebuilt one roots on the project with the scratch as an extra.
    assert sid not in mgr._engines
    rebuilt = mgr.get_engine(sid, agent="cowork")
    assert rebuilt is not None
    assert Path(mgr.session_store.load(sid).workspace) == project.resolve()


def test_move_refuses_missing_folder_busy_and_internal(tmp_path):
    (tmp_path / "home").mkdir()
    mgr = _mgr(tmp_path)
    sid = "s-move-2"
    mgr.save(sid, mgr.get_engine(sid, agent="cowork"))
    assert not mgr.move_session(sid, str(tmp_path / "nope"))["ok"]
    assert not mgr.move_session("__internal", str(tmp_path))["ok"]
    assert not mgr.move_session("ghost", str(tmp_path))["ok"]
    mgr.mark_running(sid)
    try:
        assert "busy" in mgr.move_session(sid, str(tmp_path))["error"]
    finally:
        mgr.mark_idle(sid)


def test_move_to_the_same_folder_is_a_noop(tmp_path):
    (tmp_path / "home").mkdir()
    mgr = _mgr(tmp_path)
    sid = "s-move-3"
    mgr.save(sid, mgr.get_engine(sid, agent="cowork"))
    ws = mgr.session_store.load(sid).workspace
    out = mgr.move_session(sid, ws)
    assert out["ok"] and out.get("unchanged")
    assert mgr.session_store.load(sid).extra_roots == []
