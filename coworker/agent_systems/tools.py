"""Agent-facing tools for the Agents section: design a system, save it, run it.

create / update / list write only under the state dir's ``agent-systems/`` folder, so they
do not gate, like the app tools. run_agent_system ALWAYS asks first: it spends credits on
several models and may start coding agents that change files, and a tool's approval is
fixed when it is registered, not per system.

Inside a run, what the subagents may do is narrower than the chat that started it:
    * Mimi agents work in accept-edits mode: edits inside the granted folders run, while
      commands and anything that leaves the machine go to the Inbox for the person;
    * a review node asks the person through the Inbox question, never through the model,
      so a model cannot approve its own draft.
Both reach the Inbox through the turn's own loop (`tool_loop`), because the run itself
executes in a worker thread with its own short-lived loops.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Callable, Optional

import aisuite as ai

from ..permissions import Mode, PermissionEngine
from ..tools.context import tool_loop, tool_model, tool_progress
from .models import to_mermaid, validate
from .runner import Runner, answer_to_decision, run_summary, worker_prompt_note
from .store import AgentSystemStore

_SYSTEM_SCHEMA = {
    "type": "object",
    "description": (
        "The design. nodes: [{id, kind: agent|coding|router|orchestrator|review, name, "
        "instructions, model (empty = this chat's model), effort: low|medium|high or empty, "
        "tools: capability ids, agent (coding only: claude_code|codex|opencode|cursor|gemini), "
        "folder (coding only), position: {x, y}}]. edges: [{from, to, kind: flow|assign, "
        "label, max_rounds}]. assign = a lead agent's helper. An edge pointing back upstream "
        "needs max_rounds (1-5). A router's edges need distinct labels; a review node's "
        "send-back edge is labelled 'revise'. entry: the id of the agent that starts."
    ),
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "pattern": {"type": "string"},
        "nodes": {"type": "array", "items": {"type": "object"}},
        "edges": {"type": "array", "items": {"type": "object"}},
        "entry": {"type": "string"},
    },
}


def _schema(name: str, description: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": required}}}


def _tool(func: Callable[..., Any], schema: dict[str, Any], *, gated: bool = False) -> Callable[..., Any]:
    func.__name__ = schema["function"]["name"]
    func.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name=schema["function"]["name"],
        category="agents",
        risk_level="high" if gated else "low",
        capabilities=["agents"],
        requires_approval=gated,
    )
    func.__coworker_schema__ = schema
    return func


def _saved(system) -> dict[str, Any]:
    return {"ok": True, "id": system.id, "title": system.title, "problems": validate(system),
            "mermaid": to_mermaid(system),
            "note": "Show the user the mermaid diagram, and say they can edit it under Agents."}


def _on_loop(loop: Any, coro_fn: Callable[..., Any], *args: Any) -> Any:
    """Run an Inbox coroutine on the turn's loop and wait for it from this thread."""
    return asyncio.run_coroutine_threadsafe(coro_fn(*args), loop).result()


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "helper"


def agent_system_tools(
    store: AgentSystemStore,
    *,
    session_id: str = "",
    workspace: Optional[str | Path] = None,
    roots: Optional[list] = None,
    provider: Any = None,
    default_model: str = "",
    approver: Optional[Callable[..., Any]] = None,
    asker: Optional[Callable[..., Any]] = None,
) -> list[Callable[..., Any]]:
    ws = Path(workspace).resolve() if workspace else None

    def create_agent_system(system: dict) -> dict:
        try:
            made = store.create({**(system or {}), "builder_session": session_id})
        except ValueError as e:
            return {"error": str(e)}
        return _saved(made)

    def update_agent_system(id: str, system: dict) -> dict:
        try:
            return _saved(store.update(id, system or {}))
        except KeyError:
            return {"error": f"no agent system with id {id!r}"}
        except ValueError as e:
            return {"error": str(e)}

    def list_agent_systems() -> dict:
        return {"systems": [
            {"id": s.id, "title": s.title, "description": s.description, "pattern": s.pattern,
             "agents": [n["name"] for n in s.nodes]} for s in store.list()]}

    def run_agent_system(system: str, input: str) -> dict:
        found = store.get(system) or next(
            (s for s in store.list() if s.title.lower() == (system or "").strip().lower()), None)
        if found is None:
            return {"error": f"No agent system called {system!r}. Use list_agent_systems."}
        problems = validate(found)
        if problems:
            return {"error": "This system cannot run yet.", "problems": problems}
        if ws is None or provider is None:
            return {"error": "Agent systems run in a conversation with a folder."}
        loop = tool_loop.get()
        report = tool_progress.get() or (lambda _line: None)
        parent_model = tool_model.get() or default_model
        runner = Runner(
            found,
            call_agent=_agent_caller(found.title, provider, parent_model, ws, roots, approver, loop),
            call_coding=_coding_caller(session_id or str(ws), ws, roots, report),
            ask_person=_person_asker(asker, loop),
            report=report,
            save=store.save_run,
        )
        return run_summary(runner.run(input or ""))

    return [
        _tool(create_agent_system, _schema(
            "create_agent_system",
            "Save a new agent system the user can reuse (Agents section). Returns its id, any "
            "problems that stop it from running, and a Mermaid diagram to show the user.",
            {"system": _SYSTEM_SCHEMA}, ["system"])),
        _tool(update_agent_system, _schema(
            "update_agent_system",
            "Change a saved agent system. Pass only the fields that change; nodes and edges "
            "replace the whole list when given.",
            {"id": {"type": "string"}, "system": _SYSTEM_SCHEMA}, ["id", "system"])),
        _tool(list_agent_systems, _schema(
            "list_agent_systems", "The user's saved agent systems.", {}, [])),
        _tool(run_agent_system, _schema(
            "run_agent_system",
            "Run a saved agent system on an input and return its result. Each agent uses its "
            "own model, effort and tools; a review step waits for the user's answer.",
            {"system": {"type": "string", "description": "The system's id or exact title."},
             "input": {"type": "string", "description": "The work to hand the first agent."}},
            ["system", "input"]), gated=True),
    ]


def _agent_caller(title, provider, parent_model, ws, roots, approver, loop):
    from ..agents.base import AgentContext
    from ..catalog import expand
    from ..engine import ApprovalOutcome, TurnEngine
    from ..providers.effort import effort_settings
    from ..tools import ToolRegistry
    from ..tools.subagent import run_child

    async def child_approver(request):
        if approver is None or loop is None:
            return ApprovalOutcome.DENY
        return await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(approver(request), loop))

    def call(node: dict[str, Any], prompt: str, workers: list) -> str:
        model = node["model"] or parent_model
        registry = ToolRegistry()
        registry.register_all(expand(node["tools"], AgentContext(workspace=ws, roots=roots)))
        for worker, fn in workers:
            registry.register_all([_worker_tool(worker, fn)])
        instructions = (
            f"You are {node['name']}, one agent in a team called \"{title}\". Your reply goes to "
            "the next agent in the team, not to a person, so give the work itself, not a "
            f"conversation.\n\n{node['instructions']}"
            + (worker_prompt_note([w for w, _ in workers]) if workers else "")
        )
        engine = TurnEngine(
            provider=provider,
            registry=registry,
            permissions=PermissionEngine(workspace_root=ws, mode=Mode.ACCEPT_EDITS),
            model=model,
            instructions=instructions,
            approver=child_approver,
            max_iterations=25,
            model_settings=effort_settings(model, node["effort"]),
        )
        reply, status = run_child(engine, prompt)
        if status.startswith("error"):
            raise RuntimeError(f"{node['name']}: {status[7:] or 'the model call failed'}")
        if not reply:
            raise RuntimeError(f"{node['name']} returned nothing ({status}).")
        return reply

    return call


def _worker_tool(worker: dict[str, Any], fn: Callable[[str], str]) -> Callable[..., Any]:
    def ask_helper(task: str) -> dict:
        try:
            return {"result": fn(task)}
        except Exception as e:  # the lead sees the failure and can route around it
            return {"error": str(e)}

    what = worker["instructions"][:300] or worker["name"]
    schema = _schema(f"ask_{_slug(worker['name'])}", f"Give a task to {worker['name']}: {what}",
                     {"task": {"type": "string", "description": "A clear, self-contained task."}}, ["task"])
    return _tool(ask_helper, schema)


def _coding_caller(session: str, ws: Path, roots, report):
    from ..tools import delegate

    jobs: dict[str, Any] = {}
    copies: dict[str, tuple[Path, str]] = {}

    def call(node: dict[str, Any], prompt: str) -> str:
        key = node["agent"]
        # The node's role leads: two coding agents handed the same task without one did
        # the same job twice in the first live run (the builder also reviewed itself).
        if node["instructions"]:
            prompt = f"Your role in this team, as {node['name']}: {node['instructions']}\n\n{prompt}"
        problem = delegate.connection_problem(key)
        if problem:
            raise RuntimeError(problem)
        job = jobs.get(node["id"])
        if job is None:
            where = delegate._resolve_folder(node["folder"], roots or [], ws)
            if isinstance(where, str):
                raise RuntimeError(where)
            # One copy of the project per run: coding agents in one system build on each
            # other's work. ponytail: parallel coding agents on one folder share that copy
            # and may collide; give them separate folders until per-node copies are needed.
            if str(where) not in copies:
                copies[str(where)] = delegate.isolate(where, delegate._slug(f"team-{node['name']}"))
            workdir, branch = copies[str(where)]
            job = delegate.Job(session, key, delegate.find_agent(key), node["name"], workdir, branch)
            job.overrides = {"model": node["model"], "effort": node["effort"]}
            delegate._JOBS[job.id] = job
            jobs[node["id"]] = job
            job.launch(prompt + (delegate._COMMIT_NOTE if branch else ""))
        else:
            job.launch(prompt)  # the agent's own session resumes, so it remembers its work
        shown = ""
        while job.thread is not None and job.thread.is_alive():
            job.thread.join(timeout=2)
            if job.last != shown:
                shown = job.last
                report(f"{node['name']}: {shown}")
        out = job.report()
        if job.status != "finished":
            raise RuntimeError(out.get("error") or f"{node['name']} {job.status}")
        lines = [out.get("summary", "")]
        if out.get("branch"):
            lines.append(f"(Work is on branch {out['branch']} in {out['workdir']}.)")
        if out.get("changed_files"):
            lines.append("Changed: " + ", ".join(out["changed_files"][:30]))
        return "\n".join(x for x in lines if x)

    return call


def _person_asker(asker, loop):
    def ask(node: dict[str, Any], draft: str) -> tuple[str, str]:
        if asker is None or loop is None:
            return "stop", "Nobody could be asked to review it."
        args = {
            "question": f"{node['name']}: review this before it goes further.\n\n{draft[:8000]}",
            "options": [
                {"label": "Approve", "recommended": True},
                {"label": "Send back with a comment", "description": "Type what to change."},
                {"label": "Stop the run"},
            ],
        }
        return answer_to_decision(_on_loop(loop, asker, args))

    return ask
