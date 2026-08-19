"""Root-aware path resolution for the Office toolset.

Office tools take a model-supplied path, so every one of them is a potential
workspace-escape surface. The containment rule therefore lives here once, rather than being
re-derived per format.

Semantics match what the agent is told in ``roots.render_context``: relative paths resolve
against the primary root, absolute paths must land inside some root, and writes are only
allowed in a root marked writable. Resolution happens *before* the containment check, so a
symlink pointing out of the workspace is caught rather than followed.

Pure: nothing here touches the filesystem (no mkdir, no stat) — callers create directories
only after the path has been authorized.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


class PathError(ValueError):
    """A model-supplied path is empty, escapes the session's roots, or is not writable."""


def _root_paths(roots: Any) -> list:
    """Coerce the caller's roots into ``RootDir``s. Accepts the shared live list, a plain
    workspace string, or None — the same shapes the file toolkit is built from."""
    from ...roots import RootDir, normalize_roots

    if roots is None:
        return []
    if isinstance(roots, (str, Path)):
        return [RootDir(path=roots, writable=True)]
    return normalize_roots(roots)


def _resolve(path: str, roots: Any, *, need_write: bool) -> Path:
    entries = _root_paths(roots)
    if not entries:
        raise PathError("no workspace directory is available for this session")

    raw = (path or "").strip()
    if not raw:
        raise PathError("path is required")

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = entries[0].path / candidate
    # Resolve symlinks and `..` BEFORE containment: `strict=False` so a not-yet-created
    # output file still resolves (its existing parents are what matter).
    target = candidate.resolve()

    for entry in entries:
        try:
            target.relative_to(entry.path)
        except ValueError:
            continue
        if need_write and not entry.writable:
            raise PathError(
                f"{entry.path} is a read-only folder in this session; "
                "save to the primary workspace instead"
            )
        return target

    raise PathError(f"path escapes this session's folders: {raw}")


def resolve_read(path: str, roots: Any) -> Path:
    """Authorize a read. Any root (read-only included) is acceptable."""
    return _resolve(path, roots, need_write=False)


def resolve_write(path: str, roots: Any) -> Path:
    """Authorize a write. Only a writable root is acceptable."""
    return _resolve(path, roots, need_write=True)


def context_roots(context: Any) -> Any:
    """The roots a tool factory should resolve against: the session's live multi-root list
    when present, else the single workspace (writable, matching the file toolkit's fallback
    in ``catalog._files``)."""
    roots = getattr(context, "roots", None)
    if roots:
        return roots
    workspace: Optional[Path] = getattr(context, "workspace", None)
    return str(workspace) if workspace else None


def display_path(target: Path, roots: Any) -> str:
    """The path to show the user/model: relative to its root when possible, else absolute."""
    for entry in _root_paths(roots):
        try:
            return str(target.relative_to(entry.path))
        except ValueError:
            continue
    return str(target)
