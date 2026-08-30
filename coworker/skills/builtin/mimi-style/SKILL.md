---
name: mimi-style
description: The QualiTaTi / MimiWork brand system — teal palette, typography, the puppy mascot, 85 named icon assets, and per-medium style guides. Use this skill whenever creating ANYTHING that represents QualiTaTi or MimiWork visually — slides, PDF documents, web pages, social posts, ads, banners, tutorial pages, screenshots with captions, release announcements, App Store copy — even when the user doesn't say "brand" or "style". If the output will be seen by a user or customer of QualiTaTi or MimiWork, it should come through this skill.
---

# The Mimi brand

One system, two products: **QualiTaTi** (the research platform) and **MimiWork** (the
desktop AI coworker). Same teal, same mascot, same voice. The look is warm-professional:
a friendly puppy wearing a lab coat — approachable enough for a first-year student,
credible enough for a methods professor.

## The one rule that outranks everything

**Teal is the global brand. The red icon set is the China site only.** Never mix red
variants into global material, and never teal into China-site material. If you are not
told which site, it is the global one: teal.

## Core tokens

| Token | Value | Use |
|---|---|---|
| Teal (primary) | `#0D9488` | Accents, buttons, links, icon containers, headings on light |
| Teal dark | `#0B7C72` | Hover states, borders on teal, small text on tint |
| Teal mid | `#8ED6CC` | Secondary accents, chart series 2, decorative lines |
| Tint | `#E9F6F4` | Card backgrounds, callout fills, section bands |
| Tint deep | `#D9EFEC` | Table header fills, hover on tint |
| Ink | `#111111` | Body text, headings |
| Muted | `#555555` | Captions, secondary text |
| Line | `#E6E6E6` | Hairlines, card borders |
| Paper | `#FAFAFA` | Page background (never pure white edge-to-edge) |

Type: **"Avenir Next", "Nunito", "Helvetica Neue", Arial, sans-serif** — everywhere, both
products, all media. Headings semibold/bold, body regular. No serifs, no monospace outside
code samples. Copy-paste blocks live in `references/brand-core.md`.

Voice: plain sentences, outcomes over features, no hype adjectives, no emojis in
customer-facing material. "Ask for the outcome, get the file" — that register.

## The assets (all in `assets/`, semantically named)

Eleven glyph motifs, each in five container styles, plus the mascot:

| Motif | Means | Use for |
|---|---|---|
| `interview` | puppy with headphones + ? | AI interviews, asking, Q&A |
| `listening` | ear with sound waves | Listening, transcripts, audio |
| `research` | paw in magnifier | Research, analysis, findings |
| `academy` | graduate puppy | Teaching, tutorials, academy |
| `survey` | puppy reading checklist | Surveys, questionnaires |
| `report` | document with check | Reports, deliverables, exports |
| `voice` | microphone + puppy | Voice input, dictation |
| `network` | connected nodes | Distribution, sharing, teams |
| `notes` | list with pen and paw | Notes, coding, annotation |
| `panel` | three puppies | Panels, focus groups, participants |
| `ai-duality` | half-sketch half-solid face | AI + human, augmentation |

Container styles, by folder:

- `tiles/tile-<motif>.png` — white glyph on teal rounded square. App-icon weight; feature
  grids, section markers on light backgrounds.
- `circles/circle-<motif>.png` — white glyph on teal circle. Avatars, step numbers, social.
- `outline/outline-<motif>.png` — teal line on white tile. Quieter lists, tables, docs.
- `doc/doc-<motif>.png` — glyph on a dog-eared page. Anything about files/documents.
- `glyphs/glyph-<motif>.png` — bare teal glyph, no container. Inline with text, headers.
  (No `network` in this family — use the outline version.)
- `dark/dark-<motif>.png` — white line version. The ONLY set for dark/teal backgrounds.
- `mascot/puppy-<pose>.png` — the teal puppy: `sitting, side, back, lying, standing,
  walking, playing, running, resting, listening`. One per composition, never a crowd.
- `mascot-ink/puppy-ink-<pose>.png` — black mascot for mono/print contexts.

Picking rules: match the motif to the CONTENT (a survey feature gets `survey`, not a random
cute one); one container style per composition — don't mix tiles with outlines in the same
grid; the mascot is garnish, not wallpaper — once per page/slide/post at most, usually
near the title or as a sign-off.

## Per-medium guides — read the one you need

| Making | Read |
|---|---|
| Slides / decks | `references/slides.md` |
| PDF or Word documents, tutorials, one-pagers | `references/documents.md` |
| Web pages, landing pages, HTML email | `references/web.md` |
| Social posts (LinkedIn, X, WeChat), announcement cards | `references/social.md` |
| Ads and banners | `references/ads.md` |
| CSS/design tokens to copy-paste | `references/brand-core.md` |

Every guide shares the same skeleton: paper background, ink text, teal accents used
sparingly (roughly one accent moment per view), generous whitespace, one mascot at most.
When in doubt, remove decoration rather than add it.
