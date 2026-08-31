"""Growth: work that is new and very different.

The pillar is defined by the framework's author as the moment you reach for
something you have never reached for before, so it cannot be read off a tool
category — a session does not know what the account did last month. The test lives
install-wide in `SessionManager.record_time_saved`, and these are its rules:

* minutes MOVE into Growth, never add — the four pillars must keep summing to the
  same minutes as the hours-saved badge beside them;
* a tool is new exactly once;
* nothing counts during the warm-up, because in week one everything is new.
"""

from __future__ import annotations

from coworker.server.manager import SessionManager
from coworker.timesaved import TimeSaved


def _manager(tmp_path):
    return SessionManager(workspace=tmp_path, provider=None)


def _turn(**by_tool_and_category):
    """A cumulative session total, as the engine's turn_end event carries it."""
    ts = TimeSaved()
    for tool, (category, minutes) in by_tool_and_category.items():
        ts.by_tool[tool] = minutes
        ts.tool_categories[tool] = category
        ts.by_category[category] = ts.by_category.get(category, 0.0) + minutes
        ts.human_minutes += minutes
    return ts.as_dict()


def _warm(manager, count=8):
    """Give the account a habit to be different from."""
    manager._prefs["seen_tools"] = [f"old_tool_{i}" for i in range(count)]


def test_a_first_ever_tool_moves_its_minutes_into_growth(tmp_path):
    manager = _manager(tmp_path)
    _warm(manager)
    manager.record_time_saved("s1", _turn(write_presentation=("Decks", 30.0)))

    total = manager._prefs["time_saved"]
    assert total["by_category"].get("Growth") == 30.0
    # MOVED, not added: Decks kept nothing, and the human total is unchanged.
    assert "Decks" not in total["by_category"]
    assert total["human_minutes"] == 30.0
    assert sum(total["by_category"].values()) == total["human_minutes"]


def test_the_same_tool_is_new_only_once(tmp_path):
    """Otherwise every deck you ever build reads as breaking new ground."""
    manager = _manager(tmp_path)
    _warm(manager)
    manager.record_time_saved("s1", _turn(write_presentation=("Decks", 30.0)))
    # Same session, cumulative totals — the second turn adds 20 more minutes.
    manager.record_time_saved("s1", _turn(write_presentation=("Decks", 50.0)))

    by_cat = manager._prefs["time_saved"]["by_category"]
    assert by_cat["Growth"] == 30.0  # the first reach only
    assert by_cat["Decks"] == 20.0  # the repeat is ordinary efficiency
    assert manager._prefs["time_saved"]["human_minutes"] == 50.0


def test_nothing_is_growth_during_the_warm_up(tmp_path):
    """In week one every tool is new; a Growth axis at 100% would say nothing about
    the user, so novelty starts counting once there is a habit to depart from."""
    manager = _manager(tmp_path)
    manager.record_time_saved("s1", _turn(write_presentation=("Decks", 30.0)))

    by_cat = manager._prefs["time_saved"]["by_category"]
    assert "Growth" not in by_cat and by_cat["Decks"] == 30.0
    # …but the tool is still remembered, so it cannot be "new" later either.
    assert "write_presentation" in manager._prefs["seen_tools"]


def test_growth_never_invents_minutes_the_category_did_not_have(tmp_path):
    """A partial or replayed event must not let Growth exceed the work actually
    recorded — the badge and the radar would then disagree."""
    manager = _manager(tmp_path)
    _warm(manager)
    totals = _turn(run_python=("Analysis", 40.0))
    totals["by_category"]["Analysis"] = 10.0  # under-reports what by_tool claims

    manager.record_time_saved("s1", totals)
    by_cat = manager._prefs["time_saved"]["by_category"]
    assert by_cat.get("Growth", 0.0) == 10.0
    assert "Analysis" not in by_cat


def test_the_pillars_still_sum_to_the_hours_badge(tmp_path):
    """The one invariant the whole module rests on: the same minutes, grouped two
    ways. A relabel that leaked or duplicated a minute would put a number on the
    radar that contradicts the one behind the logo."""
    from coworker.edge import profile

    manager = _manager(tmp_path)
    _warm(manager)
    manager.record_time_saved(
        "s1",
        _turn(
            write_presentation=("Decks", 30.0),
            run_python=("Analysis", 45.0),
            save_skill=("Capability", 12.0),
            kb_search=("Learning", 4.0),
        ),
    )
    total = manager._prefs["time_saved"]
    got = profile(total["by_category"])
    assert got["total_minutes"] == total["human_minutes"] == 91.0
    assert sum(p["percent"] for p in got["pillars"]) == 100
