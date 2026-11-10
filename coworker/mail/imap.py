"""One logged-in connection to the mailbox, and every operation Mail makes on it.

The agent's mail tools log in afresh for each call and never change the mailbox. Mail is
on screen for minutes at a time and does change it (read, archive, bin), so it keeps one
connection of its own. Uids mean nothing without their folder, so every operation names
its folder and selects it inside the lock; no caller relies on what was selected before.
"""

from __future__ import annotations

import email as email_lib
import hashlib
import imaplib
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from ..connectors.email_tools import (
    _LIST_RE,
    _MONTHS,
    _SENT_NAMES,
    _auth_hint,
    _default_imap_factory,
    _imap_login,
    _parse_list_line,
    _quote,
    build_search_criteria,
    load_profile,
)
from ..secrets import SecretStore

HEADER_FIELDS = (
    "FROM TO CC SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES "
    "LIST-UNSUBSCRIBE LIST-ID PRECEDENCE"
)
_HEADER_SPEC = (
    f"(UID FLAGS INTERNALDATE RFC822.SIZE BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS ({HEADER_FIELDS})])"
)
_BIN_NAMES = ("Trash", "Deleted Items", "Deleted Messages", "Bin", "INBOX.Trash")
_ARCHIVE_NAMES = ("Archive", "Archives", "INBOX.Archive")
# A server may refuse a very long command line, so uids go out a couple of hundred at a time.
_CHUNK = 200


class MailError(Exception):
    """A failure whose message is fit to show the user as it is."""


def _uid_set(uids: list[int]) -> str:
    return ",".join(str(uid) for uid in uids)


def _roles(imap) -> dict[str, Optional[str]]:
    """Which folder plays which part: by RFC 6154 flag, then by conventional name."""
    status, lines = imap.list()
    folders: list[tuple[bytes, str]] = []
    for line in (lines or []) if status == "OK" else []:
        m = _LIST_RE.match(line) if isinstance(line, bytes) else None
        name = _parse_list_line(line) if m else None
        if name is not None:
            folders.append((m.group("flags"), name))
    names = [name for _, name in folders]

    def flagged(flag: bytes) -> Optional[str]:
        return next((name for flags, name in folders if flag in flags), None)

    def named(candidates: tuple[str, ...]) -> Optional[str]:
        return next((name for name in candidates if name in names), None)

    return {
        "inbox": "INBOX",
        "sent": flagged(rb"\Sent") or named(_SENT_NAMES),
        "all": flagged(rb"\All"),
        # Gmail has no archive folder: taking a message out of the inbox leaves it in All Mail.
        "archive": flagged(rb"\Archive") or flagged(rb"\All") or named(_ARCHIVE_NAMES),
        "bin": flagged(rb"\Trash") or named(_BIN_NAMES),
    }


def _search(imap, criteria) -> list[int]:
    status, data = imap.uid("SEARCH", criteria)
    if status != "OK":
        raise MailError("the mail server could not search this folder")
    return [int(uid) for uid in (data[0] or b"").split()]


def _fetch(imap, uid_set: str, spec: str) -> list:
    status, data = imap.uid("FETCH", uid_set, spec)
    if status != "OK":
        raise MailError("the mail server could not read these messages")
    return data or []


_HEADERS_LITERAL = re.compile(rb"BODY\[HEADER\.FIELDS \([^)]*\)\] \{\d+\}$")


def _answers(data: list):
    """One (meta, literals) pair for each message in a FETCH reply.

    imaplib cuts a message's answer at every literal: each cut is a tuple of the text
    before the literal and the literal itself, and the text after the last one is a plain
    bytes item that ends the message. An answer with no literal is that one item alone,
    which is also how a flag change made elsewhere turns up unasked in a reply.
    """
    meta, literals = b"", []
    for item in data:
        if isinstance(item, tuple):
            meta += item[0] + b" "
            literals.append(item)
        elif isinstance(item, bytes):
            yield meta + item, literals
            meta, literals = b"", []


def _parse_headers(data: list) -> list[dict[str, Any]]:
    out = []
    for meta, literals in _answers(data):
        # A server may send a string inside BODYSTRUCTURE as a literal too (a file name
        # with a quote in it), so the headers are the literal announced as the headers,
        # not simply the first one.
        headers = next((body for before, body in literals if _HEADERS_LITERAL.search(before)), None)
        uid = re.search(rb"UID (\d+)", meta)
        if headers is None or not uid:
            continue
        flags = re.search(rb"FLAGS \(([^)]*)\)", meta)
        size = re.search(rb"RFC822\.SIZE (\d+)", meta)
        received = imaplib.Internaldate2tuple(meta)
        out.append(
            {
                "uid": int(uid.group(1)),
                # When the server took the message in: its date when it has none of its own.
                "received": time.mktime(received) if received else 0.0,
                "flags": flags.group(1).decode() if flags else "",
                "size": int(size.group(1)) if size else 0,
                "has_attachments": b'"ATTACHMENT"' in meta.upper(),
                "headers": email_lib.message_from_bytes(headers),
            }
        )
    return out


class MailConnection:
    def __init__(
        self,
        secrets: SecretStore,
        *,
        imap_factory: Callable[[str, int], imaplib.IMAP4] = _default_imap_factory,
    ) -> None:
        self._secrets = secrets
        self._factory = imap_factory
        # ponytail: one connection behind one lock, so Mail does one thing at a time.
        # Add a second connection, or IMAP IDLE, if sync is seen to delay clicks.
        self._lock = threading.Lock()
        self._imap: Any = None
        self._key = ""
        self._account = ""
        self._selected = ""
        self._exists = 0
        self._uidvalidity = 0
        self._can_move = False
        self._roles: dict[str, Optional[str]] = {}

    # -- the connection ----------------------------------------------------------
    def close(self) -> None:
        with self._lock:
            self._drop()

    def _drop(self, *, dead: bool = False) -> None:
        imap, self._imap, self._key, self._selected = self._imap, None, "", ""
        if imap is None:
            return
        try:
            # A polite logout waits for the server's goodbye. On a line that has already
            # gone quiet that wait is another full timeout with the lock held, so a dead
            # connection is simply closed.
            imap.shutdown() if dead else imap.logout()
        except Exception:
            pass

    def _ensure(self):
        profile, servers, err = load_profile(self._secrets)
        if err:
            self._drop()
            raise MailError(err["error"])
        # Keyed by what was used to log in, so a changed password or a different mailbox
        # is noticed on the next operation instead of living on in an old connection.
        key = hashlib.sha256(
            "\0".join(
                [profile["address"], profile["app_password"], servers.imap_host, str(servers.imap_port)]
            ).encode()
        ).hexdigest()
        if self._imap is not None and key == self._key:
            return self._imap
        self._drop()
        try:
            imap = _imap_login(profile, servers, self._factory)
        except (OSError, imaplib.IMAP4.abort) as exc:
            raise MailError(f"could not reach the mail server: {exc}") from exc
        except Exception as exc:
            raise MailError(f"IMAP login failed: {exc}.{_auth_hint(servers)}") from exc
        # Held before the key is set: if anything below fails, the next operation finds a
        # connection without a matching key and closes it, so it is never left open.
        self._imap = imap
        _, caps = imap.capability()
        # The last answer is the one to this request; earlier items can be the list the
        # server volunteered at login, before it knew who was asking.
        self._can_move = "MOVE" in (caps[-1] or b"").decode().upper().split()
        self._roles = _roles(imap)
        self._key, self._account = key, profile["address"]
        return imap

    def _select(self, imap, folder: str) -> None:
        self._selected = ""
        try:
            status, data = imap.select(_quote(folder))
        except imaplib.IMAP4.readonly:
            # A folder the server will not let anyone change can still be read.
            status, data = imap.select(_quote(folder), readonly=True)
        if status != "OK":
            raise MailError(f"cannot open folder {folder!r}")
        self._exists = int(data[0] or 0)
        _, validity = imap.response("UIDVALIDITY")
        self._uidvalidity = int(validity[0]) if validity and validity[0] else 0
        self._selected = folder

    def _run(self, folder: str, operation: Callable[[Any], Any], *, fresh: bool = False):
        """One operation under the lock, in its folder; one new login if the line dropped."""
        with self._lock:
            for attempt in (1, 2):
                try:
                    imap = self._ensure()
                    if folder and (fresh or folder != self._selected):
                        self._select(imap, folder)
                    return operation(imap)
                except imaplib.IMAP4.readonly as exc:
                    # A subclass of abort, but the line is fine: the folder is read-only.
                    raise MailError("this folder cannot be changed") from exc
                except (imaplib.IMAP4.abort, OSError) as exc:
                    self._drop(dead=True)
                    if attempt == 2:
                        raise MailError(f"the mail server stopped answering: {exc}") from exc
                except imaplib.IMAP4.error as exc:
                    raise MailError(f"the mail server refused: {exc}") from exc

    # -- operations ----------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        """The mailbox's address, its special folders, and whether it can move mail."""
        return self._run(
            "",
            lambda imap: {
                "account": self._account,
                "roles": dict(self._roles),
                "can_move": self._can_move,
            },
        )

    def window(
        self, folder: str, *, days: int = 60, newest: int = 300, cap: int = 2000
    ) -> tuple[int, list[int]]:
        """(uidvalidity, uids) of the mail Mail keeps: the newest `newest` by arrival and
        everything from the last `days` days, whichever reaches further back, capped."""

        def operation(imap):
            if not self._exists:
                return self._uidvalidity, []
            since = datetime.now(timezone.utc) - timedelta(days=days)
            recent = _search(imap, f"SINCE {since.day:02d}-{_MONTHS[since.month - 1]}-{since.year}")
            # A sequence range, not SEARCH ALL: a mailbox of 100,000 answers with 300 uids.
            tail = _search(imap, f"{max(1, self._exists - newest + 1)}:*")
            return self._uidvalidity, sorted(set(recent) | set(tail))[-cap:]

        # Always a fresh SELECT: it is what reports the message count and the uidvalidity.
        return self._run(folder, operation, fresh=True)

    def headers(self, folder: str, uids: list[int]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for start in range(0, len(uids), _CHUNK):
            chunk = _uid_set(uids[start : start + _CHUNK])
            out += self._run(
                folder, lambda imap, c=chunk: _parse_headers(_fetch(imap, c, _HEADER_SPEC))
            )
        return out

    def flags(self, folder: str, low_uid: int) -> dict[int, str]:
        """Flags of every message from `low_uid` up, asked as one range, not a list."""

        def operation(imap):
            out: dict[int, str] = {}
            for meta, _ in _answers(_fetch(imap, f"{low_uid}:*", "(UID FLAGS)")):
                uid = re.search(rb"UID (\d+)", meta)
                flags = re.search(rb"FLAGS \(([^)]*)\)", meta)
                # "n:*" always brings the newest message along, even when it is below n.
                if uid and flags and int(uid.group(1)) >= low_uid:
                    out[int(uid.group(1))] = flags.group(1).decode()
            return out

        return self._run(folder, operation)

    def message(self, folder: str, uid: int) -> Optional[email_lib.message.Message]:
        def operation(imap):
            for _, literals in _answers(_fetch(imap, str(uid), "(UID BODY.PEEK[])")):
                for before, body in literals:
                    if b"BODY[]" in before:
                        return email_lib.message_from_bytes(body)
            return None

        return self._run(folder, operation)

    # set_seen and move act on uids from the cache. That is sound because every sync pass
    # begins with window(), which drops a folder's cached uids when its uidvalidity changes.
    def set_seen(self, folder: str, uids: list[int], seen: bool) -> None:
        def operation(imap):
            status, _ = imap.uid(
                "STORE", _uid_set(uids), "+FLAGS" if seen else "-FLAGS", r"(\Seen)"
            )
            if status != "OK":
                raise MailError("the mail server refused the change")

        if uids:
            self._run(folder, operation)

    def move(self, folder: str, uids: list[int], role: str) -> None:
        """Move to the `archive` or `bin` folder. There is no copy-and-delete fallback:
        without MOVE, deleting the original can take other messages with it."""

        def operation(imap):
            target = self._roles.get(role)
            if not self._can_move or not target:
                raise MailError("this mailbox cannot move mail")
            status, _ = imap.uid("MOVE", _uid_set(uids), _quote(target))
            if status != "OK":
                raise MailError(f"the mail server refused to move the message to {target}")

        if uids:
            self._run(folder, operation)

    def search(self, folder: str, text: str, *, limit: int = 25) -> list[int]:
        """Uids of the newest `limit` messages matching `text`, newest first."""
        criteria, err = build_search_criteria(text=text)
        if criteria is None:
            raise MailError(err)
        return self._run(folder, lambda imap: _search(imap, criteria)[-limit:][::-1])
