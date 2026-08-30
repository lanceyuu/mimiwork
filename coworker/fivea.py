"""Which of the Five A's this account actually works in.

Chapter 7 of *GenAI for Business* (Shubin Yu, 2026) sorts the AI toolbox onto a
continuum — Access, Assistants, Applications, Automation, Agents — where "autonomy,
blast radius, and governance requirements rise together" (Figure 7.1). The chapter's
own instruction is the one that shapes this module: **"Classify by behavior, not
branding. Who initiates? Is the path fixed? What can it touch? What happens on
failure?"** So a turn is placed by what it DID, never by what the product is called.

    Access        "interacting directly with raw, general-purpose foundation
                  models" — a turn that answered from the model alone, no tools.
    Assistants    "domain-specific ... knowledge-aware" — a turn grounded in the
                  user's own material: a skill, the knowledge base, memory,
                  folder instructions.
    Applications  "task-specific, single-purpose" — a turn whose work was one
                  defined job producing an artifact: a document, deck, workbook,
                  chart, image.
    Automation    "routine, multi-step workflows that span several applications
                  and services" — a turn that ran on a schedule rather than
                  because someone was watching.
    Agents        "independently plan, reason, and execute complex, multi-step
                  goals" — a long tool-using turn, a delegated sub-agent, or a
                  plan the user approved before it ran.

One turn counts once, at the HIGHEST rung it reached, because the continuum is
about autonomy: a scheduled run that also wrote a document is Automation, not
Applications. Counting it twice would flatter the total and blur the axis the
figure is built on.

Why counts and not minutes (the EDGE profile's weighting): this answers "which mode
of working do I actually use", and a mode is a choice made once per turn. Time is
the right unit for value landed; frequency is the right unit for habit.
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
    "Access": "The model alone, answering directly",
    "Assistants": "Grounded in your own skills, notes and instructions",
    "Applications": "One defined job, one finished artifact",
    "Automation": "Ran on a schedule, without you watching",
    "Agents": "Planned and carried out a multi-step goal",
}

# Tool categories (from `timesaved.estimate_call`) that mean a turn produced a
# single-purpose artifact — the Applications rung.
_ARTIFACT_CATEGORIES = frozenset(
    {"Documents", "Decks", "Spreadsheets", "Analysis", "Files"}
)
# Tools that ground a turn in the user's own material — the Assistants rung.
_GROUNDING_TOOLS = frozenset(
    {
        "load_skill",
        "search_kb",
        "read_kb",
        "recall_memory",
        "list_commands",
        "expand_command",
    }
)
# Tools that only an agentic turn reaches for.
_AGENTIC_TOOLS = frozenset({"explore", "subagent", "propose_plan", "run_agent"})
# Past this many tool calls a turn is planning and executing, not doing one job.
_AGENTIC_CALL_COUNT = 6


def classify_turn(
    *,
    tools: Any = (),
    categories: Any = (),
    scheduled: bool = False,
    planned: bool = False,
) -> str:
    """The single rung a finished turn belongs on — the highest it reached.

    `tools` are the tool names called, `categories` their `timesaved` categories,
    `scheduled` whether an automation started the turn, `planned` whether the user
    approved a plan first.
    """
    names = {str(t) for t in (tools or ())}
    cats = {str(c) for c in (categories or ())}

    if scheduled:
        return "Automation"
    if planned or (names & _AGENTIC_TOOLS) or len(names) >= _AGENTIC_CALL_COUNT:
        return "Agents"
    if cats & _ARTIFACT_CATEGORIES:
        return "Applications"
    if names & _GROUNDING_TOOLS:
        return "Assistants"
    return "Access"


def profile(counts: Any) -> dict[str, Any]:
    """Shares of the Five A's from `{level: turns}`.

    Every rung is reported even at zero: a gap in the middle of a continuum is
    information ("you never build one-job applications"), and a chart whose bars
    appear and disappear cannot be compared with last month's.
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
