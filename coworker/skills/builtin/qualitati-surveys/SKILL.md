---
name: qualitati-surveys
description: List the surveys in the signed-in QualiTaTi account, or read one survey's questions and blocks, before responses, edits or publishing.
allowed-tools: qualitati_surveys
---

# Find or inspect a QualiTaTi survey

Use this skill when the user refers to a QualiTaTi survey by name, topic or approximate date, or wants to see what a survey currently contains.

## Workflow

1. Call `qualitati_surveys` after the user approves access to their QualiTaTi data. With no arguments it walks every survey project in the account; pass `project_id` to look inside one project, or `survey_id` to read one survey in full (questions, blocks, links).
2. Match the user's wording against the returned titles, projects and dates. Never invent or reconstruct an ID.
3. If one result clearly matches, state its title and survey ID. If several are plausible, show a short numbered choice with the fields that distinguish them.
4. Ask the user to choose when ambiguity would change which responses are accessed or which survey is edited.
5. Use the verified survey ID with the response, analytics, export, edit or publish skill appropriate to the requested outcome.

## Boundaries

- The list is sensitive account metadata and remains subject to MimiWork's approval gate.
- Listing surveys is not consent to read individual responses or download a dataset.
- Keep unrelated surveys out of the response; return only enough context to make the selection.
- If the returned list is capped, say it may be partial and ask for a more precise title instead of claiming the survey does not exist.
- If the account is signed out or expired, direct the user to Settings, Models, QualiTaTi account. Do not ask for credentials in chat.
