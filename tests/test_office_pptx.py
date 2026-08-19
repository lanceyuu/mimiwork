"""PowerPoint: slide structure, speaker notes, and revise-an-existing-deck reads."""

import pytest

from coworker.agents.base import AgentContext
from coworker.roots import RootDir
from coworker.tools.office.pptx_tools import pptx_tools

pytest.importorskip("pptx", reason="python-pptx is an optional [office] extra")


@pytest.fixture
def tools(tmp_path):
    ws = tmp_path / "scratch"
    ws.mkdir()
    context = AgentContext(workspace=ws, roots=[RootDir(path=ws, writable=True)])
    return {t.__name__: t for t in pptx_tools(context)}, ws


def test_write_then_read_round_trips_titles_and_bullets(tools):
    write, read = tools[0]["write_presentation"], tools[0]["read_presentation"]
    out = write(
        "deck.pptx",
        [
            {"layout": "title", "title": "Q3 Review", "subtitle": "Finance"},
            {
                "layout": "bullets",
                "title": "Highlights",
                "bullets": ["Revenue +12%", "Churn -3%"],
            },
        ],
    )
    assert "error" not in out
    assert out["slides_written"] == 2

    deck = read("deck.pptx")
    assert deck["total_slides"] == 2
    assert deck["slides"][0]["title"] == "Q3 Review"
    assert deck["slides"][1]["title"] == "Highlights"
    assert "Revenue +12%" in deck["slides"][1]["bullets"]


def test_speaker_notes_round_trip(tools):
    """A deck without notes isn't a finished deliverable, so notes must survive."""
    write, read = tools[0]["write_presentation"], tools[0]["read_presentation"]
    write(
        "deck.pptx",
        [
            {
                "layout": "bullets",
                "title": "Method",
                "bullets": ["Two-sample t-test"],
                "notes": "Explain why we dropped the 14 incomplete responses.",
            }
        ],
    )
    deck = read("deck.pptx")
    assert "14 incomplete responses" in deck["slides"][0]["notes"]


def test_sub_bullets_keep_their_level(tools):
    write, read = tools[0]["write_presentation"], tools[0]["read_presentation"]
    write(
        "deck.pptx",
        [
            {
                "layout": "bullets",
                "title": "Detail",
                "bullets": ["Top", {"text": "Nested", "level": 1}],
            }
        ],
    )
    bullets = read("deck.pptx")["slides"][0]["bullets"]
    assert any(b.startswith("  ") and "Nested" in b for b in bullets)


def test_slides_are_numbered_for_revision(tools):
    write, read = tools[0]["write_presentation"], tools[0]["read_presentation"]
    write("d.pptx", [{"layout": "bullets", "title": f"S{i}"} for i in range(4)])
    assert [s["index"] for s in read("d.pptx")["slides"]] == [0, 1, 2, 3]


def test_append_adds_slides_to_an_existing_deck(tools):
    write, read = tools[0]["write_presentation"], tools[0]["read_presentation"]
    write("d.pptx", [{"layout": "title", "title": "One"}])
    write("d.pptx", [{"layout": "bullets", "title": "Two"}], append=True)
    deck = read("d.pptx")
    assert deck["total_slides"] == 2
    assert [s["title"] for s in deck["slides"]] == ["One", "Two"]


def test_section_and_blank_layouts_are_accepted(tools):
    write = tools[0]["write_presentation"]
    out = write(
        "d.pptx",
        [
            {"layout": "section", "title": "Part II"},
            {"layout": "blank"},
        ],
    )
    assert "error" not in out
    assert out["slides_written"] == 2


def test_unknown_layout_is_reported_clearly(tools):
    result = tools[0]["write_presentation"]("d.pptx", [{"layout": "carousel"}])
    assert "error" in result and "carousel" in result["error"]


def test_image_slide_embeds_a_picture_from_the_workspace(tools):
    write, ws = tools[0]["write_presentation"], tools[1]
    png = ws / "chart.png"
    # Smallest valid 1x1 PNG.
    png.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753"
            "de0000000c4944415408d76360000000020001e221bc330000000049454e44ae426082"
        )
    )
    out = write("d.pptx", [{"layout": "image", "title": "Trend", "image": "chart.png"}])
    assert "error" not in out


def test_missing_image_errors_rather_than_producing_a_broken_deck(tools):
    result = tools[0]["write_presentation"](
        "d.pptx", [{"layout": "image", "title": "T", "image": "nope.png"}]
    )
    assert "error" in result


def test_write_outside_the_workspace_is_refused(tools):
    result = tools[0]["write_presentation"]("/tmp/escape.pptx", [{"layout": "blank"}])
    assert "error" in result and "escapes" in result["error"]


def test_reading_a_missing_deck_errors_cleanly(tools):
    assert "error" in tools[0]["read_presentation"]("nope.pptx")
