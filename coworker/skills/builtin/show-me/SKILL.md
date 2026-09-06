---
name: show-me
description: Explain the current topic, or how the last task was done, visually — a short flow diagram, call tree, file tree, diff, or one focused HTML page. Use when the user says "show me", "draw it", "visualize", "how did you do that", or presses "Show me how" after a task.
---

# Show me

Help the user understand the current topic visually. Skip the preamble, keep prose brief,
and pick the smallest view that makes the key point clear. One or two visuals, not all of them.

## When the user asks how the last task was done ("Show me how")

Look back at what you actually did in this conversation: the steps, the tools, the files
read and produced, the decisions. Draw THAT — not a generic process. Real names, real files.
Usually one Mermaid flowchart (steps → files) is enough; add a short list only for a decision
the diagram cannot show.

## Views

- Flow, sequence, or data flow — Mermaid (it renders inline in the chat):

```mermaid
flowchart LR
    A[Read interviews.docx] --> B[Extract 5 themes]
    B --> C[Write report.docx]
    C --> D[Save to Reports/]
```

```mermaid
sequenceDiagram
    participant User
    participant Mimi
    participant Files
    User->>Mimi: summarize the interviews
    Mimi->>Files: read interviews.docx
    Mimi->>Files: write report.docx
    Mimi-->>User: link to the report
```

- Logic or an algorithm — pseudocode in a text fence:

```text
on(save)
  if content is unchanged
    return cached result
  write new content
```

- Control flow — a call tree; file responsibility — a shallow file tree:

```text
Reports/
├── report.docx        # the deliverable
└── themes.md          # working notes
```

- What changed — a `diff` fence, in the shape of the thing that changed (tree, flow, steps).

- A layout, a state comparison, or something too dense for Mermaid — write ONE
  self-contained HTML file (inline CSS and SVG, no network, no libraries) into the
  workspace and link it as `[Title](artifact:path/to/show-me-topic.html)`. White page,
  teal `#0d9488` accent, `#1f2937` text, `#e5e7eb` borders, system font.

## Guidance

Place each visual next to the sentence it supports. Keep only the steps, files, and
boundaries needed to answer the question. Mermaid labels: plain words, no quotes or
brackets inside a node label (they break the parser). Never draw a step you did not take.
