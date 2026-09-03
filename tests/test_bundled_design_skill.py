"""The bundled design skill is UI/UX Pro Max; mono-color lives in the skill store.

Owner call 2026-09-03: mono-color is a taste, not a default. UI/UX Pro Max is the
design intelligence every interface task should be able to reach for, so it ships
with the app — with its script paths rewritten for MimiWork, since there is no
Claude Code plugin root here.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from coworker.skills import marketplace

ROOT = Path(__file__).resolve().parents[1]
BUILTIN = ROOT / "coworker" / "skills" / "builtin"


def test_ui_ux_pro_max_is_bundled_and_speaks_mimiwork_paths():
    skill = BUILTIN / "ui-ux-pro-max"
    text = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\nname: ui-ux-pro-max")
    assert "CLAUDE_PLUGIN_ROOT" not in text, "a plugin root the app does not have"
    assert "${SKILL_DIR}/scripts/search.py" in text
    assert "resources_path" in text, "the model is told where SKILL_DIR comes from"
    assert (skill / "LICENSE").is_file() and (skill / "VENDOR-NOTE.md").is_file()
    assert not (skill / "scripts" / "tests").exists(), "upstream's own tests are not shipped"


def test_the_bundled_search_script_runs_from_its_own_folder(tmp_path):
    script = BUILTIN / "ui-ux-pro-max" / "scripts" / "search.py"
    out = subprocess.run(
        [sys.executable, str(script), "saas dashboard analytics", "--domain", "style"],
        capture_output=True,
        text=True,
        cwd=tmp_path,  # anywhere but the skill folder: the script must find its data itself
        timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert "Found:" in out.stdout and "Style ID" in out.stdout


def test_mono_color_left_the_bundle_for_the_store():
    assert not (BUILTIN / "mono-color").exists()
    assert (ROOT / "skills" / "store" / "mono-color" / "SKILL.md").is_file()
    extras = json.loads((ROOT / "coworker" / "skills" / "store_extras.json").read_text(encoding="utf-8"))
    entry = next(e for e in extras if e["name"] == "mono-color")
    assert entry["repo"] == "lanceyuu/mimiwork" and entry["path"] == "skills/store/mono-color"
    assert "monochrome" in entry["description"].lower() or "one-ink" in entry["description"].lower()
    # The store sees it like any other entry, ahead of the community copies.
    marketplace._index_cache = None
    found = marketplace.find("mono-color")
    assert found is not None and found["repo"] == "lanceyuu/mimiwork"
    assert any(r["name"] == "mono-color" for r in marketplace.search("monochrome poster", limit=10))
    # Installable within the store's own limits.
    files = [p for p in (ROOT / "skills" / "store" / "mono-color").rglob("*") if p.is_file()]
    assert len(files) <= marketplace._MAX_FILES
    assert sum(p.stat().st_size for p in files) <= marketplace._MAX_TOTAL_BYTES
