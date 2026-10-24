"""Hand-offs to Claude Code / Codex / opencode / Cursor / Gemini CLI — driven by fake agents that
print the CLIs' real JSON lines."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import aisuite as ai
import pytest
from helpers import ScriptedProvider

from coworker.engine import TurnEngine
from coworker.events import EventType
from coworker.permissions import PermissionEngine
from coworker.providers import AssistantTurn, ToolCall
from coworker.risk import RiskClass, classify
from coworker.roots import RootDir
from coworker.tools import ToolRegistry, delegate
from coworker.tools.cancellation import tool_stop
from coworker.tools.context import tool_progress, tool_yield

# Recorded from real runs on 2026-10-15 (Codex CLI 0.144.1, Claude Code 2.1.270), trimmed.
CODEX_OK = [
    {"type": "thread.started", "thread_id": "t1"},
    {"type": "turn.started"},
    {"type": "item.started", "item": {"id": "i1", "type": "command_execution", "command": "/bin/bash -lc 'pytest -q'"}},
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

# Recorded from real runs on 2026-10-18 (opencode 1.19.3), trimmed.
OPENCODE_OK = [
    {"type": "step_start", "sessionID": "ses_9", "part": {"type": "step-start"}},
    {"type": "text", "sessionID": "ses_9", "part": {"type": "text", "text": "Creating the requested file."}},
    {"type": "tool_use", "sessionID": "ses_9", "part": {"type": "tool", "tool": "apply_patch", "state": {
        "status": "completed", "input": {"patchText": "*** Begin Patch\n*** Add File: hello.txt\n+hi\n*** End Patch"}}}},
    {"type": "step_finish", "sessionID": "ses_9", "part": {"type": "step-finish", "reason": "tool-calls"}},
    {"type": "step_start", "sessionID": "ses_9", "part": {"type": "step-start"}},
    {"type": "tool_use", "sessionID": "ses_9", "part": {"type": "tool", "tool": "bash", "state": {
        "status": "completed", "input": {"command": "ls"}, "title": "ls"}}},
    {"type": "step_finish", "sessionID": "ses_9", "part": {"type": "step-finish", "reason": "tool-calls"}},
    {"type": "text", "sessionID": "ses_9", "part": {"type": "text", "text": "Created hello.txt containing hi."}},
    {"type": "step_finish", "sessionID": "ses_9", "part": {"type": "step-finish", "reason": "stop"}},
]
OPENCODE_UNKNOWN_MODEL = [
    {"type": "error", "sessionID": "ses_8", "error": {"name": "UnknownError", "data": {
        "message": "Unexpected server error. Check server logs for details.", "ref": "err_8578b641"}}},
]

# Shapes read from the CLIs' own emitters on 2026-10-24 (Cursor 2026.01.28, Gemini CLI 0.65.0);
# neither account was signed in, so no live run recorded them.
CURSOR_OK = [
    {"type": "system", "subtype": "init", "apiKeySource": "login", "cwd": "/w", "session_id": "c-1",
     "model": "GPT-6 Luna", "permissionMode": "default"},
    {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": "fix the bug"}]}, "session_id": "c-1"},
    {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "Running the tests."}]}, "session_id": "c-1"},
    {"type": "tool_call", "subtype": "started", "call_id": "1", "session_id": "c-1",
     "tool_call": {"tool": {"case": "shellToolCall", "value": {"args": {"command": "pytest -q"}}}}},
    {"type": "tool_call", "subtype": "completed", "call_id": "1", "session_id": "c-1",
     "tool_call": {"tool": {"case": "shellToolCall", "value": {"args": {"command": "pytest -q"}, "result": {}}}}},
    {"type": "tool_call", "subtype": "started", "call_id": "2", "session_id": "c-1",
     "tool_call": {"editToolCall": {"args": {"path": "app.py"}}}},
    {"type": "result", "subtype": "success", "is_error": False, "duration_ms": 9, "result": "Fixed app.py; tests pass.", "session_id": "c-1"},
]
GEMINI_OK = [
    {"type": "init", "timestamp": "t", "session_id": "g-1", "model": "gemini-3-pro"},
    {"type": "message", "timestamp": "t", "role": "user", "content": "fix the bug"},
    {"type": "message", "timestamp": "t", "role": "assistant", "content": "Let me ", "delta": True},
    {"type": "message", "timestamp": "t", "role": "assistant", "content": "look.", "delta": True},
    {"type": "tool_use", "timestamp": "t", "tool_name": "run_shell_command", "tool_id": "1", "parameters": {"command": "pytest -q"}},
    {"type": "tool_result", "timestamp": "t", "tool_id": "1", "status": "success", "output": "1 passed"},
    {"type": "message", "timestamp": "t", "role": "assistant", "content": "Fixed app.py; ", "delta": True},
    {"type": "message", "timestamp": "t", "role": "assistant", "content": "tests pass.", "delta": True},
    {"type": "result", "timestamp": "t", "status": "success", "stats": {}},
]
GEMINI_QUOTA = [
    {"type": "init", "timestamp": "t", "session_id": "g-2", "model": "gemini-3-pro"},
    {"type": "result", "timestamp": "t", "status": "error",
     "error": {"type": "QuotaError", "message": "You have exhausted your daily quota."}, "stats": {}},
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
    assert 'sandbox_mode="workspace-write"' in codex


def test_opencode_runs_unattended_with_json_events_and_without_approving_what_its_settings_ask_about():
    assert delegate.agent_command("opencode", "opencode") == ["opencode", "run", "--format", "json"]
    full = delegate.agent_command("opencode", "opencode", "ses_9", model="opencode/big-pickle", effort="high")
    assert full[full.index("--session") + 1] == "ses_9"
    assert full[full.index("-m") + 1] == "opencode/big-pickle" and full[full.index("--variant") + 1] == "high"
    assert "--auto" not in full


def test_cursor_runs_headless_with_force_so_it_can_edit_and_resumes_its_chat():
    assert delegate.agent_command("cursor", "cursor-agent") == [
        "cursor-agent", "-p", "--output-format", "stream-json", "--force"]
    full = delegate.agent_command("cursor", "cursor-agent", "c-1", model="gpt-6-luna", effort="high")
    assert full[full.index("--resume") + 1] == "c-1" and full[full.index("--model") + 1] == "gpt-6-luna"
    assert "high" not in full  # Cursor has no effort setting


def test_gemini_runs_headless_reading_the_task_from_stdin_without_stopping_to_ask():
    cmd = delegate.agent_command("gemini", "gemini", "g-1", model="pro")
    assert cmd[1:3] == ["-p", ""]  # empty prompt: the task comes in on stdin
    assert cmd[cmd.index("--approval-mode") + 1] == "yolo" and "--skip-trust" in cmd
    assert cmd[cmd.index("--resume") + 1] == "g-1" and cmd[cmd.index("-m") + 1] == "pro"


def test_a_follow_up_resumes_the_same_agent_session_in_both_clis():
    claude = delegate.agent_command("claude_code", "claude", "sess-9")
    assert claude[claude.index("--resume") + 1] == "sess-9"
    codex = delegate.agent_command("codex", "codex", "thr-9")
    assert codex[:3] == ["codex", "exec", "resume"] and codex[-2:] == ["thr-9", "-"]
    assert 'sandbox_mode="workspace-write"' in codex  # resume has no --sandbox flag


def test_a_codex_handoff_returns_its_summary_progress_and_changed_files(tmp_path):
    result, lines = _run(tmp_path, "codex", CODEX_OK, write="app.py")
    assert result["status"] == "completed"
    assert result["summary"] == "Fixed the off-by-one in app.py; tests pass."
    assert result["changed_files"] == ["app.py"]
    assert (tmp_path / "work" / "app.py").read_text() == "fix the bug"  # the task arrived on stdin
    assert lines == ["Running: pytest -q", "Changed app.py", "Fixed the off-by-one in app.py; tests pass."]
    assert result["session_id"] == "t1"  # what a follow-up resumes


def test_a_claude_code_handoff_reports_its_tool_steps_and_result(tmp_path):
    result, lines = _run(tmp_path, "claude_code", CLAUDE_OK)
    assert result["status"] == "completed" and result["summary"] == "Wrote notes.md."
    assert lines == ["Write: notes.md"]


def test_an_opencode_handoff_reports_its_tool_steps_and_final_text(tmp_path):
    result, lines = _run(tmp_path, "opencode", OPENCODE_OK, model="opencode/big-pickle")
    assert result["status"] == "completed" and result["summary"] == "Created hello.txt containing hi."
    assert lines == ["Creating the requested file.", "apply_patch", "bash: ls", "Created hello.txt containing hi."]
    assert result["session_id"] == "ses_9"  # what a follow-up continues


def test_a_cursor_handoff_reports_its_tool_steps_in_either_shape_and_its_result(tmp_path):
    result, lines = _run(tmp_path, "cursor", CURSOR_OK)
    assert result["status"] == "completed" and result["summary"] == "Fixed app.py; tests pass."
    assert lines == ["Running the tests.", "shell: pytest -q", "edit: app.py"]
    assert result["session_id"] == "c-1" and result["model"] == "GPT-6 Luna"


def test_a_gemini_handoff_joins_its_streamed_text_and_keeps_only_what_it_said_last(tmp_path):
    result, lines = _run(tmp_path, "gemini", GEMINI_OK)
    assert result["status"] == "completed" and result["summary"] == "Fixed app.py; tests pass."
    assert lines == ["Let me", "Let me look.", "run_shell_command: pytest -q", "Fixed app.py;", "Fixed app.py; tests pass."]
    assert result["session_id"] == "g-1" and result["model"] == "gemini-3-pro"


def test_a_gemini_error_result_fails_the_run_with_its_sentence(tmp_path):
    result, _ = _run(tmp_path, "gemini", GEMINI_QUOTA)
    assert result["error"] == "Gemini CLI did not finish: You have exhausted your daily quota."


def test_a_signed_out_cursor_or_gemini_fails_with_the_words_it_printed(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    script = tmp_path / "signed_out.py"
    script.write_text("import sys\nprint(\"Error: Authentication required. Please run 'agent login' first.\")\nsys.exit(1)\n")
    result = delegate.run_agent("cursor", "unused", "t", work, argv=[sys.executable, str(script)])
    assert result["error"] == "Cursor did not finish: Error: Authentication required. Please run 'agent login' first."


def test_an_opencode_answer_split_into_several_parts_comes_back_whole(tmp_path):
    split = [
        OPENCODE_OK[4],  # a step_start
        {"type": "text", "sessionID": "ses_9", "part": {"type": "text", "text": "Fixed add() to return `a + b"}},
        {"type": "text", "sessionID": "ses_9", "part": {"type": "text", "text": "`.\n\nAdded test_calc.py."}},
        OPENCODE_OK[-1],
    ]
    result, _ = _run(tmp_path, "opencode", OPENCODE_OK[:4] + split, model="opencode/big-pickle")
    assert result["summary"] == "Fixed add() to return `a + b`.\n\nAdded test_calc.py."


def test_an_agent_is_told_its_own_folder_even_through_pwd_which_opencode_follows(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    script = tmp_path / "where.py"
    script.write_text("import os\nopen('pwd.txt', 'w').write(os.environ['PWD'])\n", encoding="utf-8")
    delegate.run_agent("opencode", "unused", "t", work, argv=[sys.executable, str(script)])
    assert (work / "pwd.txt").read_text() == str(work)


def test_an_opencode_error_fails_the_run_even_though_opencode_exits_cleanly(tmp_path):
    result, _ = _run(tmp_path, "opencode", OPENCODE_UNKNOWN_MODEL, model="nope/nothing")
    assert result["error"] == "opencode did not finish: Unexpected server error. Check server logs for details."


def test_a_model_opencodes_service_has_retired_is_replaced_by_the_one_it_names_and_the_round_runs_again(tmp_path):
    # Recorded 2026-10-24: Latest picked a free model opencode still listed but had retired.
    retired = {"type": "error", "sessionID": "ses_7", "error": {"name": "APIError", "data": {
        "message": "Model minimax-m3.1-flash-free has been deprecated. Use deepseek-v4.1-flash-free instead.",
        "statusCode": 410, "isRetryable": False}}}
    work = tmp_path / "work"
    work.mkdir()
    script = tmp_path / "retiring.py"
    script.write_text(
        "import json, sys\n"
        "sys.stdin.read()\n"
        "args = sys.argv[1:]\n"
        "open('models.txt', 'a').write(args[args.index('-m') + 1] + '\\n')\n"
        f"events = {[retired]!r} if 'minimax' in args[args.index('-m') + 1] else {OPENCODE_OK!r}\n"
        "for e in events: print(json.dumps(e), flush=True)\n",
        encoding="utf-8",
    )
    delegate._catalogs["opencode"].update(at=time.monotonic(), models=[{"id": "opencode/minimax-m3.1-flash-free"}])
    lines: list[str] = []

    real = delegate.agent_command

    def argv_for(*a, **kw):
        return [sys.executable, str(script), *real("opencode", "x", model=kw["model"])[1:]]

    delegate.agent_command = argv_for
    try:
        result = delegate.run_agent("opencode", "x", "t", work, report=lines.append, model="opencode/minimax-m3.1-flash-free")
    finally:
        delegate.agent_command = real

    assert result["status"] == "completed" and result["model"] == "opencode/deepseek-v4.1-flash-free"
    assert (work / "models.txt").read_text().split() == ["opencode/minimax-m3.1-flash-free", "opencode/deepseek-v4.1-flash-free"]
    assert lines[0] == "minimax-m3.1-flash-free has been retired; using opencode/deepseek-v4.1-flash-free instead"
    assert delegate._catalogs["opencode"]["models"] == []  # Latest stops offering it


def test_an_opencode_run_cut_off_between_steps_is_not_reported_as_finished(tmp_path):
    result, _ = _run(tmp_path, "opencode", OPENCODE_OK[:4], model="opencode/big-pickle")
    assert "status" not in result and result["error"].startswith("opencode did not finish")


def test_a_signed_out_claude_code_comes_back_as_an_error_that_says_why(tmp_path):
    result, _ = _run(tmp_path, "claude_code", CLAUDE_SIGNED_OUT)
    assert "status" not in result
    assert result["error"] == (
        "Claude Code did not finish: Failed to authenticate: OAuth session expired and could not be refreshed"
    )


def test_a_failed_codex_turn_reports_the_providers_sentence_not_nested_json(tmp_path):
    result, lines = _run(tmp_path, "codex", CODEX_TOO_OLD)
    assert result["error"].startswith("Codex did not finish: The 'gpt-6-astra' model requires a newer version")
    assert lines == []  # Codex's warnings about its own setup are not progress


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


def test_an_agent_that_goes_silent_is_stopped_long_before_the_time_limit(tmp_path):
    started = time.monotonic()
    result, _ = _run(tmp_path, "codex", CODEX_OK[:2], sleep=30, silence=0.5)
    assert time.monotonic() - started < 10
    assert result["error"].startswith("Codex showed no activity for 1 minutes and was stopped")


def test_a_run_past_its_time_limit_is_stopped_and_says_so(tmp_path):
    result, _ = _run(tmp_path, "codex", [], sleep=30, timeout=0.5)
    assert result["error"] == "Codex was still working at its 1-minute limit and was stopped."


# -- the team: several agents, their own branches, feedback rounds ---------------------------

TEAM_AGENT = """import json, os, sys, time
task = sys.stdin.read()
key = sys.argv[1]
resume = sys.argv[2] if len(sys.argv) > 2 else ""
sid = resume or "thr-" + str(os.getpid())
if key == "opencode":
    print(json.dumps({"type": "step_start", "sessionID": sid, "part": {}}), flush=True)
else:
    print(json.dumps({"type": "thread.started", "thread_id": sid}), flush=True)
if task.startswith("sleep"):
    print(json.dumps({"type": "item.started", "item": {"type": "command_execution", "command": "make"}}), flush=True)
    time.sleep(30)
for line in task.splitlines():
    if line.startswith("write "):
        name, text = line[6:].split("=", 1)
        open(name, "w").write(text)
reply = ("resumed " + resume + ": " if resume else "") + "done " + task.strip()
if key == "opencode":
    print(json.dumps({"type": "text", "sessionID": sid, "part": {"text": reply}}), flush=True)
    print(json.dumps({"type": "step_finish", "sessionID": sid, "part": {"reason": "stop"}}), flush=True)
else:
    print(json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": reply}}), flush=True)
    print(json.dumps({"type": "turn.completed"}), flush=True)
"""


@pytest.fixture(autouse=True)
def _no_jobs_from_other_tests():
    delegate._JOBS.clear()
    yield
    delegate._stop_all([j for j in delegate._JOBS.values() if j.status == "running"])
    delegate._JOBS.clear()


def _team(tmp_path, monkeypatch, folder, session="s1"):
    script = tmp_path / "team_agent.py"
    script.write_text(TEAM_AGENT, encoding="utf-8")
    monkeypatch.setattr(delegate, "available_agents", lambda: {"codex": "codex", "claude_code": "claude", "opencode": "opencode"})
    monkeypatch.setattr(delegate, "connection_problem", lambda key: "")
    monkeypatch.setattr(delegate, "find_agent", lambda key: delegate.AGENTS[key][1])
    monkeypatch.setattr(delegate, "codex_models", lambda exe: [])  # never the real catalog
    monkeypatch.setattr(delegate, "_opencode_model", lambda exe, sid: "")  # nor the real opencode
    monkeypatch.setattr(
        delegate, "agent_command",
        lambda key, exe, resume_id="", **_: [sys.executable, str(script), key, *([resume_id] if resume_id else [])],
    )
    tools = delegate.agent_team_tools(workspace=folder, roots=[RootDir(folder, writable=True)], session_id=session)
    return {t.__name__: t for t in tools}


def _repo(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=repo, check=True)
    (repo / "app.py").write_text("print(1)\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "start"], cwd=repo, check=True)
    return repo


def _wait_all(t, n):
    done = []
    while len(done) < n:
        done += t["wait_for_agents"](timeout_minutes=1)["finished"]
    return {d["name"]: d for d in done}


def test_parallel_agents_each_work_on_their_own_branch_and_leave_the_main_folder_alone(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    t = _team(tmp_path, monkeypatch, repo)
    a = t["start_agent"](agent="codex", task="write api.py=A", name="backend")
    b = t["start_agent"](agent="claude_code", task="write docs.md=B", name="docs")
    assert a["branch"] == "mimi/codex-backend" and b["branch"] == "mimi/claude-docs"
    done = _wait_all(t, 2)
    assert done["backend"]["changed_files"] == ["api.py"] and done["docs"]["changed_files"] == ["docs.md"]
    assert (Path(a["workdir"]) / "api.py").read_text() == "A"
    assert not (repo / "api.py").exists() and not (repo / "docs.md").exists()
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout
    assert status == ""  # the agents' copies never show up as untracked files


def test_a_mixed_team_with_opencode_works_on_three_branches_and_opencode_takes_feedback_in_its_own_session(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    t = _team(tmp_path, monkeypatch, repo)
    starts = {
        "api": t["start_agent"](agent="codex", task="write api.py=A", name="api"),
        "docs": t["start_agent"](agent="claude_code", task="write docs.md=B", name="docs"),
        "tests": t["start_agent"](agent="opencode", task="write test_api.py=C", name="tests"),
    }
    assert starts["tests"]["branch"] == "mimi/opencode-tests" and starts["tests"]["agent"] == "opencode"
    done = _wait_all(t, 3)
    assert done["tests"]["status"] == "completed" and done["tests"]["changed_files"] == ["test_api.py"]
    assert done["tests"]["resume_command"].endswith(f"opencode --session {done['tests']['session_id']}")
    assert not (repo / "test_api.py").exists()

    again = t["message_agent"](job=starts["tests"]["job"], message="write test_api.py=D")
    second = _wait_all(t, 1)["tests"]
    assert second["summary"].startswith(f"resumed {done['tests']['session_id']}: ")
    assert again["branch"] == "mimi/opencode-tests" and (Path(again["workdir"]) / "test_api.py").read_text() == "D"
    log = subprocess.run(["git", "log", "-1", "--format=%s", "mimi/opencode-tests"], cwd=repo, capture_output=True, text=True)
    assert log.stdout.strip() == "opencode: tests"


def test_each_round_is_committed_on_the_agents_branch_so_a_merge_brings_the_work_in(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    t = _team(tmp_path, monkeypatch, repo)
    a = t["start_agent"](agent="codex", task="write api.py=A", name="backend")
    b = t["start_agent"](agent="codex", task="write docs.md=B", name="docs")
    done = _wait_all(t, 2)
    assert done["backend"]["commit"] and done["docs"]["commit"]
    log = subprocess.run(["git", "log", "-1", "--format=%s", a["branch"]], cwd=repo, capture_output=True, text=True)
    assert log.stdout.strip() == "Codex: backend"
    for branch in (a["branch"], b["branch"]):
        subprocess.run(["git", "merge", "-q", "--no-edit", branch], cwd=repo, check=True)
    assert (repo / "api.py").read_text() == "A" and (repo / "docs.md").read_text() == "B"
    # Agents are told not to commit: their own commit fails inside the sandbox.
    assert done["backend"]["summary"].endswith("Do not run git commit.)")


def test_agent_tool_logs_stay_out_of_the_branch_but_tracked_agent_files_still_commit(tmp_path):
    repo = _repo(tmp_path)
    (repo / ".claude").mkdir()
    (repo / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "settings"], cwd=repo, check=True)
    (repo / ".claude" / "logs").mkdir()
    (repo / ".claude" / "logs" / "session-1.md").write_text("log", encoding="utf-8")
    (repo / ".codex").mkdir()
    (repo / ".codex" / "run.log").write_text("log", encoding="utf-8")
    assert delegate.commit_round(repo, "Codex: logs only", {}) == ""  # nothing of the project's changed
    (repo / ".claude" / "settings.json").write_text('{"x": 1}', encoding="utf-8")
    (repo / "app.py").write_text("print(2)\n", encoding="utf-8")
    assert delegate.commit_round(repo, "Codex: fix", {})
    files = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=repo, capture_output=True, text=True)
    assert files.stdout.split() == [".claude/settings.json", "app.py"]


def test_caches_and_installs_left_by_a_test_run_stay_out_of_the_branch(tmp_path):
    repo = _repo(tmp_path)
    for junk in ("__pycache__/app.pyc", "pkg/__pycache__/m.pyc", "node_modules/x/index.js", ".pytest_cache/v"):
        (repo / junk).parent.mkdir(parents=True, exist_ok=True)
        (repo / junk).write_text("x", encoding="utf-8")
    (repo / "pkg" / "m.py").write_text("y = 1\n", encoding="utf-8")
    assert delegate.commit_round(repo, "Codex: pkg", {})
    files = subprocess.run(["git", "show", "--name-only", "--format=", "HEAD"], cwd=repo, capture_output=True, text=True)
    assert files.stdout.split() == ["pkg/m.py"]


def test_an_agents_work_is_committed_even_without_a_git_identity(tmp_path, monkeypatch):
    repo = tmp_path / "bare-identity"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "a.txt").write_text("1", encoding="utf-8")
    ident = ["-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", *ident, "add", "."], cwd=repo, check=True)
    subprocess.run(["git", *ident, "commit", "-qm", "start"], cwd=repo, check=True)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-global"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("HOME", str(tmp_path))
    (repo / "a.txt").write_text("2", encoding="utf-8")
    assert delegate.commit_round(repo, "Codex: x", {"summary": "changed a"})
    assert subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout == ""


def test_feedback_continues_the_same_agent_session_on_the_same_branch(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    t = _team(tmp_path, monkeypatch, repo)
    job = t["start_agent"](agent="codex", task="write api.py=v1", name="backend")["job"]
    first = _wait_all(t, 1)["backend"]
    again = t["message_agent"](job=job, message="write api.py=v2")
    assert again["status"] == "running" and again["branch"] == first["branch"]
    second = _wait_all(t, 1)["backend"]
    assert second["summary"].startswith("resumed thr-")  # the agent's own session id came back
    assert (Path(again["workdir"]) / "api.py").read_text() == "v2"


def test_outside_git_the_agent_works_in_the_folder_itself(tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    t = _team(tmp_path, monkeypatch, plain)
    started = t["start_agent"](agent="codex", task="write a.txt=x", name="one")
    assert "branch" not in started and "separate files" in started["note"]
    _wait_all(t, 1)
    assert (plain / "a.txt").read_text() == "x"


def test_a_message_from_the_user_ends_the_wait_but_not_the_agents(tmp_path, monkeypatch):
    t = _team(tmp_path, monkeypatch, _repo(tmp_path))
    job = t["start_agent"](agent="codex", task="sleep", name="slow")["job"]
    flag = threading.Event()
    threading.Timer(0.5, flag.set).start()
    token = tool_yield.set(flag)
    try:
        result = t["wait_for_agents"](timeout_minutes=1)
    finally:
        tool_yield.reset(token)
    assert "user sent a message" in result["note"]
    assert result["still_working"][0]["job"] == job
    assert t["stop_agent"](job=job)["status"] == "stopped"


def test_pressing_stop_during_the_wait_stops_every_agent(tmp_path, monkeypatch):
    t = _team(tmp_path, monkeypatch, _repo(tmp_path))
    t["start_agent"](agent="codex", task="sleep", name="slow")
    stop = threading.Event()
    threading.Timer(0.5, stop.set).start()
    token = tool_stop.set(stop)
    try:
        result = t["wait_for_agents"](timeout_minutes=1)
    finally:
        tool_stop.reset(token)
    assert result["error"].startswith("Stopped. The agents were stopped too")
    assert t["wait_for_agents"](timeout_minutes=0)["still_working"] == []


def test_the_wait_shows_every_working_agents_latest_step(tmp_path, monkeypatch):
    t = _team(tmp_path, monkeypatch, _repo(tmp_path))
    jobs = [t["start_agent"](agent="codex", task="sleep", name=n)["job"] for n in ("one", "two")]
    seen: list[str] = []
    token = tool_progress.set(seen.append)
    try:
        t["wait_for_agents"](timeout_minutes=0.02)
    finally:
        tool_progress.reset(token)
        for job in jobs:
            t["stop_agent"](job=job)
    assert "Codex · one: Running: make\nCodex · two: Running: make" in seen


def test_feedback_waits_until_the_agent_has_finished(tmp_path, monkeypatch):
    t = _team(tmp_path, monkeypatch, _repo(tmp_path))
    job = t["start_agent"](agent="codex", task="sleep", name="slow")["job"]
    assert "still working" in t["message_agent"](job=job, message="hurry")["error"]
    t["stop_agent"](job=job)


def test_jobs_belong_to_their_own_conversation(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    mine = _team(tmp_path, monkeypatch, repo, session="mine")
    theirs = _team(tmp_path, monkeypatch, repo, session="theirs")
    job = mine["start_agent"](agent="codex", task="write x.txt=1", name="x")["job"]
    assert "No agent job" in theirs["stop_agent"](job=job)["error"]
    _wait_all(mine, 1)


def test_no_more_than_four_agents_work_at_once(tmp_path, monkeypatch):
    t = _team(tmp_path, monkeypatch, _repo(tmp_path))
    jobs = [t["start_agent"](agent="codex", task="sleep", name=f"n{i}")["job"] for i in range(4)]
    assert "already working" in t["start_agent"](agent="codex", task="sleep", name="n5")["error"]
    for job in jobs:
        t["stop_agent"](job=job)


def test_a_folder_outside_the_writable_roots_is_refused_before_anything_runs(tmp_path, monkeypatch):
    mine = tmp_path / "mine"
    mine.mkdir()
    readonly = tmp_path / "readonly"
    readonly.mkdir()
    t = _team(tmp_path, monkeypatch, mine)
    assert "outside the folders" in t["start_agent"](agent="codex", task="t", folder=str(readonly))["error"]
    assert "outside the folders" in t["start_agent"](agent="codex", task="t", folder="../readonly")["error"]


def test_an_agent_that_is_not_connected_is_refused_with_the_reason(tmp_path, monkeypatch):
    monkeypatch.setattr(delegate, "available_agents", lambda: {"codex": "codex"})
    monkeypatch.setattr(delegate, "connection_problem", lambda key: "Claude Code is not installed." if key == "claude_code" else "")
    t = delegate.agent_team_tools(workspace=tmp_path, session_id="x")
    assert t[0](agent="claude_code", task="t")["error"] == "Claude Code is not installed."
    assert "not a coding agent" in t[0](agent="antigravity", task="t")["error"]


def test_each_round_uses_the_model_and_effort_chosen_on_the_coding_agents_page(tmp_path, monkeypatch):
    t = _team(tmp_path, monkeypatch, tmp_path)
    seen: list[dict] = []
    fake = delegate.agent_command  # _team's stand-in agent
    monkeypatch.setattr(delegate, "agent_command", lambda key, exe, resume_id="", **kw: seen.append(kw) or fake(key, exe, resume_id))
    delegate.save_settings("codex", "gpt-6-astra", "high")
    try:
        t["start_agent"](agent="codex", task="t")
        _wait_all(t, 1)
    finally:
        delegate._settings.clear()
    assert seen == [{"model": "gpt-6-astra", "effort": "high", "skip_hooks": False}]


def test_starting_an_agent_needs_approval_but_watching_and_feedback_do_not(tmp_path, monkeypatch):
    t = _team(tmp_path, monkeypatch, tmp_path)
    engine = PermissionEngine(workspace_root=tmp_path)
    meta = {name: fn.__aisuite_tool_metadata__ for name, fn in t.items()}
    assert classify("start_agent", meta["start_agent"]) is RiskClass.EXTERNAL
    assert engine.evaluate("start_agent", {"task": "t"}, meta["start_agent"]).needs_user
    for name in ("wait_for_agents", "message_agent", "stop_agent"):
        assert engine.evaluate(name, {}, meta[name]).allowed


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


def test_a_priority_message_from_the_user_reaches_a_long_waiting_tool(tmp_path):
    loop_box: list = []

    def long_wait():
        """Wait for the user."""
        flag = tool_yield.get()
        loop, engine = loop_box
        loop.call_soon_threadsafe(lambda: engine.queue_steering("look at this", priority=True))
        return {"yielded": flag.wait(timeout=5)}

    turns = [
        AssistantTurn(tool_calls=[ToolCall(id="c1", name="long_wait", arguments={})], finish_reason="tool_calls"),
        AssistantTurn(text="read it", finish_reason="stop"),
    ]
    registry = ToolRegistry()
    registry.register(long_wait, metadata=ai.ToolMetadata(category="x", risk_level="medium"))
    engine = TurnEngine(
        provider=ScriptedProvider(turns),
        registry=registry,
        permissions=PermissionEngine(workspace_root=tmp_path),
        model="gpt-5.5",
    )

    async def _go():
        loop_box[:] = [asyncio.get_running_loop(), engine]
        return [ev async for ev in engine.run("go")]

    asyncio.run(_go())
    tool_msg = next(m for m in engine.messages if m.get("role") == "tool")
    assert json.loads(tool_msg["content"]) == {"yielded": True}
