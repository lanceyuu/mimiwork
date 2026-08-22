# Document revision, research digest, tool-loop reliability — design (approved 2026-08-22)

Owner approved ("Build it"): implement, test, ship as v0.3.3. Build order 3 → 1 → 2.

## 1. `revise_document` — Word tracked changes + plain-language review

- New docx tool `revise_document(path, edits[{index, text, reason?}])` in
  `coworker/tools/office/docx_tools.py`. Same block index space as
  `read_document`/`edit_document` (non-empty paragraphs + tables, document order).
- Each edit becomes a real Word revision on the paragraph: existing runs are wrapped
  in `<w:del>` (their `w:t` → `w:delText`), and a new run with the first run's
  `rPr` is appended inside `<w:ins>`. `w:author="Mimi"`, `w:date` = now (UTC ISO),
  unique `w:id`s across the document. python-docx XML layer only (no new deps).
- Result: `{path, applied, changes:[{index, before, after, reason}]}` — the
  plain-language review payload. `edit_document` stays (direct edits).
- `read_document(path, revisions=True)` lists pending revisions (author, before/after)
  so the model can reason about an already-marked-up file; default view unchanged.
- Cowork instructions: when a turn revised a document, end with "What I changed and
  why" — one line per change, plain language, no XML/indices.
- Approval preview: the Inbox card for `revise_document` shows up to 3 changes as
  before → after (same preview slot write_file uses).

## 2. "Weekly research digest" automation template

- `AutomationQuickstart.tsx` gains recipe `research`: title "Weekly research digest",
  blurb, cadence Weekly (mon 08:00), `deliver` choice (app/slack), new `needsTopics`
  text input (free text; required). Read-only → disclosure line, no consent grant.
- Instructions (from topics + deliver): search the web for the last 7 days on each
  topic; use `kb_search` for methodological context; write a Word digest with sections
  Top papers · News · Why it matters · Suggested reading; save as deliverable or
  send to Slack DM.
- Bundled blueprint `coworker/blueprints/weekly-research-digest.mimiflow.json`
  (`mimiwork_blueprint: 1`, no grants) exposed via `GET /v1/blueprints/builtin` and
  importable from the Automations view (same path as a file import) so students can
  install it in one click.

## 3. Tool-loop reliability (engine, deterministic, no LLM)

- Transient provider errors: classify with `providers/errors.py`; retry the model
  call up to 3 times with 1s/3s/8s backoff (honor Retry-After when present), yielding a
  `notice` event "Model busy — retrying (n/3)…". Non-transient errors unchanged.
- Deliverable self-check: after a successful file-producing tool (`write_document`,
  `write_presentation`, `write_spreadsheet`, `write_file` on .md/.txt/.csv/.html)
  run `coworker/deliverable_check.py:check(path)` → `{ok, issues[]}`: file exists and
  non-empty; parses with the matching reader; no placeholder tokens
  (`[insert`, `TODO`, `lorem ipsum`, `TBD`, `XXX`); documents have at least one
  heading or ≥2 paragraphs. Issues are appended to the tool result under
  `verification` so the model fixes them in the same turn. Never blocks.
- Graceful wrap-up: at `max_iterations - 1` inject a steering notice "You're almost
  out of steps — finish now: write what you have and summarize", so turns end with a
  deliverable instead of `max_iterations_exceeded`.

## Testing & ship

docx revision round-trip (python-docx reads back w:ins/w:del; Word-compatible ids),
review payload; deliverable_check unit tests (good file, empty, placeholder, unparsable);
engine retry (fake provider raising 429 then succeeding), wrap-up nudge at n-1;
GUI recipe render + blueprint import test. Full suites, bump 0.3.3, tag, release.
