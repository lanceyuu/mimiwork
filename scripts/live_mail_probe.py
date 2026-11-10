"""Manual check of what a real mail server does, before the Mail section relies on it.

Never run in CI. Read-only unless --move is given.

    .venv/bin/python scripts/live_mail_probe.py
        the mailbox connected in the app (Connectors, Email)

    MAIL_PROBE_ADDRESS=you@example.com .venv/bin/python scripts/live_mail_probe.py
        another mailbox, without connecting it; it asks for the app password at a prompt.
        Add MAIL_PROBE_IMAP_HOST for a custom server.

--move writes one test message into INBOX, moves it to the archive folder and then to the
bin, and says where copies ended up. The test message is the only mail it touches.
"""

from __future__ import annotations

import argparse
import getpass
import imaplib
import os
import sys
import time
from email.message import EmailMessage
from email.utils import make_msgid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from coworker.connectors.email_tools import (  # noqa: E402
    _LIST_RE,
    _default_imap_factory,
    _parse_list_line,
    _quote,
    resolve_servers,
)
from coworker.secrets import SecretStore  # noqa: E402

FIELDS = (
    "FROM TO CC SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES "
    "LIST-UNSUBSCRIBE LIST-ID PRECEDENCE"
)
SPECIAL = ("\\Sent", "\\Drafts", "\\Trash", "\\Archive", "\\All", "\\Junk")


def _profile() -> dict:
    # The password is typed at a prompt, never given on the command line or in the
    # environment, so it stays out of the shell history and the process list.
    address = os.environ.get("MAIL_PROBE_ADDRESS")
    if address:
        host = os.environ.get("MAIL_PROBE_IMAP_HOST", "")
        return {
            "address": address,
            "app_password": getpass.getpass(f"App password for {address}: "),
            "imap_host": host,
            "smtp_host": host,
        }
    return SecretStore().get("email:default") or {}


def _folders(imap) -> list[tuple[str, str]]:
    _, lines = imap.list()
    out = []
    for line in lines or []:
        m = _LIST_RE.match(line) if isinstance(line, bytes) else None
        name = _parse_list_line(line) if m else None
        if name is not None:
            out.append((m.group("flags").decode(errors="replace"), name))
    return out


def _find(imap, folder: str, message_id: str, *, readonly: bool = True) -> list[bytes]:
    imap.select(_quote(folder), readonly=readonly)
    _, data = imap.uid("SEARCH", f"HEADER Message-ID {_quote(message_id)}")
    return (data[0] or b"").split()


def _move_test(imap, address: str, roles: dict) -> None:
    archive = roles["\\Archive"] or roles["\\All"]
    bin_folder = roles["\\Trash"]
    if not archive or not bin_folder:
        print(f"cannot run the move test: archive {archive!r}, bin {bin_folder!r}")
        return
    msg = EmailMessage()
    msg["From"] = msg["To"] = address
    msg["Subject"] = "MimiWork mail probe (safe to delete)"
    msg["Message-ID"] = make_msgid(domain="probe.mimiwork.invalid")
    msg.set_content("Written by scripts/live_mail_probe.py to see how this server moves mail.")
    message_id = msg["Message-ID"]
    places = list(dict.fromkeys(["INBOX", archive, bin_folder]))

    def where() -> dict:
        return {name: len(_find(imap, name, message_id)) for name in places}

    imap.append('"INBOX"', "(\\Seen)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())
    time.sleep(2)
    print("after filing the test message:", where())
    for source, target in (("INBOX", archive), (archive, bin_folder)):
        uids = _find(imap, source, message_id, readonly=False)
        if not uids:
            print(f"the test message is not in {source!r}; stopping")
            return
        status, reply = imap.uid("MOVE", uids[-1].decode(), _quote(target))
        time.sleep(2)
        print(f"MOVE {source!r} -> {target!r}: {status} {reply!r}")
        print("  now:", where())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--move",
        action="store_true",
        help="file one test message and move it to the archive, then the bin",
    )
    args = parser.parse_args()
    profile = _profile()
    if not profile.get("address") or not profile.get("app_password"):
        sys.exit("no mailbox to probe: connect Email in the app, or set MAIL_PROBE_ADDRESS")
    servers, err = resolve_servers(profile)
    if servers is None:
        sys.exit(f"no mailbox to probe: {err}")
    imap = _default_imap_factory(servers.imap_host, servers.imap_port)
    imap.login(profile["address"], profile["app_password"])
    try:
        _, caps_reply = imap.capability()
        caps = set((caps_reply[0] or b"").decode().upper().split())
        print(f"server: {servers.imap_host}")
        for cap in ("MOVE", "UIDPLUS", "SPECIAL-USE", "CONDSTORE", "IDLE"):
            print(f"  {cap}: {'yes' if cap in caps else 'NO'}")

        folders = _folders(imap)
        roles = {
            flag: next((name for flags, name in folders if flag in flags), None)
            for flag in SPECIAL
        }
        print("special folders, by flag:")
        for flag, name in roles.items():
            print(f"  {flag}: {name!r}")
        print("every folder name:", [name for _, name in folders])

        _, count = imap.select('"INBOX"', readonly=True)
        print(f"INBOX: {count[0].decode()} messages, UIDVALIDITY {imap.response('UIDVALIDITY')[1]}")
        _, found = imap.uid("SEARCH", 'HEADER List-Unsubscribe ""')
        uids = (found[0] or b"").split()
        if not uids:
            print("no message with List-Unsubscribe in INBOX; cannot check the header fetch")
        else:
            _, fetched = imap.uid(
                "FETCH",
                uids[-1].decode(),
                f"(UID FLAGS RFC822.SIZE BODYSTRUCTURE BODY.PEEK[HEADER.FIELDS ({FIELDS})])",
            )
            print("header fetch reply, item by item (the shape imap.py has to parse):")
            for item in fetched:
                if isinstance(item, tuple):
                    names = sorted(
                        {
                            line.split(b":")[0].decode().lower()
                            for line in item[1].splitlines()
                            if b":" in line and not line[:1].isspace()
                        }
                    )
                    print(f"  tuple, before the headers: {item[0][:120]!r}")
                    print(f"         header names returned: {names}")
                else:
                    print(f"  bytes: {item[:120]!r}")
        if args.move:
            _move_test(imap, profile["address"], roles)
    finally:
        imap.logout()


if __name__ == "__main__":
    main()
