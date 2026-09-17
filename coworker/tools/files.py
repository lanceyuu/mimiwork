"""Line-numbered file reading (`read_file`) — replaces the aisuite toolkit's reader.

The toolkit's `read_file` returns raw text (the agent can't cite path:line without
counting) and raises outright on large files (the agent errors and guesses). This one
returns `cat -n`-style numbered lines, windows big files instead of failing, and tells
the agent how to continue reading. Read-only, workspace-scoped.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import aisuite as ai

_DEFAULT_MAX_LINES = 2000

_DELETE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "delete_file",
        "description": (
            "Delete a file or folder by moving it to the Trash (Recycle Bin on Windows), "
            "where the user can put it back. Use this instead of `rm`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File or folder to delete."},
            },
            "required": ["path"],
        },
    },
}


def _unique(dest: Path) -> Path:
    n = 2
    out = dest
    while out.exists():
        out = dest.with_name(f"{dest.stem} {n}{dest.suffix}")
        n += 1
    return out


def send_to_trash(target: Path) -> str:
    """Move a file or folder to the OS trash; returns where it went. Never deletes for good."""
    import subprocess
    import sys
    from urllib.parse import quote

    if sys.platform == "darwin":
        # Finder's own delete keeps "Put Back"; a plain move into ~/.Trash is the fallback.
        try:
            done = subprocess.run(
                ["osascript", "-e", "on run argv", "-e",
                 'tell application "Finder" to delete (POSIX file (item 1 of argv) as alias)',
                 "-e", "end run", str(target)],
                capture_output=True, timeout=20,
            )
            if done.returncode == 0 and not target.exists():
                return "the Trash"
        except (OSError, subprocess.SubprocessError):
            pass
        import shutil

        trash = Path.home() / ".Trash"
        trash.mkdir(exist_ok=True)
        shutil.move(str(target), str(_unique(trash / target.name)))
        return "the Trash"
    if sys.platform == "win32":
        method = "DeleteDirectory" if target.is_dir() else "DeleteFile"
        done = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Add-Type -AssemblyName Microsoft.VisualBasic; "
             f"[Microsoft.VisualBasic.FileIO.FileSystem]::{method}($args[0], 'OnlyErrorDialogs', 'SendToRecycleBin')",
             str(target)],
            capture_output=True, timeout=30,
        )
        if done.returncode != 0 or target.exists():
            raise RuntimeError(done.stderr.decode(errors="replace").strip() or "PowerShell refused")
        return "the Recycle Bin"
    # Linux: the freedesktop trash layout, so the desktop's Trash shows it.
    import shutil
    import time

    base = Path.home() / ".local" / "share" / "Trash"
    (base / "files").mkdir(parents=True, exist_ok=True)
    (base / "info").mkdir(parents=True, exist_ok=True)
    dest = _unique(base / "files" / target.name)
    (base / "info" / f"{dest.name}.trashinfo").write_text(
        f"[Trash Info]\nPath={quote(str(target))}\nDeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n",
        encoding="utf-8",
    )
    shutil.move(str(target), str(dest))
    return "the Trash"
_MAX_LINE_CHARS = 500

_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Read a text file, returning numbered lines ('   12\\ttext') so code can be "
            "referenced as path:line. Large files are windowed: pass start_line to continue "
            "where the previous read stopped. Read-only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path, relative to the workspace.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "First line to read, 1-based (default 1).",
                },
                "max_lines": {
                    "type": "integer",
                    "description": f"How many lines (default {_DEFAULT_MAX_LINES}).",
                },
            },
            "required": ["path"],
        },
    },
}


def file_tools(workspace: str, roots: Any = None) -> list:
    root = Path(workspace).resolve()

    def _resolve(path: str) -> Path:
        """Multi-root read resolution: relative paths resolve against the primary root;
        absolute paths must land inside some root (the same rule the office tools use)."""
        from .office.paths import resolve_read

        return resolve_read(path, roots or root)

    def read_file(
        path: str,
        start_line: int = 1,
        max_lines: int = _DEFAULT_MAX_LINES,
    ) -> dict[str, Any]:
        start = start_line if isinstance(start_line, int) and start_line > 0 else 1
        n = (
            max_lines
            if isinstance(max_lines, int) and max_lines > 0
            else _DEFAULT_MAX_LINES
        )
        n = min(n, _DEFAULT_MAX_LINES)
        try:
            target = _resolve(path)
        except ValueError as exc:
            return {"error": str(exc)}
        if not target.is_file():
            return {"error": f"not a file: {path}"}

        selected: list[str] = []
        total = 0
        try:
            with open(target, "r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    total = i
                    if i < start or len(selected) >= n:
                        continue
                    text = line.rstrip("\n")
                    if len(text) > _MAX_LINE_CHARS:
                        text = text[:_MAX_LINE_CHARS] + "… (line truncated)"
                    selected.append(f"{i:>6}\t{text}")
        except OSError as exc:
            return {"error": f"read failed: {exc}"}

        end = start + len(selected) - 1 if selected else start - 1
        from .office.paths import display_path

        result: dict[str, Any] = {
            "path": display_path(target, roots or root),
            "start_line": start,
            "end_line": end,
            "total_lines": total,
            "content": "\n".join(selected),
        }
        if end < total:
            result["note"] = (
                f"showing lines {start}-{end} of {total}; "
                f"call again with start_line={end + 1} to continue"
            )
        return result

    read_file.__name__ = "read_file"
    read_file.__doc__ = _SCHEMA["function"]["description"]
    read_file.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="read_file",
        category="filesystem",
        risk_level="low",
        capabilities=["read"],
        requires_approval=False,
    )
    read_file.__coworker_schema__ = _SCHEMA

    def delete_file(path: str) -> dict[str, Any]:
        from .office.paths import display_path, resolve_write

        try:
            target = resolve_write(path, roots or root)
        except ValueError as exc:
            return {"error": str(exc)}
        if not target.exists():
            return {"error": f"not found: {path}"}
        try:
            where = send_to_trash(target)
        except (OSError, RuntimeError) as exc:
            return {"error": f"could not move to the Trash: {exc}"}
        return {
            "path": display_path(target, roots or root),
            "moved_to": where,
            "note": f"Moved to {where}; the user can put it back from there.",
        }

    delete_file.__name__ = "delete_file"
    delete_file.__doc__ = _DELETE_SCHEMA["function"]["description"]
    delete_file.__aisuite_tool_metadata__ = ai.ToolMetadata(
        name="delete_file",
        category="filesystem",
        risk_level="medium",
        capabilities=["write"],
        requires_approval=True,
    )
    delete_file.__coworker_schema__ = _DELETE_SCHEMA
    return [read_file, delete_file]
