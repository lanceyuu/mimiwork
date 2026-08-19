"""Every knowledge-work tool must register cleanly and expose a schema a provider accepts.

A tool that builds fine but produces a malformed schema fails at the first model call, in a
live session, with a provider-side error — so the contract is checked here instead.
"""

from __future__ import annotations

import json

import pytest

from coworker.agents.base import AgentContext
from coworker.catalog import expand
from coworker.risk import RiskClass, classify
from coworker.roots import RootDir
from coworker.tools import ToolRegistry
from coworker.tools.todo import TodoList

KNOWLEDGE_CAPABILITIES = [
    "documents",
    "spreadsheets",
    "slides",
    "pdf",
    "images",
    "data_inspect",
    "python_analysis",
    "r_analysis",
]

EXPECTED_TOOLS = {
    "read_document",
    "write_document",
    "edit_document",
    "read_workbook",
    "write_workbook",
    "edit_workbook",
    "read_presentation",
    "write_presentation",
    "inspect_data",
    "run_python",
    "reset_python",
    "run_r",
    "read_pdf",
    "read_image_info",
    "edit_image",
    "annotate_image",
    "combine_images",
}


@pytest.fixture
def registry(tmp_path):
    context = AgentContext(
        workspace=tmp_path,
        executor=object(),
        todo=TodoList(),
        roots=[RootDir(path=tmp_path, writable=True)],
    )
    reg = ToolRegistry()
    reg.register_all(expand(KNOWLEDGE_CAPABILITIES, context))
    return reg


def test_every_knowledge_tool_registers(registry):
    assert EXPECTED_TOOLS <= set(registry.names())


def test_schemas_are_well_formed_openai_function_schemas(registry):
    for schema in registry.schemas():
        assert schema["type"] == "function"
        function = schema["function"]
        assert function["name"] and isinstance(function["name"], str)
        assert function["description"] and isinstance(function["description"], str)
        parameters = function["parameters"]
        assert parameters["type"] == "object"
        assert isinstance(parameters["properties"], dict)
        for name, prop in parameters["properties"].items():
            assert isinstance(prop, dict), f"{function['name']}.{name}"


def test_schema_names_match_their_registry_keys(registry):
    for name in EXPECTED_TOOLS:
        assert registry.get(name).schema["function"]["name"] == name


def test_required_parameters_are_declared_properties(registry):
    """A required field the schema never defines makes the provider reject the whole request."""
    for schema in registry.schemas():
        function = schema["function"]
        properties = set(function["parameters"].get("properties", {}))
        for required in function["parameters"].get("required", []):
            assert required in properties, f"{function['name']}: {required}"


def test_schemas_are_json_serialisable(registry):
    """They cross the wire as JSON; a stray Python object here fails at request time."""
    json.dumps(registry.schemas())


def test_code_execution_tools_are_classified_as_consequential(registry):
    """run_python must be gated like run_shell — it is the same authority."""
    for name in ("run_python", "run_r"):
        spec = registry.get(name)
        assert classify(name, spec.metadata) is RiskClass.EXTERNAL or spec.metadata.requires_approval


def test_read_only_tools_do_not_demand_approval(registry):
    for name in (
        "read_document",
        "read_workbook",
        "read_presentation",
        "inspect_data",
        "read_pdf",
        "read_image_info",
    ):
        assert registry.get(name).metadata.requires_approval is False


def test_tools_execute_through_the_registry(registry, tmp_path):
    """The registry calls tools by keyword arguments; a mismatched signature dies here."""
    result = registry.execute(
        "write_document",
        {"path": "e2e.docx", "blocks": [{"type": "heading", "text": "Hello", "level": 1}]},
    )
    assert "error" not in result, result
    assert (tmp_path / "e2e.docx").is_file()

    read_back = registry.execute("read_document", {"path": "e2e.docx"})
    assert read_back["blocks"][0]["text"] == "Hello"


def test_a_full_office_deliverable_round_trips_through_the_registry(registry, tmp_path):
    """The workflow the repositioning is actually about: data in, deliverables out."""
    pd = pytest.importorskip("pandas")
    pd.DataFrame({"region": ["EMEA", "APAC"], "revenue": [1200, 800]}).to_csv(
        tmp_path / "sales.csv", index=False
    )

    profile = registry.execute("inspect_data", {"path": "sales.csv"})
    assert profile["rows"] == 2

    workbook = registry.execute(
        "write_workbook",
        {"path": "summary.xlsx", "rows": [["Region", "Revenue"], ["EMEA", 1200], ["APAC", 800]]},
    )
    assert "error" not in workbook, workbook

    deck = registry.execute(
        "write_presentation",
        {
            "path": "review.pptx",
            "slides": [
                {
                    "layout": "bullets",
                    "title": "EMEA leads revenue",
                    "bullets": ["EMEA 1.2M", "APAC 0.8M"],
                    "notes": "EMEA is 60% of the total.",
                }
            ],
        },
    )
    assert "error" not in deck, deck

    for name in ("summary.xlsx", "review.pptx"):
        assert (tmp_path / name).is_file()


def test_python_kernel_runs_through_the_registry(registry):
    result = registry.execute("run_python", {"code": "sum([1, 2, 3])"})
    assert result["ok"], result
    assert "6" in result["value"]


def test_python_kernel_state_persists_across_registry_calls(registry):
    registry.execute("run_python", {"code": "dataset = [1, 2, 3, 4]"})
    result = registry.execute("run_python", {"code": "len(dataset)"})
    assert result["ok"], result
    assert "4" in result["value"]


def test_python_failure_is_returned_as_data_not_raised(registry):
    result = registry.execute("run_python", {"code": "1/0"})
    assert not result["ok"]
    assert "ZeroDivisionError" in result["error"]


def test_reset_clears_kernel_state_through_the_registry(registry):
    registry.execute("run_python", {"code": "temp = 99"})
    registry.execute("reset_python", {})
    assert not registry.execute("run_python", {"code": "temp"})["ok"]


def test_missing_workspace_yields_no_analysis_tools():
    reg = ToolRegistry()
    reg.register_all(expand(KNOWLEDGE_CAPABILITIES, AgentContext()))
    assert reg.names() == []
