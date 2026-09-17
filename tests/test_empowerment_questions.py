"""Empowerment counts a question answered (owner ask 2026-09-17: the pillar was empty
because only knowledge-base lookups and saved skills scored)."""

from __future__ import annotations

import pytest

from coworker.edge import profile
from coworker.timesaved import TimeSaved, looks_like_question


@pytest.mark.parametrize(
    "text",
    [
        "Why does the regression coefficient flip sign?",
        "explain the difference between mediation and moderation",
        "What is a Likert scale",
        "how do I cite a preprint",
        "为什么要用中介分析",
        "Explique-moi la validité convergente",
        "Hvorfor bruker vi bootstrap",
        "Can you tell me about grounded theory?",
    ],
)
def test_questions_are_recognised(text):
    assert looks_like_question(text)


@pytest.mark.parametrize("text", ["Draft the syllabus for week 3", "Fix the typo in the intro", "", "Translate this into French"])
def test_instructions_are_not_questions(text):
    assert not looks_like_question(text)


def test_an_answered_question_gives_the_profile_an_empowerment_share():
    def share(ts: TimeSaved, pillar: str) -> int:
        row = next(p for p in profile(ts.by_category)["pillars"] if p["key"] == pillar)
        return int(row["percent"])

    ts = TimeSaved()
    ts.add_call("write_file", {"content": "x " * 200}, {})
    assert share(ts, "Empowerment") == 0
    ts.add_learning()
    assert share(ts, "Empowerment") > 0 and ts.by_category["Learning"] == 4.0
