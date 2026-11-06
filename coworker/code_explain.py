"""Plain-language notes for an analysis script, for a researcher who does not read code.

The model's reply is checked line range by line range before the panel sees it: a
non-coder trusts the notes, so a note pointing at the wrong lines, or code silently left
out, would be worse than no notes (spec 2026-11-06).
"""

from __future__ import annotations

import json
from typing import Any, Optional

MAX_LINES = 1500
_NOTE_CAP = 400
_CHOICE_CAP = 300

_LANGUAGES = {
    "en": "English",
    "zh": "Simplified Chinese",
    "no": "Norwegian (Bokmål)",
    "fr": "French",
    "es": "Spanish",
    "ja": "Japanese",
    "ar": "Arabic",
    "de": "German",
    "pt": "Portuguese",
}

_PROMPT = """You explain research analysis code to a researcher who does not read code. \
They need to check what was done to their data before they report it.

You get a script with line numbers. Split it, in order, into the steps a researcher would \
recognise (load the data, clean it, recode variables, fit a model, make a chart). Return \
ONLY this JSON, nothing else:
{{"steps": [{{"start": 1, "end": 4, "note": "...", "choice": null}}]}}

Rules:
- start and end are line numbers from the listing. Steps do not overlap.
- note: one or two plain sentences on what the step does to the data. No code words, no \
variable names unless the researcher would know them from their own data.
- choice: one sentence on a decision a reviewer would ask about (how missing values are \
handled, a one-sided test, a hand-picked cut-off, an outlier rule, a filter that removes \
cases, a weighting choice), or null when there is none.
- Never state numbers, counts, percentages or results. You have not seen the data, and a \
reader would trust a number you made up.
- Write note and choice in {language}."""


def system_prompt(language: str) -> str:
    return _PROMPT.format(language=_LANGUAGES.get(language, "English"))


def numbered(source: str) -> tuple[str, int, bool]:
    """The listing the model sees, how many lines it covers, and whether it was cut."""
    # split("\n"), not splitlines(): splitlines also breaks on form feeds and  , and
    # the panel splits on "\n" only, so line numbers would drift between the two.
    lines = source.rstrip("\n").split("\n") if source.strip() else []
    shown = lines[:MAX_LINES]
    listing = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(shown))
    return listing, len(shown), len(lines) > MAX_LINES


def _loads(raw: str) -> Any:
    # Models wrap JSON in fences or a sentence; the object itself is between the braces.
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(raw[start : end + 1])
    except ValueError:
        return None


def parse_steps(raw: str, line_count: int) -> Optional[list[dict[str, Any]]]:
    """Valid steps in order, with every uncovered line range as an empty step; None when
    nothing usable came back."""
    data = _loads(raw or "")
    items = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return None
    valid: list[dict[str, Any]] = []
    last = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        start, end, note = item.get("start"), item.get("end"), item.get("note")
        if not (isinstance(start, int) and isinstance(end, int) and isinstance(note, str)):
            continue
        if not (last < start <= end <= line_count) or not note.strip():
            continue
        choice = item.get("choice")
        valid.append(
            {
                "start": start,
                "end": end,
                "note": note.strip()[:_NOTE_CAP],
                "choice": choice.strip()[:_CHOICE_CAP]
                if isinstance(choice, str) and choice.strip()
                else None,
            }
        )
        last = end
    if not valid:
        return None
    # No code is ever hidden from the researcher: gaps become steps with no note.
    out: list[dict[str, Any]] = []
    cursor = 1
    for step in valid:
        if step["start"] > cursor:
            out.append({"start": cursor, "end": step["start"] - 1, "note": "", "choice": None})
        out.append(step)
        cursor = step["end"] + 1
    if cursor <= line_count:
        out.append({"start": cursor, "end": line_count, "note": "", "choice": None})
    return out
