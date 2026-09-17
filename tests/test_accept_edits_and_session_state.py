"""Claude Code's permission vocabulary (owner ask 2026-09-17): an "Accept edits" level
between Default and Bypass, and per-session state for the sidebar — waiting for you,
working, or finished while you were away."""

from __future__ import annotations

from coworker.automation.models import normalize_mode
from coworker.conversations import SessionRecord
from coworker.permissions import Mode, PermissionEngine
from coworker.server.manager import SessionManager


def test_accept_edits_runs_scoped_writes_but_still_asks_for_commands(tmp_path):
    eng = PermissionEngine(workspace_root=tmp_path, mode=Mode.ACCEPT_EDITS)
    assert eng.evaluate("write_file", {"path": str(tmp_path / "a.txt"), "content": "x"}).allowed
    assert eng.evaluate("read_file", {"path": str(tmp_path / "a.txt")}).allowed
    outside = eng.evaluate("write_file", {"path": "/etc/hosts", "content": "x"})
    assert not outside.allowed and not outside.needs_user
    shell = eng.evaluate("run_shell", {"command": "rm -rf ."})
    assert not shell.allowed and shell.needs_user
    from types import SimpleNamespace

    send = eng.evaluate("send_message", {"channel": "C1", "text": "hi"}, SimpleNamespace(category="connector", requires_approval=True))
    assert not send.allowed and send.needs_user
    assert normalize_mode("accept_edits") == "accept_edits"
    assert normalize_mode("bypass") == "auto" and normalize_mode("default") == "interactive"


class _Provider:
    """Never called."""


def test_a_turn_that_ends_while_nobody_watches_is_marked_unseen(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    mgr = SessionManager(data_dir=tmp_path / "data", provider=_Provider())
    mgr.session_store.save(
        SessionRecord(session_id="s1", workspace=str(tmp_path), model="m", mode="interactive", messages=[], agent="cowork")
    )
    rows = lambda: {s["session_id"]: s for s in mgr.list_sessions()}  # noqa: E731

    mgr.mark_running("s1")
    assert rows()["s1"]["liveness"] == "working" and not rows()["s1"]["unseen"]
    mgr.mark_idle("s1")
    assert rows()["s1"]["liveness"] == "idle" and rows()["s1"]["unseen"]
    # Opening the conversation clears it.
    mgr.register_session_client("s1", lambda *_: None)
    assert not rows()["s1"]["unseen"]
    # With a window attached, finishing is not "unseen".
    mgr.mark_running("s1")
    mgr.mark_idle("s1")
    assert not rows()["s1"]["unseen"]
    # A parked question makes it "waiting", whatever else is true.
    mgr.inbox.add("s1", "approval", "Run a command?")
    assert rows()["s1"]["liveness"] == "waiting"
