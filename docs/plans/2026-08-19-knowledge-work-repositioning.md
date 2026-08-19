# Knowledge-Work Repositioning Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking. This repo is **not** a git checkout, so "commit" steps are written as **checkpoints** (run the suite, confirm green). If you `git init` first, treat each checkpoint as a commit.

**Goal:** Turn OpenWorker from a coding-shaped agent runtime into a knowledge-work runtime that produces real Office deliverables (Word / Excel / PowerPoint / Outlook) and runs real data analysis (Excel, SPSS, Stata, Python, R), while staying provider-agnostic.

**Architecture:** Three new capability families plugged into the existing closed capability catalog (`coworker/catalog.py`), plus a context-safety layer at the engine's tool-result seam, plus three knowledge-work personas that compose them. No new frameworks, no rewrite: the persona system already mirrors opencode's agent-markdown, and the `Executor` boundary already anticipates a second runtime. We add the missing capabilities behind the same `Capability` / `RiskClass` / `ToolSpec` contracts the platform already enforces.

**Tech Stack:** Python 3.10+, `python-docx`, `openpyxl`, `python-pptx`, `pandas`, `pyreadstat` (SPSS/Stata), `matplotlib` (chart capture), all as **optional extras**; aisuite tool schemas; pytest.

---

## Why these two references

| Borrowed from | Idea | How it lands here |
|---|---|---|
| deepseek-harness | `code-runtime` as an *optional capability seam* — model writes a program, host binds callables, `CodeRunResult {value, logs, error}` with typed failure kinds | `coworker/tools/analysis/kernel.py` — but **persistent**, because a dataframe must survive between calls (harness is deliberately per-call; analysis is the case where that's wrong) |
| deepseek-harness | **Spill** — over-budget tool output is replaced by a reference plus a preview | `coworker/spill.py`, applied at `engine._tool_result_message`, the single choke point where a tool result becomes model-visible |
| deepseek-harness | Tool-result pruning before summarization; typed failure kinds rather than a bare error string | `SpillStore` head/tail preview; `run_python` returns `kind` ∈ `exception|timeout|kernel-died|output-limit` |
| opencode | Per-agent **model binding** in the agent definition (not just a recommendation) | `model:` key in the persona manifest |
| opencode | **Permission block** per agent | `permissions:` key in the persona manifest, merged into the existing `PermissionEngine` |
| opencode | `small_model` for cheap side tasks | documented in Phase 6; not implemented in this pass |

The honest framing: OpenWorker's architecture is already *closer to* opencode than opencode's docs would suggest — personas are agent-markdown, skills are progressive-disclosure SKILL.md, MCP is wired, the catalog is a capability registry. What is missing is not architecture. **It is the actual knowledge-work capabilities.** The plan is weighted accordingly: Phases 1–3 are new capability, Phase 4 composes them, Phase 5 is the borrowed context-safety idea, Phase 6 is the borrowed provider flexibility.

---

## File Structure

```
coworker/tools/office/
  __init__.py        office_tools(context) → [tools];  _MISSING dependency probe
  paths.py           root-aware resolve_read / resolve_write (multi-root, write-gated)
  docx_tools.py      read_document, write_document, edit_document
  xlsx_tools.py      read_workbook, write_workbook, edit_workbook
  pptx_tools.py      read_presentation, write_presentation
coworker/tools/analysis/
  __init__.py        analysis_tools(context) → [tools]
  kernel.py          PythonKernel — persistent subprocess, JSON-line protocol
  _kernel_child.py   the child driver (exec loop, stdout capture, figure capture)
  python_tool.py     run_python, reset_python
  data_tools.py      inspect_data — CSV/XLSX/SAV/DTA/Parquet profiling + SPSS value labels
  r_tools.py         run_r — Rscript passthrough, script-file only
coworker/spill.py    SpillStore — over-budget tool output → file + preview
coworker/personas/builtin/
  analyst.md         data analysis persona
  documents.md       Word/PDF deliverable persona
  slides.md          PowerPoint persona
tests/
  test_office_paths.py, test_office_docx.py, test_office_xlsx.py, test_office_pptx.py
  test_analysis_kernel.py, test_analysis_data.py, test_analysis_r.py
  test_spill.py
```

Split by responsibility, not layer: each Office format is one file because they change independently (a python-pptx API change must not touch the Word reader). `paths.py` is shared because path safety must be identical across all three — one resolver, one place to audit.

---

## Chunk 1: Office documents

### Task 1: Root-aware path resolution shared by every Office tool

Office tools take a path from the model, so they are a workspace-escape surface. `coworker/tools/files.py:60` guards with `target.relative_to(root)`; the multi-root variant in `coworker/roots.py` adds writability. Office tools need both, so the rule lives in one file.

Semantics (must match `roots.render_context`, `coworker/roots.py:66`): relative paths resolve against `roots[0]`; absolute paths must sit inside some root; writes are only allowed in a `writable` root.

**Files:**
- Create: `coworker/tools/office/paths.py`
- Test: `tests/test_office_paths.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_relative_path_resolves_against_primary_root(tmp_path):
    primary = tmp_path / "scratch"; primary.mkdir()
    roots = [RootDir(path=primary, writable=True)]
    assert resolve_write("out.docx", roots) == primary / "out.docx"

def test_absolute_path_outside_every_root_is_rejected(tmp_path):
    roots = [RootDir(path=tmp_path / "scratch", writable=True)]
    with pytest.raises(PathError):
        resolve_read("/etc/passwd", roots)

def test_write_into_readonly_root_is_rejected(tmp_path):
    ...  # expects PathError mentioning "read-only"

def test_traversal_escape_is_rejected(tmp_path):
    with pytest.raises(PathError):
        resolve_read("../../etc/passwd", roots)
```

- [ ] **Step 2: Run to verify it fails** — `.venv-dev/bin/python -m pytest tests/test_office_paths.py -q` → `ModuleNotFoundError`.
- [ ] **Step 3: Implement `resolve_read` / `resolve_write` / `PathError`.** Both call a shared `_resolve(path, roots, need_write)`. Symlinks resolve *before* the containment check (`Path.resolve()`), so a symlink out of the workspace is caught.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Checkpoint** — full suite green.

### Task 2: Word — read / write / edit

`read_document` must give the model something it can *reason about and cite*, mirroring how `read_file` returns numbered lines: paragraphs are numbered so the model can say "paragraph 12" and then edit it. Tables come back as structured rows, not flattened text.

**Files:** Create `coworker/tools/office/docx_tools.py`; Test `tests/test_office_docx.py`

- [ ] **Step 1: Write failing tests** — round-trip (write then read returns the same headings/paragraphs), heading levels preserved, table read, `edit_document` replace-paragraph preserves the *rest* of the document, missing-dependency path returns an actionable `{"error": ...}` rather than raising.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.** `write_document(path, blocks)` where `blocks` is a list of `{"type": "heading"|"paragraph"|"bullet"|"table", ...}` — a small, explicit document IR beats free text because the model can't produce valid OOXML but can produce structured JSON reliably. `edit_document(path, edits)` applies `{"paragraph": n, "text": ...}` in place via python-docx so styles survive.
- [ ] **Step 4: Run → PASS.** **Step 5: Checkpoint.**

### Task 3: Excel — read / write / edit

Two failure modes to design against: (a) a 200k-row sheet floods context — so `read_workbook` windows rows exactly like `read_file` windows lines, and reports `total_rows` plus a continue hint; (b) the model silently destroys formulas — so `read_workbook` can return formulas, and `edit_workbook` writes cells without rewriting the sheet.

**Files:** Create `coworker/tools/office/xlsx_tools.py`; Test `tests/test_office_xlsx.py`

- [ ] Steps 1–5 as above. Tests must cover: sheet listing, row windowing with `total_rows`, formula preservation on edit, `write_workbook` from rows, number formats.

### Task 4: PowerPoint — read / write

**Files:** Create `coworker/tools/office/pptx_tools.py`; Test `tests/test_office_pptx.py`

- [ ] `write_presentation(path, slides)` with `{"layout": "title"|"bullets"|"section"|"blank", "title", "bullets", "notes", "image"}`. Speaker notes matter — a deck without notes is not a finished deliverable. `read_presentation` returns per-slide title/bullets/notes so the agent can revise an existing deck.

### Task 5: Wire Office into the catalog

**Files:** Modify `coworker/tools/office/__init__.py`, `coworker/catalog.py`, `pyproject.toml`

- [ ] Add capability ids `documents`, `spreadsheets`, `slides` with `requires=("workspace",)` and `risk=(READ, WRITE_LOCAL)`.
- [ ] Add `office = ["python-docx>=1.1", "openpyxl>=3.1", "python-pptx>=0.6.23"]` extra.
- [ ] Dependency probe: if the library is absent the tool is **still registered** and returns `{"error": "python-docx is not installed. Install with: pip install 'coworker[office]'"}`. Registering-but-erroring beats hiding the tool: the model otherwise invents a shell workaround.
- [ ] Extend `tests/test_catalog.py` for the three new ids.

---

## Chunk 2: Data analysis

### Task 6: Persistent Python kernel

The core design decision. deepseek-harness's `code-runtime` is deliberately per-call with "no cross-run state". For *data analysis* that is the wrong trade: reloading a 300 MB SPSS file on every call is the difference between a usable analyst and an unusable one. So: persistent namespace, with an explicit `reset_python` escape hatch and an honest "state was lost" message when the kernel dies.

**Files:** Create `coworker/tools/analysis/kernel.py`, `coworker/tools/analysis/_kernel_child.py`; Test `tests/test_analysis_kernel.py`

Protocol (mirrors `LocalExecutor`'s marker discipline in `coworker/tools/shell.py`): parent writes one JSON line per request, child replies with one JSON line. Child captures stdout/stderr, evaluates a trailing expression for its repr, saves any new matplotlib figures to the artifacts dir, and never lets an exception kill the loop.

- [ ] **Step 1: Failing tests** — state persists across calls; exception returns `kind="exception"` with a traceback and the kernel *survives*; timeout returns `kind="timeout"` and the kernel recovers; oversized stdout is capped with `kind`-tagged truncation; `reset` clears state; figures are captured to PNG.
- [ ] **Step 2: Run → FAIL.** **Step 3: Implement.** **Step 4: PASS.** **Step 5: Checkpoint.**

Timeout handling is the risky part: on timeout, SIGINT the child (raising `KeyboardInterrupt` inside `exec`) and wait briefly; if it does not answer, kill and restart, and say so in the result so the model knows its variables are gone.

### Task 7: `run_python` / `reset_python` tools

**Files:** Create `coworker/tools/analysis/python_tool.py`

- [ ] One kernel per session, lazily started, keyed to the primary root as cwd. `run_python` is `RiskClass.EXEC` — same gate as `run_shell`, because it is the same authority.

### Task 8: `inspect_data` — the survey-research payoff

**Files:** Create `coworker/tools/analysis/data_tools.py`; Test `tests/test_analysis_data.py`

Profiles CSV/TSV/XLSX/SAV/DTA/Parquet/JSON: shape, per-column dtype / non-null / unique / sample values, numeric describe. For SPSS `.sav` and Stata `.dta` it additionally returns **variable labels and value labels** via pyreadstat — the thing that makes `q4_1` interpretable as "Satisfaction with onboarding (1=Strongly disagree … 5=Strongly agree)". Without it the model is guessing at column meanings, which is exactly how analyses go quietly wrong.

- [ ] Tests: CSV profile, Excel sheet selection, SPSS value labels surfaced, unreadable file returns a clean error.

### Task 9: `run_r`

**Files:** Create `coworker/tools/analysis/r_tools.py`; Test `tests/test_analysis_r.py`

- [ ] Script-file only (never `-e` with inline code) — matches the codebase's existing "NEVER inline a multi-line script" instruction in `coworker/agents/cowork.py:29`, and keeps the approval prompt short and reviewable. Absent `Rscript` → actionable error. `RiskClass.EXEC`. Tests skip when R is not installed.

### Task 10: Wire analysis into the catalog

- [ ] Capability ids `python_analysis` (requires workspace, EXEC) and `data_inspect` (requires workspace, READ), `r_analysis` (EXEC). Extra: `analysis = ["pandas>=2", "pyreadstat>=1.2", "matplotlib>=3.7"]`.

---

## Chunk 3: Context safety, personas, provider flexibility

### Task 11: Spill — borrowed from deepseek-harness

**Files:** Create `coworker/spill.py`; Modify `coworker/engine.py`; Test `tests/test_spill.py`

`engine._tool_result_message` (`coworker/engine.py:1177`) is the one place a tool result becomes model-visible content. Over-budget content is written to `<spill-dir>/tool-<id>.txt` and replaced by head + tail + a pointer telling the model it can `read_file` the rest.

- [ ] Wire as an **optional post-construction attribute** (`engine.spill = SpillStore(...)`), matching how `compaction_state` is attached at `coworker/engine.py:112` — default `None` keeps all 1171 existing tests behaviourally identical.
- [ ] Tests: under-budget passes through byte-identical; over-budget writes a file and preserves head and tail; no spill store configured → unchanged.

### Task 12: Knowledge-work personas

**Files:** Create `coworker/personas/builtin/{analyst,documents,slides}.md`; Modify `tests/test_builtin_personas.py`

- [ ] Three manifests composing the new capabilities, each with a prompt written for *deliverables*, not chat. The analyst prompt must require stating the analysis plan before running it, and reporting *n*, test, effect size and assumption checks — a statistic without its assumptions is how an agent produces confidently wrong work.

### Task 13: Per-persona model binding (opencode's idea)

**Files:** Modify `coworker/personas/manifest.py`

- [ ] Add an optional `model:` key, validated as a non-empty string, exposed on `PersonaManifest`. Recommendation → binding.

### Task 14: Documentation

- [ ] `docs/config.example.toml` gains the new extras; `README.md` capability table reflects Office + analysis.

---

## Phase 6 — specified, not implemented in this pass

Deliberately deferred, with reasons:

1. **`small_model` task routing** (opencode) — titles and compaction summaries should run on a cheap model. Touches `providers/router.py` and every call site; needs its own plan.
2. **Custom commands** (opencode) — markdown `/command` files with `$ARGUMENTS`. High value for recurring office work ("/weekly-report"); needs GUI surface work, so it is a full-stack change, not a backend one.
3. **Plugin hooks** (both references) — `tools/pre-execute` / `post-execute` waterfalls. OpenWorker's engine applies permissions inline; introducing a hook pipeline is an engine refactor that should not ride along with capability work.
4. **Outlook/Excel live-object automation** — COM on Windows, AppleScript on macOS. Platform-specific, needs real-device testing.

---

## Execution note

Verification command for every step:

```bash
.venv-dev/bin/python -m pytest -q
```

Baseline before any change: **1171 passed, 1 skipped**. No step may reduce that number.

---

## Status — implemented 2026-08-19

Chunks 1–3 are built, wired, and tested. Final suite: **1328 passed, 2 skipped** (baseline 1171 → **+157 tests, zero regressions**).

| Task | State | Notes |
|---|---|---|
| 1 · Path resolution | Done | `coworker/tools/office/paths.py`, 13 tests incl. symlink escape |
| 2 · Word | Done | numbered blocks; `edit_document` writes into the first run so styles survive |
| 3 · Excel | Done | row windowing; `data_only=False` on edit is what preserves formulas |
| 4 · PowerPoint | Done | speaker notes are a first-class field; house `template:` supported |
| 5 · Office in catalog | Done | `documents`, `spreadsheets`, `slides` + `[office]` extra |
| 6 · Persistent kernel | Done | 17 tests: state persistence, exception survival, timeout recovery, chart capture |
| 7 · `run_python` | Done | EXEC risk, same gate as `run_shell`; `state_lost` reported on restart |
| 8 · `inspect_data` | Done | SPSS/Stata variable + value labels; low-cardinality numerics flagged as coded |
| 9 · `run_r` | Done | script-file only; tests skip cleanly when R is absent |
| 10 · Analysis in catalog | Done | `python_analysis`, `data_inspect`, `r_analysis` + `[analysis]` extra |
| 11 · Spill | Done | wired at `engine._tool_result_message`; `None` default keeps old behaviour |
| 12 · Personas | Done | `analyst`, `documents`, `slides` |
| 13 · Model binding | Done | `model:` manifest key + `PersonaRegistry.bound_model()` |
| 14 · Docs | Done | README, `config.example.toml`, `[knowledge]` umbrella extra |

Three things worth flagging for review:

1. **New personas ship disabled.** `registry.is_enabled` records an explicit owner decision (2026-07-09) that a fresh install is Coworker-only and everything else is opt-in from Settings ▸ Personas. The new personas follow that policy rather than overriding it — enabling them by default is a product call, not an implementation one.
2. **The kernel is persistent, against the harness reference.** deepseek-harness's code-runtime is deliberately per-call. For analysis that trade is wrong (reloading a large `.sav` per call), so this one keeps state — and pays for it with an explicit `state_lost` flag whenever the kernel restarts, so the model can never report results from variables that no longer exist.
3. **`run_python` is EXEC risk.** Deliberate: executing model-written Python is the same authority as a shell command, and a softer classification would be a route around the shell's approval prompt.

The dev environment used for verification is `.venv-dev` (Python 3.11 — the system Python here is 3.9, below the project floor). It is gitignored.

---

## Phase 2 — capability, packaging, and layout (same day)

### New capabilities

| Capability | Tools | Why |
|---|---|---|
| `pdf` | `read_pdf` | Reports, papers, statements and board packs arrive as PDF. Windowed by page, optional table extraction, and — critically — an explicit **scanned-document warning**: a page with no text layer extracts as `""`, which is indistinguishable from a blank page, so a silent result is how a model ends up summarising a document it never read. |
| `images` | `read_image_info`, `edit_image`, `annotate_image`, `combine_images` | Charts, screenshots and figures are the last mile of a visual deliverable. Edits **never** overwrite the source by default, and every operation reports resulting dimensions and byte size because the reason for the edit is usually a constraint the model otherwise cannot verify it met. |

### Packaging — two real bugs found by building the app, not by reading it

1. **`matplotlib` and `PIL` were in the PyInstaller `excludes` list.** Every image tool and every analysis chart would have failed at runtime in the installed app, with no way for a user to `pip install` a fix into a bundled binary.
2. **No persona markdown was bundled at all** — pre-existing, and not caused by this work. `collect_submodules` walks importable modules only, so `coworker/personas/builtin/*.md` never entered the bundle: the shipped desktop app had **no `ops` persona**, and every id in that folder resolved as "unknown persona". Fixed with `collect_data_files("coworker", includes=["**/*.md"])`.

Both were caught by freezing the sidecar and querying the running binary over its own API — the second one only surfaced because enabling a persona in the frozen app returned `unknown persona: analyst`.

Verified in the built `OpenWorker.app`: all four persona manifests present, and `docx`/`pptx`/`PIL`/`pandas`/`scipy`/`pyreadstat`/`matplotlib` all staged with their runtime data (docx templates, `pptx/templates/default.pptx`, matplotlib `mpl-data`, pyreadstat's compiled ReadStat `.so`).

Build prerequisites not in the README, both needed on a clean Mac: **cmake** (the `whisper-rs` voice-input crate fails its build script without it) and **rustfmt**.

### Desktop layout

Measured in the running app rather than guessed:

| | Before | After |
|---|---|---|
| Intro column vs composer left edge | misaligned by **64px** | aligned exactly (delta 0) |
| Intro content width @1440px | 640px | 768px, matching transcript and composer |
| Dead space around the empty state | 289px below / 24px above | 175 / 174 (centred) |
| Chrome @1024px | 596px (**58%** of the window) | 524px (51%), content column +19% |

Three causes, all fixed: the intro used a different max-width (640 vs 768) *and* a different gutter from every other column; `.main-scroll` used percentage padding (`8%`) so the reading width changed whenever the right rail toggled; and the 264/332 panel widths were literals repeated in six places, so they could never flex. They are now `--nav-w` / `--rail-w`, which is what makes the narrow-window rules possible.

### Bonus fix — the GUI test suite was broken on current Node

7 of 111 tests failed on this machine before any of my changes. **Node 25 ships a native global `localStorage`** that is inert without `--localstorage-file`; its presence stops jsdom installing a real Storage, so every component reading a preference threw during render. `surfaces/gui/vitest.setup.ts` installs a spec-shaped Storage when it finds the stub, and is a no-op on Node 20–24. GUI suite: **111/111 passing**.

Backend suite after all Phase 2 work: **1372 passed, 2 skipped**.

### Still not built

The statistical-testing tool (`run_test` — automatic assumption checks, effect sizes, and confidence intervals, enforcing what the analyst persona's prompt asks for) remains the highest-value next addition. `scipy` is already declared and bundled for it.

---

## Phase 3 — Mimi visual identity + QualiTaTi account (same day)

### Visual identity

Sourced from `QualiTaTi v5/design-assets/qualitati_vi_icons` (Global-site teal `#0D9488`, 1024×1024 RGBA): app icon set regenerated via `tauri icon` from the square-filled Mimi; tray icon re-rendered as a 44×44 black+alpha template from the line-art Mimi (macOS tints templates itself); favicon; Mimi marks in the sidebar brand row, intro greeting, provider tile, and account card. Curated copies live in `surfaces/gui/src/assets/mimi/`.

### QualiTaTi credits — two halves

**QualiTaTi repo, branch `mimiwork-gateway` (NOT deployed):** an OpenAI-compatible, credit-metered gateway at `/api/llm/v1/chat/completions` + `/models`. Model choice is pinned to the new admin-configurable `mimiwork.gateway` slot (no arbitrary-model passthrough); billing = measured tokens × Annotator roster rates × markup, ledgered per completion (`source=mimiwork_gateway`, dedup by completion id); unpriced or non-openai-SDK slot configs refuse with 503; streaming forces `include_usage`, with a chars→tokens estimate if a stream dies early. Auth: JWT, X-API-Key, or API-key-in-Bearer (OpenAI SDKs can only send Bearer). 21 tests. Deploy by merging the branch through the normal pipeline; nothing in production changed.

**MimiWork:** `qualitati` provider (gateway base URL, `QUALITATI_API_KEY` env) + curated `qualitati:mimi` model; `coworker/qualitati.py` account client (login → MFA → mint personal API key via `/api/keys` → auto-configure provider; passwords never stored; sign-out revokes the key); routes `/v1/qualitati/*`; Settings → Models account card with live credit balance. 13 backend + 5 GUI tests.

Found during integration: QualiTaTi's API.md documented `/api/keys` as returning `api_key` — the real field is `key`. Fixed in the branch.

### Suites after Phase 3
Backend 1385 passed / 2 skipped · GUI 116 passed · QualiTaTi gateway 21 passed.
