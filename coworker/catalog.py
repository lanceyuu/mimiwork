"""Vetted tool catalog — the stable ``id → capability`` layer a persona references.

A *capability* bundles a group of tools (the existing ``tools/`` factories) behind a stable
id, plus what session context it needs (``requires``) and the risk classes it can produce
(``risk``, used by the Phase 2 install-consent screen). ``expand(ids, context)`` turns a
persona's ``tools:`` list into concrete callables, skipping capabilities whose context
prerequisites aren't met (e.g. no shell without an executor) — matching the per-agent
factories that used to assemble tools by hand.

The catalog is **platform-owned and closed**: third parties get breadth from us adding
vetted capabilities here and from MCP, never by adding entries. MCP tools are *not* in the
catalog (see ``PERMISSIONS-AND-INBOX.md``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import aisuite as ai

from .agents.base import AgentContext
from .risk import RiskClass
from .tools.files import file_tools
from .tools.git import git_tools
from .tools.office.docx_tools import docx_tools
from .tools.office.image_tools import image_tools
from .tools.office.pdf_tools import pdf_tools
from .tools.office.pptx_tools import pptx_tools
from .tools.office.xlsx_tools import xlsx_tools
from .tools.search import search_tools
from .tools.shell import shell_tools
from .tools.todo import todo_tools

# Context prerequisites a capability may require, mapped to a predicate over AgentContext.
_REQUIREMENTS: dict[str, Callable[[AgentContext], bool]] = {
    "workspace": lambda c: c.workspace is not None,
    "executor": lambda c: c.executor is not None,
    "todo": lambda c: c.todo is not None,
}


@dataclass(frozen=True)
class Capability:
    id: str
    name: str  # human label (consent screen)
    description: str
    build: Callable[[AgentContext], list]
    requires: tuple[str, ...] = ()
    risk: tuple[RiskClass, ...] = (RiskClass.READ,)

    def available(self, context: AgentContext) -> bool:
        return all(_REQUIREMENTS[r](context) for r in self.requires)


# -- capability builders --------------------------------------------------------
# These reproduce, exactly, what the Code and Cowork agent factories assembled by hand.


def _code_files(context: AgentContext) -> list:
    """Repo-oriented files: single-root, line-numbered/windowed `read_file`. Our `grep` and
    windowed `read_file` replace aisuite's slower `search_files` / `read_file`/`read_file_lines`.
    """
    ws = str(context.workspace)
    replaced = {"search_files", "read_file", "read_file_lines"}
    files = [
        t
        for t in ai.toolkits.files(root=ws, allow_write=True)
        if getattr(t, "__name__", "") not in replaced
    ]
    return [*files, *file_tools(ws)]


def _files(context: AgentContext) -> list:
    """Knowledge-work files: multi-root aware (reads/writes across the session's roots), keeps
    aisuite's `read_file`/`read_file_lines`. Only our `grep` replaces the slow `search_files`.
    """
    ws = str(context.workspace)
    file_kwargs = (
        {"roots": context.roots} if context.roots else {"root": ws, "allow_write": True}
    )
    return [
        t
        for t in ai.toolkits.files(**file_kwargs)
        if getattr(t, "__name__", "") != "search_files"
    ]


def _git(context: AgentContext) -> list:
    ws = str(context.workspace)
    return [*ai.toolkits.git(root=ws), *git_tools(ws)]  # git_status, git_diff, git_log


def _search(context: AgentContext) -> list:
    return search_tools(str(context.workspace))  # grep (ripgrep, .gitignore-aware)


def _shell(context: AgentContext) -> list:
    return shell_tools(context.executor)  # run_shell + background task tools


def _todo(context: AgentContext) -> list:
    return todo_tools(context.todo)  # todo_write (drives the Progress panel)


# -- knowledge-work capabilities -------------------------------------------------
# Office and analysis tools resolve paths against the session's roots (multi-root aware),
# so they take the whole context rather than a single workspace string.


def _documents(context: AgentContext) -> list:
    return docx_tools(context)  # read/write/edit .docx


def _spreadsheets(context: AgentContext) -> list:
    return xlsx_tools(context)  # read/write/edit .xlsx


def _slides(context: AgentContext) -> list:
    return pptx_tools(context)  # read/write .pptx


def _pdf(context: AgentContext) -> list:
    return pdf_tools(context)  # read_pdf (text + tables, scanned-document detection)


def _images(context: AgentContext) -> list:
    return image_tools(context)  # inspect/edit/annotate/combine


def _python_analysis(context: AgentContext) -> list:
    from .tools.analysis.python_tool import python_tools

    return python_tools(context)  # run_python + reset_python (persistent kernel)


def _data_inspect(context: AgentContext) -> list:
    from .tools.analysis.data_tools import data_tools

    return data_tools(context)  # inspect_data (CSV/Excel/SPSS/Stata/Parquet)


def _r_analysis(context: AgentContext) -> list:
    from .tools.analysis.r_tools import r_tools

    return r_tools(context)  # run_r (Rscript)


_CAPS: list[Capability] = [
    Capability(
        id="code_files",
        name="Code files",
        description="Read & edit files in a single repo workspace (line-numbered reads).",
        build=_code_files,
        requires=("workspace",),
        risk=(RiskClass.READ, RiskClass.WRITE_LOCAL),
    ),
    Capability(
        id="files",
        name="Files",
        description="Read & edit files across the session's workspace folders.",
        build=_files,
        requires=("workspace",),
        risk=(RiskClass.READ, RiskClass.WRITE_LOCAL),
    ),
    Capability(
        id="git",
        name="Git",
        description="Inspect git state and history (status, diff, log).",
        build=_git,
        requires=("workspace",),
        risk=(RiskClass.READ,),
    ),
    Capability(
        id="search",
        name="Search",
        description="Fast code/content search (grep).",
        build=_search,
        requires=("workspace",),
        risk=(RiskClass.READ,),
    ),
    Capability(
        id="shell",
        name="Shell",
        description="Run shell commands in a persistent session.",
        build=_shell,
        requires=("executor",),
        risk=(RiskClass.EXEC,),
    ),
    Capability(
        id="todo",
        name="Task list",
        description="Maintain a visible task/progress list.",
        build=_todo,
        requires=("todo",),
        risk=(RiskClass.READ,),
    ),
    Capability(
        id="documents",
        name="Word documents",
        description="Read, write, and edit Word (.docx) documents.",
        build=_documents,
        requires=("workspace",),
        risk=(RiskClass.READ, RiskClass.WRITE_LOCAL),
    ),
    Capability(
        id="spreadsheets",
        name="Excel workbooks",
        description="Read, write, and edit Excel (.xlsx) workbooks.",
        build=_spreadsheets,
        requires=("workspace",),
        risk=(RiskClass.READ, RiskClass.WRITE_LOCAL),
    ),
    Capability(
        id="slides",
        name="PowerPoint decks",
        description="Read and write PowerPoint (.pptx) presentations.",
        build=_slides,
        requires=("workspace",),
        risk=(RiskClass.READ, RiskClass.WRITE_LOCAL),
    ),
    Capability(
        id="pdf",
        name="PDF documents",
        description="Read text and tables out of PDFs (and detect scanned ones).",
        build=_pdf,
        requires=("workspace",),
        risk=(RiskClass.READ,),
    ),
    Capability(
        id="images",
        name="Images",
        description=(
            "Inspect, resize, crop, annotate, and combine images — charts, screenshots, and "
            "figures for documents and decks."
        ),
        build=_images,
        requires=("workspace",),
        risk=(RiskClass.READ, RiskClass.WRITE_LOCAL),
    ),
    Capability(
        id="data_inspect",
        name="Dataset inspection",
        description=(
            "Profile a dataset (CSV, Excel, SPSS, Stata, Parquet) — schema, types, missing "
            "values, summary statistics, and SPSS/Stata variable and value labels."
        ),
        build=_data_inspect,
        requires=("workspace",),
        risk=(RiskClass.READ,),
    ),
    Capability(
        id="python_analysis",
        name="Python analysis",
        description=(
            "Run Python in a persistent session kernel: loaded data and variables survive "
            "between calls, and charts are saved as image files."
        ),
        build=_python_analysis,
        requires=("workspace",),
        # Executing model-written code is the same authority as a shell command, and is gated
        # identically — a permissive classification here would be a privilege-escalation path
        # around the shell's approval prompt.
        risk=(RiskClass.EXEC,),
    ),
    Capability(
        id="r_analysis",
        name="R analysis",
        description="Run R scripts with Rscript (for models and tests R does best).",
        build=_r_analysis,
        requires=("workspace",),
        risk=(RiskClass.EXEC,),
    ),
]

CATALOG: dict[str, Capability] = {c.id: c for c in _CAPS}


def capability(cap_id: str) -> Capability:
    cap = CATALOG.get(cap_id)
    if cap is None:
        raise KeyError(f"Unknown capability id: {cap_id!r}")
    return cap


def expand(ids: list[str], context: AgentContext) -> list:
    """Expand a persona's ``tools:`` id list into concrete tool callables for this context.
    Capabilities whose context prerequisites aren't met are skipped (no shell without an
    executor, no files without a workspace) — exactly like the old hand-written factories.
    """
    tools: list = []
    for cap_id in ids:
        cap = capability(cap_id)
        if cap.available(context):
            tools.extend(cap.build(context))
    return tools


def risk_summary(ids: list[str]) -> set[RiskClass]:
    """The union of risk classes a tool list can produce — for the install-consent screen."""
    out: set[RiskClass] = set()
    for cap_id in ids:
        out.update(capability(cap_id).risk)
    return out
