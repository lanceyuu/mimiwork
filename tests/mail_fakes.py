"""A mail server in memory for the Mail tests: folders, uids, flags, and the handful of
IMAP commands `coworker/mail/imap.py` sends. No network, no real mailbox."""

from __future__ import annotations

import email
import email.policy
import imaplib
import re
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime, parsedate_to_datetime

from coworker.secrets import SecretStore

ADDRESS = "user@example.com"
PASSWORD = "abcd efgh"
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

PLAIN_FOLDERS = {
    "INBOX": "\\HasNoChildren",
    "Sent": "\\HasNoChildren \\Sent",
    "Archive": "\\HasNoChildren \\Archive",
    "Trash": "\\HasNoChildren \\Trash",
}
GMAIL_FOLDERS = {
    "INBOX": "\\HasNoChildren",
    "[Gmail]": "\\Noselect \\HasChildren",
    "[Gmail]/All Mail": "\\HasNoChildren \\All",
    "[Gmail]/Sent Mail": "\\HasNoChildren \\Sent",
    "[Gmail]/Trash": "\\HasNoChildren \\Trash",
}


def connected_secrets(tmp_path, *, password: str = PASSWORD) -> SecretStore:
    secrets = SecretStore(tmp_path / "secrets.json")
    secrets.put(
        "email:default",
        {
            "address": ADDRESS,
            "app_password": password,
            "imap_host": "mail.example.com",
            "smtp_host": "mail.example.com",
        },
    )
    return secrets


def mail(
    subject: str = "Hello",
    *,
    sender: str = "Ana <ana@example.com>",
    to: str = ADDRESS,
    message_id: str = "",
    references: str = "",
    in_reply_to: str = "",
    days_ago: float = 0,
    body: str = "Body.",
    html: str = "",
    attachment: str = "",
    headers: dict[str, str] | None = None,
) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc) - timedelta(days=days_ago))
    if message_id:
        msg["Message-ID"] = message_id
    if references:
        msg["References"] = references
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    for name, value in (headers or {}).items():
        msg[name] = value
    msg.set_content(body)
    if html:
        msg.add_alternative(html, subtype="html")
    if attachment:
        msg.add_attachment(
            b"%PDF-fake", maintype="application", subtype="pdf", filename=attachment
        )
    return msg


class FakeMailServer:
    """Pass `server.connect` wherever an `imap_factory` is wanted."""

    def __init__(self, *, folders: dict[str, str] | None = None, move: bool = True):
        self.capabilities = "IMAP4rev1 UIDPLUS" + (" MOVE" if move else "")
        self.password = PASSWORD
        self.listing: dict[str, str] = {}
        self.folders: dict[str, dict[int, list]] = {}  # name -> {uid: [message, flags]}
        self.uidvalidity: dict[str, int] = {}
        self._next: dict[str, int] = {}
        self.logins = 0
        self.drops = 0  # how many of the next commands lose the connection
        self.unasked: list[bytes] = []  # flag changes made elsewhere, sent with the next FETCH
        self.read_only: set[str] = set()  # folders the server will not let anyone change
        self.log: list[tuple] = []
        for name, flags in (folders or PLAIN_FOLDERS).items():
            self.add_folder(name, flags)

    def add_folder(self, name: str, flags: str = "\\HasNoChildren") -> None:
        self.listing[name] = flags
        if "\\Noselect" not in flags:
            self.folders[name] = {}
            self.uidvalidity[name] = 1
            self._next[name] = 1

    def add(self, folder: str, message: EmailMessage, *, seen: bool = False) -> int:
        uid = self._next[folder]
        self._next[folder] += 1
        self.folders[folder][uid] = [message, {"\\Seen"} if seen else set()]
        return uid

    def flags(self, folder: str, uid: int) -> set[str]:
        return self.folders[folder][uid][1]

    def subjects(self, folder: str) -> list[str]:
        return [entry[0]["Subject"] for _, entry in sorted(self.folders[folder].items())]

    def commands(self, name: str) -> list[tuple]:
        return [entry for entry in self.log if entry[0] == name]

    def connect(self, host: str, port: int) -> "FakeMailConnection":
        return FakeMailConnection(self)


class FakeMailConnection:
    def __init__(self, server: FakeMailServer):
        self.server = server
        self.selected = ""
        self._untagged: dict[str, list] = {}

    def _step(self, *entry) -> None:
        self.server.log.append(entry)
        if self.server.drops:
            self.server.drops -= 1
            raise imaplib.IMAP4.abort("socket error: EOF")

    def login(self, user, password):
        self.server.logins += 1
        if password != self.server.password:
            raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials")
        return "OK", [b"Logged in"]

    def capability(self):
        return "OK", [self.server.capabilities.encode()]

    def list(self):
        return "OK", [
            f'({flags}) "/" "{name}"'.encode() for name, flags in self.server.listing.items()
        ]

    def select(self, mailbox, readonly=False):
        name = mailbox.strip('"')
        self._step("select", name)
        if name in self.server.read_only and not readonly:
            raise imaplib.IMAP4.readonly(f"{name} is not writable")
        if name not in self.server.folders:
            return "NO", [b"no such mailbox"]
        self.selected = name
        self._untagged["UIDVALIDITY"] = [str(self.server.uidvalidity[name]).encode()]
        return "OK", [str(len(self.server.folders[name])).encode()]

    def response(self, code):
        return code, self._untagged.pop(code, [None])

    def logout(self):
        self.server.log.append(("logout",))
        return "BYE", []

    def shutdown(self):
        self.server.log.append(("shutdown",))

    def append(self, mailbox, flags, date_time, message):
        """How a sent message's copy is filed in Sent."""
        name = mailbox.strip('"')
        self._step("append", name)
        if name in self.server.read_only:
            return "NO", [b"cannot append"]
        parsed = email.message_from_bytes(message, policy=email.policy.default)
        self.server.add(name, parsed, seen="\\Seen" in flags)
        return "OK", [b"APPEND completed"]

    def uid(self, command, *args):
        self._step(command, self.selected, *args)
        box = self.server.folders[self.selected]
        if command in ("STORE", "MOVE") and self.selected in self.server.read_only:
            raise imaplib.IMAP4.readonly("mailbox status changed to READ-ONLY")
        if command == "SEARCH":
            found = self._search(box, args[0])
            return "OK", [" ".join(str(uid) for uid in found).encode()]
        if command == "FETCH":
            return "OK", self._fetch(box, args[0], args[1])
        if command == "STORE":
            for uid in self._uids(box, args[0]):
                change = box[uid][1].add if args[1].startswith("+") else box[uid][1].discard
                change("\\Seen")
            return "OK", [None]
        if command == "MOVE":
            if "MOVE" not in self.server.capabilities.split():
                raise imaplib.IMAP4.error("BAD unknown command MOVE")
            target = args[1].strip('"')
            for uid in self._uids(box, args[0]):
                message, flags = box.pop(uid)
                self.server.folders[target][self.server.add(target, message)][1] = flags
            return "OK", [None]
        raise AssertionError(f"unexpected uid command {command}")

    @staticmethod
    def _uids(box, spec) -> list[int]:
        spec = spec.decode() if isinstance(spec, bytes) else str(spec)
        top = max(box, default=0)
        out: set[int] = set()
        for part in spec.split(","):
            low, _, high = part.partition(":")
            a, b = int(low), (top if high == "*" else int(high or low))
            # As on a real server, "n:*" reaches the newest message even when n is past it.
            out.update(uid for uid in box if min(a, b) <= uid <= max(a, b))
        return sorted(out)

    @staticmethod
    def _search(box, criteria) -> list[int]:
        text = criteria.decode() if isinstance(criteria, bytes) else str(criteria)
        uids = sorted(box)
        if text == "ALL":
            return uids
        if m := re.fullmatch(r"(\d+):\*", text):  # a sequence range: the n-th message on
            return uids[int(m.group(1)) - 1 :]
        if m := re.fullmatch(r"SINCE (\d{2})-(\w{3})-(\d{4})", text):
            since = datetime(int(m.group(3)), MONTHS.index(m.group(2)) + 1, int(m.group(1))).date()
            return [u for u in uids if parsedate_to_datetime(box[u][0]["Date"]).date() >= since]
        if m := re.fullmatch(r'TEXT "(.*)"', text):
            needle = m.group(1).lower()
            return [u for u in uids if needle in box[u][0].as_string().lower()]
        raise AssertionError(f"unexpected search {text!r}")

    def _fetch(self, box, uid_spec, spec) -> list:
        wanted = set(self._uids(box, uid_spec))
        out: list = list(self.server.unasked)
        self.server.unasked.clear()
        for seq, uid in enumerate(sorted(box), 1):
            if uid not in wanted:
                continue
            message, flags = box[uid]
            raw = message.as_bytes()
            meta = f"{seq} (UID {uid} FLAGS ({' '.join(sorted(flags))})"
            if "INTERNALDATE" in spec:
                meta += ' INTERNALDATE "09-Jun-2026 10:00:00 +0000"'
            if "BODY.PEEK[]" in spec:
                out += [(f"{meta} BODY[] {{{len(raw)}}}".encode(), raw), b")"]
            elif "HEADER.FIELDS" in spec:
                names = spec.split("HEADER.FIELDS (")[1].split(")")[0].split()
                head = "".join(f"{n}: {message[n]}\r\n" for n in names if message[n]) + "\r\n"
                announce = f"BODY[HEADER.FIELDS ({' '.join(names)})] {{{len(head)}}}"
                files = [part.get_filename() for part in message.iter_attachments()]
                if files:
                    # The file name sent as a literal, ahead of the headers: what a real
                    # server does for a name it cannot put in quotes.
                    out += [
                        (
                            f'{meta} RFC822.SIZE {len(raw)} BODYSTRUCTURE ("ATTACHMENT" '
                            f'("FILENAME" {{{len(files[0])}}}'.encode(),
                            files[0].encode(),
                        ),
                        (f")) {announce}".encode(), head.encode()),
                        b")",
                    ]
                else:
                    # Flags before the headers and the rest after: real servers do both.
                    out += [
                        (f"{meta} {announce}".encode(), head.encode()),
                        f' RFC822.SIZE {len(raw)} BODYSTRUCTURE ("TEXT" "PLAIN"))'.encode(),
                    ]
            else:
                out.append(f"{meta})".encode())
        return out or [None]


class FakeSMTP:
    """Pass `smtp.connect` wherever an `smtp_factory` is wanted."""

    def __init__(self):
        self.sent: list[EmailMessage] = []
        self.refuse = ""  # when set, the server refuses every message with this reason
        self.unreachable = ""  # when set, the server cannot be reached at all
        self.before_accepting = None  # called while a message is on its way

    def connect(self, host: str, port: int) -> "FakeSMTP":
        if self.unreachable:
            raise OSError(self.unreachable)
        return self

    def login(self, user, password):
        if password != PASSWORD:
            raise RuntimeError("(535, b'authentication failed')")

    def send_message(self, msg):
        if self.before_accepting:
            self.before_accepting()
        if self.refuse:
            raise RuntimeError(self.refuse)
        self.sent.append(msg)

    def quit(self):
        pass
