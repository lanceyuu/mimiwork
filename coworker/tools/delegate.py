"""A small team of coding agents — Mimi hands work to Claude Code, Codex and opencode and reviews it.

Mimi splits a project into tasks, starts an agent on each (`start_agent`), watches them all
(`wait_for_agents`), reviews what comes back, and sends feedback into the same agent session
(`message_agent`) until the work is right. In a git project every agent gets its own worktree
and branch, so parallel agents never collide and nothing reaches the user's branch until a
merge — which goes through the shell and so asks the user. Each agent runs headless
(`claude -p` / `codex exec` / `opencode run`) under its own safety model — `roots.py` cannot
confine another program — so starting one is approval-gated and the card says so. It also
bills the user's own Claude, OpenAI or opencode provider account, not QualiTaTi credits.

All three CLIs stream JSON lines. Each line that means something to a person (a command, an edit,
a sentence of narration) becomes a progress line on the running step via `tool_progress`;
the rest is ignored, so a format change degrades to a quieter card, never a crash.
"""

from __future__ import annotations

import atexit
import json
import os
import queue
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
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
    "opencode": ("opencode", "opencode", "the model provider you set up in opencode"),
}

# An app opened from Finder inherits launchd's PATH (/usr/bin:/bin:…), which holds none of
# these CLIs — and Codex is a `#!/usr/bin/env node` script, so the child needs these dirs too.
_EXTRA_DIRS = [
    "~/.local/bin",
    "~/.claude/local",
    "~/.opencode/bin",  # opencode's own installer
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "~/.npm-global/bin",
    "~/.volta/bin",
    "~/.bun/bin",
    "~/AppData/Roaming/npm",
]

# A real coding task takes minutes; past this the run is stopped and reported as such.
_TIMEOUT = 30 * 60
# An agent whose own model call hangs prints nothing at all — a live Codex run sat silent
# for 27 minutes (2026-10-15). Silence this long means stuck, not thinking.
_SILENCE = 10 * 60
_SUMMARY_CHARS = 8000
_MAX_CHANGED = 200
# Snapshotting a huge folder to find changed files would cost more than the run; skip it.
_MAX_SNAPSHOT = 50_000
# Where the agents' own tools keep logs and settings — never the project's work.
_AGENT_DIRS = (".claude", ".codex", ".opencode")
_SKIP_DIRS = {".git", ".mimiwork", *_AGENT_DIRS, "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".pytest_cache"}


def _search_path() -> str:
    extra = [str(Path(d).expanduser()) for d in _EXTRA_DIRS]
    return os.pathsep.join([*extra, os.environ.get("PATH", "")])


def _env() -> dict[str, str]:
    return {**os.environ, "PATH": _search_path(), "NO_COLOR": "1"}


def find_agent(key: str) -> str:
    """The executable for `key`, or "" when it is not installed."""
    return shutil.which(AGENTS[key][1], path=_search_path()) or ""


def available_agents() -> dict[str, str]:
    return {key: path for key in AGENTS if (path := find_agent(key))}


def agent_command(
    key: str, executable: str, resume_id: str = "", model: str = "", effort: str = "", skip_hooks: bool = False,
) -> list[str]:
    """argv for a headless run; the task goes in on stdin (no length or leading-dash trouble).
    With `resume_id`, the message continues that agent session, its memory intact. An empty
    `model` or `effort` leaves the agent's own configured default in charge."""
    if key == "claude_code":
        # Auto mode (owner's choice, 2026-10-15): Claude Code's own classifier approves safe
        # edits and commands, so a headless run can test its work instead of having every
        # command denied for want of someone to ask.
        return [
            executable, "-p", "--output-format", "stream-json", "--verbose", "--permission-mode", "auto",
            *(["--model", model] if model else []),
            *(["--effort", effort] if effort else []),
            *(["--settings", _NO_HOOKS] if skip_hooks else []),
            *(["--resume", resume_id] if resume_id else []),
        ]
    if key == "opencode":
        # No --auto (opencode 1.19): its defaults already let a run edit files and run
        # commands in its folder, and whatever the user's own opencode settings mark "ask"
        # (reading outside the folder, by default) is refused instead of approved.
        return [
            executable, "run", "--format", "json",
            *(["-m", model] if model else []),
            *(["--variant", effort] if effort else []),
            *(["--session", resume_id] if resume_id else []),
        ]
    # `exec resume` takes no --sandbox flag; the config key sets the same policy for both.
    flags = ["-c", 'sandbox_mode="workspace-write"']
    if model:
        flags += ["-m", model]
    if effort:
        flags += ["-c", f'model_reasoning_effort="{effort}"']
    if resume_id:
        return [executable, "exec", "resume", "--json", "--skip-git-repo-check", *flags, resume_id, "-"]
    return [executable, "exec", "--json", "--skip-git-repo-check", *flags, "-"]


# ── Connecting: the Coding agents page (Connectors) reads and drives everything below. ──

# Codex's catalog lists the levels each model takes; these stand in when it cannot be read.
EFFORTS: dict[str, list[str]] = {
    "claude_code": ["low", "medium", "high", "xhigh", "max"],
    "codex": ["low", "medium", "high", "xhigh", "max"],
    "opencode": ["low", "medium", "high", "xhigh", "max"],
}
# An empty model means Latest. Claude Code cannot list models, but takes aliases that follow
# the newest model of each family as the installed CLI knows it (2.1.270 resolves `opus` to
# claude-opus-5 and `fable` to claude-fable-5-1); `default` is the one it recommends for the
# signed-in account. Updating Claude Code moves them, so nothing here goes stale.
_CLAUDE_LATEST = "default"
# The user's own Claude Code hooks are for their interactive sessions. In a hand-off they
# cost time and change the answer: on the owner's Mac a memory plugin's end-of-turn hook
# held every run for ~110 s after a 5 s answer, and a prompt hook wrote "No skills needed"
# into every reply (2026-10-17). Off by default; plugins, MCP servers, skills and
# permissions still load. The page can turn them back on for anyone whose hooks guard
# what an agent may do.
_NO_HOOKS = '{"disableAllHooks": true}'
_CLAUDE_ALIASES = [("fable", "Latest Fable"), ("opus", "Latest Opus"), ("sonnet", "Latest Sonnet"), ("haiku", "Latest Haiku")]
# opencode needs no sign-in: its own free models work as installed. Adding a provider is an
# interactive picker, so the page shows the command instead of driving it.
_SIGN_IN_ARGS = {"claude_code": ["auth", "login"], "codex": ["login"], "opencode": ["auth", "login"]}
_INSTALL = {
    "claude_code": "irm https://claude.ai/install.ps1 | iex" if _IS_WINDOWS else "curl -fsSL https://claude.ai/install.sh | bash",
    "codex": "npm install -g @openai/codex",
    "opencode": "npm install -g opencode-ai" if _IS_WINDOWS else "curl -fsSL https://opencode.ai/install | bash",
}
# A model name goes into argv and, for Codex, into a TOML value: names only, nothing that
# could close the quote or read as a flag.
_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/\[\]-]{0,99}$")
_PAGE = "Connectors > Coding agents"

_settings_path: Optional[Path] = None
# key → {"model", "effort", "resolved": {alias: the model id it last ran as}}
_settings: dict[str, dict[str, Any]] = {}


def load_settings(path: Path) -> None:
    """Where the chosen model and effort live (a small JSON file beside the app's prefs)."""
    global _settings_path, _settings
    _settings_path = path
    global _runs_path
    _runs_path = path.with_name("coding-agent-runs.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _settings = {k: dict(v) for k, v in data.items() if k in AGENTS and isinstance(v, dict)}
    except (OSError, ValueError, AttributeError):
        _settings = {}


def agent_settings(key: str) -> dict[str, str]:
    saved = _settings.get(key, {})
    return {"model": str(saved.get("model") or ""), "effort": str(saved.get("effort") or "")}


def _write_settings() -> str:
    if _settings_path is None:
        return ""
    try:
        _settings_path.write_text(json.dumps(_settings, indent=2), encoding="utf-8")
    except OSError as exc:
        return f"Could not save the setting: {exc}"
    return ""


def keeps_hooks(key: str) -> bool:
    return key == "claude_code" and bool(_settings.get(key, {}).get("keep_hooks"))


def save_settings(key: str, model: str = "", effort: str = "", keep_hooks: Optional[bool] = None) -> dict[str, Any]:
    model, effort = (model or "").strip(), (effort or "").strip()
    if model and not _MODEL_NAME.match(model):
        return {"ok": False, "error": "That model name has characters a model name never has."}
    allowed = _efforts(key)
    if effort and effort not in allowed:
        return {"ok": False, "error": f"Effort must be one of: {', '.join(allowed)}."}
    _settings[key] = {**_settings.get(key, {}), "model": model, "effort": effort}
    if keep_hooks is not None:
        _settings[key]["keep_hooks"] = bool(keep_hooks)
    problem = _write_settings()
    return {"ok": False, "error": problem} if problem else {"ok": True, **agent_settings(key), "keep_hooks": keeps_hooks(key)}


_CATALOG_TTL = 60 * 60
# ponytail: one cached catalog per agent per process; each CLI refreshes its own list.
_catalogs: dict[str, dict[str, Any]] = {k: {"at": 0.0, "models": []} for k in ("codex", "opencode")}


def _cached(key: str, read: Callable[[], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    cache = _catalogs[key]
    if cache["models"] and time.monotonic() - cache["at"] < _CATALOG_TTL:
        return cache["models"]
    models = read()
    if models:
        cache.update(at=time.monotonic(), models=models)
    return models


def codex_models(executable: str) -> list[dict[str, Any]]:
    """The models Codex offers in its own picker, newest first; [] when it cannot say.

    `codex debug models` (0.162) prints the catalog Codex refreshes from OpenAI, with the
    effort levels each model takes. It sits under `debug`, so a failure is expected someday
    and only costs the dropdown: the page falls back to typing a model name."""
    if not executable:
        return []

    def read() -> list[dict[str, Any]]:
        code, out = _probe([executable, "debug", "models"], timeout=30)
        try:
            raw = json.loads(out)["models"] if code == 0 else []
            return [
                {
                    "id": str(m["slug"]),
                    "label": str(m.get("display_name") or m["slug"]),
                    "description": str(m.get("description") or ""),
                    "efforts": [str(e["effort"]) for e in m.get("supported_reasoning_levels") or [] if e.get("effort")],
                }
                for m in sorted(raw, key=lambda m: m.get("priority", 999))
                if m.get("visibility") == "list" and _MODEL_NAME.match(str(m.get("slug") or ""))
            ]
        except (ValueError, KeyError, TypeError, AttributeError):
            return []

    return _cached("codex", read)


_MODEL_HEADER = re.compile(r"(?m)^([A-Za-z0-9][^\s{}]*/[^\s{}]+)[ \t]*$")


def opencode_models(executable: str) -> list[dict[str, Any]]:
    """Every model opencode can use with the providers set up on this computer (its free
    ones included), newest release first; [] when it cannot say.

    `opencode models --verbose` (1.19) prints each `provider/model` line followed by that
    model's JSON, whose `variants` are the effort levels it takes (`--variant`)."""
    if not executable:
        return []

    def read() -> list[dict[str, Any]]:
        code, out = _probe([executable, "models", "--verbose"], timeout=60)
        if code != 0:
            return []
        decoder, found = json.JSONDecoder(), []
        for head in _MODEL_HEADER.finditer(out):
            start = out.find("{", head.end())
            try:
                data, _ = decoder.raw_decode(out, start) if start >= 0 else ({}, 0)
            except ValueError:
                continue
            model_id = head.group(1)
            if not isinstance(data, dict) or data.get("status", "active") != "active" or not _MODEL_NAME.match(model_id):
                continue
            provider = str(data.get("providerID") or model_id.split("/")[0])
            found.append({
                "id": model_id,
                "label": f"{data.get('name') or model_id} · {provider}",
                "description": model_id,
                "efforts": [str(v) for v in data.get("variants") or {}],
                "released": str(data.get("release_date") or ""),
            })
        return sorted(found, key=lambda m: m["released"], reverse=True)

    return _cached("opencode", read)


def _catalog_for(key: str) -> list[dict[str, Any]]:
    if key == "codex":
        return codex_models(find_agent(key))
    if key == "opencode":
        return opencode_models(find_agent(key))
    return []


def _efforts(key: str) -> list[str]:
    seen = [e for m in _catalog_for(key) for e in m["efforts"]]
    return list(dict.fromkeys(seen)) if seen else EFFORTS[key]


def run_settings(key: str) -> dict[str, Any]:
    """What a run actually passes: the chosen model, or Latest made concrete, and whether
    the user's own hooks stay out of it."""
    chosen: dict[str, Any] = {**agent_settings(key), "skip_hooks": key == "claude_code" and not keeps_hooks(key)}
    if not chosen["model"]:
        if key == "claude_code":
            chosen["model"] = _CLAUDE_LATEST
        elif key == "codex":
            models = codex_models(find_agent(key))
            chosen["model"] = models[0]["id"] if models else ""  # "" → Codex's own default
        # opencode stays "": its list mixes every provider's newest previews, so the newest
        # entry is no sensible default. Its own pick (the user's opencode settings, or the
        # best model of the providers they set up) is.
    return chosen


def note_resolved(key: str, requested: str, resolved: str) -> None:
    """Remember which model an alias ran as, so the page can say "currently …". An empty
    `requested` is the agent's own choice (opencode's Latest)."""
    if not resolved or requested == resolved:
        return
    entry = _settings.setdefault(key, {})
    if entry.get("resolved", {}).get(requested) != resolved:
        entry["resolved"] = {**entry.get("resolved", {}), requested: resolved}
        _write_settings()


def _probe(argv: list[str], timeout: float = 20) -> tuple[Optional[int], str]:
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, env=_env(), stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return None, "it did not answer in time"
    except OSError as exc:
        return None, str(exc)
    return done.returncode, (done.stdout or done.stderr or "").strip()


def _own_defaults(key: str) -> dict[str, str]:
    """The model and effort the agent uses when MimiWork sets none: its own config file."""
    try:
        if key == "claude_code":
            data = json.loads((Path.home() / ".claude" / "settings.json").read_text(encoding="utf-8"))
            return {"model": str(data.get("model") or ""), "effort": str(data.get("effortLevel") or "")}
        if key == "opencode":
            # JSON with comments allowed, so no json.loads. ponytail: the first "model" key
            # wins, which may be an agent's own model in an unusual config; display only.
            folder = Path.home() / ".config" / "opencode"
            for name in ("opencode.json", "opencode.jsonc", "config.json"):
                if (folder / name).is_file():
                    m = re.search(r'"model"\s*:\s*"([^"]+)"', (folder / name).read_text(encoding="utf-8"))
                    return {"model": m.group(1) if m else "", "effort": ""}
            return {"model": "", "effort": ""}
        text = (Path.home() / ".codex" / "config.toml").read_text(encoding="utf-8")
    except (OSError, ValueError, AttributeError):
        return {"model": "", "effort": ""}
    top = re.split(r"(?m)^\s*\[", text, maxsplit=1)[0]  # top-level keys only, before any [table]

    def value(name: str) -> str:
        m = re.search(rf'(?m)^\s*{name}\s*=\s*"([^"]*)"', top)
        return m.group(1) if m else ""

    return {"model": value("model"), "effort": value("model_reasoning_effort")}


def _sign_in_state(key: str, executable: str) -> tuple[Optional[bool], str]:
    """(signed in?, account or reason). None means the check itself failed."""
    if key == "claude_code":
        code, out = _probe([executable, "auth", "status", "--json"])
        try:
            data = json.loads(out)
        except ValueError:
            return None, out or "its sign-in check gave no answer"
        if not data.get("loggedIn"):
            return False, ""
        return True, str(data.get("email") or data.get("authMethod") or "")
    if key == "opencode":
        # Always ready: its free models need no account. The account line names the
        # providers the user added ("●  GitHub Copilot \x1b[90moauth" in opencode 1.19).
        code, out = _probe([executable, "providers", "list"])
        if code is None:
            return None, out
        return True, ", ".join(m.group(1) for m in re.finditer(r"●\s+(.+?)\s*(?:\x1b|$)", out, re.M))
    code, out = _probe([executable, "login", "status"])
    if code is None:
        return None, out
    # "Logged in using ChatGPT" / "Not logged in" (Codex CLI 0.162)
    return (True, out.splitlines()[0].removeprefix("Logged in using ") if out else "") if code == 0 else (False, "")


def agent_status(key: str) -> dict[str, Any]:
    """Everything the Coding agents page shows for one agent. Never raises."""
    label, exe_name, billing = AGENTS[key]
    path = find_agent(key)
    out: dict[str, Any] = {
        "key": key, "label": label, "billing": billing,
        "installed": bool(path), "path": path, "version": "",
        "signed_in": False, "account": "", "error": "",
        "install_command": _INSTALL[key],
        "sign_in_command": " ".join([exe_name, *_SIGN_IN_ARGS[key]]),
        "efforts": EFFORTS[key], "defaults": _own_defaults(key),
        "models": [], "models_listed": False, "latest": "",
        **agent_settings(key), "keep_hooks": keeps_hooks(key),
    }
    resolved = _settings.get(key, {}).get("resolved", {})
    if key == "claude_code":
        out["models"] = [{"id": a, "label": lbl, "resolved": resolved.get(a, "")} for a, lbl in _CLAUDE_ALIASES]
        out["latest"] = resolved.get(_CLAUDE_LATEST, "")
    if not path:
        return out
    code, version = _probe([path, "--version"])
    if code != 0:
        out["error"] = f"{label} is installed at {path} but does not start: {_short(version, 300)}"
        return out
    out["version"] = _short(version, 80)
    signed_in, detail = _sign_in_state(key, path)
    if signed_in is None:
        out["error"] = f"Could not check whether {label} is signed in: {_short(detail, 300)}"
    out["signed_in"], out["account"] = bool(signed_in), detail if signed_in else ""
    if key == "codex":
        models = codex_models(path)
        out["models"], out["models_listed"] = models, bool(models)
        out["latest"] = models[0]["id"] if models else ""
        out["efforts"] = _efforts(key)
    if key == "opencode":
        models = opencode_models(path)
        out["models"], out["models_listed"] = models, bool(models)
        out["latest"] = resolved.get("", "")  # what opencode's own choice last ran as
        out["efforts"] = _efforts(key)
    return out


def connection_problem(key: str) -> str:
    """Why `key` cannot take work right now, in words for the user; "" when it can."""
    status = agent_status(key)
    label = status["label"]
    if not status["installed"]:
        return f"{label} is not installed on this computer. The user can set it up in {_PAGE}."
    if status["error"]:
        return f"{status['error']}. The user can check it in {_PAGE}."
    if not status["signed_in"]:
        return f"{label} is installed but not signed in. The user can sign in from {_PAGE}."
    return ""


def try_agent(key: str) -> dict[str, Any]:
    """The page's Test button: one tiny real call with the chosen model and effort."""
    problem = connection_problem(key)
    if problem:
        return {"ok": False, "error": problem}
    started = time.monotonic()
    chosen = run_settings(key)
    with tempfile.TemporaryDirectory(prefix="mimiwork-agent-test-") as tmp:
        result = run_agent(
            key, find_agent(key), "Reply with just the word OK. Do not run any commands or change any files.",
            Path(tmp), timeout=300, silence=240, **chosen,
        )
    seconds = round(time.monotonic() - started, 1)
    model = result.get("model") or chosen["model"]
    note_resolved(key, chosen["model"], model)
    if "error" in result:
        return {"ok": False, "error": result["error"], "seconds": seconds}
    return {"ok": True, "reply": _short(result.get("summary") or "", 200), "seconds": seconds, "model": model}


_LOGINS: dict[str, subprocess.Popen] = {}
_LOGIN_LIMIT = 10 * 60  # a sign-in nobody finishes stops holding its local callback port
_URL = re.compile(r"https://\S+")


def sign_in(key: str) -> dict[str, Any]:
    """Start the agent's own browser sign-in in the background. The CLI opens the browser;
    its link comes back too, for when no browser window appears."""
    label = AGENTS[key][0]
    path = find_agent(key)
    if not path:
        return {"started": False, "error": f"{label} is not installed on this computer."}
    old = _LOGINS.pop(key, None)
    if old is not None:
        _kill(old)
    spawn: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if _IS_WINDOWS else {"start_new_session": True}
    )
    try:
        proc = subprocess.Popen(
            [path, *_SIGN_IN_ARGS[key]], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=_env(), text=True, encoding="utf-8", errors="replace", **spawn,
        )
    except OSError as exc:
        return {"started": False, "error": f"Could not start {label}'s sign-in: {exc}"}
    _LOGINS[key] = proc
    seen: list[str] = []

    def _drain() -> None:  # keeps reading so a chatty CLI never blocks on a full pipe
        assert proc.stdout is not None
        for line in proc.stdout:
            seen.append(line.strip())

    threading.Thread(target=_drain, daemon=True).start()
    timer = threading.Timer(_LOGIN_LIMIT, _kill, args=(proc,))
    timer.daemon = True  # never what keeps the app from quitting
    timer.start()
    deadline = time.monotonic() + 5
    url = ""
    while time.monotonic() < deadline and proc.poll() is None and not url:
        url = next((m.group(0) for line in seen if (m := _URL.search(line))), "")
        time.sleep(0.1)
    if proc.poll() not in (None, 0):
        why = _short(" ".join(seen[-5:]), 400) or f"exited with code {proc.returncode}"
        return {"started": False, "error": f"{label}'s sign-in did not start: {why}"}
    return {"started": True, "url": url}


def _short(text: str, n: int = 140) -> str:
    line = " ".join(str(text).split())
    return line if len(line) <= n else line[: n - 1] + "…"


def _unwrap(command: str) -> str:
    """`/bin/bash -lc "pytest -q"` → `pytest -q`: Codex wraps every command in a login shell."""
    for prefix in ("/bin/bash -lc ", "/bin/zsh -lc ", "bash -lc ", "zsh -lc "):
        if command.startswith(prefix):
            inner = command[len(prefix):].strip()
            if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in "'\"":
                inner = inner[1:-1]
            return inner
    return command


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
        self.model = ""  # the model an alias resolved to, when the CLI says

    def claude(self, event: dict) -> list[str]:
        kind = event.get("type")
        self.session_id = str(event.get("session_id") or self.session_id)
        if kind == "system" and event.get("subtype") == "init":
            self.model = str(event.get("model") or "")
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
            return [_short(f"Running: {_unwrap(str(item.get('command', '')))}")]
        if kind == "item.completed":
            if itype == "agent_message":
                self.summary = str(item.get("text") or "")
                return [_short(self.summary)]
            if itype == "file_change":
                paths = [c.get("path", "") for c in item.get("changes") or []]
                return [_short("Changed " + ", ".join(Path(p).name for p in paths if p))] if paths else []
            # itype "error" is a warning about the user's own Codex setup (hook timeouts, skill
            # budgets); the run carries on and it says nothing about progress, so it stays off.
        if kind == "turn.completed":
            # A top-level "error" can be a reconnect notice that the turn survived.
            self.finished, self.error = True, ""
        if kind in ("turn.failed", "error"):
            self.finished = self.finished or kind == "turn.failed"
            self.error = _error_text((event.get("error") or {}).get("message") or event.get("message"))
        return []

    def opencode(self, event: dict) -> list[str]:
        # opencode 1.19 `run --format json`: step_start / text / tool_use / step_finish, and
        # an "error" event on failure — with exit code 0, so the event is the only signal.
        kind = event.get("type")
        self.session_id = str(event.get("sessionID") or self.session_id)
        part = event.get("part") or {}
        if kind == "step_start":
            self._step_text: list[str] = []
        if kind == "text" and str(part.get("text") or "").strip():
            # One answer can arrive as several text parts in a step (a live run split it
            # mid-sentence); the summary is the whole of the latest step's text.
            self._step_text = [*getattr(self, "_step_text", []), str(part["text"])]
            self.summary = "".join(self._step_text)
            return [_short(part["text"])]
        if kind == "tool_use":
            state = part.get("state") or {}
            args = state.get("input") or {}
            target = args.get("command") or args.get("filePath") or args.get("pattern") or state.get("title") or ""
            tool = str(part.get("tool") or "tool")
            return [_short(f"{tool}: {target}" if target else tool)]
        if kind == "step_finish":
            # "tool-calls" means another step follows; anything else ends the turn.
            self.finished = part.get("reason") != "tool-calls"
        if kind == "error":
            err = event.get("error") or {}
            self.error = str((err.get("data") or {}).get("message") or err.get("name") or "opencode stopped with an error")
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
    silence: float = _SILENCE,
    model: str = "",
    effort: str = "",
    skip_hooks: bool = False,
) -> dict[str, Any]:
    """Run one headless hand-off to completion, streaming progress through `report`."""
    label = AGENTS[key][0]
    # opencode (1.19) works in the folder $PWD names, not its real working directory, and
    # a child inherits MimiWork's own $PWD: the first live hand-off edited the app's folder
    # instead of the agent's branch (2026-10-18). The folder goes in both places.
    env = {**_env(), "PWD": str(folder)}
    spawn: dict[str, Any] = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if _IS_WINDOWS else {"start_new_session": True}
    )
    before = _snapshot(folder)
    try:
        proc = subprocess.Popen(
            argv or agent_command(key, executable, resume_id, model=model, effort=effort, skip_hooks=skip_hooks),
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
    parse = {"claude_code": run.claude, "codex": run.codex, "opencode": run.opencode}[key]
    plain: list[str] = []  # non-JSON output (startup errors, stack traces)
    deadline = time.monotonic() + timeout
    heard = time.monotonic()
    outcome = ""
    while True:
        if stop is not None and stop.is_set():
            outcome = "stopped"
            break
        if time.monotonic() > deadline:
            outcome = "timed out"
            break
        if time.monotonic() - heard > silence:
            outcome = "silent"
            break
        try:
            line = lines.get(timeout=0.25)
        except queue.Empty:
            continue
        heard = time.monotonic()
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

    if key == "opencode" and run.session_id and not model:
        run.model = _opencode_model(executable, run.session_id)
    changed = changed_files(before, _snapshot(folder))
    result: dict[str, Any] = {"agent": label, "folder": str(folder), "session_id": run.session_id or resume_id}
    if changed is not None:
        result["changed_files"] = changed[:_MAX_CHANGED]
        if len(changed) > _MAX_CHANGED:
            result["changed_files_note"] = f"{len(changed) - _MAX_CHANGED} more not listed"
    if run.summary:
        result["summary"] = run.summary[:_SUMMARY_CHARS]
    if run.model:
        result["model"] = run.model
    if outcome == "stopped":
        return {**result, "error": f"Stopped. {label} may have changed some files before it stopped."}
    if outcome == "silent":
        return {**result, "error": (
            f"{label} showed no activity for {max(1, round(silence / 60))} minutes and was stopped; its model service "
            "may be down. Its branch keeps what it did; try it again or give the task to another agent."
        )}
    if outcome == "timed out":
        return {**result, "error": f"{label} was still working at its {_minutes(timeout)} limit and was stopped."}
    if run.error or (code not in (0, None) and not run.summary) or not run.finished:
        why = run.error or _short(" ".join(plain[-5:]), 600) or f"exited with code {code}"
        return {**result, "error": f"{label} did not finish: {why}"}
    return {**result, "status": "completed"}


def _opencode_model(executable: str, session_id: str) -> str:
    """The `provider/model` opencode chose for a session; its events never say. ""
    when unknown — the page then just cannot say what Latest ran as."""
    code, out = _probe([executable, "export", session_id], timeout=30)
    # Into a pipe, opencode 1.19 cuts the export off at 64 KB, so a real session never parses
    # whole. The session's `info` comes first, and its "model" object is the first one.
    start = out.find("{", out.find('"model"')) if code == 0 and '"model"' in out else -1
    try:
        model, _ = json.JSONDecoder().raw_decode(out, start) if start >= 0 else ({}, 0)
        return f"{model['providerID']}/{model['id']}"
    except (ValueError, KeyError, TypeError):
        return ""


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


def commit_round(workdir: Path, title: str, result: dict[str, Any]) -> str:
    """Commit whatever an agent changed onto its own branch; the short hash, or "" if nothing.

    Agents rarely commit on their own, and an uncommitted worktree leaves the branch at its
    starting point — a merge would then bring in nothing (seen in the first live run,
    2026-10-15). Committing here is safe: the branch is the agent's alone, and the user's
    branch only changes through a merge the user approves."""
    if not _git(workdir, "status", "--porcelain")[1]:
        return ""
    # Agents' own tooling drops session logs into the folder it runs in (`.claude/logs/…`
    # from a user's hook plugin, second live run); committed on two branches they collide
    # at merge. New files there never belong to the project; tracked ones still commit.
    _git(workdir, "add", "-u")
    # Same for caches and installs a test run leaves behind in a project with no .gitignore
    # (__pycache__ landed on a branch in the third live run; node_modules would be worse).
    junk = [*_AGENT_DIRS, *(f"**/{d}" for d in _SKIP_DIRS - {".git", ".mimiwork", *_AGENT_DIRS})]
    _git(workdir, "add", "-A", "--", ".", *(f":(exclude,glob){d}/**" for d in junk))
    if _git(workdir, "diff", "--cached", "--quiet")[0]:
        return ""  # only agent logs changed
    outcome = "" if "error" not in result else " (did not finish)"
    body = _short(result.get("summary") or result.get("error") or "", 600)
    message = [f"{title}{outcome}", "", body] if body else [f"{title}{outcome}"]
    args = ["commit", "-q", "--no-verify", "-m", "\n".join(message)]
    ok, _ = _git(workdir, *args)
    if not ok:  # no git identity on this machine: commit as MimiWork rather than lose the work
        ok, _ = _git(workdir, "-c", "user.name=MimiWork", "-c", "user.email=mimiwork@localhost", *args)
    return _git(workdir, "rev-parse", "--short", "HEAD")[1] if ok else ""


# A worktree keeps its git data in the main repo's .git, outside Codex's writable sandbox, so
# an agent's own `git commit` fails and it reports a "blocked commit" that sends the
# coordinator chasing a non-problem (live run, 2026-10-15). MimiWork commits for it instead.
_COMMIT_NOTE = "\n\n(MimiWork commits your changes to your branch when you finish. Do not run git commit.)"


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
            # Read at every round, so a model changed on the Coding agents page applies to
            # the next round without restarting anything.
            chosen = run_settings(self.key)
            result = run_agent(
                self.key, self.executable, message, self.workdir,
                report=note, stop=self.stop, resume_id=self.resume_id, **chosen,
            )
            note_resolved(self.key, chosen["model"], result.get("model", ""))
            self.resume_id = result.pop("session_id", "") or self.resume_id
            if self.branch:
                commit = commit_round(self.workdir, f"{self.label}: {self.name}", result)
                if commit:
                    result["commit"] = commit
            self.result = result
            self.status = "stopped" if self.stop.is_set() else ("failed" if "error" in result else "finished")
            record_run(self)

        self.thread = threading.Thread(target=work, daemon=True, name=f"agent-{self.id}")
        self.thread.start()

    def report(self) -> dict[str, Any]:
        out = {"job": self.id, "agent": self.label, "name": self.name, "status": self.status}
        if self.branch:
            out["branch"] = self.branch
        out["workdir"] = str(self.workdir)
        if self.resume_id:
            # So Mimi can tell the user how to open the agent's own conversation themselves.
            out["session_id"] = self.resume_id
            out["resume_command"] = resume_command(self.key, self.workdir, self.resume_id)
        if self.status == "running":
            out["latest"] = self.last
        else:
            out.update({k: v for k, v in self.result.items() if k not in ("agent", "folder")})
        return out


def resume_command(key: str, workdir: str | Path, session_id: str) -> str:
    """The command that opens an agent's own conversation in its CLI, in the agent's copy of
    the project. Claude Code and Codex find a session by id from any folder (checked with
    Claude Code 2.1.270 and Codex 0.162); opencode files sessions by project, so the folder
    matters there too, and it always decides which files a resumed agent works on. A
    hand-off's history otherwise hides: Claude Code files it under the agent's worktree,
    and Codex's resume list leaves out non-interactive runs."""
    exe = AGENTS[key][1]
    run = {
        "claude_code": f"{exe} --resume {session_id}",
        "codex": f"{exe} resume {session_id}",
        "opencode": f"{exe} --session {session_id}",
    }[key]
    if not workdir or not Path(workdir).is_dir():
        return run  # the worktree is gone (usually removed after a merge); the history is still there
    folder = f'"{workdir}"' if _IS_WINDOWS else shlex.quote(str(workdir))
    return f"cd {folder}; {run}" if _IS_WINDOWS else f"cd {folder} && {run}"


_runs_path: Optional[Path] = None
_runs_lock = threading.Lock()
_MAX_RUNS = 50


def record_run(job: "Job") -> None:
    """Keep the latest round of each hand-off (newest first) for the Coding agents page.
    Jobs live in memory; this list outlives a restart so their history stays findable."""
    if not job.resume_id:
        return
    entry = {
        "job": job.id, "key": job.key, "agent": job.label, "name": job.name, "status": job.status,
        "branch": job.branch, "workdir": str(job.workdir), "session_id": job.resume_id, "at": time.time(),
    }
    with _runs_lock:
        runs = [r for r in _read_runs() if r.get("job") != job.id]
        runs = [entry, *runs][:_MAX_RUNS]
        if _runs_path is not None:
            try:
                _runs_path.write_text(json.dumps(runs, indent=2), encoding="utf-8")
            except OSError:
                pass  # the page loses a row; the agent's own history is unaffected


def _read_runs() -> list[dict[str, Any]]:
    if _runs_path is None:
        return []
    try:
        data = json.loads(_runs_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in data if isinstance(r, dict) and r.get("key") in AGENTS and r.get("session_id")]


def recent_runs() -> list[dict[str, Any]]:
    """Recent hand-offs with the command that reopens each in its own CLI."""
    return [
        {**r, "resume_command": resume_command(r["key"], r.get("workdir") or "", r["session_id"]),
         "folder_exists": bool(r.get("workdir")) and Path(r["workdir"]).is_dir()}
        for r in _read_runs()
    ]


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
atexit.register(lambda: [_kill(p) for p in list(_LOGINS.values())])


def agent_team_tools(*, workspace: str | Path, roots: Optional[list] = None, session_id: str = "") -> list:
    """start_agent / wait_for_agents / message_agent / stop_agent. With no agent
    installed, only start_agent, ungated, whose one job is to say where to connect one — so
    "ask Codex to…" gets a plain answer instead of a model that has never heard of agents."""
    installed = available_agents()
    ws = Path(workspace).resolve()
    session = session_id or str(ws)
    choices = ", ".join(f"'{k}' ({AGENTS[k][0]})" for k in AGENTS)

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
        if key not in AGENTS:
            return {"error": f"'{agent}' is not a coding agent MimiWork can use. Choose {choices}."}
        # Checked at the call, not when the tools were built: the user may have signed in
        # (or out) on the Coding agents page since this conversation started.
        problem = connection_problem(key)
        if problem or not installed:
            # Built without agents, this tool skips approval, so it must never start one —
            # even if the user installed one meanwhile.
            return {"error": problem or f"{AGENTS[key][0]} was connected after this conversation started. Start a new conversation to use it."}
        if sum(j.status == "running" for j in mine()) >= _MAX_RUNNING:
            return {"error": f"{_MAX_RUNNING} agents are already working. Wait for one to finish first."}
        where = _resolve_folder(folder, roots or [], ws)
        if isinstance(where, str):
            return {"error": where}
        title = name.strip() or f"{AGENTS[key][0]} task"
        workdir, branch = isolate(where, _slug(f"{key.split('_')[0]}-{title}"))
        job = Job(session, key, find_agent(key), title, workdir, branch)
        _JOBS[job.id] = job
        job.launch(task + (_COMMIT_NOTE if branch else ""))
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
        problem = connection_problem(found.key)
        if problem:
            return {"error": problem}
        found.launch(message + (_COMMIT_NOTE if found.branch else ""))
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
        refactoring, testing) or when the user asks for Claude Code, Codex or opencode. Do the
        writing, analysis and documents yourself.

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
        project, starting from the last commit, and MimiWork commits its work there after
        every round (`commit` in the result); never ask an agent to commit. Agents cannot see this conversation: put
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
    if not installed:
        start_agent.__doc__ = """Hand software work to Claude Code, Codex or opencode. None is
        installed on this computer yet, so this only returns how the user can connect one.
        Call it when the user asks for Claude Code, Codex, opencode or a team of coding
        agents, and pass the answer on.

        Args:
            agent (str): 'claude_code', 'codex' or 'opencode'.
            task (str): What the user wanted done.
            name (str): Unused.
            folder (str): Unused.
        """
        # Nothing can run, so there is nothing to approve.
        return [ai.tool(start_agent, metadata=ai.ToolMetadata(category="agent", risk_level="low", requires_approval=False))]
    gated = ai.ToolMetadata(category="agent", risk_level="high", capabilities=["execute", "write"], requires_approval=True)
    return [
        ai.tool(start_agent, metadata=gated),
        *(
            ai.tool(fn, metadata=ai.ToolMetadata(category="agent", risk_level="medium", requires_approval=False))
            for fn in (wait_for_agents, message_agent, stop_agent)
        ),
    ]
