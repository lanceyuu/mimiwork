"""Workspace map: a compact ranked snapshot of the workspace for the system prompt.

Inspired by coding agents' "repo map": instead of the model exploring with list_dir
calls at the start of every task, hand it a small pre-built picture — the folder
skeleton plus the files most likely to matter, most-recently-touched first. Injected
once at session start next to environment_context(); the model is told it may be
stale and to verify with list_dir before relying on it.

Budgeted hard at ``budget_chars`` and pruned aggressively while walking, so a huge
workspace costs bounded time (entry cap) and bounded context.
"""

from __future__ import annotations

import os
import time
from datetime import date
from pathlib import Path

# Directories that are build/derived state — never interesting to a knowledge worker
# and often enormous. Hidden dirs are pruned wholesale (also keeps .git out).
_PRUNE_DIRS = {
    "node_modules",
    "__pycache__",
    "venv",
    "dist",
    "build",
    "target",
    "coverage",
    "site-packages",
}

# Document-y extensions get a recency boost: for the app's users a week-old .docx
# usually matters more than an hour-old .log.
_DOC_EXTS = {
    ".md", ".txt", ".rtf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".tsv",
    ".ppt", ".pptx", ".pdf", ".ipynb", ".py", ".r", ".ts", ".tsx", ".js",
    ".json", ".yaml", ".yml", ".tex", ".html",
}
_DOC_BOOST_SECONDS = 3 * 86400

_MAX_ENTRIES = 4000  # walk cap: bounded work even on pathological trees
_MAX_DEPTH = 6
_TOP_FILES = 40

# (root, signature) -> rendered text. Signature is the top-level dir mtimes, so a
# save anywhere near the surface invalidates; TTL backstops deep-only changes.
_cache: dict[str, tuple[float, tuple, str]] = {}
_CACHE_TTL = 30.0


def _signature(root: Path) -> tuple:
    try:
        entries = sorted(os.scandir(root), key=lambda e: e.name)[:64]
        return tuple((e.name, e.stat().st_mtime_ns) for e in entries)
    except OSError:
        return ()


def _walk(root: Path) -> tuple[list[tuple[str, float, int]], dict[str, int], bool]:
    """Collect (relpath, mtime, size) files + top-level dir file counts."""
    files: list[tuple[str, float, int]] = []
    top_counts: dict[str, int] = {}
    truncated = False
    stack: list[tuple[Path, int, str]] = [(root, 0, "")]
    seen = 0
    while stack:
        folder, depth, top = stack.pop()
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            seen += 1
            if seen > _MAX_ENTRIES:
                truncated = True
                stack.clear()
                break
            name = entry.name
            if name.startswith("."):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    if name in _PRUNE_DIRS or depth >= _MAX_DEPTH:
                        continue
                    stack.append((Path(entry.path), depth + 1, top or name))
                elif entry.is_file(follow_symlinks=False):
                    st = entry.stat()
                    rel = os.path.relpath(entry.path, root)
                    files.append((rel, st.st_mtime, st.st_size))
                    if top:
                        top_counts[top] = top_counts.get(top, 0) + 1
                    else:
                        top_counts["."] = top_counts.get(".", 0) + 1
            except OSError:
                continue
    return files, top_counts, truncated


def _fmt_size(n: int) -> str:
    if n >= 1 << 20:
        return f"{n / (1 << 20):.1f} MB"
    if n >= 1 << 10:
        return f"{n // (1 << 10)} KB"
    return f"{n} B"


def build_workspace_map(workspace: str | Path, budget_chars: int = 3000) -> str:
    """Render the map block, or "" for a missing/empty/unreadable workspace."""
    root = Path(workspace).expanduser()
    try:
        root = root.resolve()
    except OSError:
        return ""
    if not root.is_dir():
        return ""

    key = str(root)
    sig = _signature(root)
    hit = _cache.get(key)
    now = time.monotonic()
    if hit and hit[1] == sig and now - hit[0] < _CACHE_TTL:
        return hit[2]

    files, top_counts, truncated = _walk(root)
    if not files:
        return ""

    def score(item: tuple[str, float, int]) -> float:
        rel, mtime, _size = item
        boost = _DOC_BOOST_SECONDS if os.path.splitext(rel)[1].lower() in _DOC_EXTS else 0
        return mtime + boost

    files.sort(key=score, reverse=True)

    dirs_line = ", ".join(
        f"{name}/ ({count})" for name, count in
        sorted(top_counts.items(), key=lambda kv: -kv[1]) if name != "."
    )
    lines = [f"total files seen: {len(files)}" + (" (walk capped)" if truncated else "")]
    if dirs_line:
        lines.append(f"folders: {dirs_line}")
    lines.append("recently active files:")
    body_len = sum(len(x) + 1 for x in lines)
    for rel, mtime, size in files[:_TOP_FILES]:
        try:
            day = date.fromtimestamp(mtime).isoformat()
        except (OverflowError, OSError, ValueError):
            day = "?"
        line = f"- {rel}  ({day}, {_fmt_size(size)})"
        if body_len + len(line) > budget_chars:
            break
        lines.append(line)
        body_len += len(line) + 1

    text = (
        "Workspace map (auto-built at session start; may be stale or incomplete — "
        "verify with list_dir before relying on it):\n<workspace_map>\n"
        + "\n".join(lines)
        + "\n</workspace_map>"
    )
    _cache[key] = (now, sig, text)
    return text
