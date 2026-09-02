# MimiWork vendor note

Vendored from https://github.com/DietrichGebert/ponytail v4.9.0 (MIT, Copyright (c)
2026 DietrichGebert). Only the two skills Mimi can act on are bundled: `ponytail`
(this folder) and `ponytail-review` (its sibling). The plugin's other four skills —
audit, debt ledger, gain scoreboard, help card — and its per-editor hooks, MCP server
and statusline are Claude Code plumbing and are not bundled.

"Default" here needs no switch: MimiWork loads a skill when its description matches
the task, and ponytail's description claims every coding task. Ask for "ponytail lite"
or "ultra" in the conversation to change intensity; the `/ponytail` slash command in
the text is Claude Code's and does not exist in Mimi.

One edit: this note. SKILL.md is upstream's verbatim.
