"""Hand-offs to Claude Code / Codex — driven by fake agents that print the CLIs' real JSON lines."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time

import aisuite as ai
from helpers import ScriptedProvider

from coworker.engine import TurnEngine
from coworker.events import EventType
from coworker.permissions import PermissionEngine
from coworker.providers import AssistantTurn, ToolCall
from coworker.risk import RiskClass, classify
from coworker.roots import RootDir
from coworker.tools import ToolRegistry, delegate
from coworker.tools.context import tool_progress

# Recorded from real runs on 2026-10-15 (Codex CLI 0.144.1, Claude Code 2.1.270), trimmed.
CODEX_OK = [
    {"type": "thread.started", "thread_id": "t1"},
    {"type": "turn.started"},
    {"type": "item.started", "item": {"id": "i1", "type": "command_execution", "command": "pytest -q"}},
    {"type": "item.completed", "item": {"id": "i2", "type": "file_change", "changes": [{"path": "app.py", "kind": "update"}]}},
    {"type": "item.completed", "item": {"id": "i3", "type": "agent_message", "text": "Fixed the off-by-one in app.py; tests pass."}},
    {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
]
CODEX_TOO_OLD = [
    {"type": "thread.started", "thread_id": "t2"},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {"id": "i0", "type": "error", "message": "Model metadata for `gpt-6-astra` not found."}},
    {"type": "turn.failed", "error": {"message": json.dumps({"type": "error", "status": 400, "error": {"type": "invalid_request_error", "message": "The 'gpt-6-astra' model requires a newer version of Codex. Please upgrade to the latest app or CLI and try again."}})}},
]
CLAUDE_SIGNED_OUT = [
    {"type": "system", "subtype": "init", "session_id": "s1"},
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "Failed to authenticate: OAuth session expired and could not be refreshed"}]}, "error": "authentication_failed"},
    {"type": "result", "subtype": "success", "is_error": True, "result": "Failed to authenticate: OAuth session expired and could not be refreshed"},
]
CLAUDE_OK = [
    {"type": "system", "subtype": "init", "session_id": "s2"},
    {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Write", "input": {"file_path": "notes.md"}}]}},
    {"type": "result", "subtype": "success", "is_error": False, "result": "Wrote notes.md."},
]


def _fake_agent(tmp_path, events, *, write=None, sleep=0.0, exit_code=0):
    """argv for a stand-in agent: reads the task from stdin, optionally writes a file, prints events."""
    script = tmp_path / "fake_agent.py"
    script.write_text(
        "import json, sys, time\n"
        "task = sys.stdin.read()\n"
        f"write = {write!r}\n"
        "if write: open(write, 'w').write(task)\n"
        f"for e in {events!r}:\n"
        "    print(json.dumps(e), flush=True)\n"
        f"time.sleep({sleep})\n"
        f"sys.exit({exit_code})\n",
        encoding="utf-8",
    )
    return [sys.executable, str(script)]


def _run(tmp_path, key, events, **kw):
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    fake = _fake_agent(tmp_path, events, write=kw.pop("write", None), sleep=kw.pop("sleep", 0.0))
    lines: list[str] = []
    result = delegate.run_agent(key, "unused", "fix the bug", work, report=lines.append, argv=fake, **kw)
    return result, lines


def test_claude_code_runs_headless_in_its_auto_permission_mode_and_codex_in_its_workspace_sandbox():
    claude = delegate.agent_command("claude_code", "claude")
    assert claude[claude.index("--permission-mode") + 1] == "auto"
    codex = delegate.agent_command("codex", "codex")
    assert codex[codex.index("--sandbox") + 1] == "workspace-write"


def test_a_codex_handoff_returns_its_summary_progress_and_changed_files(tmp_path):
    result, lines = _run(tmp_path, "codex", CODEX_OK, write="app.py")
    assert result["status"] == "completed"
    assert result["summary"] == "Fixed the off-by-one in app.py; tests pass."
    assert result["changed_files"] == ["app.py"]
    assert (tmp_path / "work" / "app.py").read_text() == "fix the bug"  # the task arrived on stdin
    assert lines == ["Running: pytest -q", "Changed app.py", "Fixed the off-by-one in app.py; tests pass."]


def test_a_claude_code_handoff_reports_its_tool_steps_and_result(tmp_path):
    result, lines = _run(tmp_path, "claude_code", CLAUDE_OK)
    assert result["status"] == "completed" and result["summary"] == "Wrote notes.md."
    assert lines == ["Write: notes.md"]


def test_a_signed_out_claude_code_comes_back_as_an_error_that_says_why(tmp_path):
    result, _ = _run(tmp_path, "claude_code", CLAUDE_SIGNED_OUT)
    assert "status" not in result
    assert result["error"] == (
        "Claude Code did not finish: Failed to authenticate: OAuth session expired and could not be refreshed"
    )


def test_a_failed_codex_turn_reports_the_providers_sentence_not_nested_json(tmp_path):
    result, lines = _run(tmp_path, "codex", CODEX_TOO_OLD)
    assert result["error"].startswith("Codex did not finish: The 'gpt-6-astra' model requires a newer version")
    assert lines == ["Model metadata for `gpt-6-astra` not found."]  # a warning, shown as progress


def test_an_agent_that_exits_without_finishing_is_a_failure_with_its_output(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    script = tmp_path / "crash.py"
    script.write_text("import sys\nprint('node: command not found')\nsys.exit(127)\n", encoding="utf-8")
    result = delegate.run_agent("codex", "unused", "t", work, argv=[sys.executable, str(script)])
    assert result["error"] == "Codex did not finish: node: command not found"


def test_stopping_the_turn_stops_the_agent_and_warns_files_may_have_changed(tmp_path):
    stop = threading.Event()
    threading.Timer(0.5, stop.set).start()
    started = time.monotonic()
    result, _ = _run(tmp_path, "codex", [], sleep=30, stop=stop)
    assert time.monotonic() - started < 10
    assert result["error"] == "Stopped. Codex may have changed some files before it stopped."


def test_a_run_past_its_time_limit_is_stopped_and_says_so(tmp_path):
    result, _ = _run(tmp_path, "codex", [], sleep=30, timeout=0.5)
    assert result["error"] == "Codex was still working at its 1-minute limit and was stopped."


def _tool(tmp_path, monkeypatch, events, roots):
    fake = _fake_agent(tmp_path, events)
    monkeypatch.setattr(delegate, "available_agents", lambda: {"codex": "codex"})
    monkeypatch.setattr(delegate, "agent_command", lambda key, exe: fake)
    [tool] = delegate.delegate_tools(workspace=tmp_path, roots=roots)
    return tool


def test_a_folder_outside_the_writable_roots_is_refused_before_anything_runs(tmp_path, monkeypatch):
    mine = tmp_path / "mine"
    mine.mkdir()
    readonly = tmp_path / "readonly"
    readonly.mkdir()
    tool = _tool(tmp_path, monkeypatch, CODEX_OK, [RootDir(mine, writable=True), RootDir(readonly)])
    assert "outside the folders" in tool(agent="codex", task="t", folder=str(readonly))["error"]
    assert "outside the folders" in tool(agent="codex", task="t", folder="../readonly")["error"]
    assert tool(agent="codex", task="t")["folder"] == str(mine.resolve())


def test_an_agent_that_is_not_installed_is_refused_by_name(tmp_path, monkeypatch):
    tool = _tool(tmp_path, monkeypatch, CODEX_OK, [RootDir(tmp_path, writable=True)])
    assert tool(agent="claude_code", task="t")["error"].startswith("'claude_code' is not available here")


def test_no_tool_is_offered_when_neither_agent_is_installed(tmp_path, monkeypatch):
    monkeypatch.setattr(delegate, "available_agents", lambda: {})
    assert delegate.delegate_tools(workspace=tmp_path) == []


def test_every_handoff_needs_the_users_approval(tmp_path, monkeypatch):
    tool = _tool(tmp_path, monkeypatch, CODEX_OK, None)
    meta = tool.__aisuite_tool_metadata__
    assert classify("delegate_to_agent", meta) is RiskClass.EXTERNAL
    decision = PermissionEngine(workspace_root=tmp_path).evaluate("delegate_to_agent", {"task": "t"}, meta)
    assert not decision.allowed and decision.needs_user


def test_the_agents_are_found_where_installers_put_them_even_on_a_bare_path(tmp_path, monkeypatch):
    bindir = tmp_path / ".local" / "bin"
    bindir.mkdir(parents=True)
    exe = bindir / "claude"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # what an app opened from Finder gets
    if sys.platform != "win32":
        assert delegate.find_agent("claude_code") == str(exe)


def test_a_running_tools_progress_lines_stream_between_its_start_and_finish(tmp_path):
    def slow_step():
        """Report two lines while working."""
        report = tool_progress.get()
        report("first")
        time.sleep(0.05)
        report("second")
        time.sleep(0.05)
        return {"ok": True}

    turns = [
        AssistantTurn(tool_calls=[ToolCall(id="c1", name="slow_step", arguments={})], finish_reason="tool_calls"),
        AssistantTurn(text="done", finish_reason="stop"),
    ]
    registry = ToolRegistry()
    registry.register(slow_step, metadata=ai.ToolMetadata(category="x", risk_level="medium"))
    engine = TurnEngine(
        provider=ScriptedProvider(turns),
        registry=registry,
        permissions=PermissionEngine(workspace_root=tmp_path),
        model="gpt-5.5",
    )

    async def _go():
        return [ev async for ev in engine.run("go")]

    events = asyncio.run(_go())
    kinds = [e.type for e in events]
    start, finish = kinds.index(EventType.TOOL_STARTED), kinds.index(EventType.TOOL_FINISHED)
    progress = [e.data for e in events if e.type == EventType.TOOL_PROGRESS]
    assert progress == [{"name": "slow_step", "text": "first"}, {"name": "slow_step", "text": "second"}]
    assert all(start < i < finish for i, k in enumerate(kinds) if k == EventType.TOOL_PROGRESS)
    # display-only: nothing about progress lands in the conversation history
    assert "first" not in json.dumps(engine.messages)
