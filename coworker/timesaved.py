"""How long the work would have taken by hand, minus how long it took with Mimi.

The number this produces sits in the composer next to the token count and, as a
running total, next to the logo. That placement makes honesty the whole design
problem: a figure a user can disprove from their own memory ("that did NOT save me
four hours") discredits everything else in the interface. So three rules shape the
estimates below.

**Count the artifact, not the tokens.** Tokens measure how much the model read, which
has almost nothing to do with how long a person would have needed. A 200k-token
context might be one glance at a folder. Ten slides with speaker notes is an
afternoon. Every estimate here is keyed to something that actually exists afterwards:
slides written, words drafted, pages read, analyses run, messages sent.

**Round down, always.** Each rate is the FAST end of what the task realistically
takes a competent professional — the fast end, so the claim survives an argument. A
deck slide is costed at 6 minutes when 15 is typical; drafting is costed at 1,000
words an hour when 500–800 is the usual band for finished prose. If the number feels
low to the user, the feature is working.

**Charge for the collaboration honestly.** Time spent waiting on Mimi, writing the
request, reading the answer and approving actions is real time the user spent, so it
comes off the top. When a turn runs long the waiting is capped — past ten minutes
people go and do something else — but it is never zero.

The result is deliberately an ESTIMATE and is always shown as one ("≈"). It is not
billing, it is not a promise, and the breakdown is one click away so anyone can see
exactly which line they disagree with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ── rates, in minutes ────────────────────────────────────────────────────────
# Each is the fast end of a realistic professional pace; see the module docstring.

MIN_PER_PAGE_READ = 1.5  # skim a page and pull out what matters
MIN_PER_100_WORDS_WRITTEN = 6.0  # ≈1,000 words/hour, drafted AND formatted
MIN_PER_DOC_BLOCK = 1.2  # a heading, paragraph or table placed by hand
MIN_PER_EDIT = 2.0  # find the passage, revise it, keep the formatting
MIN_PER_SLIDE = 6.0  # content, layout and speaker notes (15 is typical)
MIN_PER_ANALYSIS = 8.0  # write the code, run it, fix it, read the output
MIN_PER_CHART = 6.0  # build it, label it, make it presentable
MIN_PER_SEARCH = 3.0  # search, open results, decide what's useful
MIN_PER_100_ROWS = 0.4  # spreadsheet rows entered or transformed
MIN_PER_SHEET = 2.0  # a sheet set up with headers and formats
MIN_PER_100_LINES_READ = 0.3  # scanning a file for the relevant part
MIN_PER_CONNECTOR_READ = 2.0  # open the app, find the thing, read it
MIN_PER_CONNECTOR_WRITE = 3.0  # compose it, address it, send it
MIN_PER_SHELL = 1.5  # remember the command, run it, read the output
MIN_PER_FILE_OP = 0.4  # move/copy/rename by hand
# Capability someone would otherwise have had to write out by hand. Only the artifact
# is costed — the re-use it buys later is real but speculative, and this module counts
# what exists, not what might.
# What you learned. Looking a method up in the curated knowledge base replaces
# finding, opening and reading the source — costed like the reading it saves.
MIN_PER_KB_LOOKUP = 4.0
MIN_PER_SKILL = 12.0  # writing the instructions, examples and rules down properly
MIN_PER_AUTOMATION = 5.0  # deciding the schedule, wording the standing task
MIN_PER_INSTRUCTIONS = 5.0  # setting out house rules for a folder

# No single call is worth more than this. A 900-page PDF read is still one action;
# without a ceiling one outlier turn would dwarf a month of real work.
MAX_MINUTES_PER_CALL = 45.0

# ── what the user spends ─────────────────────────────────────────────────────
MIN_PER_TURN_OVERHEAD = 1.5  # writing the request, reading the answer
MIN_PER_APPROVAL = 0.5  # reading a card and deciding
MAX_WAIT_MINUTES_PER_TURN = 10.0  # past this, nobody is still watching


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _len(value: Any) -> int:
    return len(value) if isinstance(value, (list, tuple)) else 0


def _words_in_blocks(blocks: Any) -> int:
    """Words the model actually wrote into a document, counted from the blocks it
    passed — not from the file, which may already have held most of them."""
    total = 0
    for block in blocks if isinstance(blocks, list) else []:
        if isinstance(block, dict):
            for key in ("text", "content", "caption"):
                if isinstance(block.get(key), str):
                    total += len(block[key].split())
            rows = block.get("rows")
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, (list, tuple)):
                        total += sum(len(str(c).split()) for c in row)
        elif isinstance(block, str):
            total += len(block.split())
    return total


def _slide_words(slides: Any) -> int:
    total = 0
    for slide in slides if isinstance(slides, list) else []:
        if not isinstance(slide, dict):
            continue
        for key in ("title", "subtitle", "statement", "quote", "notes", "caption"):
            if isinstance(slide.get(key), str):
                total += len(slide[key].split())
        for key in ("bullets", "stats", "columns"):
            total += _words_in_blocks(slide.get(key))
    return total


def estimate_call(tool: str, args: Optional[dict], result: Any) -> tuple[str, float]:
    """(category, human minutes) for one completed tool call.

    Unknown tools cost nothing. Silence is the honest default: a tool whose work
    nobody has costed should not quietly inflate the number.
    """
    args = args if isinstance(args, dict) else {}
    res = result if isinstance(result, dict) else {}
    name = tool or ""

    # ── documents ──
    if name == "write_document":
        blocks = args.get("blocks")
        minutes = _len(blocks) * MIN_PER_DOC_BLOCK + (
            _words_in_blocks(blocks) / 100.0
        ) * MIN_PER_100_WORDS_WRITTEN
        return "Documents", minutes
    if name == "edit_document":
        return "Documents", max(_len(args.get("edits")), 1) * MIN_PER_EDIT
    if name in ("read_document", "read_pdf"):
        pages = _num(res.get("pages") or res.get("total_pages"))
        blocks = _num(res.get("total_blocks"))
        units = pages or (blocks / 6.0)  # ≈6 blocks reads like a page
        return "Reading", max(units, 1.0) * MIN_PER_PAGE_READ

    # ── decks ──
    if name == "write_presentation":
        slides = args.get("slides")
        count = _num(res.get("slides_written")) or _len(slides)
        minutes = count * MIN_PER_SLIDE + (
            _slide_words(slides) / 100.0
        ) * MIN_PER_100_WORDS_WRITTEN
        return "Decks", minutes
    if name == "read_presentation":
        return "Reading", max(_num(res.get("total_slides")), 1.0) * 0.8

    # ── spreadsheets ──
    if name in ("write_workbook", "append_rows", "update_cells"):
        rows = _len(args.get("rows"))
        for sheet in args.get("sheets") or []:
            if isinstance(sheet, dict):
                rows += _len(sheet.get("rows"))
        sheets = max(_len(args.get("sheets")), 1)
        return "Spreadsheets", sheets * MIN_PER_SHEET + (rows / 100.0) * MIN_PER_100_ROWS
    if name in ("read_workbook", "inspect_data"):
        return "Reading", 3.0  # opening a dataset and working out what's in it

    # ── analysis ──
    if name in ("run_python", "run_r", "python_analysis", "r_analysis"):
        code = str(args.get("code") or "")
        blocks = max(1.0, code.count("\n") / 25.0)  # ≈25 lines per coherent step
        charts = code.count("savefig") + code.count("ggsave")
        return "Analysis", blocks * MIN_PER_ANALYSIS + charts * MIN_PER_CHART

    # ── web ──
    if name in ("web_search", "browser_read_url", "web_fetch"):
        return "Research", MIN_PER_SEARCH

    # ── files and shell ──
    if name in ("read_file", "read_lines"):
        lines = _num(res.get("total_lines"))
        return "Reading", min(max(lines, 40.0) / 100.0 * MIN_PER_100_LINES_READ, 6.0)
    if name in ("write_file", "edit_file", "create_file"):
        return "Files", MIN_PER_FILE_OP + (
            len(str(args.get("content") or "").split()) / 100.0
        ) * MIN_PER_100_WORDS_WRITTEN
    if name in ("move_file", "copy_file", "delete_file", "make_directory", "list_dir"):
        return "Files", MIN_PER_FILE_OP
    if name in ("run_shell", "shell", "bash"):
        return "Files", MIN_PER_SHELL

    # ── connectors (slack_send_message, gmail_search, qualtrics_export_responses, …) ──
    # ── learning ──
    # The Empowerment pillar is "you learned something" (see edge.py). Looking a
    # method up in the knowledge base is exactly that; without this it fell through
    # to the generic `*_search` rule below and read as a connector fetch.
    if name in ("kb_search", "kb_read", "kb_list"):
        return "Learning", MIN_PER_KB_LOOKUP

    # ── capability built to last ──
    # Also Empowerment: what you learned, made permanent.
    if name == "save_skill":
        return "Capability", MIN_PER_SKILL
    if name in ("create_scheduled_task", "update_scheduled_task"):
        return "Capability", MIN_PER_AUTOMATION
    if name in ("set_global_instructions", "write_instructions", "init_agents"):
        return "Capability", MIN_PER_INSTRUCTIONS

    if "_" in name:
        verb = name.split("_", 1)[1]
        if verb.startswith(("send", "post", "create", "update", "reply", "export", "add")):
            return "Connectors", MIN_PER_CONNECTOR_WRITE
        if verb.startswith(("search", "list", "get", "read", "fetch")):
            return "Connectors", MIN_PER_CONNECTOR_READ

    return "", 0.0


@dataclass
class TimeSaved:
    """Running totals for one session (and, merged, for the whole install)."""

    human_minutes: float = 0.0
    collab_minutes: float = 0.0
    turns: int = 0
    approvals: int = 0
    by_category: dict[str, float] = field(default_factory=dict)
    # Minutes per TOOL, not per category. The install-wide novelty test behind the
    # Growth pillar (see `manager.record_time_saved`) needs to know which tool the
    # minutes came from — a category cannot say whether you had ever reached for
    # `write_presentation` before this week.
    by_tool: dict[str, float] = field(default_factory=dict)
    # Which pillar-bearing category each tool's minutes landed in, so the novelty
    # test can MOVE those minutes rather than guess where they came from.
    tool_categories: dict[str, str] = field(default_factory=dict)

    def add_call(self, tool: str, args: Optional[dict], result: Any) -> float:
        category, minutes = estimate_call(tool, args, result)
        if not category or minutes <= 0:
            return 0.0
        minutes = min(minutes, MAX_MINUTES_PER_CALL)
        self.human_minutes += minutes
        self.by_category[category] = self.by_category.get(category, 0.0) + minutes
        if tool:
            self.by_tool[tool] = self.by_tool.get(tool, 0.0) + minutes
            self.tool_categories[tool] = category
        return minutes

    def tool_category(self, tool: str) -> str:
        """The category this tool's minutes were filed under, or "" if unknown."""
        return self.tool_categories.get(tool, "")

    def add_turn(self, wall_seconds: float, approvals: int = 0) -> None:
        self.turns += 1
        self.approvals += max(0, approvals)
        waiting = min(max(wall_seconds, 0.0) / 60.0, MAX_WAIT_MINUTES_PER_TURN)
        self.collab_minutes += (
            MIN_PER_TURN_OVERHEAD + waiting + max(0, approvals) * MIN_PER_APPROVAL
        )

    @property
    def saved_minutes(self) -> float:
        """Never negative: a turn where Mimi cost more than it saved is a wash, not a
        debt. Showing "-4 minutes saved" would be true arithmetic and useless UI."""
        return max(0.0, self.human_minutes - self.collab_minutes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "saved_minutes": round(self.saved_minutes, 1),
            "human_minutes": round(self.human_minutes, 1),
            "collab_minutes": round(self.collab_minutes, 1),
            "turns": self.turns,
            "approvals": self.approvals,
            "by_category": {k: round(v, 1) for k, v in sorted(self.by_category.items())},
            "by_tool": {k: round(v, 1) for k, v in sorted(self.by_tool.items())},
            "tool_categories": dict(sorted(self.tool_categories.items())),
        }

    @classmethod
    def from_dict(cls, data: Any) -> "TimeSaved":
        d = data if isinstance(data, dict) else {}
        cats = d.get("by_category")
        tools = d.get("by_tool")
        tool_cats = d.get("tool_categories")
        return cls(
            human_minutes=_num(d.get("human_minutes")),
            collab_minutes=_num(d.get("collab_minutes")),
            turns=int(_num(d.get("turns"))),
            approvals=int(_num(d.get("approvals"))),
            by_category={
                str(k): _num(v) for k, v in (cats.items() if isinstance(cats, dict) else [])
            },
            by_tool={
                str(k): _num(v)
                for k, v in (tools.items() if isinstance(tools, dict) else [])
            },
            tool_categories={
                str(k): str(v)
                for k, v in (tool_cats.items() if isinstance(tool_cats, dict) else [])
            },
        )

    def merge(self, other: "TimeSaved") -> None:
        self.human_minutes += other.human_minutes
        self.collab_minutes += other.collab_minutes
        self.turns += other.turns
        self.approvals += other.approvals
        for k, v in other.by_category.items():
            self.by_category[k] = self.by_category.get(k, 0.0) + v
        for k, v in other.by_tool.items():
            self.by_tool[k] = self.by_tool.get(k, 0.0) + v
        self.tool_categories.update(other.tool_categories)
