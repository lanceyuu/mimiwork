"""Reversible snapshots for files changed by Mimi's managed write tools.

The snapshot happens immediately before the tool crosses its write boundary.  If the
copy cannot be made, the tool is stopped: an Undo button that only works sometimes is
worse than no Undo button at all.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .tools.office.paths import resolve_write

_MAX_TRANSACTIONS = 20
_DIRECT_TARGETS: dict[str, tuple[str, ...]] = {
    "write_file": ("path",),
    "replace_in_file": ("path",),
    "write_document": ("path",),
    "edit_document": ("path",),
    "revise_document": ("path",),
    "write_presentation": ("path",),
    "write_workbook": ("path",),
    "edit_workbook": ("path",),
    "edit_image": ("output",),
    "annotate_image": ("output",),
    "combine_images": ("output",),
}
_PATCH_LINE = re.compile(r"^\*\*\* (?:Add|Delete|Update) File:\s*(.+?)\s*$", re.MULTILINE)
_MOVE_LINE = re.compile(r"^\*\*\* Move to:\s*(.+?)\s*$", re.MULTILINE)
_DIFF_LINE = re.compile(r"^(?:---|\+\+\+)\s+([^\t\n]+)", re.MULTILINE)


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(raw, path)
    finally:
        try:
            os.unlink(raw)
        except FileNotFoundError:
            pass


class RecoverySession:
    """One engine's recovery boundary; roots are read live for added folders."""

    def __init__(
        self,
        base: Path,
        session_id: str,
        roots: Callable[[], Any],
    ) -> None:
        key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
        self.base = Path(base) / "recovery" / key
        self.session_id = session_id
        self._roots = roots
        self._lock = threading.RLock()
        self._turn_id = ""
        self.base.mkdir(parents=True, exist_ok=True)

    @property
    def _index(self) -> Path:
        return self.base / "transactions.json"

    def _load(self) -> list[dict[str, Any]]:
        try:
            value = json.loads(self._index.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []
        return value if isinstance(value, list) else []

    def _save(self, rows: list[dict[str, Any]]) -> None:
        if len(rows) > _MAX_TRANSACTIONS:
            expired = rows[:-_MAX_TRANSACTIONS]
            rows = rows[-_MAX_TRANSACTIONS:]
            for row in expired:
                shutil.rmtree(self.base / str(row.get("id") or "missing"), ignore_errors=True)
        _atomic_json(self._index, rows)

    def begin_turn(self) -> None:
        with self._lock:
            self._turn_id = uuid.uuid4().hex

    def _raw_targets(self, tool: str, args: dict[str, Any]) -> list[str]:
        out = [
            str(args[key])
            for key in _DIRECT_TARGETS.get(tool, ())
            if isinstance(args.get(key), str) and str(args[key]).strip()
        ]
        if tool == "apply_patch":
            patch = str(args.get("patch") or "")
            out.extend(_PATCH_LINE.findall(patch))
            out.extend(_MOVE_LINE.findall(patch))
        elif tool == "apply_unified_diff":
            for raw in _DIFF_LINE.findall(str(args.get("diff") or "")):
                raw = raw.strip()
                if raw == "/dev/null":
                    continue
                out.append(raw[2:] if raw.startswith(("a/", "b/")) else raw)
        return list(dict.fromkeys(out))

    def capture(self, tool: str, args: dict[str, Any]) -> None:
        raw_targets = self._raw_targets(tool, args)
        if not raw_targets:
            return
        with self._lock:
            if not self._turn_id:
                self.begin_turn()
            rows = self._load()
            txn = next((row for row in rows if row.get("id") == self._turn_id), None)
            if txn is None:
                txn = {
                    "id": self._turn_id,
                    "created_at": time.time(),
                    "restored_at": None,
                    "entries": [],
                }
                rows.append(txn)
            captured = {entry.get("path") for entry in txn["entries"]}
            txn_dir = self.base / self._turn_id
            txn_dir.mkdir(parents=True, exist_ok=True)
            for raw in raw_targets:
                target = resolve_write(raw, self._roots())
                key = str(target)
                if key in captured:
                    continue
                if target.exists() and not target.is_file():
                    raise ValueError(f"cannot make a recovery copy of a directory: {raw}")
                entry: dict[str, Any] = {
                    "path": key,
                    "name": target.name,
                    "existed": target.is_file(),
                    "tool": tool,
                }
                if target.is_file():
                    blob = f"{len(txn['entries']):04d}-{uuid.uuid4().hex}.bak"
                    shutil.copy2(target, txn_dir / blob)
                    entry["blob"] = blob
                    entry["size"] = target.stat().st_size
                else:
                    entry["size"] = 0
                txn["entries"].append(entry)
                captured.add(key)
            self._save(rows)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = [row for row in self._load() if row.get("entries")]
        rows.sort(key=lambda row: float(row.get("created_at") or 0), reverse=True)
        return [
            {
                "id": row["id"],
                "created_at": row.get("created_at", 0),
                "restored_at": row.get("restored_at"),
                "files": [
                    {
                        "path": entry.get("path", ""),
                        "name": entry.get("name", ""),
                        "action": "modified" if entry.get("existed") else "created",
                    }
                    for entry in row.get("entries", [])
                ],
            }
            for row in rows
        ]

    def restore(self, transaction_id: str) -> dict[str, Any]:
        with self._lock:
            rows = self._load()
            txn = next((row for row in rows if row.get("id") == transaction_id), None)
            if txn is None:
                return {"ok": False, "error": "recovery point not found"}
            if txn.get("restored_at"):
                return {"ok": False, "error": "this recovery point was already restored"}
            entries = txn.get("entries") or []
            if not entries:
                return {"ok": False, "error": "recovery point contains no files"}

            # Validate every target and every backup before changing any user file.
            prepared: list[tuple[dict[str, Any], Path, Path | None]] = []
            for entry in entries:
                target = resolve_write(str(entry.get("path") or ""), self._roots())
                blob = None
                if entry.get("existed"):
                    blob = self.base / transaction_id / str(entry.get("blob") or "")
                    if not blob.is_file():
                        return {"ok": False, "error": f"recovery copy is missing for {target.name}"}
                elif target.exists() and not target.is_file():
                    return {"ok": False, "error": f"refusing to remove directory {target}"}
                prepared.append((entry, target, blob))

            restored: list[str] = []
            removed: list[str] = []
            for entry, target, blob in prepared:
                if entry.get("existed"):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    fd, raw = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
                    os.close(fd)
                    try:
                        shutil.copy2(blob, raw)
                        os.replace(raw, target)
                    finally:
                        try:
                            os.unlink(raw)
                        except FileNotFoundError:
                            pass
                    restored.append(str(target))
                elif target.exists():
                    target.unlink()
                    removed.append(str(target))
            txn["restored_at"] = time.time()
            self._save(rows)
            return {"ok": True, "restored": restored, "removed": removed}
