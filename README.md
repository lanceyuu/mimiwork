# MimiWork

**Your AI coworker for real work — documents, decks, spreadsheets, and data analysis, finished on your desktop.**

Most AI assistants answer questions. MimiWork ships deliverables: a formatted Word report, a PowerPoint deck with speaker notes, a cleaned-up Excel workbook, a regression run in Python or R with the assumptions actually checked — saved as files you can open, edit, and send.

It runs on your machine, works with the model provider *you* choose, and asks before doing anything consequential.

```text
┌────────────────────────────────────────────────┐
│               MimiWork desktop app             │  native shell + GUI
├────────────────────────────────────────────────┤
│           local agent server (Python)          │  engine · tools · connectors
├───────────────┬────────────────┬───────────────┤
│  your files   │   your tools   │  your model   │  everything runs with your keys,
│  & terminal   │ 25+ connectors │  any provider │  on your machine
└───────────────┴────────────────┴───────────────┘
```

## Why MimiWork

**It produces the deliverable, not a to-do list.** Ask for "a one-page brief from these three PDFs" and you get a `.docx` in your workspace — with the source PDFs actually read, tables extracted, and the numbers carried over.

**It's built for knowledge work, not coding.** Three specialist coworkers ship out of the box:

| Persona | What it does |
|---|---|
| **Data Analyst** | Profiles your dataset before touching it (SPSS/Stata *variable and value labels* included, so `q4_1` becomes "Satisfaction with onboarding, 1–5"), runs the analysis in a persistent Python kernel or R, and reports sample sizes, effect sizes, and assumption checks — not just p-values. |
| **Document Writer** | Drafts and revises Word documents in place without destroying formatting — headings, tables, comments and all. |
| **Deck Builder** | Turns findings into a PowerPoint that argues a case, with charts built from your actual data and speaker notes for whoever presents it. |

**It reads what work actually arrives in.** PDFs (including table extraction, with an explicit warning when a document is scanned rather than silently returning nothing), Word, Excel, PowerPoint, CSV, SPSS `.sav`, Stata `.dta`, and images — which it can also crop, annotate, and combine into figures.

**It checks in before acting.** Sends, writes, and shell commands are approval-gated. Unattended scheduled runs park their asks in an inbox instead of acting on their own.

**It connects to where you work.** 25+ integrations — Slack, Outlook, Gmail, Google Calendar, GitHub, Jira, Notion, Linear, HubSpot, monday.com and more — plus anything reachable over [MCP](https://modelcontextprotocol.io/). Mention it in a Slack channel and the finished work comes back as a thread reply.

**It runs on a schedule.** A morning brief, a weekly report, a standing watch over a channel — automations run locally with full transcripts.

## Bring your own model

No lock-in, no markup — paste your own API key and switch providers anytime:

**OpenAI · Anthropic · Google Gemini · DeepSeek · Qwen · Kimi (Moonshot) · GLM (Z.ai) · MiniMax · Mistral · Grok (xAI) · Inkling** — open-weight models via **Together** and **Fireworks**, AWS **Bedrock**, and fully local via **Ollama**.

## Install

### macOS (Apple Silicon)

Grab the `.dmg` from [Releases](https://github.com/lanceyuu/mimiwork/releases), drag to Applications. Builds are not yet signed, so the first launch needs right-click → Open.

### Run from source

Prerequisites: Python 3.10+, Node 20+, and (for the desktop shell) Rust via [rustup](https://rustup.rs/). Building the app also needs `cmake` (`brew install cmake`).

```shell
git clone https://github.com/lanceyuu/mimiwork
cd mimiwork

# 1. One-time bootstrap — creates the Python venv at .venv
bash packaging/setup_dev_env.sh

# 2. Start the local agent server
.venv/bin/openworker-server --cwd ~/some/project --port 8765

# 3. In a second terminal, start the UI
cd surfaces/gui
npm install
npm run dev        # browser UI on the Vite dev port
```

For the full desktop app, replace step 3 with `npm run tauri dev`. Build an installable DMG with `packaging/build_dmg.sh`.

## Privacy

MimiWork is local-first. The agent loop, your conversations, connector tokens, and model keys all live on your machine. Your data leaves it only through the model and integrations you choose.

## Quality

The test suite is part of the product: **1,372 backend tests** cover the agent engine, tools, and connectors — including that every Office tool registers a schema a real provider accepts, that code-execution tools are approval-gated like the shell, and that a scanned PDF is flagged rather than silently summarized from nothing. **111 GUI tests** cover the desktop app.

## Repository layout

| Directory | What's in it |
|---|---|
| `coworker/` | Python backend — agent engine, model providers, office/PDF/image/analysis tools, connectors, MCP client, automations |
| `surfaces/gui/` | Desktop app — React UI + Tauri shell |
| `stt/` | Speech-to-text sidecar (Rust) for voice input |
| `packaging/` | Installer builds (macOS DMG, Windows), dev bootstrap |
| `docs/` | Design specs and decision logs |
| `tests/` | Backend test suite |

## Acknowledgements

MimiWork is a fork of [OpenWorker](https://github.com/andrewyng/openworker) by Andrew Ng and contributors, which is built on [aisuite](https://github.com/andrewyng/aisuite). This fork repositions the tool for knowledge work — Office deliverables, PDF and image handling, and a statistics-aware data-analysis toolchain — and carries its own desktop refinements. Internal binary and package names (`coworker`, `openworker-server`) retain their upstream names for compatibility.

## License

MIT — see [LICENSE](LICENSE). Original work © 2024 Andrew Ng; modifications © 2026 MimiWork contributors.
