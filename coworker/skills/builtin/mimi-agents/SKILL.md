---
name: mimi-agents
description: >
  Design, save, change or run a reusable team of AI agents (the Agents section): an
  agentic AI system where each agent has its own job, model, thinking effort and
  tools, and coding agents such as Claude Code or Codex can take part. Use whenever
  the user asks for "an agent system", "a team of agents", "agents that work
  together", "a multi-agent workflow", a pattern from the Agents gallery (sequence,
  routing, parallel work, reflection, ReAct, planning, tool use, multi-agent, human
  review), or asks to run or change a system they already saved.
---

# Agent systems

An agent system is a small diagram the user keeps and reuses. You save it with
`create_agent_system`, change it with `update_agent_system`, and run it with
`run_agent_system`. It shows up under **Agents** at once, where the user can drag,
add and connect agents themselves.

## 1. Understand the need (short)

Ask only what you cannot see, at most three questions, one at a time:
1. What goes in, and what should come out (a reply, a report, a file, a code change)?
2. What does good look like, and what mistake would hurt?
3. Where must a person decide before anything is final?

If a folder is involved, look at it before designing.

## 2. Pick the simplest pattern that fits

| Pattern | Use when | Draw it as |
|---|---|---|
| Sequence | Steps depend on each other | agent → agent → agent |
| Routing | Different requests need different handling | router with labelled edges to one agent per kind |
| Parallel work | Parts can be done at once, then combined | one agent fanning out to several, all joining one combiner |
| Reflection | Quality matters and can be checked | writer → checker, with a loop edge back (max_rounds 2-3) |
| ReAct | The next step depends on what was just found | ONE agent with tools, told to look, act and observe |
| Tool use | The answer needs outside facts | look-up agent with tools → writer |
| Planning | One request hides several tasks | lead agent (`orchestrator`) that plans and assigns to helpers |
| Multi-agent | Parts need different expertise or models | lead agent with specialist helpers on `assign` edges |
| Human review | A commitment, an exception or money is involved | drafter → `review` node, with a `revise` loop edge back |

Combine patterns only when the need demands it. If one well-instructed chat would do,
say so and do not build a system.

## 3. Write each agent

- `name`: a plain job title ("Check the facts"), never jargon.
- `instructions`: address the agent directly; say what it receives, what it must
  produce, and the check it must pass. A checker must name what it checks against.
- `model`: leave empty to use the chat's model. Put cheap, fast models on sorting and
  look-ups, and stronger ones on writing and checking when the user cares about quality.
- `effort`: `low` for sorting and look-ups, `high` for checkers and planners, empty otherwise.
- `tools`: only what that agent needs, from: files, documents, spreadsheets, slides, pdf,
  images, data_inspect, python_analysis, r_analysis, knowledge_base, search, git, todo.
- Coding agents (`kind: coding`): `agent` is claude_code, codex, cursor, gemini or
  opencode, and `folder` is the project folder. Coding agents in one system share one
  copy of the project on its own branch, so a reviewer sees the builder's work. A good
  pair is one builds, the other reviews, with a loop edge back for fixes.

Subagents can edit files inside the granted folders. Anything that runs a command or
leaves the machine stops for the user in the Inbox. Design for that: let the system
produce the work, and send, publish or pay only after the user has seen it.

## 4. Save, show, test

1. Call `create_agent_system`. If it returns `problems`, fix them with
   `update_agent_system` before you go on.
2. Show the returned Mermaid diagram in a ```mermaid block, then one line: "You can
   drag, add and connect agents under Agents."
3. Before running a system with coding agents, make sure each coding agent's folder is
   open in this chat. If it is not, ask for it with `request_directory` (writable).
   A folder outside this chat makes that agent fail.
4. Offer one test run on a real example. `run_agent_system` asks the user first. A
   review step asks the user in the chat or Inbox and waits for the answer.
5. Report the result and, if a step disappointed, propose one concrete change to
   that agent's instructions, model or effort.
