# OpenClaude-inspired upgrades — design (approved 2026-08-20)

Owner picked all four ideas from the Gitlawb/openclaude survey and approved this
design ("Build it"): implement, test, ship as v0.3.0.

## 1. Workspace map (`coworker/workspace_map.py`)

A compact, ranked snapshot of the granted workspace injected into the agent's
context at session start, so the model begins knowing what's where instead of
exploring with `ls`.

- `build_workspace_map(root, budget_chars=3000) -> str`: walk the tree
  (respect `.gitignore`-style common ignores: node_modules, .git, __pycache__,
  .venv, dist, build, hidden dirs), collect dirs + files with mtime/size/ext.
- Rank files by recency (mtime) with a boost for document-y types the app's
  users care about (md, docx, xlsx, pdf, pptx, csv, py, ts …); render a
  skeleton: top-level dirs with counts, then the top-N files grouped by folder,
  most-recent first. Hard cap at `budget_chars`.
- Cache per root keyed by (root, max mtime of top-level entries) with a short
  TTL; building must stay <100ms on big trees via early pruning (cap walked
  entries).
- Injection point: where the cowork agent assembles instructions per session
  (same place workspace path is announced). Skipped when root is missing/empty.

## 2. Mission control

One live "Now" view of everything running.

- Backend: `manager.activity()` gains a `items` list: for each running session
  `{kind:"session", id, title, workspace, started_at, last_tool}`, each running
  automation `{kind:"automation", id, title}`, each pending approval
  `{kind:"approval", session_id, title, prompt}`. Broadcast unchanged (flips
  only); `GET /v1/activity` returns the detail.
- GUI: a compact panel (sidebar section above recents, only visible when
  something is live) listing items with elapsed time + jump-to; stop button per
  session (existing interrupt endpoint) and automation.

## 3. Session forking

- `ConversationStore.fork(session_id) -> new_id`: copy JSONL transcript + row
  (workspace, roots, grants, origin), fresh id, title `Fork of <title>`,
  message_count preserved.
- Manager `fork_session(sid)`: store-level fork + return record for GUI;
  forked session loads like any resumed one.
- `POST /v1/sessions/{id}/fork` → `{id}`; GUI session row menu gains
  "Duplicate as new thread", navigates to the fork.

## 4. Onboarding: "your first task" step

Extend the existing two-step wizard (provider → tools) with a third step:

- Folder pick via existing grant flow (native dir picker exposed through the
  existing AddFolderForm/open_workspace machinery — no new permission model).
- Three starter cards: Summarize this folder / Tidy & organize / Plan my week.
  Clicking one finishes onboarding and opens a session with the prompt
  prefilled (not auto-sent — the user presses Enter; consent stays theirs).
- QualiTaTi sign-in card added to the tools step (reuses QualitatiAccountCard
  machinery) so students connect credits during setup.
- Skippable; still replayable from Settings ▸ General.

## Testing & ship

Unit tests per feature (map builder ranking/caching; activity items; store
fork; GUI panel + onboarding step render tests). Full backend + GUI suites,
version bump to 0.3.0, tag, release via existing pipeline.
