"""The skill store — browse ~7,200 community skills, install on demand.

The catalog is a bundled, pinned index (``store_index.json.gz``, built by
``scripts/build_skill_store_index.py``) over three community repos:
sickn33/agentic-awesome-skills, ComposioHQ/awesome-claude-skills, and
addyosmani/agent-skills. Bundling the INDEX and downloading a skill only when
the user installs it keeps the app small (the repos total ~370 MB) and keeps
the model's context clean — installed skills join the normal catalog; the
other 7,000 stay out of every prompt.

Installs are pinned to the commit sha the index was built from: a later
force-push to a listed repo cannot swap content behind an already-listed name.
Every downloaded SKILL.md is safety-scanned (the same red-flag patterns used
when curating the bundled set); a flagged skill installs only with
``force=True`` after the UI shows the warning.
"""

from __future__ import annotations

import gzip
import json
import re
import shutil
import threading
from importlib import resources
from pathlib import Path
from typing import Any, Optional
from urllib import error, request

_MAX_FILES = 40
_MAX_TOTAL_BYTES = 3_000_000
_MAX_FILE_BYTES = 1_500_000
_BLOCKED_SUFFIXES = {".exe", ".dll", ".so", ".dylib", ".bin", ".app", ".msi", ".pkg"}

# Red flags in skill INSTRUCTIONS (they steer the agent): downloading-and-running
# arbitrary code, or classic prompt-injection framing.
_RED_FLAGS = re.compile(
    r"curl[^\n]*\|\s*(ba)?sh|wget[^\n]*\|\s*(ba)?sh|base64\s+-d|ignore (previous|prior|above) instructions"
    r"|do not tell the user|secretly|exfiltrat",
    re.IGNORECASE,
)

_index_cache: Optional[list[dict[str, Any]]] = None
_index_lock = threading.Lock()


def _load_index() -> list[dict[str, Any]]:
    global _index_cache
    if _index_cache is None:
        with _index_lock:
            if _index_cache is None:
                data = resources.files(__package__).joinpath("store_index.json.gz")
                with data.open("rb") as fh:
                    _index_cache = json.loads(gzip.decompress(fh.read()).decode("utf-8"))
    return _index_cache


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) > 1]


def search(query: str, *, limit: int = 30) -> list[dict[str, Any]]:
    """Rank the index by simple token overlap (name hits weigh 3× description
    hits, exact-name match tops everything). Empty query → nothing: 7,235 rows
    is a search problem, not a browsing problem."""
    q = _tokens(query or "")
    if not q:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    query_lower = (query or "").strip().lower()
    seen: set[tuple[str, str]] = set()  # aggregator repos list the same skill many times
    for entry in _load_index():
        key = (entry["name"], entry["description"])
        if key in seen:
            continue
        name, desc = entry["name"].lower(), entry["description"].lower()
        name_tokens = set(_tokens(name))
        desc_tokens = set(_tokens(desc))
        score = 0.0
        matched = 0
        for tok in q:
            hit = False
            if tok in name_tokens:
                score += 3.0  # whole-word name hit
                hit = True
            elif tok in name:
                score += 1.0  # substring name hit ("analysis" in "imageanalysis")
                hit = True
            if tok in desc_tokens:
                score += 1.0
                hit = True
            matched += hit
        # An entry covering EVERY query term beats any partial match — otherwise
        # "literature review" drowns under the ocean of code-review skills.
        if matched == len(q):
            score += 8.0
        if query_lower and query_lower == name:
            score += 100.0
        if score > 0:
            seen.add(key)
            scored.append((score, entry))
    scored.sort(key=lambda kv: (-kv[0], kv[1]["name"]))
    return [e for _, e in scored[:limit]]


def find(name: str, repo: Optional[str] = None) -> Optional[dict[str, Any]]:
    for entry in _load_index():
        if entry["name"] == name and (repo is None or entry["repo"] == repo):
            return entry
    return None


# ── install ──────────────────────────────────────────────────────────────────


def _http_json(url: str) -> Any:
    req = request.Request(url, headers={"User-Agent": "MimiWork-skill-store"})
    with request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _http_bytes(url: str) -> bytes:
    req = request.Request(url, headers={"User-Agent": "MimiWork-skill-store"})
    with request.urlopen(req, timeout=60) as r:
        return r.read()


def _list_files(repo: str, path: str, ref: str) -> list[dict[str, Any]]:
    """All files under the skill folder via the GitHub contents API (recursive)."""
    out: list[dict[str, Any]] = []
    stack = [path]
    while stack and len(out) <= _MAX_FILES:
        current = stack.pop()
        listing = _http_json(
            f"https://api.github.com/repos/{repo}/contents/{current}?ref={ref}"
        )
        if isinstance(listing, dict):
            listing = [listing]
        for item in listing:
            if item.get("type") == "dir":
                stack.append(item["path"])
            elif item.get("type") == "file":
                out.append(item)
    return out


def _flatten_frontmatter(text: str, name: str) -> str:
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        return text
    body = m.group(2).lstrip("\n")
    desc = ""
    try:
        import yaml

        data = yaml.safe_load(m.group(1)) or {}
        desc = " ".join(str(data.get("description") or "").split())
    except Exception:
        for line in m.group(1).splitlines():
            if line.strip().lower().startswith("description:"):
                desc = line.split(":", 1)[1].strip().strip("\"'")
                break
    return f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}"


def install(
    name: str,
    global_dir: Path,
    *,
    repo: Optional[str] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Download one listed skill into the user's global skills folder.

    Returns {ok} on success; {ok: False, error} on any refusal — including the
    safety flag, which the caller surfaces so the user can decide (`force`).
    """
    entry = find(name, repo)
    if entry is None:
        return {"ok": False, "error": f"'{name}' is not in the skill store."}
    target = Path(global_dir) / name
    if target.exists():
        return {"ok": False, "error": f"A skill named '{name}' is already installed."}

    try:
        files = _list_files(entry["repo"], entry["path"], entry["ref"])
    except error.HTTPError as e:
        if e.code == 403:
            return {
                "ok": False,
                "error": "GitHub's rate limit was hit — try again in a few minutes.",
            }
        return {"ok": False, "error": f"GitHub listing failed ({e.code})."}
    except Exception as e:
        return {"ok": False, "error": f"GitHub unreachable: {e}"}

    if len(files) > _MAX_FILES:
        return {"ok": False, "error": f"'{name}' has too many files (> {_MAX_FILES})."}
    total = sum(int(f.get("size") or 0) for f in files)
    if total > _MAX_TOTAL_BYTES:
        return {"ok": False, "error": f"'{name}' is too large ({total // 1024} KB)."}

    prefix = entry["path"].rstrip("/") + "/"
    staged: list[tuple[Path, bytes]] = []
    skill_md: Optional[str] = None
    try:
        for f in files:
            rel = f["path"]
            rel = rel[len(prefix):] if rel.startswith(prefix) else Path(rel).name
            rel_path = Path(rel)
            # Layout safety: nothing may escape the skill folder or smuggle a binary.
            if rel_path.is_absolute() or ".." in rel_path.parts:
                continue
            if rel_path.suffix.lower() in _BLOCKED_SUFFIXES:
                continue
            if int(f.get("size") or 0) > _MAX_FILE_BYTES:
                continue
            content = _http_bytes(
                f.get("download_url")
                or f"https://raw.githubusercontent.com/{entry['repo']}/{entry['ref']}/{f['path']}"
            )
            if rel_path.as_posix() == "SKILL.md":
                skill_md = content.decode("utf-8", errors="replace")
            staged.append((rel_path, content))
    except Exception as e:
        return {"ok": False, "error": f"download failed: {e}"}

    if skill_md is None:
        return {"ok": False, "error": f"'{name}' has no SKILL.md at its listed path."}
    if not force and _RED_FLAGS.search(skill_md):
        return {
            "ok": False,
            "flagged": True,
            "error": (
                "This skill's instructions contain patterns worth a human look "
                "(e.g. piping downloads to a shell). Review it on GitHub and "
                "install with force if it's fine."
            ),
            "url": f"https://github.com/{entry['repo']}/tree/{entry['ref']}/{entry['path']}",
        }

    skill_md = _flatten_frontmatter(skill_md, name).rstrip() + (
        f"\n\n---\n*Installed from [{entry['repo']}](https://github.com/{entry['repo']}) "
        f"via the MimiWork skill store (pinned to {entry['ref'][:12]}).*\n"
    )
    try:
        for rel_path, content in staged:
            dest = target / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            if rel_path.as_posix() == "SKILL.md":
                dest.write_text(skill_md, encoding="utf-8")
            else:
                dest.write_bytes(content)
    except OSError as e:
        shutil.rmtree(target, ignore_errors=True)
        return {"ok": False, "error": f"could not write the skill: {e}"}
    return {"ok": True, "name": name, "files": len(staged)}
