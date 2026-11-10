"""What the Mail screen can ask for. Every route under /v1/mail is one call into this.

Nothing here passes through the approval engine. These are the user's own button presses
on their own mailbox, each naming what it does; the agent gains no tool from this file,
and its `email_send` and `email_save_draft` still stop for approval.
"""

from __future__ import annotations

import functools
import imaplib
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

from ..connectors.email_tools import _default_imap_factory, _safe_filename
from ..secrets import SecretStore
from .imap import MailConnection, MailError
from .render import attachment_bytes, attachments, render_message
from .store import MailStore
from .sync import MailSync, message_row

INBOX = "INBOX"
_GONE = "This message is no longer in the mailbox."
# Characters that reorder the text around them, so that a program can pass for a document.
_BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def _named(folder: Any, uid: Any) -> bool:
    """A request must say which message it means. A uid without its folder would be
    looked up in whichever folder happened to be open."""
    return bool(folder) and isinstance(uid, int) and uid > 0


def _answers(method):
    """Give a failure back as the plain `{ok: False, error}` every Mail route returns."""

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except MailError as exc:
            return {"ok": False, "error": str(exc)}

    return wrapper


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "folder": row["folder"],
        "uid": row["uid"],
        "message_id": row["message_id"],
        "from": row["sender"],
        "to": row["recipients"],
        "cc": row["cc"],
        "subject": row["subject"],
        "date": row["date"],
        "unread": "\\Seen" not in row["flags"],
        "has_attachments": bool(row["has_attachments"]),
    }


class MailService:
    def __init__(
        self,
        secrets: SecretStore,
        path: str | Path,
        *,
        imap_factory: Callable[[str, int], imaplib.IMAP4] = _default_imap_factory,
        downloads: Optional[Path] = None,
    ) -> None:
        self._secrets = secrets
        self._conn = MailConnection(secrets, imap_factory=imap_factory)
        self._store = MailStore(path)
        self._sync = MailSync(self._conn, self._store)
        self._downloads = downloads

    def _account(self) -> str:
        profile = self._secrets.get("email:default") or {}
        return str(profile.get("address") or "") if profile.get("app_password") else ""

    # -- lifecycle -------------------------------------------------------------------
    def close(self) -> None:
        self._sync.stop()
        self._conn.close()
        self._store.close()

    def forget(self) -> None:
        """The Email connector was disconnected: drop the connection and all cached mail.
        The pass under way is ended first, or it would write the mail straight back."""
        self._sync.stop()
        self._conn.close()
        self._store.clear()

    # -- reading ---------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        """Answered from the cache alone, so the screen can ask as often as it likes."""
        account = self._account()
        return {
            "ok": True,
            "connected": bool(account),
            "address": account,
            "syncing": self._sync.running,
            "revision": self._store.revision,
            "last_sync": float(self._store.get("last_sync") or 0),
            "last_error": self._store.get("last_error"),
            "can_archive": bool(self._store.get("can_archive")),
            "can_bin": bool(self._store.get("can_bin")),
        }

    def sync(self) -> dict[str, Any]:
        account = self._account()
        if not account:
            return {"ok": False, "error": "Email is not connected."}
        # Another mailbox's mail goes now, not only once this one has logged in.
        self._store.forget_others(account)
        return {"ok": True, "started": self._sync.request()}

    def threads(self) -> dict[str, Any]:
        return {"ok": True, "threads": self._store.threads(self._account(), INBOX)}

    def thread(self, key: str) -> dict[str, Any]:
        rows = self._store.thread(self._account(), key, INBOX)
        if not rows:
            return {"ok": False, "error": "This conversation is no longer in the mailbox."}
        return {
            "ok": True,
            "key": key,
            "subject": rows[-1]["subject"],
            "in_inbox": any(row["folder"] == INBOX for row in rows),
            "messages": [_public(row) for row in rows],
        }

    @_answers
    def message(self, folder: str, uid: int) -> dict[str, Any]:
        """One message ready to show. Served from the cache when it is there; a search
        result is not, so it is fetched and shown without being kept."""
        if not _named(folder, uid):
            return {"ok": False, "error": _GONE}
        account, epoch = self._account(), self._store.epoch
        row = self._store.row(account, folder, uid)
        rendered = self._store.body(account, folder, uid, time.time()) if row else None
        if rendered is None:
            msg = self._conn.message(folder, uid)
            if msg is None:
                return {"ok": False, "error": _GONE}
            rendered = render_message(msg)
            if row:
                self._store.put_body(account, folder, uid, rendered, time.time(), epoch=epoch)
            else:
                item = {"uid": uid, "flags": "", "size": 0, "has_attachments": False, "headers": msg}
                row = {**message_row(account, folder, item), "has_attachments": bool(rendered["attachments"])}
        return {"ok": True, **_public(row), "thread_key": row["thread_key"], **rendered}

    @_answers
    def search(self, query: str) -> dict[str, Any]:
        """Search on the server, so it reaches mail outside the window and archived mail."""
        # One line of plain words: a line break inside a search would end the command early.
        query = " ".join(query.split())
        if not query:
            return {"ok": True, "results": []}
        account = self._account()
        roles = self._conn.describe()["roles"]
        # Gmail's All Mail holds everything; elsewhere, look where mail usually is.
        folders = [roles["all"]] if roles.get("all") else [INBOX, roles.get("sent"), roles.get("archive")]
        results = []
        for folder in dict.fromkeys(name for name in folders if name):
            found = self._conn.headers(folder, self._conn.search(folder, query))
            results += [_public(message_row(account, folder, item)) for item in found]
        return {"ok": True, "results": sorted(results, key=lambda r: r["date"], reverse=True)}

    # -- changing the mailbox --------------------------------------------------------
    # Each change is made inside `store.changing()`, from before the cache is written
    # until the server has answered, and is followed by a request to sync. A pass that
    # read the mailbox from before the change is then refused when it tries to write, and
    # the request makes sure a pass that reads it afterwards follows.
    @_answers
    def mark_message_read(self, folder: str, uid: int) -> dict[str, Any]:
        if not _named(folder, uid):
            return {"ok": False, "error": _GONE}
        try:
            with self._store.changing():
                self._conn.set_seen(folder, [uid], True)
                self._store.set_seen(self._account(), folder, [uid], True)
        finally:
            self._sync.request()
        return {"ok": True}

    @_answers
    def mark_thread(self, key: str, read: bool) -> dict[str, Any]:
        account = self._account()
        rows = self._store.thread_rows(account, key, INBOX)
        uids = [row["uid"] for row in rows]
        try:
            with self._store.changing():
                # The cache first, so the list answers at once; put back if the server refuses.
                self._store.set_seen(account, INBOX, uids, read)
                try:
                    self._conn.set_seen(INBOX, uids, read)
                except MailError:
                    self._store.set_flags(account, INBOX, {row["uid"]: row["flags"] for row in rows})
                    raise
        finally:
            self._sync.request()
        return {"ok": True}

    def archive(self, key: str) -> dict[str, Any]:
        return self._move(key, "archive")

    def bin(self, key: str) -> dict[str, Any]:
        return self._move(key, "bin")

    @_answers
    def _move(self, key: str, role: str) -> dict[str, Any]:
        account = self._account()
        # Every copy in the inbox, including two copies of one message (sent to you and to
        # a list you are on). What the reader shows is de-duplicated; what moves is not.
        rows = self._store.thread_rows(account, key, INBOX)
        if not rows:
            return {"ok": False, "error": "This conversation is no longer in the inbox."}
        uids, epoch = [row["uid"] for row in rows], self._store.epoch
        try:
            with self._store.changing():
                self._store.remove(account, INBOX, uids)
                try:
                    self._conn.move(INBOX, uids, role)
                except MailError:
                    # Put back, unless the mailbox was disconnected in the meantime.
                    self._store.add(rows, epoch=epoch)
                    raise
        finally:
            self._sync.request()
        return {"ok": True}

    @_answers
    def save_attachment(self, folder: str, uid: int, index: int) -> dict[str, Any]:
        """Save the attachment at `index` in the message's list into Downloads. By place,
        not by name: two attachments may share a name."""
        if not _named(folder, uid) or not isinstance(index, int) or index < 0:
            return {"ok": False, "error": _GONE}
        msg = self._conn.message(folder, uid)
        if msg is None:
            return {"ok": False, "error": _GONE}
        parts = attachments(msg)
        if index >= len(parts):
            return {"ok": False, "error": "This message has no such attachment."}
        name, part = parts[index]
        safe = Path(_safe_filename(_BIDI.sub("", name)))
        stem, suffix = safe.stem[:120] or "attachment", safe.suffix[:20]
        directory = self._downloads or Path.home() / "Downloads"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            for n in range(1000):
                target = directory / (f"{stem}{suffix}" if n == 0 else f"{stem}-{n}{suffix}")
                try:
                    # "x" refuses a name that is taken, a dangling link included, so
                    # nothing already in Downloads is ever written over or through.
                    with open(target, "xb") as handle:
                        handle.write(attachment_bytes(part))
                    return {"ok": True, "path": str(target)}
                except FileExistsError:
                    continue
        except OSError as exc:
            return {"ok": False, "error": f"Could not save the file: {exc.strerror or exc}"}
        return {"ok": False, "error": "Could not save the file: too many files with this name."}
