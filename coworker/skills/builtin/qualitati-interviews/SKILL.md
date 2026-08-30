---
name: qualitati-interviews
description: List the interviews inside a verified QualiTaTi project so the user can select the right participant or session safely.
allowed-tools: qualitati_interviews
---

# List QualiTaTi interviews

Use this skill when the user needs to locate interviews within a known QualiTaTi interview project. The goal is to identify the correct interview UUID before requesting its transcript.

## Workflow

1. Obtain a verified project UUID. If the user supplied only a project name, resolve the project first rather than guessing.
2. Call `qualitati_interviews` with that `project_uuid`.
3. Present only useful selection details, such as participant label, status, date, and interview UUID. Keep the list compact.
4. If one interview clearly matches, confirm the match. If several could match, ask the user to choose before fetching any transcript.
5. Pass the selected interview UUID to the transcript workflow only when transcript content is actually needed.

## Boundaries

- This tool reads personal research metadata from QualiTaTi and is approval-gated. Wait for approval; do not work around a denial.
- Listing interviews does not authorize downloading every transcript in the project.
- Never infer participant identity from a partial label or expose unrelated participant details.
- If the project has more interviews than the returned page shows, say that the result is partial instead of claiming completeness.
- On a missing or expired sign-in, direct the user to Settings, Models, QualiTaTi account. Do not collect credentials yourself.
