# Plain-language code view: implementation plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A researcher who cannot read code can open the analysis Mimi ran, read each step as a plain-language note with any choice worth checking, and ask Mimi about specific lines.

**Architecture:** `run_python` appends every block to `analysis_steps.py` in the session folder and names it in its result, so the existing artifact harvesting lists it. Scripts that ran (`run_python` log, `run_r` scripts) are exempt from the "machinery" filter by path. A new route makes one model call per file version and language, validates the returned line ranges, and caches the result in the app data folder. The right rail opens code artifacts in a new `CodeView` component with a Plain language tab and a Code tab.

**Tech stack:** Python 3 / FastAPI sidecar (`coworker/`), pytest; React + TypeScript (`surfaces/gui/src/`), vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-11-06-plain-language-code-view-design.md`. Read it first.

**House rules (from `AGENTS.md`):** test names are sentences about behaviour. Comments explain *why*, never what. Every user-visible string is plain language: no jargon, no emoji. Commit locally after each task; **never push, tag, build or release.** Run backend commands from the repo root with `.venv/bin/pytest` and `.venv/bin/ruff`. Run GUI commands from `surfaces/gui/`.

## File map

| File | Status | Responsibility |
|---|---|---|
| `coworker/tools/analysis/step_log.py` | create | Write and number the step log; never touch a file it did not start |
| `coworker/tools/analysis/python_tool.py` | modify | Call the step log from `run_python` / `reset_python`; mention it in the schema |
| `coworker/server/manager.py` | modify | Suffix sets, `"script"` harvest key, ran-set exemption, `explain_artifact` |
| `coworker/code_explain.py` | create | Prompt, numbered listing, parse and validate the model's steps |
| `coworker/server/app.py` | modify | `POST /v1/sessions/{id}/artifacts/explain` |
| `surfaces/gui/src/api.ts` | modify | `explainArtifact`, `CodeStep`, `CodeNotes` |
| `surfaces/gui/src/components/CodeView.tsx` | create | The two tabs, steps, Show code, line numbers, Ask Mimi |
| `surfaces/gui/src/components/RightRail.tsx` | modify | Route `code` to `CodeView`; leave `code` out of click-to-pin; `kindFromPath` |
| `surfaces/gui/src/i18n.tsx` | modify | New strings in all nine languages |
| `surfaces/gui/src/styles.css` | modify | CodeView styles beside `.artifact-code` |
| tests | create/modify | see each task |

---

## Chunk 1: The step log

### Task 1: `step_log.py`

**Files:**
- Create: `coworker/tools/analysis/step_log.py`
- Test: `tests/test_analysis_step_log.py`

- [ ] **Step 1: Write the failing tests**

```python
"""The analysis written down as it runs, so a researcher has a script to read and re-run."""

from __future__ import annotations

from coworker.tools.analysis.step_log import MARKER, append_restart, append_step


def test_a_successful_block_is_written_as_live_code_under_a_step_header(tmp_path):
    path = append_step(tmp_path, "df = pd.read_csv('a.csv')", failed=False, now=0)
    text = path.read_text(encoding="utf-8")
    assert path.name == "analysis_steps.py"
    assert text.startswith(MARKER + "\n")
    assert "# Step 1 · " in text
    assert "\ndf = pd.read_csv('a.csv')\n" in text


def test_a_failed_block_is_kept_commented_out_with_a_warning(tmp_path):
    path = append_step(tmp_path, "df = df.dropna()\nraise ValueError", failed=True, now=0)
    text = path.read_text(encoding="utf-8")
    assert "may have changed the data" in text
    assert "# df = df.dropna()" in text
    assert "\ndf = df.dropna()" not in text


def test_step_numbers_continue_from_the_headers_already_in_the_file(tmp_path):
    append_step(tmp_path, "a = 1", failed=False, now=0)
    append_step(tmp_path, "b = 2", failed=True, now=0)
    path = append_step(tmp_path, "c = 3", failed=False, now=0)
    text = path.read_text(encoding="utf-8")
    assert "# Step 3 · " in text and "# Step 4 · " not in text


def test_the_log_never_appends_to_a_file_it_did_not_start(tmp_path):
    theirs = tmp_path / "analysis_steps.py"
    theirs.write_text("print('my own script')\n", encoding="utf-8")
    path = append_step(tmp_path, "a = 1", failed=False, now=0)
    assert path.name == "analysis_steps-2.py"
    assert theirs.read_text(encoding="utf-8") == "print('my own script')\n"


def test_a_restart_note_is_written_only_into_an_existing_log(tmp_path):
    assert append_restart(tmp_path) is None
    assert not (tmp_path / "analysis_steps.py").exists()
    append_step(tmp_path, "a = 1", failed=False, now=0)
    append_restart(tmp_path)
    text = (tmp_path / "analysis_steps.py").read_text(encoding="utf-8")
    assert "restarted" in text and "# Step 2" not in text


def test_a_folder_that_cannot_be_written_returns_none_instead_of_raising(tmp_path):
    missing = tmp_path / "gone"
    assert append_step(missing, "a = 1", failed=False, now=0) is None
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `.venv/bin/pytest tests/test_analysis_step_log.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'coworker.tools.analysis.step_log'`

- [ ] **Step 3: Implement**

```python
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
        existing = path.read_text(encoding="utf-8") if path.exists() else ""  # may raise UnicodeDecodeError
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
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/bin/pytest tests/test_analysis_step_log.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add coworker/tools/analysis/step_log.py tests/test_analysis_step_log.py
git commit -m "Write every Python analysis step to a script the researcher can read"
```

### Task 2: Wire the log into `run_python` and `reset_python`

**Files:**
- Modify: `coworker/tools/analysis/python_tool.py` (schema description near line 28; `python_tools()` near lines 130-155)
- Test: `tests/test_analysis_step_log.py` (append)

- [ ] **Step 1: Write the failing tests** (append to the same file)

```python
from types import SimpleNamespace

from coworker.tools.analysis import python_tool


class _FakeKernel:
    def __init__(self, reply):
        self.reply = reply

    def run(self, code, timeout):
        return self.reply

    def reset(self):
        pass


def _tools(tmp_path, monkeypatch, reply):
    monkeypatch.setattr(python_tool.KernelHandle, "kernel", lambda self: _FakeKernel(reply))
    run, reset = python_tool.python_tools(SimpleNamespace(workspace=tmp_path))
    return run, reset


def test_run_python_names_the_step_log_in_its_result(tmp_path, monkeypatch):
    run, _ = _tools(tmp_path, monkeypatch, {"ok": True, "stdout": "1"})
    result = run(code="print(1)")
    assert result["files"] == ["analysis_steps.py"]
    assert "print(1)" in (tmp_path / "analysis_steps.py").read_text(encoding="utf-8")


def test_a_failed_run_is_logged_as_failed(tmp_path, monkeypatch):
    reply = {"ok": False, "error": {"message": "boom", "kind": "exception"}}
    run, _ = _tools(tmp_path, monkeypatch, reply)
    run(code="x = 1/0")
    assert "# x = 1/0" in (tmp_path / "analysis_steps.py").read_text(encoding="utf-8")


def test_a_lost_kernel_writes_a_restart_note_after_the_step(tmp_path, monkeypatch):
    reply = {"ok": False, "error": {"message": "died", "kind": "crash", "state_lost": True}}
    run, _ = _tools(tmp_path, monkeypatch, reply)
    run(code="huge()")
    text = (tmp_path / "analysis_steps.py").read_text(encoding="utf-8")
    assert text.index("# huge()") < text.index("restarted")


def test_reset_python_writes_a_restart_note(tmp_path, monkeypatch):
    run, reset = _tools(tmp_path, monkeypatch, {"ok": True})
    run(code="a = 1")
    reset()
    assert "restarted" in (tmp_path / "analysis_steps.py").read_text(encoding="utf-8")


def test_the_schema_tells_the_model_where_the_steps_are_saved():
    assert "analysis_steps.py" in python_tool._RUN_SCHEMA["function"]["description"]
```

If `python_tools` wraps `run_python` with `reports_failures` in a way that changes the call signature, call it as the existing tests call wrapped tools (check `coworker/tools/registry.py` `reports_failures`). The tests only rely on `run(code=...)` returning the dict.

- [ ] **Step 2: Run them and confirm they fail**

Run: `.venv/bin/pytest tests/test_analysis_step_log.py -q`
Expected: the five new tests FAIL (`KeyError: 'files'`, missing file, schema assertion)

- [ ] **Step 3: Implement**

At the top of `python_tool.py` add `from .step_log import append_restart, append_step`.

Add one sentence to the end of the `run_python` description string:

```python
            "work. Requires approval, like any code execution. Each block is also saved, in "
            "order, to analysis_steps.py in the session folder so the researcher can read "
            "and re-run the analysis."
```

(replace the existing final `"work. Requires approval, like any code execution."` fragment).

Replace `run_python` and `reset_python` inside `python_tools()`:

```python
    def run_python(code: str, timeout: int = int(DEFAULT_TIMEOUT)) -> dict[str, Any]:
        if not isinstance(code, str) or not code.strip():
            return {"error": "code is required"}
        try:
            raw = handle.kernel().run(code, timeout=float(timeout or DEFAULT_TIMEOUT))
        except (RuntimeError, OSError) as exc:
            # Nothing ran, so there is nothing to log.
            return {"error": f"the analysis kernel could not start: {exc}"}
        result = _shape_result(raw, roots)
        logged = append_step(Path(workspace), code, failed="error" in result)
        if logged is not None:
            # Named in the result so the artifacts list picks it up: in a granted folder only
            # paths a tool names are listed (manager._touched_paths).
            result["files"] = [display_path(logged, roots)]
        if result.get("state_lost"):
            append_restart(Path(workspace))
        return result

    def reset_python() -> dict[str, Any]:
        try:
            handle.kernel().reset()
        except (RuntimeError, OSError) as exc:
            return {"error": f"the analysis kernel could not restart: {exc}"}
        append_restart(Path(workspace))
        return {"ok": True, "note": "the Python kernel is empty; reload any data you need"}
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_analysis_step_log.py tests/test_analysis_kernel.py tests/test_analysis_data.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add coworker/tools/analysis/python_tool.py tests/test_analysis_step_log.py
git commit -m "Save each run_python block to analysis_steps.py and name it in the result"
```

---

## Chunk 2: Which scripts are listed

### Task 3: Suffix sets, the `script` key, and the ran-set exemption

**Files:**
- Modify: `coworker/server/manager.py`. `_ARTIFACT_PATH_KEYS` (~2200), `_touched_paths` (~2203-2276), `_MACHINERY_SUFFIXES` (~2303), `_meaningful` (~2311), `list_artifacts` (~2364-2481) and its walk `suffixes` (~2414), `_artifact_kind` (~7119).
- Test: `tests/test_artifacts_scope.py` (append; reuse its `_fixture`, `_turn`, `_session` helpers)

- [ ] **Step 1: Write the failing tests**

```python
from coworker.server.manager import _artifact_kind


def test_r_stata_and_sql_files_open_as_code():
    for name in ("clean.R", "clean.r", "model.do", "query.sql"):
        assert _artifact_kind(Path(name)) == "code", name


def test_the_step_log_stays_listed_beside_the_chart_it_produced(tmp_path):
    folder = tmp_path / "Study 2"
    (folder / "figures").mkdir(parents=True)
    (folder / "figures" / "fig1.png").write_bytes(b"png")
    (folder / "analysis_steps.py").write_text("# log", encoding="utf-8")
    client, manager = _fixture(tmp_path)
    _session(
        manager,
        "s-log",
        folder,
        _turn(
            "run_python",
            {"code": "plot()"},
            {"ok": True, "figures": ["figures/fig1.png"], "files": ["analysis_steps.py"]},
        ),
    )
    names = [r["name"] for r in manager.list_artifacts("s-log")]
    assert "fig1.png" in names
    assert "analysis_steps.py" in names, "the analysis itself is a deliverable"


def test_an_r_script_from_a_granted_folder_is_listed_once_it_has_run(tmp_path):
    folder = tmp_path / "Thesis"
    folder.mkdir()
    (folder / "clean.R").write_text("x <- 1", encoding="utf-8")
    (folder / "table.csv").write_text("a,b", encoding="utf-8")
    client, manager = _fixture(tmp_path)
    _session(
        manager,
        "s-r",
        folder,
        _turn("run_r", {"script": "clean.R"}, {"script": "clean.R", "ok": True}, "c1")
        + _turn("write_file", {"path": "table.csv"}, {"path": "table.csv"}, "c2"),
    )
    rows = {r["name"]: r for r in manager.list_artifacts("s-r")}
    assert "clean.R" in rows and rows["clean.R"]["kind"] == "code"
    assert "table.csv" in rows


def test_a_step_log_name_the_tool_did_not_write_stays_hidden_as_machinery(tmp_path, monkeypatch):
    client, manager = _fixture(tmp_path)
    monkeypatch.setattr(manager, "scratch_base", lambda: tmp_path / "scratch")
    workspace = Path(manager._provision_scratch("s-name"))
    (workspace / "analysis_steps.py").write_text("print('mine')", encoding="utf-8")
    (workspace / "students.xlsx").write_bytes(b"the point")
    _session(
        manager,
        "s-name",
        workspace,
        _turn("write_file", {"path": "analysis_steps.py"}, {"path": "analysis_steps.py"}),
    )
    names = [r["name"] for r in manager.list_artifacts("s-name")]
    assert "students.xlsx" in names
    assert "analysis_steps.py" not in names, "exempt by having run, never by name"
```

The existing `test_the_script_that_made_the_deliverable_is_not_a_deliverable` already proves that a script that was only written stays hidden; it must keep passing.

- [ ] **Step 2: Run them and confirm they fail**

Run: `.venv/bin/pytest tests/test_artifacts_scope.py -q`
Expected: three new tests FAIL. `test_a_step_log_name_the_tool_did_not_write_stays_hidden_as_machinery` already passes: it pins today's behaviour so the exemption cannot widen to names. Every existing test passes.

- [ ] **Step 3: Implement**

1. `_ARTIFACT_PATH_KEYS = ("path", "output_path", "target", "saved_to", "file", "script")`. Add a comment: run_r names its script under `script`, and an R script brought in a granted folder is otherwise never a row.

2. Under `_ARTIFACT_PATH_LISTS`, add:

```python
    # Scripts that WERE the analysis, not means to an end: listed even though their suffix
    # is machinery (spec 2026-11-06). Exempt by path, never by name.
    _RAN_TOOLS = frozenset({"run_python", "run_r"})
```

3. `_touched_paths(self, record, roots, ran: Optional[set[str]] = None)`. Replace `_keep` and `_harvest`, and pass the flag at both harvest sites:

```python
        def _keep(raw: Any, ran_call: bool = False) -> None:
            if not isinstance(raw, str) or not raw.strip():
                return
            candidate = Path(raw).expanduser()
            candidates = [candidate] if candidate.is_absolute() else [
                (r / candidate) for r in roots
            ]
            for cand in candidates:
                try:
                    resolved = cand.resolve()
                except OSError:
                    continue
                if not resolved.is_file():
                    continue
                if not any(
                    resolved == r or r in resolved.parents for r in roots
                ):
                    continue  # never leave the folders this session was granted
                if ran_call and ran is not None:
                    ran.add(str(resolved))
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(resolved)
                return

        def _harvest(payload: Any, ran_call: bool = False) -> None:
            if not isinstance(payload, dict):
                return
            for key in self._ARTIFACT_PATH_KEYS:
                _keep(payload.get(key), ran_call)
            for key in self._ARTIFACT_PATH_LISTS:
                value = payload.get(key)
                if isinstance(value, list):
                    for item in value:
                        _keep(item if isinstance(item, str) else (item or {}).get("path")
                              if isinstance(item, dict) else None, ran_call)
```

In the loop: `_harvest(args, name in self._RAN_TOOLS)`. For the result, keep the tool name: replace the `names.get(...) not in self._ARTIFACT_TOOLS` check with

```python
            tool = names.get(str(message.get("tool_call_id") or ""))
            if tool not in self._ARTIFACT_TOOLS:
                continue
```

and finish with `_harvest(content, tool in self._RAN_TOOLS)`.

4. `_MACHINERY_SUFFIXES`: add `".do"` beside `".r"`.

5. `_meaningful`:

```python
    @classmethod
    def _meaningful(
        cls, rows: list[dict[str, Any]], ran: frozenset[str] | set[str] = frozenset()
    ) -> list[dict[str, Any]]:
        """Drop machinery — unless machinery is all there is, or the script WAS the analysis.

        A coding session whose deliverable IS the script would otherwise get an empty
        panel, which is worse than a noisy one.
        """
        kept = [
            r
            for r in rows
            if Path(str(r.get("name", ""))).suffix.lower() not in cls._MACHINERY_SUFFIXES
            or str(r.get("abs_path", "")) in ran
        ]
        return kept or rows
```

The ran paths are the same resolved paths `_artifact_row` turns into `abs_path`. The scratch walk dedupes against seeded rows by inode, so a run script always arrives as a seeded row and plain string comparison holds.

6. `list_artifacts`: declare `ran: set[str] = set()` before `if record is not None:`. Call `self._touched_paths(record, roots, ran)`, and pass `ran` to **both** `_meaningful` calls.

7. The walk `suffixes` set: add `".r"`, `".do"`, `".sql"`.

8. `_artifact_kind`: `if suffix in {".py", ".js", ".ts", ".tsx", ".css", ".json", ".r", ".do", ".sql"}: return "code"`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_artifacts_scope.py tests/test_artifact_walk.py -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add coworker/server/manager.py tests/test_artifacts_scope.py
git commit -m "List the scripts that ran the analysis, and open R, Stata and SQL as code"
```

---

## Chunk 3: Making the notes

### Task 4: `code_explain.py` (prompt, listing, validation)

**Files:**
- Create: `coworker/code_explain.py`
- Test: `tests/test_code_explain.py`

- [ ] **Step 1: Write the failing tests**

```python
"""Turning a model's reply into steps the panel can trust: every range checked, no line hidden."""

from __future__ import annotations

import json

from coworker.code_explain import MAX_LINES, numbered, parse_steps, system_prompt


def _reply(*steps):
    return json.dumps({"steps": [dict(zip(("start", "end", "note", "choice"), s)) for s in steps]})


def test_valid_steps_come_back_in_order():
    steps = parse_steps(_reply((1, 2, "Loads the survey.", None), (3, 4, "Drops speeders.", "Cut-off of 120 seconds is a choice.")), 4)
    assert [(s["start"], s["end"]) for s in steps] == [(1, 2), (3, 4)]
    assert steps[1]["choice"].startswith("Cut-off")


def test_a_step_outside_the_file_is_dropped_and_its_lines_still_shown():
    steps = parse_steps(_reply((1, 2, "Loads.", None), (3, 99, "Nonsense.", None)), 4)
    assert steps[0]["note"] == "Loads."
    assert steps[1] == {"start": 3, "end": 4, "note": "", "choice": None}


def test_overlapping_steps_keep_the_first():
    steps = parse_steps(_reply((1, 3, "A.", None), (2, 4, "B.", None)), 4)
    assert [s["note"] for s in steps] == ["A.", ""]
    assert steps[1]["start"] == 4


def test_lines_no_step_mentions_become_an_empty_step():
    steps = parse_steps(_reply((2, 3, "Middle.", None)), 5)
    assert [(s["start"], s["end"], s["note"]) for s in steps] == [(1, 1, ""), (2, 3, "Middle."), (4, 5, "")]


def test_json_wrapped_in_a_code_fence_is_accepted():
    raw = "```json\n" + _reply((1, 1, "One.", None)) + "\n```"
    assert parse_steps(raw, 1)[0]["note"] == "One."


def test_a_reply_that_is_not_json_gives_nothing():
    assert parse_steps("Sorry, I cannot help with that.", 3) is None


def test_a_reply_with_no_valid_step_gives_nothing():
    assert parse_steps(_reply((5, 9, "Out of range.", None)), 3) is None


def test_the_listing_is_numbered_and_cut_at_the_limit():
    listing, shown, cut = numbered("\n".join(f"x{i}" for i in range(MAX_LINES + 5)))
    assert listing.startswith("1: x0\n2: x1")
    assert shown == MAX_LINES and cut is True


def test_the_prompt_asks_for_the_researchers_language_and_forbids_numbers():
    prompt = system_prompt("zh")
    assert "Simplified Chinese" in prompt
    assert "Never state numbers" in prompt
    assert "English" in system_prompt("xx")
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `.venv/bin/pytest tests/test_code_explain.py -q`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement**

```python
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
    # split("\n"), not splitlines(): splitlines also breaks on form feeds and \u2028, and
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
                "choice": choice.strip()[:_CHOICE_CAP] if isinstance(choice, str) and choice.strip() else None,
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
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_code_explain.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add coworker/code_explain.py tests/test_code_explain.py
git commit -m "Check every line range a model gives for a script before showing it"
```

### Task 5: `explain_artifact` and the route

**Files:**
- Modify: `coworker/server/manager.py` (add `import hashlib` with the stdlib imports; add `explain_artifact` right after `comment_artifact`)
- Modify: `coworker/server/app.py` (beside `session_artifact_comment`, ~line 865)
- Test: `tests/test_code_explain_route.py`

`tests/conftest.py` already isolates `state_dir()` per test (`_isolated_state_dir`), so the cache needs no extra setup.

- [ ] **Step 1: Write the failing tests**

```python
"""One model call per version of a script, only when asked, cached by content."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from coworker.providers import AssistantTurn, ModelCapabilities, ProviderClient
from coworker.server import SessionManager, create_app

GOOD = json.dumps({"steps": [{"start": 1, "end": 2, "note": "Loads the survey.", "choice": None}]})


class _ExplainProvider(ProviderClient):
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    def complete(self, *, model, messages, tools=None, **settings):
        self.calls.append(messages)
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return AssistantTurn(text=item, finish_reason="stop")

    def capabilities(self, model):
        return ModelCapabilities()


def _setup(tmp_path, replies):
    provider = _ExplainProvider(replies)
    manager = SessionManager(workspace=tmp_path, provider=provider)
    engine = manager.get_engine("s1", workspace=str(tmp_path))
    manager.save("s1", engine)
    (tmp_path / "clean.py").write_text("import pandas as pd\ndf = pd.read_csv('a.csv')\n", encoding="utf-8")
    return manager, provider


def test_explaining_a_script_returns_steps_that_cover_it(tmp_path):
    manager, _ = _setup(tmp_path, [GOOD])
    result = manager.explain_artifact("s1", "clean.py")
    assert result["ok"] is True
    assert result["steps"][0]["note"] == "Loads the survey."
    assert result["truncated"] is False


def test_an_unchanged_script_is_not_explained_twice(tmp_path):
    manager, provider = _setup(tmp_path, [GOOD])
    manager.explain_artifact("s1", "clean.py")
    again = manager.explain_artifact("s1", "clean.py")
    assert again["ok"] is True and len(provider.calls) == 1


def test_asking_only_for_saved_notes_never_calls_the_model(tmp_path):
    manager, provider = _setup(tmp_path, [])
    result = manager.explain_artifact("s1", "clean.py", cached_only=True)
    assert result == {"ok": False, "cached": False}
    assert provider.calls == []


def test_a_changed_script_is_explained_again(tmp_path):
    manager, provider = _setup(tmp_path, [GOOD, GOOD])
    manager.explain_artifact("s1", "clean.py")
    (tmp_path / "clean.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    manager.explain_artifact("s1", "clean.py")
    assert len(provider.calls) == 2


def test_a_reply_that_is_not_json_is_an_error_and_is_not_saved(tmp_path):
    manager, provider = _setup(tmp_path, ["no idea", GOOD])
    assert manager.explain_artifact("s1", "clean.py")["ok"] is False
    assert manager.explain_artifact("s1", "clean.py")["ok"] is True
    assert len(provider.calls) == 2


def test_a_provider_failure_is_an_error_not_a_crash(tmp_path):
    manager, _ = _setup(tmp_path, [RuntimeError("gateway down")])
    assert manager.explain_artifact("s1", "clean.py")["ok"] is False


def test_notes_are_asked_for_in_the_app_language(tmp_path):
    manager, provider = _setup(tmp_path, [GOOD])
    manager.set_language("zh")
    manager.explain_artifact("s1", "clean.py")
    assert "Simplified Chinese" in provider.calls[0][0]["content"]


def test_an_empty_script_is_refused_without_calling_the_model(tmp_path):
    manager, provider = _setup(tmp_path, [])
    (tmp_path / "empty.py").write_text("\n", encoding="utf-8")
    assert manager.explain_artifact("s1", "empty.py")["ok"] is False
    assert provider.calls == []


def test_a_file_outside_the_granted_folders_is_refused(tmp_path):
    manager, provider = _setup(tmp_path, [])
    assert manager.explain_artifact("s1", "/etc/hosts")["ok"] is False
    assert provider.calls == []


def test_the_route_passes_path_and_cached_only(tmp_path):
    manager, _ = _setup(tmp_path, [])
    client = TestClient(create_app(manager))
    body = client.post("/v1/sessions/s1/artifacts/explain", json={"path": "clean.py", "cached_only": True}).json()
    assert body == {"ok": False, "cached": False}
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `.venv/bin/pytest tests/test_code_explain_route.py -q`
Expected: FAIL with `AttributeError: 'SessionManager' object has no attribute 'explain_artifact'`

- [ ] **Step 3: Implement**

In `manager.py`, add `import hashlib` between `import asyncio` and `import json` (ruff's import sort checks the order). Add `from .. import code_explain` immediately before `from ..agent import build_engine`. Then add:

```python
    def explain_artifact(
        self, session_id: str, path: str, *, cached_only: bool = False
    ) -> dict[str, Any]:
        """Plain-language notes for a script in this session's folders (spec 2026-11-06).

        One model call per version of the file per language, only when the researcher asks:
        opening a file must never spend credits silently. `cached_only` lets the panel show
        notes it already has without that risk.
        """
        target, err = self._artifact_target(session_id, path)
        if target is None:
            return {"ok": False, "error": err}
        if _artifact_kind(target) != "code":
            return {"ok": False, "error": "only scripts can be explained"}
        try:
            source = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return {"ok": False, "error": str(exc)}
        language = str(self._prefs.get("language") or "en")
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        cache = state_dir() / "explain" / f"{digest}-{language}.json"
        try:
            return {**json.loads(cache.read_text(encoding="utf-8")), "path": path}
        except (OSError, ValueError):
            pass
        if cached_only:
            return {"ok": False, "cached": False}
        engine = self.get_engine(session_id)
        if engine is None:
            return {"ok": False, "error": "this conversation has no folder"}
        listing, shown, cut = code_explain.numbered(source)
        if shown == 0:
            return {"ok": False, "error": "this script is empty"}  # no call that must fail
        try:
            turn = engine.provider.complete(
                model=engine.model,
                messages=[
                    {"role": "system", "content": code_explain.system_prompt(language)},
                    {"role": "user", "content": f"File: {target.name}\n\n{listing}"},
                ],
                temperature=0.2,
                # Same reasoning as _generate_autotitle: reasoning-routed models spend hidden
                # tokens first, and a tight cap returns nothing.
                max_tokens=8000,
                reasoning_effort="none",
            )
        except Exception as exc:  # any provider failure is the same message to the panel
            logger.warning("explain_artifact: model call failed: %s", exc)
            return {"ok": False, "error": "the model could not write notes"}
        steps = code_explain.parse_steps(getattr(turn, "text", "") or "", shown)
        if steps is None:
            return {"ok": False, "error": "the model's notes could not be read"}
        result = {"ok": True, "steps": steps, "lines_explained": shown, "truncated": cut}
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(result), encoding="utf-8")
        except OSError:
            pass  # notes still show; the next open just asks again
        return {**result, "path": path}
```

If the module's logger is named differently from `logger`, use the existing one (`grep -n "^logger\|getLogger" coworker/server/manager.py`).

In `app.py`, next to `session_artifact_comment`:

```python
    @app.post("/v1/sessions/{session_id}/artifacts/explain")
    def session_artifact_explain(session_id: str, body: dict) -> dict[str, Any]:
        """Plain-language notes for a script. A plain `def` on purpose: FastAPI runs it in
        its thread pool, so the blocking model call never stalls the event loop."""
        body = body or {}
        return manager.explain_artifact(
            session_id, str(body.get("path", "")), cached_only=bool(body.get("cached_only"))
        )
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/pytest tests/test_code_explain_route.py tests/test_code_explain.py tests/test_artifacts_scope.py -q`
Expected: all pass

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check coworker tests`
Expected: no errors

```bash
git add coworker/server/manager.py coworker/server/app.py tests/test_code_explain_route.py
git commit -m "Explain a script in plain language once per version, on the researcher's click"
```

---

## Chunk 4: The panel

All commands in this chunk run from `surfaces/gui/`.

### Task 6: API client and `kindFromPath`

**Files:**
- Modify: `surfaces/gui/src/api.ts` (after `readArtifact`, ~line 246)
- Modify: `surfaces/gui/src/components/RightRail.tsx:54`

- [ ] **Step 1: Implement** (typed plumbing; exercised by Task 7's tests)

```ts
/** One step of a script, explained for a researcher who does not read code. */
export interface CodeStep {
  start: number;
  end: number;
  note: string; // "" for lines no step covered: shown, never hidden
  choice: string | null;
}

export interface CodeNotes {
  ok: boolean;
  error?: string;
  cached?: boolean;
  steps?: CodeStep[];
  lines_explained?: number;
  truncated?: boolean;
}

/** Notes for a script. `cachedOnly` never calls the model, so opening a file costs nothing. */
export async function explainArtifact(sessionId: string, path: string, cachedOnly = false): Promise<CodeNotes> {
  const res = await fetch(`${httpBase()}/v1/sessions/${encodeURIComponent(sessionId)}/artifacts/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, cached_only: cachedOnly }),
  });
  return res.json();
}
```

In `RightRail.tsx` `kindFromPath`: `if (["py", "js", "ts", "tsx", "jsx", "json", "sh", "css", "r", "do", "sql"].includes(ext)) return "code";`

- [ ] **Step 2: Type-check**

Run: `npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add src/api.ts src/components/RightRail.tsx
git commit -m "Add the client call for script notes and treat R, Stata and SQL as code"
```

### Task 7: `CodeView.tsx`

**Files:**
- Create: `surfaces/gui/src/components/CodeView.tsx`
- Test: `surfaces/gui/src/components/CodeView.test.tsx`
- Modify: `surfaces/gui/src/styles.css` (next to `.artifact-code`)

- [ ] **Step 1: Write the failing tests**

```tsx
import { describe, it, expect, vi, afterEach, beforeEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CodeView } from "./CodeView";

const SOURCE = "import pandas as pd\ndf = pd.read_csv('survey.csv')\ndf = df[df.attention == 1]\nprint(df.mean())";
const NOTES = {
  ok: true,
  steps: [
    { start: 1, end: 2, note: "Loads the survey answers.", choice: null },
    { start: 3, end: 3, note: "Keeps only people who passed the attention check.", choice: "Dropping people who failed the check is a choice to report." },
    { start: 4, end: 4, note: "", choice: null },
  ],
  lines_explained: 4,
  truncated: false,
};
const explain = vi.fn();
vi.mock("../api", async () => {
  const actual = await vi.importActual<Record<string, unknown>>("../api");
  return { ...actual, explainArtifact: (...a: unknown[]) => explain(...a) };
});

beforeEach(() => explain.mockReset());
afterEach(cleanup);

const view = (onAsk = vi.fn()) =>
  render(<CodeView sessionId="s1" path="analysis_steps.py" name="analysis_steps.py" source={SOURCE} onAsk={onAsk} />);

describe("the plain-language code view", () => {
  it("offers to explain a script it has no notes for, without calling the model on open", async () => {
    explain.mockResolvedValue({ ok: false, cached: false });
    view();
    expect(((await screen.findByRole("button", { name: "Explain this script" })) as HTMLButtonElement).disabled).toBe(false);
    expect(explain).toHaveBeenCalledTimes(1);
    expect(explain.mock.calls[0]).toEqual(["s1", "analysis_steps.py", true]);
  });

  it("shows saved notes at once, each above its folded code", async () => {
    explain.mockResolvedValue(NOTES);
    view();
    expect(await screen.findByText("Keeps only people who passed the attention check.")).toBeTruthy();
    expect(screen.getByText("Choice to check")).toBeTruthy();
    expect(screen.queryByText("df = df[df.attention == 1]")).toBeNull();
  });

  it("reveals a step's own lines, numbered, on Show code", async () => {
    explain.mockResolvedValue(NOTES);
    view();
    await screen.findByText("Loads the survey answers.");
    fireEvent.click(screen.getAllByRole("button", { name: /Show code/ })[1]);
    const line = screen.getByText("df = df[df.attention == 1]").closest("[data-line]")!;
    expect(line.getAttribute("data-line")).toBe("3");
  });

  it("shows every line, numbered, on the Code tab", async () => {
    explain.mockResolvedValue({ ok: false, cached: false });
    view();
    fireEvent.click(await screen.findByRole("tab", { name: "Code" }));
    expect(document.querySelectorAll("[data-line]")).toHaveLength(4);
  });

  it("disables Explain while it runs, and offers a retry when it fails", async () => {
    explain.mockResolvedValueOnce({ ok: false, cached: false });
    let finish: (v: unknown) => void = () => {};
    explain.mockReturnValueOnce(new Promise((r) => (finish = r)));
    view();
    const button = await screen.findByRole("button", { name: "Explain this script" });
    fireEvent.click(button);
    await waitFor(() => expect((screen.getByRole("button", { name: "Explaining…" }) as HTMLButtonElement).disabled).toBe(true));
    finish({ ok: false, error: "the model could not write notes" });
    expect(await screen.findByText("Couldn't write notes for this file. Try again.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Explain this script" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("sends the selected lines, with the file name, when Ask Mimi is clicked", async () => {
    explain.mockResolvedValue(NOTES);
    const onAsk = vi.fn();
    view(onAsk);
    const note = await screen.findByText("Keeps only people who passed the attention check.");
    const range = document.createRange();
    range.selectNodeContents(note);
    window.getSelection()!.removeAllRanges();
    window.getSelection()!.addRange(range);
    fireEvent.mouseUp(note);
    fireEvent.click(screen.getByRole("button", { name: /Ask Mimi about lines 3–3/ }));
    const text = onAsk.mock.calls[0][0] as string;
    expect(text).toContain("analysis_steps.py");
    expect(text).toContain("3: df = df[df.attention == 1]");
  });
});
```

- [ ] **Step 2: Run them and confirm they fail**

Run: `npx vitest run src/components/CodeView.test.tsx`
Expected: FAIL. Cannot resolve `./CodeView`.

- [ ] **Step 3: Implement**

```tsx
import { useEffect, useState } from "react";
import { explainArtifact, type CodeNotes } from "../api";
import { useT } from "../i18n";

// A script read as research steps, for someone who does not read code (spec 2026-11-06).
// The code is never hidden, only folded: a note that a non-coder cannot check against
// the lines it describes would be asking them to take it on trust.

function CodeLines({ lines, from, to }: { lines: string[]; from: number; to: number }) {
  return (
    <pre className="code-block">
      {lines.slice(from - 1, to).map((text, i) => (
        <div key={from + i} className="code-line" data-line={from + i}>
          <span className="code-ln" aria-hidden="true">{from + i}</span>
          <code>{text || " "}</code>
        </div>
      ))}
    </pre>
  );
}

function rangeOf(sel: Selection | null): [number, number] | null {
  if (!sel || sel.isCollapsed || !sel.toString().trim()) return null;
  const pick = (n: Node | null): [number, number] | null => {
    const el = n && (n.nodeType === 1 ? (n as Element) : n.parentElement);
    const line = el?.closest("[data-line]");
    if (line) {
      const v = Number(line.getAttribute("data-line"));
      return [v, v];
    }
    const step = el?.closest("[data-start]");
    return step ? [Number(step.getAttribute("data-start")), Number(step.getAttribute("data-end"))] : null;
  };
  const a = pick(sel.anchorNode);
  const b = pick(sel.focusNode);
  return a && b ? [Math.min(a[0], b[0]), Math.max(a[1], b[1])] : null;
}

export function CodeView({
  sessionId,
  path,
  name,
  source,
  onAsk,
}: {
  sessionId: string;
  path: string;
  name: string;
  source: string;
  onAsk?: (text: string) => void;
}) {
  const t = useT();
  const lines = source.replace(/\n$/, "").split("\n");
  const [tab, setTab] = useState<"plain" | "code">("plain");
  const [notes, setNotes] = useState<CodeNotes | null>(null);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<Set<number>>(new Set());
  const [asking, setAsking] = useState<[number, number] | null>(null);

  // Saved notes for this exact file show at once; nothing is generated, or charged,
  // until the researcher asks.
  useEffect(() => {
    let live = true;
    setNotes(null);
    setFailed(false);
    setOpen(new Set());
    explainArtifact(sessionId, path, true)
      .then((r) => { if (live && r.ok) setNotes(r); })
      .catch(() => {});
    return () => { live = false; };
  }, [sessionId, path, source]);

  const explain = async () => {
    setPending(true);
    setFailed(false);
    try {
      const r = await explainArtifact(sessionId, path);
      if (r.ok) setNotes(r);
      else setFailed(true);
    } catch {
      setFailed(true);
    } finally {
      setPending(false);
    }
  };

  const toggle = (i: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  const ask = () => {
    if (!asking || !onAsk) return;
    const [a, b] = asking;
    const quoted = lines.slice(a - 1, b).map((l, i) => `${a + i}: ${l}`).join("\n");
    onAsk(`${name}, ${t("Lines")} ${a}–${b}:\n\n\`\`\`\n${quoted}\n\`\`\`\n\n${t("What do these lines do to my data? Please explain in plain language.")}`);
    setAsking(null);
    window.getSelection()?.removeAllRanges();
  };

  // Lines no step covered that hold nothing but blank space are noise, not hidden code.
  const steps = (notes?.steps || []).filter(
    (s) => s.note || lines.slice(s.start - 1, s.end).some((l) => l.trim()),
  );

  return (
    <div className="code-view" onMouseUp={() => setAsking(onAsk ? rangeOf(window.getSelection()) : null)}>
      <div className="code-tabs" role="tablist">
        <button role="tab" aria-selected={tab === "plain"} className={"code-tab" + (tab === "plain" ? " active" : "")} onClick={() => setTab("plain")}>
          {t("Plain language")}
        </button>
        <button role="tab" aria-selected={tab === "code"} className={"code-tab" + (tab === "code" ? " active" : "")} onClick={() => setTab("code")}>
          {t("Code")}
        </button>
      </div>
      {asking && (
        <div className="code-ask">
          <button className="btn sm" onClick={ask}>{t("Ask Mimi about lines")} {asking[0]}–{asking[1]}</button>
        </div>
      )}
      {tab === "code" ? (
        <CodeLines lines={lines} from={1} to={lines.length} />
      ) : !notes ? (
        <div className="code-explain-empty">
          <p>{t("Mimi can explain this script step by step in plain language.")}</p>
          <button className="btn sm" disabled={pending} onClick={() => void explain()}>
            {pending ? t("Explaining…") : t("Explain this script")}
          </button>
          {failed && <p className="rail-error">{t("Couldn't write notes for this file. Try again.")}</p>}
        </div>
      ) : (
        <ol className="code-steps">
          {steps.map((s, i) => (
            <li key={s.start} className="code-step" data-start={s.start} data-end={s.end}>
              {s.note && <p className="code-note">{s.note}</p>}
              {s.choice && (
                <p className="code-choice">
                  <span className="code-choice-label">{t("Choice to check")}</span> {s.choice}
                </p>
              )}
              {s.note ? (
                <>
                  <button className="code-toggle" aria-expanded={open.has(i)} onClick={() => toggle(i)}>
                    {open.has(i) ? t("Hide code") : t("Show code")} · {t("Lines")} {s.start}–{s.end}
                  </button>
                  {open.has(i) && <CodeLines lines={lines} from={s.start} to={s.end} />}
                </>
              ) : (
                <CodeLines lines={lines} from={s.start} to={s.end} />
              )}
            </li>
          ))}
          {notes.truncated && (
            <li className="rail-muted">
              {t("Notes stop at line")} {notes.lines_explained}. {t("The Code tab shows the whole script.")}
            </li>
          )}
        </ol>
      )}
    </div>
  );
}
```

CSS, appended beside `.artifact-code` in `styles.css`. Use the variables `.artifact-code` already uses for font, border and muted colour; check them with `grep -n "artifact-code" -A8 src/styles.css`. Replace the variable names below if they differ.

```css
.code-view { display: flex; flex-direction: column; gap: 10px; padding: 16px 20px; }
/* Not rail-mini-btn: that is a 24x24 icon button, and this label wraps into it. */
.code-toggle { align-self: flex-start; padding: 0; border: 0; background: none; color: var(--muted); font-size: 12px; cursor: pointer; }
.code-tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--line); }
.code-tab { padding: 6px 10px; border: 0; background: none; color: var(--muted); cursor: pointer; border-bottom: 2px solid transparent; }
.code-tab.active { color: var(--ink); border-bottom-color: var(--accent); }
.code-ask { position: sticky; top: 0; z-index: 1; }
.code-explain-empty { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; }
.code-steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 14px; }
.code-step { display: flex; flex-direction: column; gap: 6px; }
.code-note { margin: 0; line-height: 1.5; }
.code-choice { margin: 0; padding: 6px 8px; border-left: 3px solid var(--accent); background: var(--paper); font-size: 13px; }
.code-choice-label { font-weight: 600; }
.code-block { margin: 0; padding: 6px 0; font: 12px/1.55 var(--mono, ui-monospace, monospace); overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
.code-line { display: flex; white-space: pre; }
/* Line numbers stay out of a copied selection: researchers paste these lines elsewhere. */
.code-ln { flex: 0 0 3.2em; padding-right: 10px; text-align: right; color: var(--muted); user-select: none; }
```

- [ ] **Step 4: Run the tests**

Run: `npx vitest run src/components/CodeView.test.tsx`
Expected: 6 passed. This project has no jest-dom, so the tests use plain matchers (`toBeTruthy`, `.disabled`); do not add `toBeInTheDocument` or `toBeEnabled`.

- [ ] **Step 5: Commit**

```bash
git add src/components/CodeView.tsx src/components/CodeView.test.tsx src/styles.css
git commit -m "Add a plain-language view for analysis scripts with Ask Mimi on selected lines"
```

### Task 8: Use `CodeView` in the rail and leave code out of click-to-pin

**Files:**
- Modify: `surfaces/gui/src/components/RightRail.tsx` (import; the `onClick` at ~838; the render chain before the final `<pre className="artifact-code">` at ~940)
- Test: `surfaces/gui/src/components/RightRail.artifacts.test.tsx`

- [ ] **Step 1: Write the failing test**

In `RightRail.artifacts.test.tsx`:
- Add `{ path: "analysis_steps.py", name: "analysis_steps.py", kind: "code", size: 64, modified_at: 3 }` to `artifacts`.
- Extend the mocked `readArtifact`: `path.endsWith(".py") ? { ok: true, path, kind: "code", content: "a = 1\nb = 2" } : ...`.
- Add `explainArtifact: async () => ({ ok: false, cached: false })` to the mock.
- Add the test:

```tsx
  it("opens a script in the plain-language view, and a click on it drops no comment pin", async () => {
    render(<RightRail sessionId="s1" active workspace="/ws" toolNames={[]} todo={[]} running={false} refreshKey={0} onFeedback={vi.fn()} />);
    const [row] = await screen.findAllByText("analysis_steps.py");
    row.closest("button")!.click();
    expect(await screen.findByRole("button", { name: "Explain this script" })).toBeTruthy();
    fireEvent.click(document.querySelector(".artifact-preview")!);
    expect(screen.queryByTestId("artifact-draft")).toBeNull();
  });
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/components/RightRail.artifacts.test.tsx`
Expected: the new test FAILS (no Explain button: the file renders as a plain `<pre>`)

- [ ] **Step 3: Implement**

- `import { CodeView } from "./CodeView";`
- In the `artifact-preview` `onClick`, add `|| content.kind === "code"` to the early return, with a comment: selecting lines ends in a click, and Ask Mimi replaces pins for scripts.
- Before the final `) : (` that renders `<pre className="artifact-code">`, insert:

```tsx
        ) : content.kind === "code" ? (
          <CodeView
            sessionId={sessionId}
            path={artifact.path}
            name={artifact.name}
            source={content.content || ""}
            onAsk={onFeedback ? (text) => onFeedback(text) : undefined}
          />
```

- [ ] **Step 4: Run the GUI unit tests**

Run: `npx vitest run src/components/RightRail.artifacts.test.tsx src/components/RightRail.builder.test.tsx src/components/CodeView.test.tsx`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add src/components/RightRail.tsx src/components/RightRail.artifacts.test.tsx
git commit -m "Open scripts in the plain-language view instead of raw text"
```

### Task 9: Translations

**Files:**
- Modify: `surfaces/gui/src/i18n.tsx` (`D`, order `[zh, no, fr, es, ja, ar, de, pt]`)

- [ ] **Step 1: Add the entries**

```ts
  "Plain language": ["通俗说明", "Enkelt språk", "Langage clair", "Lenguaje sencillo", "やさしい説明", "لغة بسيطة", "Einfache Sprache", "Linguagem simples"],
  "Code": ["代码", "Kode", "Code", "Código", "コード", "الشيفرة", "Code", "Código"],
  "Explain this script": ["解释这个脚本", "Forklar dette skriptet", "Expliquer ce script", "Explicar este script", "このスクリプトを説明", "اشرح هذا البرنامج النصي", "Dieses Skript erklären", "Explicar este script"],
  "Explaining…": ["正在解释…", "Forklarer…", "Explication…", "Explicando…", "説明中…", "جارٍ الشرح…", "Wird erklärt…", "Explicando…"],
  "Mimi can explain this script step by step in plain language.": ["Mimi 可以用通俗的语言逐步解释这个脚本。", "Mimi kan forklare dette skriptet steg for steg på enkelt språk.", "Mimi peut expliquer ce script étape par étape, en langage clair.", "Mimi puede explicar este script paso a paso en lenguaje sencillo.", "Mimiがこのスクリプトを一歩ずつやさしく説明します。", "يمكن لـ Mimi شرح هذا البرنامج النصي خطوة بخطوة بلغة بسيطة.", "Mimi kann dieses Skript Schritt für Schritt in einfacher Sprache erklären.", "A Mimi pode explicar este script passo a passo em linguagem simples."],
  "Couldn't write notes for this file. Try again.": ["无法为此文件生成说明，请重试。", "Kunne ikke lage notater for denne filen. Prøv igjen.", "Impossible de rédiger des notes pour ce fichier. Réessayez.", "No se pudieron escribir notas para este archivo. Inténtalo de nuevo.", "このファイルの説明を作成できませんでした。もう一度お試しください。", "تعذّر كتابة ملاحظات لهذا الملف. حاول مرة أخرى.", "Für diese Datei konnten keine Notizen erstellt werden. Versuche es erneut.", "Não foi possível escrever notas para este arquivo. Tente novamente."],
  "Choice to check": ["需要核对的选择", "Valg å sjekke", "Choix à vérifier", "Decisión a revisar", "確認すべき判断", "خيار يجب التحقق منه", "Zu prüfende Entscheidung", "Escolha a verificar"],
  "Show code": ["显示代码", "Vis kode", "Afficher le code", "Mostrar código", "コードを表示", "إظهار الشيفرة", "Code anzeigen", "Mostrar código"],
  "Hide code": ["隐藏代码", "Skjul kode", "Masquer le code", "Ocultar código", "コードを隠す", "إخفاء الشيفرة", "Code ausblenden", "Ocultar código"],
  "Lines": ["行", "Linjer", "Lignes", "Líneas", "行", "الأسطر", "Zeilen", "Linhas"],
  "Notes stop at line": ["说明止于第", "Notatene slutter ved linje", "Les notes s'arrêtent à la ligne", "Las notas terminan en la línea", "説明はこの行まで:", "تتوقف الملاحظات عند السطر", "Die Notizen enden bei Zeile", "As notas terminam na linha"],
  "The Code tab shows the whole script.": ["“代码”标签页显示完整脚本。", "Fanen Kode viser hele skriptet.", "L'onglet Code affiche tout le script.", "La pestaña Código muestra todo el script.", "「コード」タブにスクリプト全体が表示されます。", "يعرض تبويب الشيفرة البرنامج النصي كاملاً.", "Der Tab Code zeigt das ganze Skript.", "A aba Código mostra o script inteiro."],
  "Ask Mimi about lines": ["向 Mimi 询问这些行", "Spør Mimi om linjene", "Demander à Mimi à propos des lignes", "Preguntar a Mimi sobre las líneas", "この行についてMimiに質問", "اسأل Mimi عن الأسطر", "Mimi zu den Zeilen fragen", "Perguntar à Mimi sobre as linhas"],
  "What do these lines do to my data? Please explain in plain language.": ["这些代码对我的数据做了什么？请用通俗的语言解释。", "Hva gjør disse linjene med dataene mine? Forklar på enkelt språk.", "Que font ces lignes à mes données ? Expliquez en langage clair, s'il vous plaît.", "¿Qué hacen estas líneas con mis datos? Explícalo en lenguaje sencillo, por favor.", "この行は私のデータに何をしていますか？やさしい言葉で説明してください。", "ماذا تفعل هذه الأسطر ببياناتي؟ يرجى الشرح بلغة بسيطة.", "Was machen diese Zeilen mit meinen Daten? Bitte erkläre es in einfacher Sprache.", "O que estas linhas fazem com os meus dados? Explique em linguagem simples, por favor."],
```

If a key already exists in `D` (`"Code"` may), keep the existing entry and drop the duplicate.

- [ ] **Step 2: Run the i18n and GUI tests and type-check**

Run: `npx vitest run && npx tsc --noEmit && npx eslint .`
Expected: all pass, no type errors, no eslint errors

- [ ] **Step 3: Commit**

```bash
git add src/i18n.tsx
git commit -m "Translate the plain-language code view"
```

### Task 10: End-to-end screenshot

**Files:**
- Create: `surfaces/gui/e2e/code-view.spec.ts`

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from "./fixtures";

// The surface a non-coder uses to check an analysis (spec 2026-11-06): screenshot both
// tabs so the owner can judge the look, not just the behaviour.

const SOURCE = [
  "# MimiWork analysis log: every Python step Mimi ran in this conversation, in order.",
  "",
  "# Step 1 · 14:02",
  "df = pd.read_csv('survey.csv')",
  "",
  "# Step 2 · 14:03",
  "df = df[df['attention_check'] == 1]",
  "df['wtp'] = df['wtp'].clip(upper=df['wtp'].quantile(0.99))",
].join("\n");

const NOTES = {
  ok: true,
  path: "analysis_steps.py",
  steps: [
    { start: 1, end: 4, note: "Loads the survey answers from survey.csv.", choice: null },
    { start: 5, end: 8, note: "Keeps people who passed the attention check, then caps very high willingness-to-pay answers.", choice: "Capping at the 99th percentile is a choice to report in the method section." },
  ],
  lines_explained: 8,
  truncated: false,
};

test("a researcher explains the analysis script and reads it step by step", async ({ page }, testInfo) => {
  await page.route("**/v1/sessions/*/artifacts", (r) =>
    r.fulfill({ json: { artifacts: [{ path: "analysis_steps.py", name: "analysis_steps.py", kind: "code", size: 300, modified_at: 2 }] } }),
  );
  await page.route("**/v1/sessions/*/artifacts/read?*", (r) =>
    r.fulfill({ json: { ok: true, path: "analysis_steps.py", kind: "code", content: SOURCE } }),
  );
  await page.route("**/v1/sessions/*/artifacts/explain", async (r) => {
    const body = r.request().postDataJSON();
    await r.fulfill({ json: body.cached_only ? { ok: false, cached: false } : NOTES });
  });

  await page.goto("/");
  await page.locator(".app:not(.boot-splash)").waitFor();
  await page.getByTitle("Weekly plan 1").first().click();
  await page.getByText("analysis_steps.py").first().click();

  await page.getByRole("button", { name: "Explain this script" }).click();
  await expect(page.getByText("Choice to check")).toBeVisible();
  await page.getByRole("button", { name: /Show code/ }).nth(1).click();
  await page.screenshot({ path: testInfo.outputPath("code-view-plain.png") });

  await page.getByRole("tab", { name: "Code" }).click();
  await expect(page.locator("[data-line]")).toHaveCount(8);
  await page.screenshot({ path: testInfo.outputPath("code-view-code.png") });
});
```

- [ ] **Step 2: Run it**

Run: `npx playwright test e2e/code-view.spec.ts`
Expected: 1 passed. Then **open both screenshots and look at them.** Check the note sits above its code, the choice line reads as a callout, line numbers line up, and nothing overflows the rail. Fix the CSS and re-run until they look right.

- [ ] **Step 3: Commit**

```bash
git add e2e/code-view.spec.ts
git commit -m "Screenshot the plain-language code view in the e2e harness"
```

### Task 11: Full gates

- [ ] **Step 1: Backend**

Run (repo root): `.venv/bin/pytest -q && .venv/bin/ruff check .`
Expected: all pass, ruff clean

- [ ] **Step 2: GUI**

Run (`surfaces/gui/`): `npx vitest run && npx tsc --noEmit && npx eslint . && npx playwright test`
Expected: all pass

- [ ] **Step 3: Report**

Report the counts from each gate and attach the two screenshots. **Do not push, tag, build or release.** The owner decides when this ships.
