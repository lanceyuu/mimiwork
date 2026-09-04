---
name: qualitati-edit-survey
description: Change an existing QualiTaTi survey — retitle it, add questions or blocks, delete questions — after reading its current state.
allowed-tools: qualitati_edit_survey
---

# Edit a QualiTaTi survey

Use this skill when a survey already exists on QualiTaTi and the user wants it changed: "add an attention check", "drop question 4", "rename the survey".

## Workflow

1. Read the survey first with the surveys skill (`survey_id`) so question ids and block titles are known. Never guess an id.
2. Confirm the exact change with the user when it deletes anything.
3. Call `qualitati_edit_survey` with the `survey_id` and only the parts that change: `title`, `description`, `add_questions` (same shape as when creating; set `block` to place a question in a block), `delete_question_ids`, `blocks`.
4. Report what changed and any `problems` the result lists.

## Boundaries

- Deleting questions from a published survey with responses changes the dataset; say so before doing it.
- Edits are approval-gated writes to the user's account.
- If the account is signed out or expired, direct the user to Settings, Models, QualiTaTi account.
