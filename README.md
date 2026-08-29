<div align="center">

# MimiWork

### The AI coworker that hands you the finished file.

Not a chat window. A colleague who reads your folder, does the work, and saves a `.docx`,
`.pptx` or `.xlsx` you can send — on your machine, with your model key, asking before
anything consequential.

[![Download for Mac](https://img.shields.io/badge/Download-macOS-000?style=for-the-badge&logo=apple&logoColor=white)](https://github.com/lanceyuu/mimiwork/releases/latest/download/MimiWork-macos-arm64.dmg)
[![Download for Windows](https://img.shields.io/badge/Download-Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/lanceyuu/mimiwork/releases/latest/download/MimiWork-windows-setup.exe)
[![Latest release](https://img.shields.io/github/v/release/lanceyuu/mimiwork?style=for-the-badge&label=version&color=0d9488)](https://github.com/lanceyuu/mimiwork/releases/latest)
[![MIT](https://img.shields.io/badge/license-MIT-555?style=for-the-badge)](LICENSE)

</div>

---

## The difference in one line

> **"Summarise these three PDFs into a one-page brief."**
>
> Most assistants: a summary in the chat, which you then paste into Word and format.
> **MimiWork: `brief.docx` in your folder** — PDFs actually read, tables extracted, numbers
> carried across, formatting intact.

That's the whole idea. Ask for an outcome, get the artifact.

## What it actually does

**Three specialists ship out of the box** — pick one, or let the generalist call them in.

| | What it produces |
|---|---|
| 📊 **Data Analyst** | Profiles the dataset before touching it — SPSS/Stata *variable and value labels* included, so `q4_1` becomes "Satisfaction with onboarding, 1–5" — runs the analysis in a persistent Python kernel or R, and reports sample sizes, effect sizes and assumption checks, not just p-values. |
| 📝 **Document Writer** | Drafts and revises Word documents **in place** without wrecking your formatting — headings, tables, comments and all — and can leave **real tracked changes** with a plain-language "what I changed and why". |
| 🎯 **Deck Builder** | Turns findings into a **16:9 PowerPoint that argues a case** — every slide titled with its takeaway, not its topic, and built from a real layout vocabulary (a single claim, a big number, a participant's own words, a side-by-side, a chart) rather than slide after slide of bullets. Charts come from your actual numbers, and speaker notes come with it. Text is measured and fitted so nothing walks out of its frame. Point it at your house template and it uses your brand instead. |

**It reads what work actually arrives in.** PDF (with table extraction — and an honest
warning when a document is *scanned* rather than silently returning nothing), Word, Excel,
PowerPoint, CSV, SPSS `.sav`, Stata `.dta`, and images it can crop, annotate and combine
into figures.

**Teach it your way once.** Package your brand colors, fonts and house rules into a
**skill** and every deck, document and spreadsheet comes out in them without being asked.
Browse **8,400 community skills** by shelf, and **read a skill's real instructions** — and
which tools it wants — before it ever lands on your disk.

**It connects to where you work.** 25+ integrations — Slack, Gmail, Outlook, Google
Calendar and Drive, GitHub, Jira, Notion, Linear, HubSpot, Canva, monday.com — plus
anything reachable over [MCP](https://modelcontextprotocol.io/). Tag it in a Slack channel
and the finished work comes back as a thread reply.

**Including where your data lives.** Connect **Qualtrics** and ask for the December wave:
it reads the questionnaire so `Q4_1` arrives as *"How satisfied were you with — speed of
setup"*, then downloads the responses as a CSV or a labelled SPSS `.sav` in your folder,
ready for the analyst. It never edits or sends anything in Qualtrics, and the download
itself asks you first.

**It runs while you don't.** A Monday brief, a weekly report, a standing watch on a
channel: automations run locally with full transcripts, and anything needing a decision
waits in an Inbox instead of guessing.

**You can steer it mid-run.** Notice it heading the wrong way? Just type — "use the
December wave, not November" lands at the next safe step without stopping the work, and a
looping model is caught and stopped **before it burns your credits**.

**It checks in before acting.** Sends, writes, shell commands and external data pulls are
approval-gated. **Plan mode** proposes first and runs nothing until you say go.

## What you learn here works everywhere

MimiWork deliberately borrows the vocabulary and the gestures of Claude Code, Claude Cowork
and Codex — so the habits transfer in both directions, and nothing you learn is trapped in
one app.

| In MimiWork | Cowork | Claude Code | Codex |
|---|---|---|---|
| **`/`** — app commands, your saved commands, your skills | `/` commands | slash commands | `/` commands |
| **`@`** — point at a file in a granted folder | `@` mentions | `@` mentions | `@` mentions |
| **Plan · Ask for approval · Full access** (⇧⇥ cycles) | Manual / Auto / Skip | plan / default / bypass | plan / approval / auto |
| **`AGENTS.md`** — and `CLAUDE.md` is read too | folder instructions | `CLAUDE.md` | `AGENTS.md` |
| **Skills** — `SKILL.md` folders, importable from `~/.claude/skills` | Skills | Skills | — |
| **Projects** — folder + instructions + memory + threads | Projects | a repo you `cd` into | a repo you `cd` into |

Settings ▸ **Transfer guide** keeps the full map one click away.

## Bring your own model — no lock-in, no markup

Paste your own key and switch anytime:

**OpenAI · Anthropic · Google Gemini · DeepSeek · Qwen · Kimi (Moonshot) · GLM (Z.ai) ·
MiniMax · Mistral · Grok (xAI) · Inkling** — open-weight models via **Together** and
**Fireworks**, AWS **Bedrock**, and fully local via **Ollama**.

Or skip keys entirely: **sign in with your [QualiTaTi](https://qualitati.com) account** and
the "Mimi" models spend your existing credits — nothing to configure. The Activity page
shows **exactly what each call cost and which pool paid** — the numbers come from the
server's own ledger, not a local estimate. A switch in Settings picks where the models
run: **US (cheaper credits) or strict-GDPR Paris 🇫🇷 (data stays in Europe)**. Signing in
also opens your QualiTaTi research data: ask for a project, an interview transcript or a
survey's responses and Mimi can pull them in to analyse — **each retrieval asks your
approval first**, and nothing is fetched on its own.

## Install

The app updates itself from then on.

| Your machine | Download | First launch |
|---|---|---|
| **Mac — Apple Silicon** (M1–M4) | [**MimiWork-macos-arm64.dmg**](https://github.com/lanceyuu/mimiwork/releases/latest/download/MimiWork-macos-arm64.dmg) | Drag to Applications, then **right-click → Open** once |
| **Mac — Intel** | [**MimiWork-macos-x64.dmg**](https://github.com/lanceyuu/mimiwork/releases/latest/download/MimiWork-macos-x64.dmg) | Drag to Applications, then **right-click → Open** once |
| **Windows 10/11** | [**MimiWork-windows-setup.exe**](https://github.com/lanceyuu/mimiwork/releases/latest/download/MimiWork-windows-setup.exe) · [.msi](https://github.com/lanceyuu/mimiwork/releases/latest/download/MimiWork-windows.msi) | Run it; SmartScreen → **More info → Run anyway** |

Builds aren't code-signed yet — that's the one-time prompt on each OS. Every release, with
checksums and older versions, is on the [Releases page](https://github.com/lanceyuu/mimiwork/releases).

### First five minutes

1. **Pick a model** — paste a key, or sign in with QualiTaTi.
2. **Give it a folder.** Nothing outside the folders you grant is readable.
3. **Ask for an outcome**, not a task list: *"Read these interview transcripts and write me
   a themed summary as a Word doc."*
4. **Press `/`** to see what else it can do, and `@` to point at a specific file.

## Privacy

MimiWork is **fully local**: the agent loop, your conversations, connector tokens and model
keys all live on your machine. **There is no vendor cloud in the loop** — no hosted sign-in,
no OAuth broker, no relay. Connectors use your own credentials (or a vendor's own local
OAuth); your data leaves the machine only through the model and integrations you choose.

## Quality

The test suite is part of the product: **1,507 backend tests** cover the agent engine,
tools and connectors — including that every Office tool registers a schema a real provider
accepts, that code execution is approval-gated like the shell, and that a scanned PDF is
flagged rather than silently summarised from nothing. The desktop app carries **230 GUI unit
tests** and **150 hermetic Playwright e2e tests** (mocked backend, no network), with a
separate live suite for the real thing. `ruff` and `eslint` gate CI alongside them.

## Build from source

```text
┌────────────────────────────────────────────────┐
│               MimiWork desktop app             │  native shell + GUI (Tauri + React)
├────────────────────────────────────────────────┤
│           local agent server (Python)          │  engine · tools · connectors
├───────────────┬────────────────┬───────────────┤
│  your files   │   your tools   │  your model   │  everything runs with your keys,
│  & terminal   │ 25+ connectors │  any provider │  on your machine
└───────────────┴────────────────┴───────────────┘
```

Prerequisites: Python 3.10+, Node 20+, Rust via [rustup](https://rustup.rs/), and `cmake`
(`brew install cmake`).

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

For the full desktop app, replace step 3 with `npm run tauri dev`; build an installable DMG
with `packaging/build_dmg.sh`.

| Directory | What's in it |
|---|---|
| `coworker/` | Python backend — agent engine, model providers, office/PDF/image/analysis tools, connectors, MCP client, automations |
| `surfaces/gui/` | Desktop app — React UI + Tauri shell |
| `stt/` | Speech-to-text sidecar (Rust) for voice input |
| `packaging/` | Installer builds (macOS DMG, Windows), dev bootstrap |
| `docs/` | Design specs and decision logs |
| `tests/` | Backend test suite |

## Acknowledgements

MimiWork is a fork of [OpenWorker](https://github.com/andrewyng/openworker) by Andrew Ng and
contributors, built on [aisuite](https://github.com/andrewyng/aisuite). The repetition-guard
detection (stopping a looping model before it burns your credits) and the steer-while-running
interaction are adapted from ideas in
[FrontierAgent](https://github.com/ApodexAI/FrontierAgent) by Apodex AI (Apache-2.0). This fork
repositions the tool for knowledge work — Office deliverables, PDF and image handling, and a
statistics-aware data-analysis toolchain — and carries its own desktop refinements. Internal
binary and package names (`coworker`, `openworker-server`) keep their upstream names for
compatibility.

## License

MIT — see [LICENSE](LICENSE). Original work © 2024 Andrew Ng; modifications © 2026 MimiWork
contributors.
