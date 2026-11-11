"""Bring the cache up to date with the mailbox, one pass at a time, off the request path."""

from __future__ import annotations

import threading
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Optional

from ..connectors.email_tools import decode_mime_header
from .imap import MailConnection, MailError
from .store import MailStore
from .threads import thread_key


def message_row(account: str, folder: str, item: dict[str, Any]) -> dict[str, Any]:
    """A cache row from one parsed header fetch (`MailConnection.headers`)."""
    headers = item["headers"]
    try:
        sent = parsedate_to_datetime(str(headers.get("Date", "")))
        # A date with no zone, or "-0000", is UTC by convention, not this computer's time.
        date = (sent if sent.tzinfo else sent.replace(tzinfo=timezone.utc)).timestamp()
    except Exception:
        # No readable Date: when the server received it, so it does not sink out of sight.
        date = float(item.get("received") or 0)
    bulk = (
        headers.get("List-Unsubscribe")
        or headers.get("List-Id")
        or str(headers.get("Precedence", "")).strip().lower() == "bulk"
    )
    return {
        "account": account,
        "folder": folder,
        "uid": item["uid"],
        "message_id": " ".join(str(headers.get("Message-ID") or "").split()),
        "thread_key": thread_key(headers, account=account, folder=folder, uid=item["uid"]),
        "sender": decode_mime_header(headers.get("From", "")),
        "recipients": decode_mime_header(headers.get("To", "")),
        "cc": decode_mime_header(headers.get("Cc", "")),
        "subject": decode_mime_header(headers.get("Subject", "")),
        "date": date,
        "flags": item["flags"],
        "size": item["size"],
        "has_attachments": int(bool(item["has_attachments"])),
        "bulk": int(bool(bulk)),
    }


class _Stopped(Exception):
    """The pass ends here and nothing is wrong: it was told to stop, or the user changed
    something while it was reading, in which case the pass their change asked for follows."""


class MailSync:
    def __init__(
        self,
        conn: MailConnection,
        store: MailStore,
        then: Optional[Callable[[str, Callable[[], None]], None]] = None,
    ) -> None:
        self._conn = conn
        self._store = store
        # The second phase of a pass, run once the mail itself is up to date: sorting. It
        # is given the account and a check to call between slow steps, which ends the pass
        # at once if it has been told to stop.
        self._then = then
        self._lock = threading.Lock()
        self._running = False
        self._again = False
        self._stopping = False
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self._running

    def request(self) -> bool:
        """Start a pass and return True, or, if one is running, leave a mark so that one
        more runs after it and return False. An archive or a send made while a pass is
        under way is then still picked up."""
        with self._lock:
            if self._running:
                self._again = True
                return False
            self._running = True
            self._thread = threading.Thread(target=self._loop, name="mail-sync", daemon=True)
            # Started inside the lock, so stop() never finds a thread it cannot wait for.
            self._thread.start()
        return True

    def stop(self, timeout: float = 35.0) -> None:
        """End the pass under way and wait for it, so nothing is written after this returns.
        Used before the cache is emptied or closed: a pass still running would otherwise
        put a disconnected mailbox's mail back on disk."""
        with self._lock:
            self._again = False
            # Stays set until the pass has really ended (the loop clears it), so a pass
            # that outlives the wait below still writes nothing more.
            self._stopping = self._running
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            # At most one server operation away: the pass checks between each of them.
            thread.join(timeout)

    def _loop(self) -> None:
        try:
            while True:
                try:
                    self.run_once()
                    self._note("")
                except _Stopped:
                    pass
                except MailError as exc:
                    self._note(str(exc))
                except Exception as exc:
                    self._note(f"could not sync: {exc}")
                with self._lock:
                    if not self._again or self._stopping:
                        self._running = self._again = self._stopping = False
                        return
                    self._again = False
        except Exception:
            # Even writing down why a pass failed can fail (the cache was closed under
            # it). Whatever happened, "running" must not stay on, or Mail never syncs again.
            with self._lock:
                self._running = self._again = self._stopping = False

    def _note(self, error: str) -> None:
        # A pass that was told to stop says nothing: its mailbox has been disconnected, and
        # "not connected" would be left behind as the reason for a sync nobody asked for.
        if not self._stopping:
            self._store.put("last_error", error)

    def _check(self) -> None:
        if self._stopping:
            raise _Stopped()

    def run_once(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        info = self._conn.describe()
        account, roles = info["account"], info["roles"]
        self._check()
        self._store.forget_others(account)
        for role in ("archive", "bin"):
            self._store.put(f"can_{role}", "1" if info["can_move"] and roles.get(role) else "")
        # Sent is synced so a conversation shows your own replies.
        synced = [roles[role] for role in ("inbox", "sent") if roles.get(role)]
        for role in ("inbox", "sent"):
            if roles.get(role):
                self._folder(account, roles[role], role, now)
        self._check()
        # A server can rename its Sent folder; mail cached under the old name must not stay.
        self._store.keep_folders(account, synced)
        self._store.prune(now)
        self._store.put("last_sync", str(now))
        if self._then is not None:
            self._check()
            self._then(account, self._check)

    def _folder(self, account: str, folder: str, role: str, now: float) -> None:
        # ponytail: polled, and flags are read over the whole window on every pass.
        # Move to CONDSTORE (changed-since) or IDLE when a mailbox is big enough to feel it.
        # Noted before the server is asked anything. Each write below hands it back, and is
        # refused if the user has marked or moved something since: what this pass read is
        # then out of date. The pass ends there, and the one their change asked for reads
        # the mailbox afresh.
        mark = self._store.touched
        validity, window = self._conn.window(folder)
        self._check()
        if validity != self._store.folder_validity(account, folder):
            self._store.reset_folder(account, folder, role, validity)
        cached, wanted = self._store.uids(account, folder), set(window)
        # Gone from the server, moved by another mail app, or aged out of the window.
        if not self._store.remove(account, folder, sorted(cached - wanted), expect=mark):
            raise _Stopped()
        new = sorted(wanted - cached, reverse=True)
        # Newest first and a couple of hundred at a time, so the list fills from the top.
        for start in range(0, len(new), 200):
            fetched = self._conn.headers(folder, new[start : start + 200])
            self._check()
            rows = [message_row(account, folder, item) for item in fetched]
            if not self._store.add(rows, expect=mark):
                raise _Stopped()
        kept = cached & wanted
        if kept:
            flags = self._conn.flags(folder, min(kept))
            self._check()
            if not self._store.set_flags(account, folder, flags, expect=mark):
                raise _Stopped()
        self._store.mark_synced(account, folder, now)
