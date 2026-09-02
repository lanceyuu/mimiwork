# Apps — Mimi builds small interactive tools you use inside MimiWork (draft 2026-09-03)

Owner asks (2026-09-02): "an application section, where you can create an app like the
automation, with an interface, for example a translator, a little bit like Poe canvas
apps"; "we should have it in the sidebar like automation". Hosting on qualitati.com was
discussed and deferred (see *Not in this version*).

## What an app is

An app is one HTML file that runs inside MimiWork and can ask the model questions. That
is the whole abstraction, and it is the same one Poe uses: a page in an iframe plus one
JavaScript call that reaches a model. A translator is a text box, a language picker, and
one `Mimi.ask` call. Everything Mimi already knows about writing HTML applies unchanged.

On disk, under the state dir (next to `automations.db`):

```
apps/<id>/
  app.json     title, icon (one emoji), description, model (null = app default),
               builder_session (the chat that wrote it), created_at, updated_at
  index.html   the app, single file, no external resources
  state.json   whatever the app chose to remember (optional)
```

An app is not a workspace and has no folder grants. It never reads the user's files.

## The bridge — `window.Mimi`

The host page injects one script at the top of `index.html` before it goes into the
iframe. The app sees:

```js
Mimi.ask(prompt, { system?, json? })  // → Promise<string>; json:true parses the reply
Mimi.state.get()                      // → Promise<object>   (state.json)
Mimi.state.set(object)                // → Promise<void>
Mimi.app                              // { id, title }
```

Transport is `postMessage` with request ids; the host answers each message. `ask` goes to
`POST /v1/apps/{id}/ask` → `manager.provider_complete(app.model or manager.model, …)`,
the same path as `/v1/chat/completions`. It spends credits exactly like a chat turn and
shows in the usage chip. Non-streaming in this version: a translation of a paragraph
returns in a few seconds and the page can show its own "working…" state. Streaming is the
first follow-up if apps feel slow; the bridge signature does not change (`onText` option).

### Sandbox — the part that is not optional

The artifact viewer's iframe has `allow-same-origin`, which is fine for a document you
wrote yourself. An app is code that runs on your behalf, so it gets less:

- `sandbox="allow-scripts"` only. No same-origin: the app cannot read the launch token,
  cannot call the sidecar directly, cannot touch the GUI's storage.
- An injected `<meta http-equiv="Content-Security-Policy">`: `default-src 'none';
  script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src
  data:; connect-src 'none'`. The app has no network. The only way out is the bridge.
- The host validates every bridge message (kind, id, size cap on prompts and state) the
  way `server/app.py` validates websocket frames.

This is also what makes hosting possible later: the same file runs unchanged wherever a
host page supplies the bridge.

## Creating and improving an app

- **New app** (sidebar `+`, or the empty state) opens a chat in a scratch workspace with
  the bundled `mimi-apps` skill force-run: `/mimi-apps <what the user typed>`. The skill
  says: one `index.html`, no CDNs or external fonts, use `Mimi.ask` for anything that
  needs a model, plain language in the UI, the MimiWork palette, then call the tool.
- Two agent tools, registered like `automation/tools.py`: `create_app(title, icon,
  description, html)` and `update_app(id, html, title?, icon?)`. They write only under
  `apps/`, so they do not gate. The GUI hears `APPS_CHANGED` (mirror of
  `AUTOMATIONS_CHANGED`) and the band refreshes.
- **Improve**: the app page has the same comment box the flow diagram got on 2026-09-02.
  A comment ("add a copy button", "the result box is too small") is sent to the app's
  builder session as `Change the app <title>: …`; Mimi rewrites the file with
  `update_app`; the iframe reloads. If the builder session is gone, a new one is opened
  with the current HTML attached.
- **Starters** bundled like blueprints: *Translator* (text → language, keeps the last
  five), *Rewrite in my voice* (paste → tone picker → result). Two is enough to show the
  shape; more is a catalogue nobody asked for.
- **Export / Import**: one `.mimiapp.html` file (the manifest as a JSON block in a
  `<script type="application/json" id="mimi-app">` tag, the app below). That is the
  sharing story for this version: send the file, the other person imports it.

## GUI

- Sidebar: an **APPS** band under SCHEDULED, `+` = New app. Rows show icon and title.
- `AppsView` inside `.surface-frame` like `ScheduledView`: overview grid (icon, title,
  description, last used) and a detail page: the app full-width in its iframe, a header
  with icon and title (click to rename), **Improve**, **Export**, **Delete** (ConfirmDialog),
  and a settings row: model picker (same `RunSettings` control as automations, minus
  mode — an app has no permissions to set) and "asked the model N times today".
- App surface id `"apps"` with `appsOpenId`, like `scheduled` / `scheduledOpenId`.
- The bridge and the sandboxed iframe live in one component, `AppFrame`, so the artifact
  viewer can reuse it later if HTML artifacts should also get `Mimi.ask`.

## REST

```
GET    /v1/apps                    list of manifests
POST   /v1/apps                    import (manifest + html) → {ok, app}
GET    /v1/apps/{id}               manifest + html
PATCH  /v1/apps/{id}               title, icon, description, model
DELETE /v1/apps/{id}
POST   /v1/apps/{id}/ask           {prompt, system?} → {text}   (bridge)
GET    /v1/apps/{id}/state         state.json or {}
PUT    /v1/apps/{id}/state         ≤ 256 KB
POST   /v1/apps/{id}/improve       {comment} → {session_id, prompt}  (opens the builder chat)
GET    /v1/apps/builtin            starters
```

`AppStore` in `coworker/apps/store.py`: manifests on disk, no database — a dozen apps do
not need one. Ids are `app-<8 hex>`; the folder name is the id.

## Not in this version

- **Hosting on qualitati.com.** Feasible, and the sandbox above is designed for it, but it
  needs decisions that are not code: viewers sign in and spend their own credits (never
  the creator's key in the page), a separate origin such as apps.qualitati.com so an app
  can never read a qualitati.com session, unlisted links only, a takedown switch. Ship the
  local section, use it for a few weeks, then design publishing with those rules.
- Multi-file apps, file or folder access, connectors from inside an app, streaming
  replies, app-to-app links. Each is a follow-up with its own owner ask.

## Tests

- Backend: store round-trip; `ask` uses the app's model and falls back to the default;
  `ask` and `state` refuse unknown ids and oversized bodies; import rejects HTML with
  external resources (`src=`/`href=` to http(s)) with a plain message; the two tools
  write only under `apps/`.
- GUI: `AppFrame` answers `ask` and `state` messages and drops malformed ones; the
  iframe has no `allow-same-origin`; comment → improve → reload; sidebar band lists apps
  and `+` opens the builder chat.
- e2e (mocked backend): create from the starter, open, ask, rename, delete.

## Estimate

Bridge + store + REST + tools: one day. Sidebar band, overview, detail page, comment
loop: one day. Skill, two starters, export/import, tests and polish: one day.
