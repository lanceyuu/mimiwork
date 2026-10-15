"""A small team of coding agents — Mimi hands work to Claude Code and Codex and reviews it.

Mimi splits a project into tasks, starts an agent on each (`start_agent`), watches them all
(`wait_for_agents`), reviews what comes back, and sends feedback into the same agent session
(`message_agent`) until the work is right. In a git project every agent gets its own worktree
and branch, so parallel agents never collide and nothing reaches the user's branch until a
merge — which goes through the shell and so asks the user. Each agent runs headless (`claude -p` / `codex exec`) under its own safety
model — `roots.py` cannot confine another program — so starting one is approval-gated and
the card says so. It also bills the user's own Claude or OpenAI account, not QualiTaTi credits.

Both CLIs stream JSON lines. Each line that means something to a person (a command, an edit,
a sentence of narration) becomes a progress line on the running step via `tool_progress`;
the rest is ignored, so a format change degrades to a quieter card, never a crash.
"""

from __future__ import annotations

import atexit
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
from .context import tool_progress, tool_yield

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
_SKIP_DIRS = {".git", ".mimiwork", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}


def _search_path() -> str:
    extra = [str(Path(d).expanduser()) for d in _EXTRA_DIRS]
    return os.pathsep.join([*extra, os.environ.get("PATH", "")])


def find_agent(key: str) -> str:
    """The executable for `key`, or "" when it is not installed."""
    return shutil.which(AGENTS[key][1], path=_search_path()) or ""


def available_agents() -> dict[str, str]:
    return {key: path for key in AGENTS if (path := find_agent(key))}


def agent_command(key: str, executable: str, resume_id: str = "") -> list[str]:
    """argv for a headless run; the task goes in on stdin (no length or leading-dash trouble).
    With `resume_id`, the message continues that agent session, its memory intact."""
    if key == "claude_code":
        # Auto mode (owner's choice, 2026-10-15): Claude Code's own classifier approves safe
        # edits and commands, so a headless run can test its work instead of having every
        # command denied for want of someone to ask.
        return [
            executable, "-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "auto",
            *(["--resume", resume_id] if resume_id else []),
        ]
    # `exec resume` takes no --sandbox flag; the config key sets the same policy for both.
    sandbox = ["-c", 'sandbox_mode="workspace-write"']
    if resume_id:
        return [executable, "exec", "resume", "--json", "--skip-git-repo-check", *sandbox, resume_id, "-"]
    return [executable, "exec", "--json", "--skip-git-repo-check", *sandbox, "-"]


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
        self.session_id = ""  # what a follow-up resumes

    def claude(self, event: dict) -> list[str]:
        kind = event.get("type")
        self.session_id = str(event.get("session_id") or self.session_id)
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
        if kind == "thread.started":
            self.session_id = str(event.get("thread_id") or "")
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
    resume_id: str = "",
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
            argv or agent_command(key, executable, resume_id),
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
    result: dict[str, Any] = {"agent": label, "folder": str(folder), "session_id": run.session_id or resume_id}
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




def _git(cwd: Path, *args: str) -> tuple[bool, str]:
    try:
        done = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=60,
            env={**os.environ, "PATH": _search_path(), "GIT_TERMINAL_PROMPT": "0"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    return done.returncode == 0, (done.stdout or done.stderr).strip()


def isolate(folder: Path, slug: str) -> tuple[Path, str]:
    """A worktree on a new branch `mimi/<slug>` for one agent, or (folder, "") outside git.

    Worktrees live under `<repo>/.mimiwork/agents/` — inside the granted folder, so the
    privacy model still holds — and `.mimiwork/` is added to the repo's local exclude list so
    they never show up as untracked files in the user's own status."""
    ok, top = _git(folder, "rev-parse", "--show-toplevel")
    if not ok or not _git(folder, "rev-parse", "--verify", "HEAD")[0]:
        return folder, ""  # not a repo, or one with no commit to branch from
    top_path = Path(top).resolve()
    ok, common = _git(top_path, "rev-parse", "--git-common-dir")
    if ok:
        exclude = (top_path / common).resolve() / "info" / "exclude"
        try:
            text = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
            if ".mimiwork/" not in text.split("\n"):
                exclude.parent.mkdir(parents=True, exist_ok=True)
                exclude.write_text(text + ("" if text.endswith("\n") or not text else "\n") + ".mimiwork/\n", encoding="utf-8")
        except OSError:
            pass
    for n in range(1, 100):
        name = slug if n == 1 else f"{slug}-{n}"
        place = top_path / ".mimiwork" / "agents" / name
        if place.exists() or _git(top_path, "rev-parse", "--verify", f"refs/heads/mimi/{name}")[0]:
            continue
        ok, why = _git(top_path, "worktree", "add", "-q", "-b", f"mimi/{name}", str(place), "HEAD")
        if not ok:
            return folder, ""
        return place / folder.relative_to(top_path), f"mimi/{name}"
    return folder, ""


def _slug(text: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")
    return "-".join(p for p in out.split("-") if p)[:40] or "task"


class Job:
    """One agent working on one task, across as many feedback rounds as it takes."""

    def __init__(self, session: str, key: str, executable: str, name: str, workdir: Path, branch: str):
        self.id = f"{_slug(name)}-{os.urandom(2).hex()}"
        self.session, self.key, self.executable = session, key, executable
        self.name, self.workdir, self.branch = name, workdir, branch
        self.label = AGENTS[key][0]
        self.resume_id = ""
        self.status = "running"
        self.last = "Starting…"
        self.result: dict[str, Any] = {}
        self.reported = True
        self.stop = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def launch(self, message: str) -> None:
        self.status, self.last, self.reported = "running", "Starting…", False
        self.stop = threading.Event()

        def note(line: str) -> None:
            self.last = line

        def work() -> None:
            result = run_agent(
                self.key, self.executable, message, self.workdir,
                report=note, stop=self.stop, resume_id=self.resume_id,
            )
            self.resume_id = result.pop("session_id", "") or self.resume_id
            self.result = result
            self.status = "stopped" if self.stop.is_set() else ("failed" if "error" in result else "finished")

        self.thread = threading.Thread(target=work, daemon=True, name=f"agent-{self.id}")
        self.thread.start()

    def report(self) -> dict[str, Any]:
        out = {"job": self.id, "agent": self.label, "name": self.name, "status": self.status}
        if self.branch:
            out["branch"] = self.branch
        out["workdir"] = str(self.workdir)
        if self.status == "running":
            out["latest"] = self.last
        else:
            out.update({k: v for k, v in self.result.items() if k not in ("agent", "folder")})
        return out


# Finished jobs stay so a later follow-up can resume them. ponytail: never pruned — one small
# object per agent started, a human-scale count; prune per session if that ever changes.
_JOBS: dict[str, Job] = {}
# ponytail: a flat cap per conversation; make it a setting if people run bigger teams.
_MAX_RUNNING = 4


def _stop_all(jobs: Iterable[Job]) -> None:
    for job in jobs:
        job.stop.set()
    for job in jobs:
        if job.thread is not None:
            job.thread.join(timeout=15)


# Agents run in their own process groups and would outlive the app; quitting stops them.
atexit.register(lambda: _stop_all([j for j in _JOBS.values() if j.status == "running"]))


def agent_team_tools(*, workspace: str | Path, roots: Optional[list] = None, session_id: str = "") -> list:
    """start_agent / wait_for_agents / message_agent / stop_agent, or nothing when neither
    agent is installed (an unusable tool in the catalog misleads the model)."""
    installed = available_agents()
    if not installed:
        return []
    ws = Path(workspace).resolve()
    session = session_id or str(ws)
    choices = ", ".join(f"'{k}' ({AGENTS[k][0]})" for k in installed)

    def mine() -> list[Job]:
        return [j for j in _JOBS.values() if j.session == session]

    def find(job: str) -> Job | str:
        found = _JOBS.get(job.strip())
        if found is None or found.session != session:
            names = ", ".join(j.id for j in mine()) or "none"
            return f"No agent job '{job}' in this conversation. Jobs: {names}."
        return found

    def start_agent(agent: str, task: str, name: str = "", folder: str = "") -> dict:
        key = agent.strip().lower().replace(" ", "_")
        if key not in installed:
            return {"error": f"'{agent}' is not available here. Installed: {choices}."}
        if sum(j.status == "running" for j in mine()) >= _MAX_RUNNING:
            return {"error": f"{_MAX_RUNNING} agents are already working. Wait for one to finish first."}
        where = _resolve_folder(folder, roots or [], ws)
        if isinstance(where, str):
            return {"error": where}
        title = name.strip() or f"{AGENTS[key][0]} task"
        workdir, branch = isolate(where, _slug(f"{key.split('_')[0]}-{title}"))
        job = Job(session, key, installed[key], title, workdir, branch)
        _JOBS[job.id] = job
        job.launch(task)
        out = job.report()
        out["note"] = (
            f"Working on branch {branch}, started from the last commit: uncommitted changes in "
            "the main folder are not in its copy."
            if branch else "Not a git project, so it works directly in the folder; give parallel agents separate files."
        )
        return out

    def wait_for_agents(timeout_minutes: int = 30) -> dict:
        report = tool_progress.get() or (lambda _line: None)
        stop, yielded = tool_stop.get(), tool_yield.get()
        deadline = time.monotonic() + max(0, timeout_minutes) * 60
        shown = ""
        while True:
            jobs = mine()
            done = [j for j in jobs if j.status != "running" and not j.reported]
            running = [j for j in jobs if j.status == "running"]
            if done or not running or time.monotonic() >= deadline:
                for job in done:
                    job.reported = True
                return {"finished": [j.report() for j in done], "still_working": [j.report() for j in running]}
            if stop is not None and stop.is_set():
                _stop_all(running)  # the user pressed Stop: the agents stop with the turn
                return {"error": "Stopped. The agents were stopped too; their branches keep what they did."}
            if yielded is not None and yielded.is_set():
                return {
                    "note": "The user sent a message. Read it first; the agents keep working. Call wait_for_agents again after.",
                    "still_working": [j.report() for j in running],
                }
            board = "\n".join(f"{j.label} · {j.name}: {j.last}" for j in running)
            if board != shown:
                shown = board
                try:
                    report(board)
                except RuntimeError:
                    pass
            time.sleep(0.25)

    def message_agent(job: str, message: str) -> dict:
        found = find(job)
        if isinstance(found, str):
            return {"error": found}
        if found.status == "running":
            return {"error": f"{found.label} is still working on '{found.name}'. Wait for it to finish first."}
        if not found.resume_id:
            return {"error": f"{found.label} never started a session for '{found.name}', so there is nothing to continue. Start a new agent instead."}
        found.launch(message)
        return found.report()

    def stop_agent(job: str) -> dict:
        found = find(job)
        if isinstance(found, str):
            return {"error": found}
        _stop_all([found])
        found.reported = True
        return found.report()

    start_agent.__doc__ = f"""Start a coding agent installed on this computer on one task. It
        works on its own, in the background, while you start others and watch them with
        `wait_for_agents`. Use agents for substantial software work (building, fixing,
        refactoring, testing) or when the user asks for Claude Code or Codex. Do the writing,
        analysis and documents yourself.

        Running a project with several agents:
        1. Split it into tasks that touch different parts, and start one agent per task.
           Mix agents when it helps; you can also start one agent to review another's branch
           (`git diff main...mimi/<name>`) and report problems.
        2. Call `wait_for_agents`; it returns as each one finishes.
        3. Review every result yourself: read the diff on its branch and run the tests with
           the shell. If something is wrong or missing, say exactly what in `message_agent`
           (same agent, same branch, its memory intact) and wait again.
        4. When a branch is right, merge it with the shell (`git merge mimi/<name>`), which
           asks the user, then remove its worktree (`git worktree remove`).
        5. Never end your turn while an agent is still working.

        In a git project each agent gets its own branch `mimi/<name>` in its own copy of the
        project, starting from the last commit. Agents cannot see this conversation: put
        everything needed in `task` (goal, files, constraints, how to check the work).

        Args:
            agent (str): Which agent: {choices}.
            task (str): The complete, self-contained instructions.
            name (str): A short name for the task, like "csv export"; used for the branch.
            folder (str): Folder to work in, relative to the main folder or absolute. It
                must be a folder you may change. Empty means the main folder.
        """
    wait_for_agents.__doc__ = """Wait for the agents you started, showing their progress.
        Returns as soon as at least one finishes (with its summary, changed files and
        branch), when the time runs out, or when the user sends a message. Agents still
        working are listed under `still_working`. Use timeout_minutes=0 for a quick look.

        Args:
            timeout_minutes (int): Longest to wait before returning anyway. Default 30.
        """
    message_agent.__doc__ = """Send feedback or a next step to an agent that has finished, in
        the same session: it remembers everything it did and keeps working on the same
        branch. Then call `wait_for_agents` again.

        Args:
            job (str): The job id from `start_agent`.
            message (str): Exactly what to fix or do next, and how to check it.
        """
    stop_agent.__doc__ = """Stop an agent that is working. Its branch keeps what it did so far.

        Args:
            job (str): The job id from `start_agent`.
        """

    # Starting an agent is the consequential act — another program working on its own — so
    # it asks. Feedback stays inside a job the user already approved (owner's choice,
    # 2026-10-15); merging into the user's branch goes through the shell and asks there.
    gated = ai.ToolMetadata(category="agent", risk_level="high", capabilities=["execute", "write"], requires_approval=True)
    return [
        ai.tool(start_agent, metadata=gated),
        *(
            ai.tool(fn, metadata=ai.ToolMetadata(category="agent", risk_level="medium", requires_approval=False))
            for fn in (wait_for_agents, message_agent, stop_agent)
        ),
    ]
