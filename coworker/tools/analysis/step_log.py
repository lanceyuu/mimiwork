"""Every ``run_python`` block, in order, in one file the researcher can read and re-run.

Code that ran only as tool-call arguments left no script behind, so nobody could check
what was done to the data before putting the result in a paper (spec 2026-11-06).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Optional

MARKER = "# MimiWork analysis log: every Python step Mimi ran in this conversation, in order."
_HEADER = re.compile(r"^# Step \d+ · ", re.M)
_MAX_SIBLINGS = 50  # ponytail: linear probe; 50 foreign analysis_steps files is absurd


def _log_path(workspace: Path) -> Optional[Path]:
    """The first analysis_steps[-N].py that is new or was started by this tool. A file of
    that name without the marker belongs to someone else; appending would corrupt it."""
    for n in range(1, _MAX_SIBLINGS + 1):
        candidate = workspace / ("analysis_steps.py" if n == 1 else f"analysis_steps-{n}.py")
        if not candidate.exists():
            return candidate
        try:
            with candidate.open(encoding="utf-8") as fh:
                if fh.readline().rstrip("\n") == MARKER:
                    return candidate
        except (OSError, UnicodeDecodeError):
            continue
    return None


def append_step(
    workspace: Path, code: str, *, failed: bool, now: Optional[float] = None
) -> Optional[Path]:
    """Append one block; returns the log's path, or None when it could not be written.
    Never raises: the log is a convenience and must never fail an analysis."""
    try:
        path = _log_path(Path(workspace))
        if path is None:
            return None
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        # Counted from the file, not held in memory, so numbering survives engine restarts.
        n = len(_HEADER.findall(existing)) + 1
        body = code.rstrip("\n")
        if failed:
            # Kept, not dropped: a failed call can still have changed the data (df changed,
            # then an error), so leaving it out would replay something different from what ran.
            body = "# This step failed. It may have changed the data before it stopped.\n" + "\n".join(
                f"# {line}" if line else "#" for line in body.splitlines()
            )
        stamp = time.strftime("%H:%M", time.localtime(now))
        head = "" if existing else MARKER + "\n"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{head}\n# Step {n} · {stamp}\n{body}\n")
        return path
    except (OSError, UnicodeDecodeError):
        return None


def append_restart(workspace: Path) -> Optional[Path]:
    """Mark a kernel restart, so a reader knows later steps start from an empty session."""
    try:
        path = _log_path(Path(workspace))
        if path is None or not path.exists():
            return None
        with path.open("a", encoding="utf-8") as fh:
            fh.write(
                "\n# The Python session restarted here. "
                "The steps below start from an empty session.\n"
            )
        return path
    except OSError:
        return None
