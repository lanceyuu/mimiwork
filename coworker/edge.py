"""The EDGE profile: what KIND of value this account gets from Mimi.

Definitions and structure come from Chapter 9 of *GenAI for Business* (Shubin Yu,
2026 second edition) — the framework's own book, read rather than inferred. Two
things in it changed this module's shape:

**It is three plus one, not four.** Figure 9.1: "three outcome pillars resting on
one enabling pillar." Efficiency, Decisions and Growth are outcome pillars — "places
where value lands in the P&L". Empowerment is the enabling pillar: "the human
capability that determines whether the other three materialize at all, and which
produces its own measurable outcomes along the way". Drawing four equal slices that
sum to 100% would contradict the framework it claims to show, so the shares are of
the three outcomes and Empowerment is reported beside them, as the foundation.

**Growth is about new revenue, not outward-facing work.** "Creating AI-native
products, services, and operating models that open new revenue streams." A slide
deck is not a new revenue stream, so decks are Efficiency (a deliverable produced
faster), not Growth. Growth is largely invisible from inside a desktop tool, and the
UI says so rather than implying the user is failing at it.

Two engineering rules carried over from the hours-saved badge beside it:

**Derive, never re-measure.** Every number comes from `TimeSaved.by_category`, which
the engine already records per call and merges install-wide. The profile is correct
for work done before it existed, needs no migration, and can never disagree with the
hours figure next to it — the same minutes, grouped two ways.

**Weight by minutes, not by calls.** Ten file reads are not worth one analysis.
"""

from __future__ import annotations

from typing import Any

# The three OUTCOME pillars — where value lands (ch. 9). Order as the acronym spells it.
OUTCOME_PILLARS: tuple[str, ...] = ("Efficiency", "Decisions", "Growth")
# The ENABLING pillar. Reported alongside, never as a fourth share.
ENABLING_PILLAR = "Empowerment"
PILLARS: tuple[str, ...] = OUTCOME_PILLARS + (ENABLING_PILLAR,)

# One line each, shown under the chart so nobody has to look the framework up.
# One line each, in the book's own terms.
BLURBS: dict[str, str] = {
    "Efficiency": "Doing what you already do, faster and at greater scale",
    "Decisions": "Insight synthesised from complex material, so you can choose",
    "Growth": "New offerings and revenue — rarely visible from inside a tool",
    "Empowerment": "The enabling pillar: capability that multiplies the other three",
}

# TimeSaved category → pillar. Categories are assigned per tool call in
# `timesaved.estimate_call`; anything unmapped is ignored rather than guessed into
# a pillar, because a wrong attribution is worse than a missing one.
CATEGORY_PILLARS: dict[str, str] = {
    # "Doing what you already do, but faster, cheaper, and at a greater scale" —
    # the repetitive, high-volume work a professional would otherwise type out.
    # Decks belong HERE, not in Growth: producing a deliverable faster is
    # efficiency; a deck is not a new revenue stream.
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
    # "Equips your workforce with AI tools that act as co-pilots, mentors, and
    # creative partners" — here, the durable capability the user built: skills,
    # automations, standing instructions.
    "Capability": "Empowerment",
    # Growth has no category: new offerings and revenue streams happen in the
    # market, not in a tool's call log. Inventing a proxy would put a number on the
    # pillar the book is most careful about. The UI explains the blank instead.
}


def profile(by_category: Any) -> dict[str, Any]:
    """The EDGE profile for one set of `TimeSaved.by_category` minutes.

    Shares are of the three OUTCOME pillars and sum to 100 exactly (largest
    remainder — a radar labelled 34/33/33 that adds to 101 undermines the chart it
    decorates). Empowerment is returned separately, with its own minutes and its
    share of ALL attributed time, because it is the enabling pillar rather than a
    competing slice.
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

    outcome_total = sum(minutes[p] for p in OUTCOME_PILLARS)
    enabling = minutes[ENABLING_PILLAR]
    total = outcome_total + enabling
    percent = _shares(minutes, outcome_total)
    leader = (
        max(OUTCOME_PILLARS, key=lambda p: minutes[p]) if outcome_total > 0 else ""
    )
    return {
        "pillars": [
            {
                "key": pillar,
                "label": pillar,
                "blurb": BLURBS[pillar],
                "minutes": round(minutes[pillar], 1),
                "percent": percent[pillar],
            }
            for pillar in OUTCOME_PILLARS
        ],
        "enabling": {
            "key": ENABLING_PILLAR,
            "label": ENABLING_PILLAR,
            "blurb": BLURBS[ENABLING_PILLAR],
            "minutes": round(enabling, 1),
            # Share of everything, not of the outcomes — it sits under them.
            "percent": int(round(enabling / total * 100)) if total > 0 else 0,
        },
        "outcome_minutes": round(outcome_total, 1),
        "total_minutes": round(total, 1),
        "leading": leader,
        # Below this there isn't enough work for a shape to mean anything; the UI
        # says so instead of drawing a confident triangle from twenty minutes.
        "ready": total >= 30.0,
    }


def _shares(minutes: dict[str, float], total: float) -> dict[str, int]:
    """Whole-number percentages of the OUTCOME total, summing to 100 (largest
    remainder)."""
    if total <= 0:
        return {pillar: 0 for pillar in OUTCOME_PILLARS}
    exact = {p: minutes[p] / total * 100.0 for p in OUTCOME_PILLARS}
    out = {p: int(exact[p]) for p in OUTCOME_PILLARS}
    short = 100 - sum(out.values())
    # Hand the leftover points to the largest fractional parts, biggest first.
    for pillar in sorted(
        OUTCOME_PILLARS, key=lambda p: exact[p] - int(exact[p]), reverse=True
    ):
        if short <= 0:
            break
        out[pillar] += 1
        short -= 1
    return out
