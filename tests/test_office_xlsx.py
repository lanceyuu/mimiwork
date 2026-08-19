"""Excel: row windowing (context safety) and formula preservation (data safety)."""

import pytest

from coworker.agents.base import AgentContext
from coworker.roots import RootDir
from coworker.tools.office.xlsx_tools import xlsx_tools

pytest.importorskip("openpyxl", reason="openpyxl is an optional [office] extra")


@pytest.fixture
def tools(tmp_path):
    ws = tmp_path / "scratch"
    ws.mkdir()
    context = AgentContext(workspace=ws, roots=[RootDir(path=ws, writable=True)])
    return {t.__name__: t for t in xlsx_tools(context)}, ws


def test_write_then_read_round_trips(tools):
    write, read = tools[0]["write_workbook"], tools[0]["read_workbook"]
    out = write("data.xlsx", rows=[["Region", "Revenue"], ["EMEA", 1200], ["APAC", 800]])
    assert "error" not in out
    assert out["rows_written"] == 3

    book = read("data.xlsx")
    assert book["header"] == ["Region", "Revenue"]
    assert book["rows"] == [["EMEA", 1200], ["APAC", 800]]
    assert book["total_rows"] == 2


def test_multiple_sheets(tools):
    write, read = tools[0]["write_workbook"], tools[0]["read_workbook"]
    write(
        "multi.xlsx",
        sheets=[
            {"name": "Summary", "rows": [["Metric", "Value"], ["NPS", 42]]},
            {"name": "Raw", "rows": [["id", "score"], [1, 9]]},
        ],
    )
    book = read("multi.xlsx", sheet="Raw")
    assert book["sheet"] == "Raw"
    assert book["sheets"] == ["Summary", "Raw"]
    assert book["rows"] == [[1, 9]]


def test_unknown_sheet_name_lists_the_available_ones(tools):
    tools[0]["write_workbook"]("d.xlsx", rows=[["a"], [1]])
    result = tools[0]["read_workbook"]("d.xlsx", sheet="Nope")
    assert "error" in result
    assert "Sheet1" in result["error"]


def test_large_sheet_is_windowed_with_a_continue_hint(tools):
    write, read = tools[0]["write_workbook"], tools[0]["read_workbook"]
    rows = [["n"]] + [[i] for i in range(500)]
    write("big.xlsx", rows=rows)

    book = read("big.xlsx", max_rows=10)
    assert len(book["rows"]) == 10
    assert book["total_rows"] == 500
    assert "note" in book and "start_row=11" in book["note"]


def test_windowing_continues_where_it_stopped(tools):
    write, read = tools[0]["write_workbook"], tools[0]["read_workbook"]
    write("big.xlsx", rows=[["n"]] + [[i] for i in range(100)])

    first = read("big.xlsx", max_rows=10)
    second = read("big.xlsx", start_row=11, max_rows=10)
    assert first["rows"][0] == [0]
    assert second["rows"][0] == [10]  # no gap, no overlap


def test_row_cap_is_enforced_even_if_the_model_asks_for_more(tools):
    write, read = tools[0]["write_workbook"], tools[0]["read_workbook"]
    write("big.xlsx", rows=[["n"]] + [[i] for i in range(5000)])
    book = read("big.xlsx", max_rows=99999)
    assert len(book["rows"]) == 1000


def test_edit_preserves_formulas_elsewhere_in_the_workbook(tools):
    """The classic destructive bug: load with cached values, save, and every formula is gone."""
    write, edit, read = (
        tools[0]["write_workbook"],
        tools[0]["edit_workbook"],
        tools[0]["read_workbook"],
    )
    write("f.xlsx", rows=[["a", "b"], [1, "=A2*2"]])

    edit("f.xlsx", cells=[{"cell": "A2", "value": 5}])

    formulas = read("f.xlsx", formulas=True)
    assert formulas["rows"][0][1] == "=A2*2"  # the untouched formula survived
    assert formulas["rows"][0][0] == 5


def test_edit_can_write_a_formula(tools):
    write, edit, read = (
        tools[0]["write_workbook"],
        tools[0]["edit_workbook"],
        tools[0]["read_workbook"],
    )
    write("f.xlsx", rows=[["a"], [1], [2]])
    edit("f.xlsx", cells=[{"cell": "A4", "value": "=SUM(A2:A3)"}])
    assert read("f.xlsx", formulas=True)["rows"][2][0] == "=SUM(A2:A3)"


def test_edit_requires_a_cell_reference(tools):
    tools[0]["write_workbook"]("f.xlsx", rows=[["a"], [1]])
    assert "error" in tools[0]["edit_workbook"]("f.xlsx", cells=[{"value": 1}])


def test_edit_on_a_missing_file_errors_cleanly(tools):
    result = tools[0]["edit_workbook"]("nope.xlsx", cells=[{"cell": "A1", "value": 1}])
    assert "error" in result


def test_write_without_rows_or_sheets_is_refused(tools):
    assert "error" in tools[0]["write_workbook"]("x.xlsx")


def test_write_outside_the_workspace_is_refused(tools):
    result = tools[0]["write_workbook"]("/tmp/escape.xlsx", rows=[["a"]])
    assert "error" in result and "escapes" in result["error"]


def test_long_sheet_name_is_truncated_to_excels_limit(tools):
    write, read = tools[0]["write_workbook"], tools[0]["read_workbook"]
    out = write("s.xlsx", rows=[["a"]], sheet="x" * 60)
    assert "error" not in out
    assert len(read("s.xlsx")["sheet"]) == 31
