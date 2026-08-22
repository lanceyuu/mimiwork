"""``run_python`` / ``reset_python`` — the analyst's working surface.

One kernel per session, started lazily (someone who never analyses anything should never pay
for an interpreter). Charts land in ``figures/`` inside the workspace and come back as paths,
so the GUI's artifact panel picks them up like any other deliverable.

Risk is EXEC, identical to ``run_shell``: executing model-written Python is exactly the same
authority as executing a shell command, and classifying it any lower would be a way around the
shell's approval prompt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import aisuite as ai

from ..office._common import decorate
from ..office.paths import context_roots, display_path
from .kernel import DEFAULT_TIMEOUT, MAX_TIMEOUT, PythonKernel

_RUN_SCHEMA = {
    "type": "function",
    "function": {
        "name": "run_python",
        "description": (
            "Run Python in this session's persistent analysis kernel. Variables, imports, and "
            "loaded dataframes SURVIVE between calls, so load a dataset once and keep working "
            "on it — do not reload it every time. pandas is preloaded as `pd` and numpy as "
            "`np`. A trailing bare expression reports its value, like a notebook cell. Any "
            "matplotlib chart left open is saved to the workspace automatically and its path "
            "returned; you do not need to call savefig. Prefer this over run_shell for data "
            "work. Requires approval, like any code execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python source to execute."},
                "timeout": {
                    "type": "integer",
                    "description": (
                        f"Seconds before the call is interrupted (default {int(DEFAULT_TIMEOUT)}, "
                        f"max {int(MAX_TIMEOUT)})."
                    ),
                },
            },
            "required": ["code"],
        },
    },
}

_RESET_SCHEMA = {
    "type": "function",
    "function": {
        "name": "reset_python",
        "description": (
            "Clear the Python analysis kernel: every variable and loaded dataframe is "
            "discarded and a fresh namespace starts. Use when state has become confusing or "
            "memory needs releasing."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


class KernelHandle:
    """Lazily-started, per-session kernel owner. Holding the handle (not the kernel) lets the
    session close it on teardown without having started one."""

    def __init__(self, workdir: Path, figures_dir: Optional[Path] = None) -> None:
        self.workdir = workdir
        self.figures_dir = figures_dir or workdir / "figures"
        self._kernel: Optional[PythonKernel] = None

    def kernel(self) -> PythonKernel:
        if self._kernel is None:
            self._kernel = PythonKernel(self.workdir, figures_dir=self.figures_dir)
        if not self._kernel.alive:
            self._kernel.start()
        return self._kernel

    def close(self) -> None:
        if self._kernel is not None:
            self._kernel.close()
            self._kernel = None


def _shape_result(raw: dict[str, Any], roots: Any) -> dict[str, Any]:
    """Trim the kernel's reply to what the model benefits from seeing."""
    error = raw.get("error")
    result: dict[str, Any] = {"ok": bool(raw.get("ok"))}

    for key in ("stdout", "stderr"):
        value = (raw.get(key) or "").strip()
        if value:
            result[key] = value
    if raw.get("value") is not None:
        result["value"] = raw["value"]
    if raw.get("truncated"):
        result["note"] = (
            "output was truncated; aggregate or slice the data instead of printing it whole"
        )

    figures = raw.get("figures") or []
    if figures:
        result["figures"] = [display_path(Path(p), roots) for p in figures]

    if error:
        result["error"] = error.get("message") or "execution failed"
        result["error_kind"] = error.get("kind") or "exception"
        if error.get("traceback"):
            result["traceback"] = error["traceback"]
        if error.get("state_lost"):
            # Load-bearing: without this the model keeps referring to variables that no
            # longer exist and reports results it never computed.
            result["state_lost"] = True
            result["note"] = (
                "the kernel restarted — every variable and loaded dataset is gone; "
                "reload the data before continuing"
            )
    return result


def python_tools(context: Any) -> list:
    roots = context_roots(context)
    workspace = getattr(context, "workspace", None)
    if workspace is None:
        return []
    handle = KernelHandle(Path(workspace))
    # Expose the handle so the session can shut the kernel down on teardown (the manager's
    # interrupt hooks own this the same way they own the shell executor's kill).
    context.python_kernel = handle

    def run_python(code: str, timeout: int = int(DEFAULT_TIMEOUT)) -> dict[str, Any]:
        if not isinstance(code, str) or not code.strip():
            return {"error": "code is required"}
        try:
            raw = handle.kernel().run(code, timeout=float(timeout or DEFAULT_TIMEOUT))
        except (RuntimeError, OSError) as exc:
            return {"error": f"the analysis kernel could not start: {exc}"}
        return _shape_result(raw, roots)

    def reset_python() -> dict[str, Any]:
        try:
            handle.kernel().reset()
        except (RuntimeError, OSError) as exc:
            return {"error": f"the analysis kernel could not restart: {exc}"}
        return {"ok": True, "note": "the Python kernel is empty; reload any data you need"}

    run_python.__name__ = "run_python"
    run_python.__doc__ = _RUN_SCHEMA["function"]["description"]
    run_python.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="run_python",
        category="analysis",
        risk_level="high",
        capabilities=["execute"],
        requires_approval=True,
    )
    run_python.__coworker_schema__ = _RUN_SCHEMA

    return [
        run_python,
        decorate(
            reset_python,
            name="reset_python",
            schema=_RESET_SCHEMA,
            risk="low",
            capabilities=["execute"],
        ),
    ]
