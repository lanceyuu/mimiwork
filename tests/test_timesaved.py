"""The hours-saved estimate: grounded in artifacts, conservative, never negative.

The number sits in the composer and behind the logo, where a user can check it
against their own memory of the afternoon. That makes credibility the requirement:
every assertion here is really asking "would a professional recognise this figure?"
"""

from __future__ import annotations

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
