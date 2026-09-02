---
name: mimi-apps
description: >
  Build or change a small app the user runs inside MimiWork — a translator, a
  flashcard drill, a survey previewer, a rewriting tool, anything with a form and a
  result. Use whenever the user asks for "an app", "a tool", "a little interface",
  or asks to change an app they already have (Apps section → Improve).
---

# Mimi apps

An app is ONE self-contained `index.html` that MimiWork runs in a sandboxed frame.
You save it with the `create_app` tool, and replace it with `update_app` when the user
wants a change. Never write the file anywhere else.

## Rules the sandbox enforces

- No network. No `<script src>`, `<link href>`, web fonts, CDN libraries, images by URL.
  Inline every style and script; use system fonts; draw icons as inline SVG or emoji.
- Only the bridge reaches outside the frame:
  - `await Mimi.ask(prompt, { system?, json? })` → the model's reply as text
    (`json: true` parses it). This spends the user's credits like a chat turn, so ask
    once per user action, not on every keystroke.
  - `await Mimi.state.get()` / `await Mimi.state.set(object)` → one small JSON object
    that survives reopening (last inputs, preferences, a short history). Under 256 KB.
  - `Mimi.app` → `{ id, title }`.
- Keep the file under 100 KB. If a feature needs a library, it needs a different design.

## How to build one

1. Restate what the app does in one sentence — that becomes its description.
2. Write the page: a heading, the inputs, one primary button, a result area, and a
   "working…" state while `Mimi.ask` runs. Show errors in words, next to the button.
3. Plain language everywhere, no jargon, no emoji in the UI. MimiWork's look: white
   page, teal `#0d9488` for the primary button, `#1f2937` text, `#e5e7eb` borders,
   10px radii, system font.
4. Put the whole prompt for `Mimi.ask` in one template string; tell the model to reply
   with the result only.
5. Call `create_app(title, html, icon, description)` — an emoji icon, a short title.
   Then tell the user it is in the Apps section, in one line. Do not paste the HTML in
   the chat.

## Changing an app

The user's comment arrives as "Change the app <title> (id …): …" with the current
HTML. Make exactly that change, keep everything else as it was, and call `update_app`
with the complete new file. One line back to the user about what changed.
