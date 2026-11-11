"""What the Mail screen can ask for. Every route under /v1/mail is one call into this.

Nothing here passes through the approval engine. These are the user's own button presses
on their own mailbox, each naming what it does, Send included; the agent gains no tool
from this file, and its `email_send` and `email_save_draft` still stop for approval.
"""

from __future__ import annotations

import functools
import imaplib
import json
import re
import smtplib
import sqlite3
import threading
import time
import uuid
from email.message import EmailMessage
from email.utils import format_datetime, formatdate, getaddresses, parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, Optional

from ..connectors.email_tools import (
    _default_imap_factory,
    _default_smtp_factory,
    _one_line,
    _safe_filename,
    compose_message,
    decode_mime_header,
    load_profile,
    send_message,
)
from ..secrets import SecretStore
from . import reply as reply_writer
from . import triage
from .imap import MailConnection, MailError
from .render import attachment_bytes, attachments, render_message
from .store import DRAFT_FIELDS, MailStore
from .sync import MailSync, _Stopped, message_row
from .threads import thread_key

INBOX = "INBOX"
_GONE = "This message is no longer in the mailbox."
# Characters that reorder the text around them, so that a program can pass for a document.
_BIDI = re.compile("[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_NO_DRAFT = "This draft no longer exists."
# Sorting, per pass: how many conversations at most, how many in one request to the
# model, how often one is tried, and the largest message fetched just to be sorted.
_SORT_PER_PASS, _SORT_BATCH, _SORT_TRIES, _SORT_MAX_BYTES = 60, 20, 3, 2_000_000
_MAX_EXCLUDED = 200
# An address, or @ and a domain. Anything else would be saved and never match anyone,
# leaving the user to believe a sender is excluded when their mail is still being sent.
_EXCLUDE_RULE = re.compile(r"[^@\s<>*,;]*@[^@\s<>*,;]+\.[^@\s<>*,;]+")
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
# How Python prints a mail server's answer: (554, b'5.7.1 Relay denied').
_SERVER_SAID = re.compile(r"\((\d{3}), b?(['\"])(.*?)\2\)", re.S)


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


def _entries(text: str) -> list[str]:
    """A line of recipients as typed, one entry each. People separate addresses with
    commas or semicolons and leave one at the end; a comma inside a quoted name is part
    of the name."""
    entries, current, quoted = [], [], False
    for ch in text:
        if ch == '"':
            quoted = not quoted
        if ch in ",;" and not quoted:
            entries.append("".join(current))
            current = []
        else:
            current.append(ch)
    entries.append("".join(current))
    return [entry.strip() for entry in entries if entry.strip()]


def _is_address(entry: str) -> bool:
    """Judged by the parser that will send it, so what passes here is what is sent to."""
    try:
        header = EmailMessage()
        header["To"] = entry
        parsed = header["To"]
    except Exception:
        return False
    if parsed.defects or len(parsed.addresses) != 1:
        return False
    found = parsed.addresses[0]
    return bool(found.username and found.domain) and not _ODD_ADDRESS.search(found.addr_spec)


def check_recipients(to: str, cc: str) -> tuple[str, str, str]:
    """(to, cc, problem): the two lines as they will be sent, or why they cannot be."""
    lines = []
    for text in (to, cc):
        entries = _entries(text)
        for entry in entries:
            if not _is_address(entry):
                return "", "", f'"{entry}" is not an email address.'
        lines.append(", ".join(entries))
    if not lines[0]:
        return "", "", "Add at least one recipient."
    return lines[0], lines[1], ""


def _with_original(draft: dict[str, Any]) -> str:
    """The text that is sent: the reply, then the message it answers, quoted the usual way."""
    body = draft["body"].rstrip() + "\n"
    if not draft["orig_text"]:
        return body
    who = draft["orig_sender"] or "the sender"
    lead = f"On {draft['orig_date']}, {who} wrote:" if draft["orig_date"] else f"{who} wrote:"
    quoted = "\n".join(f"> {line}" if line else ">" for line in draft["orig_text"].splitlines())
    return f"{body}\n{lead}\n{quoted}\n"


def _readable(reason: str) -> str:
    """A mail server's answer without Python's brackets and quotes around it."""
    reason = _SERVER_SAID.sub(lambda said: f"{said.group(1)} {said.group(3)}", reason)
    return re.sub(r"'([^'\s]+@[^'\s]+)'", r"\1", reason).strip("{}")


def _plain_send_error(error: str) -> str:
    """The shared send path words a failure for the agent ("SMTP login failed: …", "send
    failed: …"). This words it for a person, and keeps apart the two cases that look alike
    and are not: the server said no (nothing went), and nothing came back (it may have gone)."""
    for stage in ("SMTP login failed: ", "send failed: "):
        if not error.startswith(stage):
            continue
        reason, signing_in = error[len(stage) :], stage.startswith("SMTP")
        if _SERVER_SAID.search(reason):
            lead = "Could not sign in to send mail: " if signing_in else "The mail server did not accept the message: "
            return lead + _readable(reason)
        if signing_in:
            return "Could not reach the mail server, so nothing was sent. Check your connection and try again."
        return (
            "The connection was lost while sending, so the message may or may not have gone. "
            "Check Sent before sending again."
        )
    return error


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
        sort_complete: Optional[Callable[[str, str], str]] = None,
        language: Callable[[], str] = lambda: "en",
        downloads: Optional[Path] = None,
    ) -> None:
        self._secrets = secrets
        self._imap_factory = imap_factory
        self._smtp_factory = smtp_factory
        # The model, as `complete(system, user) -> str`. It raises with a plain reason.
        self._complete = complete
        # The model that sorts, in the same shape: the cheapest one that fits, since it is
        # asked about every new conversation. `language` is the app's, for the summaries.
        self._sort_complete = sort_complete
        self._language = language
        self._conn = MailConnection(secrets, imap_factory=imap_factory)
        self._store = MailStore(path)
        self._sync = MailSync(self._conn, self._store, then=self._sort)
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
            "sorting": self._sorting(),
            # False until the user has answered the question once, either way.
            "sorting_asked": bool(self._store.get("sorting")),
        }

    def sync(self) -> dict[str, Any]:
        account = self._account()
        if not account:
            return {"ok": False, "error": "Email is not connected."}
        # Another mailbox's mail goes now, not only once this one has logged in.
        self._store.forget_others(account)
        return {"ok": True, "started": self._sync.request()}

    def threads(self, tab: str = "all") -> dict[str, Any]:
        """The inbox, or with sorting on one of its tabs. With sorting off, and for a
        sender the user has excluded, nothing sorting once said is shown."""
        rows = self._store.threads(self._account(), INBOX)
        sorting, rules = self._sorting(), self._excluded()
        for row in rows:
            if not sorting or triage.excluded(row["sender"], rules):
                row["category"] = row["summary"] = ""
        if tab in triage.TABS and sorting:
            rows = [row for row in rows if row["category"] == tab]
        return {"ok": True, "threads": rows}

    # -- sorting ---------------------------------------------------------------------
    def _sorting(self) -> bool:
        return self._store.get("sorting") == "on"

    def _excluded(self) -> list[str]:
        try:
            rules = json.loads(self._store.get("excluded") or "[]")
        except ValueError:
            return []
        return [rule for rule in rules if isinstance(rule, str)] if isinstance(rules, list) else []

    def settings(self) -> dict[str, Any]:
        return {
            "ok": True,
            "sorting": self._sorting(),
            "excluded": self._excluded(),
            # Why the last attempt to sort did not work, or "". Shown here and nowhere else.
            "sort_error": self._store.get("sort_error"),
        }

    def put_settings(self, changes: Any) -> dict[str, Any]:
        """Turn sorting on or off, and say whose mail is never sent to be sorted."""
        account = self._account()
        if not account:
            return _not_connected()
        changes = changes if isinstance(changes, dict) else {}
        if "excluded" in changes:
            rules = changes["excluded"]
            if not isinstance(rules, list) or len(rules) > _MAX_EXCLUDED:
                return {"ok": False, "error": "This list could not be saved."}
            clean = []
            for rule in rules:
                rule = " ".join(str(rule).split()).lower() if isinstance(rule, str) else ""
                if not rule:
                    continue
                if not _EXCLUDE_RULE.fullmatch(rule) or len(rule) > 254:
                    return {
                        "ok": False,
                        "error": f'"{rule[:80]}" is not an address or a domain. '
                        "Write ana@example.com, or @example.com for everyone there.",
                    }
                clean.append(rule)
            clean = list(dict.fromkeys(clean))
        if "sorting" in changes and not isinstance(changes["sorting"], bool):
            # Anything but a plain yes or no is refused: taken as "no" it would turn
            # sorting off and remove everything it had written.
            return {"ok": False, "error": "This setting could not be saved."}
        if "excluded" in changes:
            self._store.put("excluded", json.dumps(clean))
            # What was already said about their mail goes too, not only out of sight.
            self._store.forget_sorting(
                account,
                [row["key"] for row in self._store.threads(account, INBOX) if triage.excluded(row["sender"], clean)],
            )
        if "sorting" in changes:
            on = changes["sorting"]
            self._store.put("sorting", "on" if on else "off")
            self._store.put("sort_error", "")
            if on:
                self._sync.request()
            else:
                self._store.forget_sorting(account)
        return self.settings()

    def _text_to_sort(self, account: str, newest: dict[str, Any]) -> str:
        """The start of the newest message's text. Read from the cache when the user has
        opened the message, fetched otherwise; a very large message is not fetched just to
        be sorted. What is fetched here is not kept: sorting leaves no copy of mail the
        user has not opened. A message that cannot be read is sorted by its sender and
        subject alone, so one odd email never costs the conversations sent with it."""
        folder, uid = newest["folder"], newest["uid"]
        rendered = self._store.body(account, folder, uid, time.time())
        if rendered is None and newest["size"] <= _SORT_MAX_BYTES:
            msg = self._conn.message(folder, uid)
            try:
                rendered = render_message(msg) if msg is not None else None
            except Exception:
                rendered = None
        return (rendered or {}).get("text", "")[: triage.TEXT_LIMIT]

    def _sort(self, account: str, check: Callable[[], None]) -> None:
        """The second phase of a sync pass. Does nothing, and asks no model, unless the
        user has turned sorting on."""
        if not self._sorting() or self._sort_complete is None:
            return
        epoch, rules = self._store.epoch, self._excluded()
        # An excluded sender's mail is never sent, and so never sorted. Left out before
        # the pass's limit is counted, or sixty of theirs would use it up every time.
        waiting = [
            item
            for item in self._store.to_sort(account, INBOX, _SORT_TRIES)
            if not triage.excluded(item["newest"]["sender"], rules)
        ][:_SORT_PER_PASS]
        ruled, ask = [], []
        for item in waiting:
            newest = item["newest"]
            category = triage.by_rule(newest, account)
            if category:
                ruled.append({"key": item["key"], "category": category, "summary": "", "for_message": item["for_message"]})
            else:
                ask.append(item)
        if not self._store.put_sorted(account, ruled, epoch):
            return
        for start in range(0, len(ask), _SORT_BATCH):
            check()
            # Asked again before each request: the user may have turned sorting off, or
            # excluded a sender, while the last one was on its way.
            if not self._sorting():
                return
            rules = self._excluded()
            batch = [
                item
                for item in ask[start : start + _SORT_BATCH]
                if not triage.excluded(item["newest"]["sender"], rules)
            ]
            if not batch:
                continue
            try:
                items = [
                    {
                        "key": item["key"],
                        "sender": item["newest"]["sender"],
                        "subject": item["newest"]["subject"],
                        "text": self._text_to_sort(account, item["newest"]),
                    }
                    for item in batch
                ]
                check()
                said = triage.sort_batch(self._sort_complete, items, self._language())
                problem = ""
            except (MailError, _Stopped):
                # The mailbox's trouble, or the pass being told to stop: the pass's to deal with.
                raise
            except Exception as exc:  # every way a provider can fail lands here
                said = {}
                problem = f"Mimi could not sort new mail. {exc}"[:400]
            # The answer came back to a different world if, meanwhile, the mailbox was
            # disconnected, sorting was turned off, or one of these senders was excluded.
            if epoch != self._store.epoch or not self._sorting():
                return
            self._store.put("sort_error", problem)
            rules = self._excluded()
            batch = [item for item in batch if not triage.excluded(item["newest"]["sender"], rules)]
            done = [
                {"key": item["key"], "category": said[item["key"]][0], "summary": said[item["key"]][1], "for_message": item["for_message"]}
                for item in batch
                if item["key"] in said
            ]
            # Each batch is kept as it comes back, so the list fills in as sorting goes.
            if not self._store.put_sorted(account, done, epoch):
                return
            # Asked about and not answered, or the request failed: counted, so it stops.
            self._store.note_unsorted(account, [item for item in batch if item["key"] not in said], epoch)

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

    def write_reply(self, draft_id: str, guidance: str = "") -> dict[str, Any]:
        """Ask the model for the text of a reply, from the conversation's comments. Sends
        nothing and changes nothing: the text goes back to the screen for the user to edit."""
        account = self._account()
        if not account:
            return _not_connected()
        row = self._store.draft(account, draft_id)
        if row is None or not row["thread_key"]:
            return {"ok": False, "error": _NO_DRAFT}
        noted = self._store.comments(account, row["thread_key"])
        if not reply_writer.has_something_to_say(noted["comments"], noted["note"]):
            return {"ok": False, "error": "Add a comment or a note first, so Mimi knows what to say."}
        profile = self._secrets.get("email:default") or {}
        try:
            if self._complete is None:
                raise RuntimeError("No model is set up.")
            text = reply_writer.write_reply(
                self._complete,
                original=row["orig_text"],
                sender=row["orig_sender"],
                subject=row["orig_subject"],
                date=row["orig_date"],
                comments=noted["comments"],
                note=noted["note"],
                name=str(profile.get("display_name") or "").strip(),
                guidance=str(guidance or ""),
            )
            if not text:
                raise RuntimeError("The model returned nothing. Try again.")
        except Exception as exc:  # every way a provider can fail lands here
            return {"ok": False, "error": f"Mimi could not write the reply. {exc}".strip()}
        return {"ok": True, "text": text}

    def send_draft(self, draft_id: str) -> dict[str, Any]:
        """Send a draft through the same path the agent's `email_send` uses, so it threads,
        files its Sent copy and fails the same way. Once the server has accepted the
        message this answers success whatever happens to the Sent copy, so nothing
        invites a second send."""
        account = self._account()
        if not account:
            return _not_connected()
        with self._sending_lock:
            if draft_id in self._sending:
                return {"ok": False, "error": "This message is already being sent."}
            self._sending.add(draft_id)
        # The draft stays marked as on its way until it has been deleted, so a second
        # request arriving just as the first ends cannot find it and send it again.
        try:
            row = self._store.draft(account, draft_id)
            if row is None:
                return {"ok": False, "error": _NO_DRAFT}
            profile, servers, err = load_profile(self._secrets)
            if err:
                return {
                    "ok": False,
                    "error": "Mail does not know this mailbox's servers. Add them under Connectors, Email.",
                }
            to, cc, problem = check_recipients(row["recipients"], row["cc"])
            if problem:
                return {"ok": False, "error": problem}
            try:
                msg = compose_message(
                    profile,
                    servers,
                    to=to,
                    cc=cc,
                    subject=row["subject"],
                    body=_with_original(row),
                    reply_headers={
                        "message_id": row["orig_message_id"],
                        "references": row["orig_references"],
                        "subject": row["orig_subject"],
                    }
                    if row["thread_key"]
                    else None,
                    imap_factory=self._imap_factory,
                )
                if isinstance(msg, dict):
                    raise ValueError(msg.get("error"))
                msg["Date"] = formatdate(localtime=True)
            except Exception as exc:
                # Nothing has left the computer yet.
                return {"ok": False, "error": f"This message could not be put together: {exc}"}
            self._store.mark_sending(draft_id, time.time())
            try:
                result = send_message(
                    profile, servers, msg, imap_factory=self._imap_factory, smtp_factory=self._smtp_factory
                )
            except Exception as exc:
                result = {"error": f"send failed: {exc}"}
            finally:
                self._store.mark_sending(draft_id, 0)
            if "error" in result:
                return {"ok": False, "error": _plain_send_error(str(result["error"]))}
            self._store.delete_draft(account, draft_id)
            if row["thread_key"]:
                # The reply has answered them.
                self._store.put_comments(account, row["thread_key"], [], "")
        finally:
            with self._sending_lock:
                self._sending.discard(draft_id)
        self._sync.request()
        unfiled = str(result.get("sent_copy") or "").startswith("delivered, but")
        return {"ok": True, "note": "Sent, but no copy could be saved in your Sent folder." if unfiled else ""}
