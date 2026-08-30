---
name: qualitati-survey-responses
description: Retrieve either aggregate analytics or a bounded response sample from one verified QualiTaTi survey with explicit approval.
allowed-tools: qualitati_survey_responses
---

# Read QualiTaTi survey results

Use this skill when the user needs results from a known QualiTaTi survey and a full exported dataset is not required.

## Workflow

1. Resolve the exact survey ID before retrieving any data.
2. Choose the least sensitive useful view. Set `analytics` to `true` for an existing aggregate summary; use `false` only when the task genuinely needs individual responses.
3. Let MimiWork request approval for this specific retrieval, then call `qualitati_survey_responses` once with the verified `survey_id` and chosen `analytics` value.
4. Describe which view was returned. For raw responses, state when the result is capped or trimmed and never imply that a sample is the full dataset.
5. For calculations that require all rows, stop and use the survey-export workflow instead of extrapolating from the bounded response list.

## Boundaries

- Approval applies to this retrieval, not every survey in the account.
- Minimize exposure of free-text answers and respondent identifiers in the final response.
- Do not calculate precise population statistics from a truncated response list.
- Check denominators, missing values, and question scales before interpreting analytics.
- If access fails, report the error plainly. Never bypass QualiTaTi access controls or request credentials in chat.
