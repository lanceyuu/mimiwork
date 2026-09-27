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


@pytest.mark.parametrize(
    "command",
    [
        # Each of these stopped a Bypass-permissions automation on 2026-09-27.
        'curl -s "https://github.com/a/b/commits/main.atom" | grep -E "<title>|<updated>" | head -60',
        'echo "=== GitHub search created:>2026-09-19 sorted by stars ==="',
        "python3 - <<'EOF'\nimport re\nfound = re.findall(r'<entry>.*?</entry>', data, re.S)\nEOF",
        "cat >> ledger.md <<'EOF'\n| created:>09-19 search | copy-edit -> stats |\nEOF",
        "python3 -c \"print('a -> b')\"",
        "echo it\\'s fine",
    ],
)
def test_a_greater_than_sign_inside_quoted_text_is_not_a_redirection(tmp_path, command):
    assert destructive_reason(command) is None
    assert PermissionEngine(workspace_root=tmp_path, mode=Mode.AUTO).evaluate("run_shell", {"command": command}).allowed


@pytest.mark.parametrize(
    "command",
    [
        "cat > notes.md <<'EOF'\nhello\nEOF",
        'grep -E "<title>" feed.xml > titles.txt',
        "echo 'done' > a.txt",
        # Quoted text that a shell will run is still a command.
        'bash -c "echo x > results.csv"',
        "sh <<'EOF'\necho x > results.csv\nEOF",
        'echo "$(date > stamp.txt)"',
        "cat <<EOF\n$(date > stamp.txt)\nEOF",
        # Text the guard cannot read with confidence is treated as written.
        'echo "never closed > results.csv',
        "cat <<'EOF'\nno end > results.csv",
    ],
)
def test_a_real_redirection_still_asks_whatever_is_quoted_around_it(tmp_path, command):
    assert "redirection" in (destructive_reason(command) or "")
    assert PermissionEngine(workspace_root=tmp_path, mode=Mode.AUTO).evaluate("run_shell", {"command": command}).needs_user


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
