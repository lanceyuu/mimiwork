---
name: qualitati-publish-survey
description: Run QualiTaTi's pre-publish check on a survey and publish it, returning the link respondents open.
allowed-tools: qualitati_publish_survey
---

# Publish a QualiTaTi survey

Use this skill when the user wants a survey live: "publish it", "give me the link to send to participants".

## Workflow

1. Confirm the survey id (from the surveys or create skill) and that the user wants it live now.
2. Call `qualitati_publish_survey`. It runs QualiTaTi's preflight first; if the check finds errors, the survey is not published and the findings come back.
3. On findings, explain each in plain words and fix them with the edit skill, then try again.
4. On success, give the `share_url` and note any warnings.

## Boundaries

- Publishing exposes the survey to anyone with the link; it is approval-gated and only done on the user's explicit say-so.
- If the account is signed out or expired, direct the user to Settings, Models, QualiTaTi account.
