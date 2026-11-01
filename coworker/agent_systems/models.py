"""An agent system: a small graph of agents the user designs once and runs again.

Nine patterns from the owner's Agentic AI deck (sequence, routing, parallel work,
reflection, ReAct, planning, tool use, multi-agent, human review) are drawn with five
node kinds and two edge kinds, so one runner covers all of them instead of nine engines:

    agent         a Mimi subagent — its own instructions, model, effort and tools.
                  A normal turn loop, which already IS tool use and ReAct.
    coding        an external coding CLI (Claude Code, Codex, ...) through delegate.py.
    router        an agent whose first line names ONE outgoing edge label to follow.
    orchestrator  an agent that calls the workers on its "assign" edges as tools.
    review        a person approves, or sends it back with a comment.

    flow edge     what runs next. Several out = parallel; several in = wait for all.
                  An edge with max_rounds is a loop (reflection); the rest must be acyclic.
    assign edge   orchestrator → worker. The worker runs only when the lead calls it.

The saved shape keeps an A2A-style `card` so a later release can publish a system as an
A2A agent, or add a remote one as a node, without migrating anyone's files.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

FORMAT = 1
KINDS = ("agent", "coding", "router", "orchestrator", "review")
EFFORTS = ("", "low", "medium", "high")
MAX_ROUNDS = 5
MAX_NODES = 30
REVISE = "revise"  # the review node's send-back edge label


@dataclass
class AgentSystem:
    id: str
    title: str
    description: str = ""
    pattern: str = ""
    nodes: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    entry: str = ""
    builder_session: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def public(self) -> dict[str, Any]:
        out = asdict(self)
        out["mimiwork_agent_system"] = FORMAT
        out["card"] = {
            "name": self.title,
            "description": self.description,
            "skills": [{"id": n["id"], "name": n["name"]} for n in self.nodes],
        }
        return out

    def node(self, node_id: str) -> Optional[dict[str, Any]]:
        return next((n for n in self.nodes if n["id"] == node_id), None)


def _text(raw: Any, limit: int) -> str:
    return str(raw or "").strip()[:limit]


def clean_node(raw: Any, index: int) -> dict[str, Any]:
    """One node in its saved shape. Unknown keys are dropped so a stale or hand-edited
    file cannot smuggle settings the runner would then trust."""
    if not isinstance(raw, dict):
        raise ValueError(f"node {index + 1} is not an object")
    kind = _text(raw.get("kind"), 20) or "agent"
    pos = raw.get("position") if isinstance(raw.get("position"), dict) else {}
    tools = raw.get("tools") if isinstance(raw.get("tools"), list) else []
    return {
        "id": _text(raw.get("id"), 40) or f"n{index + 1}",
        "kind": kind,
        "name": _text(raw.get("name"), 60) or f"Agent {index + 1}",
        "instructions": _text(raw.get("instructions"), 8000),
        "model": _text(raw.get("model"), 100),
        "effort": _text(raw.get("effort"), 10).lower(),
        "tools": [_text(t, 40) for t in tools if _text(t, 40)],
        "agent": _text(raw.get("agent"), 30),
        "folder": _text(raw.get("folder"), 500),
        "position": {"x": _num(pos.get("x")), "y": _num(pos.get("y"))},
    }


def _num(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def clean_edge(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"connection {index + 1} is not an object")
    rounds = raw.get("max_rounds")
    try:
        rounds = int(rounds) if rounds not in (None, "") else None
    except (TypeError, ValueError):
        rounds = None
    return {
        "from": _text(raw.get("from"), 40),
        "to": _text(raw.get("to"), 40),
        "kind": "assign" if raw.get("kind") == "assign" else "flow",
        "label": _text(raw.get("label"), 40),
        "max_rounds": rounds,
    }


def validate(system: AgentSystem) -> list[dict[str, str]]:
    """Every reason this system cannot run, as {node, message} — node is "" when the
    problem is the whole graph. The GUI pins each message to the node it names."""
    from ..tools.delegate import AGENTS

    problems: list[dict[str, str]] = []

    def bad(node: str, message: str) -> None:
        problems.append({"node": node, "message": message})

    ids = [n["id"] for n in system.nodes]
    if not system.nodes:
        bad("", "Add at least one agent.")
        return problems
    if len(system.nodes) > MAX_NODES:
        bad("", f"A system can have at most {MAX_NODES} agents.")
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        bad(dup, "Two agents share this id.")
    if system.entry not in ids:
        bad("", "Choose which agent starts the work.")

    catalog = _catalog_ids()
    for n in system.nodes:
        if n["kind"] not in KINDS:
            bad(n["id"], f"Unknown kind of agent: {n['kind']}.")
        if n["effort"] not in EFFORTS:
            bad(n["id"], "Thinking effort must be low, medium or high.")
        unknown = [t for t in n["tools"] if t not in catalog]
        if unknown:
            bad(n["id"], f"Unknown tools: {', '.join(unknown)}.")
        if n["kind"] == "coding":
            if n["agent"] not in AGENTS:
                bad(n["id"], "Choose which coding agent does this work.")
            if not n["folder"]:
                bad(n["id"], "Choose the project folder the coding agent works in.")
        elif n["kind"] != "review" and not n["instructions"]:
            bad(n["id"], "Tell this agent what to do.")

    by_id = {n["id"]: n for n in system.nodes}
    workers: set[str] = set()
    for e in system.edges:
        if e["from"] not in by_id or e["to"] not in by_id:
            bad("", "A connection points at an agent that no longer exists.")
            continue
        if e["from"] == e["to"]:
            bad(e["from"], "An agent cannot connect to itself.")
        src = by_id[e["from"]]
        if e["kind"] == "assign":
            if src["kind"] != "orchestrator":
                bad(src["id"], "Only a lead agent can assign work.")
            workers.add(e["to"])
        if e["max_rounds"] is not None and not 1 <= e["max_rounds"] <= MAX_ROUNDS:
            bad(src["id"], f"A loop can repeat 1 to {MAX_ROUNDS} times.")

    flow = [e for e in system.edges if e["kind"] == "flow" and e["from"] in by_id and e["to"] in by_id]
    for w in sorted(workers):
        if any(e["to"] == w or e["from"] == w for e in flow):
            bad(w, "An agent the lead assigns work to cannot also be part of the main flow.")
        if by_id[w]["kind"] not in ("agent", "coding"):
            bad(w, "A lead agent can only assign work to Mimi or coding agents.")
    if system.entry in workers:
        bad(system.entry, "The starting agent cannot be one the lead assigns work to.")

    for n in system.nodes:
        out = [e for e in flow if e["from"] == n["id"]]
        if n["kind"] == "router":
            if len(out) < 2 or any(not e["label"] for e in out):
                bad(n["id"], "A router needs two or more labelled connections to choose from.")
            elif len({e["label"].lower() for e in out}) != len(out):
                bad(n["id"], "Each of a router's connections needs a different label.")
        if n["kind"] == "review":
            sends_back = [e for e in out if e["label"].lower() == REVISE]
            if any(e["max_rounds"] is None for e in sends_back):
                bad(n["id"], "The send-back connection needs a round limit.")

    if _has_cycle(ids, [e for e in flow if e["max_rounds"] is None]):
        bad("", "The flow goes in a circle. Give the connection that loops back a round limit.")
    return problems


def _catalog_ids() -> set[str]:
    # Imported here: catalog → agents → catalog is a load-order cycle at module level.
    from .. import agents  # noqa: F401
    from ..catalog import CATALOG

    return set(CATALOG)


def _has_cycle(ids: list[str], edges: list[dict[str, Any]]) -> bool:
    nexts: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges:
        nexts[e["from"]].append(e["to"])
    state: dict[str, int] = {}

    def visit(i: str) -> bool:
        state[i] = 1
        for j in nexts.get(i, []):
            if state.get(j) == 1 or (state.get(j) is None and visit(j)):
                return True
        state[i] = 2
        return False

    return any(state.get(i) is None and visit(i) for i in ids)


_SHAPES = {
    "agent": ('["', '"]'),
    "coding": ('[/"', '"/]'),
    "router": ('{"', '"}'),
    "orchestrator": ('[["', '"]]'),
    "review": ('(["', '"])'),
}


def to_mermaid(system: AgentSystem) -> str:
    """The system as a Mermaid flowchart — chat already renders these, so Mimi can show
    the design the moment it saves one, before the user opens the editor."""
    lines = ["flowchart LR"]
    for n in system.nodes:
        open_, close = _SHAPES.get(n["kind"], ('["', '"]'))
        label = n["name"].replace('"', "'")
        if n["model"]:
            label += f"<br/><small>{n['model'].split(':')[-1]}</small>"
        lines.append(f"  {_mid(n['id'])}{open_}{label}{close}")
    for e in system.edges:
        arrow = "-.->" if e["kind"] == "assign" else "-->"
        text = e["label"]
        if e["max_rounds"]:
            text = f"{text} (up to {e['max_rounds']}x)".strip()
        mid = f'|"{text.replace(chr(34), chr(39))}"|' if text else ""
        lines.append(f"  {_mid(e['from'])} {arrow}{mid} {_mid(e['to'])}")
    return "\n".join(lines)


def _mid(node_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", node_id) or "n"
