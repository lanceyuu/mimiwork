"""Project context — instruction-file ingestion (root + global) into the system prompt.

Both filenames are honoured, so an instructions file written for another agentic tool
works here unchanged: ``AGENTS.md`` (Codex, this app) and ``CLAUDE.md`` (Claude Code,
Cowork's folder instructions). A folder may carry either or both; both are injected,
``AGENTS.md`` first (owner ask 2026-08-23 — "make this app transferable").
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .secrets import state_dir

# Filenames read at both scopes, in injection order.
INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md")


def default_global_agents_path() -> Path:
    """The file the Settings ▸ Instructions editor writes (Cowork: "Global instructions")."""
    return state_dir() / "AGENTS.md"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_agents_md(
    workspace: str | Path,
    *,
    global_path: Optional[str | Path] = None,
    group_instructions: str = "",
) -> str:
    """Return a system-prompt block from the global and project instruction files.

    Global scope is the state dir (or ``global_path`` when given); project scope is the
    workspace root. Nested discovery is a fast-follow.

    ``group_instructions`` is the standing text on the session's project. A project is a
    group now, not a folder, so its instructions have no file to live in — they come
    from the database and are injected here beside the file-based ones, last, so a
    folder that carries its own AGENTS.md still leads.
    """
    parts: list[tuple[str, str, str]] = []  # (scope label, filename, text)

    g = Path(global_path) if global_path is not None else default_global_agents_path()
    for name in INSTRUCTION_FILES:
        # An explicit global_path names the file itself; the sibling CLAUDE.md counts too.
        candidate = g if (global_path is not None and name == g.name) else g.parent / name
        if candidate.is_file():
            text = _read(candidate)
            if text.strip():
                parts.append(("global", candidate.name, text))

    root = Path(workspace).expanduser().resolve()
    for name in INSTRUCTION_FILES:
        candidate = root / name
        if candidate.is_file():
            text = _read(candidate)
            if text.strip():
                parts.append(("project", name, text))

    if (group_instructions or "").strip():
        parts.append(("project", "group instructions", group_instructions))

    if not parts:
        return ""

    blocks = [
        f"<{label} {name}>\n{text.strip()}\n</{label} {name}>"
        for label, name, text in parts
    ]
    return "Project conventions:\n" + "\n\n".join(blocks)
