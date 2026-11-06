"""Turning a model's reply into steps the panel can trust: every range checked, no line hidden."""

from __future__ import annotations

import json

from coworker.code_explain import MAX_LINES, numbered, parse_steps, system_prompt


def _reply(*steps):
    return json.dumps({"steps": [dict(zip(("start", "end", "note", "choice"), s)) for s in steps]})


def test_valid_steps_come_back_in_order():
    steps = parse_steps(
        _reply((1, 2, "Loads the survey.", None), (3, 4, "Drops speeders.", "Cut-off of 120 seconds is a choice.")),
        4,
    )
    assert [(s["start"], s["end"]) for s in steps] == [(1, 2), (3, 4)]
    assert steps[1]["choice"].startswith("Cut-off")


def test_a_step_outside_the_file_is_dropped_and_its_lines_still_shown():
    steps = parse_steps(_reply((1, 2, "Loads.", None), (3, 99, "Nonsense.", None)), 4)
    assert steps[0]["note"] == "Loads."
    assert steps[1] == {"start": 3, "end": 4, "note": "", "choice": None}


def test_overlapping_steps_keep_the_first():
    steps = parse_steps(_reply((1, 3, "A.", None), (2, 4, "B.", None)), 4)
    assert [s["note"] for s in steps] == ["A.", ""]
    assert steps[1]["start"] == 4


def test_lines_no_step_mentions_become_an_empty_step():
    steps = parse_steps(_reply((2, 3, "Middle.", None)), 5)
    assert [(s["start"], s["end"], s["note"]) for s in steps] == [(1, 1, ""), (2, 3, "Middle."), (4, 5, "")]


def test_json_wrapped_in_a_code_fence_is_accepted():
    raw = "```json\n" + _reply((1, 1, "One.", None)) + "\n```"
    assert parse_steps(raw, 1)[0]["note"] == "One."


def test_a_reply_that_is_not_json_gives_nothing():
    assert parse_steps("Sorry, I cannot help with that.", 3) is None


def test_a_reply_with_no_valid_step_gives_nothing():
    assert parse_steps(_reply((5, 9, "Out of range.", None)), 3) is None


def test_the_listing_is_numbered_and_cut_at_the_limit():
    listing, shown, cut = numbered("\n".join(f"x{i}" for i in range(MAX_LINES + 5)))
    assert listing.startswith("1: x0\n2: x1")
    assert shown == MAX_LINES and cut is True


def test_line_numbers_count_newlines_only_like_the_panel():
    _, shown, _ = numbered("a = 1\x0cb = 2\nc = 3\n")
    assert shown == 2


def test_the_prompt_asks_for_the_researchers_language_and_forbids_numbers():
    prompt = system_prompt("zh")
    assert "Simplified Chinese" in prompt
    assert "Never state numbers" in prompt
    assert "English" in system_prompt("xx")
