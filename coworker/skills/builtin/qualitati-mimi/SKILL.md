---
name: qualitati-mimi
description: Delegate project analysis and editing to QualiTaTi's server-side Mimi agent while preserving confirmations, context, and user control.
allowed-tools: qualitati_mimi
---

# Work through QualiTaTi Mimi

Use this skill when the user wants QualiTaTi to analyze or change a research project, including transcript work, ThemeLens, survey statistics, data-quality checks, interview outlines, survey questions, or project creation.

## Workflow

1. Resolve the intended project first and obtain its real UUID when the task concerns an existing project.
2. Turn the user's goal into one clear, self-contained request. Call `qualitati_mimi` with that request and `project_uuid` when known.
3. Keep follow-up calls in the same conversation so Mimi can build on its earlier work. Set `new_conversation` only for a genuinely separate task or when the user asks to start over.
4. Relay Mimi's substantive answer faithfully. Separate what Mimi reports from any interpretation added by MimiWork.
5. If Mimi asks for confirmation for a destructive or credit-consuming action, stop and present that exact decision to the user. Continue only after an explicit yes.

## Boundaries

- Never turn a vague request into a broader project mutation.
- Do not claim that a server-side action succeeded unless the tool result says it did.
- Do not retry a usage-limit response or an ambiguous write automatically.
- A Skill does not bypass QualiTaTi billing, confirmation gates, access rules, or MimiWork permissions.
- If sign-in has expired, direct the user to Settings, Models, QualiTaTi account; never ask them to paste credentials into chat.
