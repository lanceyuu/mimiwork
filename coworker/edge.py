"""The EDGE profile: what KIND of value this account gets from Mimi.

Hours saved answers "how much". This answers "at what" — the shape of the help,
scored on Shubin Yu's EDGE framework for AI in business (gaiforbusiness.com):

    Efficiency    cost and effort taken out of work that had to happen anyway
    Decisions     evidence gathered and analysed so a choice can be made
    Growth        work aimed outward — persuading, reaching, delivering to others
    Empowerment   capability that outlives the session, so the person can do more

Two design rules, both learned from the hours-saved badge sitting beside it.

**Derive, never re-measure.** Every number here comes from `TimeSaved.by_category`,
which the engine already records per call and merges install-wide. So the radar is
correct for work done before this feature existed, needs no migration, and can never
disagree with the hours figure next to it — they are the same minutes, grouped two
ways.

**Weight by minutes, not by calls.** Ten file reads are not worth one deck. Counting
calls would make the busiest tool look like the biggest contribution; counting the
time each piece of work would have cost a person is the honest weighting, and it is
the weighting the hours badge already uses.

A pillar with no activity reads zero rather than being hidden — an empty axis is
information ("you have never used Mimi to build capability"), and a radar whose axes
appear and disappear cannot be compared to last month's.
"""

from __future__ import annotations

from typing import Any

# The four pillars, in the order the acronym spells them.
PILLARS: tuple[str, ...] = ("Efficiency", "Decisions", "Growth", "Empowerment")

# One line each, shown under the chart so nobody has to look the framework up.
BLURBS: dict[str, str] = {
    "Efficiency": "Work that had to happen anyway, done faster",
    "Decisions": "Evidence gathered and analysed so you can choose",
    "Growth": "Work aimed outward — decks, messages, delivery",
    "Empowerment": "Capability that outlasts the session",
}

# TimeSaved category → pillar. Categories are assigned per tool call in
# `timesaved.estimate_call`; anything unmapped is ignored rather than guessed into
# a pillar, because a wrong attribution is worse than a missing one.
CATEGORY_PILLARS: dict[str, str] = {
    # Producing and handling the documents the job requires.
    "Documents": "Efficiency",
    "Spreadsheets": "Efficiency",
    "Files": "Efficiency",
    "Reading": "Efficiency",
    # Working out what is true before deciding.
    "Analysis": "Decisions",
    "Research": "Decisions",
    # Pointed at other people: an argument to make, a message to send.
    "Decks": "Growth",
    "Connectors": "Growth",
    # Skills, automations and standing instructions — built once, used forever.
    "Capability": "Empowerment",
}


def profile(by_category: Any) -> dict[str, Any]:
    """The EDGE shares for one set of `TimeSaved.by_category` minutes.

    Returns each pillar's minutes and its percentage of the attributed total, plus
    the leading pillar. Percentages are rounded so they sum to 100 exactly — a
    radar labelled 34/33/33/1 that adds to 101 undermines the chart it decorates.
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
        # says so instead of drawing a confident triangle from twenty minutes.
        "ready": total >= 30.0,
    }


def _shares(minutes: dict[str, float], total: float) -> dict[str, int]:
    """Whole-number percentages that sum to 100 (largest-remainder)."""
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
