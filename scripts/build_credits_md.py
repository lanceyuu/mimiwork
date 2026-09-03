#!/usr/bin/env python3
"""Regenerate CREDITS.md from coworker/credits.py (the single source of truth)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coworker.credits import render_markdown  # noqa: E402

if __name__ == "__main__":
    target = Path(__file__).resolve().parents[1] / "CREDITS.md"
    target.write_text(render_markdown(), encoding="utf-8")
    print(f"wrote {target}")
