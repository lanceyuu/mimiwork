---
name: qualitati-projects
description: Find the correct interview or survey project in the signed-in QualiTaTi account before any project-specific work begins.
allowed-tools: qualitati_projects
---

# Find a QualiTaTi project

Use this skill when the user refers to a QualiTaTi study, interview project, or survey but has not supplied a project UUID. The outcome is a verified project identity that another QualiTaTi workflow can safely use.

## Workflow

1. Call `qualitati_projects`. If the current tool schema accepts `project_type`, pass `interview` or `survey` only when the user's request makes the type clear.
2. Match projects using the user's wording, project type, and dates. Never guess a UUID from a title.
3. If exactly one project is a convincing match, state its name, type, and UUID briefly.
4. If several projects could match, show a short numbered choice with distinguishing details and ask the user which one they mean.
5. If there is no match, say so and ask for a different title or type. Do not silently substitute a nearby project.

## Boundaries

- A project listing is an index, not permission to fetch transcripts or responses.
- If MimiWork asks for approval before accessing QualiTaTi, wait for the user's decision.
- If the tool reports that the account is signed out or expired, direct the user to Settings, Models, QualiTaTi account. Do not request or handle credentials in chat.
- Return only the identifying fields needed for the next step. Do not expose unrelated project details.
- For analysis or changes, load the skill for the specific QualiTaTi tool that will do that work.
