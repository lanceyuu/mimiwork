"""Kernel lifecycle: no orphaned interpreters left behind.

The kernel is a long-lived subprocess like the shell executor, and nothing in the server
explicitly closes either one. What stops a leak is the child's own read loop: when the parent
goes away its stdin reaches EOF and the child exits. That is load-bearing, so it is tested.
"""

from __future__ import annotations

import subprocess
import sys
import time

from coworker.tools.analysis.kernel import PythonKernel


def _wait_for_exit(process: subprocess.Popen, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return True
        time.sleep(0.1)
    return False


def test_closing_the_kernel_terminates_its_process(tmp_path):
    kernel = PythonKernel(tmp_path, python=sys.executable)
    kernel.start()
    process = kernel._process
    assert process.poll() is None

    kernel.close()
    assert _wait_for_exit(process), "the kernel process outlived close()"
    assert not kernel.alive


def test_close_is_idempotent(tmp_path):
    kernel = PythonKernel(tmp_path, python=sys.executable)
    kernel.start()
    kernel.close()
    kernel.close()  # must not raise


def test_close_without_start_is_a_no_op(tmp_path):
    PythonKernel(tmp_path, python=sys.executable).close()


def test_the_child_exits_when_its_stdin_closes(tmp_path):
    """The actual leak guard: an abandoned child must not linger forever."""
    kernel = PythonKernel(tmp_path, python=sys.executable)
    kernel.start()
    process = kernel._process

    # Simulate the parent disappearing without a clean shutdown.
    process.stdin.close()

    assert _wait_for_exit(process), "the kernel child ignored stdin EOF and would leak"


def test_a_dead_child_is_reported_rather_than_hanging(tmp_path):
    kernel = PythonKernel(tmp_path, python=sys.executable)
    kernel.start()
    kernel._kill(kernel._process)

    result = kernel.run("1 + 1")
    # Either it restarted cleanly, or it reported the death — never a silent hang.
    assert result["ok"] or result["error"]["kind"] in {"kernel-died", "timeout"}
    kernel.close()


def test_figures_directory_is_created_under_the_workspace(tmp_path):
    kernel = PythonKernel(tmp_path, python=sys.executable)
    kernel.start()
    try:
        assert (tmp_path / "figures").is_dir()
    finally:
        kernel.close()
