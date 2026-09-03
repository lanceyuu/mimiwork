"""Who MimiWork stands on — one list, rendered two ways.

The About page in the app and CREDITS.md in the repo both read from here, so a new
dependency, a vendored skill or a borrowed idea is credited once and shows up in both
(owner rule 2026-09-03: always credit the projects we learn from and the skills we use).
``scripts/build_credits_md.py`` regenerates the file; a test keeps the two in step.
"""

from __future__ import annotations

from typing import Any

# Each section: title, a one-line blurb, and items {name, what, url, license?}.
# Licenses are stated only where the source states them.
CREDITS: list[dict[str, Any]] = [
    {
        "title": "Where it comes from",
        "blurb": "MimiWork is a fork, and says so.",
        "items": [
            {
                "name": "OpenWorker",
                "what": "The desktop coworker MimiWork is forked from: the turn engine, the tool "
                "registry, the permission model, the Tauri shell. Andrew Ng and contributors.",
                "url": "https://github.com/andrewyng/openworker",
                "license": "MIT",
            },
            {
                "name": "aisuite",
                "what": "The provider-agnostic model interface every turn goes through. Andrew Ng.",
                "url": "https://github.com/andrewyng/aisuite",
                "license": "MIT",
            },
            {
                "name": "GenAI for Business (Shubin Yu, 2026)",
                "what": "The Five A's continuum and the EDGE profile the app measures itself "
                "against — chapter 7's operational test, adapted from products to turns.",
                "url": "https://qualitati.com",
            },
        ],
    },
    {
        "title": "Ideas borrowed",
        "blurb": "Patterns taken from other projects, with what we took.",
        "items": [
            {
                "name": "FrontierAgent",
                "what": "The repetition guard that stops a looping model before it spends "
                "your credits, and steering a run while it works. Apodex AI.",
                "url": "https://github.com/ApodexAI/FrontierAgent",
                "license": "Apache-2.0",
            },
            {
                "name": "AgentHarness",
                "what": "Search deduplication and dead-end guidance in the web tools, from its "
                "rollback observers. Apodex AI.",
                "url": "https://github.com/ApodexAI/AgentHarness",
                "license": "Apache-2.0",
            },
            {
                "name": "opencode",
                "what": "Markdown /command files with $ARGUMENTS, and plugin-style tool hooks.",
                "url": "https://github.com/sst/opencode",
            },
            {
                "name": "Claude Code and Claude Cowork",
                "what": "The /, @ and Shift+Tab gestures and the permission vocabulary, matched "
                "on purpose so the muscle memory transfers. Anthropic.",
                "url": "https://claude.com/claude-code",
            },
            {
                "name": "OpenClaude",
                "what": "The workspace map at session start, mission control, session forking "
                "and the onboarding starter cards, from the Gitlawb/openclaude survey.",
                "url": "https://github.com/Gitlawb/openclaude",
            },
            {
                "name": "Hermes agent",
                "what": "The messaging adapter contract behind the Slack and Telegram "
                "connectors follows its gateway.",
                "url": "https://github.com/NousResearch/hermes-agent",
            },
            {
                "name": "Coze Studio",
                "what": "For Apps: building beside a live preview, versions with rollback, a "
                "template gallery, an opening line with suggested actions, and a log of model "
                "calls. ByteDance.",
                "url": "https://github.com/coze-dev/coze-studio",
                "license": "Apache-2.0",
            },
            {
                "name": "Poe canvas apps",
                "what": "The shape of an app: one HTML page in a frame plus one call that "
                "reaches a model. Quora.",
                "url": "https://creator.poe.com/docs/canvas-apps/canvas-app-quick-start",
            },
            {
                "name": "n8n",
                "what": "The flow diagram's vocabulary — a main chain with dashed sub-nodes "
                "hanging off the agent — because that is the picture this audience already reads.",
                "url": "https://n8n.io",
            },
            {
                "name": "Obsidian",
                "what": "The memory graph: notes as dots, tags and folders as hubs, [[links]] as edges.",
                "url": "https://obsidian.md",
            },
            {
                "name": "Codex",
                "what": "The per-folder session accordion in the sidebar. OpenAI.",
                "url": "https://github.com/openai/codex",
            },
        ],
    },
    {
        "title": "Bundled skills",
        "blurb": "Skills that ship with the app. Each keeps its own license and vendor note in its folder.",
        "items": [
            {
                "name": "UI/UX Pro Max",
                "what": "Design intelligence — styles, palettes, type pairings, UX rules and "
                "stacks — behind interface work. Next Level Builder.",
                "url": "https://github.com/nextlevelbuilder/ui-ux-pro-max-skill",
                "license": "MIT",
            },
            {
                "name": "PPT Master",
                "what": "The routed presentation workflow and its icon library. hugohe3.",
                "url": "https://github.com/hugohe3/ppt-master",
                "license": "MIT",
            },
            {
                "name": "Ponytail",
                "what": "The least code that works — and its review counterpart. DietrichGebert.",
                "url": "https://github.com/DietrichGebert/ponytail",
                "license": "MIT",
            },
            {
                "name": "apple-design",
                "what": "The interaction polish layer: press feedback, one shared ease, "
                "translucent materials. Emil Kowalski.",
                "url": "https://github.com/emilkowalski/skills",
            },
            {
                "name": "survey-generator",
                "what": "From dair-ai's academy plugins.",
                "url": "https://github.com/dair-ai/dair-academy-plugins",
                "license": "MIT",
            },
            {
                "name": "deep-research",
                "what": "From imbad0202's academic research skills.",
                "url": "https://github.com/imbad0202/academic-research-skills",
            },
            {
                "name": "avoid-ai-writing",
                "what": "Conor Bronsdon's guide to prose that does not read as generated.",
                "url": "https://github.com/sickn33/agentic-awesome-skills",
            },
            {
                "name": "Community picks",
                "what": "file-organizer, invoice-organizer, meeting-insights-analyzer, "
                "internal-comms, content-research-writer, tailored-resume-generator and "
                "lead-research-assistant from ComposioHQ's collection; idea-refine and "
                "planning-and-task-breakdown from Addy Osmani's; data-storytelling from "
                "sickn33's. Curated and safety-scanned before bundling.",
                "url": "https://github.com/ComposioHQ/awesome-claude-skills",
            },
        ],
    },
    {
        "title": "The skill store's index",
        "blurb": "The store searches a bundled index built over these collections; a skill downloads only when you install it.",
        "items": [
            {"name": "sickn33/agentic-awesome-skills", "what": "", "url": "https://github.com/sickn33/agentic-awesome-skills"},
            {"name": "ComposioHQ/awesome-claude-skills", "what": "", "url": "https://github.com/ComposioHQ/awesome-claude-skills"},
            {"name": "addyosmani/agent-skills", "what": "", "url": "https://github.com/addyosmani/agent-skills"},
            {"name": "brycewang-stanford/Auto-Empirical-Research-Skills", "what": "", "url": "https://github.com/brycewang-stanford/Auto-Empirical-Research-Skills"},
            {"name": "VoltAgent/awesome-agent-skills", "what": "", "url": "https://github.com/VoltAgent/awesome-agent-skills"},
            {"name": "imbad0202/academic-research-skills", "what": "", "url": "https://github.com/imbad0202/academic-research-skills"},
        ],
    },
    {
        "title": "Libraries",
        "blurb": "Open source the app is built with. Each project's license applies to it.",
        "items": [
            {"name": "Tauri", "what": "The desktop shell, its updater, dialogs, tray and opener plugins.", "url": "https://tauri.app"},
            {"name": "React and Vite", "what": "The interface and its build.", "url": "https://react.dev"},
            {"name": "FastAPI and Uvicorn", "what": "The sidecar's HTTP and websocket surface.", "url": "https://fastapi.tiangolo.com"},
            {"name": "pdf.js", "what": "PDF preview in the artifact rail. Mozilla.", "url": "https://mozilla.github.io/pdf.js/"},
            {"name": "SheetJS", "what": "Spreadsheet preview.", "url": "https://sheetjs.com"},
            {"name": "html2canvas", "what": "The screenshot that travels with pinned comments. Niklas von Hertzen.", "url": "https://html2canvas.hertzen.com"},
            {"name": "react-markdown and remark-gfm", "what": "Markdown rendering in the transcript.", "url": "https://github.com/remarkjs/react-markdown"},
            {"name": "Simple Icons", "what": "Brand icons on the connector cards.", "url": "https://simpleicons.org"},
            {"name": "python-docx and python-pptx", "what": "Reading and writing Word and PowerPoint, including the previews and Word comments.", "url": "https://github.com/python-openxml/python-docx"},
            {"name": "pypdf and pypdfium2", "what": "PDF reading and rendering in the sidecar.", "url": "https://github.com/py-pdf/pypdf"},
            {"name": "Playwright", "what": "The browser automation tools, and the app's own end-to-end tests. Microsoft.", "url": "https://playwright.dev"},
            {"name": "OpenAI, Anthropic and Google Gen AI SDKs", "what": "The provider clients.", "url": "https://github.com/openai/openai-python"},
            {"name": "MCP Python SDK", "what": "Model Context Protocol servers as tools.", "url": "https://github.com/modelcontextprotocol/python-sdk"},
            {"name": "DDGS", "what": "The keyless default web search.", "url": "https://github.com/deedy5/ddgs"},
            {"name": "croniter", "what": "Next-run arithmetic for automations.", "url": "https://github.com/kiorky/croniter"},
            {"name": "Textual", "what": "The terminal interface.", "url": "https://textual.textualize.io"},
            {"name": "Pydantic and httpx", "what": "Validation and outbound HTTP.", "url": "https://docs.pydantic.dev"},
        ],
    },
]


def credits() -> list[dict[str, Any]]:
    """The sections, as the About page receives them."""
    return CREDITS


def render_markdown() -> str:
    """CREDITS.md — the same list for readers of the repository."""
    out = [
        "# Credits",
        "",
        "MimiWork stands on other people's work. This file names whose, and what we took;",
        "the same list is in the app under Settings → About. It is generated from",
        "`coworker/credits.py` by `scripts/build_credits_md.py` — edit there, not here.",
        "",
    ]
    for section in CREDITS:
        out.append(f"## {section['title']}")
        out.append("")
        if section.get("blurb"):
            out.append(section["blurb"])
            out.append("")
        for item in section["items"]:
            name = f"[{item['name']}]({item['url']})" if item.get("url") else item["name"]
            tail = f" ({item['license']})" if item.get("license") else ""
            what = f" — {item['what']}" if item.get("what") else ""
            out.append(f"- **{name}**{tail}{what}")
        out.append("")
    out.append("MimiWork itself is MIT — see [LICENSE](LICENSE). Original work © 2024 Andrew Ng;")
    out.append("modifications © 2026 QualiTaTi.")
    out.append("")
    return "\n".join(out)
