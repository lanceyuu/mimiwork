"""A tool whose optional library is absent must still register, and say what to install.

Hiding the tool would be worse: the model cannot tell the difference between "this product
can't make Word documents" and "one pip install is missing", so it invents a shell workaround
and the user never learns what was actually wrong.
"""

from __future__ import annotations

import builtins

import pytest

from coworker.agents.base import AgentContext
from coworker.roots import RootDir
from coworker.tools.office._common import MissingDependency, guard, require
from coworker.tools.office.docx_tools import docx_tools
from coworker.tools.office.pptx_tools import pptx_tools
from coworker.tools.office.xlsx_tools import xlsx_tools


@pytest.fixture
def context(tmp_path):
    return AgentContext(workspace=tmp_path, roots=[RootDir(path=tmp_path, writable=True)])


@pytest.fixture
def no_office_libs(monkeypatch):
    """Make the Office libraries unimportable, as on an install without the [office] extra."""
    blocked = {"docx", "openpyxl", "pptx"}
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.split(".")[0] in blocked:
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # importlib.import_module consults sys.modules first, so evict any cached copies.
    import sys

    for name in list(sys.modules):
        if name.split(".")[0] in blocked:
            monkeypatch.delitem(sys.modules, name, raising=False)


def test_require_names_the_install_command():
    with pytest.raises(MissingDependency) as exc:
        require("definitely_not_a_real_module", "some-package", extra="office")
    assert "pip install 'coworker[office]'" in str(exc.value)


def test_guard_turns_a_missing_dependency_into_an_error_result():
    @guard
    def tool():
        raise MissingDependency("python-docx is not installed. Install it with: pip install x")

    result = tool()
    assert "error" in result
    assert "python-docx" in result["error"]


def test_tools_still_register_without_their_libraries(context, no_office_libs):
    """The factories must not import their library at build time."""
    names = {t.__name__ for t in docx_tools(context)}
    names |= {t.__name__ for t in xlsx_tools(context)}
    names |= {t.__name__ for t in pptx_tools(context)}

    assert {"write_document", "read_workbook", "write_presentation"} <= names


@pytest.mark.parametrize(
    "factory,tool_name,kwargs,package",
    [
        (docx_tools, "write_document", {"path": "a.docx", "blocks": []}, "python-docx"),
        (docx_tools, "read_document", {"path": "a.docx"}, "python-docx"),
        (xlsx_tools, "write_workbook", {"path": "a.xlsx", "rows": [["a"]]}, "openpyxl"),
        (pptx_tools, "write_presentation", {"path": "a.pptx", "slides": []}, "python-pptx"),
    ],
)
def test_calling_without_the_library_returns_an_actionable_error(
    context, no_office_libs, factory, tool_name, kwargs, package
):
    tool = {t.__name__: t for t in factory(context)}[tool_name]
    result = tool(**kwargs)

    assert "error" in result, result
    assert package in result["error"]
    assert "pip install" in result["error"]


def test_the_catalog_still_builds_without_office_libraries(context, no_office_libs):
    """A missing extra must not break session construction for everyone else."""
    from coworker.catalog import expand

    tools = expand(["documents", "spreadsheets", "slides"], context)
    assert len(tools) == 9  # docx ×4 (write/read/edit/revise), xlsx ×3, pptx ×2
