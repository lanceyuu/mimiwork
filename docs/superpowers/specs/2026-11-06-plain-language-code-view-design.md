# Plain-language code view — design

Date: 2026-11-06 · Owner: Shubin Yu · Status: approved design, not built

## Why

Researchers ask MimiWork to analyse data, and many cannot read the Python or R it writes.
They have no way to check what was done to their data before they put the result in a
paper. Two gaps make this worse today:

- `run_python` code lives only in the tool-call arguments. The transcript shows a shortened
  one-line version (`Transcript.tsx`, `shortArgs`). There is no script to read, re-run or
  attach to a submission.
- Scripts that do reach disk open in the right rail as an unformatted `<pre>`, and `.R`,
  `.do` and `.sql` are not even classed as code (`RightRail.tsx` `kindFromPath`,
  `manager.py` artifact kind mapping) — they fall through to "text".

The audience for the first version is **a non-coder checking the work**, so the default
view is plain-language notes, with the code one click away.

## What the researcher sees

Opening a code artifact (`.py`, `.R`, `.do`, `.sql`) in the right rail shows two tabs:

**Plain language** (default)

- The script is split into steps. Each step shows a one- or two-sentence note in research
  language ("Keeps only respondents who passed the attention check.") with that step's
  code folded under **Show code**.
- A step may carry a **Choice to check** line: a decision a reviewer would ask about —
  how missing values are handled, a one-sided test, a hand-picked cut-off, an outlier rule,
  a filter that removes cases. Plain label, no icons or emoji (house style).
- Notes are written in the app's language preference, read on the sidecar from
  `self._prefs["language"]` (any value `set_language` accepts: en, zh, no, fr, es, ja,
  ar, de, pt). The model writes the notes, so every accepted language works; only the
  panel's own labels fall back to English outside en/zh/no/fr, as the rest of the GUI
  does.
- Before notes exist, the tab shows **Explain this script** (one click, one model call). It
  does not run on its own, so opening a file never spends credits silently. Once notes
  exist for this version of the file they show straight away.

**Code**

- The full script, monospaced, with line numbers. No colour highlighting in v1.

**Ask Mimi** — selecting text in either tab shows an **Ask Mimi** button. It sends a
message to the conversation quoting the selected lines (with line numbers and file name)
through the existing `onFeedback` path. Mimi answers in the chat, where the researcher can
follow up.

Ask Mimi **replaces** click-to-pin for code previews. Today any click on a code preview
opens a pin draft (`RightRail.tsx`, the `artifact-preview` `onClick`; only html, office
and folder are excluded), and finishing a text selection is a click. `code` joins the
excluded kinds, so selecting never opens a pin draft.

## Where scripts come from

- **Python.** Every `run_python` call is appended to `analysis_steps.py` in the session
  workspace (`context.workspace`, which is `roots[0]`).
  - Each block, failed ones included, gets a header comment `# Step N · HH:MM`. N is one
    more than the number of step headers already in the file, so N counts calls and
    survives engine restarts.
  - A call that succeeded is written as live code. A call that failed or timed out is
    written **commented out**, under a line saying it failed and may have changed the data
    before stopping. A failed call can still mutate the kernel (change `df`, then raise),
    so leaving it out would make the log replay something different from what ran.
  - When the kernel restarts (`reset_python`, or a result with `state_lost`), append a
    comment saying the Python session restarted and the steps below start from an empty
    session.
  - The file's first line is a marker comment written by the tool. The tool writes to the
    first of `analysis_steps.py`, `analysis_steps-2.py`, `analysis_steps-3.py`, … that
    either does not exist or starts with the marker. It never appends to a file it did not
    start; that would corrupt someone else's file.
  - A write failure (read-only folder, disk full) is swallowed: the analysis result is
    returned as normal. The log is a convenience and must never fail an analysis.
  - `run_python` returns `"files": ["<log path>"]` in its result. Without that, the log
    never reaches the artifacts list: in a granted folder only paths named in tool
    arguments or results are listed (`manager.py` `_touched_paths`, harvested keys
    `_ARTIFACT_PATH_LISTS`). The model also sees the path and can point the researcher
    to it.
  - The `run_python` schema description says each block is saved to
    `analysis_steps.py`. This is a new write into the researcher's own folder, and it
    should not be a silent one.
- **R.** Already a file on disk (`run_r` runs scripts by path); nothing to add to how it
  is written.

## Which scripts count as deliverables

Since 2026-09-02 the artifacts list hides scripts as "machinery" whenever anything else was
produced (`_MACHINERY_SUFFIXES` + `_meaningful` in `manager.py`, owner's ask). That rule
stays for scripts that were only *written*. A script that **was the analysis** is a
deliverable:

- the step log `run_python` names in its result, and
- any script passed to `run_r`.

How:

- Add `"script"` to `_ARTIFACT_PATH_KEYS`. Today `run_r`'s `script` argument and result
  key are never harvested, so an R script the researcher brought in a granted folder never
  becomes a row at all.
- `_touched_paths` also returns the subset of paths harvested from `run_python` and
  `run_r` calls (the "ran" set). Both callers of `_meaningful` pass it; where there is no
  transcript record, the set is empty.
- `_meaningful` keeps a row whose `abs_path` is in the ran set, compared with the same
  realpath key the listing already uses, even when its suffix is machinery.
- The exemption is by path, never by the `analysis_steps*.py` name. A file of that name
  that the tool refused to touch (no marker) stays machinery.

File types touch three separate sets in `manager.py`, and each needs its own change:

| Set | What it decides | Change |
|---|---|---|
| `_artifact_kind` | which viewer opens the file | `.r`, `.do`, `.sql` → `code` |
| the scratch-folder walk `suffixes` | which files a scratch folder lists at all | add `.r`, `.do`, `.sql` |
| `_MACHINERY_SUFFIXES` | which files are hidden as machinery | add `.do` (so Stata matches R and SQL); the exemption above covers the scripts that matter |

On the GUI side, `RightRail.tsx` `kindFromPath` gets the same `.r`, `.do`, `.sql` → `code`.

## How notes are made

New route `POST /v1/sessions/{session_id}/artifacts/explain` with body `{path}`.

1. Resolve `path` through the session roots for **reading** (same rule as
   `artifacts/read`; nothing outside a granted folder).
2. Hash the file content (sha256). If a cached result exists for that hash and language,
   return it.
3. Otherwise make **one** non-streaming completion on the session's own provider and model,
   the same pattern as `_generate_autotitle` (`manager.py`). Get the engine with
   `get_engine(session_id)`, which builds one when the session has none in memory (after
   an app restart). Call `engine.provider.complete` inside `asyncio.to_thread`, because it
   blocks. Use low temperature, `reasoning_effort="none"`, generous `max_tokens`. The GUI
   disables the button while a request is pending, so one click is one charge. The prompt carries the
   code with line numbers and asks for JSON:
   `{"steps": [{"start": int, "end": int, "note": str, "choice": str | null}]}`.
4. Validate: ranges inside the file, `start <= end`, ascending, non-overlapping; drop any
   step that fails rather than the whole reply. Lines not covered by any step are shown as
   their own step with no note, so no code is ever hidden from the researcher.
5. Cache the validated result under `state_dir() / "explain" / "<sha256>-<lang>.json"` —
   the app's data folder, not the researcher's folder.

**Notes never state numbers.** The prompt forbids counts, percentages and results in
notes ("drops people who failed the check", never "drops 23 people"). The model has not
seen the data at this point; a non-coder would trust an invented count. Tying notes to
real output is the follow-up below.

**Long files.** Send at most the first 1,500 lines. The panel says that notes stop at line
1,500; the Code tab still shows everything.

**Credits.** One call per file version per language, only on the researcher's click.

## When it goes wrong

| Case | Behaviour |
|---|---|
| Model call fails, or reply is not valid JSON | Response `{"error": ...}`; the panel stays on Plain language with "Couldn't write notes for this file. Try again." and a retry button. Code tab unaffected. Nothing cached. |
| Every step fails validation | Same as above. |
| `get_engine` returns `None` (session has no workspace) | Same `{"error": ...}` shape and panel message. |
| File changed since notes were made | New hash, so the old notes are not shown; the panel offers **Explain this script** again. |
| Path outside granted folders | Same refusal as `artifacts/read`. |

## Out of scope for v1

- **Colour highlighting** — needs a new dependency and matters mostly to coders.
- **Tracing a number in the report back to the line that produced it** — the strongest
  follow-up, but a project of its own (needs output capture per step).
- **"Write the methods paragraph"** — already possible as a chat request.
- **Inline answers to Ask Mimi inside the panel** — answers go to the chat in v1.

## Touch points

- `coworker/tools/analysis/python_tool.py` — step log in `run_python` / `reset_python`.
- `coworker/server/manager.py` — the three suffix sets; the deliverable-script exemption
  in `_meaningful`; `explain_artifact(session_id, path)`.
- `coworker/server/app.py` — the route.
- `surfaces/gui/src/api.ts` — `explainArtifact(sessionId, path)`.
- `surfaces/gui/src/components/RightRail.tsx` — code viewer: tabs, steps, Show code,
  line numbers, selection → Ask Mimi. If the viewer grows past a small block, it moves to
  its own `CodeView.tsx` beside `RightRail.tsx`.
- `surfaces/gui/src/i18n.tsx` — new strings in en/zh/no/fr.

## Tests

Backend (pytest):

- a successful run_python call is appended to the step log with a step header
- a failed run_python call is written commented out with a note that it failed
- step numbers continue from the headers already in the file
- a kernel restart writes a restart note into the step log
- the step log never appends to an analysis_steps.py it did not create
- a step log that cannot be written does not fail the analysis
- run_python names the step log in its result so it reaches the artifacts list
- the step log and scripts run with run_r stay listed when other files exist
- an R script from a granted folder is listed once run_r has run it
- an analysis_steps.py the tool did not create stays hidden as machinery
- a script that was only written is still hidden when other files exist
- explain returns cached notes for an unchanged file without calling the model
- explain drops steps whose line ranges fall outside the file
- explain covers lines no step mentions with an empty step
- a model reply that is not JSON returns an error and caches nothing
- R, Stata and SQL files are listed as code

GUI (vitest): notes render above their steps; Show code expands the right lines; the Code
tab shows line numbers; Ask Mimi sends the selected lines with the file name; a click on a
code preview opens no pin draft; the Explain button is disabled while pending; the error
state shows the retry button.

e2e (Playwright): open a mocked `analysis_steps.py`, click Explain, screenshot both tabs.
