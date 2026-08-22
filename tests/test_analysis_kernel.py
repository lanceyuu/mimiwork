"""The persistent Python kernel: state survives, failures don't kill it, timeouts recover."""

import sys

import pytest

from coworker.tools.analysis.kernel import PythonKernel


@pytest.fixture
def kernel(tmp_path):
    k = PythonKernel(tmp_path, python=sys.executable)
    k.start()
    yield k
    k.close()


def test_state_persists_between_calls(kernel):
    """The whole reason this kernel is persistent rather than per-call."""
    kernel.run("x = 41")
    result = kernel.run("print(x + 1)")
    assert result["ok"]
    assert result["stdout"].strip() == "42"


def test_trailing_expression_is_reported_like_a_notebook_cell(kernel):
    result = kernel.run("2 + 3")
    assert result["ok"]
    assert result["value"] == "5"


def test_statement_only_code_has_no_value(kernel):
    result = kernel.run("y = 7")
    assert result["ok"]
    assert result["value"] is None


def test_stdout_is_captured(kernel):
    assert kernel.run("print('hello')")["stdout"].strip() == "hello"


def test_exception_is_reported_and_the_kernel_survives(kernel):
    result = kernel.run("1 / 0")
    assert not result["ok"]
    assert result["error"]["kind"] == "exception"
    assert "ZeroDivisionError" in result["error"]["message"]
    assert "line" in result["error"]["traceback"]

    # The critical part: the session is still usable, with its variables intact.
    kernel.run("survivor = 'yes'")
    assert kernel.run("print(survivor)")["stdout"].strip() == "yes"


def test_syntax_error_is_reported_as_an_exception(kernel):
    result = kernel.run("def (:")
    assert not result["ok"]
    assert result["error"]["kind"] == "exception"
    assert "SyntaxError" in result["error"]["message"]


def test_sys_exit_does_not_take_the_kernel_down(kernel):
    result = kernel.run("import sys; sys.exit(3)")
    assert not result["ok"]
    assert kernel.alive
    assert kernel.run("print('still here')")["stdout"].strip() == "still here"


def test_timeout_is_reported_and_the_kernel_recovers(kernel):
    result = kernel.run("import time\nwhile True: time.sleep(0.05)", timeout=2)
    assert not result["ok"]
    assert result["error"]["kind"] == "timeout"

    # Either the child recovered (state kept) or it was restarted (state_lost flagged) —
    # both are acceptable, but silently pretending nothing happened is not.
    if result["error"].get("state_lost"):
        assert not kernel.alive or kernel.restarts >= 1
    else:
        assert kernel.run("print('recovered')")["stdout"].strip() == "recovered"


def test_kernel_restarts_after_being_killed_and_says_state_was_lost(kernel):
    kernel.run("precious = 1")
    kernel._kill(kernel._process)
    kernel._process = None

    result = kernel.run("print('fresh')")
    assert result["ok"]
    assert result["stdout"].strip() == "fresh"
    # The old variable is genuinely gone; the kernel must not pretend otherwise.
    assert not kernel.run("print(precious)")["ok"]


def test_reset_clears_the_namespace(kernel):
    kernel.run("keep = 1")
    assert kernel.reset()["ok"]
    assert not kernel.run("print(keep)")["ok"]


def test_reset_on_a_dead_kernel_restarts_it(kernel):
    kernel.close()
    result = kernel.reset()
    assert result["ok"]
    assert kernel.alive


def test_huge_output_is_truncated_rather_than_flooding_the_caller(kernel):
    result = kernel.run("print('x' * 500_000)")
    assert result["ok"]
    assert result["truncated"]
    assert len(result["stdout"]) < 250_000


def test_workdir_is_the_kernels_cwd(kernel, tmp_path):
    result = kernel.run("import os; print(os.getcwd())")
    assert str(tmp_path.resolve()) in result["stdout"]


def test_stderr_is_captured_separately(kernel):
    result = kernel.run("import sys; sys.stderr.write('warned')")
    assert result["ok"]
    assert "warned" in result["stderr"]


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("matplotlib") is None,
    reason="matplotlib is an optional [analysis] extra",
)
def test_charts_are_saved_without_the_model_calling_savefig(kernel, tmp_path):
    """A chart the model never wrote to disk is invisible to the user."""
    result = kernel.run(
        "import matplotlib\n"
        "matplotlib.use('Agg')\n"
        "import matplotlib.pyplot as plt\n"
        "plt.plot([1, 2, 3], [2, 4, 8])\n"
        "plt.title('growth')\n"
    )
    assert result["ok"], result
    assert result["figures"], "an open figure should have been captured"
    assert (tmp_path / "figures").exists()


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("pandas") is None,
    reason="pandas is an optional [analysis] extra",
)
def test_pandas_is_preloaded_as_pd(kernel):
    result = kernel.run("df = pd.DataFrame({'a': [1, 2, 3]})\ndf['a'].sum()")
    assert result["ok"], result
    # numpy 2 reprs scalars as `np.int64(6)`, numpy 1 as `6`; both are what a notebook shows.
    assert "6" in result["value"]


@pytest.mark.skipif(
    __import__("importlib.util", fromlist=["util"]).find_spec("pandas") is None,
    reason="pandas is an optional [analysis] extra",
)
def test_a_dataframe_repr_is_bounded_by_display_options(kernel):
    """A 10k-row frame must not arrive in the caller's context in full."""
    result = kernel.run("pd.DataFrame({'a': range(10_000)})")
    assert result["ok"], result
    assert len(result["value"]) < 5_000


@pytest.mark.skipif(sys.platform == "win32", reason="relies on POSIX process groups")
def test_stale_pump_sentinel_cannot_poison_a_restarted_kernel(tmp_path):
    """Regression: the killed child's reader thread used to drop its EOF sentinel into
    whichever queue ``self._replies`` pointed at — after a restart, the *new* child's —
    so the restarted kernel saw ``None`` and reported itself dead (flaky on slow CI)."""
    k = PythonKernel(tmp_path, python=sys.executable)
    k.start()
    # A detached grandchild inherits the stdout pipe and outlives the SIGKILL'd child, so the
    # old pump thread cannot reach EOF until well after the restart below — the CI ordering.
    assert k.run(
        "import subprocess, sys; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(3)'], "
        "start_new_session=True)"
    )["ok"]
    old_queue, old_reader = k._replies, k._reader
    k._kill(k._process)
    k._process = None

    k.start()
    try:
        old_reader.join(timeout=15)
        assert not old_reader.is_alive()
        # The dead child's sentinel went to its own queue; the live kernel's queue is untouched.
        assert k._replies is not old_queue
        assert old_queue.get_nowait() is None
        assert k._replies.empty()
        result = k.run("print('fresh')")
        assert result["ok"], result
        assert result["stdout"].strip() == "fresh"
    finally:
        k.close()
