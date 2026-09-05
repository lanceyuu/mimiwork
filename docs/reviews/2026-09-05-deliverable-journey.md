# From a starting request to a finished file

Follow-up to the 5 September interface review, implemented at the owner's request.

## What changed

The start screen now offers three primary tasks: summarize into Word, clean a spreadsheet,
and turn notes into slides. Each prepares an editable request, focuses the composer, and
asks for source material if it is missing. It does not send automatically. The requests
specify editable Office outputs, source preservation, relevant checks, and a link to the
result. Folder access, Canva, and custom style skills remain under “More ways to start.”

Saved-file rows now offer Open, Show in folder, and Revise for the same file. Revise prepares
a request containing the exact path and asks for a separate revised copy. It is disabled
while Mimi is working. Existing detailed preview comments remain available. The interface
reports that files are saved; it does not claim that an unfinished or failed task passed
quality checks. Actual verification summaries remain the assistant's responsibility.

The Puppy allowance explains that one task can use several requests. Account credits are
shown separately when the gateway supplies a balance. The exhausted state explains that
switching to Hound uses account credits. No cost estimate is invented.

The Recommended shelf now contains eight skills. Each has an example request, expected
output, requirements, and an installation-check date. Their folders were downloaded with
the production installer into an isolated temporary directory. No skill was enabled in a
user's profile and no downloaded code or model workflow was executed.

## Five additional recommended selections

| Skill | Purpose | Source and revision |
| --- | --- | --- |
| Content Research Writer | Sourced articles and briefings | [ComposioHQ](https://github.com/ComposioHQ/awesome-claude-skills/tree/be2a406907dbc61b73e6827ded415c96139d13a2/content-research-writer) |
| Meeting Insights Analyzer | Transcript-based communication feedback | [ComposioHQ](https://github.com/ComposioHQ/awesome-claude-skills/tree/be2a406907dbc61b73e6827ded415c96139d13a2/meeting-insights-analyzer) |
| Changelog Generator | Plain-language release notes from Git history | [ComposioHQ](https://github.com/ComposioHQ/awesome-claude-skills/tree/be2a406907dbc61b73e6827ded415c96139d13a2/changelog-generator) |
| Tailored Resume Generator | Adapt a resume to a job description | [ComposioHQ](https://github.com/ComposioHQ/awesome-claude-skills/tree/be2a406907dbc61b73e6827ded415c96139d13a2/tailored-resume-generator) |
| Copy Editing | Focused edits for clarity, voice, and consistency | [Corey Haines](https://github.com/coreyhaines31/marketingskills/tree/5b2c0007766c6a1cf1d53fd8fc73e979e0821022/skills/copy-editing) |

Composio's README declares Apache-2.0 with possible per-skill exceptions; these four folders
contain only their SKILL.md and no separate license override. Corey Haines' repository
contains an MIT license. These are optional links to pinned upstream files, not bundled
copies. Some selections were already present in the large community index; the curated
entries now update those sources and make them easier to find. Matching old repo/path
entries are removed from the loaded catalog so the listing and installation agree on the
revision. Sepia, Internal Comms, and Theme Factory remain recommended.

## Practical limits

This work implements the first-file journey, visible revision actions, a smaller initial
choice set, useful skill examples, and clearer allowance information. It does not claim
measured improvements in user success. Cross-model output evaluation on Puppy and stronger
models, and an observed usability study with new users, remain validation work. Installation
checks are explicitly labelled as such in the store.

The browser tests simulate backend responses and verify requests and navigation; they do
not generate real Office files. Existing backend document tests exercise the file tools.
No application build, installation, tag, push, or release was performed.

## Validation

- Backend: 1,691 passed, 3 skipped.
- GUI: 340 passed across 45 files.
- Browser: final full run passed all 185 tests. The first full run had one intermittent
  context-bar test failure; it passed an isolated recheck and the final full run.
- TypeScript and Ruff passed. ESLint reported 62 warnings and no errors.
- Visual inspection covered the start screen, prepared requests, saved-file actions,
  and the expanded skill store. The new browser journeys cover all three Office formats.
- All eight recommended skill folders downloaded successfully through the production
  installer. No model-quality benchmark is implied by these installation checks.
