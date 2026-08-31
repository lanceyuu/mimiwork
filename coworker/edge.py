"""The EDGE profile: what KIND of value this account gets from Mimi.

Four pillars, four axes, shares that sum to 100 — Efficiency, Decisions, Growth,
Empowerment. The framework is Chapter 9 of *GenAI for Business* (Shubin Yu, 2026
second edition); the two pillars that a usage log cannot read off its categories
are given operating definitions by the framework's author:

**Growth is work that is new and very different for you.** Not "new revenue" in
the abstract — from inside the app it is the moment you reach for something you
have never reached for before. The first deck. The first dataset. The first time
you connect Qualtrics. That reach is measured install-wide, in
`manager.record_time_saved`: minutes spent on a tool this account has never used
move into Growth instead of their usual pillar, and the tool joins the seen set,
so the same move never scores twice. A warm-up applies — see `_NOVELTY_WARMUP`
there — because in week one everything is new and that says nothing.

**Empowerment is when you learn something.** Two shapes of it: knowledge you took
in (`Learning` — looking a method up in the knowledge base) and knowledge you made
permanent (`Capability` — a skill saved, an automation written, house rules set
down). Both leave you able to do something you could not do before.

Two engineering rules carried over from the hours-saved badge beside it:

**Derive, never re-measure.** Every number comes from `TimeSaved.by_category`,
which the engine already records per call and merges install-wide. The profile is
correct for work done before it existed, needs no migration, and can never
disagree with the hours figure next to it — the same minutes, grouped two ways.
Growth is a re-labelling of minutes already counted, never an addition.

**Weight by minutes, not by calls.** Ten file reads are not worth one analysis.
"""

from __future__ import annotations

from typing import Any

# Four pillars, in the order the acronym spells them.
PILLARS: tuple[str, ...] = ("Efficiency", "Decisions", "Growth", "Empowerment")

# One line each, shown under the chart so nobody has to look the framework up.
BLURBS: dict[str, str] = {
    "Efficiency": "Doing what you already do, faster and at greater scale",
    "Decisions": "Insight synthesised from complex material, so you can choose",
    "Growth": "Work that is new and different — the first time you try something",
    "Empowerment": "What you learned, and what you made permanent",
}

# TimeSaved category → pillar. Categories are assigned per tool call in
# `timesaved.estimate_call`; anything unmapped is ignored rather than guessed into
# a pillar, because a wrong attribution is worse than a missing one.
CATEGORY_PILLARS: dict[str, str] = {
    # "Doing what you already do, but faster, cheaper, and at a greater scale" —
    # the repetitive, high-volume work a professional would otherwise type out.
    "Documents": "Efficiency",
    "Spreadsheets": "Efficiency",
    "Files": "Efficiency",
    "Reading": "Efficiency",
    "Decks": "Efficiency",
    "Connectors": "Efficiency",
    # "Better, faster choices by using AI to synthesise context-rich insights from
    # massive, complex, and often unstructured data sets."
    "Analysis": "Decisions",
    "Research": "Decisions",
    # New ground. Written by the install-wide novelty test, never by a tool
    # directly — see the module docstring.
    "Growth": "Growth",
    # What you learned, and what you made permanent.
    "Learning": "Empowerment",
    "Capability": "Empowerment",
}


def profile(by_category: Any) -> dict[str, Any]:
    """The EDGE profile for one set of `TimeSaved.by_category` minutes.

    Shares sum to 100 exactly (largest remainder — a radar labelled 34/33/33 that
    adds to 101 undermines the chart it decorates).
    """
    minutes = {pillar: 0.0 for pillar in PILLARS}
    source = by_category if isinstance(by_category, dict) else {}
    for category, value in source.items():
        pillar = CATEGORY_PILLARS.get(str(category))
        if not pillar:
            continue
        try:
            minutes[pillar] += max(0.0, float(value))
        except (TypeError, ValueError):
            continue

    total = sum(minutes.values())
    percent = _shares(minutes, total)
    leader = max(PILLARS, key=lambda p: minutes[p]) if total > 0 else ""
    return {
        "pillars": [
            {
                "key": pillar,
                "label": pillar,
                "blurb": BLURBS[pillar],
                "minutes": round(minutes[pillar], 1),
                "percent": percent[pillar],
            }
            for pillar in PILLARS
        ],
        "total_minutes": round(total, 1),
        "leading": leader,
        # Below this there isn't enough work for a shape to mean anything; the UI
        # says so instead of drawing a confident radar from twenty minutes.
        "ready": total >= 30.0,
    }


def _shares(minutes: dict[str, float], total: float) -> dict[str, int]:
    """Whole-number percentages summing to 100 (largest remainder)."""
    if total <= 0:
        return {pillar: 0 for pillar in PILLARS}
    exact = {p: minutes[p] / total * 100.0 for p in PILLARS}
    out = {p: int(exact[p]) for p in PILLARS}
    short = 100 - sum(out.values())
    # Hand the leftover points to the largest fractional parts, biggest first.
    for pillar in sorted(PILLARS, key=lambda p: exact[p] - int(exact[p]), reverse=True):
        if short <= 0:
            break
        out[pillar] += 1
        short -= 1
    return out
