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


# --- the design system (added 2026-08-25, when decks stopped being 4:3 Calibri) --------


def test_a_new_deck_is_widescreen_not_the_4_3_default(tools):
    """python-pptx's stock template is 10x7.5in. A 4:3 deck is letterboxed on every
    modern screen and is the single loudest 'this looks old' signal a slide sends."""
    import pptx

    write, ws = tools[0]["write_presentation"], tools[1]
    out = write("deck.pptx", [{"layout": "title", "title": "Q3"}])
    assert out["widescreen"] is True
    deck = pptx.Presentation(str(ws / "deck.pptx"))
    assert round(deck.slide_width / deck.slide_height, 3) == round(16 / 9, 3)


def test_new_decks_carry_the_qualitati_theme(tools):
    import pptx

    from coworker.tools.office.deck_theme import read_theme

    write, ws = tools[0]["write_presentation"], tools[1]
    write("deck.pptx", [{"layout": "bullets", "title": "T", "bullets": ["a"]}])
    theme = read_theme(pptx.Presentation(str(ws / "deck.pptx")))
    assert theme.heading == "Instrument Serif"
    assert theme.body == "Arial"
    assert (theme.ink, theme.bg, theme.accent) == (0x111C1B, 0xFAFAF7, 0x0B7C72)


def test_bullets_are_real_bullet_formatting_not_glued_to_the_text(tools):
    """A marker in the string would come back on read and be prefixed again on the next
    write — 'Revenue' becoming '— — Revenue' after two revisions."""
    write, read = tools[0]["write_presentation"], tools[0]["read_presentation"]
    write("deck.pptx", [{"layout": "bullets", "title": "T", "bullets": ["Revenue +12%"]}])
    back = read("deck.pptx")["slides"][0]["bullets"]
    assert back == ["Revenue +12%"]


def test_the_printed_slide_number_is_not_read_back_as_content(tools):
    write, read = tools[0]["write_presentation"], tools[0]["read_presentation"]
    write(
        "deck.pptx",
        [
            {"layout": "bullets", "title": "One", "bullets": ["x"]},
            {"layout": "bullets", "title": "Two", "bullets": ["y"]},
        ],
    )
    for slide in read("deck.pptx")["slides"]:
        assert "2" not in slide["bullets"] and slide["bullets"] != []


def test_every_layout_renders_and_keeps_its_title_readable(tools):
    """Titles live in the real title placeholder — outline view, the slide sorter, and
    read_presentation all depend on it, which is how a deck stays revisable."""
    write, read = tools[0]["write_presentation"], tools[0]["read_presentation"]
    write(
        "deck.pptx",
        [
            {"layout": "title", "title": "Opener", "subtitle": "sub"},
            {"layout": "section", "title": "Part one"},
            {"layout": "statement", "statement": "Mobile is the problem."},
            {"layout": "stat", "title": "Numbers", "stats": [{"value": "71%", "label": "on a phone"}]},
            {"layout": "quote", "title": "Voice", "quote": "It was too long.", "attribution": "R12"},
            {
                "layout": "two_column",
                "title": "Split",
                "columns": [{"heading": "A", "bullets": ["one"]}, {"heading": "B", "bullets": ["two"]}],
            },
            {
                "layout": "comparison",
                "title": "Before and after",
                "columns": [{"heading": "Before", "bullets": ["slow"]}, {"heading": "After", "bullets": ["fast"]}],
            },
        ],
    )
    deck = read("deck.pptx")
    assert deck["total_slides"] == 7
    titles = [s["title"] for s in deck["slides"]]
    assert titles[:2] == ["Opener", "Part one"]
    assert titles[2] == "Mobile is the problem."  # the claim IS the title
    assert titles[4] == "Voice"
    assert "one" in deck["slides"][5]["bullets"] and "two" in deck["slides"][5]["bullets"]


def test_a_layout_that_is_missing_its_own_content_says_which_field(tools):
    write = tools[0]["write_presentation"]
    assert "stats" in write("d.pptx", [{"layout": "stat", "title": "T"}])["error"]
    assert "columns" in write("d.pptx", [{"layout": "two_column", "title": "T"}])["error"]
    assert "image" in write("d.pptx", [{"layout": "image", "title": "T"}])["error"]


def test_a_house_template_outranks_the_built_in_theme(tools, tmp_path):
    """Passing template= is how someone says 'use our brand'. Ours must step aside."""
    import pptx

    from coworker.tools.office.deck_theme import read_theme

    write, ws = tools[0]["write_presentation"], tools[1]
    house = pptx.Presentation()
    house.save(str(ws / "house.pptx"))  # stock template = Calibri, the brand here
    write("deck.pptx", [{"layout": "bullets", "title": "T", "bullets": ["a"]}], template="house.pptx")
    deck = pptx.Presentation(str(ws / "deck.pptx"))
    assert read_theme(deck).heading == "Calibri"
    assert deck.slide_width == house.slide_width


def test_appending_never_reflows_someone_elses_deck(tools):
    """Resizing a 4:3 deck we were merely asked to add slides to would silently re-lay
    out every slide already in it."""
    import pptx

    write, ws = tools[0]["write_presentation"], tools[1]
    original = pptx.Presentation()  # 4:3
    original.slides.add_slide(original.slide_layouts[1])
    original.save(str(ws / "theirs.pptx"))
    write("theirs.pptx", [{"layout": "bullets", "title": "Added", "bullets": ["x"]}], append=True)
    after = pptx.Presentation(str(ws / "theirs.pptx"))
    assert after.slide_width == 9144000  # still 4:3 — we added to it, we didn't restyle it
    assert len(list(after.slides)) == 2


# --- text fitting (owner report 2026-08-26: "font sometimes too big, exceeds the frame")


def test_a_long_title_shrinks_instead_of_walking_out_of_its_frame(tools):
    """No renderer exists at runtime to screenshot-and-check, so the type must yield to
    the box deterministically."""
    import pptx
    from pptx.util import Pt

    write, ws = tools[0]["write_presentation"], tools[1]
    long_title = (
        "Why the onboarding survey completion rate collapsed on mobile devices "
        "between the June and August fieldwork waves across all three markets"
    )
    write(
        "deck.pptx",
        [
            {"layout": "bullets", "title": "Short", "bullets": ["a"]},
            {"layout": "bullets", "title": long_title, "bullets": ["a"]},
        ],
    )
    deck = pptx.Presentation(str(ws / "deck.pptx"))
    sizes = []
    for slide in deck.slides:
        run = slide.shapes.title.text_frame.paragraphs[0].runs[0]
        sizes.append(run.font.size)
    assert sizes[0] == Pt(34)  # short keeps the scale
    assert sizes[1] < sizes[0]  # long yields to the box


def test_a_reasonable_deck_carries_no_layout_warnings(tools):
    out = tools[0]["write_presentation"](
        "deck.pptx",
        [{"layout": "bullets", "title": "Fine", "bullets": ["one", "two", "three"]}],
    )
    assert "layout_warnings" not in out


def test_an_overstuffed_slide_is_flagged_for_the_model_to_split(tools):
    """The deck still saves — shrunk to the floor — but the result says which slide
    holds more than fits and what to do. The prompt forbids handing that over."""
    out = tools[0]["write_presentation"](
        "deck.pptx",
        [
            {"layout": "bullets", "title": "Fine", "bullets": ["a"]},
            {
                "layout": "bullets",
                "title": "Everything at once",
                "bullets": [
                    f"Finding number {i}: a long sentence that wraps at least once at body size"
                    for i in range(18)
                ],
            },
        ],
    )
    assert out["slides_written"] == 2  # saved, not refused
    warnings = out["layout_warnings"]
    assert len(warnings) == 1 and warnings[0].startswith("slide 2:")
    assert "split" in warnings[0]
    assert "write_presentation again" in out["action_required"]


def test_a_long_quote_shrinks_and_the_attribution_stays_below_it(tools):
    import pptx
    from pptx.util import Pt

    write, ws = tools[0]["write_presentation"], tools[1]
    write(
        "deck.pptx",
        [
            {
                "layout": "quote",
                "quote": (
                    "I started the survey on my phone during my commute and gave up "
                    "halfway through the third matrix grid because I had to scroll "
                    "sideways on every single row just to see the answer labels, and "
                    "by then my train had reached the station. I tried again that "
                    "evening on my laptop and got further, but the progress bar had "
                    "reset to zero, all my earlier answers were gone, and the grid "
                    "questions were exactly as unreadable as before, so I closed the "
                    "tab and decided the gift card was not worth a third attempt."
                ),
                "attribution": "Respondent 3,118",
            }
        ],
    )
    deck = pptx.Presentation(str(ws / "deck.pptx"))
    slide = list(deck.slides)[0]
    quote_run = next(
        shape.text_frame.paragraphs[0].runs[0]
        for shape in slide.shapes
        if shape.has_text_frame and "matrix grid" in shape.text_frame.text
    )
    assert quote_run.font.size < Pt(28)


def test_the_fit_estimator_is_monotonic_and_floored():
    from coworker.tools.office.deck_render import fitted_size

    box = dict(width_in=11.6, height_in=0.9, size=28, min_size=18, bold=True)
    short = fitted_size("Findings", **box)
    long = fitted_size("A title that goes on and on " * 6, **box)
    absurd = fitted_size("word " * 400, **box)
    assert short == 28
    assert 18 <= long < 28
    assert absurd == 18  # never below the floor — past that it's a writing problem


def test_editorial_split_keeps_photo_text_and_credit_editable(tools):
    import pptx
    from PIL import Image
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    write, read, ws = tools[0]["write_presentation"], tools[0]["read_presentation"], tools[1]
    Image.new("RGB", (600, 300)).save(ws / "scene.jpg")
    write("deck.pptx", [{"layout": "photo_split", "title": "A new setting",
                         "subtitle": "The group meets in the field.", "image": "scene.jpg", "photo_focus": 0.25,
                         "notes": "Photo credit: Field team"}])
    deck = pptx.Presentation(ws / "deck.pptx")
    picture = next(s for s in deck.slides[0].shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE)
    assert picture.width * 2 == deck.slide_width and picture.height == deck.slide_height
    assert 0 < picture.crop_left < picture.crop_right < 0.5
    assert read("deck.pptx")["slides"][0] == {
        "index": 0, "title": "A new setting", "bullets": ["The group meets in the field."],
        "notes": "Photo credit: Field team",
    }


def test_title_blocks_start_with_the_title_and_statistics_keep_their_context(tools):
    import pptx

    write, read, ws = tools[0]["write_presentation"], tools[0]["read_presentation"], tools[1]
    write("deck.pptx", [{"layout": kind, "title": "A finding"} for kind in
                        ("title", "section", "statement")] + [
        {"layout": "stat", "title": "Most teams finished", "stats": [
            {"value": "68%", "label": "finished the survey"}]},
    ])
    deck = pptx.Presentation(ws / "deck.pptx")
    for slide in deck.slides:
        assert all(shape.top >= slide.shapes.title.top for shape in slide.shapes)
        assert not slide.shapes.title.text_frame.paragraphs[0].runs[0].font.bold
    assert read("deck.pptx")["slides"][-1]["bullets"] == ["68% finished the survey"]


def test_a_requested_palette_and_typefaces_survive_appending(tools):
    import pptx

    from coworker.tools.office.deck_theme import read_theme

    write, ws = tools[0]["write_presentation"], tools[1]
    style = {"heading": "Georgia", "body": "Arial", "ink": "#FFFFFF", "bg": "#000000"}
    write("deck.pptx", [{"layout": "title", "title": "An evening briefing"}], style=style)
    write("deck.pptx", [{"layout": "section", "title": "The outcome"}], append=True)
    deck = pptx.Presentation(ws / "deck.pptx")
    theme = read_theme(deck)
    assert (theme.heading, theme.body, theme.bg, theme.ink) == ("Georgia", "Arial", 0, 0xFFFFFF)
    for slide in deck.slides:
        assert slide.shapes.title.text_frame.paragraphs[0].runs[0].font.name == "Georgia"


# -- a look the layouts cannot draw, and seeing the result -------------------------

import importlib  # noqa: E402

# The package exports a function of the same name, which hides the module.
_pptx_module = importlib.import_module("coworker.tools.office.pptx_tools")

_REAL_SOFFICE = _pptx_module._soffice


def _libreoffice_runs() -> bool:
    """A leftover launcher can outlive the application it points at."""
    import subprocess

    exe = _REAL_SOFFICE()
    try:
        return bool(exe) and subprocess.run(
            [exe, "--version"], capture_output=True, timeout=60
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _picture(path, size=(400, 300)):
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "#D9D9D9").save(path)
    return path


def test_a_background_picture_fills_the_slide_and_sits_behind_the_words(tools):
    import pptx

    write, ws = tools[0]["write_presentation"], tools[1]
    _picture(ws / "paper.png")
    _picture(ws / "cover.png")
    out = write(
        "deck.pptx",
        [
            {"layout": "bullets", "title": "Paris", "bullets": ["Seine"]},
            {"layout": "title", "title": "Bonjour", "background": "cover.png"},
        ],
        style={"background": "paper.png"},
    )
    assert "error" not in out
    deck = pptx.Presentation(ws / "deck.pptx")
    for slide in deck.slides:
        back = slide.shapes[0]
        assert back.shape_type == pptx.enum.shapes.MSO_SHAPE_TYPE.PICTURE
        assert (back.left, back.top, back.width, back.height) == (
            0, 0, deck.slide_width, deck.slide_height)
        # 4:3 into 16:9 is cropped top and bottom, never stretched
        assert back.crop_top == back.crop_bottom > 0


def test_a_style_skill_can_supply_pictures_but_nothing_else_outside_the_folders(tools, tmp_path):
    from coworker.secrets import state_dir

    write = tools[0]["write_presentation"]
    skill = state_dir() / "skills" / "cute-school"
    backdrop = _picture(skill / "paper.png")
    (skill / "SKILL.md").write_text("words", encoding="utf-8")
    stray = _picture(tmp_path / "private" / "photo.png")

    slide = {"layout": "title", "title": "Bonjour"}
    assert "error" not in write("a.pptx", [{**slide, "background": str(backdrop)}])
    assert "escapes" in write("b.pptx", [{**slide, "background": str(stray)}])["error"]
    assert "escapes" in write("c.pptx", [{**slide, "background": str(skill / "SKILL.md")}])["error"]


def test_without_a_renderer_a_deck_still_saves_and_says_it_cannot_be_shown(tools):
    write, read = tools[0]["write_presentation"], tools[0]["read_presentation"]
    out = write("deck.pptx", [{"layout": "title", "title": "Bonjour"}])
    assert "error" not in out and "_images" not in out
    seen = read("deck.pptx", show_slides=[1])
    assert "_images" not in seen and "LibreOffice" in seen["show_slides_note"]


@pytest.mark.skipif(not _libreoffice_runs(), reason="needs LibreOffice to draw slides")
def test_finished_slides_come_back_as_pictures_to_look_at(tools, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(_pptx_module, "_soffice", _REAL_SOFFICE)
    write, read = tools[0]["write_presentation"], tools[0]["read_presentation"]
    out = write("deck.pptx", [{"layout": "title", "title": f"Slide {n}"} for n in range(1, 7)])
    assert len(out["_images"]) == 4 and "slides 1-4" in out["shown"]
    assert "not the typeface" in out["shown"]
    with Image.open(out["_images"][0]) as picture:
        assert picture.width > picture.height
    assert [p[-10:] for p in read("deck.pptx", show_slides=[6, 2])["_images"]] == [
        "page-2.jpg", "page-6.jpg"]


def _body_sizes(ws, name="deck.pptx"):
    """Per slide, the point size of every body run (the title and page number left out)."""
    import pptx

    from coworker.tools.office.deck_render import FOOTER_SHAPE_NAME

    out = []
    for slide in pptx.Presentation(str(ws / name)).slides:
        out.append([
            run.font.size.pt
            for shape in slide.shapes
            if shape.has_text_frame and shape != slide.shapes.title and shape.name != FOOTER_SHAPE_NAME
            for para in shape.text_frame.paragraphs
            for run in para.runs
        ])
    return out


def test_a_short_list_is_set_large_enough_to_read_from_the_back_of_the_room(tools):
    """Seen on five real decks (2026-11-19): three bullets at 18 points left two thirds of
    every slide empty. Type shrinks to fit a full slide, so it must also grow on a sparse one."""
    write, ws = tools[0]["write_presentation"], tools[1]
    few = ["Set a steady rhythm", "Show work in progress", "Meet once at kickoff"]
    many = [f"Point number {n} with a few more words to fill the line" for n in range(1, 10)]
    out = write("deck.pptx", [
        {"layout": "bullets", "title": "Few", "bullets": few},
        {"layout": "bullets", "title": "Many", "bullets": many},
        {"layout": "two_column", "title": "Sides", "columns": [
            {"heading": "Before", "bullets": ["Seen at a desk", "Hallway updates"]},
            {"heading": "After", "bullets": ["Clear owners", "Visible progress"]}]},
    ])
    assert "layout_warnings" not in out
    sparse, full, sides = _body_sizes(ws)
    assert min(sparse) >= 24
    assert max(full) < min(sparse)
    assert min(size for size in sides) >= 22


def test_a_title_that_states_an_idea_wraps_to_two_lines_before_it_shrinks(tools):
    """The tool asks for a title that states the idea, which is a sentence. One line of room
    shrank every such title to about 25 points while the short ones stayed at 34."""
    import pptx
    from pptx.util import Pt

    write, ws = tools[0]["write_presentation"], tools[1]
    idea = "Trust has two bases, and remote work affects both differently"
    write("deck.pptx", [{"layout": "bullets", "title": idea, "bullets": ["a"]}])
    slide = pptx.Presentation(str(ws / "deck.pptx")).slides[0]
    title = slide.shapes.title
    assert title.text_frame.paragraphs[0].runs[0].font.size == Pt(34)
    body = next(s for s in slide.shapes if s.has_text_frame and s != title and "a" == s.text_frame.text)
    assert title.top + title.height <= body.top


def test_a_statistic_is_a_number_seen_from_the_back_with_its_label_beside_it(tools):
    """The stat layout promised "a number that carries it" and drew an ordinary line of
    body text. The number and its label stay one paragraph, so they are read together."""
    import pptx

    write, read, ws = tools[0]["write_presentation"], tools[0]["read_presentation"], tools[1]
    write("deck.pptx", [{"layout": "stat", "title": "Meeting once pays", "stats": [
        {"value": "23%", "label": "higher trust after six months"},
        {"value": "1,400", "label": "engineers in the study"}]}])
    slide = pptx.Presentation(str(ws / "deck.pptx")).slides[0]
    rows = [p for s in slide.shapes if s.has_text_frame and s != slide.shapes.title
            for p in s.text_frame.paragraphs if "23%" in p.text]
    value, label = rows[0].runs[0], rows[0].runs[-1]
    assert value.text.strip() == "23%" and value.font.size.pt >= 54
    assert label.font.size.pt < value.font.size.pt
    assert read("deck.pptx")["slides"][0]["bullets"][0] == "23% higher trust after six months"


def test_a_deck_rewritten_over_and_over_in_one_request_is_slowed_and_then_stopped(tmp_path, monkeypatch):
    """Seen on real runs (2026-11-19): shown its own slides, the free-tier model wrote the
    whole deck six and seven times for changes of wording, and went on past a note asking
    it to stop. The next request starts the count again: a change the person asks for is
    not a loop."""
    monkeypatch.setattr(_pptx_module, "slide_pictures", lambda deck, numbers: (["one.jpg"], ""))
    context = AgentContext(workspace=tmp_path, roots=[RootDir(path=tmp_path, writable=True)])
    write = {t.__name__: t for t in pptx_tools(context)}["write_presentation"]
    deck = [{"layout": "title", "title": "Bonjour"}]
    first, second, third, fourth = (write("deck.pptx", deck) for _ in range(4))
    assert "_images" in first and "_images" in second and "rewritten" not in second
    assert "_images" not in third and "version 3" in third["rewritten"]
    assert "error" not in fourth
    saved = (tmp_path / "deck.pptx").read_bytes()
    fifth = write("deck.pptx", [{"layout": "title", "title": "Encore"}])
    assert "written 4 times" in fifth["error"] and (tmp_path / "deck.pptx").read_bytes() == saved
    # Another deck, and slides added to this one, are not rewrites of it.
    assert "_images" in write("other.pptx", deck)
    assert "error" not in write("deck.pptx", deck, append=True)
    context.turn += 1
    assert "_images" in write("deck.pptx", deck)


def test_a_new_request_is_counted_for_the_tools(tmp_path):
    from helpers import ScriptedProvider

    from coworker.engine import TurnEngine
    from coworker.permissions import PermissionEngine
    from coworker.providers import AssistantTurn
    from coworker.tools.registry import ToolRegistry

    context = AgentContext(workspace=tmp_path)
    engine = TurnEngine(
        provider=ScriptedProvider([AssistantTurn(text="One."), AssistantTurn(text="Two.")]),
        registry=ToolRegistry(), permissions=PermissionEngine(tmp_path), model="m",
    )
    engine.tool_context = context

    async def ask(text):
        async for _ in engine.run(text):
            pass

    import asyncio

    asyncio.run(ask("first"))
    asyncio.run(ask("second"))
    assert context.turn == 2


def test_a_blank_slide_given_words_is_refused_instead_of_dropping_them(tools):
    """Real run, 2026-11-19: a 'blank' slide with a title came out empty, and the model
    spent five rewrites of the whole deck trying to find out why."""
    write = tools[0]["write_presentation"]
    out = write("d.pptx", [{"layout": "blank", "title": "Trust travels through a loop"}])
    assert "blank" in out["error"] and "bullets" in out["error"]
    assert "error" not in write("d.pptx", [{"layout": "blank", "notes": "Pause here."}])


def test_writing_the_renderer_dropped_is_noticed():
    """LibreOffice on a Mac drew no Chinese at all (2026-11-19): every slide came back
    blank but for its quotation marks and page number."""
    lost = _pptx_module._lost_writing
    assert lost("远程办公如何影响团队信任？", "“ ” 2")
    assert not lost("远程办公如何影响团队信任？", "远程办公如何影响团队信任？ 2")
    assert not lost("Remote work changes trust", "")  # Latin text is not judged this way
    assert not lost("MBA 课堂", "MBA")  # too little to tell


def test_blank_pictures_are_not_shown_as_what_the_deck_looks_like(tools, monkeypatch):
    """Shown its Chinese deck as blank slides, the model decided the deck was broken and
    rebuilt it by script, with the words baked into pictures (real run, 2026-11-19)."""
    monkeypatch.setattr(_pptx_module, "slide_pictures", lambda deck, numbers: ([], _pptx_module._LOST_WRITING))
    write, read = tools[0]["write_presentation"], tools[0]["read_presentation"]
    out = write("deck.pptx", [{"layout": "title", "title": "远程办公如何影响团队信任？"}])
    assert "_images" not in out and "not affected" in out["shown"]
    seen = read("deck.pptx", show_slides=[1])
    assert "_images" not in seen and "not affected" in seen["show_slides_note"]


def test_a_photograph_can_fill_the_slide_with_the_words_in_white_over_it(tools):
    """Owner, 2026-11-19: "the default slide style should still be image first". His own
    rule for it: a photo as background under a dark scrim for questions, breaks and dividers."""
    import pptx
    from PIL import Image
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    write, read, ws = tools[0]["write_presentation"], tools[0]["read_presentation"], tools[1]
    Image.new("RGB", (1200, 500), "#446").save(ws / "harbour.jpg")
    out = write("deck.pptx", [{"layout": "photo", "title": "Where is home for you?",
                               "subtitle": "Two minutes, in pairs", "image": "harbour.jpg"}])
    assert "error" not in out
    deck = pptx.Presentation(ws / "deck.pptx")
    shapes = list(deck.slides[0].shapes)
    picture = next(s for s in shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE)
    assert (picture.width, picture.height) == (deck.slide_width, deck.slide_height)
    scrim = next(s for s in shapes if s.name == "mimiwork-photo-scrim")
    title = deck.slides[0].shapes.title
    # Drawn bottom to top: the photograph, the scrim that darkens it, then the words.
    assert shapes.index(picture) < shapes.index(scrim) < shapes.index(title)
    assert title.text_frame.paragraphs[0].runs[0].font.color.rgb == RGBColor(0xFF, 0xFF, 0xFF)
    assert read("deck.pptx")["slides"][0]["title"] == "Where is home for you?"
    assert "image" in write("d.pptx", [{"layout": "photo", "title": "No picture"}])["error"]


def test_a_few_lines_can_sit_beside_a_half_page_photograph(tools):
    import pptx
    from PIL import Image

    write, read, ws = tools[0]["write_presentation"], tools[0]["read_presentation"], tools[1]
    Image.new("RGB", (600, 600)).save(ws / "scene.jpg")
    lines = ["Set a steady rhythm", "Show work in progress", "Meet once at kickoff"]
    out = write("deck.pptx", [{"layout": "photo_split", "title": "Three routines rebuild trust",
                               "bullets": lines, "image": "scene.jpg"}])
    assert "layout_warnings" not in out
    deck = pptx.Presentation(ws / "deck.pptx")
    slide = deck.slides[0]
    body = next(s for s in slide.shapes if s.has_text_frame and "steady rhythm" in s.text_frame.text)
    assert body.left + body.width <= deck.slide_width / 2
    assert body.top >= slide.shapes.title.top + slide.shapes.title.height
    assert read("deck.pptx")["slides"][0]["bullets"] == lines


def test_a_new_deck_short_of_photographs_is_told_so_once(tools, monkeypatch):
    """Told in its instructions to build around photographs, Wolf still wrote "no stock
    photos, I'll keep it text-driven" and Puppy saved one picture for eight slides (live
    runs, 2026-11-19). A result the model has to answer works where a paragraph did not."""
    from PIL import Image

    monkeypatch.setattr(_pptx_module, "slide_pictures", lambda deck, numbers: ([], ""))
    write, ws = tools[0]["write_presentation"], tools[1]
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        Image.new("RGB", (1200, 800)).save(ws / name)
    words = [{"layout": "bullets", "title": f"Point {n}", "bullets": ["one"]} for n in range(1, 9)]
    # None at all is a gap in the file itself, said every time and again when the model
    # calls the deck ready (the engine reopens it): see the finished-file check.
    plain = write("plain.pptx", words)
    assert "pictures" not in plain
    assert any("photograph" in issue and "search_slide_photos" in issue for issue in plain["verification"]["issues"])
    # Enough photographs, each used once: nothing to say.
    shown = [{"layout": "photo_split", "title": "Open", "image": "a.jpg"}, *words[:5],
             {"layout": "photo", "title": "Ask", "image": "b.jpg"}, {"layout": "photo", "title": "Close", "image": "c.jpg"}]
    assert "pictures" not in write("shown.pptx", shown)
    # One photograph on three slides is one photograph.
    same = [{"layout": "photo", "title": f"Again {n}", "image": "a.jpg"} for n in range(3)] + words[:5]
    one = write("one.pptx", [{"layout": "photo_split", "title": "Open", "image": "a.jpg"}, *words[:7]])
    assert any("1 photograph" in issue for issue in one["verification"]["issues"])
    few = write("same.pptx", same)
    assert "3 photographs" in few["pictures"] and "search_slide_photos" in few["pictures"]
    assert "verification" not in few
    # A short deck, slides added to a deck, and a second look at the same deck are left alone.
    assert "pictures" not in write("short.pptx", words[:2])
    assert "pictures" not in write("plain.pptx", words[:1], append=True)
    assert "pictures" not in write("plain.pptx", words)


def test_a_deck_on_a_house_template_is_not_asked_for_photographs(tools, tmp_path):
    import pptx

    house = pptx.Presentation()
    house.save(str(tools[1] / "house.pptx"))
    words = [{"layout": "bullets", "title": f"Point {n}", "bullets": ["one"]} for n in range(1, 7)]
    out = tools[0]["write_presentation"]("deck.pptx", words, template="house.pptx")
    assert "pictures" not in out and "verification" not in out
    # Nor is a deck in a style the person chose, or a short one in the default style.
    assert "verification" not in tools[0]["write_presentation"]("own.pptx", words, style={"heading": "Georgia", "bg": "#FFFFFF"})
    assert "verification" not in tools[0]["write_presentation"]("short.pptx", words[:3])


def test_slides_looked_at_again_and_again_in_one_request_stop_being_shown(tmp_path, monkeypatch):
    """Real run, 2026-11-19: with the rewrites capped, the free-tier model went on asking to
    see the same nine slides, fifteen times in six minutes, finding nothing to change."""
    monkeypatch.setattr(_pptx_module, "slide_pictures", lambda deck, numbers: (["one.jpg"], ""))
    context = AgentContext(workspace=tmp_path, roots=[RootDir(path=tmp_path, writable=True)])
    kit = {t.__name__: t for t in pptx_tools(context)}
    kit["write_presentation"]("deck.pptx", [{"layout": "title", "title": f"Slide {n}"} for n in range(1, 9)])
    looks = [kit["read_presentation"]("deck.pptx", show_slides=[5, 6, 7, 8]) for _ in range(5)]
    assert all("_images" in look for look in looks[:4])
    assert "_images" not in looks[4] and "already" in looks[4]["show_slides_note"]
    context.turn += 1
    assert "_images" in kit["read_presentation"]("deck.pptx", show_slides=[1])


def test_a_credits_slide_with_long_links_is_set_small_enough_to_stay_on_the_slide(tools):
    """A link has no space to break at, so it drops whole to the next line and a list of
    photo credits ran off the bottom of the slide (live deck, 2026-11-19)."""
    from coworker.tools.office.deck_render import text_lines

    credit = "Video Teleconference BLC by U.S. Army photo by Spc. Ryan Lucas, Public domain, https://commons.wikimedia.org/wiki/File:Video_Teleconference_BLC_(6181786).jpg"
    words = "Video Teleconference BLC by the U.S. Army, photographed by Specialist Ryan Lucas and placed in the public domain on Wikimedia Commons in the year 2011"
    assert text_lines(credit, 11.6, 26) > text_lines(words, 11.6, 26)
    write, ws = tools[0]["write_presentation"], tools[1]
    credits = [credit, *[f"Home Office {n} by Kristin Hardwick, CC0, https://stocksnap.io/photo/home-office-D3OTBIDS9{n}" for n in range(3)]]
    write("deck.pptx", [{"layout": "bullets", "title": "Photo credits", "bullets": credits}])
    assert max(_body_sizes(ws)[0]) <= 22
