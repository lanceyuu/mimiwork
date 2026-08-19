#!/usr/bin/env python3
"""Build the bundled skill-store index from the three community skill repos.

Usage:
    python scripts/build_skill_store_index.py /path/with/clones

Expects shallow clones of the three repos in the given directory; writes
``coworker/skills/store_index.json.gz``. Each entry pins the clone's HEAD sha
so installs download exactly the files that were indexed (a later force-push
can't swap the content behind an already-reviewed listing).

Rerun whenever refreshing the catalog:
    d=$(mktemp -d)
    for r in sickn33/agentic-awesome-skills ComposioHQ/awesome-claude-skills \
             addyosmani/agent-skills; do git -C "$d" clone --depth 1 https://github.com/$r; done
    python scripts/build_skill_store_index.py "$d"
"""

from __future__ import annotations

import gzip
import json
import re
import subprocess
import sys
from pathlib import Path

REPOS = {
    "agentic-awesome-skills": "sickn33/agentic-awesome-skills",
    "awesome-claude-skills": "ComposioHQ/awesome-claude-skills",
    "agent-skills": "addyosmani/agent-skills",
}

_DESC_CAP = 280


def _frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    try:
        import yaml

        data = yaml.safe_load(m.group(1)) or {}
        return {k: str(v) for k, v in data.items() if isinstance(k, str)}
    except Exception:
        out: dict[str, str] = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                out[k.strip()] = v.strip().strip("\"'")
        return out


def main(base: Path) -> None:
    entries = []
    for folder, repo in REPOS.items():
        root = base / folder
        if not root.is_dir():
            print(f"missing clone: {root}", file=sys.stderr)
            continue
        sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        for md in sorted(root.rglob("SKILL.md")):
            rel = md.parent.relative_to(root).as_posix()
            try:
                fm = _frontmatter(md.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            name = (fm.get("name") or md.parent.name).strip()
            desc = " ".join((fm.get("description") or "").split())[:_DESC_CAP]
            if not name or not desc:
                continue  # a skill nobody can identify or pick is dead weight
            entries.append(
                {
                    "name": name,
                    "description": desc,
                    "repo": repo,
                    "path": rel,
                    "ref": sha,
                }
            )
    out = Path(__file__).parent.parent / "coworker" / "skills" / "store_index.json.gz"
    with gzip.open(out, "wt", encoding="utf-8") as fh:
        json.dump(entries, fh, separators=(",", ":"))
    print(f"{len(entries)} skills → {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
