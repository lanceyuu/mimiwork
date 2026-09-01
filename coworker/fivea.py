"""Where this account's turns sit on the Five A's continuum.

Chapter 7 of *GenAI for Business* (Shubin Yu, 2026) sorts the AI toolbox onto a
continuum — Access, Assistants, Applications, Automation, Agents — where "autonomy,
blast radius, and governance requirements rise together" (Figure 7.1).

The chapter classifies PRODUCTS. This module classifies TURNS, which is a
deliberate adaptation and worth stating plainly: by §7.5.3's own reckoning
MimiWork is an agentic workbench, so every turn would score "Agents" and the
chart would say nothing. What is worth measuring instead is how much autonomy
each turn was actually handed — the axis Figure 7.1 is drawn on.

So a turn is placed with §7.6's operational test, which asks four behavioural
questions rather than reading a label:

    Who initiates?          A human at the keyboard, or a schedule? "If a human
                            triggers every run, it is at most an Assistant or
                            Automation; Agents act on goals and events."
    Is the path fixed?      "If the steps are predefined, it is an Automation
                            regardless of how much AI sits inside the steps;
                            Agents choose their own next action."
    What can it touch?      "Read-only access to one system is Assistant
                            territory; write access ACROSS SYSTEMS is agent
                            territory." Note the plural — one write to one
                            service is not yet agent territory.
    What on failure?        "If failure means a wrong answer a human reads, risk
                            is low; if failure means a wrong action a customer
                            experiences, you are governing an Agent whatever the
                            vendor calls it."

Which gives the five rungs their per-turn readings:

    Access        "interacting directly or through APIs with raw, general-purpose
                  foundation models." §7.1 is explicit that the modern wrapper —
                  built-in web search, file handling, memory — is still Access,
                  so a turn that only searched the web has not left this rung.
    Assistants    "domain-specific ... knowledge-aware", grounded through RAG in
                  "project documents, codebases, academic papers". A turn that
                  read the user's own material and answered from it.
    Applications  "task-specific, single-purpose ... no-code or low-code, built
                  through natural-language prompts". A skill or saved command is
                  exactly that: one defined job, one fixed recipe.
    Automation    "routine, multi-step workflows ... run themselves". A schedule
                  started it and it followed the path it was given.
    Agents        "independently plan, reason, and execute complex, multi-step
                  goals". The model chose its own next action — or wrote across
                  more than one outside system while doing so.

One turn counts once, at the HIGHEST rung it reached, because the continuum is
about autonomy: a scheduled run that also wrote a document is Automation, not
Applications. Counting it twice would flatter the total and blur the axis.

Why counts and not minutes (the EDGE profile's weighting): this answers "how much
autonomy do I actually hand over", and that is a choice made once per turn. Time
is the right unit for value landed; frequency is the right unit for habit.
"""

from __future__ import annotations

from typing import Any

# The continuum, in the order the chapter draws it — autonomy rising left to right.
LEVELS: tuple[str, ...] = (
    "Access",
    "Assistants",
    "Applications",
    "Automation",
    "Agents",
)

BLURBS: dict[str, str] = {
    "Access": "The model on its own, answering you directly",
    "Assistants": "Grounded in your own documents, notes and knowledge base",
    "Applications": "One fixed recipe, one defined job — a skill or a command",
    "Automation": "A schedule started it and it followed the path it was given",
    "Agents": "It chose its own next step, or reached across your systems",
}

# ── Q1. Who initiates? ──
# `scheduled` answers it for a run that a schedule started. Building the automation is
# the other half: the turn that creates one is the moment the work stops needing a
# person to start it, which is exactly what the Automation rung describes. Without
# this, an account could set up ten automations and still read as 100% Access until
# the first one happened to fire (owner-hit 2026-08-31).
_AUTOMATION_TOOLS = frozenset(
    {"create_scheduled_task", "update_scheduled_task", "mcp__scheduled-tasks__create_scheduled_task"}
)

# ── Q2. Is the path fixed? ──
# A skill or a saved command IS the predefined path: one job, written down in
# advance. Running one is the Applications rung, and it also means the turn did
# NOT choose its own way, however many tools the recipe called for.
_RECIPE_TOOLS = frozenset({"load_skill", "expand_command", "list_commands"})
# The opposite: tools that exist only because the model is deciding what to do
# next — delegating, exploring, or proposing a plan to carry out.
_SELF_DIRECTION_TOOLS = frozenset({"explore", "subagent", "run_agent", "propose_plan"})
# Past this many DISTINCT tools with no recipe in sight, a turn is not answering
# a question — it is working out its own route. Six is where a turn stops looking
# like "read this, answer that" in the transcripts.
_SELF_DIRECTED_TOOL_COUNT = 6

# ── Q3/Q4. What can it touch, and what does failure cost? ──
# Anything that leaves the workspace and changes something out there. `shell`
# counts as one such system: it can reach anything the machine can.
_OUTWARD_TOOLS = frozenset({"run_shell", "shell", "bash", "send_message"})
# Connector tools are named `<service>_<verb>`; these verbs write.
_WRITE_VERBS = ("send", "post", "create", "update", "reply", "export", "add", "delete")
# "Write access ACROSS SYSTEMS is agent territory" — the plural is the rule. One
# write to one service is a user-directed action, not a delegated goal.
_AGENT_REACH_SYSTEMS = 2

# ── Assistants: grounded in the user's own material (the RAG rung) ──
# The knowledge base and memory, plus reading the user's own files: §7.2's
# "project documents, codebases, academic papers, or product manuals".
_GROUNDING_TOOLS = frozenset(
    {
        "kb_search",
        "kb_read",
        "kb_list",
        "recall_memory",
        "read_file",
        "read_document",
        "read_pdf",
        "read_workbook",
        "read_presentation",
        "list_directory",
        "grep",
        "inspect_data",
    }
)


def _outward_systems(names: set[str]) -> int:
    """How many distinct outside systems this turn WROTE to.

    Connector tools are `<service>_<verb>`, so the service name is the system;
    every shell-family tool collapses into one ("the machine"), because running
    two shell commands is not reaching across two systems.
    """
    systems: set[str] = set()
    for name in names:
        if name in _OUTWARD_TOOLS:
            systems.add("send_message" if name == "send_message" else "shell")
            continue
        service, _, verb = name.partition("_")
        if service and verb and verb.startswith(_WRITE_VERBS):
            systems.add(service)
    return len(systems)


def classify_turn(
    *,
    tools: Any = (),
    scheduled: bool = False,
    planned: bool = False,
) -> str:
    """The single rung a finished turn belongs on — the highest it reached.

    `tools` are the tool names called, `scheduled` whether an automation started
    the turn rather than a person, `planned` whether the model proposed a plan and
    then carried it out.
    """
    names = {str(t) for t in (tools or ())}
    recipe = bool(names & _RECIPE_TOOLS)

    # Q2 — did it choose its own next action? A recipe means the path was given,
    # so tool COUNT alone cannot promote a skill run to Agents; an explicit
    # delegation or plan still can, because that is the model deciding.
    self_directed = bool(planned or (names & _SELF_DIRECTION_TOOLS))
    if not recipe and len(names) >= _SELF_DIRECTED_TOOL_COUNT:
        self_directed = True

    # Q3/Q4 — write access across systems, with a wrong action at the far end.
    if self_directed or _outward_systems(names) >= _AGENT_REACH_SYSTEMS:
        return "Agents"
    # Q1 — nobody was watching, and the path was the one it was given; or the turn built
    # the thing that will run without anyone watching.
    if scheduled or (names & _AUTOMATION_TOOLS):
        return "Automation"
    if recipe:
        return "Applications"
    if names & _GROUNDING_TOOLS:
        return "Assistants"
    return "Access"


def profile(counts: Any) -> dict[str, Any]:
    """Shares of the Five A's from `{level: turns}`.

    Every rung is reported even at zero: a gap in the middle of a continuum is
    information ("you never run a fixed recipe"), and a chart whose bars appear
    and disappear cannot be compared with last month's.
    """
    source = counts if isinstance(counts, dict) else {}
    turns = {level: 0 for level in LEVELS}
    for level, value in source.items():
        if str(level) in turns:
            try:
                turns[str(level)] += max(0, int(value))
            except (TypeError, ValueError):
                continue

    total = sum(turns.values())
    percent = _shares(turns, total)
    return {
        "levels": [
            {
                "key": level,
                "label": level,
                "blurb": BLURBS[level],
                "turns": turns[level],
                "percent": percent[level],
            }
            for level in LEVELS
        ],
        "total_turns": total,
        "leading": max(LEVELS, key=lambda level: turns[level]) if total else "",
        # Ten turns is enough to see a habit; fewer is just the last thing you did.
        "ready": total >= 10,
    }


def _shares(turns: dict[str, int], total: int) -> dict[str, int]:
    """Whole-number percentages summing to 100 (largest remainder)."""
    if total <= 0:
        return {level: 0 for level in LEVELS}
    exact = {level: turns[level] / total * 100.0 for level in LEVELS}
    out = {level: int(exact[level]) for level in LEVELS}
    short = 100 - sum(out.values())
    for level in sorted(LEVELS, key=lambda x: exact[x] - int(exact[x]), reverse=True):
        if short <= 0:
            break
        out[level] += 1
        short -= 1
    return out
