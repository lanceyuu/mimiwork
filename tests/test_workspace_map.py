"""Workspace map builder: ranking, pruning, budget, cache invalidation."""

import os
import time

import pytest

from coworker import workspace_map
from coworker.workspace_map import build_workspace_map


@pytest.fixture(autouse=True)
def _fresh_cache():
    workspace_map._cache.clear()
    yield
    workspace_map._cache.clear()


def _touch(path, mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_empty_workspace_yields_nothing(tmp_path):
    assert build_workspace_map(tmp_path) == ""


def test_missing_workspace_yields_nothing(tmp_path):
    assert build_workspace_map(tmp_path / "nope") == ""


def test_lists_folders_and_recent_files(tmp_path):
    now = time.time()
    _touch(tmp_path / "docs" / "report.docx", now - 60)
    _touch(tmp_path / "docs" / "notes.md", now - 3600)
    _touch(tmp_path / "data" / "results.csv", now - 120)
    out = build_workspace_map(tmp_path)
    assert "<workspace_map>" in out
    assert "docs/ (2)" in out
    assert "data/ (1)" in out
    assert os.path.join("docs", "report.docx") in out
    assert "may be stale" in out


def test_doc_boost_outranks_fresher_junk(tmp_path):
    now = time.time()
    _touch(tmp_path / "notes.md", now - 86400)  # a day old, but a document
    _touch(tmp_path / "trace.log", now - 60)  # fresh, but junk-ish
    out = build_workspace_map(tmp_path)
    assert out.index("notes.md") < out.index("trace.log")


def test_prunes_hidden_and_derived_dirs(tmp_path):
    _touch(tmp_path / "keep.md")
    _touch(tmp_path / "node_modules" / "pkg" / "index.js")
    _touch(tmp_path / ".git" / "config")
    _touch(tmp_path / "__pycache__" / "m.pyc")
    out = build_workspace_map(tmp_path)
    assert "keep.md" in out
    assert "node_modules" not in out
    assert ".git" not in out
    assert "__pycache__" not in out


def test_prunes_configured_app_state_inside_workspace(tmp_path, monkeypatch):
    state = tmp_path / "visible-state-name"
    _touch(state / "skills" / "private-skill" / "SKILL.md")
    _touch(tmp_path / "report.md")
    monkeypatch.setenv("COWORKER_STATE_DIR", str(state))

    out = build_workspace_map(tmp_path)

    assert "report.md" in out
    assert "visible-state-name" not in out
    assert "private-skill" not in out


def test_budget_cap_respected(tmp_path):
    for i in range(200):
        _touch(tmp_path / f"file_with_a_rather_long_name_{i:03d}.md")
    out = build_workspace_map(tmp_path, budget_chars=800)
    # Body (inside the tags) stays within the budget plus one line of slack.
    body = out.split("<workspace_map>\n")[1].split("\n</workspace_map>")[0]
    assert len(body) < 900
    assert "total files seen: 200" in out


def test_cache_hit_and_invalidation_on_change(tmp_path):
    _touch(tmp_path / "a.md")
    first = build_workspace_map(tmp_path)
    assert build_workspace_map(tmp_path) is first  # same object -> cache hit
    time.sleep(0.01)
    _touch(tmp_path / "b.md")  # changes the top-level signature
    second = build_workspace_map(tmp_path)
    assert "b.md" in second


def test_walk_cap_notes_truncation(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_map, "_MAX_ENTRIES", 10)
    for i in range(30):
        _touch(tmp_path / f"f{i}.md")
    out = build_workspace_map(tmp_path)
    assert "walk capped" in out
