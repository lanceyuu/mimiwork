"""PDF reading: page windowing, table extraction, and the scanned-document trap."""

import pytest

from coworker.agents.base import AgentContext
from coworker.roots import RootDir
from coworker.tools.office.pdf_tools import pdf_tools

pytest.importorskip("pypdf")
reportlab = pytest.importorskip(
    "reportlab", reason="reportlab builds the PDF fixtures"
)


@pytest.fixture
def tools(tmp_path):
    ws = tmp_path / "scratch"
    ws.mkdir()
    context = AgentContext(workspace=ws, roots=[RootDir(path=ws, writable=True)])
    return {t.__name__: t for t in pdf_tools(context)}["read_pdf"], ws


def _make_pdf(path, pages):
    """A text PDF with one line of known text per page."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    for text in pages:
        c.drawString(72, 720, text)
        c.showPage()
    c.save()


def _make_image_only_pdf(path, count=2):
    """A PDF with no text layer at all — what a scan looks like."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    for _ in range(count):
        c.rect(72, 600, 200, 100, fill=1)  # ink, but no text
        c.showPage()
    c.save()


def test_reads_page_text(tools):
    read, ws = tools
    _make_pdf(ws / "doc.pdf", ["Revenue grew twelve percent"])

    result = read("doc.pdf")
    assert "error" not in result, result
    assert result["total_pages"] == 1
    assert "Revenue grew twelve percent" in result["pages"][0]["text"]


def test_pages_are_numbered_from_one(tools):
    read, ws = tools
    _make_pdf(ws / "doc.pdf", ["First", "Second", "Third"])

    result = read("doc.pdf")
    assert [p["page"] for p in result["pages"]] == [1, 2, 3]


def test_long_documents_are_windowed_with_a_continue_hint(tools):
    read, ws = tools
    _make_pdf(ws / "doc.pdf", [f"Page {i}" for i in range(30)])

    result = read("doc.pdf", max_pages=5)
    assert len(result["pages"]) == 5
    assert result["total_pages"] == 30
    assert "start_page=6" in result["note"]


def test_windowing_continues_without_gaps(tools):
    read, ws = tools
    _make_pdf(ws / "doc.pdf", [f"Page {i}" for i in range(20)])

    second = read("doc.pdf", start_page=6, max_pages=5)
    assert [p["page"] for p in second["pages"]] == [6, 7, 8, 9, 10]


def test_page_cap_is_enforced(tools):
    read, ws = tools
    _make_pdf(ws / "doc.pdf", [f"P{i}" for i in range(80)])
    assert len(read("doc.pdf", max_pages=9999)["pages"]) == 50


def test_reading_past_the_end_is_not_an_error(tools):
    read, ws = tools
    _make_pdf(ws / "doc.pdf", ["Only page"])
    result = read("doc.pdf", start_page=99)
    assert "error" not in result
    assert result["pages"] == []


def test_a_scanned_pdf_is_flagged_loudly(tools):
    """A silent empty page is how a model ends up summarising a document it never read."""
    read, ws = tools
    _make_image_only_pdf(ws / "scan.pdf")

    result = read("scan.pdf")
    assert result["scanned"] is True
    assert "scanned" in result["warning"]
    assert "ocr" in result["warning"].lower()
    assert "Do NOT summarise" in result["warning"]


def test_a_text_pdf_is_not_flagged_as_scanned(tools):
    read, ws = tools
    _make_pdf(ws / "doc.pdf", ["Real text here"])
    assert "scanned" not in read("doc.pdf")


def test_missing_file_errors_cleanly(tools):
    assert "error" in tools[0]("nope.pdf")


def test_reading_outside_the_workspace_is_refused(tools):
    result = tools[0]("/etc/hosts")
    assert "error" in result and "escapes" in result["error"]


def test_a_corrupt_pdf_reports_an_error_rather_than_crashing(tools):
    read, ws = tools
    (ws / "bad.pdf").write_text("this is not a PDF at all")
    assert "error" in read("bad.pdf")


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("pdfplumber") is None,
    reason="pdfplumber is an optional extra",
)
def test_tables_are_extracted_as_rows(tools):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    read, ws = tools
    # A ruled grid is what table detection keys off.
    c = canvas.Canvas(str(ws / "t.pdf"), pagesize=letter)
    rows = [["Region", "Revenue"], ["EMEA", "1200"], ["APAC", "800"]]
    top, left, height, width = 700, 72, 24, 120
    for r, row in enumerate(rows):
        for col, value in enumerate(row):
            x, y = left + col * width, top - r * height
            c.rect(x, y, width, height)
            c.drawString(x + 4, y + 8, value)
    c.showPage()
    c.save()

    result = read("t.pdf", tables=True)
    assert "error" not in result, result
    assert result["tables"], result
    flat = [cell for table in result["tables"] for row in table["rows"] for cell in row]
    assert "EMEA" in flat


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("pdfplumber") is None,
    reason="pdfplumber is an optional extra",
)
def test_no_tables_says_so_rather_than_returning_silence(tools):
    read, ws = tools
    _make_pdf(ws / "prose.pdf", ["Just a sentence of prose."])
    result = read("prose.pdf", tables=True)
    assert result["tables"] == []
    assert "tables_note" in result
