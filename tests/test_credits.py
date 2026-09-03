"""Credits: one list, shown in the app and committed as CREDITS.md, always in step."""

from __future__ import annotations

from pathlib import Path

from coworker.credits import CREDITS, render_markdown

ROOT = Path(__file__).resolve().parents[1]


def test_credits_md_is_generated_from_the_list():
    # Edit coworker/credits.py, run scripts/build_credits_md.py, commit both.
    assert (ROOT / "CREDITS.md").read_text(encoding="utf-8") == render_markdown()


def test_every_entry_names_its_source_and_the_origin_is_first():
    assert CREDITS[0]["items"][0]["name"] == "OpenWorker"
    assert "Andrew Ng" in CREDITS[0]["items"][0]["what"]
    for section in CREDITS:
        assert section["title"] and section["items"]
        for item in section["items"]:
            assert item["name"] and item["url"].startswith("https://"), item


def test_the_about_page_carries_the_credits(tmp_path, monkeypatch):
    from helpers import CapturingProvider

    from coworker.server.manager import SessionManager

    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    m = SessionManager(data_dir=tmp_path / "data", provider=CapturingProvider())
    monkeypatch.setattr(SessionManager, "_fetch_releases", lambda self: [])
    about = m.about()
    titles = [s["title"] for s in about["credits"]]
    assert titles[0] == "Where it comes from" and "Bundled skills" in titles
    names = {i["name"] for s in about["credits"] for i in s["items"]}
    assert {"OpenWorker", "UI/UX Pro Max", "Coze Studio", "pdf.js"} <= names
