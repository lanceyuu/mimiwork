# MimiWork vendor note

Vendored from https://github.com/nextlevelbuilder/ui-ux-pro-max-skill at commit
f3ac195224eac1eb0dfe1a3059c2a6add78ffbe3 (v2.13.0, MIT, Copyright (c) 2024 Next Level
Builder). Bundled: the `ui-ux-pro-max` skill folder — SKILL.md, `references/`, the
search scripts and their CSV/JSON data. Not bundled: the repo's other skills (design,
banner-design, ui-styling, brand, slides, design-system), the CLI installer, galleries,
screenshots and the scripts' own test suite.

Edits: every `${CLAUDE_PLUGIN_ROOT}/.claude/skills/ui-ux-pro-max/` path became
`${SKILL_DIR}/`, and one sentence tells the model that `load_skill`'s `resources_path`
is that directory — MimiWork has no plugin root. Everything else is upstream's verbatim.

Replaces `mono-color` as the bundled design skill (owner ask 2026-09-03); mono-color
moved to the skill store (`skills/store/mono-color` in this repo).
