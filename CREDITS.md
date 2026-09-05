# Credits

MimiWork stands on other people's work. This file names whose, and what we took;
the same list is in the app under Settings → About. It is generated from
`coworker/credits.py` by `scripts/build_credits_md.py` — edit there, not here.

## Where it comes from

MimiWork is a fork, and says so.

- **[OpenWorker](https://github.com/andrewyng/openworker)** (MIT) — The desktop coworker MimiWork is forked from: the turn engine, the tool registry, the permission model, the Tauri shell. Andrew Ng and contributors.
- **[aisuite](https://github.com/andrewyng/aisuite)** (MIT) — The provider-agnostic model interface every turn goes through. Andrew Ng.
- **[GenAI for Business (Shubin Yu, 2026)](https://qualitati.com)** — The Five A's continuum and the EDGE profile the app measures itself against — chapter 7's operational test, adapted from products to turns.

## Ideas borrowed

Patterns taken from other projects, with what we took.

- **[FrontierAgent](https://github.com/ApodexAI/FrontierAgent)** (Apache-2.0) — The repetition guard that stops a looping model before it spends your credits, and steering a run while it works. Apodex AI.
- **[AgentHarness](https://github.com/ApodexAI/AgentHarness)** (Apache-2.0) — Search deduplication and dead-end guidance in the web tools, from its rollback observers. Apodex AI.
- **[opencode](https://github.com/sst/opencode)** — Markdown /command files with $ARGUMENTS, and plugin-style tool hooks.
- **[Claude Code and Claude Cowork](https://claude.com/claude-code)** — The /, @ and Shift+Tab gestures and the permission vocabulary, matched on purpose so the muscle memory transfers. Anthropic.
- **[OpenClaude](https://github.com/Gitlawb/openclaude)** — The workspace map at session start, mission control, session forking and the onboarding starter cards, from the Gitlawb/openclaude survey.
- **[Hermes agent](https://github.com/NousResearch/hermes-agent)** — The messaging adapter contract behind the Slack and Telegram connectors follows its gateway.
- **[Coze Studio](https://github.com/coze-dev/coze-studio)** (Apache-2.0) — For Apps: building beside a live preview, versions with rollback, a template gallery, an opening line with suggested actions, and a log of model calls. ByteDance.
- **[Poe canvas apps](https://creator.poe.com/docs/canvas-apps/canvas-app-quick-start)** — The shape of an app: one HTML page in a frame plus one call that reaches a model. Quora.
- **[n8n](https://n8n.io)** — The flow diagram's vocabulary — a main chain with dashed sub-nodes hanging off the agent — because that is the picture this audience already reads.
- **[Obsidian](https://obsidian.md)** — The memory graph: notes as dots, tags and folders as hubs, [[links]] as edges.
- **[Codex](https://github.com/openai/codex)** — The per-folder session accordion in the sidebar. OpenAI.

## Bundled skills

Skills that ship with the app. Each keeps its own license and vendor note in its folder.

- **[UI/UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)** (MIT) — Design intelligence — styles, palettes, type pairings, UX rules and stacks — behind interface work. Next Level Builder.
- **[PPT Master](https://github.com/hugohe3/ppt-master)** (MIT) — The routed presentation workflow and its icon library. hugohe3.
- **[Ponytail](https://github.com/DietrichGebert/ponytail)** (MIT) — The least code that works — and its review counterpart. DietrichGebert.
- **[apple-design](https://github.com/emilkowalski/skills)** — The interaction polish layer: press feedback, one shared ease, translucent materials. Emil Kowalski.
- **[survey-generator](https://github.com/dair-ai/dair-academy-plugins)** (MIT) — From dair-ai's academy plugins.
- **[deep-research](https://github.com/imbad0202/academic-research-skills)** — From imbad0202's academic research skills.
- **[avoid-ai-writing](https://github.com/sickn33/agentic-awesome-skills)** — Conor Bronsdon's guide to prose that does not read as generated.
- **[Community picks](https://github.com/ComposioHQ/awesome-claude-skills)** — file-organizer, invoice-organizer, meeting-insights-analyzer, internal-comms, content-research-writer, tailored-resume-generator and lead-research-assistant from ComposioHQ's collection; idea-refine and planning-and-task-breakdown from Addy Osmani's; data-storytelling from sickn33's. Curated and safety-scanned before bundling.

## The skill store's index

The store searches a bundled index built over these collections; a skill downloads only when you install it.

- **[sickn33/agentic-awesome-skills](https://github.com/sickn33/agentic-awesome-skills)**
- **[ComposioHQ/awesome-claude-skills](https://github.com/ComposioHQ/awesome-claude-skills)**
- **[addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)**
- **[brycewang-stanford/Auto-Empirical-Research-Skills](https://github.com/brycewang-stanford/Auto-Empirical-Research-Skills)**
- **[VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills)**
- **[imbad0202/academic-research-skills](https://github.com/imbad0202/academic-research-skills)**

## Libraries

Open source the app is built with. Each project's license applies to it.

- **[Tauri](https://tauri.app)** — The desktop shell, its updater, dialogs, tray and opener plugins.
- **[React and Vite](https://react.dev)** — The interface and its build.
- **[FastAPI and Uvicorn](https://fastapi.tiangolo.com)** — The sidecar's HTTP and websocket surface.
- **[pdf.js](https://mozilla.github.io/pdf.js/)** — PDF preview in the artifact rail. Mozilla.
- **[SheetJS](https://sheetjs.com)** — Spreadsheet preview.
- **[html2canvas](https://html2canvas.hertzen.com)** — The screenshot that travels with pinned comments. Niklas von Hertzen.
- **[react-markdown and remark-gfm](https://github.com/remarkjs/react-markdown)** — Markdown rendering in the transcript.
- **[Simple Icons](https://simpleicons.org)** — Brand icons on the connector cards.
- **[python-docx and python-pptx](https://github.com/python-openxml/python-docx)** — Reading and writing Word and PowerPoint, including the previews and Word comments.
- **[pypdf and pypdfium2](https://github.com/py-pdf/pypdf)** — PDF reading and rendering in the sidecar.
- **[Playwright](https://playwright.dev)** — The browser automation tools, and the app's own end-to-end tests. Microsoft.
- **[OpenAI, Anthropic and Google Gen AI SDKs](https://github.com/openai/openai-python)** — The provider clients.
- **[MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)** — Model Context Protocol servers as tools.
- **[Canva Connect API and Canva MCP](https://www.canva.dev/docs/mcp/)** — The Canva connector: one-click sign-in against Canva's own MCP server, and the Connect REST endpoints for the manual path. Canva.
- **[DDGS](https://github.com/deedy5/ddgs)** — The keyless default web search.
- **[croniter](https://github.com/kiorky/croniter)** — Next-run arithmetic for automations.
- **[Textual](https://textual.textualize.io)** — The terminal interface.
- **[Pydantic and httpx](https://docs.pydantic.dev)** — Validation and outbound HTTP.

MimiWork itself is MIT — see [LICENSE](LICENSE). Original work © 2024 Andrew Ng;
modifications © 2026 QualiTaTi.
