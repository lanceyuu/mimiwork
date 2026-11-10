"""What the Mail screen can ask for. Every route under /v1/mail is one call into this.

Nothing here passes through the approval engine. These are the user's own button presses
on their own mailbox, each naming what it does; the agent gains no tool from this file,
and its `email_send` and `email_save_draft` still stop for approval.
"""

from __future__ import annotations

import functools
import imaplib
import re
import smtplib
import sqlite3
import threading
import time
import uuid
from email.utils import format_datetime, getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Optional

from ..connectors.email_tools import (
    _default_imap_factory,
    _default_smtp_factory,
    _one_line,
    _safe_filename,
    decode_mime_header,
)
from ..secrets import SecretStore
from .imap import MailConnection, MailError
from .render import attachment_bytes, attachments, render_message
from .store import DRAFT_FIELDS, MailStore
from .sync import MailSync, message_row
from .threads import thread_key

INBOX = "INBOX"
_GONE = "This message is no longer in the mailbox."
# Characters that reorder the text around them, so that a program can pass for a document.
_BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_NO_DRAFT = "This draft no longer exists."
_KEY = re.compile(r"[0-9a-f]{16}")
# What the screen may hand over, at most. It is the only caller, but a limit here means a
# mistake there cannot fill the cache.
_QUOTE_LIMIT, _NOTE_LIMIT, _MAX_COMMENTS = 1000, 4000, 100
# A draft field over its limit is refused, never cut: a list of recipients cut short would
# be sent to the wrong people, and nobody would be told.
_DRAFT_LIMITS = {
    "recipients": (20_000, "That is too many recipients for one message."),
    "cc": (20_000, "That is too many recipients for one message."),
    "subject": (998, "The subject is too long."),
    "body": (200_000, "The message is too long to save."),
}
# The screen's name for each thing a user may change in a draft, and the cache's.
_DRAFT_NAMES = dict(zip(("to", "cc", "subject", "body"), DRAFT_FIELDS))
_NEEDS_QUOTES = re.compile(r'[,;:<>@()\[\]."\\]')
# An address is one word. One with a space, a control character or an encoded word in it
# is not what it looks like on screen.
_ODD_ADDRESS = re.compile(r"[\s\x00-\x1f\x7f]|=\?")


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


def _not_connected() -> dict[str, Any]:
    return {"ok": False, "error": "Email is not connected."}


def _people(*headers: Any) -> list[tuple[str, str]]:
    return [
        pair
        for pair in getaddresses([str(h) for h in headers if h])
        if "@" in pair[1] and not _ODD_ADDRESS.search(pair[1])
    ]


def _address(name: str, address: str) -> str:
    """One recipient as a person reads and types it: `Ana Lopez <ana@example.com>`. The
    name comes from an incoming email, so marks that reorder or hide text are left out."""
    name = " ".join(decode_mime_header(name).replace('"', "").replace("\\", "").split())
    name = "".join(ch for ch in name if ch.isprintable())[:200]
    if not name:
        return address
    return f'"{name}" <{address}>' if _NEEDS_QUOTES.search(name) else f"{name} <{address}>"


def reply_recipients(msg: Any, own: str, reply_all: bool) -> tuple[str, str]:
    """(to, cc) for a reply to `msg`. Reply answers whoever the message asks to be
    answered; Reply all adds everyone else it went to, never the user's own address."""
    sender = _people(msg.get("From"))
    to = _people(msg.get("Reply-To")) or sender
    others = _people(*msg.get_all("To", []), *msg.get_all("Cc", []))
    if sender and all(address.lower() == own.lower() for _, address in sender):
        # The user's own message: a follow-up goes to the people that message went to.
        # Judged by who sent it, not by where it asks replies to go.
        to, others = _people(*msg.get_all("To", [])) or to, _people(*msg.get_all("Cc", []))
    seen = {own.lower()} | {address.lower() for _, address in to}
    cc = []
    for name, address in others if reply_all else []:
        if address.lower() not in seen:
            seen.add(address.lower())
            cc.append((name, address))
    return ", ".join(_address(*pair) for pair in to), ", ".join(_address(*pair) for pair in cc)


def _sent_on(msg: Any) -> str:
    """When a message was sent, for the line above the quote in a reply. Built again from
    the date as parsed, never copied: the header is the sender's text, and that line is
    sent as the user's own words."""
    try:
        return format_datetime(parsedate_to_datetime(str(msg.get("Date", ""))))
    except Exception:
        return ""


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
        smtp_factory: Callable[[str, int], smtplib.SMTP] = _default_smtp_factory,
        complete: Optional[Callable[[str, str], str]] = None,
        downloads: Optional[Path] = None,
    ) -> None:
        self._secrets = secrets
        self._imap_factory = imap_factory
        self._smtp_factory = smtp_factory
        # The model, as `complete(system, user) -> str`. It raises with a plain reason.
        self._complete = complete
        self._conn = MailConnection(secrets, imap_factory=imap_factory)
        self._store = MailStore(path)
        self._sync = MailSync(self._conn, self._store)
        self._downloads = downloads
        # Drafts being sent right now. In memory on purpose: after a restart nothing is
        # in flight, and `send_started_at` in the cache says a send was cut short.
        self._sending: set[str] = set()
        self._sending_lock = threading.Lock()

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
        account = self._account()
        rows = self._store.thread(account, key, INBOX)
        if not rows:
            return {"ok": False, "error": "This conversation is no longer in the mailbox."}
        received = [row for row in rows if row["folder"] == INBOX]
        # What a reply answers: the newest message that came in, not the user's own last word.
        answer = (received or rows)[-1]
        draft = self._store.reply_draft(account, key)
        return {
            "ok": True,
            "key": key,
            "subject": rows[-1]["subject"],
            "in_inbox": bool(received),
            "messages": [_public(row) for row in rows],
            "answer": {"folder": answer["folder"], "uid": answer["uid"], "message_id": answer["message_id"]},
            "draft": draft["id"] if draft else "",
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
        draft = self._store.reply_draft(account, row["thread_key"])
        return {
            "ok": True,
            **_public(row),
            "thread_key": row["thread_key"],
            "draft": draft["id"] if draft else "",
            **rendered,
        }

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

    # -- comments --------------------------------------------------------------------
    # Comments and drafts are kept by conversation, not by where its mail sits, so they
    # are there for a search result too, and stay when the conversation is archived.
    def comments(self, key: str) -> dict[str, Any]:
        return {"ok": True, **self._store.comments(self._account(), key)}

    def put_comments(self, key: str, comments: Any, note: Any) -> dict[str, Any]:
        """Save the whole list, as the screen does while the user types."""
        account = self._account()
        if not account:
            return _not_connected()
        if not _KEY.fullmatch(str(key)) or not isinstance(comments, list) or len(comments) > _MAX_COMMENTS:
            return {"ok": False, "error": "These comments could not be saved."}
        kept = []
        for comment in comments:
            if not isinstance(comment, dict):
                continue
            quote = " ".join(str(comment.get("quote") or "").split())[:_QUOTE_LIMIT]
            if quote:
                kept.append(
                    {
                        "message_id": _one_line(comment.get("message_id"))[:998],
                        "quote": quote,
                        "note": str(comment.get("note") or "")[:_NOTE_LIMIT],
                    }
                )
        self._store.put_comments(account, key, kept, str(note or "")[:_NOTE_LIMIT])
        return {"ok": True}

    # -- drafts ----------------------------------------------------------------------
    def _draft(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "thread_key": row["thread_key"],
            "to": row["recipients"],
            "cc": row["cc"],
            "subject": row["subject"],
            "body": row["body"],
            # Who a reply answers, and which of their messages; "" for a new message.
            "answers": row["orig_sender"] if row["thread_key"] else "",
            "answers_id": row["orig_message_id"],
            "reply": bool(row["thread_key"]),
            "interrupted": bool(row["send_started_at"]) and row["id"] not in self._sending,
            "updated_at": row["updated_at"],
        }

    def drafts(self) -> dict[str, Any]:
        return {"ok": True, "drafts": [self._draft(row) for row in self._store.drafts(self._account())]}

    def draft(self, draft_id: str) -> dict[str, Any]:
        row = self._store.draft(self._account(), draft_id)
        return {"ok": True, "draft": self._draft(row)} if row else {"ok": False, "error": _NO_DRAFT}

    @_answers
    def create_draft(self, folder: str = "", uid: int = 0, reply_all: bool = False) -> dict[str, Any]:
        """A new message, or with `folder` and `uid` a reply to that message. A reply takes
        what it will need from the original now (who to answer, how to thread, the text to
        quote), so it can still be sent after the original has been archived or has left
        the cache. A conversation has one reply draft; asking again gives it back, unless
        it answers an earlier message and nothing has been written in it yet, in which case
        it is started again for this one."""
        account, epoch = self._account(), self._store.epoch
        if not account:
            return _not_connected()
        row = dict.fromkeys(
            ("thread_key", "recipients", "cc", "subject", "body", "orig_message_id",
             "orig_references", "orig_subject", "orig_sender", "orig_date", "orig_text"),
            "",
        )
        if folder or uid:
            if not _named(folder, uid):
                return {"ok": False, "error": _GONE}
            msg = self._conn.message(folder, uid)
            if msg is None:
                return {"ok": False, "error": _GONE}
            key = thread_key(msg, account=account, folder=folder, uid=uid)
            answered = _one_line(msg.get("Message-ID"))
            existing = self._store.reply_draft(account, key)
            if existing:
                in_use = existing["body"].strip() or existing["id"] in self._sending
                if existing["orig_message_id"] == answered or in_use:
                    return {"ok": True, "draft": self._draft(existing)}
                # Left empty on an earlier message of the conversation. Kept, it would
                # answer, thread under and quote a message the user is no longer looking at.
                self._store.delete_draft(account, existing["id"])
            to, cc = reply_recipients(msg, account, bool(reply_all))
            sender = _people(msg.get("From"))
            subject = _one_line(decode_mime_header(msg.get("Subject", "")))
            row.update(
                thread_key=key,
                recipients=to,
                cc=cc,
                subject=subject if subject.lower().startswith("re:") else f"Re: {subject}".strip(),
                orig_message_id=answered,
                orig_references=_one_line(msg.get("References")),
                orig_subject=subject,
                orig_sender=_address(*sender[0]) if sender else "",
                orig_date=_sent_on(msg),
                # ponytail: one cap (render's 20,000 characters) for what the model reads
                # and what is quoted. Keep the whole text for quoting if long mail is cut short.
                orig_text=render_message(msg)["text"],
            )
        else:
            # Pressing New message again gives back the one still empty, not another.
            for old in self._store.drafts(account):
                if not old["thread_key"] and not any(old[name] for name in DRAFT_FIELDS):
                    return {"ok": True, "draft": self._draft(old)}
        row.update(id=uuid.uuid4().hex, account=account, updated_at=time.time())
        try:
            # Refused if the mailbox was disconnected while the original was being fetched.
            if not self._store.add_draft(row, epoch=epoch):
                return _not_connected()
        except sqlite3.IntegrityError:
            # Two requests at once for one conversation: the other one made its reply draft.
            return {"ok": True, "draft": self._draft(self._store.reply_draft(account, row["thread_key"]))}
        return {"ok": True, "draft": self._draft({**row, "send_started_at": 0})}

    def update_draft(self, draft_id: str, fields: Any) -> dict[str, Any]:
        account = self._account()
        if not account:
            return _not_connected()
        fields = fields if isinstance(fields, dict) else {}
        clean = {}
        for name, column in _DRAFT_NAMES.items():
            if name not in fields:
                continue
            value, (limit, too_long) = fields[name], _DRAFT_LIMITS[column]
            if not isinstance(value, str):
                return {"ok": False, "error": "This draft could not be saved."}
            # A header on one line: a line break in one would start another header.
            value = value if column == "body" else _one_line(value)
            if len(value) > limit:
                return {"ok": False, "error": too_long}
            clean[column] = value
        if not self._store.update_draft(account, draft_id, clean, time.time()):
            return {"ok": False, "error": _NO_DRAFT}
        return {"ok": True}

    def delete_draft(self, draft_id: str) -> dict[str, Any]:
        account = self._account()
        if not account:
            return _not_connected()
        self._store.delete_draft(account, draft_id)
        return {"ok": True}
