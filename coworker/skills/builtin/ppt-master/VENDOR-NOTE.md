# MimiWork vendor note

Vendored from https://github.com/hugohe3/ppt-master (MIT, Copyright (c) 2025-2026
Hugo He) — the `skills/ppt-master` directory at v6.1.0, trimmed to keep the app
small. Not bundled:

- `references/ai-image-comparison/` (43MB of AI-image-model comparison galleries —
  advisory only)
- `templates/sounds/bigsoundbank/` (10MB of ambience/effect cues; the 2.4MB
  `kenney-ui` click/rollover set ships, sound defaults to off, and `sound_sync.py`
  reports a missing library clearly if a bigsoundbank cue is ever selected)
- `templates/icons/tabler-outline/`, `templates/icons/simple-icons/` (36MB; see the
  note in `templates/icons/README.md`)

Everything removed can be restored by copying the same-named folder from the
official repository. No bundled file was modified except `templates/icons/README.md`
(the library table now lists what ships) and SKILL.md's frontmatter description
(flattened from a YAML folded scalar to one line — MimiWork's frontmatter reader
takes single-line values).
