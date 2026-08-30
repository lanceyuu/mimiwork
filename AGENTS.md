# MimiWork — what this repo is, for whoever works on it next

MimiWork is a **desktop AI coworker for knowledge work**: a Tauri 2 shell (Rust) + React
GUI talking over loopback HTTP/WebSocket to a **Python sidecar** that runs the agent loop.
You ask for an outcome — "read these transcripts and write me a themed summary as a Word
doc" — and it hands back the finished file. It is a fork of
[OpenWorker](https://github.com/andrewyng/openworker), repositioned for Office deliverables,
PDF/image handling, and a statistics-aware analysis toolchain.

Two products share one brand: **MimiWork** (this app) and **QualiTaTi** (qualitati.com, the
research platform that sells credits and hosts the model gateway). Repo:
github.com/lanceyuu/mimiwork. Owner: Shubin Yu (`lanceyuu`).

## The shape of the thing

| Path | What lives there |
|---|---|
| `coworker/` | The Python backend: `engine.py` (the turn loop), `server/manager.py` + `server/app.py` (session manager and the REST/WS surface), `tools/` (files, office, analysis, web), `connectors/` (25+ integrations), `skills/` (store + `builtin/`), `personas/`, `qualitati.py` (account + gateway) |
| `surfaces/gui/src/` | React app. `App.tsx` is the shell; `api.ts` is the ONLY place that talks to the sidecar (module-local fetch wrapper adds the launch token); `components/` is everything else |
| `surfaces/gui/src-tauri/` | The Rust shell. **`tauri.conf.json` holds the single source of truth for the version** |
| `packaging/` | `build_dmg.sh` (macOS), `build_windows.ps1`, the PyInstaller spec |
| `tests/`, `surfaces/gui/src/**/*.test.tsx`, `surfaces/gui/e2e/` | Backend pytest, GUI vitest, Playwright e2e (hermetic, mocked backend) |

## Things that will bite you if you don't know them

- **`npm run tauri build` does NOT rebuild the Python sidecar.** It copies whatever is in
  `src-tauri/binaries/sidecar/`. Always ship via `bash packaging/build_dmg.sh`, which
  freezes the sidecar first. Three releases once went out with a month-old backend because
  of this. Before installing a local build, prove the new code is really in the binary —
  open the PyInstaller archive and look for the module you just added.
- **Nothing outside a granted folder is readable.** `roots.py` is the whole privacy model;
  `roots[0]` is the session's own folder and the default save location.
- **Consequential actions are approval-gated** through `risk.py` → the permission engine.
  A tool marked `requires_approval=True` classifies as EXTERNAL and stops for the user.
  Connector *reads* never gate; writes do. Don't quietly widen this.
- **The websocket validates every inbound frame** (`server/app.py`). A new attachment kind
  or message type must be added there too, or the feature dies at the door with a generic
  rejection — this has happened twice.
- **Version lives only in `tauri.conf.json`.** Bump it, tag `vX.Y.Z`, push the tag; CI
  (`release.yml`) builds all three platforms and drafts the release.

## House style

Tests are named as sentences about behaviour, not `test_function_name`. Comments explain
*why* a constraint exists, never what the next line does. Commit messages say what changed
and why it mattered, in prose. Every user-visible string is plain language — no jargon, no
emojis. The GUI frame is translated (`src/i18n.tsx`, en/zh/no/fr); deep prose falls back to
English by design.

## Ship discipline (the owner's standing rule)

**Never build, tag, push, or release without being asked.** Implement, run the full gates,
commit locally, report, and wait. The gates: `pytest` (backend), `vitest` + `tsc` + `eslint`
(GUI), `playwright test` (e2e), `ruff check` (Python), `cargo test` when Rust changed.
