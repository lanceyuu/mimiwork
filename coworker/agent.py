"""Engine assembly from an Agent (Code / Chat / …).

Wires the agent's base tools + permissions + AGENTS.md (workspace agents) + memory +
the skill catalog (progressive disclosure) + load_skill into a TurnEngine.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional

from .agents import Agent, AgentContext, code_agent
from .automation import scheduling_tools
from .config import load_config
from .connectors import (
    connector_list,
    load_settings,
    make_integration_tools,
    make_send_file_tool,
    make_send_message_tool,
)
from .engine import Approver, TurnEngine
from .environment import environment_context
from .memory import (
    MemoryStore,
    Scope,
    format_user_rules,
    memory_tools,
    render_memory_block,
)
from .overrides import RiskOverrideStore
from .permissions import Mode, PermissionEngine
from .project import load_agents_md
from .providers import ProviderClient, ProviderRouter
from .roots import RootDir, normalize_roots, render_context
from .secrets import SecretStore, state_dir
from .selfwake import selfwake_tools
from .skills import SkillLoader, save_skill_tool, skill_catalog_text, skill_tools
from .subscriptions import subscription_tools
from .tools import ToolRegistry
from .tools.ask import ask_user_tool
from .tools.directories import request_directory_tool
from .tools.plan import propose_plan_tool
from .tools.shell import LocalExecutor
from .tools.subagent import explorer_tools
from .tools.todo import TodoList
from .web import make_web_fetch_tool, make_web_search_tool
from .workspace_map import build_workspace_map
from .workspace_trust import WorkspaceTrustStore

# Appended each turn while discuss mode is active: enforcement-only read-only, with no
# pressure toward a plan proposal (that's what distinguishes it from plan mode).
_DISCUSS_MODE_CONTEXT = """\
Discuss mode is active: write and shell tools are disabled. Explore and answer freely; if
the user asks for a change, describe it in chat instead of attempting it (they can switch
to plan or approval mode to have you make it)."""

# Appended to the latest user message every turn while plan mode is active. The mode can
# flip mid-session (plan approval), so this can't live in the static instructions.
_PLAN_MODE_CONTEXT = """\
Plan mode is active: write and shell tools are blocked. Explore read-only and design an
approach. When you've committed to one, present it with `propose_plan` (what you'll change,
in which files, how you'll verify) — don't describe edits as if you were making them. If
the plan is approved, this same session switches to execution and you implement it; if
rejected, revise the plan using the feedback."""

# When-to-remember rules (MEMORY-SPEC §4.2), injected only when a memory store is wired.
# Without these, models either never call `remember` or save noise the repo already
# records. The conservative bias is deliberate: a wrong memory feels broken and creepy at
# once; a missing one merely means the user repeats themselves.
_MEMORY_GUIDANCE = """\
Memory:
- You have persistent memory across sessions. Use `remember` for facts that will still \
matter next week. Scope by what the fact is about: facts about the user -> "global"; \
facts about the current work -> "workspace". Always pass a one-line summary (15 words \
max) alongside the full content.
- Save when you learn something durable, not only when told to. The four that recur:
  (1) a CORRECTION — they tell you something you had wrong about their setup, their \
tools, or how they work. Corrections are durable by nature; save the corrected fact \
with the reason it matters.
  (2) how their WORLD is arranged — their role, their institution, where things live, \
which branch deploys, what a name in their stack refers to.
  (3) a DECISION with a life beyond today — "we use teal, not red", "never push before \
asking", a convention they set.
  (4) a preference they state or demonstrate twice.
- You do not need the words "always" or "from now on". Someone saying "the deploy branch \
is starfish-prod" or "don't build until I say" has told you something durable in \
ordinary language, and failing to save it means asking them again next week — the most \
common way this feature disappoints.
- Still save carefully. A wrong memory costs more than a missing one, so: save the fact, \
not your interpretation of it; skip anything true only for today's task; skip what the \
repo already records (code structure, git history, AGENTS.md); use absolute dates, never \
"yesterday".
- Sensitive topics (health, finances, relationships, beliefs): never save silently. Ask \
first — "Want me to remember this for next time?" — and save only on a yes.
- Before saving, check the known-memories list: if an entry already covers it, revise \
that entry with `memory_update` instead of adding a near-duplicate; retire wrong or \
obsolete entries with `memory_forget`. A correction almost always means an UPDATE to \
something you already believed, not a new row beside it.
- When you save, say so in one short plain sentence in your visible reply ("I'll remember \
that you prefer short replies."). And the first time a remembered fact shapes your \
behavior in a session, note it in one quiet line ("Keeping this short since you prefer \
simple replies.") — first use only, not every message.
- Memories reflect when they were written. If one names a file, flag, or URL, verify it \
still exists before relying on it."""

# Asked once, when a long conversation is about to lose its own history to compaction.
# Memory writes previously depended entirely on the model noticing mid-turn, and the
# measured result was four memories across twenty-one sessions (owner report
# 2026-08-31) — three of them written in the same second, from a single explicit "remember
# this". Compaction is the honest moment to ask: the detail is about to go, so anything
# durable in it has to be saved now or lost. It uses the ordinary tools, so the save
# notice and Undo still apply and nothing is written silently.
MEMORY_CONSOLIDATION_NUDGE = """\
This conversation's earlier detail is about to be condensed. Before it goes: was there \
anything durable here that should outlive it — a correction to something you had wrong, \
how their setup is arranged, a decision with a life beyond today? If so, save it now with \
`remember` (or revise an existing entry with `memory_update`), and say in one line what \
you saved. If there was nothing durable, say nothing and carry on — an empty answer is a \
fine answer."""

# Injected INSTEAD of the memory guidance when the user turned memory off (§4.3).
# Off means "stop LEARNING", not "forget what you know": already-saved memories stay
# injected and usable; only the write tools are gone. Without this notice the model
# bluffs — asked to "remember" with no remember tool, it narrated a fake save through
# its todo list ("I'll remember that your favorite color is blue"), observed live
# 2026-07-28. Honesty needs the model to KNOW saving is off, not just lack the tools.
_MEMORY_OFF_NOTICE = """\
Saving new memories is turned off in this user's Settings. What you already know about \
them (the known-memories list, if any) is still true and you should keep using it — but \
you have no way to save, change, or delete anything, and nothing new from this \
conversation will carry over to future ones. If the user asks you to remember something \
new, state both halves plainly: you'll keep it in mind for the rest of this conversation, \
but it won't be saved once the conversation ends — they can turn saving back on in \
Settings ▸ Memory. Never imply you saved, noted, or will remember anything new."""

# UX-015 (§33): the GUI interleaves these status lines with humanized tool rows inside a
# collapsed "turn" — they're what the user reads while the agent works. Universal (appended
# for every persona); models that ignore it degrade gracefully to a turn with no narration.
_NARRATION_GUIDANCE = """\
Narration: before each batch of tool calls, write ONE short plain sentence saying what \
you're doing and why (e.g. "Checking what merged since yesterday's digest."). It is shown \
to the user as live progress. Don't narrate trivial single-call follow-ups, don't repeat \
the previous line, and never let narration replace your final answer."""


def _enabled_connector_tools(secrets: SecretStore) -> tuple[set[str], set[str]]:
    connectors = {c["name"]: c for c in connector_list(secrets)}
    enabled_connectors = {
        name
        for name, c in connectors.items()
        if c.get("connected") and c.get("enabled")
    }
    enabled_tools = {
        tool["name"]
        for c in connectors.values()
        if c.get("name") in enabled_connectors
        for tool in c.get("tools", [])
        if tool.get("enabled")
    }
    return enabled_connectors, enabled_tools


def _loaded_skill_names(messages: list[dict[str, Any]]) -> set[str]:
    """Skills whose instructions successfully entered THIS conversation (a load_skill call
    with a non-error result). Drives the disable countermand: a menu quietly shrinking is
    passive, but instructions already in history keep steering the model unless it is
    explicitly asked to stop."""
    import json as _json

    results: dict[str, str] = {}
    for m in messages:
        if m.get("role") == "tool" and m.get("tool_call_id"):
            content = m.get("content")
            results[m["tool_call_id"]] = (
                content if isinstance(content, str) else _json.dumps(content)
            )
    loaded: set[str] = set()
    for m in messages:
        if m.get("role") != "assistant" or not m.get("tool_calls"):
            continue
        for tc in m["tool_calls"]:
            fn = tc.get("function") or {}
            if fn.get("name") != "load_skill":
                continue
            try:
                name = str(_json.loads(fn.get("arguments") or "{}").get("name", ""))
            except Exception:
                continue
            result = results.get(tc.get("id", ""), "")
            if name and '"instructions"' in result:
                loaded.add(name)
    return loaded


def _skill_dirs(workspace: Optional[Path]) -> list[Path]:
    # Claude Code's skills (user + project) are an extra source: same folder+SKILL.md format,
    # so they load unchanged. Later dirs override earlier ones on name collisions, so
    # coworker's own dirs come LAST — its skills keep precedence over Claude's.
    dirs: list[Path] = []
    claude_config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    dirs.append(claude_config / "skills")
    dirs.append(state_dir() / "skills")
    if workspace is not None:
        dirs.append(workspace / ".claude" / "skills")
        dirs.append(workspace / ".coworker" / "skills")
    return dirs


def build_engine(
    *,
    agent: Agent,
    workspace: Optional[str | Path] = None,
    model: str = "gpt-5.6-sol",
    mode: Mode = Mode.INTERACTIVE,
    approver: Optional[Approver] = None,
    provider: Optional[ProviderClient] = None,
    allowed_commands: Optional[list[str]] = None,
    max_iterations: Optional[int] = None,
    model_settings: Optional[dict[str, Any]] = None,
    memory_store: Optional[MemoryStore] = None,
    # MEMORY-SPEC §5.1: called with the MemoryItem right after `remember` persists it —
    # the manager uses this to push the memory_saved event that powers the save toast.
    on_memory_saved: Optional[Any] = None,
    # MEMORY-SPEC §6: the user's standing rules (Settings textarea). Injected verbatim
    # above auto memories; independent of the memory on/off switch. No tool writes it.
    # A CALLABLE is read per turn (the server passes one so a Settings edit reaches
    # conversations already open); a plain string is a fixed value for CLI/tests.
    user_rules: Optional[Any] = None,
    # Standing instructions from the session's project GROUP (2026-08-31). A group has
    # no folder, so this arrives as text rather than being read off disk.
    group_instructions: Optional[str] = None,
    # The project GROUP this conversation is filed under. Scopes the memory it starts
    # with, and the memory `remember` writes when the model says "about this project".
    project_id: Optional[str] = None,
    # True when the user turned memory OFF in Settings (vs. memory simply not wired):
    # injects the honesty notice so the model says so instead of faking a save.
    memory_off: bool = False,
    # LIVE saving switch, consulted per write so turning memory off applies to
    # conversations already running (the registry is fixed at build, so the tool stays
    # and refuses). Same pattern as the skills menu's live filter.
    memory_saving_enabled: Optional[Any] = None,
    messages: Optional[list[dict[str, Any]]] = None,
    extra_tools: Optional[list[Any]] = None,
    secrets: Optional[SecretStore] = None,
    task_store: Optional[Any] = None,
    wake_store: Optional[Any] = None,
    session_id: Optional[str] = None,
    audit_sink: Optional[Any] = None,
    roots: Optional[list] = None,
    directory_requester: Optional[Any] = None,
    plan_approver: Optional[Any] = None,
    question_asker: Optional[Any] = None,
    subscription_store: Optional[Any] = None,
    channel_buffer: Optional[Any] = None,
    routing_targets: Optional[list[str]] = None,
    connector_filter: Optional[set[str]] = None,
    # A set (static snapshot) or a zero-arg callable (live, re-evaluated per load_skill).
    skill_filter: Optional[set[str] | Callable[[], set[str]]] = None,
    # Plugin-style tool hooks (opencode-style): pre hooks may short-circuit a tool call,
    # post hooks observe the result. Attached as `engine.hooks` (None by default).
    hooks: Optional[Any] = None,
) -> TurnEngine:
    ws = Path(workspace).expanduser().resolve() if workspace else None
    if agent.needs_workspace and ws is None:
        raise ValueError(f"agent '{agent.name}' requires a workspace")

    # The session's directories. Explicit `roots` (orphan Cowork: scratch + added folders) wins;
    # otherwise the single workspace is the sole writable root. One shared, mutable list flows to
    # the file tools, the permission engine, and the context injector so add/remove is seen by all.
    if roots:
        root_list: list[RootDir] = normalize_roots(roots)
    elif ws is not None:
        root_list = [RootDir(path=ws, writable=True)]
    else:
        root_list = []

    workspace_trusted = bool(ws and WorkspaceTrustStore().is_trusted(ws))
    config = load_config(ws, workspace_trusted=workspace_trusted)
    executor = (
        LocalExecutor(cwd=ws) if (agent.needs_workspace and ws is not None) else None
    )
    todo = TodoList()
    context = AgentContext(
        workspace=ws, executor=executor, todo=todo, roots=root_list or None
    )

    registry = ToolRegistry()
    registry.register_all(agent.build_tools(context))
    # MCP / connector tools (supplied by the manager) carry their own metadata + schema.
    if extra_tools:
        registry.register_all(extra_tools)
    # Messaging personas (Cowork / Ops / MyHelper) expose send_message; MyHelper also uses it as
    # the reply path for inbound Telegram/Slack super-agent sessions.
    secrets = secrets or SecretStore()
    if agent.messaging and any(s.enabled for s in load_settings(secrets).values()):
        registry.register(make_send_message_tool(secrets))
        # send_file (§34): hand deliverables into the chat — same targets, but its OWN
        # approval surface (a thread's standing send_message grant never covers uploads).
        registry.register(
            make_send_file_tool(secrets, workspace=ws, roots=root_list or None)
        )
        # Channel subscriptions (inbound): listen to a channel, catch up, (un)subscribe. The agent
        # obtains a channel via ask_user or from a channel message it's reacting to.
        if subscription_store is not None and channel_buffer is not None and session_id:
            registry.register_all(
                subscription_tools(
                    subscription_store,
                    session_id,
                    channel_buffer,
                    routing_targets=routing_targets,
                )
            )
    # Knowledge surfaces with a multi-root workspace can ask the user mid-task for another folder.
    if agent.family == "knowledge" and root_list:
        registry.register(request_directory_tool())
    if agent.connectors:
        enabled_connectors, enabled_tools = _enabled_connector_tools(secrets)
        # Per-session connection hierarchy (UI-REFRESH §4.3): when the caller supplies the session's
        # effective connector set, intersect it so only effective-enabled connectors expose tools.
        # Default None preserves CLI / direct callers (no per-session restriction).
        if connector_filter is not None:
            enabled_connectors = enabled_connectors & connector_filter
        registry.register_all(
            make_integration_tools(
                secrets,
                enabled_connectors=enabled_connectors,
                enabled_tools=enabled_tools,
                roots=root_list or None,
            )
        )
    # Web search + fetch: research tools for every agent (keyless DuckDuckGo default).
    registry.register(make_web_search_tool(secrets))
    registry.register(make_web_fetch_tool())
    # ask_user: the universal human-in-the-loop Q&A primitive (every agent; engine-intercepted).
    if question_asker is not None:
        registry.register(ask_user_tool())
    # Route by the model's `provider:` prefix (OpenAI default, Ollama, …). The manager normally
    # passes its shared router; this fallback covers the TUI / direct build_engine() callers.
    # Resolved here (not at engine construction) because the explorer subagent captures it.
    provider = provider or ProviderRouter(secrets, default_provider="openai")
    # Code-family personas can fan broad research out to read-only explorer subagents, keeping
    # their own context for the actual change. Knowledge-work coworkers (Cowork) get the same
    # delegation, scoped to their roots.
    if agent.family in ("code", "knowledge") and ws is not None:
        registry.register_all(
            explorer_tools(
                workspace=ws,
                provider=provider,
                model=model,
                model_settings=model_settings,
                roots=root_list or None,
            )
        )
    # Scheduling: knowledge surfaces with a workspace can set up scheduled tasks (origin = this
    # session). Code stays out (it fans out to explorers instead).
    if task_store is not None and ws is not None and agent.family == "knowledge":
        origin = {
            "surface": agent.name,
            "session_id": session_id or "",
            "workspace": str(ws),
            "agent": agent.name,
        }
        registry.register_all(
            scheduling_tools(task_store, origin=origin, default_workspace=str(ws))
        )
    # The signed-in QualiTaTi account's own research data (projects, interviews, surveys).
    # Registered only while signed in — an unusable tool in the catalog is a lie to the
    # model — and every one of them is approval-gated: pulling personal research data off
    # a server is the user's call, each time (owner ask 2026-08-23).
    from .qualitati import AUTH_PROFILE

    _qt = secrets.get(AUTH_PROFILE) or {}
    if isinstance(_qt, dict) and _qt.get("access_token"):
        from .tools.qualitati_data import qualitati_data_tools

        registry.register_all(qualitati_data_tools(secrets, workspace=ws))

    # Custom commands (opencode-style markdown /commands with $ARGUMENTS): project commands
    # under .coworker/commands, user commands under the state dir. Available to any workspace
    # session; the model discovers them via list_commands.
    command_store = None
    if ws is not None:
        from .commands import CommandStore, command_tools

        command_store = CommandStore(
            [ws / ".coworker" / "commands", state_dir() / "commands"]
        )
        registry.register_all(command_tools(command_store))
    # Self-wake: knowledge surfaces can suspend + schedule their own resumption (timer /
    # on-completion / on-event). The scheduler tick resumes due wakes.
    if wake_store is not None and session_id and agent.family == "knowledge":
        registry.register_all(selfwake_tools(wake_store, session_id))

    instructions = f"{agent.system_prompt}\n\n{_NARRATION_GUIDANCE}"
    if ws is not None:
        instructions = f"{instructions}\n\n{environment_context(ws)}"
        # Workspace map: session-start knowledge like the environment block above —
        # a ranked picture of what's in the workspace so the model doesn't spend its
        # first tool calls exploring. Empty workspaces contribute nothing.
        ws_map = build_workspace_map(ws)
        if ws_map:
            instructions = f"{instructions}\n\n{ws_map}"
        conventions = load_agents_md(ws, group_instructions=group_instructions or "")
        if conventions:
            instructions = f"{instructions}\n\n{conventions}"

    # The user's own standing instructions, read once here: like the memories below,
    # they're session-stable knowledge. Edits apply to NEW conversations (the Settings
    # copy says exactly that), never mid-conversation.
    rules_block = format_user_rules(
        (user_rules() if callable(user_rules) else user_rules) or ""
    )
    if rules_block:
        instructions = f"{instructions}\n\n{rules_block}"

    # The live saving switch. The callable (server) beats the build-time flag (CLI/tests):
    # the setting can flip EITHER WAY mid-conversation, so nothing about it may be baked
    # into the fixed registry or the static instructions (owner-hit 2026-07-28, both
    # directions: off kept saving, then on kept claiming it was off).
    def _saving_enabled() -> bool:
        if memory_saving_enabled is not None:
            return bool(memory_saving_enabled())
        return not memory_off

    if memory_store is not None:
        # Always the full toolset: the registry is fixed at build, so a session born
        # while saving was off must still be able to save the moment it's turned on.
        # Enforcement is the tools' own live check, not their absence.
        registry.register_all(
            memory_tools(
                memory_store,
                workspace=str(ws) if ws else None,
                project_id=project_id,
                on_saved=on_memory_saved,
                saving_enabled=_saving_enabled,
            )
        )
        instructions = f"{instructions}\n\n{_MEMORY_GUIDANCE}"
        # What the coworker KNOWS is fixed at session start (MEMORY-SPEC §7.1): a
        # conversation's knowledge must not shift underfoot — a fact it referenced ten
        # turns ago cannot silently vanish — and the system prompt is the cached prefix,
        # so the facts are processed once instead of re-sent every turn. Deletions reach
        # NEW conversations; the UI says so rather than pretending otherwise.
        remembered = memory_store.list(scope=Scope.GLOBAL)
        if ws is not None:
            remembered += memory_store.list(scope=Scope.WORKSPACE, workspace=str(ws))
        block = render_memory_block(remembered)
        if block:
            instructions = f"{instructions}\n\n{block}"

    skill_loader = SkillLoader(_skill_dirs(ws))
    # Per-session effective menu (SKILLS-SPEC §3). The manager passes a CALLABLE so
    # load_skill consults the LIVE state per call (a Settings disable applies to running
    # sessions; a skill created after this build is still loadable). The catalog itself
    # is injected per turn via context_provider (below), NOT here — so the menu the model
    # sees is also live: skill changes apply from the next message, no new session needed.
    # Default None preserves CLI / direct callers.
    registry.register_all(skill_tools(skill_loader, allowed=skill_filter))
    # The worker-authors door (SKILLS-SPEC §5.2): save_skill proposes installing a finished
    # skill; requires_approval routes it through the standard approval card, so the review-
    # before-save rule holds without any bespoke plumbing. Bundled files may only come from
    # this session's roots.
    registry.register(
        save_skill_tool(
            allowed_dirs=[r.path for r in (root_list or [])] or ([ws] if ws else [])
        )
    )

    # User-local risk overrides (mainly to relax MCP's conservative default). Empty store →
    # no-op; never written by persona loading (the no-self-grant rule).
    risk_overrides = RiskOverrideStore(state_dir() / "risk_overrides.json").resolver()
    permissions = PermissionEngine(
        workspace_root=ws or (root_list[0].path if root_list else Path.cwd()),
        mode=mode,
        # `[]` is an explicit deny-by-default override, not a request to fall back to config.
        allowed_commands=(
            allowed_commands if allowed_commands is not None else config.allowed_commands
        ),
        auto_allow_tools=set(config.auto_allow),
        roots=root_list or None,
        risk_overrides=risk_overrides,
    )
    # The plan-mode exit door. Always registered (surfaces can flip a live session into
    # plan mode via set_mode, and the registry is fixed at build); the engine rejects the
    # call whenever the session isn't actually in plan mode.
    registry.register(propose_plan_tool())

    # Per-turn ephemeral context, appended to the latest user message since mid-thread system
    # messages aren't reliable across providers. Three producers: the plan-mode reminder (mode can
    # flip mid-session, so it's checked each turn, not baked into the instructions), the live
    # directory list (orphan Cowork can gain folders mid-session; Cowork/MyHelper only), and the
    # memory-SAVING notice (same reason as plan mode — the switch flips either way mid-chat).
    # Note what is NOT here: the memories and the user's rules. Those are knowledge, fixed at
    # session start (§7.1).
    roots_context = (
        (lambda: render_context(root_list))
        if root_list and agent.family == "knowledge"
        else None
    )

    # Late-bound engine ref: the closure needs the conversation history (for the disable
    # countermand) but the engine is constructed after the closure. Filled below.
    _engine_box: list = []

    def context_provider() -> str:
        parts = []
        if permissions.mode is Mode.PLAN:
            parts.append(_PLAN_MODE_CONTEXT)
        elif permissions.mode is Mode.DISCUSS:
            parts.append(_DISCUSS_MODE_CONTEXT)
        # Only the SAVING switch is per-turn (§4.3): it governs an action, not
        # knowledge, so it must bite the moment the user flips it. What the coworker
        # knows stays fixed for the session — see the instructions built above.
        if memory_store is not None and not _saving_enabled():
            parts.append(_MEMORY_OFF_NOTICE)
        if roots_context is not None:
            ctx = roots_context()
            if ctx:
                parts.append(ctx)
        # Live skill menu (SKILLS-SPEC §4.1): recomputed every turn like the roots list, so
        # a skill installed/enabled/disabled mid-session applies from the NEXT MESSAGE —
        # no new session, no lost context.
        skill_loader.rescan()
        allowed = skill_filter() if callable(skill_filter) else skill_filter
        skills_ctx = skill_catalog_text(skill_loader, allowed=allowed)
        if skills_ctx:
            parts.append(skills_ctx)
        # Disable countermand (§3): instructions already loaded into this conversation keep
        # steering the model even after the skill is turned off/deleted — history can't be
        # un-read. So a loaded-but-no-longer-available skill gets an explicit stop note,
        # recomputed fresh each turn (re-enable → the note disappears; never persisted).
        eng = _engine_box[0] if _engine_box else None
        if eng is not None:
            available = set(skill_loader.names()) if allowed is None else set(allowed)
            for name in sorted(_loaded_skill_names(eng.messages) - available):
                parts.append(
                    f'Note: the skill "{name}" has been disabled by the user — stop '
                    "following its instructions from here on."
                )
        return "\n\n".join(parts)

    engine = TurnEngine(
        provider=provider,
        registry=registry,
        permissions=permissions,
        model=model,
        instructions=instructions,
        approver=approver,
        # Stop kills the in-flight foreground shell command, not just the loop.
        interrupt_hooks=[executor.interrupt_now] if executor is not None else None,
        max_iterations=(
            max_iterations if max_iterations is not None else config.max_iterations
        ),
        model_settings=model_settings,
        messages=messages,
        audit_sink=audit_sink,
        context_provider=context_provider,
        directory_requester=directory_requester,
        plan_approver=plan_approver,
        question_asker=question_asker,
    )
    # Whether this session can save at all — the consolidation nudge at compaction stays
    # quiet when it can't, so it never invites a claim the tools can't back.
    engine.memory_enabled = memory_store is not None and _saving_enabled()
    # Plugin-style pre/post tool hooks (opencode hooks). Attached post-construction so the
    # engine defaults (None) are untouched for engines built without them.
    if hooks is not None:
        engine.hooks = hooks  # type: ignore[attr-defined]
    engine.executor = executor  # type: ignore[attr-defined]
    # Oversized tool output (a wide sheet, a printed dataframe, a large connector payload)
    # is redirected to a file under the workspace instead of consuming the context window.
    # Needs a workspace to write into; without one, results stay verbatim as before.
    if ws is not None:
        from .spill import SpillStore

        engine.spill = SpillStore(Path(ws) / ".coworker" / "spill")
    engine.todo = todo  # type: ignore[attr-defined]
    engine.agent_name = agent.name  # type: ignore[attr-defined]
    engine.roots = root_list  # type: ignore[attr-defined]  # shared list; Slice C mutates in place
    engine.audit_context = {
        "session_id": session_id or "",
        "agent": agent.name,
        "workspace": str(ws) if ws else "",
    }
    engine.skill_loader = skill_loader  # type: ignore[attr-defined]
    engine.command_store = command_store  # type: ignore[attr-defined]  # None for workspace-less
    # Teardown handle for the analysis kernel. It is a live subprocess with open
    # pipes, so letting go of the engine does NOT reclaim it; whoever retires an
    # engine has to close this. python_tools sets it on the context and its comment
    # has always promised this hand-off — until now nothing read it back.
    engine.python_kernel = getattr(context, "python_kernel", None)  # type: ignore[attr-defined]
    _engine_box.append(engine)  # late-bind for the countermand (see context_provider)
    return engine


def build_code_engine(**kwargs: Any) -> TurnEngine:
    """Back-compat shim: build the Code agent's engine."""
    return build_engine(agent=code_agent(), **kwargs)


def build_cowork_engine(**kwargs: Any) -> TurnEngine:
    """Build the Cowork agent's engine (the default surface since the session-type
    consolidation: chat/code sessions are gone, cowork is the one workspace agent)."""
    from .agents import cowork_agent

    return build_engine(agent=cowork_agent(), **kwargs)
