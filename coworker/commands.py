"""Custom commands — markdown `/command` files with `$ARGUMENTS` (opencode-style).

A command is a small markdown file (``frontmatter + body``) that turns a short invocation
into a full instruction. It is the opencode ``command.md`` pattern, re-hosted for knowledge
work: a recurring job ("weekly report", "summarize this folder") gets one file the coworker
can be told to run, with ``$ARGUMENTS`` substituted from the invocation.

Command locations (first match wins, later dirs are fallbacks):
  - <workspace>/.coworker/commands/<name>.md      (project-scoped, travels with the work)
  - <state_dir>/commands/<name>.md                 (user-global, works everywhere)

Frontmatter keys: ``name`` (optional; defaults to the file stem), ``description`` (shown in
``list_commands`` so the model knows when to run it), ``model`` (optional per-command model
binding — reserved, not yet enforced). The body is the instruction text; every occurrence of
``$ARGUMENTS`` is replaced with the invocation's argument string verbatim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import aisuite as ai
import yaml

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


class CommandError(ValueError):
    """A command is missing, unparsable, or its frontmatter is invalid."""


@dataclass
class Command:
    name: str
    description: str = ""
    body: str = ""
    path: Optional[Path] = None
    model: str = ""
    raw_frontmatter: dict[str, Any] = field(default_factory=dict)

    def expand(self, arguments: str = "") -> str:
        """The instruction with ``$ARGUMENTS`` substituted (verbatim when empty)."""
        return self.body.replace("$ARGUMENTS", arguments or "")


def parse_command(path: Path, name: Optional[str] = None) -> Command:
    text = path.read_text(encoding="utf-8")
    fm = _FRONTMATTER.match(text)
    if not fm:
        raise CommandError(f"command '{path.stem}' has no frontmatter")
    try:
        meta = yaml.safe_load(fm.group(1)) or {}
    except yaml.YAMLError as exc:
        raise CommandError(f"command '{path.stem}' has invalid frontmatter: {exc}")
    if not isinstance(meta, dict):
        raise CommandError(f"command '{path.stem}' frontmatter must be a mapping")
    body = fm.group(2).strip()
    if not body:
        raise CommandError(f"command '{path.stem}' has an empty body")
    return Command(
        name=name or str(meta.get("name") or path.stem),
        description=str(meta.get("description") or ""),
        body=body,
        path=path,
        model=str(meta.get("model") or ""),
        raw_frontmatter=meta,
    )


class CommandStore:
    """Loads commands from a list of directories (later dirs are fallbacks)."""

    def __init__(self, dirs: list[str | Path]) -> None:
        self.dirs = [Path(d) for d in dirs]
        self._commands: dict[str, Command] = {}
        self.rescan()

    def rescan(self) -> None:
        found: dict[str, Command] = {}
        for d in self.dirs:
            if not d.is_dir():
                continue
            for md in sorted(d.glob("*.md")):
                try:
                    cmd = parse_command(md)
                except (CommandError, OSError):
                    continue
                found.setdefault(cmd.name, cmd)  # first dir wins
        self._commands = found

    def names(self) -> list[str]:
        return sorted(self._commands)

    def get(self, name: str) -> Optional[Command]:
        return self._commands.get(name)

    def expand(self, name: str, arguments: str = "") -> str:
        cmd = self.get(name)
        if cmd is None:
            raise CommandError(f"unknown command: {name}")
        return cmd.expand(arguments)

    def catalog(self) -> list[dict]:
        return [
            {"name": c.name, "description": c.description}
            for c in self._commands.values()
        ]


def command_tools(store: CommandStore) -> list:
    def run_command(name: str, arguments: str = "") -> dict:
        """Run a saved command: load its instruction markdown, substitute `$ARGUMENTS` with
        the arguments you pass, and follow the resulting instructions as the task. Use this
        for recurring jobs the user has saved as commands (a weekly report, a folder
        summary, a house-style memo); when the user invokes one by name, run it. Args:
        name (str): the command name. arguments (str): text substituted for $ARGUMENTS.
        """
        try:
            prompt = store.expand(name, arguments or "")
        except CommandError as exc:
            return {"error": str(exc)}
        return {"name": name, "instructions": prompt}

    def list_commands() -> dict:
        """List the user's saved commands (name + description) so you know what recurring
        jobs exist and when to use them."""
        return {"commands": store.catalog()}

    run_command.__name__ = "run_command"
    run_command.__doc__ = (
        "Run a saved command: load its instruction markdown, substitute `$ARGUMENTS` with "
        "the arguments you pass, and follow the resulting instructions as the task. Args: "
        "name (str): the command name. arguments (str): text substituted for $ARGUMENTS."
    )
    list_commands.__name__ = "list_commands"
    run_command.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="run_command",
        category="commands",
        risk_level="low",
        capabilities=["commands"],
        requires_approval=False,
    )
    list_commands.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="list_commands",
        category="commands",
        risk_level="low",
        capabilities=["commands"],
        requires_approval=False,
    )
    return [run_command, list_commands]
