---
name: qualitati-create-survey
description: Build a questionnaire on QualiTaTi from a study design — project, survey, blocks (including randomized conditions), questions and stimulus images — in one call.
allowed-tools: qualitati_create_survey
---

# Create a survey on QualiTaTi

Use this skill when the user wants a questionnaire to exist on QualiTaTi: "put this study on QualiTaTi", "create the survey", "build the questionnaire for the experiment".

## Workflow

1. Design first, in the conversation: the blocks, each question's type and wording, the scales, and which workspace image (if any) each stimulus shows. Ground scales in the study document or the literature; keep variable names short and meaningful (`brand_attitude_1`).
2. Show the user the plan as a compact list and get a yes. One call creates everything; a wrong plan is cheaper to fix on paper.
3. Call `qualitati_create_survey` once with `title`, `description`, `questions` in order, and `blocks` when the design needs them. Omit `project_id` and a study project named after the survey is created; pass one only when the user named an existing survey project.
4. Read the result: `questions_added`, `problems` (questions that were refused and why) and `builder_url`. Fix problems with the edit skill rather than creating a second survey.
5. Tell the user the survey is a draft, give the builder link, and offer to publish.

## Question shapes

- Choice: `single_choice`, `multi_choice`, `dropdown`, `ranking`, `constant_sum` need `options`.
- Agreement items: `rating_scale` with `min`, `max`, `min_label`, `max_label` (a 7-point Likert is min 1, max 7). Several items on one scale: `matrix` with `rows` (statements) and `columns` (scale points).
- Semantic differential: `bipolar_scale` with the two poles in `min_label` / `max_label`.
- Stimulus or instruction: `info_text` with the passage in `prompt` and a workspace image path in `image` (PNG, JPEG, GIF or WebP, at most 2 MB).
- Open answers: `short_text` or `long_text`; set `follow_up` to `light` or `deep` for AI probing.
- Between-subjects conditions: a block with `randomizer: true` and `children` named for the conditions; give each condition's stimulus and questions `block` set to that child's title.

## Boundaries

- Creating a survey writes to the user's QualiTaTi account and is approval-gated; never call it before the user has agreed to the design.
- Do not paste the survey into `qualitati_mimi`; this tool builds it directly.
- Never publish from this skill; publishing is its own decision.
- If the account is signed out or expired, direct the user to Settings, Models, QualiTaTi account.
