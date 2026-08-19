"""PythonKernel — the parent side of the persistent analysis runtime.

deepseek-harness models its code-runtime as strictly per-call ("no cross-run state"). For an
analysis session that is the wrong trade: reloading a large SPSS or Excel file on every call is
the difference between a usable analyst and an unusable one. So this kernel is **persistent**,
with two honesty requirements that follow from that choice:

* ``reset()`` exists, because persistent state eventually needs clearing.
* When the kernel dies or has to be killed, the result says so explicitly — silently restarting
  and letting the model believe its dataframes still exist produces confidently wrong analysis.

Lifetime and interruption follow ``tools/shell.py``: one long-lived child, SIGINT to interrupt a
runaway call, kill-and-restart only if it will not come back.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Optional

DEFAULT_TIMEOUT = 120.0
MAX_TIMEOUT = 600.0
_STARTUP_TIMEOUT = 60.0
# Grace period for the child to unwind after SIGINT before we give up and kill it.
_INTERRUPT_GRACE = 5.0
_IS_WINDOWS = sys.platform == "win32"


class PythonKernel:
    """One persistent Python process. Not thread-safe by design: the engine serialises
    ``run_python`` (it is EXEC-risk, so it never runs in the parallel-safe read pool)."""

    def __init__(
        self,
        workdir: str | Path,
        *,
        figures_dir: Optional[str | Path] = None,
        python: Optional[str] = None,
    ) -> None:
        self.workdir = Path(workdir)
        self.figures_dir = Path(figures_dir) if figures_dir else self.workdir / "figures"
        self.python = python or sys.executable
        self._process: Optional[subprocess.Popen] = None
        self._replies: "queue.Queue[Optional[str]]" = queue.Queue()
        self._reader: Optional[threading.Thread] = None
        self.restarts = 0

    # -- lifecycle ---------------------------------------------------------------
    @property
    def alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        if self.alive:
            return
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.figures_dir.mkdir(parents=True, exist_ok=True)

        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        # Headless: without this, a plot call on macOS tries to open a GUI window and hangs.
        env["MPLBACKEND"] = "Agg"
        # The child imports `coworker.tools.analysis._kernel_child`, so the repo root must be
        # importable even when the kernel runs from a workspace elsewhere on disk.
        repo_root = str(Path(__file__).resolve().parents[3])
        env["PYTHONPATH"] = os.pathsep.join(
            [p for p in (repo_root, env.get("PYTHONPATH", "")) if p]
        )

        creationflags = 0
        preexec = None
        if _IS_WINDOWS:
            # Own process group, so a Ctrl-Break reaches the child without hitting our own shell.
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            preexec = os.setsid

        self._process = subprocess.Popen(
            [
                self.python,
                "-u",
                "-m",
                "coworker.tools.analysis._kernel_child",
                str(self.workdir),
                str(self.figures_dir),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=str(self.workdir),
            env=env,
            creationflags=creationflags,
            preexec_fn=preexec,
        )
        self._replies = queue.Queue()
        self._reader = threading.Thread(target=self._pump, args=(self._process,), daemon=True)
        self._reader.start()

        ready = self._await_reply(_STARTUP_TIMEOUT)
        if ready is None or not ready.get("ready"):
            self.close()
            raise RuntimeError("the Python analysis kernel did not start")

    def _pump(self, process: subprocess.Popen) -> None:
        """Drain the child's stdout on a thread so a slow reader can never deadlock the pipe."""
        try:
            for line in process.stdout:  # type: ignore[union-attr]
                self._replies.put(line)
        except (ValueError, OSError):
            pass
        finally:
            self._replies.put(None)  # EOF sentinel: the child is gone

    def _await_reply(self, timeout: float) -> Optional[dict[str, Any]]:
        try:
            line = self._replies.get(timeout=timeout)
        except queue.Empty:
            return None
        if line is None:
            return None
        try:
            return json.loads(line)
        except ValueError:
            return None

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.poll() is None and process.stdin:
                process.stdin.write(json.dumps({"shutdown": True}) + "\n")
                process.stdin.flush()
        except (OSError, ValueError):
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self._kill(process)

    def _kill(self, process: subprocess.Popen) -> None:
        try:
            if _IS_WINDOWS:
                process.kill()
            else:
                os.killpg(os.getpgid(process.pid), 9)
        except (OSError, ProcessLookupError):
            try:
                process.kill()
            except OSError:
                pass

    def _interrupt(self, process: subprocess.Popen) -> None:
        """SIGINT, which surfaces inside the child's ``exec`` as KeyboardInterrupt."""
        try:
            if _IS_WINDOWS:
                process.send_signal(subprocess.signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                os.killpg(os.getpgid(process.pid), 2)
        except (OSError, ProcessLookupError, AttributeError):
            pass

    # -- execution ---------------------------------------------------------------
    def reset(self) -> dict[str, Any]:
        """Clear the namespace. Restarts the process if it is not running."""
        if not self.alive:
            self.start()
            return {"ok": True, "reset": True, "restarted": True}
        result = self._request({"reset": True}, timeout=30.0)
        result["reset"] = True
        return result

    def run(self, code: str, timeout: float = DEFAULT_TIMEOUT) -> dict[str, Any]:
        if not self.alive:
            self.start()
        limit = timeout if isinstance(timeout, (int, float)) and timeout > 0 else DEFAULT_TIMEOUT
        return self._request({"code": code}, timeout=min(float(limit), MAX_TIMEOUT))

    def _request(self, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        process = self._process
        if process is None or process.poll() is not None:
            return self._died("the analysis kernel is not running")

        try:
            process.stdin.write(json.dumps(payload) + "\n")  # type: ignore[union-attr]
            process.stdin.flush()  # type: ignore[union-attr]
        except (OSError, ValueError):
            return self._died("the analysis kernel stopped accepting work")

        reply = self._await_reply(timeout)
        if reply is not None:
            return reply

        # No answer in time: interrupt, and give the child a moment to report the timeout
        # itself (which keeps the namespace, and the user's loaded data, alive).
        if process.poll() is None:
            self._interrupt(process)
            recovered = self._await_reply(_INTERRUPT_GRACE)
            if recovered is not None:
                recovered.setdefault("error", None)
                if recovered.get("error") is None:
                    recovered["error"] = {
                        "kind": "timeout",
                        "message": f"execution exceeded {timeout:.0f}s and was interrupted",
                    }
                    recovered["ok"] = False
                return recovered
            self._kill(process)

        return self._died(
            f"execution exceeded {timeout:.0f}s and the kernel had to be restarted",
            kind="timeout",
        )

    def _died(self, message: str, kind: str = "kernel-died") -> dict[str, Any]:
        """Report a dead kernel honestly: the caller must know its variables are gone."""
        self._process = None
        self.restarts += 1
        return {
            "ok": False,
            "stdout": "",
            "stderr": "",
            "value": None,
            "figures": [],
            "truncated": False,
            "error": {
                "kind": kind,
                "message": message,
                "state_lost": True,
            },
        }
