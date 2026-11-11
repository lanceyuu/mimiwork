"""Mail's local cache: what the list and the reader show without asking the server.

The mailbox is the truth for mail: `folder`, `message` and `body` can be deleted and
rebuilt from it. Their rows are keyed by where the server keeps a message (folder and
uid), which changes when the message moves. `comment` and `draft` exist only here, so
they are keyed by `thread_key` instead and outlive an archive, a move made by another
mail app, and a folder that had to be read again from scratch. Thread-safe (check_same_thread=False and a lock),
because the sync thread and the request handlers both use it.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS folder (
  account TEXT NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL DEFAULT '',
  uidvalidity INTEGER NOT NULL DEFAULT 0, synced_at REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (account, name));
CREATE TABLE IF NOT EXISTS message (
  account TEXT NOT NULL, folder TEXT NOT NULL, uid INTEGER NOT NULL,
  message_id TEXT NOT NULL DEFAULT '', thread_key TEXT NOT NULL,
  sender TEXT NOT NULL DEFAULT '', recipients TEXT NOT NULL DEFAULT '',
  cc TEXT NOT NULL DEFAULT '', subject TEXT NOT NULL DEFAULT '',
  date REAL NOT NULL DEFAULT 0, flags TEXT NOT NULL DEFAULT '',
  size INTEGER NOT NULL DEFAULT 0, has_attachments INTEGER NOT NULL DEFAULT 0,
  bulk INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (account, folder, uid));
CREATE INDEX IF NOT EXISTS message_thread ON message (account, thread_key);
CREATE TABLE IF NOT EXISTS body (
  account TEXT NOT NULL, folder TEXT NOT NULL, uid INTEGER NOT NULL,
  html TEXT NOT NULL, text TEXT NOT NULL, attachments TEXT NOT NULL,
  opened_at REAL NOT NULL,
  PRIMARY KEY (account, folder, uid));
CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comment (
  account TEXT NOT NULL, thread_key TEXT NOT NULL, position INTEGER NOT NULL,
  message_id TEXT NOT NULL DEFAULT '', quote TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '', orphaned_at REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (account, thread_key, position));
CREATE TABLE IF NOT EXISTS draft (
  id TEXT PRIMARY KEY, account TEXT NOT NULL, thread_key TEXT NOT NULL DEFAULT '',
  recipients TEXT NOT NULL DEFAULT '', cc TEXT NOT NULL DEFAULT '',
  subject TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '',
  orig_message_id TEXT NOT NULL DEFAULT '', orig_references TEXT NOT NULL DEFAULT '',
  orig_subject TEXT NOT NULL DEFAULT '', orig_sender TEXT NOT NULL DEFAULT '',
  orig_date TEXT NOT NULL DEFAULT '', orig_text TEXT NOT NULL DEFAULT '',
  send_started_at REAL NOT NULL DEFAULT 0, updated_at REAL NOT NULL DEFAULT 0,
  orphaned_at REAL NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX IF NOT EXISTS draft_reply ON draft (account, thread_key) WHERE thread_key != '';
"""
_COLUMNS = (
    "account", "folder", "uid", "message_id", "thread_key", "sender", "recipients", "cc",
    "subject", "date", "flags", "size", "has_attachments", "bulk",
)
_INSERT = (
    f"INSERT OR REPLACE INTO message ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join(':' + column for column in _COLUMNS)})"
)
_BODY_SECONDS = 30 * 86400
_DRAFT_COLUMNS = (
    "id", "account", "thread_key", "recipients", "cc", "subject", "body", "orig_message_id",
    "orig_references", "orig_subject", "orig_sender", "orig_date", "orig_text", "updated_at",
)
# What the user may change in a draft. The rest is the snapshot of the original, taken once.
DRAFT_FIELDS = ("recipients", "cc", "subject", "body")
# A comment goes this long after its conversation left the cache.
_ORPHAN_SECONDS = 30 * 86400


class MailStore:
    def __init__(self, path: str | Path) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Deleting a row only marks its space free; the text stays in the file until
        # something else is written there. Mail that was archived, binned or disconnected
        # must not linger on disk, so freed space is overwritten as it is freed.
        self._conn.execute("PRAGMA secure_delete = ON")
        # Goes up whenever what the screen shows may have changed, so the screen can ask
        # "anything new?" without fetching the list. In memory only: a restarted sidecar
        # starts again from 0 and the screen, seeing a different number, reloads.
        self.revision = 0
        # Moves when the user starts a change (a mark, an archive) and again when the mail
        # server has answered it. A sync pass notes it before asking the server anything and
        # hands it back with what it writes. If it has moved, or a change is still under
        # way, the pass may have read the mailbox from before the change, and its write is
        # refused: a pass can never put back what the user has just changed.
        self.touched = 0
        self._changing = 0
        # Moves when the cache is emptied. A request that began before the mailbox was
        # disconnected hands back what it noted, and what it would write is dropped.
        self.epoch = 0
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._conn.execute(sql, params)]

    @contextmanager
    def changing(self):
        """Wrap a change the user makes, from before the cache is written until the mail
        server has answered. While it is open, and for any pass that began before it
        closed, writes from a sync pass are refused."""
        with self._lock:
            self._changing += 1
            self.touched += 1
        try:
            yield
        finally:
            with self._lock:
                self._changing -= 1
                self.touched += 1

    def _write(
        self, statements: list[tuple[str, list]], expect: Optional[int], epoch: Optional[int] = None
    ) -> bool:
        """Run each statement for each of its rows, as one change. With `expect` (a sync
        pass), nothing is written and False comes back if the user has changed something
        since the pass noted `touched`, or is changing something now. The revision moves
        only if a row changed."""
        with self._lock, self._conn:
            if expect is not None and (self._changing or expect != self.touched):
                return False
            if epoch is not None and epoch != self.epoch:
                return False
            changed = sum(
                self._conn.executemany(sql, rows).rowcount for sql, rows in statements if rows
            )
            self.revision += 1 if changed > 0 else 0
            return True

    # -- folders ---------------------------------------------------------------------
    def folder_validity(self, account: str, folder: str) -> Optional[int]:
        rows = self._all(
            "SELECT uidvalidity FROM folder WHERE account = ? AND name = ?", (account, folder)
        )
        return rows[0]["uidvalidity"] if rows else None

    def reset_folder(self, account: str, folder: str, role: str, uidvalidity: int) -> None:
        """Start a folder again. A new uidvalidity means every uid the cache holds for the
        folder may now name a different message, so they all go."""
        with self._lock, self._conn:
            for table in ("message", "body"):
                self._conn.execute(
                    f"DELETE FROM {table} WHERE account = ? AND folder = ?", (account, folder)
                )
            self._conn.execute(
                "INSERT OR REPLACE INTO folder (account, name, role, uidvalidity) VALUES (?, ?, ?, ?)",
                (account, folder, role, uidvalidity),
            )
            self.revision += 1

    def mark_synced(self, account: str, folder: str, now: float) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE folder SET synced_at = ? WHERE account = ? AND name = ?",
                (now, account, folder),
            )

    # -- messages --------------------------------------------------------------------
    def uids(self, account: str, folder: str) -> set[int]:
        rows = self._all(
            "SELECT uid FROM message WHERE account = ? AND folder = ?", (account, folder)
        )
        return {row["uid"] for row in rows}

    def add(
        self, rows: list[dict[str, Any]], expect: Optional[int] = None, epoch: Optional[int] = None
    ) -> bool:
        return self._write([(_INSERT, rows)], expect, epoch)

    def remove(
        self, account: str, folder: str, uids: list[int], expect: Optional[int] = None
    ) -> bool:
        keys = [(account, folder, uid) for uid in uids]
        where = "WHERE account = ? AND folder = ? AND uid = ?"
        return self._write(
            [(f"DELETE FROM body {where}", keys), (f"DELETE FROM message {where}", keys)], expect
        )

    def row(self, account: str, folder: str, uid: int) -> Optional[dict[str, Any]]:
        rows = self._all(
            "SELECT * FROM message WHERE account = ? AND folder = ? AND uid = ?",
            (account, folder, uid),
        )
        return rows[0] if rows else None

    def set_flags(
        self, account: str, folder: str, flags: dict[int, str], expect: Optional[int] = None
    ) -> bool:
        sql = "UPDATE message SET flags = ? WHERE account = ? AND folder = ? AND uid = ? AND flags != ?"
        rows = [(value, account, folder, uid, value) for uid, value in flags.items()]
        return self._write([(sql, rows)], expect)

    def set_seen(self, account: str, folder: str, uids: list[int], seen: bool) -> None:
        changes = {}
        for uid in uids:
            row = self.row(account, folder, uid)
            if row is None:
                continue
            kept = [flag for flag in row["flags"].split() if flag != "\\Seen"]
            changes[uid] = " ".join(kept + (["\\Seen"] if seen else []))
        self.set_flags(account, folder, changes)

    # -- threads ---------------------------------------------------------------------
    def threads(self, account: str, inbox: str) -> list[dict[str, Any]]:
        """Conversations with at least one message in the inbox, newest first."""
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in self._all("SELECT * FROM message WHERE account = ? ORDER BY date", (account,)):
            groups.setdefault(row["thread_key"], []).append(row)
        out = []
        for key, rows in groups.items():
            received = [row for row in rows if row["folder"] == inbox]
            if not received:
                continue
            out.append(
                {
                    "key": key,
                    "subject": rows[-1]["subject"],
                    # The other person, even when the newest message is your own reply.
                    "sender": received[-1]["sender"],
                    "date": rows[-1]["date"],
                    "unread": any("\\Seen" not in row["flags"] for row in received),
                    "count": len(_distinct(rows, inbox)),
                    "has_attachments": any(row["has_attachments"] for row in rows),
                }
            )
        return sorted(out, key=lambda thread: thread["date"], reverse=True)

    def thread(self, account: str, key: str, inbox: str) -> list[dict[str, Any]]:
        """A conversation's messages from every synced folder, oldest first."""
        return _distinct(
            self._all(
                "SELECT * FROM message WHERE account = ? AND thread_key = ? ORDER BY date",
                (account, key),
            ),
            inbox,
        )

    def thread_rows(self, account: str, key: str, folder: str) -> list[dict[str, Any]]:
        """Every row of a conversation in one folder, duplicates included. This is what a
        change acts on; `thread` is what the reader shows."""
        return self._all(
            "SELECT * FROM message WHERE account = ? AND thread_key = ? AND folder = ?",
            (account, key, folder),
        )

    # -- bodies ----------------------------------------------------------------------
    def body(self, account: str, folder: str, uid: int, now: float) -> Optional[dict[str, Any]]:
        key = (account, folder, uid)
        where = "WHERE account = ? AND folder = ? AND uid = ?"
        rows = self._all(f"SELECT html, text, attachments FROM body {where}", key)
        if not rows:
            return None
        with self._lock, self._conn:
            self._conn.execute(f"UPDATE body SET opened_at = ? {where}", (now, *key))
        return {**rows[0], "attachments": json.loads(rows[0]["attachments"])}

    def put_body(
        self, account: str, folder: str, uid: int, rendered: dict[str, Any], now: float,
        epoch: Optional[int] = None,
    ) -> None:
        with self._lock, self._conn:
            if epoch is not None and epoch != self.epoch:
                return
            self._conn.execute(
                "INSERT OR REPLACE INTO body (account, folder, uid, html, text, attachments, opened_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (account, folder, uid, rendered["html"], rendered["text"],
                 json.dumps(rendered["attachments"]), now),
            )

    def prune(self, now: float) -> None:
        """Forget message text nobody has opened for 30 days, and comments whose
        conversation has been out of the cache for 30 days. The cache must not only grow.

        A draft is never forgotten here (the owner's decision, 2026-11-11): it is what the
        user wrote, and it goes only when it is sent or discarded. Comments on a
        conversation that still has an unsent reply are kept with it, because the reply
        can still be rewritten from them."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM body WHERE opened_at < ?", (now - _BODY_SECONDS,))
            has_mail = (
                "EXISTS (SELECT 1 FROM message WHERE message.account = comment.account "
                "AND message.thread_key = comment.thread_key)"
            )
            has_reply = (
                "EXISTS (SELECT 1 FROM draft WHERE draft.account = comment.account "
                "AND draft.thread_key = comment.thread_key)"
            )
            # The clock starts when the conversation is first found missing, and stops if
            # its mail comes back.
            self._conn.execute(f"UPDATE comment SET orphaned_at = 0 WHERE orphaned_at > 0 AND {has_mail}")
            self._conn.execute(
                f"UPDATE comment SET orphaned_at = ? WHERE orphaned_at = 0 AND NOT {has_mail}",
                (now,),
            )
            self._conn.execute(
                f"DELETE FROM comment WHERE orphaned_at > 0 AND orphaned_at < ? AND NOT {has_reply}",
                (now - _ORPHAN_SECONDS,),
            )

    # -- comments --------------------------------------------------------------------
    def comments(self, account: str, key: str) -> dict[str, Any]:
        """A conversation's comments in the order they were made, and its free note. The
        free note is kept as the one row with no quote."""
        rows = self._all(
            "SELECT message_id, quote, note FROM comment "
            "WHERE account = ? AND thread_key = ? ORDER BY position",
            (account, key),
        )
        return {
            "comments": [row for row in rows if row["quote"]],
            "note": next((row["note"] for row in rows if not row["quote"]), ""),
        }

    def put_comments(self, account: str, key: str, comments: list[dict[str, str]], note: str) -> None:
        """Replace a conversation's comments. The screen always saves the whole list, so
        a comment needs no id of its own."""
        rows = [(account, key, n, c["message_id"], c["quote"], c["note"]) for n, c in enumerate(comments)]
        if note:
            rows.append((account, key, len(rows), "", "", note))
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM comment WHERE account = ? AND thread_key = ?", (account, key))
            self._conn.executemany(
                "INSERT INTO comment (account, thread_key, position, message_id, quote, note) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )

    # -- drafts ----------------------------------------------------------------------
    def drafts(self, account: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM draft WHERE account = ? ORDER BY updated_at DESC", (account,))

    def draft(self, account: str, draft_id: str) -> Optional[dict[str, Any]]:
        rows = self._all("SELECT * FROM draft WHERE account = ? AND id = ?", (account, draft_id))
        return rows[0] if rows else None

    def reply_draft(self, account: str, key: str) -> Optional[dict[str, Any]]:
        """The conversation's unsent reply. There is at most one."""
        rows = self._all(
            "SELECT * FROM draft WHERE account = ? AND thread_key = ? AND thread_key != ''",
            (account, key),
        )
        return rows[0] if rows else None

    def add_draft(self, row: dict[str, Any], epoch: Optional[int] = None) -> bool:
        """Keep a new draft. False, and nothing kept, when the cache was emptied since
        `epoch` was noted: a reply draft holds the original's text, and mail text must not
        be written back after its mailbox was disconnected. A second reply draft for one
        conversation is refused by the table itself (`sqlite3.IntegrityError`)."""
        marks = ", ".join(":" + column for column in _DRAFT_COLUMNS)
        with self._lock, self._conn:
            if epoch is not None and epoch != self.epoch:
                return False
            self._conn.execute(f"INSERT INTO draft ({', '.join(_DRAFT_COLUMNS)}) VALUES ({marks})", row)
            return True

    def update_draft(self, account: str, draft_id: str, fields: dict[str, str], now: float) -> bool:
        """Change what the user may change. False when the draft is no longer there."""
        names = [name for name in DRAFT_FIELDS if name in fields]
        sets = ", ".join(f"{name} = ?" for name in [*names, "updated_at"])
        with self._lock, self._conn:
            done = self._conn.execute(
                f"UPDATE draft SET {sets} WHERE account = ? AND id = ?",
                (*(fields[name] for name in names), now, account, draft_id),
            )
            return done.rowcount > 0

    def delete_draft(self, account: str, draft_id: str) -> bool:
        with self._lock, self._conn:
            done = self._conn.execute("DELETE FROM draft WHERE account = ? AND id = ?", (account, draft_id))
            return done.rowcount > 0

    def mark_sending(self, draft_id: str, started_at: float) -> None:
        """Written before a send and cleared (0) when it returns. A draft found with it
        still set was being sent when the app stopped."""
        with self._lock, self._conn:
            self._conn.execute("UPDATE draft SET send_started_at = ? WHERE id = ?", (started_at, draft_id))

    # -- settings --------------------------------------------------------------------
    def get(self, key: str) -> str:
        rows = self._all("SELECT value FROM setting WHERE key = ?", (key,))
        return rows[0]["value"] if rows else ""

    def put(self, key: str, value: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO setting (key, value) VALUES (?, ?)", (key, value)
            )

    # -- forgetting ------------------------------------------------------------------
    def forget_others(self, account: str) -> None:
        """Drop every other mailbox's mail, comments and drafts: only one is connected
        at a time."""
        with self._lock, self._conn:
            changed = sum(
                self._conn.execute(f"DELETE FROM {table} WHERE account != ?", (account,)).rowcount
                for table in ("folder", "message", "body", "comment", "draft")
            )
            self.revision += 1 if changed else 0

    def keep_folders(self, account: str, folders: list[str]) -> None:
        """Drop mail cached under a folder that is no longer one of the synced ones."""
        marks = ", ".join("?" for _ in folders)
        with self._lock, self._conn:
            changed = sum(
                self._conn.execute(
                    f"DELETE FROM {table} WHERE account = ? AND {column} NOT IN ({marks})",
                    (account, *folders),
                ).rowcount
                for table, column in (("folder", "name"), ("message", "folder"), ("body", "folder"))
            )
            self.revision += 1 if changed else 0

    def clear(self) -> None:
        """Empty the cache, for when the mailbox is disconnected."""
        with self._lock, self._conn:
            for table in ("folder", "message", "body", "setting", "comment", "draft"):
                self._conn.execute(f"DELETE FROM {table}")
            self.revision += 1
            # A pass, or a request, still running when the mailbox was disconnected must
            # not write its mail back, so everything they noted is made out of date.
            self.touched += 1
            self.epoch += 1
        with self._lock:
            # Give the space back as well; this cannot run inside the transaction above.
            self._conn.execute("VACUUM")


def _distinct(rows: list[dict[str, Any]], inbox: str) -> list[dict[str, Any]]:
    """One row for each message. Mail you send to yourself sits in Sent and in the inbox;
    the inbox copy is the one kept, because that is the one archive and bin act on."""
    seen: set[str] = set()
    out = []
    for row in sorted(rows, key=lambda row: (row["date"], row["folder"] != inbox)):
        identity = row["message_id"] or f"{row['folder']}/{row['uid']}"
        if identity not in seen:
            seen.add(identity)
            out.append(row)
    return out
