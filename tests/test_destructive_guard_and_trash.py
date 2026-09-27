"""Two nets under the shell (owner ask 2026-09-17): a destructive command is confirmed
every time, in every mode, and deletion goes to the Trash instead of `rm`."""

from __future__ import annotations

import sys

import pytest

from coworker.engine import ApprovalOutcome
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


@pytest.fixture
def folder(tmp_path):
    """A working folder holding notes.md and sub/inner.md; nothing else exists."""
    (tmp_path / "notes.md").write_text("keep me")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "inner.md").write_text("keep me")
    return tmp_path


def _decide(folder, command, cwd="."):
    where = None if cwd is None else str(folder / cwd)
    command = command.replace("{folder}", str(folder))
    engine = PermissionEngine(workspace_root=folder, mode=Mode.AUTO)
    return engine.evaluate("run_shell", {"command": command}, shell_cwd=where)


@pytest.mark.parametrize(
    "command",
    [
        "cat > fresh.md <<'EOF'\nhello\nEOF",
        'echo x > "fresh file.md"',
        "echo x > sub/fresh.md",
        "echo x > {folder}/fresh.md",
        "cd sub && echo x > notes.md",  # notes.md lives one folder up, not in sub
        "cd {folder}/sub && echo x > fresh.md",
        "python3 run.py > fresh.log 2>&1",
        "python3 run.py 2> errors.log",
        "python3 run.py > /dev/null 2>&1",
        "echo problem >&2",
    ],
)
def test_writing_a_file_that_does_not_exist_yet_runs_without_asking(folder, command):
    assert _decide(folder, command).allowed


@pytest.mark.parametrize(
    "command",
    [
        "echo x > notes.md",
        'echo x > "notes.md"',
        "echo x > 'notes.md'; ls",
        "echo x > ./notes.md",
        "echo x > sub/../notes.md",
        "echo x > {folder}/notes.md",
        "echo x >| notes.md",
        "python3 run.py 2> notes.md",
        "python3 run.py &> notes.md",
        "cat > notes.md <<'EOF'\nhello\nEOF",
        'grep -E "<title>" feed.xml > notes.md',
        "cd sub && echo x > inner.md",
        "cd sub; echo x > ../notes.md",
        'echo "$(date > notes.md)"',
    ],
)
def test_writing_over_a_file_that_exists_asks_even_in_bypass(folder, command):
    d = _decide(folder, command)
    assert not d.allowed and d.needs_user
    assert "already exists" in d.reason and "always asks" in d.reason
    assert ("inner.md" if "inner.md" in command else "notes.md") in d.reason


@pytest.mark.parametrize(
    "command",
    [
        # The file name is only known once the shell has expanded it.
        "echo x > $OUT",
        'echo x > "$HOME/fresh.md"',
        "echo x > fresh-*.md",
        "echo x > `date +%F`.md",
        "echo x > C:\\out\\fresh.md",
        # The folder the command ends up in cannot be followed.
        "(cd sub && ls); echo x > fresh.md",
        "if true; then cd sub; fi; echo x > fresh.md",
        "cd missing; echo x > fresh.md",
        'cd "$DIR" && echo x > fresh.md',
        "cd - && echo x > fresh.md",
        "pushd sub && echo x > fresh.md",
        "cd() { :; }; cd sub && echo x > notes.md",
        # Quoted text that a shell will run is a command the guard has not read.
        'bash -c "echo x > fresh.md"',
        "sh <<'EOF'\necho x > fresh.md\nEOF",
        # Text it cannot read with confidence.
        'echo "never closed > fresh.md',
        "cat <<'EOF'\nno end > fresh.md",
    ],
)
def test_a_redirection_the_guard_cannot_place_asks(folder, command):
    d = _decide(folder, command)
    assert not d.allowed and d.needs_user and "always asks" in d.reason


@pytest.mark.skipif(sys.platform == "win32", reason="runs the commands in bash")
@pytest.mark.parametrize(
    "command",
    [
        "echo x > no\"tes\".md",
        "echo x>notes.md",
        "echo x 2>&1 > notes.md",
        ": > notes.md",
        "cd link && cd .. && echo x > notes.md",  # link points at sub: `..` is this folder
        "cd link/.. && echo x > notes.md",
        "cd -P link && cd .. && echo x > sub/inner.md",
        "{ cd sub; echo x > inner.md; }",
        "cd sub || true; echo x > inner.md",
        "command cd sub && echo x > inner.md",
        "cd sub\\\n && echo x > inner.md",
        "F=notes.md; echo x > ${F}",
        "echo x > ~+/notes.md",
        "echo x > note?.md",
        "echo 'echo x > notes.md' | bash",
        "eval 'echo x > notes.md'",
        "cat <<EOF > notes.md\nhello\nEOF",
        "cat <<'A' <<'B'\none\nA\ntwo\nB\necho x > notes.md",
        "cat <<'EOF'\n EOF\nEOF\necho x > notes.md",
        "cat <<\\EOF > notes.md\nx\nEOF",
        "echo x > fresh.md",
        "cd sub && echo x > notes.md",
        "cat > fresh.md <<'EOF'\na -> b\nEOF",
    ],
)
def test_nothing_the_guard_lets_through_changes_a_file_that_was_there(folder, command):
    """The guard's reading of a command against what bash really does with it."""
    import subprocess

    (folder / "link").symlink_to(folder / "sub")
    if destructive_reason(command, str(folder)) is None:
        subprocess.run(["/bin/bash", "-c", command], cwd=folder, capture_output=True, timeout=10)
    assert (folder / "notes.md").read_text() == "keep me"
    assert (folder / "sub" / "inner.md").read_text() == "keep me"


def test_without_knowing_where_the_shell_stands_only_full_paths_are_trusted(folder):
    assert _decide(folder, "echo x > fresh.md", cwd=None).needs_user
    assert _decide(folder, "echo x > {folder}/fresh.md", cwd=None).allowed
    assert _decide(folder, "cd {folder} && echo x > fresh.md", cwd=None).allowed
    assert _decide(folder, "cd {folder} && echo x > notes.md", cwd=None).needs_user


def test_a_command_cleared_earlier_in_the_same_turn_puts_the_folder_in_doubt(folder):
    """Every call in a turn is cleared before the first one runs, so a `cd` in an earlier
    call has not happened yet when the next call's file name is checked."""
    import asyncio
    from types import SimpleNamespace

    from coworker.engine import TurnEngine
    from coworker.events import EventType
    from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient, ToolCall
    from coworker.tools import ToolRegistry

    def run_shell(command: str):
        return {"exit_code": 0}

    run_shell.__coworker_schema__ = {
        "type": "function",
        "function": {"name": "run_shell", "description": "run", "parameters": {"type": "object", "properties": {}}},
    }

    def held(*commands):
        class _P(ProviderClient):
            def __init__(self):
                calls = [ToolCall(id=f"c{i}", name="run_shell", arguments={"command": c}) for i, c in enumerate(commands)]
                self._turns = [AssistantTurn(tool_calls=calls, finish_reason="tool_calls"), AssistantTurn(text="done", finish_reason="stop")]

            def complete(self, *, model, messages, tools=None, **settings):
                return self._turns.pop(0)

            def capabilities(self, model):
                return ModelCapabilities()

        registry = ToolRegistry()
        registry.register_all([run_shell])

        async def allow(_request):
            return ApprovalOutcome.ONCE

        engine = TurnEngine(
            provider=_P(),
            registry=registry,
            permissions=PermissionEngine(workspace_root=folder, mode=Mode.AUTO),
            model="gpt-5.5",
            approver=allow,
        )
        engine.executor = SimpleNamespace(cwd=str(folder))

        async def run():
            return [ev async for ev in engine.run("go")]

        events = asyncio.run(run())
        return [e.data["arguments"]["command"] for e in events if e.type == EventType.PERMISSION_REQUIRED]

    assert held("echo x > inner.md") == []
    assert held("ls", "echo x > inner.md") == ["echo x > inner.md"]
    # A full path does not depend on where the shell stands.
    assert held("cd sub", f"echo x > {folder}/fresh.md") == []


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
