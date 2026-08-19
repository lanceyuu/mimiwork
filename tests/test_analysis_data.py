"""Dataset profiling: schema, missingness, coded-categorical detection, SPSS/Stata labels."""

import pytest

from coworker.agents.base import AgentContext
from coworker.roots import RootDir
from coworker.tools.analysis.data_tools import data_tools

pd = pytest.importorskip("pandas", reason="pandas is an optional [analysis] extra")


@pytest.fixture
def inspect(tmp_path):
    ws = tmp_path / "scratch"
    ws.mkdir()
    context = AgentContext(workspace=ws, roots=[RootDir(path=ws, writable=True)])
    tool = {t.__name__: t for t in data_tools(context)}["inspect_data"]
    return tool, ws


def test_csv_profile_reports_shape_and_columns(inspect):
    tool, ws = inspect
    pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]}).to_csv(ws / "d.csv", index=False)

    result = tool("d.csv")
    assert "error" not in result
    assert result["rows"] == 3
    assert result["columns"] == 2
    assert result["column_names"] == ["a", "b"]


def test_missing_values_are_counted_and_percentaged(inspect):
    tool, ws = inspect
    pd.DataFrame({"a": [1, None, None, 4]}).to_csv(ws / "d.csv", index=False)

    column = tool("d.csv")["profile"][0]
    assert column["missing"] == 2
    assert column["missing_pct"] == 50.0


def test_numeric_summary_statistics_are_present(inspect):
    tool, ws = inspect
    pd.DataFrame({"score": [10, 20, 30]}).to_csv(ws / "d.csv", index=False)

    column = tool("d.csv")["profile"][0]
    assert column["min"] == 10
    assert column["max"] == 30
    assert column["mean"] == 20.0


def test_a_low_cardinality_numeric_column_shows_its_levels(inspect):
    """A 1-5 Likert column must not look like a continuous variable to average blindly."""
    tool, ws = inspect
    pd.DataFrame({"likert": [1, 2, 2, 3, 5, 5, 5]}).to_csv(ws / "d.csv", index=False)

    column = tool("d.csv")["profile"][0]
    assert "levels" in column
    assert column["levels"]["5"] == 3


def test_text_column_reports_top_values(inspect):
    tool, ws = inspect
    pd.DataFrame({"region": ["EMEA", "EMEA", "APAC"]}).to_csv(ws / "d.csv", index=False)

    column = tool("d.csv")["profile"][0]
    assert column["top_values"]["EMEA"] == 2


def test_column_selection_narrows_the_profile(inspect):
    tool, ws = inspect
    pd.DataFrame({"a": [1], "b": [2], "c": [3]}).to_csv(ws / "d.csv", index=False)

    result = tool("d.csv", columns=["b"])
    assert [c["name"] for c in result["profile"]] == ["b"]


def test_unknown_column_lists_what_is_available(inspect):
    tool, ws = inspect
    pd.DataFrame({"a": [1]}).to_csv(ws / "d.csv", index=False)

    result = tool("d.csv", columns=["nope"])
    assert "error" in result and "a" in result["error"]


def test_excel_is_supported_and_lists_sheets(inspect):
    pytest.importorskip("openpyxl")
    tool, ws = inspect
    with pd.ExcelWriter(ws / "d.xlsx") as writer:
        pd.DataFrame({"a": [1, 2]}).to_excel(writer, sheet_name="First", index=False)
        pd.DataFrame({"b": [3]}).to_excel(writer, sheet_name="Second", index=False)

    result = tool("d.xlsx", sheet="Second")
    assert result["column_names"] == ["b"]
    assert result["sheets"] == ["First", "Second"]


def test_all_missing_column_is_flagged_rather_than_crashing(inspect):
    tool, ws = inspect
    pd.DataFrame({"empty": [None, None]}).to_csv(ws / "d.csv", index=False)
    assert tool("d.csv")["profile"][0]["all_missing"] is True


def test_unsupported_format_names_what_is_supported(inspect):
    tool, ws = inspect
    (ws / "d.docx").write_text("not data")
    result = tool("d.docx")
    assert "error" in result and ".sav" in result["error"]


def test_missing_file_errors_cleanly(inspect):
    assert "error" in inspect[0]("nope.csv")


def test_reading_outside_the_workspace_is_refused(inspect):
    result = inspect[0]("/etc/passwd")
    assert "error" in result and "escapes" in result["error"]


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("pyreadstat") is None,
    reason="pyreadstat is an optional [analysis] extra",
)
def test_spss_variable_and_value_labels_are_surfaced(inspect, tmp_path):
    """The reason this tool exists: `q1` alone is not interpretable, its labels are."""
    import pyreadstat

    tool, ws = inspect
    frame = pd.DataFrame({"q1": [1.0, 2.0, 5.0], "age": [31.0, 44.0, 29.0]})
    pyreadstat.write_sav(
        frame,
        str(ws / "survey.sav"),
        column_labels=["Satisfaction with onboarding", "Age in years"],
        variable_value_labels={
            "q1": {1: "Strongly disagree", 3: "Neutral", 5: "Strongly agree"}
        },
    )

    result = tool("survey.sav")
    assert "error" not in result, result
    assert result["variable_labels"]["q1"] == "Satisfaction with onboarding"
    assert result["value_labels"]["q1"][5] == "Strongly agree"
    assert "labels_note" in result


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("pyreadstat") is None,
    reason="pyreadstat is an optional [analysis] extra",
)
def test_stata_files_are_supported(inspect):
    import pyreadstat

    tool, ws = inspect
    pyreadstat.write_dta(pd.DataFrame({"x": [1.0, 2.0]}), str(ws / "d.dta"))
    result = tool("d.dta")
    assert "error" not in result, result
    assert result["rows"] == 2
