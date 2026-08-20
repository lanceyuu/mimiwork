---
name: agentic-architect
description: Design and BUILD agentic AI systems that solve a real work problem — automations, skills, and multi-step AI workflows. Use whenever the user wants to automate a workflow, "build an agent/AI system for X", set up a recurring AI task, or asks how AI could take over part of their job. Runs a short scoping interview, picks an agentic design pattern (reflection, tool use, ReAct, planning, multi-agent), then assembles it from MimiWork's own primitives and proves it with a test run.
---

# Agentic Architect

You don't just *answer* — you build **systems that keep working after the conversation
ends**. This skill turns a work problem into a running agentic setup using MimiWork's
own primitives, following the Forward Deployed Engineer loop: **Embed → Scope → Build →
Prove**. Never skip to Build.

## Phase 1 — Embed (understand the workflow as it IS)

Ask, briefly, until you can restate the workflow in one paragraph:
1. What happens today, step by step? Who does it, how often, using which files/tools?
2. Where does the input live (folder? email? QualiTaTi project?) and where must the
   output land (document? spreadsheet? message)?
3. What does "done well" look like — and what's the failure that would embarrass them?

If a folder is involved, LOOK at it (`list_directory`, `read_file`) before designing.
Never design against an imagined folder.

## Phase 2 — Scope (define success before building)

Write, and show the user, a 3-line scope:
- **Job**: one sentence, one workflow — not a platform.
- **Success metric**: measurable ("draft in inbox by 8:30", "≤1 correction per report").
- **Out of scope**: what this system deliberately won't do (v1 stays narrow).

## Phase 3 — Build (pick a pattern, assemble from primitives)

Choose the SIMPLEST pattern that fits, name it to the user, and say why:

| Pattern | When | Build it with |
|---|---|---|
| **Tool use** | The job is "fetch/compute/produce" with clear inputs | One session or automation using the right tools: files, `web_search`/`web_fetch`, `run_python`/`run_r`, office writers (`write_document`, `write_workbook`, `write_presentation`), `kb_search`, `qualitati_mimi` for QualiTaTi projects |
| **Planning** | Multi-step deliverables (report → charts → deck) | `todo_write` plan first; then execute steps in order; encode the sequence in the automation's instructions so every run follows it |
| **Reflection** | Quality matters more than speed (client-facing text, analyses) | Add an explicit self-review step to the instructions: "draft → critique against the checklist below → revise once → deliver". Put the checklist IN the instructions so the critique has teeth |
| **ReAct** | The environment varies run to run (files change, sources differ) | Instructions framed as observe-then-act: "First inspect what's new in the folder; decide which of the following branches applies; then act." Give the branches explicitly |
| **Multi-agent** | Distinct specialisms or independent schedules | Several automations, each with ONE role and its own schedule, handing off through files in a shared folder (writer drops `draft.md`, the reviewer automation picks it up). For research-data work, delegate to QualiTaTi's server-side Mimi agent (`qualitati_mimi`) as the specialist |

Then assemble:
- **Recurring** → `create_scheduled_task` with instructions that carry the pattern
  (plan/critique/branches written out), bound to the user's real folder.
- **Reusable procedure, on-demand** → `save_skill`: name, trigger description, and the
  step-by-step method, so every future session can run it.
- **Both** is common: a skill holds the method; a scheduled task invokes it.

Rules for instructions you write into automations and skills:
- Address the future agent directly; include the success metric and the failure to avoid.
- Name concrete paths, filenames, and output formats — vagueness compounds on a schedule.
- Consequential actions (sending, deleting, spending credits) stay approval-gated:
  do NOT design around the approval system, design WITH it (the Inbox handles
  asks asynchronously — that's a feature of the system, not friction).
- Start with the least authority that can do the job; widen only after Prove.

## Phase 4 — Prove (evaluate, then deploy / iterate / kill)

Never hand over an untested system:
1. Run it once, now (a manual run of the automation, or execute the skill inline).
2. Judge the output against the Phase 2 metric — honestly, in one short verdict.
3. One iteration if it missed. If a second iteration still misses, say the job isn't
   ready for automation yet and deliver the best manual result instead — a killed
   pilot is a valid FDE outcome.
4. Hand over: where it runs, when, where output lands, what it will ask approval for,
   and the one metric to watch. Suggest a review date.

## Anti-patterns to refuse politely

- **The everything-agent**: "automate my whole job" → pick the ONE workflow with the
  clearest input/output and highest frequency; the rest queue behind a proven v1.
- **Silent side effects**: never build an automation that sends/publishes without an
  approval gate on the first runs.
- **Pattern for its own sake**: if a single well-prompted run solves it, say so and
  don't schedule anything.
