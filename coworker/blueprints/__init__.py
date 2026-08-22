"""Bundled automation blueprints — starter .mimiflow.json files shipped with the app.

Same shape as a user export (`manager.export_automation_blueprint`): title,
instructions, schedule, notify flag, and permission REQUESTS (never grants — the
import form shows them and the user's Create click is the consent). Students in a
course import these in one click instead of typing instructions from a slide.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DIR = Path(__file__).parent


def builtin_blueprints() -> list[dict[str, Any]]:
    """Every bundled blueprint, sorted by title: ``{"name", "blueprint"}``."""
    out: list[dict[str, Any]] = []
    for path in sorted(_DIR.glob("*.mimiflow.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict) or data.get("mimiwork_blueprint") != 1:
            continue
        if not data.get("title") or not data.get("instructions"):
            continue
        out.append({"name": path.name.removesuffix(".mimiflow.json"), "blueprint": data})
    return sorted(out, key=lambda e: str(e["blueprint"]["title"]).lower())
