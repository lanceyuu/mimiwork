"""The memory vault: every memory as a markdown note, with MEMORY.md as the index.

SQLite stays the store the engine reads and the tools write. The vault is a mirror of
it, regenerated after every change, so the user can open the folder in Obsidian, read
it, search it and follow the links; the graph's note panel shows the same text. Edits
go through MimiWork (Settings ▸ Memory, or the graph's Edit), which is what rewrites
the files — a note changed by hand here is overwritten on the next change. One way,
on purpose: two writers to one fact is how facts get lost (owner ask 2026-09-17).

Notes are ``NNN-slug.md`` (id first, so the folder sorts in the order things were
learned); ``[[14]]`` and ``[[key]]`` links inside a memory are rewritten to the note
name so Obsidian resolves them.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

from .base import MemoryItem
from .graph import _TAG, _WIKI

_MARK = "mimiwork: memory"


def vault_dir() -> Path:
    override = os.environ.get("COWORKER_MEMORY_VAULT")
    return Path(override) if override else Path.home() / "MimiWork" / "Memory"


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:60].rstrip("-") or "memory"


def _title(item: MemoryItem) -> str:
    return (
        (item.summary or "").strip()
        or (item.key or "").strip()
        or (item.content.strip().splitlines()[0][:80] if item.content.strip() else f"memory {item.id}")
    )


def note_name(item: MemoryItem) -> str:
    return f"{item.id:03d}-{_slug(_title(item))}"


def export(
    items: list[MemoryItem],
    *,
    labels: Optional[dict[str, str]] = None,
    project_names: Optional[dict[str, str]] = None,
    where: Optional[Path] = None,
) -> Path:
    """Write the notes and the index; drop notes for memories that no longer exist."""
    labels = labels or {}
    project_names = project_names or {}
    vault = where or vault_dir()
    vault.mkdir(parents=True, exist_ok=True)

    names = {item.id: note_name(item) for item in items}
    by_key = {item.key.strip().lower(): item.id for item in items if item.key}
    titles = {item.id: _title(item) for item in items}

    def rewrite(content: str) -> str:
        def one(m: re.Match[str]) -> str:
            raw = m.group(0)[2:-2]
            target, _, alias = raw.partition("|")
            t = target.strip().lower()
            mid = by_key.get(t) or (int(t) if t.isdigit() and int(t) in names else None)
            if mid is None:
                return m.group(0)
            return f"[[{names[mid]}|{alias.strip() or titles[mid]}]]"

        return _WIKI.sub(one, content or "")

    def place(item: MemoryItem) -> str:
        if item.project_id:
            return project_names.get(item.project_id) or "Project"
        if item.workspace:
            return labels.get(item.workspace) or Path(item.workspace).name or item.workspace
        return ""

    written: set[Path] = set()
    for item in items:
        path = vault / f"{names[item.id]}.md"
        head = [
            "---",
            _MARK,
            f"id: {item.id}",
            f"scope: {item.scope.value if hasattr(item.scope, 'value') else item.scope}",
        ]
        if place(item):
            head.append(f"where: {place(item)}")
        if item.created_at:
            head.append(f"created: {item.created_at}")
        head.append("---")
        body = "\n".join(head) + f"\n\n# {titles[item.id]}\n\n{rewrite(item.content).strip()}\n"
        path.write_text(body, encoding="utf-8")
        written.add(path)

    # The index: what Mimi knows about you, then what it learned per folder or project.
    lines = [
        "# Mimi's memory",
        "",
        "Everything Mimi remembers between conversations, one note each. Open this folder",
        "in Obsidian to browse it; edit a memory in MimiWork (Settings ▸ Memory, or click a",
        "dot in the graph) — the notes here are rewritten from it after every change.",
        "",
    ]
    groups: dict[str, list[MemoryItem]] = {}
    for item in items:
        groups.setdefault(place(item), []).append(item)
    if "" in groups:
        lines += ["## About you", ""] + [f"- [[{names[i.id]}|{titles[i.id]}]]" for i in groups.pop("")] + [""]
    for label in sorted(groups, key=str.lower):
        lines += [f"## {label}", ""] + [f"- [[{names[i.id]}|{titles[i.id]}]]" for i in groups[label]] + [""]
    tags: dict[str, list[int]] = {}
    for item in items:
        for tag in {t.lower() for t in _TAG.findall(item.content or "")}:
            tags.setdefault(tag, []).append(item.id)
    if tags:
        lines += ["## Tags", ""]
        for tag in sorted(tags):
            lines.append(f"- #{tag} — " + ", ".join(f"[[{names[i]}]]" for i in tags[tag]))
        lines.append("")
    index = vault / "MEMORY.md"
    index.write_text("\n".join(lines), encoding="utf-8")
    written.add(index)

    # Only notes this exporter wrote are ever removed — the user's own files stay.
    for stale in vault.glob("*.md"):
        if stale in written:
            continue
        try:
            if stale.read_text(encoding="utf-8", errors="replace").startswith(f"---\n{_MARK}"):
                stale.unlink()
        except OSError:
            continue
    return vault


def read_index(where: Optional[Path] = None) -> dict[str, Any]:
    vault = where or vault_dir()
    try:
        text = (vault / "MEMORY.md").read_text(encoding="utf-8")
    except OSError:
        text = ""
    return {"path": str(vault), "index": text}
