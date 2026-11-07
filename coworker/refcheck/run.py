"""One reference check, start to finish, and the plan for writing its fixes (spec
2026-11-07, steps 7 to 9 and "Writing the fixes").

The result is saved per file hash: opening the tab again costs nothing, and a fix can only
be written into exactly the file version it was checked against.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

from ..secrets import state_dir
from ..tools.office.docx_tools import _indexed_blocks, _para_text, word_level_ok
from ..tools.papers import STYLES
from . import reading
from .matching import loose
from .reading import Listing
from .verdicts import (
    REASONS,
    Lookups,
    Outcome,
    apply_spans,
    code,
    doi_form,
    group_of,
    look_up,
    make_fixes,
    mark_missing_dois,
)

KEEP_DAYS = 90
# Bumped whenever a saved result could hold a verdict or fix the current code would not
# make, so an old one is checked again instead of shown. 2: a DOI the model cut short
# could write a corrupt DOI; fix ids came from the model's order.
VERSION = 2


class NoModel(Exception):
    """The conversation has no engine to make the reading calls with."""


def _error(name: str) -> dict[str, Any]:
    return {"ok": False, "error": name}


def _folder(cache_dir: Optional[Path]) -> Path:
    return cache_dir or state_dir() / "refcheck"


def _load(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("ok") or data.get("version") != VERSION:
        return None
    return data if isinstance(data.get("counts"), dict) and isinstance(data.get("entries"), list) else None


def _save(path: Path, result: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # the result still shows; the next open just asks again


# digest -> [lock, callers holding or waiting for it]. One lock per file checked would only
# grow over a long session, so it goes once its last caller is done; counting waiters keeps
# a third caller from getting a fresh lock while a second still waits on the old one.
_locks: dict[str, list[Any]] = {}
_locks_guard = threading.Lock()


def _lock_for(digest: str) -> threading.Lock:
    with _locks_guard:
        entry = _locks.setdefault(digest, [threading.Lock(), 0])
        entry[1] += 1
        return entry[0]


def _release(digest: str) -> None:
    with _locks_guard:
        entry = _locks.get(digest)
        if entry is not None:
            entry[1] -= 1
            if entry[1] <= 0:
                _locks.pop(digest, None)


def check_file(
    target: Path,
    *,
    complete: Callable[[str, str], str],
    lookups: Lookups,
    fresh: bool = False,
    cached_only: bool = False,
    cache_dir: Optional[Path] = None,
) -> dict[str, Any]:
    try:
        data = target.read_bytes()
    except OSError:
        return _error("unreadable")
    digest = hashlib.sha256(data).hexdigest()
    saved = _folder(cache_dir) / f"{digest}.json"
    if not fresh:
        cached = _load(saved)
        # A result with lookups that failed (offline, OpenAlex's daily limit) is shown
        # when asked for, but never reused as the answer to a new check.
        if cached and (cached_only or not cached["counts"].get("couldnt")):
            return cached
    if cached_only:
        return {"ok": False, "cached": False}
    asked = time.time()
    lock = _lock_for(digest)
    try:
        with lock:
            # A check of this file that finished while this one waited is the answer, Check
            # again or not: a panel click and the chat tool must not pay twice.
            try:
                if saved.stat().st_mtime >= asked:
                    cached = _load(saved)
                    if cached and not cached["counts"].get("couldnt"):
                        return cached
            except OSError:
                pass
            result = _check(target, digest, complete, lookups)
            if result.get("ok"):
                _save(saved, result)
            return result
    finally:
        _release(digest)


def _safe_look_up(entry: Any, lookups: Lookups, style: str) -> Outcome:
    try:
        return look_up(entry, lookups, style)
    except Exception:  # one bad record must not lose the other entries' results
        return Outcome([code("lookup_failed")])


def _check(target: Path, digest: str, complete: Callable[[str, str], str], lookups: Lookups) -> dict[str, Any]:
    kind = target.suffix.lower().lstrip(".")
    try:
        listing = reading.load_docx(target) if kind == "docx" else reading.load_pdf(target)
    except Exception:
        return _error("unreadable")
    if listing.password:
        return _error("password")
    if listing.scan:
        return _error("scan")
    if not listing.paras:
        return _error("no_list")
    try:
        read = reading.read_entries(listing, complete)
    except NoModel:
        return _error("no_folder")
    except Exception:
        return _error("read_failed")
    if not read.entries:
        return _error("no_list")
    style = read.style if read.style in STYLES else "apa"
    with ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(lambda e: _safe_look_up(e, lookups, style), read.entries))
    mark_missing_dois(read.entries, outcomes)
    form = doi_form(read.entries)
    claims = Counter(k for e in read.entries for k in range(e.first, e.last + 1))
    rows = [_row(e, o, listing, claims, form) for e, o in zip(read.entries, outcomes)]
    counts = Counter(row["group"] for row in rows)
    return {
        "ok": True,
        "version": VERSION,
        "hash": digest,
        "checked_at": time.time(),
        "kind": listing.kind,
        "managed": listing.managed,
        "heading_found": listing.heading_found,
        "cut": listing.cut,
        "unread": read.unread,
        "not_checked": read.not_checked,
        "style": style,
        "counts": {"total": len(rows), **{g: counts.get(g, 0) for g in ("verified", "fix", "not_found", "retracted", "couldnt")}},
        "entries": rows,
    }


def _can_write(entry: Any, listing: Listing, claims: Counter) -> bool:
    if listing.kind != "docx" or listing.managed:
        return False
    if entry.first != entry.last or claims[entry.first] > 1:
        return False
    para = listing.paras[entry.first]
    if para.obj is None or para.index is None:
        return False
    # Fix spans are offsets in _para_text, where a tab or break reads differently from the
    # reading text; and the entry must be the whole paragraph, nothing more.
    return _para_text(para.obj) == para.text and loose(entry.text) == loose(para.text)


def _file_text(entry: Any, listing: Listing, claims: Counter) -> Optional[str]:
    """The file's own text for a Word entry that cannot be written, so a Copy suggestion
    never carries the model's retyped copy (its case, dashes and quotes only match loosely)."""
    if listing.kind != "docx" or any(claims[k] > 1 for k in range(entry.first, entry.last + 1)):
        return None
    joined = " ".join(p.text for p in listing.paras[entry.first : entry.last + 1])
    return joined if loose(joined) == loose(entry.text) else None


def _row(entry: Any, outcome: Outcome, listing: Listing, claims: Counter, form: str) -> dict[str, Any]:
    writable = _can_write(entry, listing, claims)
    para = listing.paras[entry.first] if writable else None
    text = para.text if para else (_file_text(entry, listing, claims) or entry.text)
    fixes = make_fixes(entry, outcome, text, form)
    group = group_of(outcome.codes)
    layout = False
    if fixes and para is not None:
        new_text = apply_spans(text, fixes)
        if new_text is not None and word_level_ok(para.obj, new_text):
            for fix in fixes:
                fix["writable"] = True
                fix["ticked"] = group != "retracted"  # first decide whether to cite it at all
        else:
            layout = True
    elif fixes and listing.kind == "docx" and not listing.managed:
        layout = True
    cand = outcome.match.cand if outcome.match else None
    extra: dict[str, Any] = {}
    if len(fixes) > 1 and not any(f["writable"] for f in fixes):
        # Each fix's own Copy text carries only that fix, so pasting one undoes another.
        combined = apply_spans(text, fixes)
        if combined is not None:
            extra["fixed_text"] = combined
    return {
        "id": entry.id,
        "paragraph": para.index if para else None,
        "text": text,
        "title": entry.title,
        "group": group,
        "codes": outcome.codes,
        "record": {"doi": cand.doi, "title": cand.title, "link": cand.link} if cand else None,
        "fixes": fixes,
        "suggestions": [{"text": outcome.suggestion}] if outcome.suggestion else [],
        "layout": layout,
        **extra,
    }


def plan_fixes(target: Path, ids: list[str], digest: str, cache_dir: Optional[Path] = None) -> dict[str, Any]:
    """The tracked-change edits for the ticked fixes, or the reason none can be written."""
    try:
        now = hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError:
        return _error("unreadable")
    result = _load(_folder(cache_dir) / f"{now}.json") if now == digest else None
    if result is None:
        return _error("changed")
    if result.get("managed"):
        return _error("managed")
    wanted = set(ids)
    known = {fix["id"] for row in result["entries"] for fix in row["fixes"]}
    if not wanted <= known:
        # An id this result never offered was ticked on another check's results: the
        # panel is showing something other than what is saved now.
        return _error("changed")
    by_para: dict[int, list[dict[str, Any]]] = {}
    for row in result["entries"]:
        for fix in row["fixes"]:
            if fix["id"] not in wanted:
                continue
            if not fix["writable"] or row["paragraph"] is None:
                return _error("not_writable")
            by_para.setdefault(row["paragraph"], []).append(fix)
    if not by_para:
        return _error("nothing")
    import docx

    blocks = _indexed_blocks(docx.Document(str(target)))
    edits = []
    for index, fixes in sorted(by_para.items()):
        para = blocks[index] if 0 <= index < len(blocks) else None
        new_text = apply_spans(_para_text(para), fixes) if para is not None else None
        if new_text is None:
            return _error("not_writable")
        edits.append({"index": index, "text": new_text, "reason": " ".join(REASONS[f["kind"]] for f in fixes)})
    return {"ok": True, "edits": edits, "count": sum(len(f) for f in by_para.values())}


def prune(cache_dir: Optional[Path] = None, days: int = KEEP_DAYS) -> None:
    cutoff = time.time() - days * 86400
    folder = _folder(cache_dir)
    for path in [*folder.glob("*.json"), *folder.glob("*.tmp")]:  # .tmp: a save cut short
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue
