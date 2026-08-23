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


# People type requests, not keywords ("clean up my downloads folder"). These words carry
# no signal against an index of skill names, and leaving them in drags the ranking toward
# whatever happens to mention them.
_STOPWORDS = frozenset(
    """the a an and or of for to in on with my me i you your our it this that
    is are be can help please how do does make made get got want need using use
    up down out off over into from at as by""".split()
)


def _query_tokens(query: str) -> list[str]:
    tokens = _tokens(query or "")
    trimmed = [t for t in tokens if t not in _STOPWORDS]
    return trimmed or tokens  # a query that is ALL stopwords still deserves a try


def _score(entry: dict[str, Any], q: list[str], query_lower: str) -> float:
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
    # The words in the typed order, as a phrase, are the strongest signal short of an
    # exact name — and the comparison has to ignore the separators skill names are made
    # of, or "seo audit" never matches the skill actually called "seo-audit".
    flat_name = " ".join(_tokens(name))
    if len(q) > 1 and query_lower:
        phrase = " ".join(q)
        if phrase in flat_name:
            score += 8.0
        elif phrase in " ".join(_tokens(desc)):
            score += 4.0
    if query_lower and (query_lower == name or " ".join(q) == flat_name):
        score += 100.0
    if score > 0:
        # A skill nobody bothered to describe is worse than one that is described,
        # all else equal — this only ever breaks ties.
        score += min(len(desc), 240) / 400.0
    return score


def _rank(
    scored: list[tuple[float, dict[str, Any]]], limit: int, offset: int
) -> tuple[list[dict[str, Any]], int]:
    """Collapse the same skill listed by several collections into one row (keeping the
    best-scoring copy, counting the rest), then page it."""
    best: dict[str, tuple[float, dict[str, Any]]] = {}
    copies: dict[str, int] = {}
    for score, entry in scored:
        key = entry["name"].lower()
        copies[key] = copies.get(key, 0) + 1
        if key not in best or score > best[key][0]:
            best[key] = (score, entry)
    rows = sorted(best.values(), key=lambda kv: (-kv[0], kv[1]["name"]))
    total = len(rows)
    page = rows[offset : offset + limit] if limit > 0 else rows[offset:]
    return (
        [
            {**entry, "also_in": max(0, copies[entry["name"].lower()] - 1)}
            for _score, entry in page
        ],
        total,
    )


def search(query: str, *, limit: int = 30, offset: int = 0) -> list[dict[str, Any]]:
    """Rank the index by token overlap (name hits weigh 3× description hits, a
    whole-phrase hit and an exact-name match top everything). Empty query → nothing:
    8,400 rows is a search problem — see `browse` for the no-query path."""
    return search_page(query, limit=limit, offset=offset)["results"]


def search_page(
    query: str, *, limit: int = 30, offset: int = 0
) -> dict[str, Any]:
    """`search` with the numbers the UI needs: how many matched, and whether the
    list it is showing is the whole story."""
    q = _query_tokens(query)
    if not q:
        return {"results": [], "total": 0, "offset": 0}
    query_lower = (query or "").strip().lower()
    scored = [
        (score, entry)
        for entry in _load_index()
        if (score := _score(entry, q, query_lower)) > 0
    ]
    results, total = _rank(scored, limit, max(0, offset))
    return {"results": results, "total": total, "offset": max(0, offset)}


# ── browsing ─────────────────────────────────────────────────────────────────
# An empty search box used to show an empty page, which reads as "there is nothing
# here" in front of 8,400 skills. These shelves are the browsing path: hand-written
# term sets, matched against the same index, so no extra data has to ship.

CATEGORIES: list[dict[str, Any]] = [
    {"key": "writing", "label": "Writing & editing",
     "terms": ["writing", "editing", "copywriting", "proofread", "style", "prose"]},
    {"key": "research", "label": "Research",
     "terms": ["research", "literature", "paper", "citation", "academic", "survey"]},
    {"key": "data", "label": "Data & analysis",
     "terms": ["data", "analysis", "statistics", "excel", "spreadsheet", "visualization"]},
    {"key": "slides", "label": "Slides & docs",
     "terms": ["slides", "presentation", "powerpoint", "document", "report", "pdf"]},
    {"key": "email", "label": "Email & messages",
     "terms": ["email", "inbox", "message", "slack", "outreach", "reply"]},
    {"key": "planning", "label": "Planning & tasks",
     "terms": ["planning", "task", "project", "roadmap", "meeting", "notes"]},
    {"key": "web", "label": "Web & research online",
     "terms": ["web", "browser", "scrape", "search", "crawl", "website"]},
    {"key": "coding", "label": "Coding",
     "terms": ["code", "debug", "refactor", "test", "git", "review"]},
    {"key": "design", "label": "Design & media",
     "terms": ["design", "image", "video", "figma", "ui", "brand"]},
]

_browse_cache: dict[str, tuple[list[dict[str, Any]], int]] = {}


def categories() -> list[dict[str, Any]]:
    """The shelves, each with how many skills sit on it."""
    return [
        {"key": c["key"], "label": c["label"], "count": browse_page(c["key"], limit=0)["total"]}
        for c in CATEGORIES
    ]


def browse_page(category: str, *, limit: int = 24, offset: int = 0) -> dict[str, Any]:
    """Everything on one shelf, best-described first. Cached: the index never changes
    inside a run, so a shelf is computed once however often the user flips back to it."""
    spec = next((c for c in CATEGORIES if c["key"] == category), None)
    if spec is None:
        return {"results": [], "total": 0, "offset": 0}
    cached = _browse_cache.get(category)
    if cached is None:
        terms = set(spec["terms"])
        scored: list[tuple[float, dict[str, Any]]] = []
        for entry in _load_index():
            words = set(_tokens(entry["name"])) | set(_tokens(entry["description"]))
            hits = terms & words
            if hits:
                # Shelf order: how squarely it belongs, then how well it explains itself.
                scored.append((len(hits) * 4.0 + min(len(entry["description"]), 240) / 60.0, entry))
        rows, total = _rank(scored, 0, 0)
        cached = (rows, total)
        _browse_cache[category] = cached
    rows, total = cached
    start = max(0, offset)
    page = rows[start : start + limit] if limit > 0 else []
    return {"results": page, "total": total, "offset": start}


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


def preview(name: str, repo: Optional[str] = None) -> dict[str, Any]:
    """Read a listed skill's SKILL.md without installing it.

    Installing used to be the only way to find out what a skill actually tells the agent
    to do. This fetches just the one file (raw, at the pinned commit — no GitHub API
    call, so it doesn't burn the rate limit the installer needs), and reports the same
    red flags the installer would refuse on, before anything lands on disk.
    """
    entry = find(name, repo)
    if entry is None:
        return {"ok": False, "error": f"'{name}' is not in the skill store."}
    url = (
        f"https://raw.githubusercontent.com/{entry['repo']}/{entry['ref']}/"
        f"{entry['path'].rstrip('/')}/SKILL.md"
    )
    try:
        raw = _http_bytes(url).decode("utf-8", errors="replace")
    except error.HTTPError as e:
        if e.code == 404:
            return {"ok": False, "error": f"'{name}' has no SKILL.md at its listed path."}
        return {"ok": False, "error": f"GitHub fetch failed ({e.code})."}
    except Exception as e:
        return {"ok": False, "error": f"GitHub unreachable: {e}"}

    description, allowed_tools, body = entry["description"], [], raw
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", raw, re.S)
    if m:
        body = m.group(2).lstrip("\n")
        try:
            import yaml

            data = yaml.safe_load(m.group(1)) or {}
        except Exception:
            data = {}
        if isinstance(data, dict):
            description = " ".join(str(data.get("description") or description).split())
            tools = data.get("allowed-tools") or data.get("allowed_tools") or []
            if isinstance(tools, str):
                tools = [t.strip() for t in tools.split(",")]
            allowed_tools = [str(t).strip() for t in tools if str(t).strip()]

    flag = _RED_FLAGS.search(raw)
    excerpt = body.strip()
    truncated = len(excerpt) > 4000
    return {
        "ok": True,
        "name": name,
        "repo": entry["repo"],
        "description": description,
        "allowed_tools": allowed_tools,
        "instructions": excerpt[:4000],
        "truncated": truncated,
        "flagged": bool(flag),
        "flag_hit": flag.group(0) if flag else "",
        "url": f"https://github.com/{entry['repo']}/tree/{entry['ref']}/{entry['path']}",
        "ref": entry["ref"],
    }


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
