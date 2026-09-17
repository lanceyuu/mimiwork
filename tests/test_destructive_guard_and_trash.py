"""Two nets under the shell (owner ask 2026-09-17): a destructive command is confirmed
every time, in every mode, and deletion goes to the Trash instead of `rm`."""

from __future__ import annotations

import pytest

from coworker.permissions import Mode, PermissionEngine, destructive_reason
from coworker.tools.files import file_tools, send_to_trash


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf build",
        "rm -r old",
        "rm -f notes.txt",
        "rmdir drafts",
        "find . -name '*.bak' -delete",
        "git reset --hard HEAD~1",
        "git clean -fd",
        "git checkout -- report.docx",
        "sed -i 's/a/b/' data.csv",
        "echo x > results.csv",
        "truncate -s 0 log.txt",
        "Remove-Item -Recurse old",
        "del /s /q old",
    ],
)
def test_destructive_commands_always_ask_even_in_bypass(tmp_path, command):
    assert destructive_reason(command)
    eng = PermissionEngine(workspace_root=tmp_path, mode=Mode.AUTO, allowed_commands=["rm", "git"])
    eng.allow_command_for_session(command)
    d = eng.evaluate("run_shell", {"command": command})
    assert not d.allowed and d.needs_user and "always asks" in d.reason


@pytest.mark.parametrize(
    "command",
    ["ls -la", "rm notes.txt", "git status", "cat a.txt 2>/dev/null", "echo hi >> log.txt", "python3 run.py 2>&1"],
)
def test_ordinary_commands_are_not_flagged(tmp_path, command):
    assert destructive_reason(command) is None
    assert PermissionEngine(workspace_root=tmp_path, mode=Mode.AUTO).evaluate("run_shell", {"command": command}).allowed


def test_delete_file_moves_into_the_trash_and_stays_inside_the_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    # No Finder in a test: the fallback path (a move into ~/.Trash) is what runs.
    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no osascript")))
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "old.txt").write_text("keep me")
    tools = {t.__name__: t for t in file_tools(str(ws))}
    out = tools["delete_file"]("old.txt")
    assert "error" not in out, out
    assert not (ws / "old.txt").exists()
    trashed = list((tmp_path / "home" / ".Trash").glob("old*.txt")) or list((tmp_path / "home" / ".local" / "share" / "Trash" / "files").glob("old*"))
    assert trashed and trashed[0].read_text() == "keep me"
    assert "error" in tools["delete_file"]("/etc/hosts")
    assert "error" in tools["delete_file"]("missing.txt")
    # It is path-scoped like every write, and Accept edits runs it without asking.
    eng = PermissionEngine(workspace_root=ws, mode=Mode.ACCEPT_EDITS)
    assert eng.evaluate("delete_file", {"path": str(ws / "a.txt")}).allowed
    assert not eng.evaluate("delete_file", {"path": "/etc/hosts"}).allowed
    assert PermissionEngine(workspace_root=ws).evaluate("delete_file", {"path": str(ws / "a.txt")}).needs_user
    # A second file with the same name does not overwrite the first in the Trash.
    (ws / "old.txt").write_text("second")
    tools["delete_file"]("old.txt")
    assert len(list((tmp_path / "home" / ".Trash").glob("old*.txt")) or list((tmp_path / "home" / ".local" / "share" / "Trash" / "files").glob("old*"))) == 2
    assert isinstance(send_to_trash, object)
