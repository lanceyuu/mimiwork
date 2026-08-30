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

## Why it feels different

**Actually agentic.** Not a chat window with tools bolted on: Mimi plans the work,
reads the files, runs the analysis, checks its own layout, and iterates until the file is
finished — dozens of steps from one ask. **Plan mode** shows you the whole approach before
anything runs.

**It learns as you work.** Memory keeps what it noticed about your projects. Skills
package your know-how once — brand rules, methods, house style — and apply forever.
Instructions set standing rules per folder. Week two is visibly better than week one, and
everything it learned is yours to read, edit, or delete.

**Steerable while it works.** See it heading the wrong way? Just type. Your correction
lands at the next safe step without restarting the work — and a looping model is stopped
before it burns your credits.

**It runs while you don't.** Say "every Monday at 8…" in plain words and it becomes a
local automation with a full transcript; anything needing a decision waits in your Inbox
instead of guessing.

**Yours, on your machine.** No vendor cloud, your model keys, every consequential
action approval-gated, and nothing outside the folders you grant is readable.

## What it actually does

**One coworker, three trades.** There is no mode to pick — Mimi carries all of this
into every conversation and reaches for the right craft when the work calls for it.

| | What it produces |
|---|---|
| **Data analysis** | Profiles the dataset before touching it — SPSS/Stata *variable and value labels* included, so `q4_1` becomes "Satisfaction with onboarding, 1–5" — runs the analysis in a persistent Python kernel or R, and reports sample sizes, effect sizes and assumption checks, not just p-values. |
| **Documents** | Drafts and revises Word documents **in place** without wrecking your formatting — headings, tables, comments and all — and can leave **real tracked changes** with a plain-language "what I changed and why". |
| **Decks** | Turns findings into a **16:9 PowerPoint that argues a case** — every slide titled with its takeaway, not its topic, and built from a real layout vocabulary (a single claim, a big number, a participant's own words, a side-by-side, a chart) rather than slide after slide of bullets. Charts come from your actual numbers, and speaker notes come with it. Text is measured and fitted so nothing walks out of its frame. Point it at your house template and it uses your brand instead. |

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
run: **US (cheaper credits) or strict-GDPR Paris (data stays in Europe)**. Signing in
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

### The ten-minute tutorial

The one habit that matters most: **ask for the outcome, not the steps.** "Read these
transcripts and write me a themed summary as a Word doc" gets you `summary.docx`. "Can you
help me analyse interviews?" gets you a conversation.
([One page: docs/TUTORIAL.md](docs/TUTORIAL.md) — also in [中文](docs/TUTORIAL.zh.md), [Norsk](docs/TUTORIAL.no.md), [Français](docs/TUTORIAL.fr.md) · [Illustrated PDF, 13 pages: docs/MimiWork-Tutorial.pdf](docs/MimiWork-Tutorial.pdf))

<details>
<summary><b>1 · Connect a model</b> — QualiTaTi credits or your own key (2 minutes)</summary>
<br>

Open **Settings ▸ Models**. Two ways in:

- **Sign in with QualiTaTi** — no keys; the Mimi models spend your existing credits. The
  card shows the three tiers — **Mimi Puppy** (free every day), **Mimi Hound** (fast),
  **Mimi Wolf** (most capable) — each with a **Test** button that makes a real call.
  While you're here: pick your **model region** (*Default · US*, cheaper — or *Strict
  GDPR · Paris*, data stays in Europe), and know that the **Activity** page shows
  exactly what each call cost, from the server's own ledger.
- **Paste your own key** — OpenAI, Anthropic, Gemini, Kimi, DeepSeek, Mistral and more,
  or fully local via Ollama. Switch anytime from the composer.
</details>

<details>
<summary><b>2 · Give it a folder</b> — the one real setup decision</summary>
<br>

Click the folder starter card, or just ask *"work in my Projects/interviews folder"*.
**Nothing outside the folders you grant is readable** — so grant the folder where the
real files live. Click a folder's name under Access to open it in Finder/Explorer.
</details>

<details>
<summary><b>3 · The first real task</b> — and what to expect while it runs</summary>
<br>

> Read the three PDFs in this folder and write a one-page brief as `brief.docx` —
> keep the numbers in a table.

> Turn `results.xlsx` into a 10-slide deck that argues we should fix mobile first.
> Speaker notes for my co-presenter.

While it runs: **anything consequential asks first** (approval cards); **you can steer
without stopping** — type *"use the December wave, not November"* and it lands at the
next safe step; **drop files straight into the chat** — from a granted folder they become
`@mentions` worked on in place, from anywhere else they're copied visibly into the
session's folder. Finished files land in your folder; the **Files** page keeps every
deliverable in one place.
</details>

<details>
<summary><b>4 · Three keys</b> — <code>/</code>, <code>@</code>, <code>⇧⇥</code></summary>
<br>

| Key | What it does |
|---|---|
| **`/`** | App commands (`/plan`, `/compact`, `/init`, `/model`…), your saved commands, your skills |
| **`@`** | Point at a file in a granted folder — no path typing |
| **`⇧⇥`** | Cycle **Plan** → **Ask for approval** → **Full access** |

For anything with stakes, hit `⇧⇥` into **Plan** first: Mimi proposes the whole approach,
you approve or redirect, *then* it runs. Same gestures as Claude Code / Cowork / Codex —
**Settings ▸ Transfer guide** has the full map.
</details>

<details>
<summary><b>5 · Teach it your way — once</b> — instructions, skills, memory</summary>
<br>

- **Instructions** (Settings ▸ Instructions, or `AGENTS.md`/`CLAUDE.md` in the folder):
  standing rules. *"Reports in UK English. Stats always with effect sizes."*
- **Skills** (Settings ▸ Skills): package your brand rules or methods once; every deck
  and doc comes out in them without being asked. Browse **8,400 community skills**, read
  a skill's real instructions before installing, import from `~/.claude/skills`.
- **Memory** (Settings ▸ Memory): what Mimi noticed and kept — review, edit, delete.
</details>

<details>
<summary><b>6 · Connect where you work</b> — Slack, Qualtrics, QualiTaTi data, 25+ more</summary>
<br>

**Settings ▸ Connectors**: Slack (tag Mimi in a channel, work comes back in-thread),
Gmail/Outlook, Calendar, Drive, GitHub, Jira, Notion, Canva — and **Qualtrics**: read a
questionnaire so `Q4_1` becomes a real question, pull responses as CSV or labelled SPSS
`.sav`, with your approval per download. Your QualiTaTi research data works the same way.
Anything else speaks [MCP](https://modelcontextprotocol.io/).
</details>

<details>
<summary><b>7 · Make it run while you don't</b> — automations and the Inbox</summary>
<br>

> Every Monday at 8, read the new files in `field-notes/`, and put a one-page weekly
> summary in `reports/`.

That becomes an **Automation** — local, full transcript, and anything needing a decision
waits in your **Inbox** instead of guessing.
</details>

<details>
<summary><b>8 · A good week, in five asks</b></summary>
<br>

1. *"Work in this folder. Profile every `.sav` in it and give me a data dictionary as a Word doc."*
2. *"Package our brand guidelines into a skill."*
3. *"Turn the wave-2 findings into a 12-slide deck for the steering committee."* (in Plan mode)
4. *"Pull the December survey from Qualtrics as SPSS and test whether satisfaction differs by channel — effect sizes, not just p-values."*
5. *"Every Friday at 4, summarise this Slack channel's week into a memo in `reports/`."*

By Friday: a data dictionary, an on-brand deck, a real analysis, and a standing
automation — every file on your disk, made with your keys, under your approval.
</details>

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
[FrontierAgent](https://github.com/ApodexAI/FrontierAgent) by Apodex AI (Apache-2.0); the
search deduplication and dead-end guidance in the web tools adapt the rollback observers of
[AgentHarness](https://github.com/ApodexAI/AgentHarness) (Apache-2.0) to a desktop where the
user pays per model call. The markdown `/command` files with `$ARGUMENTS` and the plugin-style
tool hooks follow [opencode](https://github.com/sst/opencode)'s conventions, and the `/`, `@`
and Shift+Tab gestures deliberately match Claude Code and Claude Cowork so the muscle memory
transfers. This fork
repositions the tool for knowledge work — Office deliverables, PDF and image handling, and a
statistics-aware data-analysis toolchain — and carries its own desktop refinements. Internal
binary and package names (`coworker`, `openworker-server`) keep their upstream names for
compatibility.

## License

MIT — see [LICENSE](LICENSE). Original work © 2024 Andrew Ng; modifications © 2026 MimiWork
contributors.
