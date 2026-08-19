"""Spill — keep an oversized tool result out of the context window without losing it.

Borrowed from deepseek-harness, whose tool pipeline replaces an over-budget result with a
reference rather than truncating it away. The failure this prevents is specific to knowledge
work: a single ``read_workbook`` on a wide sheet, a ``run_python`` that prints a frame, or a
connector returning a large payload can consume a whole context window in one tool call, and
the model then compacts away the earlier conversation to make room for output nobody wanted.

The design keeps three properties:

* **Nothing is lost.** The full content is written to a file the agent can read back with
  ``read_file``, so a spill is a redirection, not a truncation.
* **Head and tail both survive.** Errors and totals usually sit at the end; a plain head-only
  cut hides exactly the part that mattered.
* **The model is told what happened**, in the same string it is reading, so it can decide to
  narrow its query instead of blindly retrying the same call.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

# Roughly 15k tokens of text — big enough that ordinary results never spill, small enough that
# one runaway result can't dominate a turn.
DEFAULT_LIMIT = 60_000
_HEAD = 2_000
_TAIL = 1_000


class SpillStore:
    """Writes over-budget tool output to ``directory`` and returns a summary in its place."""

    def __init__(self, directory: str | Path, *, limit: int = DEFAULT_LIMIT) -> None:
        self.directory = Path(directory)
        self.limit = max(int(limit), _HEAD + _TAIL + 200)
        self.spilled = 0

    def maybe_spill(self, content: str, *, label: str = "result") -> str:
        """Return ``content`` unchanged, or a head/tail summary pointing at the spill file."""
        if not isinstance(content, str) or len(content) <= self.limit:
            return content

        path = self._write(content, label=label)
        head = content[:_HEAD]
        tail = content[-_TAIL:]
        location = str(path) if path else "(could not be saved to disk)"
        return (
            f"{head}\n\n"
            f"… [{len(content) - _HEAD - _TAIL:,} characters omitted — this result was too "
            f"large for the conversation and was saved in full to:\n{location}\n"
            f"Read that file (or re-run with a narrower query, a filter, or an aggregation) "
            f"to see the rest.] …\n\n"
            f"{tail}"
        )

    def _write(self, content: str, *, label: str) -> Optional[Path]:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            # Content-addressed: an identical result spilled twice reuses one file instead of
            # filling the workspace with duplicates.
            digest = hashlib.sha256(content.encode("utf-8", "replace")).hexdigest()[:12]
            safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)[:40] or "result"
            path = self.directory / f"{safe}-{digest}.txt"
            if not path.exists():
                path.write_text(content, encoding="utf-8", errors="replace")
            self.spilled += 1
            return path
        except OSError:
            # A spill that cannot be written must not fail the turn: the caller still gets its
            # head/tail summary, just without a file to point at.
            return None
