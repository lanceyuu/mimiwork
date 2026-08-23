# Transfer pack — Cowork / Claude Code / Codex parity (approved 2026-08-23)

Owner ask: "make this app transferable — if you know how to use MimiWork, you should be
able to use Claude Code, Claude Cowork and Codex as well." Source of truth for the target
vocabulary: the Claude Academy course *Introduction to Claude Cowork* (delegation model,
Global instructions, folder instructions, skills, plugins, connectors, three permission
modes, sub-agents, plan-before-acting) plus Claude Code's CLI conventions.

Owner picked **Full transfer pack**. Two waves, shipped together.

## What already matches (no work)

Projects + memory, connectors, skills as `SKILL.md` folders, `explore` sub-agent, todo
panel, approval cards, `AGENTS.md` at global + project scope, markdown `/command` files
(backend only), auto-compaction.

## Wave 1 — interaction parity

1. **Unified `/` palette** (`Composer.tsx`). Today `/` lists skills only. It becomes one
   palette with three row kinds, each badged:
   - **App commands** named exactly as in Claude Code / Cowork, so the muscle memory
     transfers: `/help`, `/init`, `/clear`, `/compact`, `/model`, `/permissions`,
     `/memory`, `/skills`, `/plan`, `/usage`.
   - **Saved commands** — the markdown `.coworker/commands/*.md` + `<state>/commands/*.md`
     the backend already parses, finally reachable from the GUI. Picking one expands
     `$ARGUMENTS` server-side and sends the expanded instruction (deterministic — no extra
     model round-trip).
   - **Skills** — today's force-run rows, unchanged in behaviour.
2. **`@` file mentions.** Typing `@` opens a path picker over the session's granted roots
   (server-side search, ignore-list shared with `workspace_map`); picking inserts
   `@relative/path`. Same gesture as Claude Code, Cowork and Codex.
3. **Plan mode returns to the mode menu** (hidden 2026-07-22 because its approval flow was
   rough; the flow now has `PlanCard` + `propose_plan`), and **Shift+Tab cycles modes**
   exactly like Claude Code.
4. **Cross-tool labels.** Each mode row names its equivalent elsewhere — e.g.
   *Ask for approval · Cowork: Manual · Claude Code: default*. Teaching happens where the
   choice is made, not in a manual.
5. **Transfer guide** (`/help`, Settings ▸ Transfer guide): one page mapping every MimiWork
   concept to its Claude Code / Cowork / Codex name and keystroke.

## Wave 2 — portability

6. **`CLAUDE.md` read alongside `AGENTS.md`** (`project.py`), global and project scope, so
   an instructions file written for one tool works in the other. Precedence: both are
   loaded and labelled; `AGENTS.md` first.
7. **Global instructions editor** (Settings ▸ Instructions) over `<state>/AGENTS.md` —
   Cowork's "Global instructions", same words.
8. **`/init`** writes a starter `AGENTS.md` for the current folder from the workspace map.
9. **Import skills from Claude Code**: scan `~/.claude/skills`, `~/.claude/plugins/*/skills`
   and `<workspace>/.claude/skills` for `SKILL.md` folders; the Skills tab lists what it
   found (with its plugin name when it came from one) and copies chosen ones into the
   store. This is also how a Cowork/Claude Code **plugin's** skills land here.
10. **Manual `/compact`** — `POST /v1/sessions/{id}/compact` runs the existing compaction
    policy on demand (engine `_compact_now(force=True)`), persisting the new boundary.

## API surface

`GET /v1/commands?workspace=` · `POST /v1/commands/expand` ·
`GET|PUT /v1/instructions` (global) · `GET /v1/files/search?workspace=&q=` ·
`GET /v1/skills/importable?workspace=` · `POST /v1/skills/import` ·
`POST /v1/sessions/{id}/compact`.

## Testing & ship

Backend: command listing/expansion, CLAUDE.md ingestion, instructions round-trip, file
search scoping (never escapes granted roots), importable-skill discovery + copy, manual
compact. GUI: palette rows by kind + keyboard, `@` picker insertion, Shift+Tab cycle, plan
row present, transfer-guide render, instructions editor, import panel. Full suites, bump
version, tag, release.
