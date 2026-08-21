# Projects, project memory, and navigation — design (approved 2026-08-21)

Owner asks: "a project system like Claude Code to organize different projects and a
memory system related to it"; "a return button on the top"; "the collapse button needs
to align with the three colorful buttons" (macOS traffic lights). Approved: full scope,
ship as v0.3.2.

## Projects

A project IS a real workspace folder. Per-conversation scratch dirs under `~/MimiWork/`
are never projects. Nothing is migrated: the project key is the workspace path that
sessions, memory and AGENTS.md were already bound to.

- Metadata on the `workspaces` row: `name`, `emoji`, `pinned`, `archived`
  (`ConversationStore.workspaces_with_meta / workspace_meta / set_workspace_meta`;
  `canonicalize_workspaces` carries the columns).
- Instructions = the folder's `AGENTS.md` — already injected into every new session as
  "Project conventions" (`coworker/project.py`). The page edits that file; empty text
  removes it. Writes are refused for folders the store doesn't know.
- Memory = the workspace scope (`Scope.WORKSPACE`, keyed by path) the `remember` tool
  already writes to. `GET /v1/memory?workspace=` filters; `POST /v1/memory` accepts
  `workspace`.
- REST: `GET /v1/projects`, `PATCH /v1/projects`, `GET /v1/projects/detail?path=`,
  `PUT /v1/projects/instructions`.
- GUI: sidebar **Projects** band for every persona (pinned first, archived hidden,
  `+` = existing folder picker); **Project page** (`ProjectView`) with emoji/name,
  path (opens in the file manager), New session here / Pin / Archive, Instructions,
  "What Mimi remembers about this project", Conversations; the topbar folder chip opens
  the Project page for known projects (scratch folders still reveal in Finder).

## Navigation

- Every non-session surface (Automations, Connectors, Activity, Inbox, Persona,
  Settings, Project) renders inside `.surface-frame` with one `← Back · <title>` strip.
- `App` keeps a surface history stack (push on every change not caused by Back, cap 20);
  Back pops, falling back to the session. PersonaView's own Back was removed — the
  frame's lands where the user actually came from (Settings → Persona → Back → Settings).
- The frame is a flex column; wrapped views get `min-height: 0` so their own panes keep
  scrolling (they were grid children of `.app` before).

## Title strip

Traffic lights sit at logical (19, 24), 12px, 20px pitch → centers y=30, x=25/45/65.
The collapse/pin control and the collapsed reveal button are 22px boxes centered at
(85, 30) — the next slot on that pitch (`.nav-pin-btn`, `.nav-reveal-btn`, overlay
padding 19/74).

## Fixed along the way

- Primary buttons get a disabled look (`opacity .45`).
- Slack person picker (fixed popover) clamps to the viewport (it could open below the
  fold and was unreachable — surfaced by the strip shifting content down 44px).
