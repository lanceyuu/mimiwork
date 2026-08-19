"""``run_r`` — hand statistics to R when R is the right tool.

Script-file only, never ``Rscript -e "<inline code>"``. That matches the instruction the
knowledge-work prompts already carry ("NEVER inline a multi-line script in a shell command"),
and it has two concrete payoffs: the approval prompt the user sees stays a short filename
instead of a wall of code, and the script survives on disk as part of the deliverable — a
reviewer can re-run the analysis, which is the whole point of using R for it.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import aisuite as ai

from ..office._common import MAX_TEXT_CHARS, clip
from ..office.paths import PathError, context_roots, display_path, resolve_write

DEFAULT_TIMEOUT = 300
MAX_TIMEOUT = 900

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_r",
        "description": (
            "Run an R script with Rscript. Write the script to a file first (with "
            "write_file), then run it by path — the script stays reviewable and re-runnable "
            "as part of the deliverable. Use R for the models and tests it does best (lme4, "
            "lavaan, survey, ggplot2); use run_python for general data wrangling. Requires "
            "approval, like any code execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "Path to the .R script to run, relative to the workspace.",
                },
                "args": {
                    "type": "array",
                    "description": "Arguments passed to the script (read via commandArgs()).",
                    "items": {"type": "string"},
                },
                "timeout": {
                    "type": "integer",
                    "description": f"Seconds before the run is killed (default {DEFAULT_TIMEOUT}).",
                },
            },
            "required": ["script"],
        },
    },
}


def rscript_path() -> str:
    """The Rscript executable, or "" when R is not installed."""
    return shutil.which("Rscript") or ""


def r_tools(context: Any) -> list:
    roots = context_roots(context)
    workspace = getattr(context, "workspace", None)

    def run_r(script: str, args: Any = None, timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
        executable = rscript_path()
        if not executable:
            return {
                "error": (
                    "Rscript is not installed or not on PATH. Install R from "
                    "https://cran.r-project.org (or `brew install r`), then retry. Use "
                    "run_python if the analysis does not specifically need R."
                )
            }
        try:
            # resolve_write, not resolve_read: a script runs with the session's authority, so
            # it must live somewhere the session actually owns, not in a read-only folder.
            target = resolve_write(script, roots)
        except PathError as exc:
            return {"error": str(exc)}
        if not target.is_file():
            return {"error": f"no such script: {script} (write it with write_file first)"}
        if target.suffix.lower() not in {".r", ".rscript"}:
            return {"error": f"expected an .R script, got {target.suffix or 'no extension'}"}

        limit = timeout if isinstance(timeout, int) and timeout > 0 else DEFAULT_TIMEOUT
        limit = min(limit, MAX_TIMEOUT)
        argv = [executable, "--vanilla", str(target)]
        argv += [str(a) for a in (args or [])]

        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=limit,
                cwd=str(workspace) if workspace else str(target.parent),
            )
        except subprocess.TimeoutExpired:
            return {
                "error": f"the R script exceeded {limit}s and was stopped",
                "error_kind": "timeout",
            }
        except OSError as exc:
            return {"error": f"could not run Rscript: {exc}"}

        result: dict[str, Any] = {
            "script": display_path(target, roots),
            "exit_code": completed.returncode,
            "ok": completed.returncode == 0,
        }
        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        if stdout:
            result["stdout"] = clip(stdout, MAX_TEXT_CHARS)
        if stderr:
            # R writes messages, warnings, and progress to stderr even on success, so this is
            # not by itself a failure signal — exit_code is.
            result["stderr"] = clip(stderr, MAX_TEXT_CHARS)
        if completed.returncode != 0:
            result["error"] = f"the R script failed with exit code {completed.returncode}"
        return result

    run_r.__name__ = "run_r"
    run_r.__doc__ = _SCHEMA["function"]["description"]
    run_r.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="run_r",
        category="analysis",
        risk_level="high",
        capabilities=["execute"],
        requires_approval=True,
    )
    run_r.__coworker_schema__ = _SCHEMA
    return [run_r]
