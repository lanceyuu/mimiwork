"""Bundled starter blueprints: shipped, well-formed, grant-free."""

from coworker.blueprints import builtin_blueprints


def test_weekly_research_digest_is_bundled_and_well_formed():
    entries = builtin_blueprints()
    names = [e["name"] for e in entries]
    assert "weekly-research-digest" in names
    bp = next(e["blueprint"] for e in entries if e["name"] == "weekly-research-digest")
    assert bp["mimiwork_blueprint"] == 1
    assert bp["title"] == "Weekly research digest"
    assert "kb_search" in bp["instructions"] and "Word document" in bp["instructions"]
    assert bp["schedule"] == {"kind": "cron", "cron": "0 8 * * 1"}
    assert bp["permissions"] == []  # read-only recipe: disclosure, never a grant


def test_builtin_blueprints_are_sorted_and_named_by_file():
    entries = builtin_blueprints()
    titles = [e["blueprint"]["title"].lower() for e in entries]
    assert titles == sorted(titles)
    assert all(".json" not in e["name"] for e in entries)
