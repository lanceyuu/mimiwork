"""The packaged app has no Python interpreter to hand ``-m``: the sidecar binary must become
the kernel itself. Every release from 0.1.7 to 0.6.24 shipped with run_python unable to start,
because only the source-tree launch was ever exercised."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from coworker.tools.analysis.kernel import PythonKernel

ENTRY = Path(__file__).resolve().parents[1] / "packaging" / "server_entry.py"


@pytest.fixture
def frozen_sidecar(tmp_path, monkeypatch):
    # Stands in for the PyInstaller binary: the same entry script behind the same argv, so the
    # launch contract is tested without freezing anything.
    shim = tmp_path / "openworker-server"
    shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{ENTRY}" "$@"\n')
    shim.chmod(0o755)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    return shim


@pytest.mark.skipif(sys.platform == "win32", reason="the stand-in binary is a shell script")
def test_the_packaged_sidecar_can_run_the_analysis_kernel(tmp_path, frozen_sidecar):
    kernel = PythonKernel(tmp_path / "work", python=str(frozen_sidecar))
    try:
        kernel.start()
        reply = kernel.run("21 * 2")
    finally:
        kernel.close()

    assert reply["ok"], reply
    assert reply["value"] == "42"
