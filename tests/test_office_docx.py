"""Word deliverables: write → read round-trip, structure preservation, in-place edits."""

import pytest

from coworker.agents.base import AgentContext
from coworker.roots import RootDir
from coworker.tools.office.docx_tools import docx_tools

pytest.importorskip("docx", reason="python-docx is an optional [office] extra")


@pytest.fixture
def tools(tmp_path):
    ws = tmp_path / "scratch"
    ws.mkdir()
    context = AgentContext(workspace=ws, roots=[RootDir(path=ws, writable=True)])
    return {t.__name__: t for t in docx_tools(context)}, ws


def test_write_then_read_round_trips_headings_and_paragraphs(tools):
    write, read = tools[0]["write_document"], tools[0]["read_document"]
    out = write(
        "report.docx",
        [
            {"type": "heading", "text": "Q3 Results", "level": 1},
            {"type": "paragraph", "text": "Revenue grew 12%."},
            {"type": "heading", "text": "Method", "level": 2},
            {"type": "paragraph", "text": "Two-sample t-test."},
        ],
    )
    assert "error" not in out
    assert out["path"] == "report.docx"

    doc = read("report.docx")
    assert "error" not in doc
    texts = [b["text"] for b in doc["blocks"]]
    assert texts == ["Q3 Results", "Revenue grew 12%.", "Method", "Two-sample t-test."]
    kinds = [b["type"] for b in doc["blocks"]]
    assert kinds == ["heading", "paragraph", "heading", "paragraph"]
    assert doc["blocks"][0]["level"] == 1
    assert doc["blocks"][2]["level"] == 2


def test_blocks_are_numbered_so_the_model_can_cite_and_edit(tools):
    write, read = tools[0]["write_document"], tools[0]["read_document"]
    write("d.docx", [{"type": "paragraph", "text": f"Line {i}"} for i in range(5)])
    doc = read("d.docx")
    assert [b["index"] for b in doc["blocks"]] == [0, 1, 2, 3, 4]


def test_bullets_survive_the_round_trip(tools):
    write, read = tools[0]["write_document"], tools[0]["read_document"]
    write(
        "b.docx",
        [
            {"type": "bullet", "text": "First"},
            {"type": "bullet", "text": "Second"},
        ],
    )
    doc = read("b.docx")
    assert [b["type"] for b in doc["blocks"]] == ["bullet", "bullet"]


def test_tables_read_back_as_structured_rows(tools):
    write, read = tools[0]["write_document"], tools[0]["read_document"]
    write(
        "t.docx",
        [
            {
                "type": "table",
                "rows": [["Region", "Revenue"], ["EMEA", "1.2M"], ["APAC", "0.8M"]],
                "header": True,
            }
        ],
    )
    doc = read("t.docx")
    tables = [b for b in doc["blocks"] if b["type"] == "table"]
    assert len(tables) == 1
    assert tables[0]["rows"][0] == ["Region", "Revenue"]
    assert tables[0]["rows"][2] == ["APAC", "0.8M"]


def test_edit_replaces_one_paragraph_and_leaves_the_rest_intact(tools):
    write, read, edit = (
        tools[0]["write_document"],
        tools[0]["read_document"],
        tools[0]["edit_document"],
    )
    write(
        "e.docx",
        [
            {"type": "heading", "text": "Title", "level": 1},
            {"type": "paragraph", "text": "Old text."},
            {"type": "paragraph", "text": "Keep me."},
        ],
    )
    result = edit("e.docx", [{"index": 1, "text": "New text."}])
    assert "error" not in result
    assert result["edited"] == 1

    doc = read("e.docx")
    texts = [b["text"] for b in doc["blocks"]]
    assert texts == ["Title", "New text.", "Keep me."]
    assert doc["blocks"][0]["type"] == "heading"  # style survived the edit


def test_edit_rejects_an_out_of_range_index(tools):
    write, edit = tools[0]["write_document"], tools[0]["edit_document"]
    write("e.docx", [{"type": "paragraph", "text": "Only one."}])
    result = edit("e.docx", [{"index": 99, "text": "nope"}])
    assert "error" in result


def test_append_adds_to_an_existing_document(tools):
    write, read = tools[0]["write_document"], tools[0]["read_document"]
    write("a.docx", [{"type": "paragraph", "text": "First."}])
    write("a.docx", [{"type": "paragraph", "text": "Second."}], append=True)
    doc = read("a.docx")
    assert [b["text"] for b in doc["blocks"]] == ["First.", "Second."]


def test_read_windows_a_long_document_and_says_how_to_continue(tools):
    write, read = tools[0]["write_document"], tools[0]["read_document"]
    write("long.docx", [{"type": "paragraph", "text": f"P{i}"} for i in range(50)])
    doc = read("long.docx", start=0, limit=10)
    assert len(doc["blocks"]) == 10
    assert doc["total_blocks"] == 50
    assert "note" in doc and "start=10" in doc["note"]


def test_write_outside_the_workspace_is_refused(tools):
    write = tools[0]["write_document"]
    result = write("/tmp/escape.docx", [{"type": "paragraph", "text": "x"}])
    assert "error" in result
    assert "escapes" in result["error"]


def test_reading_a_missing_file_returns_an_error_not_an_exception(tools):
    assert "error" in tools[0]["read_document"]("nope.docx")


def test_unknown_block_type_is_reported_clearly(tools):
    result = tools[0]["write_document"]("x.docx", [{"type": "sonnet", "text": "hi"}])
    assert "error" in result
    assert "sonnet" in result["error"]


def test_nested_directories_are_created_on_write(tools):
    write = tools[0]["write_document"]
    out = write("sub/dir/report.docx", [{"type": "paragraph", "text": "x"}])
    assert "error" not in out
    assert (tools[1] / "sub" / "dir" / "report.docx").is_file()


# -- revise_document: Word tracked changes -----------------------------------------------


def _xml(ws, name):
    import zipfile

    with zipfile.ZipFile(ws / name) as z:
        return z.read("word/document.xml").decode("utf-8")


def test_revise_document_writes_tracked_changes_and_a_plain_review(tools):
    toolbox, ws = tools
    write, revise, read = toolbox["write_document"], toolbox["revise_document"], toolbox["read_document"]
    write(
        "draft.docx",
        [
            {"type": "heading", "text": "Findings", "level": 1},
            {"type": "paragraph", "text": "Sales went up a lot."},
            {"type": "paragraph", "text": "Unchanged line."},
        ],
    )
    out = revise(
        "draft.docx",
        [
            {"index": 1, "text": "Sales rose 12% year on year.", "reason": "quantified the claim"},
            {"index": 2, "text": "Unchanged line."},  # identical → no revision
        ],
    )
    assert "error" not in out, out
    assert out["applied"] == 1
    (change,) = out["changes"]
    assert change == {
        "index": 1,
        "before": "Sales went up a lot.",
        "after": "Sales rose 12% year on year.",
        "reason": "quantified the claim",
    }
    assert "tracked" in out["note"]

    xml = _xml(ws, "draft.docx")
    assert '<w:del ' in xml and '<w:ins ' in xml
    assert 'w:author="Mimi"' in xml
    # Word by word, like a person's Track Changes: the words that stay are not touched
    # (a user reported every edit deleting the whole paragraph, 2026-09-16).
    assert '<w:t xml:space="preserve">Sales </w:t>' in xml
    assert "<w:delText" in xml and ">went up a lot<" in xml and "Sales went up a lot." not in xml
    assert ">rose 12% year on year<" in xml

    # The plain read shows the accepted view; revisions=True lists the pending change.
    doc = read("draft.docx", revisions=True)
    assert [b["text"] for b in doc["blocks"]][:2] == ["Findings", "Sales rose 12% year on year."]
    assert doc["revisions"] == [
        {
            "index": 1,
            "author": "Mimi",
            "deleted": "went up a lot",
            "inserted": "rose 12% year on year",
        }
    ]
    # Dropping a word in the middle: one deletion, nothing else touched.
    revise("draft.docx", [{"index": 1, "text": "Sales rose year on year."}])
    assert read("draft.docx", revisions=True)["revisions"] == [
        {
            "index": 1,
            "author": "Mimi",
            "deleted": "went up a lot12% ",
            "inserted": "rose year on year",
        }
    ]
    assert "revisions" not in read("draft.docx")


def test_revise_document_keeps_formatting_and_falls_back_for_a_rewrite(tools):
    toolbox, ws = tools
    revise, read = toolbox["revise_document"], toolbox["read_document"]
    import docx

    d = docx.Document()
    p = d.add_paragraph("The results were ")
    p.add_run("very").bold = True
    p.add_run(" promising overall.")
    d.add_paragraph("Old sentence here.")
    d.save(str(ws / "f.docx"))
    revise(
        "f.docx",
        [
            {"index": 0, "text": "The results were very encouraging overall."},
            {"index": 1, "text": "Completely different words."},
        ],
    )
    xml = _xml(ws, "f.docx")
    # The bold run survives untouched; only one word is swapped, in that run's formatting.
    assert "<w:b/>" in xml.split(">very<")[0].rsplit("<w:r>", 1)[1]
    assert ">promising <" in xml and ">encouraging <" in xml
    assert "<w:del " in xml.split("encouraging")[0]
    doc = read("f.docx", revisions=True)
    assert doc["revisions"][0] == {"index": 0, "author": "Mimi", "deleted": "promising ", "inserted": "encouraging "}
    # No word in common → one replacement, not a change per word.
    assert doc["revisions"][1] == {
        "index": 1, "author": "Mimi", "deleted": "Old sentence here.", "inserted": "Completely different words."
    }
    assert [b["text"] for b in doc["blocks"]] == [
        "The results were very encouraging overall.", "Completely different words."
    ]
    # A second pass over the same paragraph revises the revision, and the file still opens.
    revise("f.docx", [{"index": 0, "text": "The results were very encouraging."}])
    doc = read("f.docx", revisions=True)
    assert doc["blocks"][0]["text"] == "The results were very encouraging."
    assert "overall" in doc["revisions"][0]["deleted"]


def test_revise_document_ids_stay_unique_across_calls(tools):
    toolbox, ws = tools
    write, revise = toolbox["write_document"], toolbox["revise_document"]
    write("d.docx", [{"type": "paragraph", "text": "one"}, {"type": "paragraph", "text": "two"}])
    revise("d.docx", [{"index": 0, "text": "uno"}])
    revise("d.docx", [{"index": 1, "text": "dos"}])
    import re

    ids = re.findall(r'<w:(?:ins|del) [^>]*w:id="(\d+)"', _xml(ws, "d.docx"))
    assert len(ids) == 4 and len(set(ids)) == 4


def test_revise_document_rejects_tables_and_bad_indexes(tools):
    toolbox, _ = tools
    write, revise = toolbox["write_document"], toolbox["revise_document"]
    write(
        "t.docx",
        [{"type": "paragraph", "text": "intro"}, {"type": "table", "rows": [["a", "b"]]}],
    )
    assert "table" in revise("t.docx", [{"index": 1, "text": "x"}])["error"]
    assert "out of range" in revise("t.docx", [{"index": 9, "text": "x"}])["error"]


def _hyperlinked(paragraph, text):
    """A run inside w:hyperlink, the way Word stores a clickable DOI."""
    from docx.oxml import OxmlElement

    link = OxmlElement("w:hyperlink")
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


def test_a_plain_paragraph_takes_word_level_changes_and_a_linked_one_does_not(tmp_path):
    import docx

    from coworker.tools.office.docx_tools import word_level_ok

    document = docx.Document()
    plain = document.add_paragraph("Baumiester, R. (1998). The self. https://doi.org/10.1000/a")
    linked = document.add_paragraph("Baumeister, R. (1998). The self. ")
    _hyperlinked(linked, "https://doi.org/10.1000/a")
    assert word_level_ok(plain, "Baumeister, R. (1998). The self. https://doi.org/10.1000/a")
    assert not word_level_ok(linked, "Baumeister, R. (1998). The self. https://doi.org/10.1000/b")
    assert not word_level_ok(plain, "Completely different words")  # no shared word: whole paragraph


def test_tracked_revisions_can_be_written_without_the_tool(tmp_path):
    import docx

    from coworker.tools.office.docx_tools import (
        _indexed_blocks,
        _para_text,
        apply_tracked_revisions,
    )

    path = tmp_path / "refs.docx"
    document = docx.Document()
    document.add_paragraph("References")
    document.add_paragraph("Baumiester, R. (1998). The self. https://doi.org/10.1000/a")
    document.save(path)
    out = apply_tracked_revisions(
        path,
        [{"index": 1, "text": "Baumeister, R. (1998). The self. https://doi.org/10.1000/b", "reason": "Corrected."}],
    )
    assert out["applied"] == 1
    reopened = docx.Document(str(path))
    assert _para_text(_indexed_blocks(reopened)[1]) == "Baumeister, R. (1998). The self. https://doi.org/10.1000/b"
    assert "<w:delText" in _xml(tmp_path, "refs.docx")


def _run_with(paragraph, tag, **attrs):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    run = OxmlElement("w:r")
    el = OxmlElement(tag)
    for key, value in attrs.items():
        el.set(qn(key), value)
    run.append(el)
    paragraph._p.append(run)


def test_a_paragraph_holding_a_field_mark_or_a_comment_reference_is_replaced_whole():
    import docx

    from coworker.tools.office.docx_tools import word_level_ok

    document = docx.Document()
    field = document.add_paragraph("Baumiester, R. (1998). The self.")
    _run_with(field, "w:fldChar", **{"w:fldCharType": "begin"})
    commented = document.add_paragraph("Baumiester, R. (1998). The self.")
    _run_with(commented, "w:commentReference", **{"w:id": "0"})
    assert not word_level_ok(field, "Baumeister, R. (1998). The self.")
    assert not word_level_ok(commented, "Baumeister, R. (1998). The self.")


def test_a_later_edit_that_splits_an_earlier_insertion_keeps_every_revision_id_unique(tmp_path):
    import re

    import docx

    from coworker.tools.office.docx_tools import apply_tracked_revisions

    path = tmp_path / "split.docx"
    document = docx.Document()
    document.add_paragraph("start end")
    document.save(path)
    apply_tracked_revisions(path, [{"index": 0, "text": "start alpha beta gamma end"}])
    apply_tracked_revisions(path, [{"index": 0, "text": "start alpha BETA gamma end"}])
    ids = re.findall(r'<w:(?:ins|del) [^>]*w:id="(\d+)"', _xml(tmp_path, "split.docx"))
    assert len(ids) == len(set(ids))


def test_new_revision_ids_skip_those_on_formatting_changes():
    import docx
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    from coworker.tools.office.docx_tools import _next_revision_id

    document = docx.Document()
    run = document.add_paragraph().add_run("x")
    change = OxmlElement("w:rPrChange")
    change.set(qn("w:id"), "41")
    run._r.get_or_add_rPr().append(change)
    assert _next_revision_id(document) == 42
