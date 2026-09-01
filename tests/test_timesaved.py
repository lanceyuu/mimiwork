"""The hours-saved estimate: grounded in artifacts, conservative, never negative.

The number sits in the composer and behind the logo, where a user can check it
against their own memory of the afternoon. That makes credibility the requirement:
every assertion here is really asking "would a professional recognise this figure?"
"""

from __future__ import annotations

import pytest

from coworker.timesaved import TimeSaved, estimate_call


def test_a_ten_slide_deck_costs_about_an_hour_by_hand():
    """Six minutes a slide plus its words — the fast end of real deck-building, so
    the claim survives someone arguing about it."""
    slides = [
        {"title": f"Finding {i}", "bullets": ["one point", "another point"], "notes": "say this"}
        for i in range(10)
    ]
    category, minutes = estimate_call("write_presentation", {"slides": slides}, {"slides_written": 10})
    assert category == "Decks"
    assert 55 <= minutes <= 90


def test_reading_a_twelve_page_pdf_is_costed_from_the_pages_not_the_tokens():
    category, minutes = estimate_call("read_document", {}, {"pages": 12})
    assert category == "Reading" and minutes == 18.0


def test_an_unknown_tool_costs_nothing():
    """Silence is the honest default — an uncosted tool must not inflate the number."""
    assert estimate_call("some_new_tool", {"x": 1}, {"ok": True}) == ("", 0.0)


def test_no_single_call_can_dominate_a_month_of_work():
    huge = {"slides": [{"title": "x" * 400, "bullets": ["y " * 300]} for _ in range(400)]}
    t = TimeSaved()
    assert t.add_call("write_presentation", huge, {"slides_written": 400}) == 45.0


def test_the_users_own_time_comes_off_the_top():
    t = TimeSaved()
    t.add_call("read_document", {}, {"pages": 12})  # 18 min of reading
    t.add_turn(120, approvals=2)  # 2 min waiting + 1.5 overhead + 1.0 approvals
    assert t.collab_minutes == 4.5
    assert t.saved_minutes == 13.5


def test_a_long_wait_is_capped_because_nobody_watches_for_an_hour():
    t = TimeSaved()
    t.add_turn(3600)
    assert t.collab_minutes == 11.5  # 10 capped + 1.5 overhead


def test_a_turn_that_saved_nothing_reads_as_zero_not_as_a_debt():
    t = TimeSaved()
    t.add_call("web_search", {"q": "x"}, {})  # 3 min
    t.add_turn(600)  # 11.5 min of the user's time
    assert t.human_minutes == 3.0
    assert t.saved_minutes == 0.0


def test_totals_survive_a_round_trip_and_merge_across_sessions():
    a = TimeSaved()
    a.add_call("write_document", {"blocks": [{"text": "word " * 200}]}, {})
    a.add_turn(60)
    b = TimeSaved.from_dict(a.as_dict())
    assert b.as_dict() == a.as_dict()
    b.merge(a)
    assert b.human_minutes == 2 * a.human_minutes
    assert b.turns == 2


def test_the_breakdown_names_categories_a_person_recognises():
    t = TimeSaved()
    t.add_call("write_presentation", {"slides": [{"title": "a"}]}, {"slides_written": 1})
    t.add_call("run_python", {"code": "print(1)"}, {})
    t.add_call("slack_send_message", {"channel": "x", "text": "hi"}, {})
    assert set(t.by_category) == {"Decks", "Analysis", "Connectors"}


# ── the EDGE profile, per Chapter 9 of the book ───────────────────────────


def test_edge_shares_all_four_pillars_and_sums_to_100():
    """Four axes, four shares. Growth and Empowerment are measured (see edge.py) —
    Growth from work that is new for this account, Empowerment from what the user
    learned — so neither is a decorative zero."""
    from coworker.edge import profile

    got = profile(
        {
            "Documents": 100.0,
            "Decks": 20.0,
            "Analysis": 60.0,
            "Growth": 40.0,
            "Capability": 20.0,
        }
    )
    shares = {p["key"]: p["percent"] for p in got["pillars"]}
    assert set(shares) == {"Efficiency", "Decisions", "Growth", "Empowerment"}
    assert sum(shares.values()) == 100
    assert shares["Efficiency"] == 50  # 120 of 240
    assert shares["Decisions"] == 25 and shares["Growth"] == 17
    assert got["total_minutes"] == 240.0 and got["leading"] == "Efficiency"


def test_a_deck_is_efficiency_growth_comes_from_novelty_instead():
    """Producing a deliverable faster is Efficiency however outward-facing it is.
    Growth is written by the install-wide novelty test, never by a tool, so no tool
    category may claim it directly."""
    from coworker.edge import CATEGORY_PILLARS

    assert CATEGORY_PILLARS["Decks"] == "Efficiency"
    assert CATEGORY_PILLARS["Connectors"] == "Efficiency"
    assert [k for k, v in CATEGORY_PILLARS.items() if v == "Growth"] == ["Growth"]


def test_edge_percentages_always_sum_to_exactly_100():
    from coworker.edge import profile

    for mix in (
        {"Documents": 1.0, "Analysis": 1.0},
        {"Documents": 7.0, "Analysis": 3.0, "Research": 3.0},
        {"Reading": 0.1, "Research": 0.2, "Decks": 0.3},
        {"Documents": 1.0, "Analysis": 1.0, "Growth": 1.0, "Capability": 1.0},
    ):
        assert sum(p["percent"] for p in profile(mix)["pillars"]) == 100


def test_edge_ignores_categories_it_cannot_place_rather_than_guessing():
    from coworker.edge import profile

    got = profile({"Documents": 60.0, "SomethingNew": 999.0})
    assert got["total_minutes"] == 60.0


def test_edge_hides_itself_when_there_is_too_little_to_shape():
    from coworker.edge import profile

    assert profile({"Documents": 20.0})["ready"] is False
    assert profile({})["ready"] is False and profile({})["leading"] == ""
    assert profile({"Documents": 45.0})["ready"] is True


def test_empowerment_is_what_you_learned_and_what_you_made_permanent():
    """Two shapes of learning: taken in (a method looked up) and made permanent (a
    skill, an automation, house rules). Without both, the axis could only ever read
    the second."""
    from coworker.edge import profile
    from coworker.timesaved import TimeSaved

    ts = TimeSaved()
    ts.add_call("kb_search", {}, {})          # learned something
    ts.add_call("save_skill", {}, {})         # made it permanent
    ts.add_call("create_scheduled_task", {}, {})
    ts.add_call("set_global_instructions", {}, {})
    assert ts.by_category["Learning"] == 4.0
    assert ts.by_category["Capability"] == 22.0
    got = {p["key"]: p["minutes"] for p in profile(ts.by_category)["pillars"]}
    assert got["Empowerment"] == 26.0


def test_a_knowledge_base_lookup_is_learning_not_a_connector_fetch():
    """`kb_search` matched the generic `*_search` rule and read as a connector
    fetch, which put "I looked a method up" under Efficiency."""
    from coworker.timesaved import estimate_call

    assert estimate_call("kb_search", {}, {})[0] == "Learning"
    assert estimate_call("slack_search", {}, {})[0] == "Connectors"


def test_minutes_are_recorded_per_tool_so_novelty_can_be_judged():
    from coworker.timesaved import TimeSaved

    ts = TimeSaved()
    ts.add_call("write_presentation", {"slides": [{"title": "x"}]}, {"slides_written": 1})
    ts.add_call("save_skill", {}, {})
    assert set(ts.by_tool) == {"write_presentation", "save_skill"}
    assert ts.tool_category("save_skill") == "Capability"
    assert sum(ts.by_tool.values()) == pytest.approx(sum(ts.by_category.values()))
    # And it survives the round trip the manager banks it through.
    back = TimeSaved.from_dict(ts.as_dict())
    assert back.by_tool == {k: round(v, 1) for k, v in ts.by_tool.items()}
    assert back.tool_categories == ts.tool_categories


# ── the Five A's, per Chapter 7 ───────────────────────────────────────────


def test_a_turn_is_placed_by_the_chapter_s_four_behavioural_questions():
    """§7.6's operational test, applied per turn: who initiates, is the path fixed,
    what can it touch, what does failure cost."""
    from coworker.fivea import classify_turn

    # The model alone. §7.1 is explicit that the modern wrapper — built-in web
    # search, file handling — is still Access, so searching the web is not a rung up.
    assert classify_turn() == "Access"
    assert classify_turn(tools=["web_search"]) == "Access"

    # Grounded in the user's own material: the RAG rung (§7.2). These are the REAL
    # tool names — an earlier cut listed `search_kb`, which does not exist, so
    # knowledge-base grounding never once counted.
    assert classify_turn(tools=["kb_search"]) == "Assistants"
    assert classify_turn(tools=["read_document"]) == "Assistants"

    # A skill is "task-specific, single-purpose ... built through natural-language
    # prompts" (§7.3) — one job, one fixed recipe.
    assert classify_turn(tools=["load_skill", "write_document"]) == "Applications"

    # Q1: a schedule initiated it and it followed the path it was given.
    assert classify_turn(tools=["write_document"], scheduled=True) == "Automation"

    # Q2: it chose its own next action.
    assert classify_turn(tools=["explore"]) == "Agents"
    assert classify_turn(planned=True) == "Agents"
    assert classify_turn(tools=[f"t{i}" for i in range(6)]) == "Agents"


def test_a_fixed_recipe_is_not_promoted_by_the_length_of_the_recipe():
    """Q2: "if the steps are predefined, it is an Automation regardless of how much
    AI sits inside the steps". A skill that calls nine tools still did not choose
    its own route — only an explicit plan or delegation does that."""
    from coworker.fivea import classify_turn

    long_recipe = ["load_skill"] + [f"t{i}" for i in range(9)]
    assert classify_turn(tools=long_recipe) == "Applications"
    assert classify_turn(tools=long_recipe, planned=True) == "Agents"


def test_agent_territory_needs_writes_across_systems_not_one_write():
    """Q3, and the plural in it: "read-only access to one system is Assistant
    territory; write access ACROSS SYSTEMS is agent territory". One user-directed
    Slack message is an action a person asked for, not a delegated goal."""
    from coworker.fivea import classify_turn

    assert classify_turn(tools=["slack_send_message"]) == "Access"
    assert classify_turn(tools=["slack_send_message", "kb_search"]) == "Assistants"
    # Two services written to in one turn is the line the chapter draws.
    assert classify_turn(tools=["slack_send_message", "gmail_create_draft"]) == "Agents"
    # Reads across many services stay read-only, so they stay below Agents.
    assert classify_turn(tools=["slack_search", "gmail_search"]) == "Access"


def test_a_scheduled_run_that_directs_itself_is_an_agent():
    """Q1 and Q2 are separate questions. A schedule starting a run makes it an
    Automation only while the path stays the one it was given; a scheduled run that
    plans its own way is what the chapter calls an Agent acting on events."""
    from coworker.fivea import classify_turn

    assert classify_turn(tools=["write_document"], scheduled=True) == "Automation"
    assert classify_turn(tools=["subagent"], scheduled=True) == "Agents"


def test_a_turn_counts_once_at_the_highest_rung_it_reached():
    """The continuum is about autonomy: a scheduled run that also ran a skill is
    Automation. Counting it twice would blur the axis the figure is built on."""
    from coworker.fivea import classify_turn

    assert (
        classify_turn(tools=["write_document", "load_skill"], scheduled=True)
        == "Automation"
    )


def test_five_a_reports_every_rung_even_at_zero():
    """A gap in the middle of a continuum is information."""
    from coworker.fivea import profile

    got = profile({"Access": 10})
    assert [level["key"] for level in got["levels"]] == [
        "Access",
        "Assistants",
        "Applications",
        "Automation",
        "Agents",
    ]
    assert got["leading"] == "Access" and got["ready"] is True
    assert sum(level["percent"] for level in got["levels"]) == 100
    assert profile({"Access": 3})["ready"] is False  # too few turns to be a habit


def test_building_an_automation_is_itself_the_automation_rung():
    """The owner set one up and the chart still read 100% Access. Creating an automation
    is the moment work stops needing a person to start it — which is exactly what the
    rung describes. Waiting for the first fire meant an account could set up ten of them
    and still look like it had never left Access (owner-hit 2026-08-31)."""
    from coworker.fivea import classify_turn

    assert classify_turn(tools=["create_scheduled_task"]) == "Automation"
    assert classify_turn(tools=["update_scheduled_task"]) == "Automation"
    # And the run it later produces is Automation too, by the schedule that started it.
    assert classify_turn(tools=["write_document"], scheduled=True) == "Automation"


def test_creating_an_automation_does_not_read_as_reaching_across_systems():
    """`create_scheduled_task` starts with a write verb by coincidence of naming; it
    writes to MimiWork's own schedule, not out to two services."""
    from coworker.fivea import classify_turn

    assert classify_turn(tools=["create_scheduled_task", "update_scheduled_task"]) == "Automation"
