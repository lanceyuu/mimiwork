"""run_r: script-file discipline, clean errors when R is absent, real execution when present."""

import pytest

from coworker.agents.base import AgentContext
from coworker.roots import RootDir
from coworker.tools.analysis.r_tools import r_tools, rscript_path

has_r = bool(rscript_path())


@pytest.fixture
def run(tmp_path):
    ws = tmp_path / "scratch"
    ws.mkdir()
    context = AgentContext(workspace=ws, roots=[RootDir(path=ws, writable=True)])
    return {t.__name__: t for t in r_tools(context)}["run_r"], ws


def test_missing_script_is_reported_with_the_remedy(run):
    tool, _ = run
    result = tool("analysis.R")
    assert "error" in result
    # Either R is absent (install hint) or the script is (write_file hint) — both actionable.
    assert "install" in result["error"].lower() or "write_file" in result["error"]


@pytest.mark.skipif(has_r, reason="R is installed, so the absent-R path can't be exercised")
def test_absent_r_explains_how_to_install_and_offers_the_alternative(run):
    tool, ws = run
    (ws / "a.R").write_text("cat('hi')")
    result = tool("a.R")
    assert "error" in result
    assert "cran.r-project.org" in result["error"]
    assert "run_python" in result["error"]


def test_a_non_r_file_is_refused(run):
    tool, ws = run
    (ws / "a.py").write_text("print('hi')")
    result = tool("a.py")
    assert "error" in result
    assert ".py" in result["error"] or "install" in result["error"].lower()


def test_script_outside_the_workspace_is_refused(run):
    tool, _ = run
    result = tool("/tmp/evil.R")
    assert "error" in result
    assert "escapes" in result["error"] or "install" in result["error"].lower()


@pytest.mark.skipif(not has_r, reason="Rscript is not installed")
def test_a_real_script_runs_and_returns_stdout(run):
    tool, ws = run
    (ws / "a.R").write_text("cat('mean:', mean(c(1,2,3)), '\\n')")
    result = tool("a.R")
    assert result["ok"], result
    assert "mean: 2" in result["stdout"]


@pytest.mark.skipif(not has_r, reason="Rscript is not installed")
def test_a_failing_script_reports_a_nonzero_exit_code(run):
    tool, ws = run
    (ws / "bad.R").write_text("stop('deliberate failure')")
    result = tool("bad.R")
    assert not result["ok"]
    assert result["exit_code"] != 0
    assert "deliberate failure" in result.get("stderr", "")


@pytest.mark.skipif(not has_r, reason="Rscript is not installed")
def test_arguments_reach_the_script(run):
    tool, ws = run
    (ws / "a.R").write_text("args <- commandArgs(trailingOnly=TRUE); cat(args[1])")
    assert "hello" in tool("a.R", args=["hello"])["stdout"]
