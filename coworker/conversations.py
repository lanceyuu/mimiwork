"""ConversationStore — global, file-backed session storage shared by all surfaces.

Layout under a base dir (default `~/.config/coworker/`):
  coworker.db                  SQLite index: sessions(id → project, title, n_msgs), workspaces, memory
  conversations/<id>.jsonl     append-only message log, one file per conversation

Writes append only the new messages each turn (no rewriting history). Legacy rows that
stored messages inline are lazily migrated to a .jsonl on first load/save.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
from pathlib import Path
from typing import Optional

from .sessions import SessionRecord


def _load_roots(raw: Optional[str]) -> list[dict]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _load_grants(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _display_title(row: sqlite3.Row) -> Optional[str]:
    """Title precedence for every read path: a manual rename (renamed=1) always wins,
    then the generated auto_title, then the first-line snapshot `save()` wrote."""
    if row["renamed"]:
        return row["title"]
    return row["auto_title"] or row["title"]


def title_from(messages: list[dict]) -> str:
    from .attachments import content_to_text

    for m in messages:
        if m.get("role") == "user":
            text = content_to_text(m.get("content"), image_placeholder="").strip()
            if text:
                return text.splitlines()[0][:60]
    return "New session"


class ConversationStore:
    def __init__(self, base_dir: str | Path) -> None:
        self.base = Path(base_dir).expanduser()
        self.base.mkdir(parents=True, exist_ok=True)
        self.conv_dir = self.base / "conversations"
        self.conv_dir.mkdir(exist_ok=True)
        self.db_path = self.base / "coworker.db"

        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY, workspace TEXT, model TEXT, mode TEXT,
                title TEXT, agent TEXT DEFAULT 'cowork', n_msgs INTEGER DEFAULT 0, messages TEXT,
                extra_roots TEXT, pinned INTEGER DEFAULT 0, archived INTEGER DEFAULT 0,
                origin TEXT, origin_label TEXT,
                auto_title TEXT, renamed INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS workspaces (
                path TEXT PRIMARY KEY, last_used TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS store_meta (
                key TEXT PRIMARY KEY, value TEXT
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                emoji TEXT,
                pinned INTEGER DEFAULT 0,
                archived INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS tool_runs (
                session_id TEXT NOT NULL,
                message_index INTEGER NOT NULL,
                call_ordinal INTEGER NOT NULL,
                call_id TEXT,
                tool_name TEXT NOT NULL,
                arguments_hash TEXT NOT NULL,
                recovery_policy TEXT NOT NULL,
                state TEXT NOT NULL,
                result TEXT,
                result_status TEXT,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (session_id, message_index, call_ordinal)
            );
            """)
        for ddl in (
            "ALTER TABLE sessions ADD COLUMN title TEXT",
            "ALTER TABLE sessions ADD COLUMN n_msgs INTEGER DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN agent TEXT DEFAULT 'cowork'",
            "ALTER TABLE sessions ADD COLUMN extra_roots TEXT",
            "ALTER TABLE sessions ADD COLUMN pinned INTEGER DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN archived INTEGER DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN origin TEXT",
            # Project metadata (PROJECTS, 2026-08-21): a project IS a workspace row.
            "ALTER TABLE workspaces ADD COLUMN name TEXT",
            "ALTER TABLE workspaces ADD COLUMN emoji TEXT",
            "ALTER TABLE workspaces ADD COLUMN pinned INTEGER DEFAULT 0",
            "ALTER TABLE workspaces ADD COLUMN archived INTEGER DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN origin_label TEXT",
            "ALTER TABLE sessions ADD COLUMN auto_title TEXT",
            "ALTER TABLE sessions ADD COLUMN renamed INTEGER DEFAULT 0",
            "ALTER TABLE sessions ADD COLUMN grants TEXT",
            "ALTER TABLE sessions ADD COLUMN compaction TEXT",
            # A project is a GROUP, not a folder (2026-08-31). It used to be the
            # workspace path itself, which meant "which project is this in" and
            # "where do its files go" were the same answer and you could not have
            # one without the other. project_id carries membership on its own;
            # `workspace` keeps doing only its real job.
            "ALTER TABLE sessions ADD COLUMN project_id TEXT",
        ):
            try:
                self._conn.execute(ddl)
            except sqlite3.OperationalError:
                pass
        self._conn.commit()
        self._backfill_counts()
        self._migrate_folder_projects_to_groups()

    # -- file helpers -----------------------------------------------------------
    def _file(self, sid: str) -> Path:
        return self.conv_dir / f"{sid}.jsonl"

    def _read_jsonl(self, sid: str) -> Optional[list[dict]]:
        path = self._file(sid)
        if not path.exists():
            return None
        raw_bytes = path.read_bytes()
        raw_lines = [line for line in raw_bytes.splitlines() if line.strip()]
        messages: list[dict] = []
        for index, raw in enumerate(raw_lines):
            try:
                messages.append(json.loads(raw.decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                # A process can die between write(2) and fsync(2), leaving only the
                # final JSON object torn.  Preserve the valid prefix; corruption in
                # the middle is not a crash tail and must remain visible.
                if index == len(raw_lines) - 1 and not raw_bytes.endswith(b"\n"):
                    break
                raise
        return messages

    def _count(self, sid: str) -> int:
        return len(self._read_jsonl(sid) or [])

    def _append(self, sid: str, messages: list[dict]) -> None:
        path = self._file(sid)
        needs_separator = False
        if path.exists():
            raw_bytes = path.read_bytes()
            raw_lines = [line for line in raw_bytes.splitlines() if line.strip()]
            if raw_lines:
                try:
                    json.loads(raw_lines[-1].decode("utf-8"))
                    needs_separator = not raw_bytes.endswith(b"\n")
                except (UnicodeDecodeError, json.JSONDecodeError):
                    # Repair a previously tolerated torn tail before appending; otherwise
                    # the new valid object would be glued to corrupt bytes and lost too.
                    self._write_all(sid, self._read_jsonl(sid) or [])
        with open(path, "a", encoding="utf-8") as f:
            if needs_separator:
                f.write("\n")
            for m in messages:
                f.write(json.dumps(m) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _write_all(self, sid: str, messages: list[dict]) -> None:
        target = self._file(sid)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{sid}.", suffix=".tmp", dir=self.conv_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                for message in messages:
                    stream.write(json.dumps(message) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            # Persist the directory entry where the platform supports directory fsync.
            try:
                directory_fd = os.open(
                    self.conv_dir,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                )
            except OSError:
                directory_fd = None
            if directory_fd is not None:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def _migrate_folder_projects_to_groups(self) -> None:
        """Turn each folder-backed project into a group, once.

        A project used to BE a workspace folder, so membership was "your workspace
        equals the project's path". Groups replace that, and this carries the
        existing ones over: every workspace that has real sessions becomes a project
        row, and those sessions get its project_id.

        `sessions.workspace` is deliberately NOT touched. It still says where the
        session's files live, which must not change because the way they are
        ORGANISED did. Nothing moves on disk.

        Idempotent: it only considers sessions whose project_id is still NULL, so a
        session later dragged out of its group is not silently dragged back in on the
        next start.
        """
        import uuid as _uuid

        with self._lock:
            # Exactly once, ever — recorded by a flag rather than inferred from the
            # data. Inferring it ("no groups yet?") re-ran the migration on every
            # start, so a session the user deliberately dragged OUT of its group was
            # silently filed straight back in on the next launch.
            done = self._conn.execute(
                "SELECT value FROM store_meta WHERE key='folder_projects_migrated'"
            ).fetchone()
            if done is not None:
                return
            rows = self._conn.execute(
                # A per-conversation scratch directory is named after the session that
                # owns it (`<scratch base>/<session id>`), so it is that session's
                # private working area and never a project. Excluded by that exact
                # shape rather than by guessing at path prefixes — the store must not
                # need to know where the manager puts scratch.
                "SELECT s.workspace AS path, COUNT(*) AS n FROM sessions s "
                "WHERE s.project_id IS NULL AND s.workspace IS NOT NULL "
                "  AND s.workspace != '' AND s.session_id NOT LIKE '\\_\\_%' ESCAPE '\\' "
                "  AND s.workspace NOT LIKE '%/' || s.session_id "
                "  AND s.workspace NOT LIKE '%\\' || s.session_id "
                "GROUP BY s.workspace",
                (),
            ).fetchall()
            meta = {
                r["path"]: r
                for r in self._conn.execute(
                    "SELECT path, name, emoji, pinned, archived FROM workspaces"
                ).fetchall()
            }
            for row in rows:
                path = row["path"]
                if self._is_scratch_like(path):
                    continue  # a per-conversation scratch dir was never a project
                m = meta.get(path)
                name = (m["name"] if m and m["name"] else "") or Path(path).name or path
                pid = f"grp_{_uuid.uuid4().hex[:12]}"
                self._conn.execute(
                    "INSERT INTO projects (id, name, emoji, pinned, archived) VALUES (?,?,?,?,?)",
                    (
                        pid,
                        name[:80],
                        (m["emoji"] if m else "") or "",
                        int(bool(m["pinned"])) if m else 0,
                        int(bool(m["archived"])) if m else 0,
                    ),
                )
                self._conn.execute(
                    "UPDATE sessions SET project_id=? WHERE workspace=? AND project_id IS NULL",
                    (pid, path),
                )
            self._conn.execute(
                "INSERT OR REPLACE INTO store_meta (key, value) VALUES ('folder_projects_migrated','1')"
            )
            self._conn.commit()

    @staticmethod
    def _is_scratch_like(path: str) -> bool:
        """Machinery folders that were never projects.

        `__`-prefixed names are MimiWork's own (an automation's `__task__…` working
        directory, for instance). Per-session scratch dirs are excluded by the query
        above instead, which matches them exactly rather than by naming convention.
        """
        name = Path(str(path or "")).name
        return name.startswith("__") or name.startswith("session-")

    def _backfill_counts(self) -> None:
        """One-time per session: move any inline blob into a .jsonl and persist
        title + n_msgs in the index. Skips already-migrated rows on later startups."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT session_id, messages, n_msgs, title FROM sessions"
            ).fetchall()
            for row in rows:
                sid = row["session_id"]
                jsonl = self._file(sid)
                if jsonl.exists() and row["title"] and row["n_msgs"]:
                    continue  # already migrated
                if jsonl.exists():
                    messages = self._read_jsonl(sid) or []
                elif row["messages"]:
                    try:
                        messages = json.loads(row["messages"])
                    except json.JSONDecodeError:
                        messages = []
                    if messages:
                        self._append(sid, messages)
                    self._conn.execute(
                        "UPDATE sessions SET messages = NULL WHERE session_id = ?",
                        (sid,),
                    )
                else:
                    messages = []
                self._conn.execute(
                    "UPDATE sessions SET n_msgs = ?, title = ? WHERE session_id = ?",
                    (len(messages), row["title"] or title_from(messages), sid),
                )
            self._conn.commit()

    # -- API --------------------------------------------------------------------
    def save(self, record: SessionRecord) -> None:
        sid = record.session_id
        with self._lock:
            # lazily migrate a legacy inline blob into the .jsonl
            if not self._file(sid).exists():
                row = self._conn.execute(
                    "SELECT messages FROM sessions WHERE session_id = ?", (sid,)
                ).fetchone()
                if row and row["messages"]:
                    try:
                        legacy = json.loads(row["messages"])
                    except json.JSONDecodeError:
                        legacy = []
                    if legacy:
                        self._append(sid, legacy)

            existing = self._count(sid)
            if len(record.messages) > existing:
                self._append(sid, record.messages[existing:])
            elif len(record.messages) < existing:  # rare; not append-only
                self._write_all(sid, record.messages)

            title = record.title or title_from(record.messages)
            self._conn.execute(
                """
                INSERT INTO sessions (session_id, workspace, model, mode, title, agent, n_msgs, messages, extra_roots, grants, compaction, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id) DO UPDATE SET
                    workspace = excluded.workspace, model = excluded.model, mode = excluded.mode,
                    title = COALESCE(sessions.title, excluded.title), agent = excluded.agent,
                    n_msgs = excluded.n_msgs, messages = NULL, extra_roots = excluded.extra_roots,
                    grants = excluded.grants, compaction = excluded.compaction,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    sid,
                    record.workspace,
                    record.model,
                    record.mode,
                    title,
                    record.agent,
                    len(record.messages),
                    json.dumps(record.extra_roots or []),
                    json.dumps(record.grants or {}),
                    json.dumps(record.compaction or {}),
                ),
            )
            self._conn.commit()
        self.touch_workspace(record.workspace)

    def load(self, session_id: str) -> Optional[SessionRecord]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if not row:
            return None
        messages = self._read_jsonl(session_id)
        if messages is None:
            try:
                messages = json.loads(row["messages"] or "[]")
            except json.JSONDecodeError:
                messages = []
        return SessionRecord(
            session_id=session_id,
            workspace=row["workspace"],
            model=row["model"],
            mode=row["mode"],
            messages=messages,
            title=_display_title(row),
            agent=row["agent"] or "cowork",
            message_count=len(messages),
            updated_at=row["updated_at"],
            extra_roots=_load_roots(
                row["extra_roots"] if "extra_roots" in row.keys() else None
            ),
            grants=_load_grants(row["grants"] if "grants" in row.keys() else None),
            # Auto-compaction state (OPE-27) — same defensive parse as grants.
            compaction=_load_grants(
                row["compaction"] if "compaction" in row.keys() else None
            ),
            pinned=bool(row["pinned"]),
            archived=bool(row["archived"]),
            origin=row["origin"],
            origin_label=row["origin_label"],
            project_id=row["project_id"] if "project_id" in row.keys() else None,
        )

    def fork(self, session_id: str) -> Optional[str]:
        """Branch a conversation: copy the transcript + scope (workspace, extra
        roots, grants, compaction) under a fresh id so the user can try another
        direction without losing the original. Returns the new id, or None when
        the source doesn't exist."""
        src = self.load(session_id)
        if src is None:
            return None
        import uuid

        new_id = uuid.uuid4().hex
        self.save(
            SessionRecord(
                session_id=new_id,
                workspace=src.workspace,
                model=src.model,
                mode=src.mode,
                messages=src.messages,
                title=f"Fork of {src.title or 'session'}",
                agent=src.agent,
                extra_roots=src.extra_roots,
                grants=src.grants,
                compaction=src.compaction,
            )
        )
        # Provenance rides the origin fields (save() doesn't touch them).
        self.set_origin(new_id, "fork", src.title or "")
        return new_id

    def set_extra_roots(self, session_id: str, extra_roots: list[dict]) -> None:
        """Persist just the session's added folders, independent of its message log — used when
        the user adds/removes a folder (which may happen with no active engine)."""
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET extra_roots = ?, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (json.dumps(extra_roots or []), session_id),
            )
            self._conn.commit()

    def list(self, *, workspace: Optional[str] = None) -> list[SessionRecord]:
        with self._lock:
            if workspace is None:
                rows = self._conn.execute(
                    "SELECT * FROM sessions ORDER BY pinned DESC, updated_at DESC"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM sessions WHERE workspace = ? ORDER BY pinned DESC, updated_at DESC",
                    (workspace,),
                ).fetchall()
        return [
            SessionRecord(
                session_id=r["session_id"],
                workspace=r["workspace"],
                model=r["model"],
                mode=r["mode"],
                messages=[],
                title=_display_title(r),
                agent=r["agent"] or "cowork",
                message_count=r["n_msgs"] or 0,
                updated_at=r["updated_at"],
                pinned=bool(r["pinned"]),
                archived=bool(r["archived"]),
                origin=r["origin"],
                origin_label=r["origin_label"],
                project_id=r["project_id"],
            )
            for r in rows
        ]

    def touch_workspace(self, path: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO workspaces (path, last_used) VALUES (?, CURRENT_TIMESTAMP) "
                "ON CONFLICT(path) DO UPDATE SET last_used = CURRENT_TIMESTAMP",
                (path,),
            )
            self._conn.commit()

    def recent_workspaces(self, limit: int = 20) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT path FROM workspaces ORDER BY last_used DESC LIMIT ?", (limit,)
            ).fetchall()
        return [r["path"] for r in rows]

    def canonicalize_workspaces(self) -> None:
        with self._lock:
            for (ws,) in self._conn.execute(
                "SELECT DISTINCT workspace FROM sessions WHERE workspace IS NOT NULL"
            ).fetchall():
                real = os.path.realpath(ws)
                if real != ws:
                    self._conn.execute(
                        "UPDATE sessions SET workspace = ? WHERE workspace = ?",
                        (real, ws),
                    )
            latest: dict[str, sqlite3.Row] = {}
            for row in self._conn.execute("SELECT * FROM workspaces").fetchall():
                real = os.path.realpath(row["path"])
                if real not in latest or (row["last_used"] or "") > (
                    latest[real]["last_used"] or ""
                ):
                    latest[real] = row
            self._conn.execute("DELETE FROM workspaces")
            for path, row in latest.items():
                # Project metadata rides along — collapsing /tmp vs /private/tmp must
                # never drop a name, emoji, pin or archive flag.
                self._conn.execute(
                    "INSERT OR REPLACE INTO workspaces "
                    "(path, last_used, name, emoji, pinned, archived) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        path,
                        row["last_used"],
                        row["name"],
                        row["emoji"],
                        row["pinned"] or 0,
                        row["archived"] or 0,
                    ),
                )
            self._conn.commit()

    # -- projects (a project is a workspace row + display metadata) --------------
    _PROJECT_FIELDS = ("name", "emoji", "pinned", "archived")

    # -- projects as groups (2026-08-31) ---------------------------------------
    # A project groups sessions and nothing else: no path, no folder, no bearing on
    # where a session writes. Membership is `sessions.project_id`.

    def create_project(self, name: str, emoji: str = "") -> dict:
        import uuid as _uuid

        pid = f"grp_{_uuid.uuid4().hex[:12]}"
        with self._lock:
            self._conn.execute(
                "INSERT INTO projects (id, name, emoji) VALUES (?,?,?)",
                (pid, (name or "New project")[:80], emoji or ""),
            )
            self._conn.commit()
        return {"id": pid, "name": (name or "New project")[:80], "emoji": emoji or ""}

    def list_projects(self) -> list[dict]:
        """Every group with its live session count, most recently active first.

        The count and last_activity come from the member sessions, so a group that
        has been emptied sorts to the bottom rather than pretending to be current.
        Archived sessions do not count toward the badge — the group would look busy
        while showing nothing when opened.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT p.id, p.name, p.emoji, p.pinned, p.archived, p.sort_order, "
                "       COUNT(s.session_id) AS sessions, MAX(s.updated_at) AS last_activity "
                "FROM projects p "
                "LEFT JOIN sessions s ON s.project_id = p.id AND s.archived = 0 "
                "     AND s.session_id NOT LIKE '\\_\\_%' ESCAPE '\\' "
                "GROUP BY p.id "
                "ORDER BY p.pinned DESC, p.sort_order ASC, last_activity DESC, p.created_at DESC",
                (),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "emoji": r["emoji"] or "",
                "pinned": bool(r["pinned"]),
                "archived": bool(r["archived"]),
                "sessions": int(r["sessions"] or 0),
                "last_activity": r["last_activity"] or "",
            }
            for r in rows
        ]

    def update_project(self, project_id: str, **fields) -> bool:
        allowed = {"name", "emoji", "pinned", "archived", "sort_order"}
        sets, values = [], []
        for key, value in fields.items():
            if key not in allowed or value is None:
                continue
            sets.append(f"{key}=?")
            values.append(
                int(bool(value)) if key in ("pinned", "archived") else value
            )
        if not sets:
            return False
        values.append(project_id)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE projects SET {', '.join(sets)} WHERE id=?", values
            )
            self._conn.commit()
        return cur.rowcount > 0

    def delete_project(self, project_id: str) -> bool:
        """Remove the group. Its sessions are UNGROUPED, never deleted — a group is
        an organising idea, and deleting one must not take conversations with it."""
        with self._lock:
            self._conn.execute(
                "UPDATE sessions SET project_id=NULL WHERE project_id=?", (project_id,)
            )
            cur = self._conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
            self._conn.commit()
        return cur.rowcount > 0

    def set_session_project(self, session_id: str, project_id: Optional[str]) -> bool:
        """Move a session into a group, or out of one with None."""
        with self._lock:
            if project_id is not None:
                exists = self._conn.execute(
                    "SELECT 1 FROM projects WHERE id=?", (project_id,)
                ).fetchone()
                if exists is None:
                    return False
            cur = self._conn.execute(
                "UPDATE sessions SET project_id=? WHERE session_id=?",
                (project_id, session_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def workspaces_with_meta(self, limit: int = 200) -> list[dict]:
        """Recent workspaces with their project metadata, most recently used first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT path, last_used, name, emoji, pinned, archived FROM workspaces "
                "ORDER BY last_used DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "path": r["path"],
                "last_used": r["last_used"],
                "name": r["name"],
                "emoji": r["emoji"],
                "pinned": bool(r["pinned"]),
                "archived": bool(r["archived"]),
            }
            for r in rows
        ]

    def workspace_meta(self, path: str) -> Optional[dict]:
        with self._lock:
            r = self._conn.execute(
                "SELECT path, last_used, name, emoji, pinned, archived FROM workspaces "
                "WHERE path = ?",
                (path,),
            ).fetchone()
        if r is None:
            return None
        return {
            "path": r["path"],
            "last_used": r["last_used"],
            "name": r["name"],
            "emoji": r["emoji"],
            "pinned": bool(r["pinned"]),
            "archived": bool(r["archived"]),
        }

    def delete_workspace(self, path: str) -> bool:
        """Forget a workspace row (project identity + recents entry). Sessions are deleted
        separately and the folder itself is never touched — this is bookkeeping only."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM workspaces WHERE path = ?", (path,))
            self._conn.commit()
        return cur.rowcount > 0

    def set_workspace_meta(self, path: str, **fields) -> bool:
        """Update project display metadata; unknown fields are ignored. Creates the
        workspace row if needed so a project can be named before its first session."""
        updates = {k: v for k, v in fields.items() if k in self._PROJECT_FIELDS}
        if not updates:
            return False
        self.touch_workspace(path)
        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = [
            (int(bool(v)) if k in ("pinned", "archived") else (v or None))
            for k, v in updates.items()
        ]
        with self._lock:
            self._conn.execute(
                f"UPDATE workspaces SET {sets} WHERE path = ?", (*vals, path)
            )
            self._conn.commit()
        return True

    def session_stats_by_workspace(self) -> dict[str, dict]:
        """{workspace: {"sessions": n, "last_activity": iso}} over non-archived sessions."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT workspace, COUNT(*) AS n, MAX(updated_at) AS last "
                "FROM sessions WHERE workspace IS NOT NULL AND archived = 0 "
                "GROUP BY workspace"
            ).fetchall()
        return {
            r["workspace"]: {"sessions": r["n"], "last_activity": r["last"]} for r in rows
        }

    def delete(self, session_id: str) -> bool:
        with self._lock:
            self._conn.execute(
                "DELETE FROM tool_runs WHERE session_id = ?", (session_id,)
            )
            cur = self._conn.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,)
            )
            self._conn.commit()
        path = self._file(session_id)
        if path.exists():
            path.unlink()
        return cur.rowcount > 0

    # -- crash-safe tool execution journal --------------------------------------
    def prepare_tool_run(
        self,
        session_id: str,
        message_index: int,
        call_ordinal: int,
        *,
        call_id: str,
        tool_name: str,
        arguments_hash: str,
        recovery_policy: str,
    ) -> dict:
        """Create the durable intent record before authorization/execution.

        INSERT OR IGNORE makes reconstruction idempotent.  The caller validates
        identity fields on the returned row so a rewritten transcript cannot be
        mistaken for an older operation occupying the same position.
        """
        with self._lock:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO tool_runs
                    (session_id, message_index, call_ordinal, call_id, tool_name,
                     arguments_hash, recovery_policy, state)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'prepared')
                """,
                (
                    session_id,
                    message_index,
                    call_ordinal,
                    call_id,
                    tool_name,
                    arguments_hash,
                    recovery_policy,
                ),
            )
            self._conn.commit()
            row = self._conn.execute(
                """
                SELECT * FROM tool_runs
                WHERE session_id = ? AND message_index = ? AND call_ordinal = ?
                """,
                (session_id, message_index, call_ordinal),
            ).fetchone()
        return dict(row) if row is not None else {}

    def get_tool_run(
        self, session_id: str, message_index: int, call_ordinal: int
    ) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM tool_runs
                WHERE session_id = ? AND message_index = ? AND call_ordinal = ?
                """,
                (session_id, message_index, call_ordinal),
            ).fetchone()
        return dict(row) if row is not None else None

    def start_tool_run(
        self, session_id: str, message_index: int, call_ordinal: int
    ) -> None:
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE tool_runs SET state = 'running', updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ? AND message_index = ? AND call_ordinal = ?
                  AND state = 'prepared'
                """,
                (session_id, message_index, call_ordinal),
            )
            if cur.rowcount != 1:
                self._conn.rollback()
                raise RuntimeError("tool run is not executable")
            self._conn.commit()

    def reset_replay_safe_tool_run(
        self, session_id: str, message_index: int, call_ordinal: int
    ) -> None:
        """Claim recovery of a running read by moving it back to executable state."""
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE tool_runs SET state = 'prepared', updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ? AND message_index = ? AND call_ordinal = ?
                  AND state = 'running' AND recovery_policy = 'replay_safe'
                """,
                (session_id, message_index, call_ordinal),
            )
            if cur.rowcount != 1:
                self._conn.rollback()
                raise RuntimeError("replay-safe tool run could not be claimed")
            self._conn.commit()

    def finish_tool_run(
        self,
        session_id: str,
        message_index: int,
        call_ordinal: int,
        *,
        result: str,
        result_status: str,
    ) -> None:
        state = "succeeded" if result_status == "ok" else "failed"
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE tool_runs
                SET state = ?, result = ?, result_status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ? AND message_index = ? AND call_ordinal = ?
                  AND state = 'running'
                """,
                (
                    state,
                    result,
                    result_status,
                    session_id,
                    message_index,
                    call_ordinal,
                ),
            )
            if cur.rowcount != 1:
                self._conn.rollback()
                raise RuntimeError("tool run result could not be committed")
            self._conn.commit()

    def cancel_tool_run(
        self,
        session_id: str,
        message_index: int,
        call_ordinal: int,
        *,
        reason: str,
        result_status: str,
    ) -> None:
        """Commit a prepared call that was denied/stopped before execution."""
        result = json.dumps({"error": "tool call not executed", "reason": reason})
        with self._lock:
            self._conn.execute(
                """
                UPDATE tool_runs
                SET state = 'failed', result = ?, result_status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ? AND message_index = ? AND call_ordinal = ?
                  AND state = 'prepared'
                """,
                (
                    result,
                    result_status,
                    session_id,
                    message_index,
                    call_ordinal,
                ),
            )
            self._conn.commit()

    def mark_tool_indeterminate(
        self, session_id: str, message_index: int, call_ordinal: int
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                UPDATE tool_runs SET state = 'indeterminate', updated_at = CURRENT_TIMESTAMP
                WHERE session_id = ? AND message_index = ? AND call_ordinal = ?
                  AND state NOT IN ('succeeded', 'failed')
                """,
                (session_id, message_index, call_ordinal),
            )
            self._conn.commit()

    def set_workspace(self, session_id: str, workspace: str) -> bool:
        """Re-bind a session to another project folder (drag-to-project in the sidebar)."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE sessions SET workspace = ?, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (workspace, session_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def rename(self, session_id: str, title: str) -> bool:
        clean = " ".join((title or "").split())[:120]
        if not clean:
            return False
        with self._lock:
            # renamed=1 makes the manual title final: auto-titling skips the session and
            # `_display_title` ignores any auto_title already there.
            cur = self._conn.execute(
                "UPDATE sessions SET title = ?, renamed = 1, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (clean, session_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def set_auto_title(self, session_id: str, title: str) -> bool:
        """Store a generated title. Its own column — never `title` — so a manual rename
        (past or future) always wins; doesn't touch updated_at (a title landing after the
        turn must not reorder the session list)."""
        clean = " ".join((title or "").split())[:60]
        if not clean:
            return False
        with self._lock:
            cur = self._conn.execute(
                "UPDATE sessions SET auto_title = ? WHERE session_id = ? AND renamed = 0",
                (clean, session_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def display_title(self, session_id: str) -> Optional[str]:
        """The user-facing title only — one indexed row read, no transcript load
        (mission control names running sessions on every activity snapshot)."""
        s = self.summary(session_id)
        return s["title"] if s else None

    def summary(self, session_id: str) -> Optional[dict]:
        """Row facts without the transcript: {title, workspace, agent} — what
        mission control needs to name a running session and jump to it."""
        with self._lock:
            row = self._conn.execute(
                "SELECT title, auto_title, renamed, workspace, agent "
                "FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "title": _display_title(row),
            "workspace": row["workspace"] or "",
            "agent": row["agent"] or "cowork",
        }

    def title_state(self, session_id: str) -> Optional[dict]:
        """The auto-title guard inputs: whether the user renamed and whether a generated
        title already exists. None when the session has no row yet."""
        with self._lock:
            row = self._conn.execute(
                "SELECT renamed, auto_title FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return {"renamed": bool(row["renamed"]), "auto_title": row["auto_title"]}

    def set_flags(
        self,
        session_id: str,
        *,
        pinned: Optional[bool] = None,
        archived: Optional[bool] = None,
    ) -> bool:
        """Update pin/archive flags without touching updated_at (so pinning doesn't reorder)."""
        sets, params = [], []
        if pinned is not None:
            sets.append("pinned = ?")
            params.append(1 if pinned else 0)
        if archived is not None:
            sets.append("archived = ?")
            params.append(1 if archived else 0)
        if not sets:
            return False
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE sessions SET {', '.join(sets)} WHERE session_id = ?",
                (*params, session_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def set_origin(self, session_id: str, origin: str, origin_label: str = "") -> bool:
        """Mark where a spawned session came from (§31). Set once at spawn; `save()` never
        names these columns, so per-turn saves can't clobber them (the pinned mechanism).
        """
        with self._lock:
            cur = self._conn.execute(
                "UPDATE sessions SET origin = ?, origin_label = ? WHERE session_id = ?",
                (origin, origin_label or None, session_id),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()
