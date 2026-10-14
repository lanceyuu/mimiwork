"""The `delegate_to_agent` tool — hand a coding task to Claude Code or Codex on this computer.

Mimi plans and writes the deliverable; an outside coding agent the user already has does the
software work in a granted folder, and only its final summary plus the list of files it
changed come back. The agent runs headless (`claude -p` / `codex exec`) under its own safety
model — `roots.py` cannot confine another program — so every hand-off is approval-gated and
the card says so. It also bills the user's own Claude or OpenAI account, not QualiTaTi credits.

Both CLIs stream JSON lines. Each line that means something to a person (a command, an edit,
a sentence of narration) becomes a progress line on the running step via `tool_progress`;
the rest is ignored, so a format change degrades to a quieter card, never a crash.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import aisuite as ai

from .cancellation import tool_stop
from .context import tool_progress

_IS_WINDOWS = sys.platform == "win32"

# key → (label, executable, whose account pays)
AGENTS: dict[str, tuple[str, str, str]] = {
    "claude_code": ("Claude Code", "claude", "your own Claude account"),
    "codex": ("Codex", "codex", "your own OpenAI account"),
}

# An app opened from Finder inherits launchd's PATH (/usr/bin:/bin:…), which holds neither
# CLI — and Codex is a `#!/usr/bin/env node` script, so the child needs these dirs too.
_EXTRA_DIRS = [
    "~/.local/bin",
    "~/.claude/local",
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "~/.npm-global/bin",
    "~/.volta/bin",
    "~/.bun/bin",
    "~/AppData/Roaming/npm",
]

# A real coding task takes minutes; past this the run is stopped and reported as such.
_TIMEOUT = 30 * 60
_SUMMARY_CHARS = 8000
_MAX_CHANGED = 200
# Snapshotting a huge folder to find changed files would cost more than the run; skip it.
_MAX_SNAPSHOT = 50_000
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}


def _search_path() -> str:
    extra = [str(Path(d).expanduser()) for d in _EXTRA_DIRS]
    return os.pathsep.join([*extra, os.environ.get("PATH", "")])


def find_agent(key: str) -> str:
    """The executable for `key`, or "" when it is not installed."""
    return shutil.which(AGENTS[key][1], path=_search_path()) or ""


def available_agents() -> dict[str, str]:
    return {key: path for key in AGENTS if (path := find_agent(key))}


def agent_command(key: str, executable: str) -> list[str]:
    """argv for a headless run; the task goes in on stdin (no length or leading-dash trouble)."""
    if key == "claude_code":
        # Auto mode (owner's choice, 2026-10-15): Claude Code's own classifier approves safe
        # edits and commands, so a headless run can test its work instead of having every
        # command denied for want of someone to ask.
        return [
            executable, "-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "auto",
        ]
    return [executable, "exec", "--json", "--skip-git-repo-check", "--sandbox", "workspace-write", "-"]


def _short(text: str, n: int = 140) -> str:
    line = " ".join(str(text).split())
    return line if len(line) <= n else line[: n - 1] + "…"


def _error_text(raw: Any) -> str:
    """Codex nests the provider's JSON error inside a string; dig the sentence out."""
    text = str(raw or "")
    try:
        data = json.loads(text)
        return str(data.get("error", {}).get("message") or data.get("message") or text)
    except (ValueError, AttributeError):
        return text


class _Run:
    """What a stream of agent events adds up to: progress lines, final text, outcome."""

    def __init__(self) -> None:
        self.summary = ""
        self.error = ""
        self.finished = False

    def claude(self, event: dict) -> list[str]:
        kind = event.get("type")
        if kind == "assistant":
            out = []
            for block in (event.get("message") or {}).get("content") or []:
                if block.get("type") == "text" and block.get("text", "").strip():
                    out.append(_short(block["text"]))
                elif block.get("type") == "tool_use":
                    args = block.get("input") or {}
                    target = args.get("command") or args.get("file_path") or args.get("pattern") or ""
                    out.append(_short(f"{block.get('name', 'tool')}: {target}" if target else block.get("name", "tool")))
            return out
        if kind == "result":
            self.finished = True
            text = str(event.get("result") or "")
            if event.get("is_error"):
                self.error = text or "Claude Code stopped with an error"
            else:
                self.summary = text
        return []

    def codex(self, event: dict) -> list[str]:
        kind = event.get("type")
        item = event.get("item") or {}
        itype = item.get("type")
        if kind == "item.started" and itype == "command_execution":
            return [_short(f"Running: {item.get('command', '')}")]
        if kind == "item.completed":
            if itype == "agent_message":
                self.summary = str(item.get("text") or "")
                return [_short(self.summary)]
            if itype == "file_change":
                paths = [c.get("path", "") for c in item.get("changes") or []]
                return [_short("Changed " + ", ".join(Path(p).name for p in paths if p))] if paths else []
            if itype == "error":  # a warning; the run carries on
                return [_short(item.get("message", ""))]
        if kind == "turn.completed":
            # A top-level "error" can be a reconnect notice that the turn survived.
            self.finished, self.error = True, ""
        if kind in ("turn.failed", "error"):
            self.finished = self.finished or kind == "turn.failed"
            self.error = _error_text((event.get("error") or {}).get("message") or event.get("message"))
        return []


def _snapshot(folder: Path) -> Optional[dict[str, tuple[int, int]]]:
    seen: dict[str, tuple[int, int]] = {}
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath, name)
            try:
                st = path.stat()
            except OSError:
                continue
            seen[str(path.relative_to(folder))] = (st.st_mtime_ns, st.st_size)
            if len(seen) > _MAX_SNAPSHOT:
                return None
    return seen


def changed_files(before: Optional[dict], after: Optional[dict]) -> Optional[list[str]]:
    """Files created, modified or removed between two snapshots (None when either was skipped)."""
    if before is None or after is None:
        return None
    return sorted(p for p in before.keys() | after.keys() if before.get(p) != after.get(p))


def _minutes(seconds: float) -> str:
    n = max(1, round(seconds / 60))
    return f"{n}-minute"


def _kill(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        if _IS_WINDOWS:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (OSError, subprocess.SubprocessError):
        pass


def run_agent(
    key: str,
    executable: str,
    task: str,
    folder: Path,
    *,
    report: Callable[[str], None] = lambda _line: None,
    stop: Optional[threading.Event] = None,
    timeout: float = _TIMEOUT,
    argv: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Run one headless hand-off to completion, streaming progress through `report`."""
    label = AGENTS[key][0]
    env = {**os.environ, "PATH": _search_path(), "NO_COLOR": "1"}
    spawn: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if _IS_WINDOWS else {"start_new_session": True}
    )
    before = _snapshot(folder)
    try:
        proc = subprocess.Popen(
            argv or agent_command(key, executable),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(folder),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **spawn,
        )
    except OSError as exc:
        return {"error": f"Could not start {label}: {exc}"}
    assert proc.stdin is not None and proc.stdout is not None
    try:
        proc.stdin.write(task)
        proc.stdin.close()
    except OSError:
        pass  # it exited before reading; its output says why

    lines: queue.Queue[Optional[str]] = queue.Queue()

    def _read(stream: Iterable[str]) -> None:
        for line in stream:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=_read, args=(proc.stdout,), daemon=True).start()

    run = _Run()
    parse = run.claude if key == "claude_code" else run.codex
    plain: list[str] = []  # non-JSON output (startup errors, stack traces)
    deadline = time.monotonic() + timeout
    outcome = ""
    while True:
        if stop is not None and stop.is_set():
            outcome = "stopped"
            break
        if time.monotonic() > deadline:
            outcome = "timed out"
            break
        try:
            line = lines.get(timeout=0.25)
        except queue.Empty:
            continue
        if line is None:
            break
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            plain.append(line)
            continue
        if isinstance(event, dict):
            for text in parse(event):
                try:
                    if text:
                        report(text)
                except RuntimeError:
                    pass  # the turn's loop is gone (stopped turn); finish the run quietly
    if outcome:
        _kill(proc)
    try:
        code = proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        _kill(proc)
        code = None

    changed = changed_files(before, _snapshot(folder))
    result: dict[str, Any] = {"agent": label, "folder": str(folder)}
    if changed is not None:
        result["changed_files"] = changed[:_MAX_CHANGED]
        if len(changed) > _MAX_CHANGED:
            result["changed_files_note"] = f"{len(changed) - _MAX_CHANGED} more not listed"
    if run.summary:
        result["summary"] = run.summary[:_SUMMARY_CHARS]
    if outcome == "stopped":
        return {**result, "error": f"Stopped. {label} may have changed some files before it stopped."}
    if outcome == "timed out":
        return {**result, "error": f"{label} was still working at its {_minutes(timeout)} limit and was stopped."}
    if run.error or (code not in (0, None) and not run.summary) or not run.finished:
        why = run.error or _short(" ".join(plain[-5:]), 600) or f"exited with code {code}"
        return {**result, "error": f"{label} did not finish: {why}"}
    return {**result, "status": "completed"}


def _resolve_folder(folder: str, roots: list, workspace: Path) -> Path | str:
    """The folder to work in: inside a writable granted folder, or an error string."""
    writable = [Path(r.path) for r in roots if r.writable] if roots else [workspace]
    if not writable:
        return "No folder you can change is open in this conversation."
    if not folder.strip():
        return writable[0]
    path = Path(folder).expanduser()
    path = (path if path.is_absolute() else writable[0] / path).resolve()
    if not any(path == w or w in path.parents for w in writable):
        return f"{folder} is outside the folders this conversation may change."
    if not path.is_dir():
        return f"{folder} is not a folder."
    return path


def delegate_tools(*, workspace: str | Path, roots: Optional[list] = None) -> list:
    """The tool, or nothing when neither agent is installed (an unusable tool misleads the model)."""
    installed = available_agents()
    if not installed:
        return []
    ws = Path(workspace).resolve()
    choices = ", ".join(f"'{k}' ({AGENTS[k][0]})" for k in installed)

    def delegate_to_agent(agent: str, task: str, folder: str = "") -> dict:
        key = agent.strip().lower().replace(" ", "_")
        if key not in installed:
            return {"error": f"'{agent}' is not available here. Installed: {choices}."}
        where = _resolve_folder(folder, roots or [], ws)
        if isinstance(where, str):
            return {"error": where}
        return run_agent(
            key,
            installed[key],
            task,
            where,
            report=tool_progress.get() or (lambda _line: None),
            stop=tool_stop.get(),
        )

    delegate_to_agent.__doc__ = f"""Hand a software task to a coding agent installed on this
        computer, which works on its own in a folder and reports back. Use it when the user
        asks for Claude Code or Codex by name, or for substantial code work: building or
        fixing a program, refactoring, running and repairing tests. Do the writing, analysis
        and documents yourself. The agent cannot see this conversation: put everything it
        needs in `task` (goal, files, constraints, how to check the work). You get its final
        summary and the files it changed; check them before reporting to the user.

        Args:
            agent (str): Which agent: {choices}.
            task (str): The complete, self-contained instructions.
            folder (str): Folder to work in, relative to the main folder or absolute. It
                must be a folder you may change. Empty means the main folder.
        """
    return [
        ai.tool(
            delegate_to_agent,
            metadata=ai.ToolMetadata(
                category="agent",
                risk_level="high",
                capabilities=["execute", "write"],
                requires_approval=True,
            ),
        )
    ]
