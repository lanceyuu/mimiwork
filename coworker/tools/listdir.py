"""The `list_directory` tool — enumerate a folder's contents across the session's roots.

The knowledge-work coworker's discovery problem: aisuite's `list_files` defaults to the
primary scratch dir and its schema never hints at added folders, so the agent concludes a
folder is empty instead of looking inside it. `list_directory` is multi-root aware (relative
paths resolve against the primary root, absolute paths against any root), returns sizes and
types so the agent can choose what to read, and skips the same heavy dirs grep skips.
Read-only, workspace-scoped.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import aisuite as ai

from .office.paths import PathError, resolve_read

_DEFAULT_MAX_ENTRIES = 200

_IGNORE_DIRS = {
    ".git",
    "node_modules",
    "target",
    "dist",
    "build",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".idea",
    ".coworker",
}

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "list_directory",
        "description": (
            "List the contents of a directory in the session's folders, with each entry's "
            "type, size, and modified time. Relative paths resolve against the primary folder; "
            "pass an absolute path to list a folder you were given access to. Use this FIRST "
            "when a task mentions files or a folder — see what is there before reading. "
            "Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to list (default: the primary folder).",
                },
                "recursive": {
                    "type": "boolean",
                    "description": (
                        "Recurse into subdirectories and return every file found "
                        "(bounded by max_entries)."
                    ),
                },
                "max_entries": {
                    "type": "integer",
                    "description": f"Max entries returned (default {_DEFAULT_MAX_ENTRIES}).",
                },
            },
            "required": [],
        },
    },
}


def _entry_stat(path: Path) -> dict[str, Any]:
    try:
        st = path.stat()
        return {"size": st.st_size, "modified": st.st_mtime}
    except OSError:
        return {"size": 0, "modified": 0}


def list_directory_tool(roots: Any) -> list:
    def list_directory(
        path: str = ".",
        recursive: bool = False,
        max_entries: int = _DEFAULT_MAX_ENTRIES,
    ) -> dict[str, Any]:
        n = (
            max_entries
            if isinstance(max_entries, int) and max_entries > 0
            else _DEFAULT_MAX_ENTRIES
        )
        try:
            target = resolve_read(path or ".", roots)
        except PathError as exc:
            return {"error": str(exc)}
        if not target.is_dir():
            return {"error": f"not a directory: {path}"}

        entries: list[dict[str, Any]] = []
        truncated = False
        file_count = 0
        dir_count = 0

        if recursive:
            for dirpath, dirs, files in os.walk(target):
                dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
                for fn in sorted(files):
                    if len(entries) >= n:
                        truncated = True
                        break
                    fp = Path(dirpath) / fn
                    entries.append(
                        {
                            "name": str(fp.relative_to(target)),
                            "type": "file",
                            **_entry_stat(fp),
                        }
                    )
                    file_count += 1
                if truncated:
                    break
                for d in sorted(dirs):
                    if len(entries) >= n:
                        truncated = True
                        break
                    entries.append(
                        {
                            "name": str((Path(dirpath) / d).relative_to(target)) + "/",
                            "type": "dir",
                            "size": 0,
                            "modified": 0,
                        }
                    )
                    dir_count += 1
                if truncated:
                    break
        else:
            try:
                with os.scandir(target) as it:
                    for entry in it:
                        if entry.name in _IGNORE_DIRS:
                            continue
                        if len(entries) >= n:
                            truncated = True
                            break
                        if entry.is_dir(follow_symlinks=False):
                            entries.append(
                                {
                                    "name": entry.name + "/",
                                    "type": "dir",
                                    "size": 0,
                                    "modified": 0,
                                }
                            )
                            dir_count += 1
                        else:
                            try:
                                st = entry.stat()
                                size, modified = st.st_size, st.st_mtime
                            except OSError:
                                size, modified = 0, 0
                            entries.append(
                                {
                                    "name": entry.name,
                                    "type": "file",
                                    "size": size,
                                    "modified": modified,
                                }
                            )
                            file_count += 1
            except OSError as exc:
                return {"error": f"list failed: {exc}"}

        result: dict[str, Any] = {
            "path": str(target),
            "entries": entries,
            "file_count": file_count,
            "dir_count": dir_count,
        }
        if truncated:
            result["truncated"] = True
            result["note"] = (
                f"listing capped at {n} entries; pass `path` to narrow the search or "
                f"`recursive` to walk a specific subdirectory"
            )
        return result

    list_directory.__name__ = "list_directory"
    list_directory.__doc__ = _SCHEMA["function"]["description"]
    list_directory.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="list_directory",
        category="filesystem",
        risk_level="low",
        capabilities=["read"],
        requires_approval=False,
    )
    list_directory.__coworker_schema__ = _SCHEMA
    return [list_directory]