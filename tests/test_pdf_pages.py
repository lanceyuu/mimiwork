"""Pages of a PDF as pictures: the only way a model learns how a document looks."""

import pytest

from coworker.agents.base import AgentContext
from coworker.roots import RootDir
from coworker.tools.office.pdf_tools import pdf_tools

pytest.importorskip("pypdfium2")


def _make_pdf(path, pages):
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=960, height=540)
    with path.open("wb") as out:
        writer.write(out)



@pytest.fixture
def save_pages(tmp_path):
    ws = tmp_path / "scratch"
    ws.mkdir()
    context = AgentContext(workspace=ws, roots=[RootDir(path=ws, writable=True)])
    return {t.__name__: t for t in pdf_tools(context)}["save_pdf_pages"], ws


def test_chosen_pages_are_saved_as_pictures_and_handed_over_to_be_looked_at(save_pages):
    from PIL import Image

    save, ws = save_pages
    _make_pdf(ws / "style.pdf", 3)
    out = save("style.pdf", [3, 1], "reference")
    assert out["files"] == ["reference/style-page-1.jpg", "reference/style-page-3.jpg"]
    assert out["_images"] == [str(ws / name) for name in out["files"]]
    with Image.open(ws / out["files"][0]) as picture:
        assert max(picture.size) == 1600


def test_a_page_that_is_not_in_the_document_or_a_fifth_page_is_refused(save_pages):
    save, ws = save_pages
    _make_pdf(ws / "style.pdf", 6)
    assert "between 1 and 6" in save("style.pdf", [7], "reference")["error"]
    assert "at most 4" in save("style.pdf", [1, 2, 3, 4, 5], "reference")["error"]
    assert not (ws / "reference").exists()


def test_pictures_already_saved_are_not_overwritten(save_pages):
    save, ws = save_pages
    _make_pdf(ws / "style.pdf", 1)
    save("style.pdf", [1], "reference")
    assert "already" in save("style.pdf", [1], "reference")["error"]


def test_pictures_cannot_be_saved_outside_the_granted_folders(save_pages, tmp_path):
    save, ws = save_pages
    _make_pdf(ws / "style.pdf", 1)
    assert "escapes" in save("style.pdf", [1], str(tmp_path / "elsewhere"))["error"]
    assert not (tmp_path / "elsewhere").exists()
