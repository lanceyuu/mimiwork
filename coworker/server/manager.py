"""Session manager — owns engines (one per session), stores, and the provider.

Each session is bound to a workspace folder (Code requires one). Storage is a single DB
under a data dir (global for the real server, per-workspace for tests), so recents and
sessions span folders.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # annotation only — the runtime import stays local, as before.
    from ..timesaved import TimeSaved

from ..agent import build_engine
from ..agents import get_agent
from ..agents import list_agents as _list_agents
from ..audit import AuditStore
from ..automation import Schedule, ScheduledTask, Scheduler, TaskRun, TaskStore
from ..config import load_config, workspace_allowed_commands
from ..connections import (
    PersonaConnectionStore,
    SessionConnectionStore,
)
from ..connections import (
    effective as effective_connections,
)
from ..connectors import (
    Gateway,
    MessageSource,
    connect_connector,
    connector_list,
    disconnect_connector,
    experimental_enabled,
    load_settings,
    make_adapter,
    set_experimental_enabled,
    slack_split,
    update_connector_tools,
)
from ..connectors.browser_automation import (
    browser_close_session,
    browser_state,
    browser_take_screenshot,
)
from ..connectors.parked import ParkedStore
from ..conversations import ConversationStore, title_from
from ..engine import Approver, TurnEngine
from ..inbox import InboxStore, args_preview
from ..inbox_routing import InboxRouting
from ..mcp import (
    MCPManager,
    build_callables,
    delete_global_server,
    load_mcp_servers,
    patch_global_server,
    put_global_server,
    read_global,
)
from ..memory import MemorySettingsStore, MemoryStore, Scope, SQLiteMemoryStore
from ..mentions import MentionSessionStore
from ..permissions import Mode
from ..personas import PersonaRegistry
from ..personas.registry import set_registry as set_persona_registry
from ..providers import (
    ProviderClient,
    ProviderRouter,
    descriptor_configured,
    get_descriptor,
    provider_descriptors,
    verify_provider_key,
)
from ..recovery import RecoverySession
from ..roots import RootDir
from ..secrets import SecretStore, state_dir
from ..selfwake import WakeStore
from ..sessions import SessionRecord
from ..skills import (
    SessionSkillStore,
    SkillLoader,
    SkillStore,
    effective_skills,
)
from ..subscriptions import ChannelBuffer, SubscriptionStore
from ..unattended import UnattendedRegistry
from ..unrouted import UnroutedStore
from ..workspace_trust import WorkspaceTrustStore

_SCOPES = {s.value for s in Scope}

logger = logging.getLogger("coworker.manager")


def _grants_of(engine) -> dict[str, Any]:
    """The engine's session-scoped "Always allow" approvals, in persistable shape."""
    tools = sorted(getattr(engine.permissions, "session_allow_tools", None) or ())
    commands = sorted(getattr(engine.permissions, "session_allow_commands", None) or ())
    return {"tools": tools, "commands": commands} if (tools or commands) else {}


def _approval_body(request) -> str:
    """Approval card body: the tool's reason (if any) plus a compact preview of its args, so a
    mirrored 'Run `write_file`?' shows the path/content rather than just the tool name.
    """
    reason = (getattr(request, "reason", "") or "").strip()
    preview = args_preview(getattr(request, "arguments", None))
    return "\n".join(p for p in (reason, preview) if p)


def _os_reveal(target: Path, mode: str = "reveal") -> dict[str, Any]:
    """Show a path in the OS file manager (`reveal`) or open it with its default app
    (`open`). The server runs on the user's own machine in both desktop and browser
    builds, so this is always local. A folder "opens" as itself either way."""
    import os
    import subprocess
    import sys

    is_dir = target.is_dir()
    try:
        if sys.platform == "darwin":
            args = (
                ["open", "-R", str(target)]
                if mode == "reveal" and not is_dir
                else ["open", str(target)]
            )
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "win32":
            if mode == "reveal" and not is_dir:
                # Explorer wants the path glued to the switch: /select,<path>
                subprocess.Popen(["explorer", f"/select,{target}"])
            else:
                os.startfile(str(target))  # type: ignore[attr-defined]  # default app
        else:  # Linux/BSD
            tgt = str(target.parent) if mode == "reveal" and not is_dir else str(target)
            subprocess.Popen(
                ["xdg-open", tgt], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def _same_dir(a: str, b: str) -> bool:
    """Two paths naming one directory (after ~ and symlinks) — or both empty."""
    try:
        return Path(a).expanduser().resolve() == Path(b).expanduser().resolve()
    except OSError:
        return a == b


class SessionManager:
    def __init__(
        self,
        *,
        workspace: Optional[str | Path] = None,  # default/seed workspace (e.g. --cwd)
        data_dir: Optional[str | Path] = None,
        model: str = "gpt-5.6-sol",
        mode: Mode = Mode.INTERACTIVE,
        provider: Optional[ProviderClient] = None,
    ) -> None:
        self.default_workspace = (
            str(Path(workspace).expanduser().resolve()) if workspace else None
        )
        self.model = model
        self.mode = mode
        self.provider = provider

        if data_dir is not None:
            base = Path(data_dir).expanduser()
        elif self.default_workspace is not None:
            base = Path(self.default_workspace) / ".coworker"
        else:
            base = state_dir()
        base.mkdir(parents=True, exist_ok=True)

        self.memory_store: MemoryStore = SQLiteMemoryStore(base / "coworker.db")
        # MEMORY-SPEC §4.3/§6: the on/off switch + the user's standing rules. Settings-
        # level, outside the memory table; read at engine build time.
        self.memory_settings = MemorySettingsStore(base / "memory-settings.json")
        self.audit_store = AuditStore(base / "coworker.db")
        self.session_store = ConversationStore(base)
        self._rescope_folder_memory_to_groups()
        self.session_store.canonicalize_workspaces()  # collapse /tmp vs /private/tmp etc.
        if self.default_workspace:
            self.session_store.touch_workspace(self.default_workspace)
        self._engines: dict[str, TurnEngine] = {}
        # Per-session time-saved totals, so the all-time counter banks deltas
        # rather than re-adding a session's cumulative figure every turn.
        self._session_time_saved: dict[str, dict] = {}
        # Sessions with an in-flight turn (busy): id → epoch the turn started
        # (the start time feeds mission control's elapsed display; membership is
        # all the busy logic ever tests).
        self._running_sessions: dict[str, float] = {}
        # Sessions with an auto-title LLM call in flight (FB-010) — one call at a time.
        self._autotitle_inflight: set[str] = set()
        self._autotitle_tasks: set[asyncio.Task] = set()
        self._autotitle_attempts: dict[str, int] = {}
        # Sessions whose title has already been redone from what they produced. Once
        # each: a title the user has grown used to should not keep moving.
        self._autotitle_retitled: set[str] = set()
        self.workspace_trust = WorkspaceTrustStore()
        self.secrets = SecretStore()
        # No explicit provider injected → route by the model's `provider:` prefix (OpenAI default,
        # Ollama, …). Tests inject a provider directly and bypass the router. The same router is
        # shared by every engine and the `/v1/chat/completions` proxy.
        if self.provider is None:
            self.provider = ProviderRouter(
                self.secrets, default_provider="openai", on_use=self._note_provider_use
            )
        self.mcp = MCPManager(secrets=self.secrets)
        # OAuth MCP servers with a sign-in in flight / their last connect error —
        # feeds list_mcp's status so the GUI can show "authorizing…" and failures.
        self._mcp_authorizing: set[str] = set()
        self._mcp_errors: dict[str, str] = {}
        self.gateway: Optional[Gateway] = None
        self._data_base = base
        # Desktop/UI prefs (default model, onboarding state) — not secrets; a plain JSON file.
        self._prefs = self._load_prefs()
        if self._prefs.get("default_model"):
            self.model = self._prefs["default_model"]
        # QualiTaTi tier rename (2026-08-19): configs written before it hold the old
        # alias as the default, which the picker then shows as a raw id ("qualitati:mimi")
        # alongside the three tiers. Migrate stored prefs once; the gateway keeps the old
        # wire aliases forever, so this is cosmetic-config hygiene, not compatibility.
        _LEGACY_QUALITATI = {
            "qualitati:mimi": "qualitati:mimi-hound",
            "qualitati:hound": "qualitati:mimi-hound",
            "qualitati:wolf": "qualitati:mimi-wolf",
            "qualitati:werewolf": "qualitati:mimi-werewolf",
            "qualitati:deepseek-v4-flash": "qualitati:mimi-puppy",
            "qualitati:puppy": "qualitati:mimi-puppy",
        }
        migrated = False
        if self.model in _LEGACY_QUALITATI:
            self.model = _LEGACY_QUALITATI[self.model]
            if self._prefs.get("default_model"):
                self._prefs["default_model"] = self.model
                migrated = True
        for key in ("models", "hidden_models"):
            vals = self._prefs.get(key)
            if isinstance(vals, list) and any(v in _LEGACY_QUALITATI for v in vals):
                remapped = [_LEGACY_QUALITATI.get(v, v) for v in vals]
                self._prefs[key] = list(dict.fromkeys(remapped))
                migrated = True
        if migrated:
            self._save_prefs()
        # Seed the PDF-fallback module global from prefs so engines see the user's
        # choice from the first turn (set_pdf_settings keeps it in sync after).
        from ..pdf_support import set_fallback_mode

        set_fallback_mode(self.pdf_settings()["pdf_fallback"])
        # Per-session live-view registry: every socket open on a session id gets the turn's events,
        # whoever drives the turn (foreground user_message, channel delivery, self-wake, resume).
        # Delivery itself is socket-independent — this only governs *live visibility*.
        self._session_clients: dict[str, set[Any]] = {}
        # App-wide event sockets (/ws/events): session-independent pushes — today the
        # automation-run-started toast (UX-026); badges could ride it later.
        self._event_clients: set[Any] = set()
        # App-wide activity (the floating Mimi companion): busy = any session turn OR
        # automation run in flight. Broadcast on /ws/events as {"type":"activity"} only
        # when the boolean FLIPS — the companion sleeps while busy and wakes on done.
        self._activity_busy: Any = (False, False)  # (busy, needs-the-user)
        self._active_automation_runs = 0
        # Titles of automations currently mid-run — the companion's speech bubble
        # says WHAT Mimi is working on, not just that she is.
        self._active_automation_titles: list[str] = []
        # Mission-control detail: automations mid-run as {id, title, started_at}
        # (parallel to the counter/titles above; feeds activity()["items"]).
        self._active_automation_info: list[dict[str, Any]] = []
        # Automation: scheduled tasks store + the tick scheduler (started in the lifespan).
        # The scheduler also resumes self-wake'd sessions each tick (extra_tick).
        self.task_store = TaskStore(base / "automation.db")
        # Apps: Mimi-written HTML tools, one folder each (Apps section).
        from ..apps import AppStore

        self.app_store = AppStore(base / "apps")
        self.scheduler = Scheduler(
            self.task_store, self._run_scheduled_task, extra_tick=self.resume_due_wakes
        )
        # Personas: registry + lifecycle state under this manager's data dir. Installed as the
        # process singleton so agents.get_agent resolves persona ids (incl. third-party) here.
        self.personas = PersonaRegistry(state_path=base / "personas.json")
        set_persona_registry(self.personas)
        # Inbox (cross-session human-attention queue), routing (named inboxes + Slack/Telegram
        # bindings), the Unattended toggle, and self-wake records.
        self.inbox = InboxStore(base / "inbox.json")
        # Companion alert: any parked approval/question flips the activity signal.
        self.inbox.on_change = self._announce_activity
        self.inbox_routing = InboxRouting(base / "inbox_routing.json")
        self.unattended = UnattendedRegistry(base / "unattended.json")
        self.wakes = WakeStore(base / "wakes.json")
        # Channel subscriptions (inbound): persisted (session_id, channel) records + a ring buffer
        # of recently-seen channel messages for get_channel_messages.
        self.subscriptions = SubscriptionStore(base / "subscriptions.json")
        self.channel_buffer = ChannelBuffer(state_path=base / "channels.json")
        # Mention router (§31): thread target → the session that owns that Slack thread.
        # Also the durable source of the thread's standing send_message grant (re-seeded
        # onto the engine in get_engine).
        self.mention_sessions = MentionSessionStore(base / "mention_threads.json")
        # Unauthorized inbound messages, parked instead of dropped (one-step allow-and-deliver).
        self.parked = ParkedStore(base / "parked.json")
        # People directory: "platform:user_id" → display name, noted from every inbound
        # (authorized or parked) so allow-list chips read "Rohit Prsad", not "U07JK…".
        self._people_path = base / "people.json"
        try:
            self._people: dict[str, str] = json.loads(self._people_path.read_text())
        except (OSError, ValueError):
            self._people = {}
        # Seed from already-parked messages (they carry resolved names) so an allow made from
        # an old parked item still gets a named chip.
        for it in self.parked.list():
            if it.get("user_name"):
                self._people.setdefault(
                    f"{it['platform']}:{it['user_id']}", it["user_name"]
                )
        # Connection hierarchy (UI-REFRESH §4): per-persona default connector on/off (seeded from the
        # manifest, then user-editable) + per-session overrides. Resolved into the session's effective
        # connector set, which gates inbound delivery and the engine's connector tools.
        self.persona_connections = PersonaConnectionStore(
            base / "persona_connections.json"
        )
        self.session_connections = SessionConnectionStore(
            base / "session_connections.json"
        )
        # Skills (SKILLS-SPEC §4): folder-backed CRUD + per-session mutes. The effective menu
        # gates the engine's skill catalog the same way effective_connectors gates connector
        # tools — one resolver feeds the catalog injection, the rail, and the composer popup.
        # seed_builtin: first run drops the bundled skills (theory building, consumer
        # paper writing, academic writing, business communication, slide design) into
        # the user's global skills folder — ordinary skills from then on.
        self.skill_store = SkillStore(seed_builtin=True)
        self.session_skills = SessionSkillStore(base / "session_skills.json")
        # Dead-letter: inbound messages with no destination + background-turn failures, so neither
        # vanishes silently (a debugging/visibility surface, not a redelivery queue).
        self.unrouted = UnroutedStore(base / "unrouted.json")

    # -- workspaces -------------------------------------------------------------
    def open_workspace(self, path: str, *, create: bool = False) -> dict[str, Any]:
        resolved = Path(path).expanduser()
        if resolved.exists() and not resolved.is_dir():
            return {"path": str(resolved), "ok": False, "error": "not a directory"}
        if not resolved.exists():
            if not create:
                return {
                    "path": str(resolved),
                    "ok": False,
                    "error": "folder does not exist",
                }
            try:
                resolved.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                return {"path": str(resolved), "ok": False, "error": str(exc)}
        resolved = resolved.resolve()
        self.session_store.touch_workspace(str(resolved))
        return {
            "path": str(resolved),
            "ok": True,
            "git_branch": _git_branch(resolved),
            "command_trust": self.workspace_command_trust(resolved),
        }

    def workspace_command_trust(self, path: str | Path) -> dict[str, Any]:
        if not str(path).strip():
            return {
                "workspace": "",
                "requested_commands": [],
                "trusted": False,
                "required": False,
            }
        canonical = WorkspaceTrustStore.canonical(path)
        commands = (
            workspace_allowed_commands(canonical)
            if Path(canonical).is_dir()
            else []
        )
        trusted = self.workspace_trust.is_trusted(canonical)
        return {
            "workspace": canonical,
            "requested_commands": commands,
            "trusted": trusted,
            "required": bool(commands and not trusted),
        }

    def _mcp_workspace_trusted(self, workspace: Optional[str | Path]) -> bool:
        """Whether workspace `.coworker/mcp.json` may be loaded (#213).

        Same consent boundary as repository ``allowed_commands``: an untrusted
        clone must not define stdio processes that spawn at session open.
        """
        return bool(workspace and self.workspace_trust.is_trusted(workspace))

    def set_workspace_trust(
        self, path: str | Path, *, trusted: bool
    ) -> dict[str, Any]:
        if not str(path).strip():
            return {"ok": False, "error": "workspace path is required"}
        candidate = Path(path).expanduser()
        if trusted and not candidate.is_dir():
            return {"ok": False, "error": "workspace is not a directory"}
        canonical = self.workspace_trust.set_trusted(candidate, trusted)
        effective = load_config(
            canonical, workspace_trusted=trusted
        ).allowed_commands
        # Apply trust/revocation immediately to live sessions rooted at this exact path.
        for engine in self._engines.values():
            engine_workspace = str(
                (getattr(engine, "audit_context", {}) or {}).get("workspace", "")
            )
            if engine_workspace and WorkspaceTrustStore.canonical(
                engine_workspace
            ) == canonical:
                engine.permissions.allowed_commands = list(effective)
        return {
            "ok": True,
            **self.workspace_command_trust(canonical),
        }

    def trusted_workspaces(self) -> list[dict[str, Any]]:
        return [
            {
                **self.workspace_command_trust(path),
                "exists": Path(path).is_dir(),
            }
            for path in self.workspace_trust.list()
        ]

    def recent_workspaces(self) -> list[dict[str, Any]]:
        """Recent real projects for the folder gate. Per-conversation scratch dirs are
        excluded — they're workspaces to the session store, but never something a user
        should re-open as a 'project'."""
        scratch = self.scratch_base().resolve()
        out = []
        for path in self.session_store.recent_workspaces():
            p = Path(path)
            try:
                if p.resolve().is_relative_to(scratch):
                    continue
            except OSError:
                pass
            out.append({"path": path, "name": p.name, "exists": p.is_dir()})
        return out

    # -- projects (PROJECTS spec, 2026-08-21) -------------------------------------
    # A project IS a real workspace folder — the per-conversation scratch dirs are never
    # projects. Metadata (name/emoji/pin/archive) lives on the workspaces row; instructions
    # are the folder's AGENTS.md (already injected as "Project conventions"); memory is the
    # workspace scope the `remember` tool already writes to. This layer only surfaces them.

    def _is_scratch_path(self, path: str) -> bool:
        try:
            return Path(path).resolve().is_relative_to(self.scratch_base().resolve())
        except OSError:
            return False

    def _project_path(self, requested: str) -> Optional[str]:
        """A known, non-scratch project path (canonical) — or None."""
        if not requested:
            return None
        path = str(Path(requested).expanduser().resolve())
        if self._is_scratch_path(path):
            return None
        if self.session_store.workspace_meta(path) is None:
            return None
        return path

    def _rescope_folder_memory_to_groups(self) -> None:
        """Move what a project knew onto the group that replaced it. Once, at startup.

        Project memory used to be workspace-scoped, because a project WAS a folder. With
        the folder gone, those facts would have been orphaned — still in the database,
        still injected for anything working in that directory, but no longer reachable
        from the project they belong to. The folder-to-group migration records where each
        group came from; this follows that trail.
        """
        try:
            origins = self.session_store.project_origins()
        except Exception:
            return
        if not origins:
            return
        moved = 0
        for project_id, folder in origins.items():
            try:
                items = self.memory_store.list(
                    scope=Scope.WORKSPACE, workspace=folder
                )
            except Exception:
                continue
            for item in items:
                try:
                    if self.memory_store.rescope_to_project(item.id, project_id):
                        moved += 1
                except Exception:
                    continue
        if moved:
            logger.info("re-scoped %d folder memories onto their project groups", moved)

    def list_projects(self, *, include_archived: bool = True) -> list[dict[str, Any]]:
        rows = self.session_store.list_projects()
        return [r for r in rows if include_archived or not r["archived"]]

    def create_project(self, name: str = "", emoji: str = "") -> dict[str, Any]:
        row = self.session_store.create_project((name or "New project").strip()[:80], (emoji or "").strip()[:8])
        return {"ok": True, "project": {**row, "sessions": 0, "pinned": False, "archived": False, "last_activity": ""}}

    def update_project(self, project_id: str, **fields: Any) -> dict[str, Any]:
        if "name" in fields and fields["name"] is not None:
            fields["name"] = str(fields["name"]).strip()[:80]
        if "emoji" in fields and fields["emoji"] is not None:
            fields["emoji"] = str(fields["emoji"]).strip()[:8]
        if not self.session_store.update_project(project_id, **fields):
            return {"ok": False, "error": "unknown project"}
        row = next(
            (p for p in self.session_store.list_projects() if p["id"] == project_id), None
        )
        return {"ok": True, "project": row}

    def delete_project(self, project_id: str, *, delete_sessions: bool = False) -> dict[str, Any]:
        """Delete the group. Its sessions are UNGROUPED by default, not deleted.

        A group is how the user files conversations, so removing the folder they are
        filed under must not shred the conversations — they return to the flat list.
        `delete_sessions=True` is the deliberate opt-in, and is refused while one of
        them is running so nothing is destroyed mid-turn.
        """
        rows = [
            s
            for s in self.list_sessions_in_project(project_id)
            if not str(s.get("session_id", "")).startswith("__")
        ]
        deleted = 0
        if delete_sessions:
            busy = [s for s in rows if self.is_running(str(s.get("session_id")))]
            if busy:
                return {
                    "ok": False,
                    "error": "a conversation in this project is still running — stop it first",
                }
            for row in rows:
                if self.delete_session(str(row["session_id"])).get("ok"):
                    deleted += 1
        if not self.session_store.delete_project(project_id):
            return {"ok": False, "error": "unknown project"}
        return {"ok": True, "id": project_id, "deleted_sessions": deleted, "ungrouped": len(rows) - deleted}

    def list_sessions_in_project(self, project_id: str) -> list[dict[str, Any]]:
        return [s for s in self.list_sessions() if s.get("project_id") == project_id]

    def set_project_instructions(self, project_id: str, text: str) -> dict[str, Any]:
        """The group's standing instructions — injected as "Project conventions" for
        every conversation filed under it.

        Stored on the group row, not in a file: a group has no folder to hold one, and
        a temp directory would be worse than nowhere — the OS empties it, and text
        somebody typed must not evaporate. Applies to NEW conversations, matching how
        folder instructions have always behaved.
        """
        text = (text or "").rstrip()
        if not self.session_store.update_project(project_id, instructions=text or ""):
            return {"ok": False, "error": "unknown project"}
        return {"ok": True, "instructions": text}

    def project_detail(self, project_id: str) -> dict[str, Any]:
        row = next(
            (p for p in self.session_store.list_projects() if p["id"] == project_id), None
        )
        if row is None:
            return {"ok": False, "error": "unknown project"}
        sessions = [
            s
            for s in self.list_sessions_in_project(project_id)
            if not s.get("archived") and not str(s.get("session_id", "")).startswith("__")
        ][:50]
        return {
            "ok": True,
            "project": row,
            "sessions": sessions,
            "instructions": self.session_store.project_instructions(project_id),
            "memory": self.list_memory(project_id=project_id),
        }

    def move_session_to_project(
        self, session_id: str, project_id: Optional[str]
    ) -> dict[str, Any]:
        """File a session under a group, or return it to the flat list with None.

        This changes only how the session is FILED. Its workspace — where its files
        live — is deliberately untouched: grouping is the user's organising idea, and
        it must never move anybody's documents.
        """
        if session_id.startswith("__"):
            return {"ok": False, "error": "internal sessions cannot be grouped"}
        if not self.session_store.set_session_project(session_id, project_id or None):
            return {"ok": False, "error": "unknown session or project"}
        if project_id:
            self._maybe_name_group_from_contents(project_id)
        return {"ok": True, "session_id": session_id, "project_id": project_id or None}

    # A group made from the sidebar's "+" is called "New project" until it is renamed,
    # and a placeholder nobody bothers to change is worse than no name. Once something
    # has been filed into it, take the name from the work (owner ask 2026-08-31).
    _PLACEHOLDER_GROUP_NAMES = {"new project", "untitled", "new group", ""}

    def _maybe_name_group_from_contents(self, project_id: str) -> None:
        """Name a still-unnamed group after the first conversation filed into it.

        Only ever replaces a placeholder — a name the user typed, or one already taken
        from a conversation, is left exactly alone.
        """
        row = next(
            (p for p in self.session_store.list_projects() if p["id"] == project_id), None
        )
        if row is None:
            return
        if str(row.get("name", "")).strip().lower() not in self._PLACEHOLDER_GROUP_NAMES:
            return
        members = self.list_sessions_in_project(project_id)
        titles = [
            str(m.get("title") or "").strip()
            for m in members
            if str(m.get("title") or "").strip()
            and str(m.get("title")).strip().lower() != "new session"
        ]
        if not titles:
            return
        self.session_store.update_project(project_id, name=titles[0][:80])

    # -- transfer pack: commands, instructions, @-mentions, skill import ------------
    # The vocabulary here is deliberately the one Claude Code / Cowork / Codex use, so a
    # user who learns MimiWork can drive those and vice-versa (owner ask 2026-08-23).

    def _command_store(self, workspace: Optional[str] = None):
        from ..commands import CommandStore

        dirs: list[Path] = []
        ws = self._project_path(workspace) if workspace else None
        if ws:
            dirs.append(Path(ws) / ".coworker" / "commands")
        dirs.append(state_dir() / "commands")
        return CommandStore(dirs), dirs

    def list_commands(self, workspace: Optional[str] = None) -> list[dict[str, Any]]:
        """The saved markdown commands reachable from this workspace, project scope first
        — the rows behind the composer's "/" palette."""
        store, dirs = self._command_store(workspace)
        project_dir = dirs[0] if len(dirs) > 1 else None
        out: list[dict[str, Any]] = []
        for row in store.catalog():
            cmd = store.get(row["name"])
            path = getattr(cmd, "path", None)
            scope = (
                "project"
                if project_dir is not None and path is not None and project_dir in path.parents
                else "global"
            )
            out.append({**row, "scope": scope, "path": str(path) if path else ""})
        return sorted(out, key=lambda r: (r["scope"] != "project", r["name"]))

    def expand_command(
        self, name: str, arguments: str = "", workspace: Optional[str] = None
    ) -> dict[str, Any]:
        """Substitute $ARGUMENTS and hand back the instruction text. Expanding here (not in
        the model) keeps a saved command deterministic — same input, same prompt."""
        from ..commands import CommandError

        store, _ = self._command_store(workspace)
        try:
            return {"ok": True, "name": name, "text": store.expand(name, arguments or "")}
        except CommandError as exc:
            return {"ok": False, "error": str(exc)}

    def global_instructions(self) -> dict[str, Any]:
        """Cowork calls this "Global instructions": one file that applies to every session."""
        from ..project import default_global_agents_path

        path = default_global_agents_path()
        try:
            text = path.read_text(encoding="utf-8") if path.is_file() else ""
        except OSError:
            text = ""
        return {"ok": True, "instructions": text, "path": str(path)}

    def set_global_instructions(self, text: str) -> dict[str, Any]:
        from ..project import default_global_agents_path

        path = default_global_agents_path()
        text = (text or "").rstrip()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            if text:
                path.write_text(text + "\n", encoding="utf-8")
            elif path.is_file():
                path.unlink()
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "instructions": text, "path": str(path)}

    def _mention_roots(
        self, workspace: Optional[str], session_id: Optional[str]
    ) -> list[Path]:
        """Folders the @-picker may look inside: the session's workspace plus the folders
        the user added to it. Nothing outside a granted root is ever searchable."""
        roots: list[Path] = []
        record = self.session_store.load(session_id) if session_id else None
        candidates: list[str] = []
        if record is not None:
            if record.workspace:
                candidates.append(record.workspace)
            for extra in record.extra_roots or []:
                path = extra.get("path") if isinstance(extra, dict) else None
                if path:
                    candidates.append(str(path))
        if workspace:
            candidates.append(workspace)
        for raw in candidates:
            try:
                path = Path(raw).expanduser().resolve()
            except OSError:
                continue
            if path.is_dir() and path not in roots:
                roots.append(path)
        return roots

    def workspace_tree(
        self,
        workspace: Optional[str] = None,
        session_id: Optional[str] = None,
        path: str = ".",
    ) -> dict[str, Any]:
        """One level of the file browser: entries under `path` (relative to a root).

        Containment is the same rule as @-mentions: only folders inside a granted
        root (the session's workspace + added roots) are ever listed. `path`
        selects the directory to open; it may be "root:<n>/sub/dir" to pick a
        specific root when several are granted, or a plain relative path which
        resolves against the first root that contains it.
        """
        from ..workspace_map import _PRUNE_DIRS

        roots = self._mention_roots(workspace, session_id)
        if not roots:
            return {"error": "no workspace folder is open"}

        rel = (path or ".").strip() or "."
        base: Optional[Path] = None
        root_index = 0
        if rel.startswith("root:"):
            # "root:2/sub/dir" → open root #2, then the sub-path
            head, _, rest = rel.partition("/")
            try:
                root_index = int(head.split(":", 1)[1])
            except ValueError:
                root_index = 0
            if 0 <= root_index < len(roots):
                base = roots[root_index]
                rel = rest or "."
        if base is None:
            for r in roots:
                candidate = (r / rel).resolve() if rel != "." else r
                try:
                    candidate.relative_to(r)
                except ValueError:
                    continue
                base = candidate
                root_index = roots.index(r)
                break
        if base is None or not base.is_dir():
            return {"error": f"not a folder in this workspace: {path}"}

        entries: list[dict[str, Any]] = []
        try:
            for entry in sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
                name = entry.name
                if name.startswith(".") or name in _PRUNE_DIRS:
                    continue
                try:
                    st = entry.stat()
                    size, mtime = st.st_size, st.st_mtime
                except OSError:
                    size, mtime = 0, 0.0
                entries.append(
                    {
                        "name": name,
                        "type": "dir" if entry.is_dir() else "file",
                        "size": size,
                        "modified_at": mtime,
                        # The path the next tree/read call should use.
                        "path": (f"root:{root_index}/" if len(roots) > 1 else "")
                        + (f"{rel}/{name}" if rel != "." else name),
                    }
                )
                if len(entries) >= 500:
                    entries[-1]["truncated"] = True
                    break
        except OSError as exc:
            return {"error": f"list failed: {exc}"}

        return {
            "root": str(roots[root_index]),
            "root_label": roots[root_index].name,
            "roots": [
                {"index": i, "path": str(r), "label": r.name} for i, r in enumerate(roots)
            ],
            "path": rel,
            "entries": entries,
        }

    def workspace_read(
        self,
        path: str,
        workspace: Optional[str] = None,
        session_id: Optional[str] = None,
        start_line: int = 1,
        max_lines: int = 500,
    ) -> dict[str, Any]:
        """Read a text file for the browser pane. Same containment as tree()."""
        roots = self._mention_roots(workspace, session_id)
        if not roots:
            return {"error": "no workspace folder is open"}

        target: Optional[Path] = None
        rel = (path or "").strip()
        if rel.startswith("root:"):
            head, _, rest = rel.partition("/")
            try:
                idx = int(head.split(":", 1)[1])
            except ValueError:
                idx = 0
            if 0 <= idx < len(roots):
                target = (roots[idx] / rest).resolve()
                rel = rest
        if target is None:
            for r in roots:
                candidate = (r / rel).resolve()
                try:
                    candidate.relative_to(r)
                except ValueError:
                    continue
                target = candidate
                break
        if target is None or not target.is_file():
            return {"error": f"not a file in this workspace: {path}"}

        start = start_line if isinstance(start_line, int) and start_line > 0 else 1
        n = max_lines if isinstance(max_lines, int) and max_lines > 0 else 500
        n = min(n, 2000)
        lines: list[str] = []
        total = 0
        try:
            with open(target, "r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    total = i
                    if i < start or len(lines) >= n:
                        continue
                    text = line.rstrip("\n")
                    if len(text) > 1000:
                        text = text[:1000] + "…"
                    lines.append(f"{i}\t{text}")
        except OSError as exc:
            return {"error": f"read failed: {exc}"}

        end = start + len(lines) - 1 if lines else start - 1
        out: dict[str, Any] = {
            "path": rel,
            "full_path": str(target),
            "start_line": start,
            "end_line": end,
            "total_lines": total,
            "content": "\n".join(lines),
        }
        if end < total:
            out["note"] = f"showing {start}-{end} of {total}; call with start_line={end + 1}"
        return out

    def search_files(
        self,
        query: str,
        workspace: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Fuzzy-ish path search under the granted roots, for the composer's @ mentions.
        Substring match on the relative path, most-recently-modified first."""
        from ..workspace_map import _PRUNE_DIRS

        needle = (query or "").strip().lower()
        hits: list[tuple[float, dict[str, Any]]] = []
        seen: set[str] = set()
        for root in self._mention_roots(workspace, session_id):
            walked = 0
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames if not d.startswith(".") and d not in _PRUNE_DIRS
                ]
                for name in filenames:
                    if name.startswith("."):
                        continue
                    walked += 1
                    if walked > 20000:  # bounded work on pathological trees
                        break
                    full = Path(dirpath) / name
                    try:
                        rel = full.relative_to(root).as_posix()
                    except ValueError:
                        continue
                    if needle and needle not in rel.lower():
                        continue
                    key = str(full)
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        st = full.stat()
                        mtime, size = st.st_mtime, st.st_size
                    except OSError:
                        mtime, size = 0.0, 0
                    hits.append(
                        (
                            mtime,
                            {
                                "path": rel,
                                "full_path": key,
                                "root": str(root),
                                "root_label": root.name,
                                # Size lets a drop tell two same-named files apart before it
                                # mentions one of them.
                                "size": size,
                                "modified_at": mtime,
                            },
                        )
                    )
                if walked > 20000:
                    break
        hits.sort(key=lambda h: -h[0])
        return [row for _mtime, row in hits[: max(1, min(int(limit or 20), 50))]]

    # Where the other agentic tools keep skills on this machine. The layouts differ and
    # aren't documented as stable, so this WALKS the trees looking for SKILL.md instead of
    # assuming a shape: plugin skills sit under `plugins/<name>/skills/` on one machine and
    # directly under `plugins/marketplaces/<name>/` on another, and Codex keeps its own
    # `~/.codex/skills` (owner report 2026-08-23 — "it does not find my claude skills").
    # Depth-bounded so a deep tree can't turn discovery into a crawl.
    _IMPORT_ROOTS = (
        (".claude/skills", "Claude Code"),
        (".claude/plugins", "Claude Code plugin"),
        (".codex/skills", "Codex"),
        (".codex/plugins", "Codex plugin"),
    )
    _IMPORT_DEPTH = 5
    _IMPORT_PRUNE = {".git", "node_modules", "__pycache__", "dist", "build", ".venv"}

    def _import_search_roots(self, workspace: Optional[str] = None) -> list[tuple[Path, str]]:
        roots = [(Path.home() / rel, label) for rel, label in self._IMPORT_ROOTS]
        ws = self._project_path(workspace) if workspace else None
        if ws:
            roots.append((Path(ws) / ".claude" / "skills", "this folder"))
            roots.append((Path(ws) / ".codex" / "skills", "this folder"))
        return roots

    def _discover_skill_folders(
        self, workspace: Optional[str] = None
    ) -> list[tuple[Path, str]]:
        """Every folder holding a SKILL.md under the known roots, with a source label."""
        found: list[tuple[Path, str]] = []
        seen: set[Path] = set()
        for base, source in self._import_search_roots(workspace):
            if not base.is_dir():
                continue
            base_depth = len(base.parts)
            for dirpath, dirnames, filenames in os.walk(base):
                here = Path(dirpath)
                if len(here.parts) - base_depth >= self._IMPORT_DEPTH:
                    dirnames[:] = []
                    continue
                dirnames[:] = [d for d in dirnames if d not in self._IMPORT_PRUNE]
                if "SKILL.md" not in filenames or here in seen:
                    continue
                seen.add(here)
                dirnames[:] = []  # a skill folder's children are its resources, not skills
                label = source
                if source.endswith("plugin"):
                    # Name the plugin it came from: "plugin: daymade-skills" says more.
                    rel = here.relative_to(base).parts
                    owner = next(
                        (part for part in rel if part not in ("marketplaces", "repos", "skills")),
                        "",
                    )
                    if owner and owner != here.name:
                        label = f"plugin: {owner}"
                found.append((here, label))
        return found

    def importable_skills(self, workspace: Optional[str] = None) -> list[dict[str, Any]]:
        """SKILL.md folders this machine already has for Claude Code / Cowork / Codex."""
        from ..skills.base import _parse_skill  # the parser the store itself uses

        have = {row.get("name") for row in self.list_skills(workspace)}
        found: list[dict[str, Any]] = []
        seen: set[str] = set()
        for folder, source in self._discover_skill_folders(workspace):
            try:
                parsed = _parse_skill(folder / "SKILL.md")
            except Exception:
                continue
            name = str(parsed.name or folder.name)
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            found.append(
                {
                    "name": name,
                    "description": str(parsed.description or ""),
                    "source": source,
                    "path": str(folder),
                    "installed": name in have,
                }
            )
        # Not-yet-imported first: the list is a shopping list, not an inventory.
        return sorted(found, key=lambda r: (r["installed"], r["name"].lower()))

    def import_skill(
        self, path: str, scope: str = "global", workspace: Optional[str] = None
    ) -> dict[str, Any]:
        """Copy a Claude Code / Cowork skill folder into this app's store, resources and
        all. The folder layout is identical, so nothing is rewritten."""
        source = Path(path).expanduser()
        if not (source / "SKILL.md").is_file():
            return {"ok": False, "error": "not a skill folder (no SKILL.md)"}
        allowed = {f.resolve() for f, _ in self._discover_skill_folders(workspace)}
        if source.resolve() not in allowed:
            return {"ok": False, "error": "that folder is not an importable skill location"}
        try:
            base = self.skill_store._base(scope, workspace)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        target = base / source.name
        if target.exists():
            return {"ok": False, "error": f"a skill folder named '{source.name}' already exists"}
        try:
            base.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target)
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "name": source.name, "path": str(target)}

    async def compact_session(self, session_id: str) -> dict[str, Any]:
        """Manual "/compact" — run the same policy auto-compaction uses, now. Refused while
        a turn is in flight (the engine owns its message list during a run)."""
        engine = self.get_engine(session_id)
        if engine is None:
            return {"ok": False, "error": "unknown session"}
        if not self.try_mark_running(session_id):
            return {"ok": False, "error": "that conversation is busy — try again when it finishes"}
        try:
            notice = await engine._compact_now(force=True)
            self.save(session_id, engine)
        except Exception as exc:  # summarizer/provider failure must not kill the session
            return {"ok": False, "error": str(exc)}
        finally:
            self.mark_idle(session_id)
        return {"ok": True, "compacted": bool(notice), "notice": notice or ""}

    DEFAULT_SCRATCH_BASE = "~/MimiWork"

    def scratch_base(self) -> Path:
        """Common area for per-conversation scratch directories. Configurable via prefs."""
        base = self._prefs.get("scratch_base") or self.DEFAULT_SCRATCH_BASE
        return Path(base).expanduser()

    def _provision_scratch(self, session_id: str) -> str:
        """Create (idempotently) and return this conversation's scratch directory."""
        d = self.scratch_base() / session_id
        d.mkdir(parents=True, exist_ok=True)
        return str(d.resolve())

    def _new_session_workspace(self, session_id: str) -> str:
        """Where a brand-new Cowork conversation works: the folder the user handed over
        for good, else a fresh scratch dir. A designated folder means no temp folder at
        all (owner ask 2026-09-02: "do not create a temp folder if we already have one")."""
        folder = self.default_folder()
        if folder:
            p = Path(folder["path"]).expanduser()
            if p.is_dir():
                return str(p.resolve())
        return self._provision_scratch(session_id)

    def _primary_root(self, ws: str) -> dict[str, Any]:
        """The primary root row: a scratch dir is labelled as such (the context rendering
        and the rail key on it); a real folder carries its own name."""
        label = "scratch" if self._is_scratch_path(ws) else (Path(ws).name or ws)
        return {"path": ws, "writable": True, "label": label}

    def resolve_workspace(self, requested: Optional[str]) -> Optional[str]:
        if requested:
            p = Path(requested).expanduser()
            if p.is_dir():
                return str(p.resolve())
            return None
        return self.default_workspace

    # -- engines ----------------------------------------------------------------
    def engine_workspace(
        self, session_id: str, *, workspace: Optional[str] = None, agent: str = "cowork"
    ) -> Optional[str]:
        """The workspace `get_engine` would bind — for prepping MCP tools beforehand."""
        record = self.session_store.load(session_id)
        if record:
            return record.workspace or None
        ag = get_agent(agent or "cowork")
        return self.resolve_workspace(workspace) if ag.needs_workspace else None

    def get_engine(
        self,
        session_id: str,
        *,
        workspace: Optional[str] = None,
        agent: str = "cowork",
        approver: Optional[Approver] = None,
        extra_tools: Optional[list[Any]] = None,
        directory_requester: Optional[Any] = None,
        plan_approver: Optional[Any] = None,
        question_asker: Optional[Any] = None,
    ) -> Optional[TurnEngine]:
        engine = self._engines.get(session_id)
        if engine is not None:
            if approver is not None:
                engine.approver = approver
            if directory_requester is not None:
                engine.directory_requester = directory_requester
            if plan_approver is not None:
                engine.plan_approver = plan_approver
            if question_asker is not None:
                engine.question_asker = question_asker
            return engine

        record = self.session_store.load(session_id)
        agent_name = (record.agent if record else agent) or "cowork"
        ag = get_agent(agent_name)

        seed_default = False  # only a brand-new conversation inherits the remembered folder
        if record:
            ws = record.workspace or None
            model, mode, messages = record.model, Mode(record.mode), record.messages
        else:
            ws = self.resolve_workspace(workspace) if ag.needs_workspace else None
            model, mode, messages = self.model, self.mode, None
            # "Run now" opens a fresh session for an automation's run: it must obey
            # the automation's own model and permission level, not the app defaults,
            # or the same task would behave differently by hand than on schedule.
            # (Only on first build — once a record exists it may carry the user's
            # own mid-run changes, which win.)
            owner = getattr(self, "task_store", None) and self.task_store.task_for_run_session(
                session_id
            )
            if owner is not None:
                model = owner.model or model
                mode = Mode(owner.mode)
            # An automation's own run is not "a new conversation the user just opened":
            # unattended runs get exactly the folders their task was given, never a
            # default picked up from the desktop.
            seed_default = owner is None
            # The folder handed over for good IS a new Cowork conversation's workspace —
            # no temp dir beside it (owner ask 2026-09-02). A folder the GUI names
            # explicitly still wins; the manager's generic default workspace does not.
            if seed_default and not workspace and ag.family == "knowledge":
                folder = self.default_folder()
                if folder and Path(folder["path"]).is_dir():
                    ws = str(Path(folder["path"]).resolve())

        if ag.needs_workspace and (not ws or not Path(ws).is_dir()):
            # Knowledge surfaces (Cowork, Ops, …) start "orphan": no folder picked →
            # auto-provision a per-conversation scratch directory (generalizes MyHelper's
            # auto-workspace). Code-family surfaces still require a real repo; Chat needs none.
            if ag.family == "knowledge":
                ws = (
                    self._new_session_workspace(session_id)
                    if seed_default
                    else self._provision_scratch(session_id)
                )
            else:
                return None

        if ws:
            self.session_store.touch_workspace(ws)
        # Orphan surfaces are multi-root: the scratch (ws) is the primary writable root, plus any
        # folders the user added (persisted per session). Code/Chat stay single-root (roots=None).
        roots = None
        if ag.family == "knowledge" and ws:
            extra = [
                r
                for r in ((record.extra_roots if record else []) or [])
                if Path(str(r.get("path", ""))).is_dir()
            ]
            if seed_default:
                extra = self._with_default_folder(extra)
            primary = self._primary_root(ws)
            extra = [r for r in extra if not _same_dir(str(r.get("path", "")), ws)]
            roots = [primary, *extra]
        engine = build_engine(
            agent=ag,
            workspace=ws,
            model=model,
            mode=mode,
            provider=self.provider,
            # Memory off (§4.3) = stop LEARNING, not amnesia: saved facts still inject
            # and stay usable, only the write tools go. Read at build time; running
            # sessions finish under the mode they started with.
            memory_store=self.memory_store,
            memory_off=not self.memory_settings.enabled,
            # LIVE, not a snapshot: turning saving off mid-conversation must take
            # effect at once (owner-hit 2026-07-28 — a running session kept saving).
            memory_saving_enabled=lambda: self.memory_settings.enabled,
            app_store=self.app_store,
            # Callable, not a snapshot: editing your instructions in Settings applies
            # to conversations already open (same reason as the saving switch).
            user_rules=lambda: self.memory_settings.user_rules,
            # The group's standing instructions, if this conversation is filed under
            # one. A group has no folder, so this comes from the database rather than
            # an AGENTS.md — the reason it survives at all now that a project is not
            # a directory.
            group_instructions=self.session_store.project_instructions(
                (record.project_id if record else None) or ""
            ),
            project_id=(record.project_id if record else None) or None,
            on_memory_saved=self._memory_saved_notifier(session_id),
            messages=messages,
            extra_tools=extra_tools,
            secrets=self.secrets,
            task_store=self.task_store,
            wake_store=self.wakes,
            session_id=session_id,
            audit_sink=self.audit_store.append,
            roots=roots,
            # WS sessions pass mode-aware callbacks (attended → live prompt, unattended → Inbox).
            # Background / self-wake / durable-resume runs have no live socket → default to the
            # Inbox-based callbacks so a rebuilt engine can still get approvals/answers (and, on
            # resume, the already-resolved item returns immediately).
            approver=approver or self.inbox_approver(session_id, agent),
            directory_requester=directory_requester
            or self.inbox_directory_requester(session_id, agent),
            plan_approver=plan_approver or self.inbox_plan_approver(session_id, agent),
            question_asker=question_asker
            or self.inbox_question_asker(session_id, agent),
            subscription_store=self.subscriptions,
            channel_buffer=self.channel_buffer,
            routing_targets=self._routing_targets(session_id, agent),
            # Per-session connection hierarchy: expose only effective-enabled connectors' tools.
            connector_filter=self.effective_connectors(session_id, agent_name),
            # Per-session skill menu, LIVE (SKILLS-SPEC §3): a callable so load_skill sees
            # disables/new skills immediately; the catalog snapshot is taken at build.
            skill_filter=lambda sid=session_id, w=ws: self.effective_skill_names(sid, w),
        )
        # An automation run rebuilt here (manual "Run now" over WS, durable resume) still
        # carries its task's standing allowances — the rules live on the task record.
        owning_task = self.task_store.task_for_run_session(session_id)
        if owning_task is not None:
            self._seed_task_permissions(engine, owning_task)
        # A mention-spawned session (§31) keeps its in-thread reply pre-approved across
        # rebuilds/restarts — the grant is re-derived from the durable thread map.
        for thread_target in self.mention_sessions.targets_for(session_id):
            engine.permissions.task_rules.setdefault("send_message", set()).add(
                thread_target
            )
        if record is not None and record.grants:
            self._apply_grants(engine, record.grants)
        # Auto-compaction (OPE-27): restore the persisted view boundary and wire the live
        # Settings getter — post-construction, so build_engine's signature stays put.
        if record is not None and record.compaction:
            from ..compaction import CompactionState

            engine.compaction_state = CompactionState.from_dict(record.compaction)
        engine.compaction_settings = self.compaction_settings
        self._wire_tool_recovery(engine, session_id)
        self._engines[session_id] = engine
        return engine

    def _wire_tool_recovery(self, engine: TurnEngine, session_id: str) -> None:
        """Install the shared durability boundary on every persistent engine path."""
        engine.tool_journal = self.session_store
        engine.session_id = session_id
        engine.checkpoint = lambda eng=engine: self.save(session_id, eng)
        engine.file_recovery = RecoverySession(
            self._data_base,
            session_id,
            roots=lambda eng=engine: getattr(eng, "roots", None)
            or str(eng.permissions.workspace_root),
        )

    def list_recovery_points(self, session_id: str) -> list[dict[str, Any]]:
        engine = self.get_engine(session_id)
        if engine is None or engine.file_recovery is None:
            return []
        return engine.file_recovery.list()

    def restore_recovery_point(
        self, session_id: str, transaction_id: str
    ) -> dict[str, Any]:
        engine = self.get_engine(session_id)
        if engine is None or engine.file_recovery is None:
            return {"ok": False, "error": "session has no file recovery history"}
        if session_id in self._running_sessions:
            return {"ok": False, "error": "wait for Mimi to finish before restoring files"}
        return engine.file_recovery.restore(transaction_id)

    def _routing_targets(self, session_id: str, agent: str) -> list[str]:
        """The channel address(es) this session's Inbox routes OUT to — used to warn when a
        subscription (inbound) collides with Inbox routing (outbound) on the same channel.
        """
        binding = self.inbox_routing.binding_for(
            self.inbox_routing.route_for(session_id, agent)
        )
        return [f"{binding.channel}:{binding.target}"] if binding.channel else []

    # -- connection hierarchy (UI-REFRESH §4) -----------------------------------
    def _persona_of(self, session_id: str, persona_id: Optional[str] = None) -> str:
        if persona_id:
            return persona_id
        record = self.session_store.load(session_id)
        return (record.agent if record else None) or self.personas.default_id()

    def effective_connectors(
        self, session_id: str, persona_id: Optional[str] = None
    ) -> set[str]:
        """The connectors effectively enabled for this session (§4.1): connected AND not muted by
        the session override / persona default. Drives the engine's connector-tool gating; seeds the
        persona defaults from the manifest on first read using the full connected set.
        """
        persona = self._persona_of(session_id, persona_id)
        connected = {c["name"] for c in connector_list(self.secrets) if c["connected"]}
        entry = self.personas.get(persona)
        manifest = entry.manifest if entry else None
        persona_defaults = self.persona_connections.defaults_for(
            persona, manifest, connected=connected
        )
        session_overrides = self.session_connections.get(session_id)
        return set(
            effective_connections(
                connected=connected,
                persona_defaults=persona_defaults,
                session_overrides=session_overrides,
            )
        )

    def _inbound_connector_allowed(self, session_id: str, connector: str) -> bool:
        """Whether an inbound message on `connector` should be DELIVERED to `session_id` (§4.3).

        Uses the SAME effective set as the engine's connector-tool gating so the inbound gate and the
        tool gate can never disagree (a muted connector is muted both ways, from the first message).
        """
        return connector in self.effective_connectors(session_id)

    # -- persona + session connection surfaces (UI-REFRESH §5/§6) ----------------
    @staticmethod
    def _workspace_kind(entry) -> str:
        """The persona's workspace requirement as a stable string for the GUI. Manifest-backed
        personas carry it verbatim (git|deliverable|none); builtins (which have no manifest) map
        family/needs_workspace into the SAME vocabulary so the frontend reads one enum:
        code-family → git, knowledge-family with a workspace → deliverable, none → none.
        """
        if entry.manifest is not None:
            return entry.manifest.workspace
        if not entry.needs_workspace:
            return "none"
        return "git" if entry.family == "code" else "deliverable"

    def _connected_connectors(self) -> set[str]:
        """The account-connected connector names (the first layer of the §4 hierarchy)."""
        return {c["name"] for c in connector_list(self.secrets) if c["connected"]}

    def _persona_default_connections(
        self, persona_id: str, manifest, connected: set[str]
    ) -> list[dict[str, Any]]:
        """The persona's default connector map (seeded from the manifest's connector recommends on
        first read, then user-editable) as a list, each annotated with account-connectedness.
        """
        defaults = self.persona_connections.defaults_for(
            persona_id, manifest, connected=connected
        )
        return [
            {"connector": c, "enabled": bool(enabled), "connected": c in connected}
            for c, enabled in defaults.items()
        ]

    def persona_detail(self, persona_id: str) -> Optional[dict[str, Any]]:
        """Identity + capabilities + recommends(+connected) + default connections for one persona
        (UI-REFRESH §5). Returns None for an unknown id (the route maps that to an error).
        """
        entry = self.personas.get(persona_id)
        if entry is None:
            return None
        manifest = entry.manifest
        connected = self._connected_connectors()
        recommends = [
            {
                "kind": rec.kind,
                "ref": rec.ref,
                "reason": rec.reason,
                "tier": rec.tier,
                "connected": rec.ref in connected,
            }
            for rec in (manifest.recommends if manifest else [])
        ]
        return {
            "id": entry.id,
            "name": entry.name,
            "icon": entry.icon,
            "tagline": entry.tagline,
            "description": manifest.description if manifest else "",
            "enabled": self.personas.is_enabled(entry.id),
            "tools": list(entry.tools),
            "recommended_models": list(manifest.recommended_models) if manifest else [],
            "default_permission_mode": (
                manifest.default_permission_mode if manifest else "interactive"
            ),
            "workspace": self._workspace_kind(entry),
            "recommends": recommends,
            "default_connections": self._persona_default_connections(
                persona_id, manifest, connected
            ),
        }

    def set_persona_connection(
        self, persona_id: str, connector: str, enabled: bool
    ) -> dict[str, Any]:
        """Set a persona-default connector on/off (UI-REFRESH §5). Seeds the manifest defaults
        first so the stored row stays complete (the edit overlays the full seed rather than
        collapsing the row to this one connector), then returns the refreshed default_connections
        so the client can re-render without a second GET."""
        entry = self.personas.get(persona_id)
        if entry is None:
            return {"ok": False, "error": f"unknown persona: {persona_id}"}
        manifest = entry.manifest
        connected = self._connected_connectors()
        self.persona_connections.defaults_for(persona_id, manifest, connected=connected)
        self.persona_connections.set(persona_id, connector, bool(enabled))
        return {
            "ok": True,
            "default_connections": self._persona_default_connections(
                persona_id, manifest, connected
            ),
        }

    def set_persona_enabled(self, persona_id: str, enabled: bool) -> dict[str, Any]:
        """Flip a persona's enabled flag. Disabling also archives its real (unarchived,
        non-internal) sessions — disable means "put this coworker and its history away", so
        the persona's sidebar section disappears with it (owner call, 2026-07-04). Re-enabling
        never unarchives: that would overwrite the user's archive state; history returns one
        click at a time via the Show-archived disclosure. Raises KeyError for unknown ids.
        """
        self.personas.set_enabled(persona_id, enabled)
        archived = 0
        if not enabled:
            for r in self.session_store.list():
                if (
                    r.agent == persona_id
                    and not r.archived
                    and not r.session_id.startswith("__")
                ):
                    self.session_store.set_flags(r.session_id, archived=True)
                    archived += 1
        return {"ok": True, "archived_sessions": archived}

    def _connection_detail(
        self, session_id: str, connector: str, info: Optional[dict[str, Any]]
    ) -> str:
        """A short human description of WHY a connector is live for a session: the chat ids it's
        subscribed to on that platform, plus "DMs" if this is the designated DM session. Channel
        *names* would need the live adapter's resolve cache (not cheap here), so we show the chat
        ids; with no subscription/DM tie we fall back to the connector's title."""
        prefix = f"{connector}:"
        parts = [
            s.channel.split(":", 1)[1]
            for s in self.subscriptions.for_session(session_id)
            if s.channel.startswith(prefix)
        ]
        if self.dm_session() == session_id:
            parts.append("DMs")
        if parts:
            return " · ".join(parts)
        return (info or {}).get("title") or connector

    def session_connections_view(
        self, session_id: str, persona_id: Optional[str] = None
    ) -> dict[str, Any]:
        """The per-session connections drawer payload (UI-REFRESH §6): every account-connected
        connector with its effective on/off state (muted ones stay VISIBLE as off — a §4.2 toggle
        must never make a row vanish), the persona's connector recommends that aren't yet
        account-connected, and the attention count (= those unconnected recommends).

        ``persona_id`` is the caller's hint (the GUI knows the active persona). It matters for a
        brand-new session: no SessionRecord exists until the first turn persists, so without the
        hint the view would resolve to the DEFAULT persona and show its defaults/recommends —
        the owner's 2026-07-03 finding (a fresh Project Manager session rendered cowork's view).
        """
        persona = self._persona_of(session_id, persona_id)
        entry = self.personas.get(persona)
        manifest = entry.manifest if entry else None
        connectors = connector_list(self.secrets)
        by_name = {c["name"]: c for c in connectors}
        connected_names = {c["name"] for c in connectors if c["connected"]}
        effective = self.effective_connectors(session_id, persona)
        connected = [
            {
                "connector": name,
                "enabled": name in effective,
                "detail": self._connection_detail(session_id, name, by_name.get(name)),
            }
            for name in sorted(connected_names)
        ]
        recommended = [
            {
                "connector": rec.ref,
                "reason": rec.reason,
                "tier": rec.tier,
                "connected": False,
            }
            for rec in (manifest.recommends if manifest else [])
            if rec.kind == "connector" and rec.ref not in connected_names
        ]
        return {
            "connected": connected,
            "recommended": recommended,
            "attention": sum(1 for r in recommended if not r["connected"]),
        }

    def inbox_question_asker(self, session_id: str, agent: str):
        """The Unattended `ask_user` handler: turn the agent's question into an Inbox item and
        suspend until a human answers it (from the Inbox, or inline when they open the session).
        Also the default for background/self-wake runs (no live socket). Mirrors to a bound channel
        like the approver does."""

        async def ask(
            args: dict[str, Any], tool_call_id: Optional[str] = None
        ) -> dict[str, Any]:
            from ..tools.ask import answer_result, question_item_fields

            fields = question_item_fields(args)
            if fields is None:
                return {"answer": "", "error": "no question"}
            inbox_name = self.inbox_routing.route_for(session_id, agent)
            item = self.inbox.add_question(
                session_id,
                inbox=inbox_name,
                tool_call_id=tool_call_id,
                **fields,
            )
            if (
                item.state != "pending"
            ):  # durable resume re-raised an already-answered prompt
                return answer_result(item.questions, item.resolution)
            self.persist_session(session_id)  # the pending tool call is now on disk
            await self.mirror_inbox_item(item)
            answer = await self.inbox.wait(item.id)
            return answer_result(item.questions, answer)

        return ask

    def inbox_approver(self, session_id: str, agent: str):
        """Inbox-based approver — the default for no-socket runs (background, self-wake, durable
        resume). On resume the item already exists + is resolved, so wait returns at once.
        """

        async def approve(request):
            item = self.inbox.add_approval(
                session_id,
                f"Run `{request.tool_name}`?",
                body=_approval_body(request),
                inbox=self.inbox_routing.route_for(session_id, agent),
                tool_call_id=getattr(request, "tool_call_id", None),
                data=self.approval_prompt_data(session_id, request),
            )
            if item.state == "pending":
                self.persist_session(session_id)
                await self.mirror_inbox_item(item)
            resolution = await self.inbox.wait(item.id)
            return self.approval_outcome(resolution, request, session_id)

        return approve

    def inbox_directory_requester(self, session_id: str, agent: str):
        async def request(args, tool_call_id=None):
            item = self.inbox.add_directory(
                session_id,
                "Grant access to a folder?",
                body=str(args.get("reason", "")),
                inbox=self.inbox_routing.route_for(session_id, agent),
                data={
                    "path": str(args.get("path", "")),
                    "writable": bool(args.get("writable", False)),
                },
                tool_call_id=tool_call_id,
            )
            if item.state == "pending":
                self.persist_session(session_id)
                await self.mirror_inbox_item(item)
            resp = _parse_inbox_json(await self.inbox.wait(item.id))
            if not resp.get("granted"):
                return {"granted": False, "reason": "the user declined the request"}
            path = (resp.get("path") or args.get("path") or "").strip()
            if not path:
                return {"granted": False, "error": "no directory was provided"}
            writable = bool(resp.get("writable", args.get("writable", False)))
            res = self.add_root(session_id, path, writable)
            if not res.get("ok"):
                return {
                    "granted": False,
                    "error": res.get("error", "could not grant access"),
                }
            return {"granted": True, "path": path, "writable": writable}

        return request

    def inbox_plan_approver(self, session_id: str, agent: str):
        async def approve(args, tool_call_id=None):
            item = self.inbox.add_plan(
                session_id,
                "Approve the plan?",
                body=str(args.get("plan", "")),
                inbox=self.inbox_routing.route_for(session_id, agent),
                tool_call_id=tool_call_id,
            )
            if item.state == "pending":
                self.persist_session(session_id)
                await self.mirror_inbox_item(item)
            resp = _parse_inbox_json(await self.inbox.wait(item.id))
            if not resp.get("approved"):
                return {
                    "approved": False,
                    "feedback": resp.get("feedback") or "the user rejected the plan",
                }
            return {"approved": True, "mode": resp.get("mode") or "interactive"}

        return approve

    def persist_session(self, session_id: str) -> None:
        """Save the cached engine's thread (so a prompt's pending tool call survives a crash)."""
        engine = self._engines.get(session_id)
        if engine is not None:
            self.save(session_id, engine)

    async def resolve_inbox(self, item_id: str, resolution: str) -> bool:
        """Resolve an Inbox item from any surface (REST / Slack button / channel reply). If the
        asking agent is still suspended live, that await handles it. Otherwise the process restarted
        (or the engine was evicted) while blocked → durably resume: rebuild the engine from the
        saved thread and continue the turn."""
        item = self.inbox.get(item_id)
        ok = self.inbox.resolve(item_id, resolution)
        if not ok or item is None:
            return ok
        if not self.is_running(item.session_id):
            await self._durable_resume(item)
        return ok

    async def _durable_resume(self, item) -> None:
        if not getattr(item, "tool_call_id", None):
            return  # nothing to reconstruct (legacy item) — best-effort: leave it
        engine = self.get_engine(item.session_id)
        if engine is None or not hasattr(engine, "resume"):
            return
        if getattr(item, "kind", "") == "approval":
            # A legacy transcript may predate tool_runs.  The existence of the
            # approval proves this exact call parked before execution, so it is safe
            # to seed `prepared` after upgrade.  Generic row-less calls still fail closed.
            engine.seed_approved_recovery(item.tool_call_id)
        if not self.try_mark_running(item.session_id):
            return
        try:
            async for _event in engine.resume():
                pass
            self.save(item.session_id, engine)
        finally:
            self.mark_idle(item.session_id)

    # -- MCP --------------------------------------------------------------------
    async def prepare_mcp_tools(
        self, session_id: str, *, workspace: Optional[str] = None, agent: str = "cowork"
    ) -> list[Any]:
        """Connect enabled MCP servers (global + workspace) and return their tool callables.

        Called from the async WS handler before `get_engine`; no-op if the engine is already
        built (its MCP tools are attached). Servers that fail to connect are skipped.
        """
        if session_id in self._engines:
            return []
        from ..connectors.descriptors import get_descriptor
        from ..connectors.tool_defs import (
            approval_for_tool,
            mcp_tool_defs,
            tool_enabled,
        )
        from ..mcp import oauth as mcp_oauth

        ws = self.engine_workspace(session_id, workspace=workspace, agent=agent)
        loop = asyncio.get_running_loop()
        effective: Optional[set[str]] = None  # computed lazily, once
        out: list[Any] = []
        for server in load_mcp_servers(
            ws,
            secrets=self.secrets,
            workspace_trusted=self._mcp_workspace_trusted(ws),
        ):
            if not server.enabled:
                continue
            if server.auth == "oauth" and not mcp_oauth.has_tokens(
                server.name, self.secrets
            ):
                # NEVER start an interactive OAuth flow from a turn: a token-less
                # server here would open a browser and block every session for the
                # full flow timeout (owner-hit 2026-07-20 — a failed one-click's
                # leftover config froze all new sessions). Flows start only from an
                # explicit connect in Settings/Connectors.
                continue
            descriptor = get_descriptor(server.name)
            backed = descriptor is not None and bool(descriptor.mcp_url)
            if backed:
                # Connector-backed server: obey the same gates as connector tools —
                # the session's effective connector set and the per-tool toggles.
                # The descriptor's PIN is authoritative over whatever the config
                # file says (drift can only ever shrink the surface).
                if effective is None:
                    effective = self.effective_connectors(session_id, agent)
                if server.name not in effective:
                    continue
                prefix = f"mcp__{server.name}__"
                server.include_tools = [
                    t.name.removeprefix(prefix)
                    for t in mcp_tool_defs(server.name)
                    if tool_enabled(self.secrets, server.name, t.name)
                ]
            try:
                conn = await self.mcp.ensure(server)
            except Exception as exc:
                if mcp_oauth.is_auth_required(exc):
                    # Stored tokens no longer refresh (vendor rotated/expired
                    # them) — the non-interactive connect refused to open a
                    # browser. Record it so the MCP page shows WHY the server is
                    # dark; the session just runs without its tools.
                    self._mcp_errors[server.name] = (
                        "sign-in required — reconnect this server from its page"
                    )
                    logger.info(
                        "mcp %s needs re-auth; skipped for this session", server.name
                    )
                # else: bad command / unreachable url — skip, don't break the session
                continue
            callables = build_callables(
                server,
                conn.tools,
                lambda tool, args, name=server.name: self.mcp.call(name, tool, args),
                loop,
            )
            if backed:
                # Per-tool approval from the pinned read/write classification
                # (server-level requires_approval is off for backed servers);
                # anything unclassified stays approval-gated — fail closed.
                for fn in callables:
                    fn.__aisuite_tool_metadata__.requires_approval = approval_for_tool(
                        fn.__aisuite_tool_metadata__.name, default=True
                    )
            out.extend(callables)
        return out

    def list_mcp(self) -> list[dict[str, Any]]:
        """Servers from the global config + connection status (does not connect)."""
        from ..connectors.descriptors import get_descriptor
        from ..mcp import oauth as mcp_oauth

        out = []
        for name, raw in read_global().items():
            d = get_descriptor(name)
            if d is not None and d.mcp_url:
                # Connector-backed server: surfaced on the Connectors page (its
                # connect/disconnect lifecycle lives there), not in the MCP tab.
                continue
            connected = name in self.mcp._conns
            is_oauth = str(raw.get("auth", "")).lower() == "oauth"
            if connected:
                status = "connected"
            elif not raw.get("enabled", True):
                status = "disabled"
            elif name in self._mcp_authorizing:
                status = "authorizing"
            elif is_oauth and not mcp_oauth.has_tokens(name, self.secrets):
                status = "needs_auth"
            else:
                status = "configured"
            out.append(
                {
                    "name": name,
                    "enabled": bool(raw.get("enabled", True)),
                    "transport": (
                        "http"
                        if (
                            raw.get("url")
                            or str(raw.get("type", "")).lower()
                            in {"http", "sse", "streamable-http"}
                        )
                        else "stdio"
                    ),
                    "requires_approval": bool(raw.get("requires_approval", True)),
                    "auth": "oauth" if is_oauth else None,
                    "status": status,
                    "last_error": self._mcp_errors.get(name),
                    "tool_count": (
                        len(self.mcp._conns[name].tools) if connected else None
                    ),
                    "config": _redact(raw),
                }
            )
        return out

    async def connect_mcp(self, name: str) -> dict[str, Any]:
        """Connect one server NOW — for OAuth servers this may open the browser and wait
        for the loopback callback, so callers run it as a background task and watch
        list_mcp for the status flip."""
        for server in load_mcp_servers(
            self.default_workspace,
            secrets=self.secrets,
            workspace_trusted=self._mcp_workspace_trusted(self.default_workspace),
        ):
            if server.name != name:
                continue
            self._mcp_authorizing.add(name)
            self._mcp_errors.pop(name, None)
            try:
                # The ONE place a browser sign-in may start: an explicit connect.
                conn = await self.mcp.ensure(server, interactive=True)
                return {"ok": True, "tools": len(conn.tools)}
            except Exception as exc:
                self._mcp_errors[name] = str(exc) or exc.__class__.__name__
                return {"ok": False, "error": self._mcp_errors[name]}
            finally:
                self._mcp_authorizing.discard(name)
        return {"ok": False, "error": f"unknown MCP server: {name}"}

    async def mcp_connect_connector(self, name: str) -> dict[str, Any]:
        """One-click connect for an MCP-BACKED connector (descriptor.mcp_url): seed
        the global server entry pinned to the curated allowlist, run the browser
        OAuth flow, and mark the connector profile `mode: "mcp"` on success."""
        from ..connectors.descriptors import get_descriptor
        from ..connectors.tool_defs import mcp_pinned_tools

        d = get_descriptor(name)
        if d is None or not d.mcp_url:
            return {"ok": False, "error": f"{name} has no MCP connect path"}
        put_global_server(
            name,
            {
                "url": d.mcp_url,
                "auth": "oauth",
                # Server-level approval off: writes gate per-tool via the pinned
                # read/write classification (prepare_mcp_tools); unknown vendor
                # tools never load at all (include_tools).
                "requires_approval": False,
                "include_tools": mcp_pinned_tools(name),
                "enabled": True,
            },
        )
        result = await self.connect_mcp(name)
        if result.get("ok"):
            profile = self.secrets.get(f"{name}:default") or {}
            self.secrets.put(
                f"{name}:default", {**profile, "mode": "mcp", "enabled": True}
            )
        else:
            # A failed connect must take its seeded config with it: an enabled
            # oauth entry with no tokens lingers forever (nothing owns it once
            # the descriptor's mcp_url is gone) and re-arms at every session
            # start — the owner-hit asana leftover, 2026-07-20.
            delete_global_server(name)
        return result

    async def signout_mcp(self, name: str) -> dict[str, Any]:
        """Drop the live connection (if any) and forget the stored OAuth tokens."""
        from ..mcp import oauth as mcp_oauth

        conn = self.mcp._conns.get(name)
        if conn is not None:
            conn.shutdown.set()
        self._mcp_errors.pop(name, None)
        removed = mcp_oauth.sign_out(name, self.secrets)
        return {"ok": True, "had_tokens": removed}

    def add_mcp(self, name: str, config: dict[str, Any]) -> dict[str, Any]:
        put_global_server(name, config)
        return {"ok": True, "name": name}

    def patch_mcp(self, name: str, changes: dict[str, Any]) -> dict[str, Any]:
        ok = patch_global_server(name, changes)
        return {"ok": ok, "name": name}

    def delete_mcp(self, name: str) -> dict[str, Any]:
        ok = delete_global_server(name)
        return {"ok": ok, "name": name}

    async def mcp_tools(self, name: str) -> dict[str, Any]:
        """Connect one server and list its tools (name + description)."""
        for server in load_mcp_servers(
            self.default_workspace,
            secrets=self.secrets,
            workspace_trusted=self._mcp_workspace_trusted(self.default_workspace),
        ):
            if server.name == name:
                try:
                    conn = await self.mcp.ensure(server)
                except Exception as exc:
                    return {"name": name, "ok": False, "error": str(exc), "tools": []}
                return {
                    "name": name,
                    "ok": True,
                    "tools": [
                        {"name": t.name, "description": getattr(t, "description", "")}
                        for t in conn.tools
                    ],
                }
        return {"name": name, "ok": False, "error": "unknown server", "tools": []}

    async def reload_mcp(self) -> dict[str, Any]:
        """Drop live MCP connections so new sessions reconnect with fresh config."""
        await self.mcp.aclose()
        return {"ok": True}

    # -- connectors -------------------------------------------------------------
    def list_connectors(self) -> list[dict[str, Any]]:
        # Enrich two-way connectors with the live gateway's recently-seen senders, so the Connectors
        # tab can manage the allow-list inline (each recent sender flagged authorized or not).
        connectors = connector_list(self.secrets)
        for c in connectors:
            if not (c.get("two_way") and c.get("connected")):
                continue
            allowed = set(c.get("allowed_users") or [])
            # Per-workspace allow-lists (managed relay) — a sender is judged against
            # ITS workspace's list; the flat list only governs team-less (socket) events.
            team_allowed = {
                w["team_id"]: set(w.get("allowed_users") or [])
                for w in (c.get("workspaces") or [])
            }
            recent = self.gateway.recent_senders(c["name"]) if self.gateway else []
            for r in recent:
                team = r.get("team_id")
                pool = team_allowed.get(team, set()) if team else allowed
                r["authorized"] = r.get("user_id") in pool
                # Backfill from the people directory (an event may predate name scopes).
                r["user_name"] = r.get("user_name") or self._people.get(
                    f"{c['name']}:{r.get('user_id')}"
                )
            c["recent"] = recent
            # Parked unauthorized messages (§19) — the connector page resolves them inline.
            c["unauthorized"] = self.parked.list(c["name"])
            # Allow-list display names from the people directory (ids stay the source of truth).
            c["allowed_user_names"] = {
                u: self._people.get(f"{c['name']}:{u}")
                for u in (c.get("allowed_users") or [])
            }
            c["approval_owner_names"] = {
                u: self._people.get(f"{c['name']}:{u}")
                for u in (c.get("approval_owner_ids") or [])
            }
            for w in c.get("workspaces") or []:
                w["allowed_user_names"] = {
                    u: self._people.get(f"{c['name']}:{u}")
                    for u in (w.get("allowed_users") or [])
                }
                w["approval_owner_names"] = {
                    u: self._people.get(f"{c['name']}:{u}")
                    for u in (w.get("approval_owner_ids") or [])
                }
        return connectors

    def connect_connector(
        self, name: str, fields: dict[str, Any], *, acknowledged: bool = False
    ) -> dict[str, Any]:
        # validates the token by a live API call (sync httpx) — run off the event loop
        return connect_connector(self.secrets, name, fields, acknowledged=acknowledged)

    def set_experimental_connectors(self, value: bool) -> dict[str, Any]:
        return set_experimental_enabled(self.secrets, value)

    def disconnect_connector(self, name: str) -> dict[str, Any]:
        # MCP-backed profile: drop the live server connection before the tokens go.
        conn = self.mcp._conns.get(name)
        if conn is not None:
            conn.shutdown.set()
        return disconnect_connector(self.secrets, name)

    def update_connector_tools(
        self, name: str, enabled: dict[str, Any]
    ) -> dict[str, Any]:
        return update_connector_tools(self.secrets, name, enabled)

    def list_audit(
        self,
        *,
        limit: int = 100,
        session_id: Optional[str] = None,
        connector: Optional[str] = None,
        tool: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        return self.audit_store.list(
            limit=limit, session_id=session_id, connector=connector, tool=tool
        )

    def browser_state(self) -> dict[str, Any]:
        return browser_state()

    def browser_screenshot(self) -> dict[str, Any]:
        return browser_take_screenshot()

    def browser_close(self) -> dict[str, Any]:
        return browser_close_session()

    # Tools whose success means a file on disk changed. Reading a folder is not producing
    # one: a conversation that opened your course folder did not make its contents.
    _ARTIFACT_TOOLS = frozenset(
        {
            "write_file",
            "replace_in_file",
            "apply_patch",
            "apply_unified_diff",
            "write_document",
            "edit_document",
            "revise_document",
            "write_presentation",
            "write_workbook",
            "edit_workbook",
            "annotate_image",
            "combine_images",
            "edit_image",
            "run_python",  # charts land in figures/
            "run_r",
            "qualitati_export_survey",
            "save_skill",
        }
    )
    _ARTIFACT_PATH_KEYS = ("path", "output_path", "target", "saved_to", "file")
    _ARTIFACT_PATH_LISTS = ("paths", "figures", "files", "outputs")

    def _touched_paths(self, record: Any, roots: list[Path]) -> list[Path]:
        """Files THIS conversation wrote, in the order it wrote them.

        Read from the transcript rather than a side table, so it is right for conversations
        that happened before this existed. Tool results carry the path they wrote; the tool
        NAME lives on the assistant message that requested the call, so the two are joined
        by tool_call_id.
        """
        names: dict[str, str] = {}
        found: list[Path] = []
        seen: set[Path] = set()

        def _keep(raw: Any) -> None:
            if not isinstance(raw, str) or not raw.strip():
                return
            candidate = Path(raw).expanduser()
            candidates = [candidate] if candidate.is_absolute() else [
                (r / candidate) for r in roots
            ]
            for cand in candidates:
                try:
                    resolved = cand.resolve()
                except OSError:
                    continue
                if resolved in seen or not resolved.is_file():
                    continue
                if not any(
                    resolved == r or r in resolved.parents for r in roots
                ):
                    continue  # never leave the folders this session was granted
                seen.add(resolved)
                found.append(resolved)
                return

        def _harvest(payload: Any) -> None:
            if not isinstance(payload, dict):
                return
            for key in self._ARTIFACT_PATH_KEYS:
                _keep(payload.get(key))
            for key in self._ARTIFACT_PATH_LISTS:
                value = payload.get(key)
                if isinstance(value, list):
                    for item in value:
                        _keep(item if isinstance(item, str) else (item or {}).get("path")
                              if isinstance(item, dict) else None)

        for message in record.messages or []:
            if not isinstance(message, dict):
                continue
            for call in message.get("tool_calls") or []:
                fn = (call or {}).get("function") or {}
                name = str(fn.get("name") or "")
                call_id = str((call or {}).get("id") or "")
                if call_id:
                    names[call_id] = name
                if name not in self._ARTIFACT_TOOLS:
                    continue
                # The arguments name the target even when the result doesn't echo it.
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except (TypeError, ValueError):
                    args = {}
                _harvest(args)
            if message.get("role") != "tool":
                continue
            if names.get(str(message.get("tool_call_id") or "")) not in self._ARTIFACT_TOOLS:
                continue
            content = message.get("content")
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except ValueError:
                    continue
            _harvest(content)
        return found

    # What the user came for, ranked. A turn that writes a report also writes the script
    # that made it, the intermediate CSV and a scratch note — sorted by time alone, the
    # .docx someone actually wants lands under three files they never asked about (owner
    # ask 2026-08-30). Recency still orders WITHIN a tier; it just stops outranking type.
    _DELIVERABLE_TIERS: tuple[tuple[int, frozenset[str]], ...] = (
        # Finished things a person opens, presents or sends.
        (0, frozenset({".pdf", ".docx", ".doc", ".docm", ".pptx", ".ppt", ".pptm",
                       ".xlsx", ".xls", ".xlsm", ".html", ".htm"})),
        # Figures and charts — usually the point of an analysis turn.
        (1, frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"})),
        # Data someone will open in another tool.
        (2, frozenset({".csv", ".tsv", ".sav", ".dta", ".json", ".xml", ".parquet"})),
    )
    # Everything else — source, notes, logs — is working material: still listed, just
    # below the deliverables it produced.
    _WORKING_TIER = 3

    # Machinery: the means, never the end. A turn that builds a workbook also leaves the
    # script that built it, and listing both put the throwaway beside the thing the user
    # waited for (owner ask 2026-09-02: "we would not put all those medium python file
    # artifact, instead only meaningful output as artifacts"). Prose (.md, .txt, .Rmd) is
    # NOT here — a written report is exactly what someone asked for, R chunks or not.
    _MACHINERY_SUFFIXES = frozenset(
        {
            ".py", ".pyc", ".pyo", ".r", ".js", ".mjs", ".cjs", ".ts", ".tsx",
            ".jsx", ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd", ".rb", ".pl", ".lua",
            ".sql", ".css", ".scss", ".less", ".log", ".lock", ".toml", ".ini", ".cfg",
            ".yaml", ".yml", ".env",
        }
    )

    @classmethod
    def _meaningful(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Drop machinery — unless machinery is all there is.

        A coding session whose deliverable IS the script would otherwise get an empty
        panel, which is worse than a noisy one.
        """
        kept = [
            r
            for r in rows
            if Path(str(r.get("name", ""))).suffix.lower() not in cls._MACHINERY_SUFFIXES
        ]
        return kept or rows

    @classmethod
    def _artifact_tier(cls, name: str) -> int:
        suffix = Path(name).suffix.lower()
        for tier, suffixes in cls._DELIVERABLE_TIERS:
            if suffix in suffixes:
                return tier
        return cls._WORKING_TIER

    @staticmethod
    def _artifact_order(row: dict[str, Any]) -> tuple[int, float]:
        """Deliverables first, newest first inside each tier."""
        return (int(row.get("tier", 3)), -float(row.get("modified_at") or 0.0))

    def _artifact_row(self, path: Path, root: Path) -> Optional[dict[str, Any]]:
        try:
            st = path.stat()
        except OSError:
            return None
        try:
            rel = str(path.relative_to(root))
        except ValueError:
            rel = str(path)  # a granted folder outside the workspace: show it whole
        return {
            "path": rel,
            # Absolute path for "Copy path" — the relative one is useless outside the app
            # (tester catch 2026-07-12: it copied just the filename).
            "abs_path": str(path),
            "name": path.name,
            "kind": _artifact_kind(path),
            "size": st.st_size,
            "modified_at": st.st_mtime,
            # Sort rank AND a hint the UI can group on — see _artifact_tier.
            "tier": self._artifact_tier(path.name),
        }

    def list_artifacts(self, session_id: str) -> list[dict[str, Any]]:
        record = self.session_store.load(session_id)
        workspace = record.workspace if record else self.default_workspace
        if not workspace:
            return []
        root = Path(workspace).expanduser().resolve()
        if not root.is_dir():
            return []
        # What the conversation produced — not what happens to sit in the folder it was
        # given (owner report 2026-08-24). A granted project folder can hold hundreds of
        # files nobody here wrote; listing them as "artifacts" buries the two that matter.
        seeded: list[dict[str, Any]] = []  # what the transcript named, before any walk
        if record is not None:
            roots = [root] + [
                p
                for p in (
                    Path(str(extra.get("path"))).expanduser().resolve()
                    for extra in (record.extra_roots or [])
                    if isinstance(extra, dict) and extra.get("path")
                )
                if p.is_dir()
            ]
            touched = self._touched_paths(record, roots)
            seeded = [
                row for row in (self._artifact_row(p, root) for p in touched) if row
            ]
            # Outside a scratch folder the transcript is the ONLY safe signal: a granted
            # course folder holds hundreds of files nobody here wrote (2026-08-24).
            if not self._is_scratch_path(str(root)):
                if seeded:
                    seeded.sort(key=self._artifact_order)
                    return self._meaningful(seeded)[:80]
                return []
            # Inside a per-conversation scratch folder every file is this conversation's by
            # construction, so the walk runs even when the transcript already named things.
            # It has to: a file a SCRIPT creates is named by no tool call, so the workbook a
            # run_python produced went missing while the script that wrote it was listed
            # (owner report 2026-09-02: "i only see all those python file in the artifact,
            # but not the generated valuable new file").
        out: list[dict[str, Any]] = list(seeded)

        def _key(p: Any) -> Any:
            # File IDENTITY, not spelling: a tool argument may differ in case from what
            # sits on disk, and APFS treats those as one file — while `normcase` is a
            # no-op on macOS and `realpath` keeps the caller's case. The inode does not
            # care how the path was written.
            try:
                st = os.stat(str(p))
                return (st.st_dev, st.st_ino)
            except OSError:
                return os.path.realpath(str(p))

        already = {_key(row["abs_path"]) for row in out}
        suffixes = {
            ".md",
            ".markdown",
            ".html",
            ".htm",
            ".txt",
            ".json",
            ".csv",
            ".tsv",
            ".py",
            ".js",
            ".ts",
            ".tsx",
            ".css",
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".gif",
            ".pdf",
            ".xlsx",
            ".xls",
            ".pptx",
            ".ppt",
            ".pptm",
            ".docx",
            ".doc",
            ".docm",
        }
        # os.walk with in-place pruning, NOT rglob: rglob descends first and filters after,
        # so a home-directory workspace walked into ~/Library and tripped the macOS App Data
        # TCC prompt ("MimiWork would like to access data from other apps") on every turn.
        # Pruning here means those directories are never entered at all.
        from ..tools.search import OS_DATA_DIRS

        # `attachments` holds the reference files a user uploaded when creating an
        # automation (see create_automation) — inputs, never something this run produced.
        skip = {"node_modules", "target", "dist", "__pycache__", "attachments"} | OS_DATA_DIRS
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in skip]
            for name in files:
                if name.startswith("."):
                    continue
                path = Path(dirpath) / name
                if path.suffix.lower() not in suffixes:
                    continue
                if _key(path) in already:
                    continue  # the transcript already placed it, with its own tier
                try:
                    st = path.stat()
                    if not path.is_file():
                        continue
                    out.append(
                        {
                            "path": str(path.relative_to(root)),
                            # Absolute path for "Copy path" — the relative one is useless
                            # outside the app (tester catch 2026-07-12: it copied just the
                            # filename).
                            "abs_path": str(path),
                            "name": path.name,
                            "kind": _artifact_kind(path),
                            "size": st.st_size,
                            "modified_at": st.st_mtime,
                            "tier": self._artifact_tier(path.name),
                        }
                    )
                except OSError:
                    continue
        out.sort(key=self._artifact_order)
        return self._meaningful(out)[:80]

    MAX_BINARY_PREVIEW = 25 * 1024 * 1024  # base64-over-JSON gets heavy past this

    def _artifact_target(
        self, session_id: str, path: str, *, allow_dir: bool = False
    ) -> tuple[Optional[Path], Optional[str]]:
        """Resolve an artifact path inside ANY folder this session was granted.

        Not just the workspace: a deliverable written into a folder the user added — and
        linked back as `[Open it](artifact:/absolute/path.docx)` — has to open from that
        link too, which it could not while resolution was workspace-only (owner report
        2026-08-24). Anything outside the granted folders is still refused.
        """
        record = self.session_store.load(session_id)
        workspace = record.workspace if record else self.default_workspace
        if not workspace:
            return None, "no workspace"
        roots = [Path(workspace).expanduser().resolve()]
        for extra in (record.extra_roots if record else None) or []:
            raw = extra.get("path") if isinstance(extra, dict) else None
            if not raw:
                continue
            try:
                candidate = Path(str(raw)).expanduser().resolve()
            except OSError:
                continue
            if candidate.is_dir() and candidate not in roots:
                roots.append(candidate)

        raw_path = Path(path).expanduser()
        candidates = (
            [raw_path] if raw_path.is_absolute() else [(root / raw_path) for root in roots]
        )
        outside = False
        for candidate in candidates:
            try:
                target = candidate.resolve()
            except OSError:
                continue
            if not any(target == root or root in target.parents for root in roots):
                outside = True
                continue
            if allow_dir and target.is_dir():
                return target, None
            if target.is_file():
                return target, None
        if outside:
            return None, "path escapes the folders this conversation can reach"
        return None, (
            "This isn't in the conversation's folders anymore — it may have been "
            "moved or deleted."
        )

    def reveal_root(self, session_id: str, path: str) -> dict[str, Any]:
        """Open one of this session's granted folders in the OS file manager — the Access
        list's folder names are clickable (owner ask 2026-08-24).

        Only a folder the user already granted TO THIS SESSION opens: the row is a shortcut
        to a decision they made, never a way to browse the disk from a path in a payload.
        """
        target = Path(path).expanduser()
        try:
            target = target.resolve()
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        granted = {
            Path(r["path"]).expanduser().resolve()
            for r in self.get_roots(session_id)
            if r.get("path")
        }
        if target not in granted:
            return {"ok": False, "error": "that folder is not one of this conversation's"}
        if not target.is_dir():
            return {"ok": False, "error": "that folder is not on this computer any more"}
        return _os_reveal(target, "open")

    def read_artifact(self, session_id: str, path: str) -> dict[str, Any]:
        # Folders are readable too (a model sometimes links a whole package, e.g. a skill
        # build dir): return a listing the viewer can render instead of a dead end.
        target, err = self._artifact_target(session_id, path, allow_dir=True)
        if target is None:
            return {"ok": False, "error": err}
        if target.is_dir():
            entries: list[dict[str, Any]] = []
            try:
                children = sorted(
                    target.iterdir(), key=lambda c: (c.is_file(), c.name.lower())
                )
            except OSError as exc:
                return {"ok": False, "error": str(exc)}
            for child in children[:500]:
                try:
                    size = 0 if child.is_dir() else child.stat().st_size
                except OSError:
                    continue
                entries.append({"name": child.name, "dir": child.is_dir(), "size": size})
            return {"ok": True, "path": path, "kind": "folder", "entries": entries}
        kind = _artifact_kind(target)
        if kind == "office":
            # PowerPoint/Word binaries can't be previewed inline; the UI offers
            # "Open in default app" instead of trying to render them.
            return {"ok": True, "path": path, "kind": "office"}
        if kind in ("image", "pdf", "sheet"):
            import base64

            if target.stat().st_size > self.MAX_BINARY_PREVIEW:
                return {
                    "ok": False,
                    "error": "file too large to preview — use Reveal to open it",
                }
            mime = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif",
                ".pdf": "application/pdf",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".xls": "application/vnd.ms-excel",
            }.get(target.suffix.lower(), "application/octet-stream")
            data = base64.b64encode(target.read_bytes()).decode("ascii")
            return {
                "ok": True,
                "path": path,
                "kind": kind,
                "data_url": f"data:{mime};base64,{data}",
            }
        try:
            text = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return {"ok": False, "error": "binary file cannot be previewed"}
        return {
            "ok": True,
            "path": path,
            "kind": kind,
            "content": text[:500000],
            "truncated": len(text) > 500000,
        }

    def reveal_artifact(
        self, session_id: str, path: str, mode: str = "reveal"
    ) -> dict[str, Any]:
        """Show the file in the OS file manager (`reveal`) or open it with its default app
        (`open`), once the path is confirmed to live inside this session's workspace."""
        target, err = self._artifact_target(session_id, path, allow_dir=True)
        if target is None:
            return {"ok": False, "error": err}
        return _os_reveal(target, mode)

    # -- web search -------------------------------------------------------------
    def get_web_search(self) -> dict[str, Any]:
        from ..config import load_config
        from ..web import provider_names

        profile = self.secrets.get("web_search:default") or {}
        provider = (
            profile.get("provider") or load_config().web_search_provider or "duckduckgo"
        )
        return {
            "provider": provider,
            "has_key": bool(profile.get("api_key")),
            "providers": provider_names(),
        }

    def set_web_search(
        self, provider: str, api_key: Optional[str] = None
    ) -> dict[str, Any]:
        from ..web import provider_names

        if provider not in provider_names():
            return {"ok": False, "error": f"unknown provider: {provider}"}
        profile: dict[str, Any] = {"provider": provider}
        if api_key:
            profile["api_key"] = api_key
        self.secrets.put("web_search:default", profile)
        return {"ok": True, "provider": provider}

    # -- QualiTaTi account (credit-metered gateway) -----------------------------
    def _qualitati(self):
        from ..qualitati import QualitatiClient

        return QualitatiClient(self.secrets)

    _MIMI_TIER_MODELS = (
        "qualitati:mimi-puppy",
        "qualitati:mimi-hound",
        "qualitati:mimi-wolf",
        "qualitati:mimi-werewolf",
    )

    def _adopt_qualitati_models(self, state: dict[str, Any]) -> None:
        """After a successful sign-in, the three Mimi tiers belong in the picker, and a
        fresh install's never-configured default (gpt-5.6-sol with no key) gives way to
        the free tier — the model a new account can actually talk to (owner ask
        2026-08-29). A default that already works is never stolen."""
        if not (state.get("signed_in") and state.get("provider_configured")):
            return
        for model in self._MIMI_TIER_MODELS:
            try:
                self.add_model(model)
            except Exception:
                pass
        if not self._provider_configured(self._model_provider(self.model)):
            self.set_default_model("qualitati:mimi-puppy")

    def _qualitati_key_changed(self) -> None:
        """Drop the cached gateway client so the next turn reads the key we just wrote.

        Signing in mints a NEW key, and the router caches its client — key and all —
        at first use. Without this, a re-signed-in app kept presenting the previous
        key: if that one had been revoked, every model call failed with "Invalid or
        revoked API key", and signing in again did not help, because the same stale
        client answered. Only quitting the app cleared it (owner-hit 2026-08-31).

        Logout matters just as much in the other direction: the key is deleted from
        disk, and a cached client would happily keep spending on it.
        """
        self._refresh_provider("qualitati")

    def qualitati_login(self, username: str, password: str) -> dict[str, Any]:
        out = self._qualitati().login(username, password)
        self._qualitati_key_changed()
        self._adopt_qualitati_models(out)
        return out

    def qualitati_register(
        self, username: str, email: str, password: str, referrer_code: str = ""
    ) -> dict[str, Any]:
        return self._qualitati().register(username, email, password, referrer_code)

    def qualitati_verify_mfa(self, code: str) -> dict[str, Any]:
        out = self._qualitati().verify_mfa(code)
        self._qualitati_key_changed()
        self._adopt_qualitati_models(out)
        return out

    def qualitati_status(self) -> dict[str, Any]:
        """Signed-in state for the account card. A session that is signed in but has no
        gateway key gets one here, silently: the user did everything right, and the only
        thing standing between them and the Mimi models is a key mint that failed once."""
        client = self._qualitati()
        state = client.status()
        if state.get("signed_in") and not state.get("provider_configured"):
            if client.ensure_provider_key().get("ok"):
                self._qualitati_key_changed()
                state = client.status()
        self._adopt_qualitati_models(state)
        return state

    def qualitati_reconnect(self) -> dict[str, Any]:
        """The account card's "Reconnect" — mint the gateway key without a fresh password."""
        client = self._qualitati()
        out = client.ensure_provider_key()
        if out.get("ok"):
            self._qualitati_key_changed()
        return {**out, **({"status": client.status()} if out.get("ok") else {})}

    def qualitati_logout(self) -> dict[str, Any]:
        out = self._qualitati().logout()
        self._qualitati_key_changed()
        return out

    def _qualitati_get(self, path: str, *, label: str) -> dict[str, Any]:
        """GET a QualiTaTi API path with the stored credential.

        The personal API key comes first and the JWT second: keys don't expire,
        so a signed-in app keeps working after the token would have lapsed.
        """
        import json as _json
        from urllib import error, request

        from ..qualitati import AUTH_PROFILE, DEFAULT_BASE, PROVIDER_PROFILE

        auth = self.secrets.get(AUTH_PROFILE) or {}
        provider = self.secrets.get(PROVIDER_PROFILE) or {}
        api_key = provider.get("api_key") if isinstance(provider, dict) else None
        jwt = auth.get("access_token")
        if not (api_key or jwt):
            return {"ok": False, "error": "not signed in"}
        base = (auth.get("base_url") or DEFAULT_BASE).rstrip("/")
        headers = (
            {"X-API-Key": api_key} if api_key else {"Authorization": f"Bearer {jwt}"}
        )
        req = request.Request(base + path, headers=headers)
        try:
            with request.urlopen(req, timeout=30) as r:
                return {"ok": True, **_json.load(r)}
        except error.HTTPError as e:
            return {"ok": False, "error": f"{label} unavailable ({e.code})"}
        except Exception as e:
            return {"ok": False, "error": f"{label} unavailable: {e}"}

    def _qualitati_send(self, path: str, payload: dict, *, label: str) -> dict[str, Any]:
        """PUT a small JSON body to a QualiTaTi API path with the stored credential —
        the write twin of _qualitati_get, same key-first auth order."""
        import json as _json
        from urllib import error, request

        from ..qualitati import AUTH_PROFILE, DEFAULT_BASE, PROVIDER_PROFILE

        auth = self.secrets.get(AUTH_PROFILE) or {}
        provider = self.secrets.get(PROVIDER_PROFILE) or {}
        api_key = provider.get("api_key") if isinstance(provider, dict) else None
        jwt = auth.get("access_token")
        if not (api_key or jwt):
            return {"ok": False, "error": "not signed in"}
        base = (auth.get("base_url") or DEFAULT_BASE).rstrip("/")
        headers = {"Content-Type": "application/json"}
        headers.update(
            {"X-API-Key": api_key} if api_key else {"Authorization": f"Bearer {jwt}"}
        )
        req = request.Request(
            base + path, data=_json.dumps(payload).encode(), headers=headers, method="PUT"
        )
        try:
            with request.urlopen(req, timeout=30) as r:
                return {"ok": True, **_json.load(r)}
        except error.HTTPError as e:
            return {"ok": False, "error": f"{label} unavailable ({e.code})"}
        except Exception as e:
            return {"ok": False, "error": f"{label} unavailable: {e}"}

    def qualitati_region(self) -> dict[str, Any]:
        """The account's Mimi model region — where the models answering this app run.
        "us" (default, DigitalOcean, cheaper) or "eu" (strict GDPR, Scaleway Paris,
        pricier). Lives on the ACCOUNT, read by the gateway per request — so setting
        it here changes the very next message, on every device."""
        return self._qualitati_get("/api/user/mimiwork-region", label="model region")

    def qualitati_set_region(self, region: str) -> dict[str, Any]:
        region = str(region or "").strip().lower()
        if region not in ("eu", "us"):
            return {"ok": False, "error": "region must be 'eu' or 'us'"}
        return self._qualitati_send(
            "/api/user/mimiwork-region", {"region": region}, label="model region"
        )

    def qualitati_footprint(self) -> dict[str, Any]:
        """Measured environmental impact of the Mimi service (Scaleway data,
        proxied through the QualiTaTi gateway with the stored credential)."""
        return self._qualitati_get("/api/llm/v1/footprint", label="footprint")

    def qualitati_credits(self, limit: int = 50) -> dict[str, Any]:
        """What this app has spent from the QualiTaTi account, most recent first.

        Reads the account's own credit ledger, narrowed to the rows MimiWork
        wrote (`source=mimiwork*`), and shapes it for the Activity page: one row
        per model call with the credits it cost and which pool paid, plus the
        totals and the balance that is left. Spend is the server's ledger, never
        a local estimate — the numbers in the app are the numbers on the bill.
        """
        limit = max(1, min(int(limit or 50), 200))
        body = self._qualitati_get(
            f"/api/user/credit-ledger?limit={limit}&source=mimiwork*", label="credit history"
        )
        if not body.get("ok"):
            return body

        rows: list[dict[str, Any]] = []
        spent = 0
        free_calls = 0
        for entry in body.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            meta = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            cost = meta.get("credits_cost")
            if cost is None:
                cost = -int(entry.get("delta_credits") or 0)
            cost = max(0, int(cost or 0))
            free = str(entry.get("source") or "").endswith("_free")
            spent += cost
            free_calls += 1 if free else 0
            rows.append(
                {
                    "id": entry.get("id"),
                    "at": entry.get("created_at"),
                    "credits": cost,
                    "free": free,
                    "model": meta.get("model") or "",
                    "route": meta.get("route") or "",
                    "tokens_in": int(meta.get("tokens_in") or 0),
                    "tokens_out": int(meta.get("tokens_out") or 0),
                    # Which pool paid — team pool, this month's points, or the
                    # purchased credits that never expire.
                    "team_points": int(meta.get("team_points_used") or 0),
                    "monthly_points": int(meta.get("monthly_points_used") or 0),
                    "lifelong_credits": int(meta.get("lifelong_credits_used") or 0),
                    "estimated": bool(meta.get("usage_estimated")),
                }
            )
        return {
            "ok": True,
            "entries": rows,
            "spent": spent,
            "calls": len(rows),
            "free_calls": free_calls,
            "balance": {
                "available": int(body.get("available_balance") or 0),
                "team_points": int(body.get("team_points") or 0),
                "monthly_points": int(body.get("monthly_points") or 0),
                "lifelong_credits": int(body.get("current_credits") or 0),
            },
        }

    # -- model providers (OpenAI, Ollama, …) ------------------------------------
    def get_providers(self) -> list[dict[str, Any]]:
        """Descriptor + per-provider status for the Settings UI. Never returns secret values;
        non-secret field values (e.g. the Ollama base URL) ARE returned so the form can prefill.
        """
        out: list[dict[str, Any]] = []
        for d in provider_descriptors():
            profile = self.secrets.get(f"provider:{d.name}") or {}
            configured = descriptor_configured(d, profile)
            values = {
                f.key: profile.get(f.key)
                for f in d.fields
                if not f.secret and profile.get(f.key)
            }
            out.append(
                {
                    **d.to_dict(),
                    "configured": configured,
                    "values": values,
                    "suggested_models": self._suggested_models(d.name),
                    # Key hygiene for the Settings pane: when the key was saved (date, stamped
                    # by set_provider) and when the provider last served a completion (epoch,
                    # stamped by the router's on_use hook). Absent for env-only config.
                    "key_set_at": profile.get("key_set_at"),
                    "last_used_at": (self._prefs.get("provider_last_used") or {}).get(
                        d.name
                    ),
                }
            )
        return out

    def pick_native_folder(self) -> dict[str, Any]:
        """Open the OS folder picker FROM THE SIDECAR — the browser GUI can't obtain absolute
        paths from web file dialogs, but the sidecar is local and can (the desktop shell uses
        Tauri's own picker instead). Blocking until pick/cancel; callers run it off-thread.
        """
        import subprocess
        import sys

        if sys.platform == "darwin":
            cmd = [
                "osascript",
                "-e",
                'tell application "System Events" to activate',
                "-e",
                'POSIX path of (choose folder with prompt "Give the coworker access to a folder")',
            ]
        elif sys.platform == "win32":
            # WinForms folder dialog via PowerShell — no extra deps. -STA is required
            # (the dialog silently fails in the default MTA apartment).
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms; "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "$f.Description = 'Give the coworker access to a folder'; "
                "if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) "
                "{ [Console]::Out.Write($f.SelectedPath) }"
            )
            cmd = ["powershell.exe", "-NoProfile", "-STA", "-Command", ps]
        else:
            # Linux: zenity when present; otherwise the GUI's paste-a-path input remains.
            cmd = ["zenity", "--file-selection", "--directory"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired):
            return {"ok": False, "error": "no native folder picker available"}
        path = (out.stdout or "").strip()
        if out.returncode != 0 or not path:
            return {"ok": False, "canceled": True}
        return {"ok": True, "path": path}

    def _note_provider_use(self, name: str) -> None:
        """Router on_use hook: remember when a provider last served a completion. Persisted
        THROTTLED (once per provider per minute) — this fires on every model call, from engine
        threads, and prefs.json isn't a place for a write-per-token-of-work."""
        import time

        now = time.time()
        used = self._prefs.setdefault("provider_last_used", {})
        if now - float(used.get(name) or 0) < 60:
            return
        used[name] = now
        try:
            self._save_prefs()
        except OSError:
            pass

    # Suggestions for the OpenAI-compatible vendor providers (checked against vendor docs
    # 2026-07-04; refresh alongside `recommended_model` in providers/registry.py).
    # Extras the matrix doesn't vouch for, offered in the "add model" datalist. Refreshed
    # with the matrix on 2026-08-23.
    COMPAT_MODELS = {
        "zai": ["glm-5.3", "glm-5.2-turbo", "glm-5.2"],
        "deepseek": ["deepseek-v4-flash", "deepseek-v4-pro"],
        "kimi": ["kimi-k3", "kimi-k2.6"],
        "minimax": ["MiniMax-M3", "MiniMax-M2.5"],
        "qwen": ["qwen3.8-max", "qwen3-max", "qwen3-coder-plus", "qwen-plus"],
        "xai": ["grok-4.6", "grok-4.3"],
        "mistral": ["mistral-large-latest", "mistral-small-latest"],
    }

    def _suggested_models(self, name: str) -> list[str]:
        """Bare model-name suggestions for the 'add model' form (datalist), per provider.
        Ollama → live `/api/tags` (best-effort); everyone else → the curated matrix,
        topped up with the compat-vendor extras the matrix doesn't vouch for."""
        if name == "ollama":
            return [m.split(":", 1)[-1] for m in self._ollama_models()]
        from ..providers.matrix import models_for_provider

        return list(
            dict.fromkeys(
                [*models_for_provider(name), *self.COMPAT_MODELS.get(name, [])]
            )
        )

    def set_provider(
        self, name: str, fields: Optional[dict[str, Any]]
    ) -> dict[str, Any]:
        """Store a provider's config in its `provider:<name>` SecretStore profile and rebuild
        its cached client. Merges provided fields into any existing profile."""
        d = get_descriptor(name)
        if d is None:
            return {"ok": False, "error": f"unknown provider: {name}"}
        fields = fields or {}
        profile = dict(self.secrets.get(f"provider:{name}") or {})
        for f in d.fields:
            if f.key not in fields:
                continue
            val = fields.get(f.key)
            if isinstance(val, str):
                val = val.strip()
            if val:
                profile[f.key] = val
            elif not f.required:
                profile.pop(f.key, None)
        missing = [f.label for f in d.fields if f.required and not profile.get(f.key)]
        if missing:
            return {"ok": False, "error": "missing: " + ", ".join(missing)}
        # A (re)pasted key stamps its save date — Settings shows "key added <date>" so stale
        # keys are visible. Endpoint-only saves keep the original stamp.
        if isinstance(fields.get("api_key"), str) and fields["api_key"].strip():
            from datetime import date

            profile["key_set_at"] = date.today().isoformat()
        self.secrets.put(f"provider:{name}", profile)
        self._refresh_provider(name)
        # Convenience: if the provider recommends a model and it's actually available, add it to
        # the curated list so it shows up in the composer right after configuring the provider.
        rec = d.recommended_model
        added: Optional[str] = None
        if rec and rec in self._suggested_models(name):
            # OpenAI models stay bare (the router's default); others carry their prefix.
            added = rec if name == "openai" else f"{name}:{rec}"
            self.add_model(added)
        # First working provider wins the default: if the current default model belongs to a
        # provider with no usable config (the fresh-install gpt-5.6-sol case), switch the default to
        # this provider's model. A default that already works is never stolen.
        if added and not self._provider_configured(self._model_provider(self.model)):
            self.set_default_model(added)
        return {"ok": True, "provider": name, "recommended_model": rec}

    def remove_provider(self, name: str) -> dict[str, Any]:
        """Forget a provider's stored config (Settings ▸ Models "Remove key"). The whole
        `provider:<name>` profile goes — key, endpoint, key_set_at — so the provider reads
        as never configured. Curated models stay; they just gray out until a new key."""
        d = get_descriptor(name)
        if d is None:
            return {"ok": False, "error": f"unknown provider: {name}"}
        self.secrets.delete(f"provider:{name}")
        self._refresh_provider(name)
        return {"ok": True, "provider": name}

    def verify_provider(
        self, name: str, fields: Optional[dict[str, Any]]
    ) -> dict[str, Any]:
        """Test a provider's credentials with a live read-only call, WITHOUT persisting them, so
        onboarding can offer a "Test" button. Falls back to stored/env values when the form left
        a field blank (e.g. testing an already-configured provider)."""
        import os

        d = get_descriptor(name)
        if d is None:
            return {"ok": False, "error": f"unknown provider: {name}"}
        fields = fields or {}
        profile = self.secrets.get(f"provider:{name}") or {}
        merged = {}
        for f in d.fields:
            val = fields.get(f.key) or profile.get(f.key) or ""
            if isinstance(val, str):
                val = val.strip()
            if val:
                merged[f.key] = val
        api_key = merged.get("api_key", "")
        if not api_key and d.env_key:
            api_key = os.environ.get(d.env_key, "").strip()
        has_key_field = any(f.key == "api_key" for f in d.fields)
        if d.needs_key and has_key_field and not api_key:
            return {"ok": False, "error": "Enter an API key to test."}
        if d.needs_key and not has_key_field:
            # Multi-field cloud providers (Bedrock): required fields must be present;
            # actual credentials may be ambient (~/.aws, env) and are checked by the call.
            missing = [f.label for f in d.fields if f.required and not merged.get(f.key)]
            if missing:
                return {"ok": False, "error": "missing: " + ", ".join(missing)}
        return verify_provider_key(
            name, api_key=api_key, base_url=merged.get("base_url", ""), fields=merged
        )

    def test_model(self, model: str) -> dict[str, Any]:
        """Ask one model to answer once — the honest version of "does this work?".

        Listing a provider's catalog (what `verify_provider` does) proves the key is valid,
        not that a particular model will answer: the QualiTaTi tiers are gateway aliases, so
        a tier can be missing or out of credit while the key is perfectly good. This sends
        the smallest possible completion and reports what came back.
        """
        model = (model or "").strip()
        if not model:
            return {"ok": False, "error": "no model given"}
        try:
            reply = self.provider.complete(
                model=model,
                messages=[{"role": "user", "content": "Reply with the single word: ready"}],
                max_tokens=16,
                temperature=0,
            )
        except Exception as exc:  # every provider failure mode lands here
            from ..providers.errors import friendly_model_error

            return {
                "ok": False,
                "model": model,
                "error": friendly_model_error(model, exc) or str(exc)[:300],
            }
        text = ""
        try:  # the shape differs per provider; a missing text is not a failure
            choice = getattr(reply, "choices", [None])[0]
            message = getattr(choice, "message", None)
            text = str(getattr(message, "content", "") or "").strip()
        except Exception:
            text = ""
        return {"ok": True, "model": model, "reply": text[:120]}

    def _model_provider(self, model: str) -> str:
        """The provider a model string routes to (known `prefix:` or the OpenAI default)."""
        if ":" in (model or ""):
            prefix = model.split(":", 1)[0]
            if get_descriptor(prefix) is not None:
                return prefix
        return "openai"

    def _provider_configured(self, name: str) -> bool:
        d = get_descriptor(name)
        if d is None:
            return False
        return descriptor_configured(d, self.secrets.get(f"provider:{name}") or {})

    # -- settings / prefs (model API key, default model, onboarding) -------------
    def _prefs_path(self) -> Path:
        return self._data_base / "prefs.json"

    def _load_prefs(self) -> dict[str, Any]:
        try:
            return json.loads(self._prefs_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_prefs(self) -> None:
        self._prefs_path().write_text(
            json.dumps(self._prefs, indent=2), encoding="utf-8"
        )

    # -- direct-message routing -------------------------------------------------
    def dm_session(self) -> Optional[str]:
        """The session a DM to the bot is routed to (user-designated). None → DMs are parked."""
        sid = self._prefs.get("dm_session")
        return sid or None

    def set_dm_session(self, session_id: Optional[str]) -> dict[str, Any]:
        """Designate (or clear, with a falsy id) the session that handles incoming DMs."""
        sid = (session_id or "").strip()
        if sid:
            self._prefs["dm_session"] = sid
        else:
            self._prefs.pop("dm_session", None)
        self._save_prefs()
        return {"ok": True, "dm_session": self.dm_session()}

    def _ollama_alive(self) -> bool:
        """Best-effort local-Ollama liveness, cached 30s (get_settings runs on every GUI
        fetch — no 2s probe inline). Keyless is not the same as PRESENT: `ollama:*` picker
        entries render only when an Ollama actually answers, so a machine with no Ollama
        never shows phantom local models (e.g. a stray pasted string saved as a model id,
        caught 2026-07-21)."""
        import time

        now = time.monotonic()
        cached = getattr(self, "_ollama_alive_cache", None)
        if cached and now - cached[0] < 30:
            return cached[1]
        profile = self.secrets.get("provider:ollama") or {}
        base = (profile.get("base_url") or "http://localhost:11434").strip().rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        try:
            import httpx

            alive = httpx.get(base + "/api/tags", timeout=0.8).status_code == 200
        except Exception:
            alive = False
        self._ollama_alive_cache = (now, alive)
        return alive

    def _ollama_models(self) -> list[str]:
        """Live list of models pulled into the configured Ollama server (via its native
        `/api/tags`), as `ollama:<name>` so they're directly selectable. Empty if Ollama isn't
        configured or unreachable — best-effort, never raises."""
        profile = self.secrets.get("provider:ollama")
        if not profile:
            return []
        base = (profile.get("base_url") or "http://localhost:11434").strip().rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        try:
            import httpx

            data = httpx.get(base + "/api/tags", timeout=2.0).json()
            return [
                f"ollama:{m['name']}" for m in data.get("models", []) if m.get("name")
            ]
        except Exception:
            return []

    def _curated_models(self) -> list[str]:
        """The models offered in the composer's selector: every curated-matrix model
        (`get_settings` culls the ones whose provider has no key) plus custom ids the user
        added, minus matrix models they removed. Deliberately NO built-in seed list — a
        fresh install offers nothing until a provider key exists, and then exactly that
        provider's matrix models appear. The active default is always kept selectable.
        """
        from ..providers.matrix import MATRIX

        user = self._prefs.get("models")
        user = user if isinstance(user, list) else []
        hidden = set(self._prefs.get("hidden_models") or [])
        models = [m for m in [*MATRIX, *user] if m not in hidden]
        return list(dict.fromkeys([self.model, *models]))

    def add_model(self, model: str) -> dict[str, Any]:
        """Add a model id (e.g. `gpt-4o`, `ollama:qwen2.5-coder:32b`) to the picker.
        Custom ids persist in prefs; a previously removed matrix model is just unhidden
        (storing it too would shadow future matrix updates)."""
        from ..providers.matrix import MATRIX

        model = (model or "").strip()
        if not model:
            return {"ok": False, "error": "empty model"}
        hidden = [m for m in self._prefs.get("hidden_models") or [] if m != model]
        if hidden:
            self._prefs["hidden_models"] = hidden
        else:
            self._prefs.pop("hidden_models", None)
        models = self._prefs.get("models")
        models = models if isinstance(models, list) else []
        if model not in models and model not in MATRIX:
            models.append(model)
        self._prefs["models"] = models
        self._save_prefs()
        return {"ok": True, **self.get_settings()}

    def remove_model(self, model: str) -> dict[str, Any]:
        """Remove a model id from the picker. Custom ids are dropped; matrix models are
        hidden by id (the matrix is derived, not stored, so a bare drop would resurrect
        them on the next read)."""
        from ..providers.matrix import MATRIX

        models = self._prefs.get("models")
        models = models if isinstance(models, list) else []
        self._prefs["models"] = [m for m in models if m != model]
        if model in MATRIX:
            hidden = self._prefs.get("hidden_models") or []
            if model not in hidden:
                self._prefs["hidden_models"] = [*hidden, model]
        self._save_prefs()
        return {"ok": True, **self.get_settings()}

    def get_settings(self) -> dict[str, Any]:
        """Model-access + UI status. Never returns the key; `source` says where it comes from."""
        import os

        env_key = bool(os.environ.get("OPENAI_API_KEY"))
        stored = bool((self.secrets.get("provider:openai") or {}).get("api_key"))
        # Only surface models whose provider is actually configured — the composer picker
        # reflects exactly what's connected. The active default is always kept selectable
        # (it's hidden behind the "No model" state until a provider is connected anyway).
        # Ollama is keyless, so "configured" is meaningless there — its models show only
        # while a local Ollama answers (cached liveness probe).
        def _selectable(m: str) -> bool:
            provider = self._model_provider(m)
            if provider == "ollama":
                return self._ollama_alive()
            return self._provider_configured(provider)

        selectable = [m for m in self._curated_models() if _selectable(m)]
        if self.model not in selectable:
            selectable.insert(0, self.model)
        from ..providers.matrix import model_context_windows, model_labels

        return {
            "provider": "openai",
            "model": self.model,
            "models": selectable,
            # Curated-matrix display names ({full id → "GLM-5.2 · via Together"}) so every
            # picker shows human labels; custom models absent here render their raw id.
            "model_labels": model_labels(),
            # {full id → context window in tokens}, verified matrix entries only —
            # drives the composer's context-fill meter (absent id → meter hides).
            "model_context_windows": model_context_windows(),
            "has_key": env_key or stored,
            # Provider-agnostic "can this default model actually run?" — true when the default
            # model's provider is configured (any provider, not just OpenAI). Drives the GUI's
            # "No model connected" composer chip and the onboarding Skip warning.
            "model_ready": self._provider_configured(self._model_provider(self.model)),
            "source": "env" if env_key else ("store" if stored else None),
            "onboarded": bool(self._prefs.get("onboarded")),
            "tour_seen": bool(self._prefs.get("tour_seen")),
            "language": str(self._prefs.get("language") or "en"),
            "time_saved": self.time_saved_total(),
            "experimental_connectors": experimental_enabled(self.secrets),
            "surfaces": self._surfaces(),
            "nav_layout": self._nav_layout(),
            "sessions_peek": self.sessions_peek(),
            "context_bar": self.context_bar(),
            "scratch_base": self._prefs.get("scratch_base")
            or self.DEFAULT_SCRATCH_BASE,
            # The folder new conversations start with — None until the user hands one over.
            "default_folder": self.default_folder(),
            # Real on-disk secrets location, so the UI shows the OS-native path instead of a
            # hardcoded POSIX one (Windows -> %APPDATA%\coworker, macOS/Linux -> ~/.config).
            "secrets_path": str(self.secrets.path),
            **self.pdf_settings(),
            **self.compaction_settings_payload(),
        }

    def _surfaces(self) -> dict[str, bool]:
        """Which session surfaces are shown in the sidebar. Cowork is the only surface."""
        return {"cowork": True}

    def set_surfaces(
        self, chat: Optional[bool] = None, code: Optional[bool] = None
    ) -> dict[str, Any]:
        """Back-compat no-op: Cowork is the only surface; Chat/Code were removed."""
        return {"ok": True, "surfaces": self._surfaces()}

    def _nav_layout(self) -> str:
        """Sidebar layout: ``"flat"`` (default) or ``"grouped"`` (by persona). Persisted in
        prefs (UI-REFRESH §7)."""
        return "grouped" if self._prefs.get("nav_layout") == "grouped" else "flat"

    def set_nav_layout(self, nav_layout: str) -> dict[str, Any]:
        """Set + persist the sidebar layout. Unknown values fall back to ``"flat"``."""
        value = "grouped" if (nav_layout or "").strip() == "grouped" else "flat"
        self._prefs["nav_layout"] = value
        self._save_prefs()
        return {"ok": True, "nav_layout": value}

    DEFAULT_SESSIONS_PEEK = 5

    def sessions_peek(self) -> int:
        """How many sessions a sidebar group shows before "Show more" (owner ask, 2026-07-03)."""
        try:
            n = int(self._prefs.get("sessions_peek", self.DEFAULT_SESSIONS_PEEK))
        except (TypeError, ValueError):
            n = self.DEFAULT_SESSIONS_PEEK
        return max(1, min(n, 50))

    def set_sessions_peek(self, n: int) -> dict[str, Any]:
        try:
            self._prefs["sessions_peek"] = max(1, min(int(n), 50))
        except (TypeError, ValueError):
            return {"ok": False, "error": "sessions_peek must be a number"}
        self._save_prefs()
        return {"ok": True, "sessions_peek": self.sessions_peek()}

    def context_bar(self) -> bool:
        """Whether the composer shows the context-window fill bar. OFF by default (owner
        ask): the chip then states the session total, and the popover keeps both numbers."""
        return bool(self._prefs.get("context_bar", False))

    def set_context_bar(self, shown: Any) -> dict[str, Any]:
        self._prefs["context_bar"] = bool(shown)
        self._save_prefs()
        return {"ok": True, "context_bar": self.context_bar()}

    # -- PDF attachments / token savings (owner ask, 2026-07-17) ----------------
    DEFAULT_PDF_MAX_PAGES = 20
    DEFAULT_PDF_MAX_MB = 10

    def pdf_settings(self) -> dict[str, Any]:
        """Fallback mode for models without native PDF support + the attach-time
        thresholds (Settings → Token savings: big PDFs quietly eat tokens)."""
        from ..pdf_support import FALLBACK_MODES

        mode = self._prefs.get("pdf_fallback")
        try:
            pages = int(self._prefs.get("pdf_max_pages", self.DEFAULT_PDF_MAX_PAGES))
        except (TypeError, ValueError):
            pages = self.DEFAULT_PDF_MAX_PAGES
        try:
            mb = int(self._prefs.get("pdf_max_mb", self.DEFAULT_PDF_MAX_MB))
        except (TypeError, ValueError):
            mb = self.DEFAULT_PDF_MAX_MB
        return {
            "pdf_fallback": mode if mode in FALLBACK_MODES else "text",
            "pdf_max_pages": max(1, min(pages, 100)),
            "pdf_max_mb": max(1, min(mb, 10)),
        }

    def compaction_settings(self) -> dict[str, Any]:
        """The live auto-compaction knobs (OPE-27) — read by every engine per check, so a
        Settings change applies without a rebuild. Only the two spec'd overrides plus the
        summarizer-model pin; absent keys fall back to compaction.py defaults."""
        from ..compaction import DEFAULT_CAP_TOKENS, DEFAULT_THRESHOLD_PCT

        return {
            "threshold_pct": float(
                self._prefs.get("compaction_threshold_pct") or DEFAULT_THRESHOLD_PCT
            ),
            "cap_tokens": int(
                self._prefs.get("compaction_cap_tokens") or DEFAULT_CAP_TOKENS
            ),
            # "" → the session's own model (engine falls back to self.model).
            "model": str(self._prefs.get("compaction_model") or ""),
        }

    def compaction_settings_payload(self) -> dict[str, Any]:
        """The same knobs under REST-facing names (prefixed to keep /v1/settings flat)."""
        settings = self.compaction_settings()
        return {
            "compaction_threshold_pct": settings["threshold_pct"],
            "compaction_cap_tokens": settings["cap_tokens"],
            "compaction_model": settings["model"],
        }

    def set_compaction_settings(
        self,
        threshold_pct: Any = None,
        cap_tokens: Any = None,
        model: Any = None,
    ) -> dict[str, Any]:
        """Persist the auto-compaction overrides (OPE-27). Threshold is a percentage of
        the model's context window (10–95); the cap is an absolute token ceiling; model
        pins the summarizer ('' → the session's own model). Engines read these live via
        `compaction_settings()`, so changes apply to running sessions immediately."""
        if threshold_pct is not None:
            try:
                pct = float(threshold_pct)
            except (TypeError, ValueError):
                return {"ok": False, "error": "compaction_threshold_pct must be a number"}
            if not 0.10 <= pct <= 0.95:
                return {
                    "ok": False,
                    "error": "compaction_threshold_pct must be between 0.10 and 0.95",
                }
            self._prefs["compaction_threshold_pct"] = pct
        if cap_tokens is not None:
            try:
                self._prefs["compaction_cap_tokens"] = max(
                    10_000, min(int(cap_tokens), 2_000_000)
                )
            except (TypeError, ValueError):
                return {"ok": False, "error": "compaction_cap_tokens must be a number"}
        if model is not None:
            self._prefs["compaction_model"] = str(model)
        self._save_prefs()
        return {"ok": True, **self.compaction_settings()}

    def set_pdf_settings(
        self,
        fallback: Any = None,
        max_pages: Any = None,
        max_mb: Any = None,
    ) -> dict[str, Any]:
        from ..pdf_support import FALLBACK_MODES, set_fallback_mode

        if fallback is not None:
            if fallback not in FALLBACK_MODES:
                return {"ok": False, "error": "pdf_fallback must be 'text' or 'images'"}
            self._prefs["pdf_fallback"] = fallback
        for key, value, ceiling in (
            ("pdf_max_pages", max_pages, 100),
            ("pdf_max_mb", max_mb, 10),
        ):
            if value is None:
                continue
            try:
                self._prefs[key] = max(1, min(int(value), ceiling))
            except (TypeError, ValueError):
                return {"ok": False, "error": f"{key} must be a number"}
        self._save_prefs()
        settings = self.pdf_settings()
        set_fallback_mode(settings["pdf_fallback"])  # engines read the module global
        return {"ok": True, **settings}

    def set_model_key(self, api_key: str) -> dict[str, Any]:
        """Persist the model API key to the SecretStore (0600). The new provider client is
        built lazily on the next turn, so it picks the key up without a restart."""
        api_key = (api_key or "").strip()
        if not api_key:
            return {"ok": False, "error": "empty api key"}
        # Merge, don't replace: the profile may also hold a custom endpoint (base_url).
        profile = dict(self.secrets.get("provider:openai") or {})
        profile.update({"type": "api_key", "api_key": api_key})
        self.secrets.put("provider:openai", profile)
        self._refresh_provider("openai")  # rebuild the OpenAI client with the new key
        return {"ok": True, **self.get_settings()}

    def set_default_model(self, model: str) -> dict[str, Any]:
        """Set + persist the default model for new sessions (the UI pre-selects it)."""
        model = (model or "").strip()
        if not model:
            return {"ok": False, "error": "empty model"}
        self.model = model
        self._prefs["default_model"] = model
        self._save_prefs()
        return {"ok": True, **self.get_settings()}

    # Below this many distinct tools, the account is still learning the app rather
    # than exploring: in week one everything is new, and a Growth axis at 90% would
    # say nothing about the user. Novelty starts counting once there is a habit to
    # be different from.
    _NOVELTY_WARMUP = 8

    def _attribute_growth(self, delta: "TimeSaved") -> None:
        """Move a turn's first-ever-tool minutes from their usual pillar into Growth.

        MOVE, never add: the pillars have to keep summing to the same minutes as the
        hours-saved badge beside them. A tool counts as new exactly once — it joins
        the seen set here — so a Growth spike is a real first, not a recurring bonus.
        """
        seen = self._prefs.get("seen_tools")
        seen = set(seen) if isinstance(seen, list) else set()
        fresh = [t for t, m in delta.by_tool.items() if m > 0 and t not in seen]
        warmed = len(seen) >= self._NOVELTY_WARMUP
        if fresh:
            self._prefs["seen_tools"] = sorted(seen | set(fresh))
        if not (fresh and warmed):
            return
        moved = 0.0
        for tool in fresh:
            minutes = delta.by_tool.get(tool, 0.0)
            category = delta.tool_category(tool)
            if not category or minutes <= 0:
                continue
            available = delta.by_category.get(category, 0.0)
            take = min(minutes, available)
            if take <= 0:
                continue
            delta.by_category[category] = available - take
            if delta.by_category[category] <= 0:
                delta.by_category.pop(category, None)
            moved += take
        if moved > 0:
            delta.by_category["Growth"] = delta.by_category.get("Growth", 0.0) + moved

    def record_time_saved(self, session_id: str, totals: dict[str, Any]) -> None:
        """Fold a finished turn's estimate into the install's running total.

        The per-session figure lives on the engine and rides each turn_end event; this
        is the all-time counter behind the logo. Stored as the accumulated components
        rather than the difference, so a later change to the rates re-reads the past
        honestly instead of freezing an old claim."""
        from ..timesaved import TimeSaved

        if not isinstance(totals, dict):
            return
        turn = TimeSaved.from_dict(totals)
        session = TimeSaved.from_dict(self._session_time_saved.get(session_id) or {})
        # The engine's totals are cumulative for the session — bank the delta only.
        delta = TimeSaved(
            human_minutes=max(0.0, turn.human_minutes - session.human_minutes),
            collab_minutes=max(0.0, turn.collab_minutes - session.collab_minutes),
            turns=max(0, turn.turns - session.turns),
            approvals=max(0, turn.approvals - session.approvals),
            by_category={
                k: max(0.0, v - session.by_category.get(k, 0.0))
                for k, v in turn.by_category.items()
            },
            by_tool={
                k: max(0.0, v - session.by_tool.get(k, 0.0))
                for k, v in turn.by_tool.items()
            },
            tool_categories=dict(turn.tool_categories),
        )
        # Growth = work that is new and very different (see edge.py). The engine
        # cannot judge that — a session does not know what the account has done
        # before — so the install-wide test lives here, where the seen set does.
        self._attribute_growth(delta)
        # Five A's counts ride the same event and bank the same way — the delta since
        # this session last reported, so a reconnect can't double-count a turn.
        turn_five = totals.get("five_a") if isinstance(totals.get("five_a"), dict) else {}
        seen_five = (self._session_time_saved.get(session_id) or {}).get("five_a") or {}
        five_delta = {
            level: max(0, int(count) - int(seen_five.get(level, 0)))
            for level, count in turn_five.items()
            if isinstance(count, (int, float))
        }

        banked = turn.as_dict()
        banked["five_a"] = dict(turn_five)
        # Bank the raw (pre-relabel) totals: the delta is computed against these
        # next turn, and moving minutes into Growth here would make the next
        # subtraction see a category that never existed on the engine's side.
        self._session_time_saved[session_id] = banked

        total = TimeSaved.from_dict(self._prefs.get("time_saved") or {})
        total.merge(delta)
        stored = total.as_dict()
        running_five = dict(self._prefs.get("five_a") or {})
        for level, count in five_delta.items():
            if count:
                running_five[level] = int(running_five.get(level, 0)) + count
        self._prefs["five_a"] = running_five
        self._prefs["time_saved"] = stored
        self._save_prefs()

    _RELEASES_CACHE: dict[str, Any] = {}

    def about(self) -> dict[str, Any]:
        """What a user needs to believe this app is alive and will stay current.

        The three questions someone asks a week after installing — is it still being
        worked on, will my models fall behind, who is behind this — answered with
        EVIDENCE rather than adjectives: the real release history with real dates,
        the real size of the model catalogue, and a named maintainer. A claim the
        user can check is worth ten they have to take on faith.

        The release list comes from the same GitHub host the updater already
        contacts on launch, so it exposes nothing new, is fetched only when the
        panel is opened, cached for an hour, and fails to an empty list — an
        offline user sees the local facts, never an error.
        """
        import time as _time

        from ..providers.matrix import MATRIX

        version = ""
        try:  # the shell's version, written into the bundle at build time
            from .. import __version__ as _v

            version = str(_v)
        except Exception:
            version = ""
        providers = sorted({k.split(":")[0] for k in MATRIX if ":" in k})
        cached = self._RELEASES_CACHE
        fresh = cached.get("at", 0) and (_time.time() - cached["at"] < 3600)
        releases = cached.get("rows", []) if fresh else self._fetch_releases()
        return {
            "version": version,
            "models": len(MATRIX),
            "providers": len(providers),
            "releases": releases,
            "maintainer": "Shubin Yu, HEC Paris",
            "repo_url": "https://github.com/lanceyuu/mimiwork",
            "tutorial_url": "https://github.com/lanceyuu/mimiwork#the-ten-minute-tutorial",
        }

    def _fetch_releases(self) -> list[dict[str, Any]]:
        """The five most recent published releases: tag, date, title. Soft-fails."""
        import json as _json
        import time as _time
        from urllib import request

        rows: list[dict[str, Any]] = []
        try:
            req = request.Request(
                "https://api.github.com/repos/lanceyuu/mimiwork/releases?per_page=5",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "MimiWork"},
            )
            with request.urlopen(req, timeout=6) as r:
                for item in _json.load(r):
                    if not isinstance(item, dict) or item.get("draft"):
                        continue
                    rows.append(
                        {
                            "tag": str(item.get("tag_name") or ""),
                            "name": str(item.get("name") or ""),
                            "published_at": str(item.get("published_at") or ""),
                        }
                    )
        except Exception:
            return self._RELEASES_CACHE.get("rows", [])  # keep the last good answer
        self._RELEASES_CACHE = {"rows": rows, "at": _time.time()}
        return rows

    def time_saved_total(self) -> dict[str, Any]:
        """The install's all-time estimate, for the badge next to the logo — plus the
        EDGE profile, which is the same minutes grouped by what KIND of help they
        were (see edge.py). Derived here rather than stored, so it is correct for
        work done before the profile existed."""
        from ..edge import profile
        from ..fivea import profile as five_a_profile
        from ..timesaved import TimeSaved

        totals = TimeSaved.from_dict(self._prefs.get("time_saved") or {}).as_dict()
        totals["edge"] = profile(totals.get("by_category"))
        # Which of the Five A's the account works in (ch. 7) — counts, not minutes:
        # a mode of working is a choice made once per turn.
        totals["five_a"] = five_a_profile(self._prefs.get("five_a"))
        return totals

    def set_language(self, value: str) -> dict[str, Any]:
        """The app's display language (en/zh/no/fr) — a UI pref, stored so every
        window and the next launch agree."""
        value = str(value or "en").lower()
        if value not in ("en", "zh", "no", "fr"):
            return {"ok": False, "error": "language must be one of en, zh, no, fr"}
        self._prefs["language"] = value
        self._save_prefs()
        return {"ok": True, "language": value}

    def set_tour_seen(self, value: bool = True) -> dict[str, Any]:
        """Record that the first-run tour was shown (or replayed and dismissed)."""
        self._prefs["tour_seen"] = bool(value)
        self._save_prefs()
        return {"ok": True, "tour_seen": bool(value)}

    def set_onboarded(self, value: bool = True) -> dict[str, Any]:
        """Record that first-run setup is complete (so it isn't shown again)."""
        self._prefs["onboarded"] = bool(value)
        self._save_prefs()
        return {"ok": True, "onboarded": bool(value)}

    def set_scratch_base(self, path: str) -> dict[str, Any]:
        """Set + persist the common area where each Cowork conversation's scratch directory is
        created (default ~/MimiWork). The raw value is stored so the UI shows it as entered;
        new conversations use it immediately (existing ones keep their provisioned dir).
        """
        path = (path or "").strip()
        if not path:
            return {"ok": False, "error": "empty path"}
        try:
            Path(path).expanduser().mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        self._prefs["scratch_base"] = path
        self._save_prefs()
        return {"ok": True, **self.get_settings()}

    # -- the default working folder ---------------------------------------------
    # Folder access is per session (`sessions.extra_roots`), so onboarding's pick reached
    # exactly the conversation it created and every later one started blind — 139
    # conversations in the owner's store, 3 of which had ever been granted a folder
    # (2026-09-02: "even i have already set the folder at the beginning"). One remembered
    # folder closes that without widening Mimi's reach: seeded into NEW conversations only,
    # never back-filled, and one-off grants stay one-off.
    def default_folder(self) -> Optional[dict[str, Any]]:
        """The folder handed over for good, or None. Absent path = never set."""
        raw = self._prefs.get("default_folder")
        if not isinstance(raw, dict):
            return None
        path = str(raw.get("path") or "").strip()
        if not path:
            return None
        # Always read-write (owner ask 2026-09-02): the folder you hand Mimi for good is
        # where her work goes, and a read-only home is a temp dir by another name.
        return {"path": path, "writable": True}

    def set_default_folder(self, path: str, writable: bool = True) -> dict[str, Any]:
        """Remember this folder for new conversations. An empty path clears it."""
        path = (path or "").strip()
        if not path:
            return self.clear_default_folder()
        p = Path(path).expanduser()
        if not p.is_dir():
            return {"ok": False, "error": f"not a directory: {path}"}
        resolved = p.resolve()
        self._prefs["default_folder"] = {
            "path": str(resolved),
            "writable": bool(writable),
        }
        self._save_prefs()
        self.session_store.touch_workspace(str(resolved))
        return {"ok": True, **self.get_settings()}

    def clear_default_folder(self) -> dict[str, Any]:
        self._prefs.pop("default_folder", None)
        self._save_prefs()
        return {"ok": True, **self.get_settings()}

    def _default_root_seed(self) -> list[dict[str, Any]]:
        """The remembered folder as an extra-root row — empty when unset or since deleted.
        A folder that moved between launches must be skipped, never fatal."""
        folder = self.default_folder()
        if not folder:
            return []
        p = Path(folder["path"]).expanduser()
        if not p.is_dir():
            return []
        return [
            {"path": str(p), "writable": bool(folder["writable"]), "label": p.name}
        ]

    def _with_default_folder(self, extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Seed a NEW conversation's folders. An explicit grant of the same folder wins,
        so the remembered one is dropped rather than duplicated."""
        have = set()
        for r in extra:
            try:
                have.add(Path(str(r.get("path", ""))).expanduser().resolve())
            except OSError:
                continue
        return [
            s for s in self._default_root_seed() if Path(s["path"]) not in have
        ] + list(extra)

    # -- gateway + connector allow-list (inbound messaging) ---------------------
    def allow_user(
        self,
        name: str,
        user_id: str,
        team_id: Optional[str] = None,
        *,
        display_name: str = "",
    ) -> dict[str, Any]:
        out = self._set_allowed(name, user_id, team_id=team_id, add=True)
        # Directory picks arrive with the name in hand — record it so the chip
        # is readable immediately (message-driven allows learn it on arrival).
        if out.get("ok") and display_name:
            self._note_person(name, user_id, display_name)
        return out

    def disallow_user(
        self, name: str, user_id: str, team_id: Optional[str] = None
    ) -> dict[str, Any]:
        if name == "slack" and user_id in self.slack_approval_owner_ids(team_id):
            return {
                "ok": False,
                "error": "Remove this person as an approval owner first.",
            }
        return self._set_allowed(name, user_id, team_id=team_id, add=False)

    def slack_approval_owner_ids(self, team_id: Optional[str] = None) -> set[str]:
        """Stable Slack user ids allowed to resolve consequential Inbox prompts.

        Managed relay installs are installer-owned. Manual Socket Mode has no
        human OAuth identity, so its owners are selected explicitly.
        """
        key = f"slack:team:{team_id}" if team_id else "slack:default"
        profile = self.secrets.get(key) or {}
        if team_id:
            installer = str(profile.get("slack_user_id") or "").strip()
            return {installer} if installer else set()
        if profile.get("mode") == "relay":
            return set()
        return {
            str(user_id).strip()
            for user_id in (profile.get("approval_owner_ids") or [])
            if str(user_id).strip()
        }

    def set_slack_approval_owner(
        self, user_id: str, *, add: bool, display_name: str = ""
    ) -> dict[str, Any]:
        """Edit Manual Socket Mode approval owners.

        Owner status implies inbound permission. Relay ownership is derived from
        the OAuth installer and is intentionally not editable here.
        """
        user_id = str(user_id).strip()
        if not user_id:
            return {"ok": False, "error": "user_id required"}
        profile = self.secrets.get("slack:default")
        if not profile:
            return {"ok": False, "error": "Slack is not connected in Manual mode."}
        if profile.get("mode") == "relay" or profile.get("managed"):
            return {
                "ok": False,
                "error": "Relay approval ownership is set by the Slack installer.",
            }

        owners = self.slack_approval_owner_ids()
        if add:
            owners.add(user_id)
        else:
            owners.discard(user_id)
            if not owners and self._has_manual_slack_inbox_binding():
                return {
                    "ok": False,
                    "error": (
                        "Choose another approval owner before removing the last one "
                        "while Slack Inbox routing is active."
                    ),
                }
        profile["approval_owner_ids"] = sorted(owners)
        if add:
            allowed = set(profile.get("allowed_users") or [])
            allowed.add(user_id)
            profile["allowed_users"] = sorted(allowed)
        self.secrets.put("slack:default", profile)
        if display_name:
            self._note_person("slack", user_id, display_name)
        if self.gateway is not None and "slack" in self.gateway.settings:
            self.gateway.settings["slack"].allowed_users = set(
                profile.get("allowed_users") or []
            )
        return {
            "ok": True,
            "approval_owner_ids": sorted(owners),
            "allowed_users": list(profile.get("allowed_users") or []),
        }

    def _has_manual_slack_inbox_binding(self) -> bool:
        for raw in self.inbox_routing.bindings():
            if raw.get("channel") != "slack":
                continue
            team_id, _ = slack_split(str(raw.get("target") or ""))
            if team_id is None:
                return True
        return False

    def _slack_actor_owns_item(
        self,
        item,
        *,
        actor_id: str,
        chat_id: str,
        team_id: Optional[str],
    ) -> bool:
        """Authorize a Slack resolution against both its owner and delivery binding."""
        event_team, event_channel = slack_split(chat_id)
        event_team = team_id or event_team
        binding = self.inbox_routing.binding_for(item.inbox)
        owner_team = event_team
        if binding.channel == "slack":
            owner_team, bound_channel = slack_split(binding.target)
            if owner_team != event_team or bound_channel != event_channel:
                return False
        return bool(actor_id) and actor_id in self.slack_approval_owner_ids(owner_team)

    def set_inbox_binding(
        self, name: str, *, channel: Optional[str], target: str
    ) -> dict[str, Any]:
        """Persist an Inbox transport after validating its approval identity."""
        channel = str(channel or "").strip() or None
        target = str(target or "").strip()
        if channel and not target:
            return {"ok": False, "error": "Choose a destination channel."}
        if channel == "slack":
            settings = load_settings(self.secrets).get("slack")
            if settings is None or not settings.enabled:
                return {"ok": False, "error": "Slack is not connected."}
            team_id, destination = slack_split(target)
            if not destination:
                return {"ok": False, "error": "Choose a destination channel."}
            key = f"slack:team:{team_id}" if team_id else "slack:default"
            if not self.secrets.get(key):
                return {
                    "ok": False,
                    "error": "That Slack workspace is not connected.",
                }
            if not self.slack_approval_owner_ids(team_id):
                return {
                    "ok": False,
                    "error": (
                        "Choose at least one approval owner in Slack settings before "
                        "routing Inbox requests there."
                    ),
                }
        self.inbox_routing.set_binding(name, channel=channel, target=target)
        return {"ok": True, "bindings": self.inbox_routing.bindings()}

    def _set_allowed(
        self, name: str, user_id: str, *, team_id: Optional[str] = None, add: bool
    ) -> dict[str, Any]:
        """Add/remove a sender on the allow-list. With `team_id` the edit targets that
        scope's profile — a workspace's `slack:team:<id>`, or a GitHub App
        installation's `github:install:<id>` (the same per-tenant pattern);
        without, the flat `<name>:default` list (manual single-workspace mode)."""
        user_id = str(user_id).strip()
        if not user_id:
            return {"ok": False, "error": "user_id required"}
        scope = "install" if name == "github" else "team"
        profile_key = f"{name}:{scope}:{team_id}" if team_id else f"{name}:default"
        profile = self.secrets.get(profile_key)
        if not profile:
            return {
                "ok": False,
                "error": (
                    "workspace not connected" if team_id else "connector not connected"
                ),
            }
        allowed = set(profile.get("allowed_users") or [])
        allowed.add(user_id) if add else allowed.discard(user_id)
        profile["allowed_users"] = sorted(allowed)
        self.secrets.put(profile_key, profile)
        # reflect into the live gateway so it takes effect without a restart
        if self.gateway is not None and name in self.gateway.settings:
            if team_id:
                from ..connectors import TeamAuth

                teams = self.gateway.settings[name].teams
                team = teams.setdefault(team_id, TeamAuth())
                team.allowed_users = set(allowed)
            else:
                self.gateway.settings[name].allowed_users = set(allowed)
        return {"ok": True, "allowed_users": sorted(allowed), "team_id": team_id}


    def slack_status(self) -> dict[str, Any]:
        """Slack connection health for the manual Socket Mode workspace (the managed
        relay layers were removed when the hosted relay was dropped)."""
        default = self.secrets.get("slack:default") or {}
        return {
            "ok": True,
            "mode": default.get("mode") or "",
            "connected": bool(default.get("bot_token") and default.get("app_token")),
        }


    def github_status(self) -> dict[str, Any]:
        """GitHub connection health for the manual PAT profile (the managed relay
        layers were removed when the hosted relay was dropped)."""
        default = self.secrets.get("github:default") or {}
        return {"ok": True, "connected": bool(default.get("token"))}

    async def start_gateway(self) -> list[str]:
        """Build the messaging gateway and start enabled listeners. Inbound messages route to
        durable sessions: a channel message to its subscribers, a DM to the designated DM session
        (else parked). Returns the platforms whose listeners came up."""
        self.scheduler.start()  # tick scheduler for automations (independent of connectors)
        return await self._build_and_start_gateway()

    async def refresh_gateway(self) -> list[str]:
        """Hot-reload the messaging listeners with fresh secrets — called after a connector
        connect/disconnect so pasting new tokens takes effect immediately. A platform socket
        (Slack Socket Mode) authenticates at connect time, so new creds mean reopening that
        socket; this replaces the adapters in-process — the sidecar never restarts."""
        await self.stop_gateway()
        started = await self._build_and_start_gateway()
        print(f"[coworker] messaging gateway reloaded: {', '.join(started) or 'none'}")
        return started

    async def _build_and_start_gateway(self) -> list[str]:
        settings = load_settings(self.secrets)
        self.gateway = Gateway(
            secrets=self.secrets,
            settings=settings,
            handler=self._dispatch_inbound,
            reply_resolver=self._resolve_inbox_reply,
            interaction_handler=self._on_interaction,
            on_unauthorized=self._park_unauthorized,
        )
        for platform, st in settings.items():
            if not st.enabled:
                continue
            profile = self.secrets.get(f"{platform}:default") or {}
            adapter = make_adapter(platform, profile, secrets=self.secrets)
            if adapter is not None:
                self.gateway.register(adapter)
        return await self.gateway.start()

    async def stop_gateway(self) -> None:
        if self.gateway is not None:
            await self.gateway.stop()
            self.gateway = None

    # -- unauthorized inbound (parked, §19) --------------------------------------
    def _note_person(
        self, platform: str, user_id: Optional[str], name: Optional[str]
    ) -> None:
        """Remember a sender's display name (persisted) so ID-keyed surfaces — the allow-list
        chips above all — can show who a U07JK… actually is. Best-effort, newest name wins.
        """
        if not user_id or not name:
            return
        key = f"{platform}:{user_id}"
        if self._people.get(key) != name:
            self._people[key] = name
            try:
                self._people_path.write_text(json.dumps(self._people))
            except OSError:
                pass

    async def _park_unauthorized(self, event) -> None:
        """Gateway callback: keep what an unallowed sender said (names already resolved by the
        adapter, best-effort) so the owner can allow-and-deliver without a re-send."""
        s = event.source
        self._note_person(s.platform, s.user_id, s.user_name)
        self.parked.park(
            platform=s.platform,
            chat_id=s.chat_id,
            chat_name=s.chat_name,
            user_id=s.user_id or "?",
            user_name=s.user_name,
            chat_type=s.chat_type,
            thread_id=s.thread_id,
            team_id=s.team_id,
            text=event.text or "",
        )

    async def resolve_unauthorized(
        self, name: str, item_id: str, action: str
    ) -> dict[str, Any]:
        """Resolve one parked message: "dismiss" throws it away; "allow" adds the sender to the
        allow-list (future messages flow); "allow_deliver" also re-injects the parked message
        through the NORMAL inbound path — buffer + subscriptions — as if it just arrived.
        """
        item = self.parked.pop(item_id)
        if item is None or item.platform != name:
            return {"ok": False, "error": "unknown item"}
        if action == "dismiss":
            return {"ok": True}
        if action not in ("allow", "allow_deliver"):
            return {"ok": False, "error": f"unknown action: {action}"}
        allowed = self._set_allowed(name, item.user_id, team_id=item.team_id, add=True)
        if not allowed.get("ok"):
            return allowed
        if action == "allow_deliver":
            from ..connectors import MessageEvent, SessionSource

            event = MessageEvent(
                text=item.text,
                source=SessionSource(
                    platform=item.platform,
                    chat_id=item.chat_id,
                    user_id=item.user_id,
                    user_name=item.user_name,
                    chat_name=item.chat_name,
                    chat_type=item.chat_type,
                    thread_id=item.thread_id,
                    team_id=item.team_id,
                ),
            )
            await self._dispatch_inbound(event)
        return {"ok": True}

    # -- per-session live view --------------------------------------------------
    def register_event_client(self, send_cb: Any) -> None:
        self._event_clients.add(send_cb)

    def unregister_event_client(self, send_cb: Any) -> None:
        self._event_clients.discard(send_cb)

    async def broadcast_event(self, message: dict) -> None:
        """Fan an app-wide event out to every /ws/events socket. Best-effort: a dead
        socket is dropped, never fatal to the caller."""
        for cb in list(self._event_clients):
            try:
                await cb(message)
            except Exception:
                self.unregister_event_client(cb)

    def register_session_client(self, session_id: str, send_cb: Any) -> None:
        self._session_clients.setdefault(session_id, set()).add(send_cb)

    def unregister_session_client(self, session_id: str, send_cb: Any) -> None:
        clients = self._session_clients.get(session_id)
        if clients is not None:
            clients.discard(send_cb)
            if not clients:
                self._session_clients.pop(session_id, None)

    async def broadcast_session(self, session_id: str, message: dict) -> None:
        """Fan a turn event out to every socket viewing this session. Best-effort: a dead socket
        is dropped, never fatal to the turn (delivery is socket-independent)."""
        for cb in list(self._session_clients.get(session_id, ())):
            try:
                await cb(message)
            except Exception:
                self.unregister_session_client(session_id, cb)

    async def aclose(self) -> None:
        await self.scheduler.stop()
        await self.stop_gateway()
        await self.mcp.aclose()
        self.audit_store.close()

    # -- automation (scheduled tasks) -------------------------------------------
    def approval_prompt_data(self, session_id: str, request) -> dict[str, Any]:
        """Extra Inbox-item payload for a parked approval. Always carries the tool name +
        arguments so the GUI can render the same humanized card (§35) it shows live —
        without them a reopened session fell back to the raw 'Run `tool`?' treatment.
        Automation runs additionally carry the owning task + (when the call is eligible)
        the exact target a standing rule would pin: the GUI offers "Allow every time" only
        when both are present — in-app only, never on Slack-mirrored buttons (§25)."""
        from ..permissions import standing_rule_candidate

        data: dict[str, Any] = {
            "tool": request.tool_name,
            "arguments": getattr(request, "arguments", None) or {},
        }
        task = self.task_store.task_for_run_session(session_id)
        if task is None:
            return data
        data.update({"task_id": task.id, "task_title": task.title})
        target = standing_rule_candidate(
            request.tool_name,
            getattr(request, "arguments", None) or {},
            getattr(request, "metadata", None),
        )
        if target:
            data["standing_target"] = target
        return data

    def mint_task_rule(
        self, session_id: str, tool_name: str, arguments: Any, metadata: Any = None
    ) -> bool:
        """Persist a standing rule a human minted via "Allow every time" on a run's
        approval card (§25's retrofit path). Server-side validation, not trust in the
        card: the session must be an automation run and the call must be rule-eligible
        (external risk, declared target argument, non-empty target). Also applies the
        rule to the live engine so the run's next call auto-allows."""
        from ..permissions import standing_rule_candidate

        task = self.task_store.task_for_run_session(session_id)
        if task is None:
            return False
        target = standing_rule_candidate(tool_name, arguments or {}, metadata)
        if not target or not task.add_rule(tool_name, target):
            return False
        self.task_store.save(task)
        engine = self._engines.get(session_id)
        if engine is not None:
            engine.permissions.task_rules.setdefault(tool_name, set()).add(target)
        try:
            self.audit_store.append(
                {
                    "session_id": session_id,
                    "tool": tool_name,
                    "arguments": arguments or {},
                    "stage": "standing_rule_minted",
                    "status": "granted",
                    "reason": f"allow every time: {tool_name} → {target} (task {task.id})",
                }
            )
        except Exception:
            pass
        return True

    def approval_outcome(self, resolution: str, request, session_id: str):
        """Map an approval resolution (from any surface) to an ApprovalOutcome, handling
        the task-persistent "always_task" vocabulary alongside the session-scoped ones.
        """
        from ..engine import ApprovalOutcome

        if resolution == "always_task":
            self.mint_task_rule(
                session_id,
                request.tool_name,
                getattr(request, "arguments", None),
                getattr(request, "metadata", None),
            )
            return ApprovalOutcome.ONCE
        try:
            return ApprovalOutcome(resolution)
        except ValueError:
            pass
        if resolution == "allow":
            return ApprovalOutcome.ONCE
        if resolution == "always":
            return ApprovalOutcome.ALWAYS_TOOL
        return ApprovalOutcome.DENY

    def _scheduled_approver(self, task, session_id: str):
        from ..engine import ApprovalOutcome
        from ..permissions import WRITE_TOOLS

        name_allowed = task.name_allowed_tools()

        async def approver(request):
            # Unattended: auto-allow the deliverable writes (path-scoped to the task
            # workspace) + tools the task allows BY NAME (legacy entries). Target-bound
            # rules never reach here — the permission engine matched them already.
            if request.tool_name in WRITE_TOOLS or request.tool_name in name_allowed:
                return ApprovalOutcome.ONCE
            # Anything else parks in the Inbox and suspends the run (§25 graceful
            # degradation — an ungranted automation still works, it just asks). The item
            # carries the task binding so the in-app card can offer "Allow every time";
            # the Slack mirror renders only Approve/Deny buttons.
            item = self.inbox.add_approval(
                session_id,
                f"Run `{request.tool_name}`?",
                body=_approval_body(request),
                inbox=self.inbox_routing.route_for(session_id, task.agent),
                tool_call_id=getattr(request, "tool_call_id", None),
                data=self.approval_prompt_data(session_id, request),
            )
            if item.state == "pending":
                self.persist_session(session_id)
                await self.mirror_inbox_item(item)
            resolution = await self.inbox.wait(item.id)
            return self.approval_outcome(resolution, request, session_id)

        return approver

    def _seed_task_permissions(self, engine: TurnEngine, task) -> None:
        """Apply a task's standing allowances to an engine: target-bound rules feed the
        permission engine's matcher (connector tools included — the target binding is the
        safety); name-only legacy entries keep their session-allowlist behavior."""
        engine.permissions.task_rules = task.standing_rules()
        for tool in task.name_allowed_tools():
            engine.permissions.allow_tool_for_session(tool)

    def _build_task_engine(self, task, *, session_id: str) -> TurnEngine:
        ag = get_agent(task.agent)
        Path(task.workspace).mkdir(parents=True, exist_ok=True)
        engine = build_engine(
            agent=ag,
            workspace=task.workspace,
            model=task.model or self.model,
            # The task's own permission level (default: ask). In "auto" the engine
            # never consults the approver; in "plan" consequential tools are refused
            # outright and the run produces a proposal instead of acting.
            mode=Mode(task.mode),
            approver=self._scheduled_approver(task, session_id),
            provider=self.provider,
            memory_store=self.memory_store,
            memory_off=not self.memory_settings.enabled,
            memory_saving_enabled=lambda: self.memory_settings.enabled,
            # Callable, not a snapshot: editing your instructions in Settings applies
            # to conversations already open (same reason as the saving switch).
            user_rules=lambda: self.memory_settings.user_rules,
            on_memory_saved=self._memory_saved_notifier(session_id),
            secrets=self.secrets,
            # No scheduling tools inside a scheduled run: the executing agent's job is to DO the
            # task, and instructions that mention timing ("every day at 5:32pm…") otherwise tempt
            # it to create another automation instead of running this one.
            task_store=None,
            session_id=session_id,
            audit_sink=self.audit_store.append,
            # Scheduled runs respect the same per-session connection hierarchy as live sessions:
            # expose only the persona's effective-enabled connectors' tools (§4.3).
            connector_filter=self.effective_connectors(session_id, task.agent),
            skill_filter=lambda sid=session_id, w=task.workspace: (
                self.effective_skill_names(sid, w)
            ),
        )
        self._seed_task_permissions(engine, task)
        self._wire_tool_recovery(engine, session_id)
        return engine

    # -- mirroring inbox items to a bound channel -------------------------------
    async def mirror_inbox_item(self, item) -> None:
        """Mirror an Inbox item to its bound channel. Discrete choices (approve/deny, ask_user
        options) render as BUTTONS — the item id rides in each, so a click resolves it
        unambiguously. Free-text answers aren't offered over messaging (open the app).
        """
        from ..interactions import buttons_for

        binding = self.inbox_routing.binding_for(item.inbox)
        if not (binding.channel and self.gateway is not None):
            return
        if binding.channel == "slack":
            team_id, _ = slack_split(binding.target)
            # Legacy bindings may predate approval ownership. Keep the item
            # available in-app, but never mirror it to an ownerless channel.
            if not self.slack_approval_owner_ids(team_id):
                return
        target = f"{binding.channel}:{binding.target}"
        body = "\n".join(p for p in (item.title, item.body) if p).strip()
        buttons = buttons_for(item)
        try:
            if buttons:
                await self.gateway.deliver_interactive(target, body, buttons)
            else:
                await self.gateway.deliver(
                    target,
                    f"{body}\n(Open the app to respond.)\n[ow:{item.id}]".strip(),
                )
        except Exception:
            pass

    # -- interactive prompt buttons (Slack/Telegram) ----------------------------
    async def _on_interaction(self, event) -> None:
        """A button click on a mirrored Inbox prompt. The button value carries the item id + the
        resolution, so this is unambiguous — resolve the item, then swap the buttons for the
        outcome. Resolving releases any agent suspended on it (first-responder-wins)."""
        from ..interactions import decode

        decoded = decode(getattr(event, "value", "") or "")
        if decoded is None:
            return
        item_id, resolution = decoded
        item = self.inbox.get(item_id)
        if item is None:
            return
        protected_kinds = {"approval", "directory", "plan"}
        if (
            getattr(event, "platform", "") == "slack"
            and item.kind in protected_kinds
        ):
            actor_id = str(getattr(event, "user_id", "") or "")
            if not self._slack_actor_owns_item(
                item,
                actor_id=actor_id,
                chat_id=getattr(event, "chat_id", "") or "",
                team_id=getattr(event, "team_id", None),
            ):
                if self.gateway is not None:
                    await self.gateway.reject_interaction(event)
                return
        already = item is not None and item.state != "pending"
        resolved = await self.resolve_inbox(item_id, resolution)
        if not resolved and not already:
            return
        who = getattr(event, "user_name", None) or "someone"
        title = item.title
        outcome = "already resolved" if already else f"“{resolution}” — by {who}"
        if self.gateway is not None and getattr(event, "message_id", None):
            try:
                await self.gateway.update_message(
                    getattr(event, "platform", "slack"),
                    getattr(event, "chat_id", ""),
                    event.message_id,
                    f"{title}\n✅ {outcome}",
                )
            except Exception:
                pass

    # -- inbox replies over messaging connectors --------------------------------
    def _resolve_inbox_reply(self, event) -> bool:
        """Try to handle an inbound Slack/Telegram message as an Inbox reply. Returns True if the
        message carried an `[ow:<id>]` token (so it's consumed here, not routed as a new turn) —
        resolving the item also releases any agent suspended on it."""
        from ..inbox_routing import resolve_from_reply

        text = getattr(event, "text", "") or ""

        def _resolve(item_id: str, resolution: str) -> bool:
            item = self.inbox.get(item_id)
            if item is None:
                return False
            if (
                getattr(event.source, "platform", "") == "slack"
                and item.kind in {"approval", "directory", "plan"}
            ):
                actor_id = str(getattr(event.source, "user_id", "") or "")
                if not self._slack_actor_owns_item(
                    item,
                    actor_id=actor_id,
                    chat_id=getattr(event.source, "chat_id", "") or "",
                    team_id=getattr(event.source, "team_id", None),
                ):
                    return False
            return self.inbox.resolve(item_id, resolution)

        return resolve_from_reply(text, _resolve) is not None

    # -- self-wake resumption ---------------------------------------------------
    async def resume_due_wakes(self) -> int:
        """Resume sessions whose self-wakes are due (called each scheduler tick). A suspended
        agent (it called sleep_for / wake_on / wake_on_event and ended its turn) is re-invoked on
        its own session with a wake message so it continues where it left off. Returns the count.
        """
        resumed = 0
        for wake in self.wakes.due():
            try:
                await self._resume_wake(wake)
                resumed += 1
            except Exception:
                pass
            finally:
                self.wakes.mark_fired(wake.id)
        return resumed

    def mark_running(self, session_id: str) -> None:
        self._running_sessions[session_id] = time.time()
        self._announce_activity()

    def try_mark_running(self, session_id: str) -> bool:
        """Atomically claim an idle session for one turn on the server event loop."""
        if session_id in self._running_sessions:
            return False
        self._running_sessions[session_id] = time.time()
        self._announce_activity()
        return True

    def mark_idle(self, session_id: str) -> None:
        self._running_sessions.pop(session_id, None)
        self._announce_activity()
        # Every turn path (WS, background delivery, durable resume) marks idle when it
        # finishes — the one shared post-turn moment, so auto-titling hooks in here and
        # can never add latency to the response itself.
        self._maybe_autotitle(session_id)

    def activity(self) -> dict[str, Any]:
        """App-wide busy snapshot — what the floating Mimi companion renders.
        `detail` names the work when it has a name (an automation title);
        `pending_input` counts parked items that need the USER (approvals,
        questions, folder requests, plans — not mere notifications)."""
        from ..inbox import KIND_NOTIFICATION

        pending = [
            i for i in self.inbox.pending() if i.kind != KIND_NOTIFICATION
        ]
        # Mission-control rows: everything live, one dict each. Session titles come
        # from the store's indexed row (a session mid-FIRST-turn has no row yet →
        # fall back to a generic label).
        items: list[dict[str, Any]] = []
        for sid, started in sorted(
            self._running_sessions.items(), key=lambda kv: kv[1]
        ):
            summary = self.session_store.summary(sid) or {}
            items.append(
                {
                    "kind": "session",
                    "id": sid,
                    "title": summary.get("title") or "New session",
                    "workspace": summary.get("workspace", ""),
                    "agent": summary.get("agent", "cowork"),
                    "started_at": started,
                }
            )
        for info in self._active_automation_info:
            items.append(
                {
                    "kind": "automation",
                    "id": info["id"],
                    "title": info["title"],
                    "started_at": info["started_at"],
                }
            )
        for item in pending:
            items.append(
                {
                    "kind": "approval",
                    "id": item.id,
                    "title": item.title,
                    "session_id": item.session_id,
                }
            )
        return {
            "busy": bool(self._running_sessions) or self._active_automation_runs > 0,
            "running_sessions": len(self._running_sessions),
            "running_automations": self._active_automation_runs,
            "pending_input": len(pending),
            "detail": self._active_automation_titles[0] if self._active_automation_titles else None,
            "items": items,
        }

    def _announce_activity(self) -> None:
        """Push an `activity` frame on /ws/events when the busy boolean OR the
        needs-the-user boolean flips (the inbox store's on_change hook routes
        add/resolve here, so the companion's alert is push-latency, not poll).

        Sync-callable from every mark_* path: the broadcast is scheduled on the
        running loop; with no loop (unit tests building a manager outside asyncio)
        the flip is still recorded and GET /v1/activity keeps serving the truth.
        """
        snap = self.activity()
        signal = (snap["busy"], snap["pending_input"] > 0)
        if signal == self._activity_busy:
            return
        self._activity_busy = signal
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.broadcast_event({"type": "activity", "data": snap}))

    def is_running(self, session_id: str) -> bool:
        return session_id in self._running_sessions

    def fork_session(self, session_id: str) -> dict[str, Any]:
        """Duplicate a conversation as a new thread (store-level copy). The fork
        loads like any resumed session; nothing about the original changes."""
        new_id = self.session_store.fork(session_id)
        if new_id is None:
            return {"ok": False, "error": "session not found"}
        rec = self.session_store.load(new_id)
        return {
            "ok": True,
            "id": new_id,
            "workspace": rec.workspace if rec else "",
            "agent": (rec.agent if rec else None) or "cowork",
        }

    def interrupt_session(self, session_id: str) -> dict[str, Any]:
        """Stop a running session's turn from OUTSIDE its own socket (mission
        control's stop button) — same request_interrupt the session WS uses."""
        engine = self._engines.get(session_id)
        if engine is None or session_id not in self._running_sessions:
            return {"ok": False, "error": "session is not running"}
        engine.request_interrupt()
        return {"ok": True}

    async def _resume_wake(self, wake) -> None:
        await self.deliver_to_session(wake.session_id, self._wake_message(wake))

    async def deliver_to_session(
        self, session_id: str, message: str, *, source: Optional[dict[str, Any]] = None
    ) -> None:
        """Deliver an out-of-band message to a (durable) session — the agent stays resumable
        forever, so this works with no live socket. Busy (mid tool-loop): steer it into the live
        turn at its next step (don't start a colliding run). Idle: run a fresh background turn
        (results persist; if the session is Unattended, any approvals route to the Inbox). Shared
        by self-wake and channel-subscription delivery. `source` is the display-only MessageSource
        sidecar for connector messages (framed `message` stays the model-facing text).
        """
        engine = self.get_engine(session_id)
        if engine is None:
            return
        if not self.try_mark_running(session_id):
            engine.queue_steering(message, source)
            return
        try:
            async for event in engine.run(message, source=source):
                # Stream every event to any socket viewing this session, so a background turn
                # (channel delivery, self-wake, durable resume) is seen live — not just on reselect.
                await self.broadcast_session(
                    session_id, {"type": event.type.value, "data": event.data}
                )
                # A background turn has no user watching to read an inline error: a dead model or
                # tool failure would otherwise vanish. Log it and park it in the dead-letter store.
                if event.type.value == "error":
                    reason = (event.data or {}).get("error", "unknown error")
                    logger.warning(
                        "background turn failed for %s: %s", session_id, reason
                    )
                    self.unrouted.record(session_id, "-", message, reason=reason)
            self.save(session_id, engine)
        except (
            Exception
        ) as exc:  # an unexpected raise out of the turn must not be swallowed
            logger.warning("background turn crashed for %s: %s", session_id, exc)
            self.unrouted.record(session_id, "-", message, reason=str(exc))
            await self.broadcast_session(
                session_id, {"type": "error", "data": {"error": str(exc)}}
            )
        finally:
            self.mark_idle(session_id)
            await self.broadcast_session(session_id, {"type": "turn_done", "data": {}})

    # -- channel subscriptions (inbound messaging) ------------------------------
    async def _dispatch_inbound(self, event) -> None:
        """Route a non-token inbound message. Channel messages are buffered (for catch-up) and
        fanned out to every subscribed session; a DM (or any non-channel) goes to the user-designated
        DM session (delivered like any background turn) or, if none is set, is parked as unrouted.
        """
        src = event.source
        text = getattr(event, "text", "") or ""
        who = src.user_name or src.user_id or "?"
        channel = f"{src.platform}:{src.chat_id}"  # thread-agnostic channel address
        self._note_person(src.platform, src.user_id, src.user_name)
        # Structured sidecar (display-only) built from the resolved identities on the event — the
        # framed text below stays the model-facing `content`; `ms.text` carries the RAW message.
        ms = MessageSource(
            connector=src.platform,
            kind="channel" if src.chat_type in ("channel", "group") else "dm",
            channel_id=src.chat_id,
            channel_name=src.chat_name or src.chat_id,
            sender_id=src.user_id or "",
            sender_name=src.user_name or src.user_id or "?",
            ts=_inbound_epoch(getattr(event, "message_id", None)),
            text=text,
        )
        if src.chat_type in ("channel", "group"):
            self.channel_buffer.record(
                channel, who, text, name=src.chat_name
            )  # buffer all, even unsubscribed
            subs = self.subscriptions.for_channel(channel)
            # §31 mention router: a direct @-mention of the bot outranks the passive fan-out —
            # subscribed sessions must answer it; an unsubscribed channel spawns (or steers)
            # the per-thread coworker session.
            if getattr(event, "mentions_me", False):
                await self._route_mention(event, ms, subs)
                return
            if subs:
                # Chattiness tiers (§31): untagged channel traffic is judgement-only —
                # silence is the default; the must-respond framing is the mention path's.
                msg = (
                    f"💬 New message on {src.chat_name or channel} from {who}: {text}\n"
                    f"(You're subscribed to this channel but were NOT mentioned. Use your "
                    f"judgement: stay silent unless the message clearly concerns your job and "
                    f"a reply adds real value — most channel chatter needs no response from "
                    f'you. If you do reply, use the send_message tool with target "{channel}".)'
                )
                for sub in subs:
                    # Per-session connection hierarchy (§4.3): a session that has muted this
                    # connector skips delivery — the message is still buffered (above) for catch-up.
                    if not self._inbound_connector_allowed(
                        sub.session_id, src.platform
                    ):
                        continue
                    try:
                        await self.deliver_to_session(
                            sub.session_id, msg, source=ms.to_dict()
                        )
                    except Exception:
                        pass
                return
            return  # channel with no subscribers — nobody is listening
        # DM (or any non-channel): route to the designated session, else park it for visibility.
        dm = self.dm_session()
        if dm and self._inbound_connector_allowed(dm, src.platform):
            await self.deliver_to_session(dm, event.tagged_text(), source=ms.to_dict())
        elif dm:
            # Designated, but this session has muted the connector → park rather than deliver.
            self.unrouted.record(
                src.target, who, text, reason="connector muted for DM session"
            )
        else:
            self.unrouted.record(
                src.target, who, text, reason="no DM session designated"
            )

    # -- mention router (§31) ----------------------------------------------------
    async def _route_mention(self, event, ms: MessageSource, subs) -> None:
        """@MimiWork tagged in a channel. A subscribed (user-connected) coworker owns the channel
        and must answer; otherwise the per-thread coworker session handles it — spawned on the
        first tag, steered by follow-ups (deduped on the thread target)."""
        from ..connectors.base import format_target

        src = event.source
        # Slack semantics: replying to a top-level message threads on THAT message's ts, so a
        # top-level tag (no thread_ts) keys — and is answered — on its own ts.
        thread_key = src.thread_id or getattr(event, "message_id", None)
        thread_target = format_target(src.platform, src.chat_id, thread_key)
        who = src.user_name or src.user_id or "?"
        chan = f"#{src.chat_name}" if src.chat_name else src.chat_id
        if subs:
            # The user connected a coworker to this channel — it answers tags; no spawn.
            msg = (
                f"🔔 You were tagged by {who} in {chan}: {event.text}\n"
                f"(You are subscribed to this channel and were mentioned directly — you must "
                f"respond. Reply in the thread with the send_message tool, target "
                f'"{thread_target}".)'
            )
            for sub in subs:
                if not self._inbound_connector_allowed(sub.session_id, src.platform):
                    continue
                try:
                    await self.deliver_to_session(
                        sub.session_id, msg, source=ms.to_dict()
                    )
                except Exception:
                    pass
            return
        sid = self.mention_sessions.get(thread_target)
        if sid and self.session_store.load(sid) is not None:
            # Follow-up tag in a thread we already own → steer the same session.
            msg = (
                f"💬 Follow-up in your Slack thread ({chan}) from {who}: {event.text}\n"
                f'(Reply in the thread with the send_message tool, target "{thread_target}" '
                f"— replies there are pre-approved.)"
            )
            await self.deliver_to_session(sid, msg, source=ms.to_dict())
            return
        await self._spawn_mention_session(event, ms, thread_target)

    async def _spawn_mention_session(
        self, event, ms: MessageSource, thread_target: str
    ) -> None:
        """First tag in a thread: a NEW visible coworker session that owns the thread. Its
        in-thread replies carry a standing grant (§25 shape, exact-target match) so the
        conversation never stalls on an approval nobody in Slack can see; everything else
        asks as usual (approvals park to the Inbox)."""
        import uuid

        src = event.source
        who = src.user_name or src.user_id or "?"
        chan = f"#{src.chat_name}" if src.chat_name else src.chat_id
        sid = uuid.uuid4().hex
        engine = self.get_engine(sid, agent=self.personas.default_id())
        if engine is None:
            self.unrouted.record(
                src.target, who, event.text, reason="could not spawn mention session"
            )
            return
        # Durable mapping FIRST (a fast follow-up tag mid-turn dedupes into steering),
        # then the live grant; get_engine re-derives it from the store on any rebuild.
        self.mention_sessions.set(
            thread_target, sid, channel=f"{src.platform}:{src.chat_id}"
        )
        engine.permissions.task_rules.setdefault("send_message", set()).add(
            thread_target
        )
        self.save(sid, engine)  # the sessions row must exist before rename/set_origin
        # Title = the ASK first, channel last (owner call 2026-07-14): the text is what
        # varies between sessions, so it gets the truncation budget; the mention token is
        # noise (origin is already told by the From Slack group + icon + origin_label).
        ask = re.sub(r"<@[^>]+>", "", event.text or "")
        ask = " ".join(ask.split())[:48]
        self.session_store.rename(sid, f"{ask} — {chan}" if ask else chan)
        label = chan + (f" · {src.team_id}" if src.team_id else "")
        self.session_store.set_origin(sid, src.platform, label)
        # Up to 6 lines of channel context, minus the tag itself (it's the opening line).
        recent = self.channel_buffer.recent(f"{src.platform}:{src.chat_id}", 7)[:-1]
        context = "\n".join(f"- {m['from']}: {m['text']}" for m in recent)
        opening = (
            f"🔔 You were mentioned on Slack in {chan} by {who}: {event.text}\n\n"
            f"You own this Slack thread. Reply in the thread using the send_message tool "
            f'with target "{thread_target}" — replies to this thread are pre-approved and '
            f"never prompt the user. Anything else (other channels, files, external "
            f"actions) asks for approval as usual. Keep replies concise and "
            f"Slack-appropriate."
            + (f"\n\nRecent channel context:\n{context}" if context else "")
        )
        try:
            await self.deliver_to_session(sid, opening, source=ms.to_dict())
        except Exception:
            logger.exception("mention session %s opening turn failed", sid)

    @staticmethod
    def _wake_message(wake) -> str:
        note = f" (note: {wake.note})" if getattr(wake, "note", "") else ""
        if wake.kind == "completion":
            return (
                f"⏰ Wake — the job `{wake.job_id}` you were waiting on has completed{note}. "
                "Continue where you left off."
            )
        if wake.kind == "event":
            return (
                f"⏰ Wake — the event `{wake.event_key}` you were waiting on has fired{note}. "
                "Continue where you left off."
            )
        return (
            f"⏰ Wake — the timer you set has fired{note}. Continue where you left off."
        )

    async def _run_scheduled_task(self, task, trigger: str) -> TaskRun:
        run = TaskRun(
            task_id=task.id, trigger=trigger
        )  # __post_init__ sets run.session_id
        self.task_store.add_run(run)  # mark "running"
        try:
            return await self._drive_scheduled_run(task, run, trigger)
        except Exception as exc:
            # Everything from here to the engine's own try/finally — building the
            # engine, claiming the session, the start broadcast — used to be able to
            # throw straight past the run row we just wrote as "running". The row
            # stayed "running" for ever and the scheduler wrote a SECOND row for the
            # same attempt, which is why a failing automation showed up as endless
            # error/running pairs (owner-hit 2026-08-31). One attempt, one row.
            run.status, run.error = "error", str(exc)
            run.finished_at = _epoch()
            self.task_store.add_run(run)
            return run

    async def _drive_scheduled_run(self, task, run: TaskRun, trigger: str) -> TaskRun:
        self._active_automation_runs += 1
        self._active_automation_titles.append(task.title)
        self._active_automation_info.append(
            {"id": task.id, "title": task.title, "started_at": time.time()}
        )
        self._announce_activity()
        # UX-026: tell every open app window a SCHEDULED run just started (the 5s
        # top-right toast). Manual runs never come through here — the user is
        # already watching those live.
        await self.broadcast_event(
            {
                "type": "automation_run_started",
                "data": {
                    "task_id": task.id,
                    "task_title": task.title,
                    "session_id": run.session_id,
                    "workspace": task.workspace,
                    "agent": task.agent,
                    "trigger": trigger,
                },
            }
        )
        # Each run is a real, persisted conversation thread: it runs the instructions under its
        # own session id, then saves the transcript. The user can reopen that session and ask a
        # follow-up — the scheduled agent is no longer fire-and-forget.
        engine = self._build_task_engine(task, session_id=run.session_id)
        # Tell the engine this turn was started by a schedule, not a person. The
        # classifier has always read this flag and NOTHING ever set it, so the
        # Automation rung was unreachable by construction (owner-hit 2026-08-31).
        engine.turn_scheduled = True
        # Register the live engine up-front: a parked approval persists the session
        # mid-run (durable suspend), and resolving from the Inbox must find this engine.
        self._engines[run.session_id] = engine
        self._retire_finished_run_engines(keep=run.session_id)
        if not self.try_mark_running(run.session_id):
            raise RuntimeError("scheduled run session is already active")
        # The first turn is the task itself. The framing matters: instructions often restate the
        # schedule ("every day at 5:32pm…"), so make explicit that the schedule already fired and
        # the job now is to execute, not to (re)schedule.
        opening = (
            f"⏰ Scheduled run — {task.title}\n\n"
            "This automation is due now: carry out the task below immediately and produce the "
            "result. The schedule already exists — do not create or modify any scheduled tasks.\n\n"
            f"{task.instructions}"
        )
        try:
            async for _event in engine.run(opening):
                pass
            run.result_text = _last_assistant_text(engine.messages)
            run.artifacts = _recent_files(task.workspace, since=run.started_at)
            run.status = "ok"
            # Bank what the run did. Interactive turns bank from the websocket loop in
            # app.py; a scheduled run never goes through it, so its time and its place
            # on the Five A's continuum were both simply lost — the one rung an
            # automation exists to demonstrate never registered.
            try:
                self.record_time_saved(run.session_id, engine.time_saved.as_dict() | {"five_a": dict(engine.five_a)})
            except Exception:
                logger.exception("could not bank the run's totals for %s", task.id)
            if task.notify_on_completion:
                await self._notify_task_done(task, run)
        except Exception as exc:
            run.status, run.error = "error", str(exc)
        finally:
            self.mark_idle(run.session_id)
            run.finished_at = _epoch()
            self._active_automation_runs = max(0, self._active_automation_runs - 1)
            if task.title in self._active_automation_titles:
                self._active_automation_titles.remove(task.title)
            self._active_automation_info = [
                i for i in self._active_automation_info if i["id"] != task.id
            ]
            self._announce_activity()
            # Persist the run as a continuable session + keep the live engine for an immediate
            # follow-up; record the run (now carrying its session_id).
            try:
                self.save(run.session_id, engine)
                self._engines[run.session_id] = engine
                self._retire_finished_run_engines(keep=run.session_id)
            except Exception:
                pass
            self.task_store.add_run(run)
        return run

    # How many finished automation runs keep a live engine in memory. The point of
    # holding one at all is the immediate follow-up: the run finishes, the user opens
    # it and asks "why?" while it is still on screen. A handful covers that. Past it,
    # the engine is just a parked Python kernel and a fistful of open files.
    _RUN_ENGINE_CACHE = 8

    def _retire_finished_run_engines(self, *, keep: str) -> None:
        """Drop all but the newest few finished automation-run engines.

        An automation that runs every few minutes used to add one engine per run and
        never remove one: `__run__` sessions cannot be deleted (delete_session refuses
        `__` ids), so nothing ever evicted them. On a long-lived server that ends as
        "[Errno 24] Too many open files", every subsequent run fails, and — before the
        scheduler fix alongside this — the schedule stopped advancing and retried every
        tick for ever (owner-hit 2026-08-31, hundreds of dead sessions).

        Dropping one is free: the transcript is on disk and `build_engine` rebuilds it
        on the next open. Runs still going are never touched, whatever their age.
        """
        run_ids = [
            sid
            for sid in self._engines
            if sid.startswith("__run__") and sid != keep and not self.is_running(sid)
        ]
        for sid in run_ids[: max(0, len(run_ids) - self._RUN_ENGINE_CACHE)]:
            engine = self._engines.pop(sid, None)
            # Dropping the reference is not enough for the analysis kernel: it is a
            # child process holding pipes, and it outlives the engine unless closed.
            kernel = getattr(engine, "python_kernel", None)
            if kernel is not None:
                try:
                    kernel.close()
                except Exception:
                    logger.exception("could not close the analysis kernel for %s", sid)

    async def _notify_task_done(self, task, run: TaskRun) -> None:
        summary = (run.result_text or "").strip()[:280]
        # Notify any socket viewing this scheduled run's session (it's a durable session of its own).
        await self.broadcast_session(
            run.session_id,
            {
                "type": "task_done",
                "data": {
                    "task": task.title,
                    "id": task.id,
                    "text": summary,
                    "run_id": run.run_id,
                },
            },
        )
        if task.notify_target:
            from ..connectors.base import parse_target
            from ..connectors.senders import DEFAULT_SENDERS

            try:
                platform, chat_id, thread = parse_target(task.notify_target)
                sender = DEFAULT_SENDERS.get(platform)
                creds = self.secrets.get(f"{platform}:default") or {}
                if sender and creds.get("bot_token"):
                    await asyncio.to_thread(
                        sender,
                        creds["bot_token"],
                        chat_id,
                        f"✓ {task.title}\n\n{summary}",
                        thread,
                    )
            except Exception:
                pass

    # -- automation REST --------------------------------------------------------
    def list_automations(self) -> dict[str, Any]:
        # Unseen = runs started after the task's seen mark (UX-023 sidebar badges).
        # `unseen_failed` tints the badge when the NEWEST unseen run errored.
        tasks = []
        for t in self.task_store.list():
            unseen = [
                r for r in self.task_store.runs(t.id) if r.started_at > t.seen_runs_at
            ]
            tasks.append(
                {
                    **t.public(),
                    "unseen_runs": len(unseen),
                    "unseen_failed": bool(unseen) and unseen[0].status == "error",
                }
            )
        return {"tasks": tasks}

    def mark_automation_seen(self, task_id: str) -> dict[str, Any]:
        task = self.task_store.get(task_id)
        if task is None:
            return {"ok": False, "error": "not found"}
        task.seen_runs_at = time.time()
        self.task_store.save(task)
        return {"ok": True}

    def export_automation_blueprint(self, task_id: str) -> dict[str, Any]:
        """Blueprint = the automation's DESIGN, shareable: title, instructions,
        schedule, notify flag, and the grants it wants (as requests, not grants —
        the importer's create form re-renders them and the import submit is the
        §25 consent). Deliberately absent: workspace paths, run history, ids —
        nothing machine- or account-specific. Written to ~/Downloads for easy
        sharing; the JSON also returns for clipboard use."""
        import json as _json
        import re as _re

        task = self.task_store.get(task_id)
        if task is None:
            return {"ok": False, "error": "not found"}
        from ..automation.models import rule_parts

        blueprint = {
            "mimiwork_blueprint": 1,
            "title": task.title,
            "instructions": task.instructions,
            "schedule": task.schedule.to_dict(),
            "notify_on_completion": task.notify_on_completion,
            "permissions": [
                {"tool": t, "target": tg, "access": "write"}
                for t, tg in (rule_parts(e) for e in sorted(set(task.always_allowed_tools)))
                if t and tg
            ],
        }
        slug = _re.sub(r"[^A-Za-z0-9]+", "-", task.title).strip("-").lower() or "automation"
        dest = Path.home() / "Downloads" / f"{slug}.mimiflow.json"
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(_json.dumps(blueprint, indent=2), encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "error": f"could not write blueprint: {exc}"}
        return {"ok": True, "path": str(dest), "blueprint": blueprint}

    def get_automation(self, task_id: str) -> dict[str, Any]:
        task = self.task_store.get(task_id)
        if task is None:
            return {"error": "not found"}
        return {
            "task": task.public(),
            "runs": [r.to_dict() for r in self.task_store.runs(task_id)],
        }

    def create_automation(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create an automation directly from the GUI (the "New automation" / template flow).
        Mirrors the agent-facing `create_scheduled_task` validation, but binds the task to a
        fresh per-task scratch workspace instead of an origin conversation's folder."""
        from croniter import croniter

        title = (payload.get("title") or "").strip()
        instructions = (payload.get("instructions") or "").strip()
        cron = (payload.get("cron") or "").strip() or None
        fire_at = (payload.get("fire_at") or "").strip() or None
        timezone = (payload.get("timezone") or "").strip() or "local"

        if not title:
            return {"ok": False, "error": "title is required"}
        if not instructions:
            return {"ok": False, "error": "instructions are required"}
        if not cron and not fire_at:
            return {
                "ok": False,
                "error": "provide a cron (recurring) or a fire_at ISO datetime (one-time)",
            }
        if cron and not croniter.is_valid(cron):
            return {"ok": False, "error": f"invalid cron expression: {cron}"}

        schedule = Schedule(
            kind="once" if (fire_at and not cron) else "cron",
            cron=cron,
            fire_at=fire_at,
            timezone=timezone,
        )
        from ..automation.models import grant_entries, normalize_mode

        # Optional user-chosen folder: the automation runs THERE (reads the user's
        # real files, writes deliverables next to them) instead of a scratch dir.
        workspace = (payload.get("workspace") or "").strip()
        if workspace:
            ws = Path(workspace).expanduser()
            if not ws.is_dir():
                return {"ok": False, "error": f"folder not found: {workspace}"}
            workspace = str(ws.resolve())

        task = ScheduledTask(
            title=title,
            instructions=instructions,
            schedule=schedule,
            workspace="",
            origin_surface="cowork",
            agent="cowork",
            # Human-driven path (GUI form / onboarding recipes): the creating surface
            # rendered the grants, the submit IS the consent. Same validation as the
            # agent tool — only target-bound write grants survive.
            always_allowed_tools=grant_entries(payload.get("permissions")),
            # Which model answers, and how much it may do without asking. Both are
            # the user's call at creation time; empty model = the app default at
            # run time, so the automation follows the default when it changes.
            model=(payload.get("model") or "").strip() or None,
            mode=normalize_mode(payload.get("mode")),
        )
        task.workspace = workspace or self._provision_scratch(task.task_session_id)

        # Reference files uploaded in the creation form land in <workspace>/attachments
        # so every run can read them. Written before save: a failed write fails creation
        # loudly rather than scheduling a task missing the material it was promised.
        files = payload.get("files") or []
        if files:
            import base64 as _b64
            import binascii as _binascii

            if not isinstance(files, list) or len(files) > 10:
                return {"ok": False, "error": "too many files (limit 10)"}
            dest = Path(task.workspace) / "attachments"
            written: list[str] = []
            for f in files:
                if not isinstance(f, dict):
                    return {"ok": False, "error": "invalid file entry"}
                name = Path(str(f.get("name") or "file")).name  # strip any path parts
                if not name or name.startswith("."):
                    return {"ok": False, "error": f"invalid file name: {f.get('name')!r}"}
                try:
                    data = _b64.b64decode(str(f.get("data_b64") or ""), validate=True)
                except (ValueError, _binascii.Error):
                    return {"ok": False, "error": f"invalid encoding for {name}"}
                if len(data) > 10_000_000:
                    return {"ok": False, "error": f"{name} is too large (limit 10 MB)"}
                try:
                    dest.mkdir(parents=True, exist_ok=True)
                    (dest / name).write_bytes(data)
                except OSError as exc:
                    return {"ok": False, "error": f"could not save {name}: {exc}"}
                written.append(name)
            if written:
                task.instructions += (
                    "\n\nReference files for this automation are in ./attachments/: "
                    + ", ".join(written)
                )

        self.task_store.save(task)
        return {"ok": True, "task": task.public()}

    def update_automation(
        self, task_id: str, changes: dict[str, Any]
    ) -> dict[str, Any]:
        task = self.task_store.get(task_id)
        if task is None:
            return {"ok": False, "error": "not found"}
        if "enabled" in changes:
            task.enabled = bool(changes["enabled"])
        if changes.get("instructions") is not None:
            task.instructions = changes["instructions"]
        if changes.get("title") is not None:
            task.title = changes["title"]
        if changes.get("cron") is not None:
            from croniter import croniter

            if not croniter.is_valid(changes["cron"]):
                return {"ok": False, "error": "invalid cron"}
            task.schedule.cron, task.schedule.kind = changes["cron"], "cron"
        if "model" in changes:
            # "" clears the pin and returns the automation to the app default.
            task.model = (str(changes["model"] or "")).strip() or None
        if changes.get("mode") is not None:
            from ..automation.models import normalize_mode

            task.mode = normalize_mode(changes["mode"], fallback=task.mode)
        if changes.get("revoke"):
            # Revocation from the task detail page ("Allowed without asking … · Revoke").
            # Human-only, like minting; the agent-facing update tool has no such field.
            task.revoke_rule(str(changes["revoke"]))
        self.task_store.save(task)
        if changes.get("revoke"):
            # A live run engine may still hold the revoked rule — reseed from the record.
            for sid, engine in self._engines.items():
                owner = self.task_store.task_for_run_session(sid)
                if owner is not None and owner.id == task.id:
                    engine.permissions.task_rules = task.standing_rules()
        return {"ok": True, "task": task.public()}

    def delete_automation(self, task_id: str) -> dict[str, Any]:
        return {"ok": self.task_store.delete(task_id), "id": task_id}

    def revise_automation(
        self, task_id: str, node: str, comment: str
    ) -> dict[str, Any]:
        """Fold one piece of feedback into the automation's instructions.

        The user clicks a node of the flow diagram ("Saved", "Search the web", …) and
        says what they did not like; the model rewrites the instructions so the next
        run does it their way. One round-trip, no tools, no session — the diagram
        redraws from the new text."""
        task = self.task_store.get(task_id)
        if task is None:
            return {"ok": False, "error": "not found"}
        comment = (comment or "").strip()
        if not comment:
            return {"ok": False, "error": "empty comment"}
        node = (node or "this automation").strip()
        messages = [
            {
                "role": "system",
                "content": (
                    "You maintain the instructions of a scheduled automation. The user "
                    "gives feedback about one part of it. Rewrite the instructions so a "
                    "future run honours the feedback. Keep everything the feedback does "
                    "not touch — wording, order, numbering, file names, commands. Do not "
                    "add commentary. Reply with the complete new instructions only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Automation: {task.title}\n\nCurrent instructions:\n{task.instructions}"
                    f"\n\nFeedback about \u201c{node}\u201d:\n{comment}"
                ),
            },
        ]
        try:
            turn = self.provider.complete(
                model=task.model or self.model, messages=messages, tools=None, max_tokens=4000
            )
        except Exception as e:  # provider down, bad key, …: the text is untouched
            return {"ok": False, "error": str(e) or "the model did not answer"}
        text = (getattr(turn, "text", None) or "").strip()
        if not text:
            return {"ok": False, "error": "the model returned nothing"}
        task.instructions = text
        self.task_store.save(task)
        return {"ok": True, "task": task.public()}

    def prepare_manual_run(self, task_id: str) -> dict[str, Any]:
        """Create a 'running' manual run and return its session, so the GUI can open it and
        drive the task LIVE over the normal session WS (you watch the agent + follow up). The
        automatic scheduler path stays headless (`_run_scheduled_task`)."""
        task = self.task_store.get(task_id)
        if task is None:
            return {"ok": False, "error": "not found"}
        Path(task.workspace).mkdir(parents=True, exist_ok=True)
        run = TaskRun(
            task_id=task.id, trigger="manual"
        )  # status "running", session_id auto
        self.task_store.add_run(run)
        return {
            "ok": True,
            "run_id": run.run_id,
            "session_id": run.session_id,
            "workspace": task.workspace,
            "agent": task.agent,
            # Same execute-now framing as the headless path — manual runs ride a normal live
            # session whose engine DOES have scheduling tools, so be explicit.
            "prompt": (
                f"⏰ Running automation '{task.title}' now. Carry out these instructions "
                "immediately and produce the result. The schedule already exists — do not create "
                f"or modify any scheduled tasks.\n\n{task.instructions}"
            ),
        }

    def finalize_manual_run(self, task_id: str, run_id: str) -> dict[str, Any]:
        """Mark a manual run complete once its first turn finished (the WS already saved the
        session). Pulls result text + artifacts from the persisted transcript/workspace.
        """
        run = next(
            (r for r in self.task_store.runs(task_id) if r.run_id == run_id), None
        )
        task = self.task_store.get(task_id)
        if run is None or task is None:
            return {"ok": False, "error": "not found"}
        if run.status == "running":
            record = self.session_store.load(run.session_id)
            run.result_text = _last_assistant_text(record.messages) if record else None
            run.artifacts = _recent_files(task.workspace, since=run.started_at)
            run.status = "ok"
            run.finished_at = _epoch()
            self.task_store.add_run(run)
            task.last_run, task.last_status = run.finished_at, "ok"
            task.run_count += 1
            self.task_store.save(task)
        return {"ok": True, "run": run.to_dict()}

    def save(self, session_id: str, engine: TurnEngine) -> None:
        executor = getattr(engine, "executor", None)
        workspace = os.path.realpath(str(executor.cwd)) if executor else ""
        self.session_store.save(
            SessionRecord(
                session_id=session_id,
                workspace=workspace,
                model=engine.model,
                mode=engine.permissions.mode.value,
                messages=engine.messages,
                title=title_from(engine.messages),
                agent=getattr(engine, "agent_name", "cowork"),
                extra_roots=self._extra_roots_of(engine),
                grants=_grants_of(engine),
                compaction=(
                    engine.compaction_state.as_dict()
                    if getattr(engine, "compaction_state", None)
                    else {}
                ),
            )
        )

    @staticmethod
    def _apply_grants(engine: TurnEngine, grants: dict[str, Any]) -> None:
        """Re-apply a reloaded session's persisted "Always allow" approvals — they're
        session-scoped, and the session outlives the process (owner-hit 2026-07-22)."""
        for tool in grants.get("tools") or []:
            engine.permissions.allow_tool_for_session(str(tool))
        for command in grants.get("commands") or []:
            engine.permissions.allow_command_for_session(str(command))

    @staticmethod
    def _extra_roots_of(engine: TurnEngine) -> list[dict[str, Any]]:
        """Added folders = the engine's roots minus the primary scratch (index 0)."""
        roots = getattr(engine, "roots", None) or []
        return [
            {"path": str(r.path), "writable": bool(r.writable), "label": r.label}
            for r in roots[1:]
        ]

    # -- LLM auto-titles (FB-010) -------------------------------------------------
    _AUTOTITLE_PROMPT = (
        "You title chat sessions. Given the user's opening message(s), reply with ONLY "
        "a 4-5 word title for the session — no quotes or punctuation wrapping it. If "
        'the opening is merely a greeting or small-talk with no topic ("hey", '
        '"how are you", "hi there"), reply with exactly: small-talk'
    )

    # The re-title, once the session has actually produced something. Titling from the
    # opening alone means a conversation that starts "help me with this" is named after
    # the vague part for ever, however much work followed (owner ask 2026-08-31).
    _RETITLE_PROMPT = (
        "You title chat sessions. Given how a session opened AND what it went on to "
        "produce, reply with ONLY a 4-5 word title — no quotes or punctuation wrapping "
        "it. Name what the session turned out to be ABOUT. Prefer the substance of the "
        "work over the words of the request, and never name the file format."
    )

    def _maybe_autotitle(self, session_id: str) -> None:
        """Kick off title generation after a turn completes, fire-and-forget. Only while
        the session has neither a manual rename nor a generated title, at most twice:
        attempt 1 rides turn 1, and the second window exists solely for the small-talk
        retry (with both openers). Attempts are counted in memory rather than derived
        from the user-message count — steering injections also land as role "user", and
        counting them would silently suppress titling on a steered first turn. A restart
        forgetting the counter is harmless: renamed/auto_title still gate re-titling."""
        if session_id.startswith("__"):
            return
        engine = self._engines.get(session_id)
        if engine is None or session_id in self._autotitle_inflight:
            return
        if self.task_store.task_for_run_session(session_id) is not None:
            return  # automation runs are titled by their task
        if self._autotitle_attempts.get(session_id, 0) >= 2:
            return
        users = [m for m in engine.messages if m.get("role") == "user"]
        if not users:
            return
        state = self.session_store.title_state(session_id)
        if state is None or state["renamed"]:
            return
        if state["auto_title"]:
            # Already titled from the opening. One more pass is allowed, and only once
            # the session has produced something to be named after — a title taken from
            # "help me with this" should not outlive the work that followed.
            self._maybe_retitle_from_content(session_id, engine)
            return
        from ..attachments import content_to_text

        openers = [
            text
            for m in users
            if (text := content_to_text(m.get("content"), image_placeholder="").strip())
        ][:2]
        if not openers:
            return
        self._autotitle_attempts[session_id] = (
            self._autotitle_attempts.get(session_id, 0) + 1
        )
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop to ride (sync caller) — skip, never block
        self._autotitle_inflight.add(session_id)
        # Retain the task: the loop holds only a weak ref, and a GC'd task would both
        # kill the title mid-flight and strand the inflight guard.
        task = loop.create_task(self._generate_autotitle(session_id, engine, openers))
        self._autotitle_tasks.add(task)
        task.add_done_callback(self._autotitle_tasks.discard)

    def _produced_digest(self, session_id: str, engine: TurnEngine) -> str:
        """What this session actually made: the files it produced, plus the last thing it
        said. Names only — a title should come from the substance, and file sizes and
        paths are noise to a model asked for four words."""
        names: list[str] = []
        try:
            names = [
                str(a.get("name") or "")
                for a in self.list_artifacts(session_id)[:6]
                if a.get("name")
            ]
        except Exception:
            names = []
        from ..attachments import content_to_text

        last = ""
        for m in reversed(engine.messages):
            if m.get("role") == "assistant":
                last = content_to_text(m.get("content"), image_placeholder="").strip()
                if last:
                    break
        parts = []
        if names:
            parts.append("Files produced: " + ", ".join(names))
        if last:
            parts.append("Last reply: " + last[:600])
        return "\n".join(parts)

    def _maybe_retitle_from_content(self, session_id: str, engine: TurnEngine) -> None:
        """Re-title once, from what the session produced rather than how it opened.

        Gated on there being something to go on: files produced, or a conversation long
        enough to have a subject. Only ever runs once per session, so a title the user
        has grown used to does not keep moving under them.
        """
        if session_id in self._autotitle_retitled or session_id in self._autotitle_inflight:
            return
        digest = self._produced_digest(session_id, engine)
        if not digest:
            return
        turns = sum(1 for m in engine.messages if m.get("role") == "user")
        has_files = digest.startswith("Files produced:")
        if not has_files and turns < 4:
            return  # nothing produced and barely under way — the opening title still fits
        from ..attachments import content_to_text

        openers = [
            text
            for m in engine.messages
            if m.get("role") == "user"
            and (text := content_to_text(m.get("content"), image_placeholder="").strip())
        ][:1]
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._autotitle_retitled.add(session_id)
        self._autotitle_inflight.add(session_id)
        task = loop.create_task(
            self._generate_autotitle(
                session_id,
                engine,
                openers,
                prompt=self._RETITLE_PROMPT,
                extra=digest,
                overwrite=True,
            )
        )
        self._autotitle_tasks.add(task)
        task.add_done_callback(self._autotitle_tasks.discard)

    async def _generate_autotitle(
        self,
        session_id: str,
        engine: TurnEngine,
        openers: list[str],
        *,
        prompt: Optional[str] = None,
        extra: str = "",
        overwrite: bool = False,
    ) -> None:
        """One cheap non-streaming completion on the session's own provider/model. Every
        failure (provider error, empty, absurdly long) is swallowed — the title_from
        fallback stays; the small-talk sentinel leaves auto_title unset so the turn-2
        retry can run."""
        try:
            turn = await asyncio.to_thread(
                engine.provider.complete,
                model=engine.model,
                messages=[
                    {"role": "system", "content": prompt or self._AUTOTITLE_PROMPT},
                    {
                        "role": "user",
                        "content": "\n\n".join([*openers, extra] if extra else openers),
                    },
                ],
                temperature=0.2,
                # Reasoning-routed models spend hidden tokens BEFORE emitting text; a
                # tight cap plus default effort yields an empty completion and a silent
                # no-op. Effort "none" reaches only the OpenAI-compat path (the native
                # providers whitelist their settings), and 64 leaves headroom either way.
                max_tokens=64,
                reasoning_effort="none",
            )
            raw = (getattr(turn, "text", None) or "").strip()
            # Sanitize: surrounding quotes off, whitespace collapsed, capped at 60.
            title = " ".join(raw.strip("\"'“”‘’`").split())
            # Sentinel tolerance: models riff on the exact token ("Small talk.", quoted,
            # trailing period) — normalize before comparing, else the riff becomes the title.
            if title.lower().strip(".!,;:'\"").replace(" ", "-").replace("_", "-") in (
                "small-talk",
                "smalltalk",
            ):
                return
            if not title or len(title) > 80:
                return
            if self.session_store.set_auto_title(
                session_id, title[:60], overwrite=overwrite
            ):
                # Best-effort nudge for any live viewer; the sidebar's poll and
                # post-turn refresh pick the new title up regardless.
                await self.broadcast_session(
                    session_id,
                    {
                        "type": "session_title",
                        "data": {"session_id": session_id, "title": title[:60]},
                    },
                )
        except Exception:
            # A failed title must never surface as a session error — but it must
            # not be invisible either (a silent provider 400 hid the max_tokens
            # rejection for a whole owner test pass, 2026-07-20).
            logger.debug("autotitle failed for %s", session_id, exc_info=True)
        finally:
            self._autotitle_inflight.discard(session_id)

    # -- session roots (orphan Cowork: scratch + added folders) ------------------
    def get_roots(self, session_id: str) -> list[dict[str, Any]]:
        """The directories this session can touch: primary scratch first, then added folders.
        Reads the live engine when one is running; otherwise reconstructs from persisted state.
        """
        engine = self._engines.get(session_id)
        if engine is not None and getattr(engine, "roots", None):
            return [
                {
                    "path": str(r.path),
                    "writable": bool(r.writable),
                    "label": r.label,
                    "primary": i == 0,
                    "exists": r.path.is_dir(),
                }
                for i, r in enumerate(engine.roots)
            ]
        record = self.session_store.load(session_id)
        primary = (
            record.workspace
            if record and record.workspace
            else self._new_session_workspace(session_id)
        )
        extra = (record.extra_roots if record else []) or []
        if record is None:
            # Brand-new conversation: show what the engine will be built with, so the
            # Access rail is never a promise the agent does not keep.
            extra = self._with_default_folder(list(extra))
        extra = [r for r in extra if not _same_dir(str(r.get("path", "")), primary)]
        out = [
            {
                **self._primary_root(primary),
                "primary": True,
                "exists": Path(primary).is_dir(),
            }
        ]
        for r in extra:
            p = str(r.get("path", ""))
            out.append(
                {
                    "path": p,
                    "writable": bool(r.get("writable", False)),
                    "label": r.get("label") or Path(p).name,
                    "primary": False,
                    "exists": Path(p).is_dir(),
                }
            )
        return out

    def add_root(
        self, session_id: str, path: str, writable: bool = False
    ) -> dict[str, Any]:
        """Grant the session access to another folder (read-only or read-write). Mutates the live
        engine in place when running (file tools + permissions + context see it immediately) and
        persists it so a later resume still has it."""
        p = Path(path).expanduser()
        if not p.is_dir():
            return {"ok": False, "error": f"not a directory: {path}"}
        resolved = p.resolve()
        # A read-write folder handed to a conversation that has not started yet becomes
        # ITS folder — the empty temp dir beside it goes (owner ask 2026-09-02). A
        # conversation with history keeps its folder: relative paths in the transcript
        # and file recovery point at it.
        if writable and not self.is_running(session_id):
            record = self.session_store.load(session_id)
            fresh = record is None or not record.messages
            primary = (
                record.workspace
                if record and record.workspace
                else self._new_session_workspace(session_id)
            )
            if fresh and self._is_scratch_path(primary) and Path(primary).resolve() != resolved:
                return self._adopt_folder(session_id, resolved, primary)
        engine = self._engines.get(session_id)
        if engine is not None and getattr(engine, "roots", None) is not None:
            if any(r.path == resolved for r in engine.roots):
                # already present: just update its access level
                for r in engine.roots:
                    if r.path == resolved:
                        r.writable = bool(writable)
            else:
                engine.roots.append(RootDir(path=resolved, writable=bool(writable)))
            self.session_store.set_extra_roots(session_id, self._extra_roots_of(engine))
        else:
            # Read the folders FIRST: for a brand-new conversation get_roots seeds the
            # remembered default folder, and it can only tell "brand-new" by the record
            # not existing yet. Saving first and reading second dropped the default from
            # any conversation whose first act was a grant from the rail (2026-09-02).
            extra = [r for r in self.get_roots(session_id) if not r["primary"]]
            # A brand-new conversation has no record yet (it's only saved after the first turn) —
            # create one now so set_extra_roots has a row to update and the folder survives.
            if self.session_store.load(session_id) is None:
                self.session_store.save(
                    SessionRecord(
                        session_id=session_id,
                        workspace=self._new_session_workspace(session_id),
                        model=self.model,
                        mode=self.mode.value,
                        messages=[],
                        agent="cowork",  # folder access is a Cowork affordance
                    )
                )
            extra = [r for r in extra if Path(r["path"]).resolve() != resolved]
            extra.append(
                {
                    "path": str(resolved),
                    "writable": bool(writable),
                    "label": resolved.name,
                }
            )
            self.session_store.set_extra_roots(
                session_id,
                [
                    {
                        "path": r["path"],
                        "writable": r["writable"],
                        "label": r.get("label", ""),
                    }
                    for r in extra
                ],
            )
        self.session_store.touch_workspace(str(resolved))
        return {"ok": True, "roots": self.get_roots(session_id)}

    def _adopt_folder(self, session_id: str, folder: Path, scratch: str) -> dict[str, Any]:
        """Make `folder` a not-yet-started conversation's own workspace, dropping the empty
        scratch dir it was provisioned with. The live engine (if any) is evicted; the GUI
        reconnects on the returned `workspace` and the next build lands on the folder."""
        extra = [
            r
            for r in self.get_roots(session_id)
            if not r["primary"] and not _same_dir(r["path"], str(folder))
        ]
        record = self.session_store.load(session_id)
        if record is None:
            self.session_store.save(
                SessionRecord(
                    session_id=session_id,
                    workspace=str(folder),
                    model=self.model,
                    mode=self.mode.value,
                    messages=[],
                    agent="cowork",
                )
            )
        else:
            self.session_store.set_workspace(session_id, str(folder))
        self.session_store.set_extra_roots(
            session_id,
            [{"path": r["path"], "writable": r["writable"], "label": r.get("label", "")} for r in extra],
        )
        self.session_store.touch_workspace(str(folder))
        self._engines.pop(session_id, None)
        try:
            Path(scratch).rmdir()  # only an EMPTY temp dir goes; anything inside stays
        except OSError:
            pass
        return {"ok": True, "roots": self.get_roots(session_id), "workspace": str(folder)}

    def remove_root(self, session_id: str, path: str) -> dict[str, Any]:
        """Revoke a previously-added folder. The primary scratch cannot be removed."""
        resolved = Path(path).expanduser().resolve()
        engine = self._engines.get(session_id)
        if engine is not None and getattr(engine, "roots", None):
            if engine.roots and engine.roots[0].path == resolved:
                return {
                    "ok": False,
                    "error": "cannot remove the primary scratch directory",
                }
            engine.roots[:] = [r for r in engine.roots if r.path != resolved]
            self.session_store.set_extra_roots(session_id, self._extra_roots_of(engine))
        else:
            current = self.get_roots(session_id)
            if (
                current
                and current[0]["primary"]
                and Path(current[0]["path"]).resolve() == resolved
            ):
                return {
                    "ok": False,
                    "error": "cannot remove the primary scratch directory",
                }
            extra = [
                r
                for r in current
                if not r["primary"] and Path(r["path"]).resolve() != resolved
            ]
            self.session_store.set_extra_roots(
                session_id,
                [
                    {
                        "path": r["path"],
                        "writable": r["writable"],
                        "label": r.get("label", ""),
                    }
                    for r in extra
                ],
            )
        return {"ok": True, "roots": self.get_roots(session_id)}

    def session_messages(self, session_id: str) -> list[dict[str, Any]]:
        # A live engine's in-memory thread is authoritative: mid-turn it's ahead of the
        # persisted record — which may not even exist yet for a scheduled run's first turn
        # (opening a "running" automation showed a blank session; owner report 2026-07-04).
        engine = self._engines.get(session_id)
        if engine is not None:
            return list(engine.messages)
        record = self.session_store.load(session_id)
        return record.messages if record else []

    def rename_session(self, session_id: str, title: str) -> dict[str, Any]:
        if session_id.startswith("__"):
            return {"ok": False, "error": "internal sessions cannot be renamed"}
        ok = self.session_store.rename(session_id, title)
        return {
            "ok": ok,
            "session_id": session_id,
            "title": " ".join((title or "").split())[:120],
        }

    def move_session(self, session_id: str, workspace: str) -> dict[str, Any]:
        """Move a conversation into another project folder (sidebar drag-and-drop).

        The folder becomes the session's primary writable root; the previous folder
        stays reachable as an extra root (a scratch conversation's earlier deliverables
        must not vanish). A running session can't be moved mid-turn; an idle one has
        its engine evicted so the next turn rebuilds on the new folder."""
        if session_id.startswith("__"):
            return {"ok": False, "error": "internal sessions cannot be moved"}
        record = self.session_store.load(session_id)
        if record is None:
            return {"ok": False, "error": "not found"}
        target = self.resolve_workspace(workspace)
        if not target:
            return {"ok": False, "error": "that folder does not exist"}
        if self.is_running(session_id):
            return {"ok": False, "error": "the session is busy — move it when it's idle"}
        previous = record.workspace
        if previous and Path(previous).resolve() == Path(target):
            return {"ok": True, "session_id": session_id, "workspace": target, "unchanged": True}
        extra = [dict(r) for r in (record.extra_roots or [])]
        extra = [r for r in extra if str(r.get("path", "")) != target]
        if previous and Path(previous).is_dir() and all(
            str(r.get("path", "")) != previous for r in extra
        ):
            extra.append({"path": previous, "writable": True, "label": "previous folder"})
        self.session_store.set_workspace(session_id, target)
        self.session_store.set_extra_roots(session_id, extra)
        self.session_store.touch_workspace(target)
        self._engines.pop(session_id, None)
        return {"ok": True, "session_id": session_id, "workspace": target}

    def set_session_flags(
        self,
        session_id: str,
        *,
        pinned: Optional[bool] = None,
        archived: Optional[bool] = None,
    ) -> dict[str, Any]:
        if session_id.startswith("__"):
            return {"ok": False, "error": "internal sessions cannot be modified here"}
        ok = self.session_store.set_flags(session_id, pinned=pinned, archived=archived)
        return {"ok": ok, "session_id": session_id}

    def delete_session(self, session_id: str) -> dict[str, Any]:
        if session_id.startswith("__"):
            return {"ok": False, "error": "internal sessions cannot be deleted here"}
        engine = self._engines.pop(session_id, None)
        if engine is not None:
            try:
                # (was engine.interrupt() — a method that never existed; the AttributeError
                # was silently swallowed, so deleting a running session never stopped it.)
                engine.request_interrupt()
            except Exception:
                pass
        record = self.session_store.load(session_id)
        ok = self.session_store.delete(session_id)
        # Deleting a session is the one implicit unsubscribe (otherwise subscriptions are permanent).
        self.subscriptions.remove_session(session_id)
        # ...and releases any Slack threads it owned (§31): the next tag there spawns fresh.
        self.mention_sessions.remove_session(session_id)
        # ...and drops its per-session connector overrides (§4.2, like subscriptions).
        self.session_connections.remove_session(session_id)
        # ...and its per-session skill mutes (SKILLS-SPEC §3 — mutes die with the session).
        self.session_skills.remove_session(session_id)
        # ...and closes its pending Inbox items — an orphaned approval/question can never be
        # meaningfully answered (owner call, 2026-07-03).
        self.inbox.resolve_session(session_id)
        # ...and its scratch dir. STRICTLY scoped: only a directory inside scratch_base is
        # removed — a real project folder the user picked is never touched.
        if ok and record and record.workspace:
            scratch = self.scratch_base().resolve()
            ws = Path(record.workspace)
            try:
                resolved = ws.resolve()
                if (
                    resolved.is_relative_to(scratch)
                    and resolved != scratch
                    and resolved.is_dir()
                ):
                    shutil.rmtree(resolved)
            except OSError:
                pass  # a stale/foreign path must not fail the delete
        return {"ok": ok, "session_id": session_id}

    # -- provider proxy ---------------------------------------------------------
    def provider_complete(self, model, messages, tools=None):
        return self.provider.complete(model=model, messages=messages, tools=tools)

    # -- apps (Mimi-written HTML tools) -------------------------------------------
    def list_apps(self) -> dict[str, Any]:
        return {"apps": [a.public() for a in self.app_store.list()]}

    def get_app(self, app_id: str) -> dict[str, Any]:
        app = self.app_store.get(app_id)
        if app is None:
            return {"ok": False, "error": "not found"}
        return {"ok": True, "app": app.public(), "html": self.app_store.html(app_id)}

    def import_app(self, body: dict[str, Any]) -> dict[str, Any]:
        """A share file or a starter, saved as the user's own app."""
        try:
            app = self.app_store.create(
                title=str(body.get("title") or ""),
                html=str(body.get("html") or ""),
                icon=str(body.get("icon") or "✨"),
                description=str(body.get("description") or ""),
                intro=str(body.get("intro") or ""),
                suggestions=body.get("suggestions"),
            )
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "app": app.public()}

    def update_app(self, app_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        try:
            if changes.get("html") is not None:
                self.app_store.set_html(app_id, str(changes["html"]))
            app = self.app_store.update(
                app_id,
                **{
                    k: changes[k]
                    for k in ("title", "icon", "description", "model", "builder_session", "intro", "suggestions")
                    if k in changes
                },
            )
        except KeyError:
            return {"ok": False, "error": "not found"}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "app": app.public()}

    def delete_app(self, app_id: str) -> dict[str, Any]:
        return {"ok": self.app_store.delete(app_id), "id": app_id}

    def revert_app(self, app_id: str) -> dict[str, Any]:
        """Undo the last change (and undo the undo: the two files swap)."""
        try:
            app = self.app_store.revert(app_id)
        except KeyError:
            return {"ok": False, "error": "not found"}
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "app": app.public(), "html": self.app_store.html(app_id)}

    def app_ask(self, app_id: str, prompt: str, system: str = "") -> dict[str, Any]:
        """The bridge's one model call. Spends credits exactly like a chat turn, on the
        app's pinned model or the app default; no tools, no session."""
        from ..apps.store import MAX_PROMPT

        app = self.app_store.get(app_id)
        if app is None:
            return {"ok": False, "error": "not found"}
        prompt = (prompt or "").strip()
        if not prompt:
            return {"ok": False, "error": "empty prompt"}
        if len(prompt) > MAX_PROMPT or len(system or "") > MAX_PROMPT:
            return {"ok": False, "error": "the prompt is too long (32 KB max)"}
        messages: list[dict[str, Any]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            turn = self.provider.complete(
                model=app.model or self.model, messages=messages, tools=None
            )
        except Exception as e:
            return {"ok": False, "error": str(e) or "the model did not answer"}
        self.app_store.note_ask(app_id)
        return {"ok": True, "text": (getattr(turn, "text", None) or "").strip()}

    def app_state(self, app_id: str) -> dict[str, Any]:
        if self.app_store.get(app_id) is None:
            return {"ok": False, "error": "not found"}
        return {"ok": True, "state": self.app_store.state(app_id)}

    def set_app_state(self, app_id: str, value: Any) -> dict[str, Any]:
        if self.app_store.get(app_id) is None:
            return {"ok": False, "error": "not found"}
        try:
            self.app_store.set_state(app_id, value)
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True}

    def export_app(self, app_id: str) -> dict[str, Any]:
        """One .mimiapp.html in ~/Downloads — the sharing story for this version."""
        import re as _re

        from ..apps.store import pack

        app = self.app_store.get(app_id)
        if app is None:
            return {"ok": False, "error": "not found"}
        slug = _re.sub(r"[^a-z0-9]+", "-", app.title.lower()).strip("-") or app.id
        out_dir = Path.home() / "Downloads"
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            path = out_dir / f"{slug}.mimiapp.html"
            n = 2
            while path.exists():
                path = out_dir / f"{slug}-{n}.mimiapp.html"
                n += 1
            path.write_text(pack(app, self.app_store.html(app_id)), encoding="utf-8")
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(path)}

    # -- manuscript workbench ----------------------------------------------------
    # Proofread + version history for the Files pane's editor. Containment is the
    # same granted-roots rule as workspace_tree/read; the AI call goes through
    # the configured provider (any key the user set, or QualiTaTi credits).

    _PROOFREAD_PROMPT = (
        "You are an expert academic manuscript proofreader. Correct the following "
        "academic text for grammar, clarity, concision, and academic style. Preserve "
        "the author's meaning and citations. Output ONLY JSON:\n"
        '{"revised":"<the fully corrected text>","notes":[{"kind":"grammar|clarity|'
        'style|structure|suggestion","issue":"<problem in the original>","suggestion":'
        '"<how to fix it>"}]}\n'
        "Include up to 12 notes. Do not add markdown fences or commentary."
    )
    _MAX_PROOFREAD_CHARS = 40000

    def manuscript_proofread(
        self,
        path: str,
        workspace: Optional[str] = None,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> dict[str, Any]:
        """Proofread a workspace text file through the configured provider."""
        roots = self._mention_roots(workspace, session_id)
        if not roots:
            return {"error": "no workspace folder is open"}
        target = self._resolve_in_roots(path, roots)
        if target is None or not target.is_file():
            return {"error": f"not a file in this workspace: {path}"}
        try:
            text = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return {"error": f"read failed: {exc}"}
        truncated = len(text) > self._MAX_PROOFREAD_CHARS
        body = text[: self._MAX_PROOFREAD_CHARS]
        try:
            turn = self.provider.complete(
                model=model or self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._PROOFREAD_PROMPT,
                    },
                    {"role": "user", "content": body},
                ],
            )
        except Exception as exc:  # provider not configured / quota / network
            return {"error": f"model call failed: {exc}"}
        content = getattr(getattr(turn, "message", None), "content", "") or ""
        # Tolerate fences/prose around the JSON object.
        start, end = content.find("{"), content.rfind("}")
        parsed: dict[str, Any] = {}
        if start >= 0 and end > start:
            import json as _json

            try:
                parsed = _json.loads(content[start : end + 1])
            except ValueError:
                parsed = {}
        return {
            "path": path,
            "truncated": truncated,
            "revised": str(parsed.get("revised") or "") or None,
            "notes": parsed.get("notes") or [],
            "model": model or self.model,
        }

    def _resolve_in_roots(self, path: str, roots: list[Path]) -> Optional[Path]:
        """Resolve a display path against the granted roots (containment)."""
        rel = (path or "").strip()
        if rel.startswith("root:"):
            head, _, rest = rel.partition("/")
            try:
                idx = int(head.split(":", 1)[1])
            except ValueError:
                idx = 0
            if 0 <= idx < len(roots):
                return (roots[idx] / rest).resolve()
        for r in roots:
            candidate = (r / rel).resolve()
            try:
                candidate.relative_to(r)
            except ValueError:
                continue
            return candidate
        return None

    @staticmethod
    def _versions_paths(target: Path) -> tuple[Path, Path]:
        """(chain file, snapshot dir) — versions live beside the file under
        .versions/, so history travels with the folder it describes."""
        stem = target.name.rsplit(".", 1)[0] if "." in target.name else target.name
        vdir = target.parent / ".versions"
        return vdir / f"{stem}.json", vdir

    def manuscript_versions(
        self,
        path: str,
        workspace: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """List saved version snapshots for a file (newest first)."""
        roots = self._mention_roots(workspace, session_id)
        if not roots:
            return {"error": "no workspace folder is open"}
        target = self._resolve_in_roots(path, roots)
        if target is None:
            return {"error": f"not a file in this workspace: {path}"}
        chain_file, vdir = self._versions_paths(target)
        versions: list[dict[str, Any]] = []
        if chain_file.is_file():
            try:
                import json as _json

                chain = _json.loads(chain_file.read_text(encoding="utf-8"))
                versions = chain.get("versions") or []
            except (OSError, ValueError):
                versions = []
        return {"path": path, "versions": list(reversed(versions))}

    def manuscript_save(
        self,
        path: str,
        content: str,
        label: str = "manual",
        workspace: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Write new content AND snapshot the previous version (editor save).
        Snapshots skip no-op saves (byte-identical to the last snapshot)."""
        roots = self._mention_roots(workspace, session_id)
        if not roots:
            return {"error": "no workspace folder is open"}
        target = self._resolve_in_roots(path, roots)
        if target is None:
            return {"error": f"not a file in this workspace: {path}"}
        chain_file, vdir = self._versions_paths(target)
        import json as _json
        from datetime import datetime, timezone

        try:
            chain = (
                _json.loads(chain_file.read_text(encoding="utf-8"))
                if chain_file.is_file()
                else {"file": path, "versions": []}
            )
        except (OSError, ValueError):
            chain = {"file": path, "versions": []}

        previous = ""
        try:
            previous = target.read_text(encoding="utf-8")
        except OSError:
            previous = ""

        # Skip an identical-content save entirely.
        if previous == content:
            return {"ok": True, "saved": False, "note": "unchanged", "versions": len(chain.get("versions", []))}

        # Snapshot the PREVIOUS content (what is being replaced).
        ts = datetime.now(timezone.utc).isoformat()
        stem = target.name.rsplit(".", 1)[0] if "." in target.name else target.name
        if previous:
            snap = vdir / f"{stem}.{ts.replace(':', '-')}.md"
            vdir.mkdir(parents=True, exist_ok=True)
            snap.write_text(previous, encoding="utf-8")
            chain.setdefault("versions", []).append({"ts": ts, "label": label or "manual"})
            # Keep the newest 20.
            versions = chain["versions"]
            dropped = len(versions) - 20
            if dropped > 0:
                for v in versions[:dropped]:
                    old = vdir / f"{stem}.{v['ts'].replace(':', '-')}.md"
                    try:
                        old.unlink()
                    except OSError:
                        pass
                chain["versions"] = versions[-20:]
            chain_file.parent.mkdir(parents=True, exist_ok=True)
            chain_file.write_text(_json.dumps(chain, indent=2), encoding="utf-8")

        target.write_text(content, encoding="utf-8")
        return {"ok": True, "saved": True, "versions": len(chain.get("versions", []))}

    def manuscript_restore(
        self,
        path: str,
        ts: str,
        workspace: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Restore a snapshot's content (returns it; the caller saves)."""
        roots = self._mention_roots(workspace, session_id)
        if not roots:
            return {"error": "no workspace folder is open"}
        target = self._resolve_in_roots(path, roots)
        if target is None:
            return {"error": f"not a file in this workspace: {path}"}
        chain_file, vdir = self._versions_paths(target)
        stem = target.name.rsplit(".", 1)[0] if "." in target.name else target.name
        snap = vdir / f"{stem}.{ts.replace(':', '-')}.md"
        if not snap.is_file():
            return {"error": f"no snapshot for {ts}"}
        try:
            return {"path": path, "ts": ts, "content": snap.read_text(encoding="utf-8")}
        except OSError as exc:
            return {"error": f"read failed: {exc}"}

    def _refresh_provider(self, name: Optional[str] = None) -> None:
        """Drop the router's cached client(s) so the next turn rebuilds with fresh config.
        No-op for an injected non-router provider (tests)."""
        invalidate = getattr(self.provider, "invalidate", None)
        if callable(invalidate):
            invalidate(name)

    # -- read models ------------------------------------------------------------
    def list_sessions(self, workspace: Optional[str] = None) -> list[dict[str, Any]]:
        ws = self.resolve_workspace(workspace) if workspace else None
        return [
            {
                "session_id": r.session_id,
                "title": r.title or "New session",
                "workspace": r.workspace,
                "agent": r.agent,
                "model": r.model,
                "mode": r.mode,
                "updated_at": r.updated_at,
                "messages": r.message_count,
                "pinned": r.pinned,
                "archived": r.archived,
                # §31: non-user origin ("slack") + display label — drives the sidebar's
                # "From Slack" group and the row's platform icon.
                "origin": r.origin,
                "origin_label": r.origin_label,
                # Which group the user filed this under (null = the flat list).
                "project_id": r.project_id,
                # Attention = Inbox items awaiting this session (the amber count that bubbles
                # session → persona → footer Inbox). Liveness = working (in-flight turn) /
                # sleeping (a self-wake is pending) / idle — a count-less dot that never bubbles.
                "attention": len(self.inbox.pending(session_id=r.session_id)),
                "liveness": self._session_liveness(r.session_id),
                # Channels this session listens to (inbound subscriptions) — drives the per-session
                # "connections" indicator.
                "subscriptions": [
                    s.channel for s in self.subscriptions.for_session(r.session_id)
                ],
            }
            for r in self.session_store.list(workspace=ws)
            if not r.session_id.startswith("__")  # hide internal threads
        ]

    def _session_liveness(self, session_id: str) -> str:
        if self.is_running(session_id):
            return "working"
        if self.wakes.pending(session_id):
            return "sleeping"
        return "idle"

    def list_agents(self) -> list[dict[str, Any]]:
        return _list_agents()

    # -- skills (SKILLS-SPEC §4.4) ------------------------------------------------
    def list_skills(self, workspace: Optional[str] = None) -> list[dict[str, Any]]:
        """Enriched rows for the Settings screen (scope/source/enabled). Optional workspace
        adds that project's skills, with project copies shadowing same-named global ones."""
        return self.skill_store.rows(workspace or None)

    def skill_store_search(
        self, query: str, *, category: str = "", limit: int = 24, offset: int = 0
    ) -> dict[str, Any]:
        """One entry point for both ways into the store: a typed query, or a shelf to
        browse when the box is empty. Rows carry `installed` so the UI can say so, and
        the page carries `total` so it can offer "show more" honestly."""
        from ..skills import marketplace

        page = (
            marketplace.search_page(query, limit=limit, offset=offset)
            if (query or "").strip()
            else marketplace.browse_page(category, limit=limit, offset=offset)
        )
        installed = {r["name"] for r in self.skill_store.rows(None)}
        return {
            **page,
            "category": category if not (query or "").strip() else "",
            "results": [
                {**r, "installed": r["name"] in installed} for r in page["results"]
            ],
        }

    def skill_store_categories(self) -> dict[str, Any]:
        from ..skills import marketplace

        return {"categories": marketplace.categories()}

    def skill_store_preview(self, name: str, repo: Optional[str] = None) -> dict[str, Any]:
        """What this skill would tell the agent to do — read before installing."""
        from ..skills import marketplace

        return marketplace.preview(name, repo or None)

    def skill_store_install(
        self, name: str, repo: Optional[str] = None, force: bool = False
    ) -> dict[str, Any]:
        from ..skills import marketplace

        result = marketplace.install(
            name, self.skill_store.global_dir, repo=repo, force=force
        )
        return result

    def reveal_skill(
        self, name: str, workspace: Optional[str] = None
    ) -> dict[str, Any]:
        """Open the skill's folder in the OS file manager (§6 "Show folder" — the power-user
        window into folder-is-truth). Same local-machine rationale as reveal_artifact."""
        import subprocess
        import sys

        try:
            folder, _scope = self.skill_store.find(name, workspace or None)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        try:
            if sys.platform == "darwin":
                subprocess.Popen(
                    ["open", str(folder)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif sys.platform == "win32":
                import os

                os.startfile(str(folder))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(
                    ["xdg-open", str(folder)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    def effective_skill_names(
        self, session_id: str, workspace: Optional[str | Path] = None
    ) -> set[str]:
        """The session's skill menu (§3): merged scopes − Settings disables − session mutes.
        The single resolver behind the engine catalog, the rail list, and the composer popup."""
        dirs = [self.skill_store.global_dir]
        if workspace:
            dirs.append(self.skill_store.project_dir(workspace))
        loader = SkillLoader(dirs)
        return effective_skills(
            names=set(loader.names()),
            disabled=self.skill_store.disabled_names(),
            session_overrides=self.session_skills.get(session_id),
        )

    def session_skills_view(
        self, session_id: str, workspace: Optional[str] = None
    ) -> dict[str, Any]:
        """The rail payload: every in-scope, Settings-enabled skill with its mute state."""
        disabled = self.skill_store.disabled_names()
        overrides = self.session_skills.get(session_id)
        rows = [
            {
                "name": r["name"],
                "description": r["description"],
                "scope": r["scope"],
                "enabled": overrides.get(r["name"], True),
            }
            for r in self.skill_store.rows(workspace or None)
            if r["name"] not in disabled
        ]
        return {"skills": rows}

    def _scratch_workspace_error(self, workspace: Any) -> Optional[dict[str, Any]]:
        """Refuse skill WRITES into a per-conversation scratch dir — a skill saved there is
        stranded in a throwaway folder. Backend chokepoint: guards every entry path (UI,
        REST, future import), not just the flows the GUI happens to gate."""
        if not workspace:
            return None
        try:
            ws = Path(str(workspace)).expanduser().resolve()
            if ws.is_relative_to(self.scratch_base().resolve()):
                return {
                    "ok": False,
                    "error": (
                        "That folder is a temporary session space — skills saved there "
                        "would be lost. Save it globally or pick a real project."
                    ),
                }
        except OSError:
            pass
        return None

    def create_skill(self, body: dict[str, Any]) -> dict[str, Any]:
        blocked = self._scratch_workspace_error(body.get("workspace"))
        if blocked:
            return blocked
        try:
            created = self.skill_store.create(
                name=str(body.get("name", "")),
                description=str(body.get("description", "")),
                instructions=str(body.get("instructions", "")),
                scope=str(body.get("scope", "global") or "global"),
                workspace=body.get("workspace") or None,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "skill": created}

    def update_skill(self, name: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            if "enabled" in body:
                self.skill_store.set_enabled(name, bool(body["enabled"]))
            if body.get("description") is not None or body.get("instructions") is not None:
                self.skill_store.update(
                    name,
                    description=body.get("description"),
                    instructions=body.get("instructions"),
                    workspace=body.get("workspace") or None,
                )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    def delete_skill(self, name: str, workspace: Optional[str] = None) -> dict[str, Any]:
        try:
            self.skill_store.delete(name, workspace or None)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    def move_skill(self, name: str, body: dict[str, Any]) -> dict[str, Any]:
        # Moving INTO project scope must not target a scratch dir (moving OUT is fine —
        # that's the rescue path for already-stranded skills).
        if str(body.get("scope", "")) == "project":
            blocked = self._scratch_workspace_error(body.get("workspace"))
            if blocked:
                return blocked
        try:
            moved = self.skill_store.move(
                name,
                to_scope=str(body.get("scope", "")),
                workspace=body.get("workspace") or None,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "skill": moved}

    def stage_skill_upload(self, data: bytes, filename: str = "") -> dict[str, Any]:
        try:
            preview = self.skill_store.stage_upload(data, filename)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, **preview}

    def confirm_skill_upload(self, body: dict[str, Any]) -> dict[str, Any]:
        blocked = self._scratch_workspace_error(body.get("workspace"))
        if blocked:
            return blocked
        try:
            saved = self.skill_store.confirm_upload(
                str(body.get("token", "")),
                scope=str(body.get("scope", "global") or "global"),
                workspace=body.get("workspace") or None,
            )
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "skill": saved}

    def _memory_saved_notifier(self, session_id: str):
        """MEMORY-SPEC §5.1: push the memory_saved event that powers the GUI's save
        toast ("I'll remember that — … [Undo]"). Best-effort by design: `remember` may
        run with no socket attached (background runs) or off the loop thread — a lost
        toast never fails the save."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        def notify(item, previous=None) -> None:
            if loop is None or not loop.is_running():
                return
            payload = {
                "type": "memory_saved",
                "data": {
                    "id": item.id,
                    "scope": item.scope.value,
                    "summary": item.summary or "",
                    "content": item.content,
                    # Set when this was an EDIT of an existing memory: the surface says
                    # "I've updated what I remember" and Undo restores this text.
                    "previous": previous or "",
                },
            }
            try:
                asyncio.run_coroutine_threadsafe(
                    self.broadcast_session(session_id, payload), loop
                )
            except RuntimeError:
                pass

        return notify

    def memory_graph(self) -> dict[str, Any]:
        """Obsidian-style graph over all memories: [[links]], #tags, workspace hubs."""
        from ..memory.graph import build_graph

        return build_graph(
            self.memory_store.list(),
            labels=self._workspace_labels(),
            project_names={
                str(p.get("id")): str(p.get("name") or "")
                for p in self.session_store.list_projects()
            },
        )

    def _workspace_labels(self) -> dict[str, str]:
        """A readable name for the folders that only exist because something ran in
        them: a conversation's scratch folder (named after the conversation id) reads
        as the conversation's title, an automation's ``__task__`` folder as the
        automation's. Real folders the user handed over keep their own name."""
        labels: dict[str, str] = {}
        for task in self.task_store.list():
            if task.workspace and Path(task.workspace).name.startswith("__task__"):
                labels[task.workspace] = task.title
        for r in self.session_store.list():
            ws = r.workspace or ""
            if ws and Path(ws).name == r.session_id and r.title:
                labels.setdefault(ws, r.title)
        return labels

    def list_memory(
        self, workspace: Optional[str] = None, project_id: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """All memories, or just one scope's: a folder's, or a project group's."""
        if project_id:
            items = self.memory_store.list(scope=Scope.PROJECT, project_id=project_id)
        elif workspace:
            items = self.memory_store.list(scope=Scope.WORKSPACE, workspace=workspace)
        else:
            items = self.memory_store.list()
        return [
            {
                "id": m.id,
                "scope": m.scope.value,
                "workspace": m.workspace,
                "project_id": m.project_id,
                "content": m.content,
                "summary": m.summary or "",
                "created_at": m.created_at or "",
            }
            for m in items
        ]

    def add_memory(
        self,
        content: str,
        scope: str = "workspace",
        workspace: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> dict[str, Any]:
        content = (content or "").strip()
        if not content:
            return {"ok": False, "error": "content required"}
        chosen = Scope(scope) if scope in _SCOPES else Scope.WORKSPACE
        # A group id makes it the group's fact, whatever word the caller used: the
        # project page has no folder to scope against.
        if project_id:
            chosen = Scope.PROJECT
        ws = self.resolve_workspace(workspace) if chosen is Scope.WORKSPACE else None
        item = self.memory_store.add(
            content,
            scope=chosen,
            workspace=ws,
            project_id=project_id if chosen is Scope.PROJECT else None,
        )
        return {"id": item.id, "scope": item.scope.value, "content": item.content}

    def update_memory(self, item_id: int, content: str) -> dict[str, Any]:
        """Edit-in-place from the memory screen (§5.3). The user rewrote the fact, so
        the stale one-line summary is cleared rather than left contradicting it."""
        content = (content or "").strip()
        if not content:
            return {"ok": False, "error": "content required"}
        item = self.memory_store.update(item_id, content, summary="")
        if item is None:
            return {"ok": False, "error": f"no memory with id {item_id}"}
        return {"ok": True, "id": item.id, "content": item.content}

    def delete_memory(self, item_id: int) -> dict[str, Any]:
        """Row delete on the memory screen — and the toast's Undo (§5.1)."""
        if self.memory_store.delete(item_id):
            return {"ok": True, "id": item_id}
        return {"ok": False, "error": f"no memory with id {item_id}"}

    def delete_all_memory(self) -> dict[str, Any]:
        return {"ok": True, "deleted": self.memory_store.delete_all()}

    def get_memory_settings(self) -> dict[str, Any]:
        return self.memory_settings.snapshot()

    def set_memory_settings(
        self, enabled: Optional[bool] = None, user_rules: Optional[str] = None
    ) -> dict[str, Any]:
        return self.memory_settings.set(enabled=enabled, user_rules=user_rules)


def _parse_inbox_json(s: str) -> dict[str, Any]:
    """Parse a structured Inbox resolution (directory/plan carry their reply as a JSON string)."""
    import json as _json

    try:
        v = _json.loads(s) if s else {}
        return v if isinstance(v, dict) else {}
    except Exception:
        return {}


def _epoch() -> float:
    import time

    return time.time()


# A Slack message ts looks like "1700000001.000001" (epoch seconds + microseconds). Other
# platforms use opaque/incrementing ids (e.g. a Telegram integer), so only parse the Slack shape.
_SLACK_TS_RE = re.compile(r"^\d+\.\d+$")


def _inbound_epoch(message_id: Optional[str]) -> float:
    """Best-effort epoch-seconds for a MessageSource: a Slack-style ts, else wall-clock now."""
    if message_id and _SLACK_TS_RE.match(str(message_id)):
        try:
            return float(message_id)
        except ValueError:
            pass
    return time.time()


def _last_assistant_text(messages: list[dict[str, Any]]) -> Optional[str]:
    for msg in reversed(messages or []):
        if msg.get("role") == "assistant" and msg.get("content"):
            return msg["content"]
    return None


def _recent_files(workspace: str, *, since: float, limit: int = 20) -> list[str]:
    """Files in the task workspace modified during the run — the run's artifacts."""
    out: list[str] = []
    root = Path(workspace)
    if not root.is_dir():
        return out
    for path in root.rglob("*"):
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        try:
            if path.is_file() and path.stat().st_mtime >= since - 1:
                out.append(str(path.relative_to(root)))
        except OSError:
            continue
        if len(out) >= limit:
            break
    return out


def _artifact_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
        return "image"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".xlsx", ".xls"}:
        return "sheet"
    if suffix in {".pptx", ".ppt", ".pptm", ".docx", ".doc", ".docm"}:
        return "office"
    if suffix in {".csv", ".tsv"}:
        return "csv"
    if suffix in {".py", ".js", ".ts", ".tsx", ".css", ".json"}:
        return "code"
    return "text"


def _redact(raw: dict[str, Any]) -> dict[str, Any]:
    """Copy of a server config safe to return over REST — env/header values masked."""
    out = dict(raw)
    for key in ("env", "headers"):
        if isinstance(out.get(key), dict):
            out[key] = {k: ("***" if v else v) for k, v in out[key].items()}
    return out


def _git_branch(path: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=path,
            capture_output=True,
            text=True,
            timeout=3,
        )
        branch = result.stdout.strip()
        return branch or None
    except (OSError, subprocess.SubprocessError):
        return None
