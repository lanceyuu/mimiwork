# MimiWork interface review and product advice

Reviewed 5 September 2026. Scope: session/composer, account menu, Settings > Skills,
community-skill discovery and installation. Visual inspection used the real React app
with hermetic browser fixtures; no live account or paid model call was used. This is a
focused interface review, not a claim of a complete accessibility or usability study.

## Changes made

| Finding | Change |
| --- | --- |
| Puppy hid the balance until the final 10% | Show remaining free requests, daily cap, and local reset time whenever Puppy is selected. Retain the low and exhausted states. Refresh on window focus as well as the existing minute/turn refresh. |
| Missing allowance could look like exhaustion; another free model could supply the number | Read only Puppy's model entry and require both allowance fields. Missing data stays unknown. Failed GUI refresh clears stale data. |
| Thousands of skills gave little guidance about where to begin | Open on a Recommended shelf containing three specific upstream skills. Keep search and all existing category shelves. |
| Search input relied on a placeholder | Add an accessible name and a Clear search button that returns to the active shelf. |
| Late search results could overwrite a newer query | Apply only the latest request's result. |
| Store failures looked like no matching skills | Show a retry action; HTTP errors now enter the failure path. |
| Skill names were squeezed beside actions in narrow settings panels | Wrap publisher labels and move actions below descriptions when the results container is narrow. |

Puppy's free requests and purchased QualiTaTi credits are distinct units. A multi-step
agent task may make several model requests. The reset remains the backend's existing
next-midnight-UTC estimate; this change does not independently verify the gateway's reset
policy. No balance is invented when the gateway is unavailable.

## Skill selection and provenance

| Skill | Why it fits MimiWork | Pinned source | License inspected |
| --- | --- | --- | --- |
| Sepia | Review and revise professional prose; preserve facts and author intent; Chinese guidance | [Nanako0129/sepia](https://github.com/Nanako0129/sepia/tree/401c89e43caf03ce5e8da0bf5cd6c96095ba70af/skills/sepia) | MIT, repository root |
| Internal Comms | Team updates, newsletters, FAQs, and project reports | [anthropics/skills](https://github.com/anthropics/skills/tree/41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f/skills/internal-comms) | Apache-2.0, skill folder |
| Theme Factory | Consistent colors and typography for documents and slides | [anthropics/skills](https://github.com/anthropics/skills/tree/41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f/skills/theme-factory) | Apache-2.0, skill folder |

These are optional store listings, not automatically enabled skills. Sepia uses the
canonical folder, not its sibling-dependent command wrappers. The existing installer
successfully downloaded all three to an isolated temporary folder: 17, 6, and 13 files
respectively. No downloaded scripts or model workflows were executed. Installation
compatibility is verified; output quality across Mimi models is not yet benchmarked.
The community collection was not mass-refreshed, and existing user skills were untouched.

## Visual verification

Inspected account/settings before changes and the updated store at 980, 1280, and 1920
pixels wide, plus a 768-pixel stress case. The native app's minimum width is 980 pixels.
Inspected Puppy's new balance in the 1280-pixel session view. Browser tests cover selecting
Puppy, finding Sepia, and clearing search back to the Recommended shelf.

## Advice: make the first finished file the product's main journey

My highest priority would be a short path from supplied material to a useful, editable
file. Offer three prominent starting tasks: summarize interviews into Word, clean a
spreadsheet, and turn notes into slides. Ask for the input and desired output, then guide
the user through a complete task. The current starting view already asks “What should we
produce?”; its example cards can connect that promise more directly to Office outputs.

After that, I would prioritize:

1. Make completion unmistakable: finished filename, a short account of what was checked,
   and direct Open / Show folder / Revise actions. Evaluate this across Word, slides, and
   spreadsheets before changing every results surface.
2. Add examples to recommended skills: one sample request, expected output, required tools,
   and a tested-on date. Grow the shelf only after running the same tasks on Puppy and a
   stronger Mimi model. Treat “recommended” as a maintained selection, not a popularity score.
3. Reduce first-run navigation choices. Keep advanced model, connector, and permission
   controls available, but test whether they need to be visible before the first task.
4. Make costs understandable before a long run: free request balance, separate paid-credit
   balance, and an explanation that one task can use multiple requests. Estimate costs only
   where model usage supports a defensible estimate.

Validate priorities with a small observed usability study: can a new user supply a file,
choose a useful task, find the result, and request a revision without help? Track completion
and time to first useful file; ask users whether the result is usable in their actual work.

## Validation results

- Backend: 1,690 passed, 3 skipped.
- GUI: 338 passed across 45 files.
- Browser: 179 passed, including both new user journeys.
- TypeScript: passed (`tsc --noEmit`).
- Ruff: passed.
- ESLint: no errors; 62 warnings across the GUI.
- Rust was unchanged; Cargo tests were not required.

No app bundle was built, installed, tagged, pushed, or released.
