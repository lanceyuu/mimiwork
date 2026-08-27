# coworker GUI (React + Tauri)

A thin client of the coworker server (OpenAI-compatible API + WS event/approval stream).
Same codebase runs in a browser (dev) and as the OpenWorker desktop app.

## First time: bootstrap the Python backend

A fresh checkout has no server to run — create the venv both flows below expect
(from the repo root):

```bash
bash packaging/setup_dev_env.sh   # → .venv (server + aisuite)
```

## Run it (browser, two terminals)

1. **Start the server** (needs a model key, e.g. `OPENAI_API_KEY`, in the environment —
   or add one later in the app's Settings), from the repo root:
   ```bash
   ./.venv/bin/openworker-server --cwd /path/to/your/project --port 8765
   ```
2. **Start the UI:**
   ```bash
   cd surfaces/gui
   npm install      # first time
   npm run dev      # → http://localhost:5173
   ```

Open http://localhost:5173. The UI talks to `http://127.0.0.1:8765` (override with
`VITE_COWORKER_HTTP` / `VITE_COWORKER_WS`). Start the server before Vite so the
UI can read its per-launch token from `<state-dir>/sidecar-8765.token`; restart
Vite if the server is restarted.

## Run the desktop app from source

The Tauri shell wraps the same UI and supervises the Python server itself — no separate
terminal. It needs the Rust toolchain (`rustup`) plus the venv from the bootstrap step;
in dev it finds the server at `.venv/bin/openworker-server` automatically (a
packaged sidecar binary is only produced by the release scripts in `packaging/`).

```bash
cd surfaces/gui
npm install        # first time
npm run tauri dev  # builds the shell, launches the window, starts the server
```

## Files surface

Account menu → **Files** browses the session's granted folders (the same roots the
@-picker and file tools see): one-level tree with breadcrumbs, multi-root switcher,
filter box, and a line-numbered viewer for text files. Read-only by design — edits go
through the agent's approval-gated tools; this pane is for the human to see what's
there. Backed by `GET /v1/workspace/tree` and `GET /v1/workspace/read` (containment =
`_mention_roots`, so nothing outside a granted root is ever listed or read).

### Manuscript workbench (in the Files pane)

Text files open into an editable mode with the workbench essentials, ported from
QualiTaTi Local's ManuscriptWorkbench:

- **Edit + Save** — `POST /v1/manuscript/save` writes the file and snapshots the
  previous content into `<dir>/.versions/` (max 20, no-op saves skipped).
- **Proofread** — `POST /v1/manuscript/proofread` sends the text through the
  configured provider (any key, or QualiTaTi credits) with the academic
  grammar/clarity/style prompt; notes render as a card and the revised text
  loads into the editor in one click.
- **Versions** — `GET /v1/manuscript/versions` + `POST /v1/manuscript/restore`;
  any snapshot loads back into the editor.

Same containment as the tree: `.versions/` lives beside the file, inside the
granted roots.

## Tests

```bash
npx tsc --noEmit && npx vitest run   # typecheck + unit
npx playwright test                  # hermetic e2e (mocked /v1 + WS, no Python needed)
```
