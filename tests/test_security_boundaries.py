"""Regressions for artifact review findings: write approvals and search containment."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from coworker.permissions import Mode, PermissionEngine
from coworker.risk import RiskClass, classify
from coworker.roots import RootDir
from coworker.tools.office.docx_tools import docx_tools
from coworker.tools.office.image_tools import image_tools
from coworker.tools.office.pptx_tools import pptx_tools
from coworker.tools.office.xlsx_tools import xlsx_tools
from coworker.tools.search import search_tools


@pytest.mark.parametrize("factory", [docx_tools, xlsx_tools, pptx_tools, image_tools])
def test_every_office_writer_obeys_read_only_modes_and_asks_before_writing(tmp_path, factory):
    context = SimpleNamespace(workspace=tmp_path, roots=None)
    for tool in factory(context):
        metadata = tool.__aisuite_tool_metadata__
        if "write" not in metadata.capabilities:
            assert classify(tool.__name__, metadata) is RiskClass.READ
            continue
        assert classify(tool.__name__, metadata) is RiskClass.WRITE_LOCAL
        for mode in (Mode.PLAN, Mode.DISCUSS):
            decision = PermissionEngine(tmp_path, mode=mode).evaluate(tool.__name__, {}, metadata)
            assert not decision.allowed and not decision.needs_user
        decision = PermissionEngine(tmp_path).evaluate(tool.__name__, {}, metadata)
        assert not decision.allowed and decision.needs_user


@pytest.mark.parametrize("name", ["edit_image", "annotate_image", "combine_images"])
def test_image_permissions_scope_the_destination_instead_of_the_source(tmp_path, name):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    engine = PermissionEngine(
        workspace, mode=Mode.AUTO,
        roots=[RootDir(workspace, writable=True), RootDir(source, writable=False)],
    )
    assert engine.evaluate(name, {"path": str(source / "original.png"), "output": "new.png"}).allowed
    for destination in (source / "original.png", tmp_path / "private.png"):
        assert not engine.evaluate(name, {"path": "input.png", "output": str(destination)}).allowed


def test_python_search_never_returns_contents_of_links_outside_granted_folders(tmp_path, monkeypatch):
    monkeypatch.setattr("coworker.tools.search.shutil.which", lambda _: None)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "private.txt"
    secret.write_text("needle private")
    (workspace / "leak.txt").symlink_to(secret)
    (workspace / "safe.txt").write_text("needle public")
    result = search_tools(str(workspace))[0]("needle")
    assert result["engine"] == "python"
    assert [m["text"] for m in result["matches"]] == ["needle public"]


def test_python_search_allows_links_into_an_additional_granted_folder(tmp_path, monkeypatch):
    monkeypatch.setattr("coworker.tools.search.shutil.which", lambda _: None)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    granted = tmp_path / "granted"
    granted.mkdir()
    (granted / "data.txt").write_text("needle permitted")
    (workspace / "linked.txt").symlink_to(granted / "data.txt")
    roots = [RootDir(workspace, writable=True), RootDir(granted)]
    result = search_tools(str(workspace), roots=roots)[0]("needle", path=str(workspace))
    assert [m["text"] for m in result["matches"]] == ["needle permitted"]
    assert Path(result["matches"][0]["file"]).name == "linked.txt"
