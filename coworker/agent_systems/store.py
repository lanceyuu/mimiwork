"""Agent systems on disk: ``agent-systems/<id>/system.json`` (+ ``runs/<run_id>.json``).

Folder-is-truth like Apps: a handful of designs does not need a database, and a folder
is the export story when everything else fails.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from .models import AgentSystem, clean_edge, clean_node

_ID = re.compile(r"sys-[0-9a-f]{8}")


def from_dict(data: dict[str, Any], *, system_id: str = "") -> AgentSystem:
    """A system from user- or model-supplied JSON. Shape errors raise ValueError;
    whether it can RUN is validate()'s question, so a half-drawn design still saves."""
    if not isinstance(data, dict):
        raise ValueError("an agent system is a JSON object")
    nodes = data.get("nodes") if isinstance(data.get("nodes"), list) else []
    edges = data.get("edges") if isinstance(data.get("edges"), list) else []
    clean = [clean_node(n, i) for i, n in enumerate(nodes)]
    entry = str(data.get("entry") or "").strip() or (clean[0]["id"] if clean else "")
    return AgentSystem(
        id=system_id or str(data.get("id") or ""),
        title=str(data.get("title") or "Untitled system").strip()[:80] or "Untitled system",
        description=str(data.get("description") or "").strip()[:500],
        pattern=str(data.get("pattern") or "").strip()[:30],
        nodes=clean,
        edges=[clean_edge(e, i) for i, e in enumerate(edges)],
        entry=entry,
        builder_session=str(data.get("builder_session") or ""),
    )


class AgentSystemStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _dir(self, system_id: str) -> Path:
        # Ids are ours; anything else is not a path we will build.
        if not _ID.fullmatch(system_id or ""):
            raise KeyError(system_id)
        return self.root / system_id

    def list(self) -> list[AgentSystem]:
        out = [s for d in sorted(self.root.iterdir()) if (s := self._load(d)) is not None]
        return sorted(out, key=lambda s: -s.updated_at)

    def get(self, system_id: str) -> Optional[AgentSystem]:
        try:
            return self._load(self._dir(system_id))
        except KeyError:
            return None

    def _load(self, d: Path) -> Optional[AgentSystem]:
        try:
            data = json.loads((d / "system.json").read_text(encoding="utf-8"))
            system = from_dict(data, system_id=d.name)
        except (OSError, ValueError, TypeError):
            return None
        system.created_at = float(data.get("created_at") or system.created_at)
        system.updated_at = float(data.get("updated_at") or system.updated_at)
        return system

    def create(self, data: dict[str, Any]) -> AgentSystem:
        system = from_dict(data, system_id=f"sys-{secrets.token_hex(4)}")
        self._dir(system.id).mkdir(parents=True, exist_ok=False)
        self._save(system)
        return system

    def update(self, system_id: str, changes: dict[str, Any]) -> AgentSystem:
        current = self.get(system_id)
        if current is None:
            raise KeyError(system_id)
        merged = {**current.public(), **{k: v for k, v in changes.items() if v is not None}}
        system = from_dict(merged, system_id=system_id)
        system.created_at = current.created_at
        self._save(system)
        return system

    def delete(self, system_id: str) -> bool:
        try:
            d = self._dir(system_id)
        except KeyError:
            return False
        if not d.is_dir():
            return False
        shutil.rmtree(d, ignore_errors=True)
        return True

    def _save(self, system: AgentSystem) -> None:
        system.updated_at = time.time()
        data = system.public()
        (self._dir(system.id) / "system.json").write_text(json.dumps(data, indent=2), encoding="utf-8")

    # -- runs: kept so a run paused for a person survives a restart ----------------
    def save_run(self, run: dict[str, Any]) -> None:
        d = self._dir(run["system_id"]) / "runs"
        d.mkdir(exist_ok=True)
        (d / f"{run['run_id']}.json").write_text(json.dumps(run, indent=2), encoding="utf-8")

    def get_run(self, system_id: str, run_id: str) -> Optional[dict[str, Any]]:
        if not re.fullmatch(r"run-[0-9a-f]{8}", run_id or ""):
            return None
        try:
            return json.loads((self._dir(system_id) / "runs" / f"{run_id}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            return None

    def list_runs(self, system_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """This system's runs, newest first. Runs start from chat, so this is how the
        Agents page finds the one to highlight on the canvas."""
        try:
            files = list((self._dir(system_id) / "runs").glob("run-*.json"))
        except KeyError:
            return []
        runs = []
        for f in sorted(files, key=lambda f: f.stat().st_mtime, reverse=True)[:limit]:
            try:
                runs.append(json.loads(f.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        return runs

    def find_run(self, run_id: str) -> Optional[dict[str, Any]]:
        for s in self.list():
            run = self.get_run(s.id, run_id)
            if run is not None:
                return run
        return None
