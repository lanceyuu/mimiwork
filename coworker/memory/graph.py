"""The memory graph — Obsidian-style structure derived from what memories say.

Memories are flat rows; the graph is built by READING them, not by a second
bookkeeping table that could drift out of sync:

- ``[[wiki-links]]`` in a memory's content link it to the memory whose ``key``
  (or numeric id) matches. Unresolved links are dropped — a dangling link is a
  note-taking artifact, not an error.
- ``#tags`` become hub nodes, exactly like Obsidian's tag nodes: every memory
  mentioning ``#pricing`` hangs off the same hub.
- A memory's workspace becomes a hub node too, so per-project clusters are
  visible without anyone writing a single link.

Node ids are namespaced (``m:<id>``, ``t:<tag>``, ``w:<workspace>``) so the
three kinds can never collide. Edges are deduplicated and undirected for
display purposes; ``kind`` says why the edge exists.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from .base import MemoryItem

# [[link target]] — Obsidian syntax; the target matches a memory key or numeric id.
_WIKI = re.compile(r"\[\[([^\[\]|]+?)(?:\|[^\[\]]*)?\]\]")
# #tag — word chars and dashes, not part of a longer word and not a heading
# ("# Title" has a space; "#3" alone is more likely an issue number, so require
# at least one letter).
_TAG = re.compile(r"(?<![\w#])#([\w-]*[a-zA-Z][\w-]*)")


def _workspace_label(workspace: str) -> str:
    return Path(workspace).name or workspace


def build_graph(
    items: list[MemoryItem],
    *,
    labels: Optional[dict[str, str]] = None,
    project_names: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """{nodes, edges} for the GUI's graph view.

    ``labels`` names a workspace hub by something better than its folder name — a
    conversation's scratch folder is called after the conversation's id, and a hub
    reading "d338424c-827" tells nobody what it is (owner report 2026-09-02).
    ``project_names`` does the same for project-group hubs (``p:<id>``)."""
    labels = labels or {}
    project_names = project_names or {}
    by_key: dict[str, MemoryItem] = {}
    by_id: dict[str, MemoryItem] = {}
    for item in items:
        by_id[str(item.id)] = item
        if item.key:
            by_key[item.key.strip().lower()] = item

    nodes: dict[str, dict[str, Any]] = {}
    edges: set[tuple[str, str, str]] = set()

    def _edge(a: str, b: str, kind: str) -> None:
        if a == b:
            return
        # Undirected: normalize order so A→B and B→A dedupe.
        edges.add((a, b, kind) if a < b else (b, a, kind))

    for item in items:
        node_id = f"m:{item.id}"
        label = (item.summary or "").strip() or (item.key or "").strip() or (
            item.content.strip().splitlines()[0][:60] if item.content.strip() else f"memory {item.id}"
        )
        nodes[node_id] = {
            "id": node_id,
            "kind": "memory",
            "label": label[:80],
            "scope": item.scope.value if hasattr(item.scope, "value") else str(item.scope),
            "memory_id": item.id,
        }

        content = item.content or ""

        for raw in _WIKI.findall(content):
            target = raw.strip().lower()
            other: Optional[MemoryItem] = by_key.get(target) or by_id.get(target)
            if other is not None and other.id != item.id:
                _edge(node_id, f"m:{other.id}", "link")

        for tag in {t.lower() for t in _TAG.findall(content)}:
            tag_id = f"t:{tag}"
            nodes.setdefault(tag_id, {"id": tag_id, "kind": "tag", "label": f"#{tag}"})
            _edge(node_id, tag_id, "tag")

        if item.workspace:
            ws_id = f"w:{item.workspace}"
            nodes.setdefault(
                ws_id,
                {
                    "id": ws_id,
                    "kind": "workspace",
                    "label": labels.get(item.workspace) or _workspace_label(item.workspace),
                },
            )
            _edge(node_id, ws_id, "workspace")

        if item.project_id:
            p_id = f"p:{item.project_id}"
            nodes.setdefault(
                p_id,
                {
                    "id": p_id,
                    "kind": "project",
                    "label": project_names.get(item.project_id) or "Project",
                },
            )
            _edge(node_id, p_id, "project")

    degree: dict[str, int] = {}
    for a, b, _ in edges:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
    for node_id, node in nodes.items():
        node["degree"] = degree.get(node_id, 0)

    return {
        "nodes": list(nodes.values()),
        "edges": [{"source": a, "target": b, "kind": k} for a, b, k in sorted(edges)],
    }
