"""The kernel child process — a persistent Python namespace driven over stdin/stdout.

Runs as ``python -m coworker.tools.analysis._kernel_child <workdir> <figdir>``. The protocol is
one JSON object per line in each direction, mirroring the marker discipline ``tools/shell.py``
uses for the persistent shell:

    in   {"code": "...", "echo": true}
    out  {"ok": bool, "stdout": str, "value": str|null, "error": {...}|null, "figures": [...]}

Design constraints:

* The namespace is module-level and **never** reset between requests — that is the whole point
  (a 300 MB dataframe must not be reloaded per call).
* An exception must never kill the loop. A dead kernel loses every variable the user's session
  built up, so the child catches everything and reports it as data.
* stdout/stderr are captured, not inherited: a stray ``print`` in analysis code would otherwise
  corrupt the JSON protocol on the pipe.
* Nothing here imports pandas or matplotlib at start-up. Importing matplotlib costs seconds and
  the kernel must feel instant for someone who only wanted arithmetic.
"""

from __future__ import annotations

import ast
import io
import json
import os
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout

# Bound what one call can push into the model's context. The parent re-checks, but capping at
# the source keeps a runaway loop from filling the pipe faster than the parent can drain it.
MAX_STREAM_CHARS = 200_000
MAX_VALUE_CHARS = 20_000


def _bootstrap(workdir: str) -> dict:
    """The persistent namespace. Display options are set so a dataframe repr stays readable
    rather than becoming a wall of columns the model has to parse."""
    namespace: dict = {
        "__name__": "__analysis__",
        "__builtins__": __builtins__,
    }
    preamble = (
        "import os, sys, json, math, statistics\n"
        "from pathlib import Path\n"
        "try:\n"
        "    import pandas as pd\n"
        "    pd.set_option('display.max_rows', 60)\n"
        "    pd.set_option('display.max_columns', 40)\n"
        "    pd.set_option('display.width', 200)\n"
        "    pd.set_option('display.max_colwidth', 80)\n"
        "except Exception:\n"
        "    pd = None\n"
        "try:\n"
        "    import numpy as np\n"
        "except Exception:\n"
        "    np = None\n"
    )
    try:
        exec(compile(preamble, "<bootstrap>", "exec"), namespace)
    except Exception:  # pragma: no cover - a broken preamble must not stop the kernel
        pass
    namespace["WORKDIR"] = workdir
    return namespace


def _capture_figures(namespace: dict, figdir: str) -> list:
    """Save any open matplotlib figures to PNG and close them.

    A chart the model 'made' but never wrote to disk is invisible to the user, and asking the
    model to remember to call savefig every time is a rule it will eventually forget. Only
    engages when matplotlib is already imported — probing for it would defeat the lazy import.
    """
    module = sys.modules.get("matplotlib.pyplot")
    if module is None:
        return []
    saved = []
    try:
        numbers = module.get_fignums()
    except Exception:  # pragma: no cover
        return []
    for number in numbers:
        try:
            figure = module.figure(number)
            if not figure.get_axes():  # an empty canvas isn't a chart
                module.close(figure)
                continue
            index = namespace.get("_figure_counter", 0) + 1
            namespace["_figure_counter"] = index
            path = os.path.join(figdir, f"figure-{index:02d}.png")
            figure.savefig(path, dpi=144, bbox_inches="tight")
            module.close(figure)
            saved.append(path)
        except Exception:  # pragma: no cover - one bad figure must not fail the call
            continue
    return saved


def _split_trailing_expression(code: str):
    """Return (body, trailing_expression_or_None).

    Mirrors a notebook cell: the value of a trailing bare expression is reported, so
    ``df.describe()`` shows its result without an explicit print. Syntax errors are left for the
    normal exec path to raise, so the model sees the real SyntaxError.
    """
    try:
        parsed = ast.parse(code)
    except SyntaxError:
        return code, None
    if not parsed.body or not isinstance(parsed.body[-1], ast.Expr):
        return code, None
    last = parsed.body[-1]
    body = ast.Module(body=parsed.body[:-1], type_ignores=parsed.type_ignores)
    return body, ast.Expression(body=last.value)


def _run(code: str, namespace: dict, figdir: str) -> dict:
    out, err = io.StringIO(), io.StringIO()
    value = None
    error = None

    try:
        body, tail = _split_trailing_expression(code)
        with redirect_stdout(out), redirect_stderr(err):
            if isinstance(body, str):
                exec(compile(body, "<analysis>", "exec"), namespace)
            else:
                exec(compile(body, "<analysis>", "exec"), namespace)
                if tail is not None:
                    result = eval(compile(tail, "<analysis>", "eval"), namespace)
                    if result is not None:
                        namespace["_"] = result
                        value = repr(result)
    except KeyboardInterrupt:
        error = {"kind": "timeout", "message": "execution was interrupted (timed out)"}
    except SystemExit as exc:
        # sys.exit() inside analysis code must not take the kernel with it.
        error = {"kind": "exception", "message": f"SystemExit: {exc.code}", "traceback": ""}
    except BaseException as exc:  # noqa: BLE001 - a live kernel is worth more than a clean raise
        error = {
            "kind": "exception",
            "message": f"{type(exc).__name__}: {exc}",
            "traceback": "".join(traceback.format_exc(limit=12)),
        }

    figures = _capture_figures(namespace, figdir)

    stdout = out.getvalue()
    stderr = err.getvalue()
    truncated = False
    if len(stdout) > MAX_STREAM_CHARS:
        stdout = stdout[:MAX_STREAM_CHARS] + "\n… (output truncated)"
        truncated = True
    if len(stderr) > MAX_STREAM_CHARS:
        stderr = stderr[:MAX_STREAM_CHARS] + "\n… (output truncated)"
        truncated = True
    if value is not None and len(value) > MAX_VALUE_CHARS:
        value = value[:MAX_VALUE_CHARS] + "… (truncated)"
        truncated = True

    return {
        "ok": error is None,
        "stdout": stdout,
        "stderr": stderr,
        "value": value,
        "error": error,
        "figures": figures,
        "truncated": truncated,
    }


def main() -> None:  # pragma: no cover - exercised through the parent in tests
    workdir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    figdir = sys.argv[2] if len(sys.argv) > 2 else workdir
    try:
        os.chdir(workdir)
    except OSError:
        pass
    os.makedirs(figdir, exist_ok=True)

    namespace = _bootstrap(workdir)
    # Hand the parent a ready signal so it never races the first request against interpreter
    # start-up (importing pandas in the preamble can take a second or more).
    sys.__stdout__.write(json.dumps({"ready": True}) + "\n")
    sys.__stdout__.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            continue
        if request.get("shutdown"):
            break
        if request.get("reset"):
            namespace = _bootstrap(workdir)
            response = {"ok": True, "stdout": "", "stderr": "", "value": None,
                        "error": None, "figures": [], "truncated": False}
        else:
            response = _run(str(request.get("code") or ""), namespace, figdir)
        try:
            sys.__stdout__.write(json.dumps(response, default=str) + "\n")
            sys.__stdout__.flush()
        except (BrokenPipeError, ValueError):  # parent went away
            break


if __name__ == "__main__":  # pragma: no cover
    main()
