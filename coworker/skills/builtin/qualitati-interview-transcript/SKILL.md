---
name: qualitati-interview-transcript
description: Retrieve one selected QualiTaTi interview transcript with explicit approval and keep sensitive participant data tightly scoped.
allowed-tools: qualitati_interview_transcript
---

# Retrieve one QualiTaTi transcript

Use this skill when the user's task requires the conversation from one identified QualiTaTi interview. Resolve the interview UUID before loading the transcript.

## Workflow

1. Confirm which interview the user means. Do not call `qualitati_interview_transcript` with a guessed or ambiguous UUID.
2. Explain briefly that the next action retrieves personal research data from QualiTaTi, then let MimiWork's approval prompt collect the decision.
3. After approval, call the tool once with `interview_uuid`.
4. Use only the returned content needed for the requested analysis. Preserve speaker attribution and distinguish quotations from summaries.
5. Tell the user if the transcript result says it was trimmed. Do not describe a partial transcript as complete.

## Boundaries

- A prior approval to list projects or interviews is not approval to fetch transcript content.
- Never fetch additional participants' transcripts merely to enrich the answer.
- Do not write the transcript to a local file unless the user asks for a file deliverable.
- Avoid repeating sensitive passages in the final answer when a concise finding is enough.
- If access is rejected, expired, or missing, report that plainly and direct the user to Settings, Models, QualiTaTi account. Never request credentials in chat.
