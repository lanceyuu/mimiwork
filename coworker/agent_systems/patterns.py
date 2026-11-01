"""The nine starting patterns, from the owner's "Agentic AI for Executives" deck.

Skills, the deck's tenth pattern, is left out on purpose: MimiWork already has skills,
and a node can load them. Every template uses the deck's hotel front-desk case, so a
pattern runs the moment it is picked and the user edits a working example rather than
a blank canvas. An empty model means "the model this chat uses".
"""

from __future__ import annotations

from typing import Any

_X = 260  # horizontal gap between columns on the canvas
_Y = 140


def _n(node_id: str, name: str, instructions: str = "", *, kind: str = "agent", col: int = 0,
       row: float = 0, tools: list[str] | None = None, effort: str = "") -> dict[str, Any]:
    return {"id": node_id, "kind": kind, "name": name, "instructions": instructions,
            "tools": tools or [], "effort": effort, "position": {"x": col * _X, "y": row * _Y}}


def _e(a: str, b: str, label: str = "", *, kind: str = "flow", rounds: int | None = None) -> dict[str, Any]:
    return {"from": a, "to": b, "label": label, "kind": kind, "max_rounds": rounds}


_EMAIL = "The input is a guest email to a small hotel's front desk."

PATTERNS: list[dict[str, Any]] = [
    {
        "pattern": "sequence", "group": "Flow", "title": "Sequence",
        "summary": "Pass each result to the next step.",
        "when": "Consecutive steps depend on each other.",
        "nodes": [
            _n("extract", "Extract the request", f"{_EMAIL} List exactly what the guest is asking for, one line each."),
            _n("policy", "Check policy", "For each request, say what hotel policy allows. Flag anything you cannot confirm.", col=1),
            _n("draft", "Draft the reply", "Write a short, warm reply in the guest's language that answers each request within policy.", col=2),
        ],
        "edges": [_e("extract", "policy"), _e("policy", "draft")],
    },
    {
        "pattern": "routing", "group": "Flow", "title": "Routing",
        "summary": "Choose a path for each request.",
        "when": "Different kinds of request need different handling.",
        "nodes": [
            _n("triage", "Sort the request", f"{_EMAIL} Decide which kind of request it is.", kind="router", effort="low"),
            _n("info", "Answer a question", "Answer the guest's question about the hotel briefly and accurately.", col=1, row=-1),
            _n("late", "Arrange late arrival", "Explain how late check-in works and what the guest needs to do.", col=1, row=0),
            _n("owner", "Prepare for the owner", "Summarise the exception the guest asks for and what deciding it needs.", col=1, row=1),
        ],
        "edges": [_e("triage", "info", "question"), _e("triage", "late", "late arrival"), _e("triage", "owner", "exception")],
    },
    {
        "pattern": "parallel", "group": "Flow", "title": "Parallel work",
        "summary": "Split independent tasks, then combine the results.",
        "when": "Subtasks can be done at the same time.",
        "nodes": [
            _n("brief", "Read the brief", f"{_EMAIL} Restate what a good answer must cover."),
            _n("needs", "Check needs", "List what the guest needs and why.", col=1, row=-1),
            _n("rules", "Check policy", "List the policies that apply and any limits.", col=1, row=0),
            _n("cost", "Check cost", "Estimate any extra cost to the guest or the hotel.", col=1, row=1),
            _n("combine", "Combine the findings", "Reconcile the three findings, resolve conflicts, and write one reply.", col=2),
        ],
        "edges": [_e("brief", "needs"), _e("brief", "rules"), _e("brief", "cost"),
                  _e("needs", "combine"), _e("rules", "combine"), _e("cost", "combine")],
    },
    {
        "pattern": "reflection", "group": "Loops", "title": "Reflection",
        "summary": "Draft, check against the facts, revise until it passes.",
        "when": "Quality matters and a checker can say what is wrong.",
        "nodes": [
            _n("draft", "Draft the reply", f"{_EMAIL} Write a reply. If you get feedback, revise the draft to address all of it."),
            _n("check", "Check the draft", "Check the draft for wrong facts, missing answers and tone. List what to fix.", col=1, effort="high"),
        ],
        "edges": [_e("check", "draft", "revise", rounds=3)],
        "chain": [("draft", "check")],
    },
    {
        "pattern": "react", "group": "Loops", "title": "ReAct",
        "summary": "Reason, act, observe the result, repeat.",
        "when": "The next step depends on what the last action found.",
        "nodes": [
            _n("agent", "Front-desk agent",
               f"{_EMAIL} Work step by step: think about what you need, look it up with your tools, "
               "read what you found, and repeat until you can answer. Then write the reply.",
               tools=["knowledge_base", "files"]),
        ],
        "edges": [],
    },
    {
        "pattern": "planning", "group": "Loops", "title": "Planning",
        "summary": "Break a combined request into a plan, then carry it out.",
        "when": "One request hides several tasks.",
        "nodes": [
            _n("planner", "Plan and assign",
               f"{_EMAIL} Write a numbered plan of the separate tasks it contains. Give each task to the right "
               "helper, check what comes back, revise the plan if needed, then write the final reply.",
               kind="orchestrator", effort="high"),
            _n("facts", "Look up facts", "Answer the factual question you are given from hotel information.", col=1, row=-0.5),
            _n("writer", "Write a section", "Write the reply section you are asked for, in the guest's language.", col=1, row=0.5),
        ],
        "edges": [_e("planner", "facts", kind="assign"), _e("planner", "writer", kind="assign")],
    },
    {
        "pattern": "tool_use", "group": "Capabilities", "title": "Tool use",
        "summary": "Retrieve a fact with a tool, then apply it.",
        "when": "The answer depends on information outside the model.",
        "nodes": [
            _n("lookup", "Look it up", f"{_EMAIL} Use your tools to find the facts the reply needs. Quote where each came from.",
               tools=["knowledge_base", "files"]),
            _n("reply", "Write a grounded reply", "Write the reply using only the facts found. Say plainly if one is missing.", col=1),
        ],
        "edges": [_e("lookup", "reply")],
    },
    {
        "pattern": "multi_agent", "group": "Collaboration", "title": "Multi-agent",
        "summary": "A lead agent assigns work to specialists and integrates their results.",
        "when": "Different parts need different expertise or models.",
        "nodes": [
            _n("lead", "Lead agent",
               f"{_EMAIL} Give each part of the work to the specialist best suited to it, compare what they "
               "report, and write the final answer.", kind="orchestrator"),
            _n("booking", "Booking specialist", "Handle questions about rooms, dates and check-in.", col=1, row=-1),
            _n("billing", "Billing specialist", "Handle questions about prices, refunds and invoices.", col=1, row=0),
            _n("local", "Local guide", "Handle questions about the area, transport and parking.", col=1, row=1),
        ],
        "edges": [_e("lead", "booking", kind="assign"), _e("lead", "billing", kind="assign"), _e("lead", "local", kind="assign")],
    },
    {
        "pattern": "human_review", "group": "Collaboration", "title": "Human review",
        "summary": "A person approves before anything is committed.",
        "when": "The output makes a commitment, an exception or a consequential judgment.",
        "nodes": [
            _n("draft", "Draft the refund reply",
               f"{_EMAIL} Draft a reply proposing a refund amount and terms. Show the evidence. "
               "If you get reviewer comments, revise to address them."),
            _n("review", "Owner reviews", kind="review", col=1),
            _n("final", "Prepare the final reply", "Turn the approved draft into the final reply, unchanged in substance.", col=2),
        ],
        "edges": [_e("review", "final"), _e("review", "draft", "revise", rounds=3)],
        "chain": [("draft", "review")],
    },
]


def patterns() -> list[dict[str, Any]]:
    """Each pattern as a ready-to-save system: {pattern, group, title, summary, when,
    system}. "chain" edges are the forward half of a loop, listed apart only so the
    templates above read in the order the work happens."""
    out = []
    for p in PATTERNS:
        edges = [_e(a, b) for a, b in p.get("chain", [])] + p["edges"]
        out.append({
            "pattern": p["pattern"], "group": p["group"], "title": p["title"],
            "summary": p["summary"], "when": p["when"],
            "system": {"title": p["title"], "description": p["summary"], "pattern": p["pattern"],
                       "nodes": p["nodes"], "edges": edges, "entry": p["nodes"][0]["id"]},
        })
    return out
