# Mail, Plan A: the reader — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Mail section that lists the connected mailbox's inbox as threads, shows each email as it was sent without letting it run, load or navigate, and can search, save attachments, archive, bin and mark read or unread.

**Architecture:** A new package `coworker/mail/` holds one reused IMAP connection (`imap.py`), a SQLite cache (`store.py`), a background sync pass (`sync.py`), threading and rendering as pure functions (`threads.py`, `render.py`) and a facade (`service.py`) the REST routes call. The screen is five React components under `components/mail/`; the email is made inert in the app (`disarm.ts`) before a sandboxed frame ever loads it, and the app reads the frame from outside on a timer because nothing inside it can run.

**Tech Stack:** Python 3.11 standard library (`imaplib`, `sqlite3`, `email`), FastAPI; React + TypeScript, vitest, Playwright (Chromium and WebKit).

**Spec:** `docs/superpowers/specs/2026-11-10-mail-client-design.md`. Read it before starting a chunk. This plan builds steps 1 to 3 of its build order. Comments and replies are Plan B; AI sorting is Plan C.

**How this plan was checked.** Every code block below was applied to a throwaway copy of the repository at `bcbce42` and run there, then pasted in from the files that ran. In that copy the whole backend suite, the whole GUI unit suite, the type check, the linter and the whole Chromium browser suite pass. Four things were not run and are marked where they occur: the live mail-server probe (Task 1), the probe of the real app window (Task 2, Step 7), the safety tests in WebKit (Task 17, because WebKit for the tests is a download that needs the owner's word), and the fallback in Task 12, Step 5. `docs/superpowers/plans/mail-reader-preview/` holds five screenshots of the screen this plan builds, taken against the mocked backend.

**Standing rules for whoever executes this** (from `AGENTS.md`):

- Never build, tag, push or release. Commit locally and stop.
- Tests are named as sentences about behaviour. Comments say why, never what.
- Every string a user sees is plain language, with no jargon and no emojis.
- Gates before each commit that touches the side named: `.venv/bin/pytest -q` and `.venv/bin/ruff check coworker tests scripts` (Python); `npm test`, `npx tsc --noEmit`, `npm run lint` and `npm run e2e` in `surfaces/gui` (GUI).
- End every commit message with `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

---

## Open items from the last review round (do these before starting Chunk 7)

The plan's second review of the backend chunks ended with these still open. None is in the code below yet.

- **Disconnecting must not block the sidecar.** `POST /v1/connectors/{name}/disconnect` is an `async def` route. `MailService.forget()` waits for a running sync pass (up to 35 seconds) and logs out. Task 10 must run it off the event loop, for example `await asyncio.to_thread(manager.mail.forget)` in the route when `name == "email"`, and `aclose` must do the same for `mail.close()`. Add a test.
- **The full backend suite, the full GUI suite and the Chromium browser suite were last run before the final batch of backend fixes** (the `changing()` guard, `render.py`'s choice of parts, `INTERNALDATE`, read-only folders). The 122 mail and email-tool tests pass on the final code; rerun everything before trusting it.
- **Chunks 4 to 6 were not reviewed a third time** after those fixes.

## Decisions this plan makes where the spec left room

- **A facade, `coworker/mail/service.py`.** The spec has each route call "a manager method". `manager.py` is 7,400 lines, so the methods live on a `MailService` the manager holds as `manager.mail`, and routes call `manager.mail.…`.
- **Sync compares a window, not a high-water mark.** Each pass asks the server which uids are in the window (newest 300 by arrival, plus the last 60 days) and applies the difference to the cache. That covers new mail, mail moved away and mail that aged out in one rule, so the spec's `last_uid` column and its `<last_uid+1>:*` fetch are not needed. The newest-300 search uses a sequence range (`<exists-299>:*`), which is cheap on a huge mailbox where `SEARCH ALL` is not.
- **Plan A creates four tables:** `folder`, `message`, `body`, `setting`. `comment` and `draft` arrive with Plan B and `thread_ai` with Plan C; `CREATE TABLE IF NOT EXISTS` makes that an addition.
- **A body's last-opened time sits on the `body` row** (`opened_at`), not on `message` as `body_at`.
- **Bodies load one message at a time through `GET /message`.** `GET /threads/{key}` answers from the cache alone and never waits on the mail server; the screen asks for each message it expands. A thread of thirty messages opens at once.
- **`GET /threads` takes no `tab` yet.** There is one tab until Plans B and C add Drafts and the sorted ones.
- **Opening a thread marks every Inbox message in it read**, not only the one on screen.
- **The folder is always opened read-write.** Reads use `PEEK`, so nothing changes by reading, and one kind of `SELECT` keeps "which folder is selected" a single fact.
- **The cache's revision number lives in memory.** The screen only checks whether it changed, and a restarted sidecar reloads the list anyway.
- **The screen asks for status every two seconds the whole time Mail is open**, not only while a pass runs. It is a loopback call, and it also catches changes the screen made itself.
- **Disarming is stricter than the spec's list.** It removes every `template` outright (the spec removes only the `shadowrootmode` attribute), and also `script`, `noscript`, nested frames (`iframe`, `frame`, `frameset`, `object`, `embed`) and SVG animation elements (`animate`, `set`, `animateMotion`, `animateTransform`). An SVG `animate` can give a link an address after loading with no script at all, which the spec's list missed. After disarming, the result is parsed once more; if anything armed reappears, or the policy is not first in the head, the email is shown as plain text.
- **Disarming never trusts a property read off the email's document.** The plan's first reviewer showed, in a real macOS webview, that `<img name="head">` makes `document.head` return the image, so the policy was put in the wrong place and remote content loaded. `disarm.ts` therefore calls the real accessors from the prototype, strips those names, and gives the reader two safe readers (`focusedAddress`, `contentHeight`) so no component reads an email's document directly.
- **Only `a` and `area` keep their address for the app to offer.** An address on anything else (a stylesheet link, an SVG `image` or `use`) is dropped, and a `data-mail-href` the email brought itself is removed.
- **A reply to a long thread no longer fails.** A `References` header folded over several lines used to make `email_send` answer "Header values may not contain linefeed or carriage return characters". Task 3 unfolds the reply headers, so that reply now threads. This is the one deliberate change to the agent tools' behaviour.
- **A link inside a `template` is not shown at all**, because its template is gone. The spec's test wanted its address card; the test here checks that it cannot be clicked.
- **The reader is two components.** `MailFrame` is only the sandboxed frame, the address card and Show images. `MailReader` is the thread around it. The part that must stay safe stays small.
- **A change the user makes can never be undone by a sync pass in flight.** The cache counts the user's own changes (`touched`). A pass notes the count before it asks the server anything and hands it back with each write; if it has moved, the write is refused. Every change also asks for a pass, so one always follows and reads the mailbox afresh.
- **Disconnecting stops the pass first.** `MailSync.stop()` ends the pass under way and waits for it before the cache is emptied, so a pass cannot write a disconnected mailbox's mail back to disk.
- **Changes act on every copy; the reader shows one.** A message that reached you twice (directly and through a list) is shown once, and marked or moved as both.
- **An attachment is saved by its place in the list**, not its name: `POST /attachments/save` takes `index`. Two attachments can share a name.
- **An attached email is an attachment.** A forwarded or bounced email's own body is never shown as the body of the message that carries it.
- **`cid:` is replaced only in an image's `src`**, and a plain-text email is shown in the app's own sans-serif face.
- **The policy also says `form-action 'none'`.** The sandbox already refuses forms; this is a second lock on the one request `default-src` does not cover.
- **An email is shown as soon as it has been read and checked, not when its last image arrives**, and the frame follows the email's height upward a limited number of times. Both came from the screen's reviewer, who found the email blank behind one slow image and two common layouts sized wrongly.
- **The address card shows the address as the browser reads it** (`new URL(…).href`), so a look-alike or reordered address appears in its plain form, and Close lets go of the link so the same link can be clicked again.
- **The WebKit project joins the browser tests in CI always, and locally only where WebKit is installed for the tests.** Installing it is a download, so it waits for the owner's word; without it the local gate still runs.
- **Mail gets a row in the main navigation**, with Automations, Apps and Agents. The spec said "beside Inbox", but Inbox lives in the account menu.
- **The screen says "Connectors"**, the name the app shows for the Integrations page.
- **`disarm.ts` is written in Task 2**, earlier than the rest of the screen, because the probe of the real app window needs it.

## File map

| File | Change |
|---|---|
| `scripts/live_mail_probe.py` | new: manual check of a real mail server |
| `surfaces/gui/probe/mail.html`, `surfaces/gui/probe/mail.ts` | new: manual check of the real app window; served in dev only |
| `coworker/connectors/email_tools.py` | compose, send and save-draft become module-level functions; the six tools wrap them |
| `coworker/mail/__init__.py` | new: empty package marker |
| `coworker/mail/imap.py` | new: `MailConnection`, `MailError` |
| `coworker/mail/threads.py` | new: `thread_key` |
| `coworker/mail/store.py` | new: `MailStore` |
| `coworker/mail/render.py` | new: `render_message` |
| `coworker/mail/sync.py` | new: `MailSync`, `message_row` |
| `coworker/mail/service.py` | new: `MailService` |
| `coworker/server/manager.py` | hold `self.mail`; close and forget it |
| `coworker/server/app.py` | eleven routes under `/v1/mail` |
| `surfaces/gui/src/api.ts` | Mail types and calls |
| `surfaces/gui/src/components/mail/disarm.ts` | new: make an email inert |
| `surfaces/gui/src/components/mail/MailFrame.tsx` | new: the sandboxed frame |
| `surfaces/gui/src/components/mail/MailReader.tsx` | new: a thread or one message |
| `surfaces/gui/src/components/mail/MailList.tsx` | new: the rows |
| `surfaces/gui/src/components/mail/MailView.tsx` | new: the section |
| `surfaces/gui/src/components/Icon.tsx`, `Sidebar.tsx`, `src/App.tsx` | the `mail` icon, the nav row, the `"mail"` surface |
| `surfaces/gui/src/styles.css`, `src/i18n.tsx` | Mail styles and strings |
| `surfaces/gui/playwright.config.ts`, `.github/workflows/ci.yml`, `.github/workflows/release.yml` | run the safety tests in WebKit too |
| tests | `tests/mail_fakes.py`, `tests/test_mail_imap.py`, `tests/test_mail_threads.py`, `tests/test_mail_store.py`, `tests/test_mail_render.py`, `tests/test_mail_sync.py`, `tests/test_mail_service.py`, `tests/test_mail_routes.py`, additions to `tests/test_email_tools.py`; `disarm.test.ts`, `MailFrame.test.tsx`, `MailList.test.tsx`, `MailView.test.tsx`; `e2e/mail-data.ts`, `e2e/mail.spec.ts`, `e2e/mail-safety.spec.ts`, additions to `e2e/fixtures.ts` |

---

## Chunk 1: Probes

### Task 1: Probe a real mail server

The design rests on four things a real server must do. This script checks them. It is run by hand and never in CI.

**Files:**
- Create: `scripts/live_mail_probe.py`

- [ ] **Step 1: Write the script**

```python
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
```

- [ ] **Step 2: Check it is clean and starts**

Run: `.venv/bin/ruff check scripts/live_mail_probe.py && .venv/bin/python scripts/live_mail_probe.py --help`
Expected: `All checks passed!`, then the usage text with `--move`.

- [ ] **Step 3: Run the read-only probe on the mailbox connected in the app**

Run: `.venv/bin/python scripts/live_mail_probe.py`

If it prints `no mailbox to probe`, the app has no Email connection on this machine. Stop and ask the owner to connect one (Connectors, Email) or to run the probe himself; do not ask him for a password in chat.

Expected, and what each line decides:

| Line | Expected | If it differs |
|---|---|---|
| `MOVE:` | `yes` | Mail shows no Archive or Bin for this server. That is already the design; note the server. |
| `\Sent:` | a folder name | Sync falls back to the conventional names in `_SENT_NAMES`. |
| `\Trash:` | a folder name | Bin falls back to the conventional names. |
| `\Archive:` or `\All:` | one of them is a name | Archive falls back to `Archive`, `Archives`, `INBOX.Archive`. |
| header names returned | includes `list-unsubscribe` | Plan C's newsletter rule cannot rely on the header fetch; note it for Plan C. |
| the reply's items | one tuple, then one `bytes` item | Note where `FLAGS` and `BODYSTRUCTURE` land: before the headers (in the tuple) or after (in the `bytes` item). `imap.py` in Task 4 reads both places. |

- [ ] **Step 4: Ask the owner before the two probes that are his to allow**

Two things need his word, so ask once, plainly:

1. Running `--move` on his mailbox. It writes one message titled "MimiWork mail probe (safe to delete)" into his inbox and leaves it in the bin.
2. A second mailbox on a different kind of server (one Gmail, one not). Only he can run that one: he sets `MAIL_PROBE_ADDRESS` and types the app password at the prompt, in his own terminal.

On a yes, run `.venv/bin/python scripts/live_mail_probe.py --move`.

Expected on Gmail (archive is `[Gmail]/All Mail`):

```
after filing the test message: {'INBOX': 1, '[Gmail]/All Mail': 1, '[Gmail]/Trash': 0}
MOVE 'INBOX' -> '[Gmail]/All Mail': OK ...
  now: {'INBOX': 0, '[Gmail]/All Mail': 1, '[Gmail]/Trash': 0}
MOVE '[Gmail]/All Mail' -> '[Gmail]/Trash': OK ...
  now: {'INBOX': 0, '[Gmail]/All Mail': 0, '[Gmail]/Trash': 1}
```

Expected elsewhere (archive is `Archive`): the count is 1 in exactly one place after every line.

If a move leaves two copies or none, stop: the archive design is wrong for that server and the spec needs correcting before Task 4.

If it prints `cannot run the move test`, the server flags no archive or bin folder. Record that; moving stays untested on that server, and Mail will offer Archive or Bin there only if a folder with a conventional name exists.

- [ ] **Step 5: Record what the probe found in the spec**

Add a section `## Probe results` at the end of `docs/superpowers/specs/2026-11-10-mail-client-design.md`, with the date, each server's host (never the address), and the table's lines as found. Where a probe was not run, say so and why.

- [ ] **Step 6: Commit**

```bash
git add scripts/live_mail_probe.py docs/superpowers/specs/2026-11-10-mail-client-design.md
git commit -m "Add a hand-run probe of what a real mail server does for Mail"
```

### Task 2: Make an email inert, and probe the real app window

`disarmEmail` is the function the whole reader's safety rests on. It is pure, so it is written and tested first, then tried in the real macOS window against a hostile email.

One thing the unit tests cannot show: in the macOS webview an element named like a document property (`<img name="head">`) answers in place of that property. jsdom and Chromium do not do this on a parsed copy, so these tests pass either way. Only the WebKit runs guard it: Step 7 here, and the WebKit safety tests in the last chunk. Do not "simplify" the prototype calls in `disarm.ts` into plain property reads.

`disarm.ts` also holds the few readers the reader component uses on a shown email (`focusedAddress`, `contentHeight`, `isParsed`, `releaseFocus`, `linkAddresses`), so that no component ever reads an email's document directly.

**Files:**
- Create: `surfaces/gui/src/components/mail/disarm.ts`
- Test: `surfaces/gui/src/components/mail/disarm.test.ts`
- Create: `surfaces/gui/probe/mail.html`, `surfaces/gui/probe/mail.ts`

- [ ] **Step 1: Write the failing tests**

`surfaces/gui/src/components/mail/disarm.test.ts`:

```ts
/** An email is made inert before any frame loads it. */
import { describe, expect, it } from "vitest";
import { disarmEmail, focusedAddress, linkAddresses, MAIL_CSP, releaseFocus, stillArmed } from "./disarm";

const parse = (html: string) => new DOMParser().parseFromString(html, "text/html");
const disarmed = (html: string, images = false) => {
  const out = disarmEmail(html, { images });
  if (out === null) throw new Error("expected a safe document");
  return parse(out);
};

describe("disarmEmail", () => {
  it("takes the address off a link and keeps it where the app can read it", () => {
    const doc = disarmed('<p><a href="https://example.com/a">Read</a></p>');
    const link = doc.querySelector("a")!;
    expect(link.hasAttribute("href")).toBe(false);
    expect(link.getAttribute("data-mail-href")).toBe("https://example.com/a");
    expect(link.getAttribute("tabindex")).toBe("0");
    expect(link.textContent).toBe("Read");
  });

  it("takes the address off an SVG link written with xlink:href", () => {
    const doc = disarmed('<svg><a xlink:href="https://example.com/s"><text>Go</text></a></svg>');
    const link = doc.querySelector("svg a")!;
    expect(link.getAttributeNames()).not.toContain("xlink:href");
    expect(link.getAttributeNames()).not.toContain("href");
    expect(link.getAttribute("data-mail-href")).toBe("https://example.com/s");
  });

  it("keeps an address only on what a person clicks", () => {
    const doc = disarmed(
      '<link rel="stylesheet" href="https://x.example/a.css">' +
        '<svg><image href="https://x.example/i.png"/><use xlink:href="https://x.example/u.svg#a"/></svg>',
    );
    expect(doc.documentElement.outerHTML).not.toContain("x.example");
    expect(doc.querySelector("[tabindex]")).toBeNull();
  });

  it("removes what could run, load a page or give a link an address later", () => {
    const doc = disarmed(
      '<head><base href="https://x.example/"><meta http-equiv="refresh" content="0;url=https://x.example"></head>' +
        '<body><script>1</script><noscript><p>off</p></noscript>' +
        '<div><template shadowrootmode="closed"><a href="https://x.example/t">t</a></template></div>' +
        '<iframe src="https://x.example/f"></iframe><object data="https://x.example/o"></object>' +
        '<svg><a><animate attributeName="href" to="https://x.example/smil"/><text>x</text></a></svg></body>',
    );
    for (const gone of ["base", "script", "noscript", "template", "iframe", "object", "animate"]) {
      expect(doc.querySelector(gone), gone).toBeNull();
    }
    expect(doc.querySelector('meta[http-equiv="refresh"]')).toBeNull();
    expect(doc.documentElement.outerHTML).not.toContain("x.example");
  });

  it("takes away the names that would let an element stand in for part of the document", () => {
    const doc = disarmed(
      '<img name="head" src="data:image/png;base64,AAAA"><img name="documentElement">' +
        '<form name="querySelectorAll"><input name="q"></form>',
    );
    expect(doc.querySelector("img[name], form[name]")).toBeNull();
    expect(doc.querySelectorAll("img").length).toBe(2);
    expect(doc.head.firstElementChild!.getAttribute("http-equiv")).toBe("Content-Security-Policy");
  });

  it("does not let an email plant the address the app will offer", () => {
    const doc = disarmed('<p tabindex="0" data-mail-href="https://evil.example">Click</p>');
    expect(doc.querySelector("[data-mail-href]")).toBeNull();
  });

  it("puts the policy first in the head, without remote images unless asked", () => {
    const first = (doc: Document) => doc.head.firstElementChild!;
    const closed = first(disarmed('<head><meta http-equiv="Content-Security-Policy" content="img-src *"></head><p>hi</p>'));
    expect(closed.getAttribute("http-equiv")).toBe("Content-Security-Policy");
    expect(closed.getAttribute("content")).toBe("default-src 'none'; img-src data:; style-src 'unsafe-inline'; form-action 'none'");
    expect(first(disarmed("<p>hi</p>", true)).getAttribute("content")).toBe(MAIL_CSP(true));
    expect(MAIL_CSP(true)).toContain("img-src data: https:");
  });

  it("leaves an email's own images, text and styles alone", () => {
    const doc = disarmed('<p style="color:red">Hello <img src="data:image/png;base64,AAAA" alt="logo"></p>');
    expect(doc.querySelector("p")!.getAttribute("style")).toBe("color:red");
    expect(doc.querySelector("img")!.getAttribute("src")).toBe("data:image/png;base64,AAAA");
  });

  it("gives back a document that is still inert when parsed again", () => {
    const out = disarmEmail('<a href="https://example.com">x</a><svg><a xlink:href="https://e.example">y</a></svg>')!;
    expect(stillArmed(parse(out))).toBe(false);
  });
});

describe("stillArmed", () => {
  const policy = `<meta http-equiv="Content-Security-Policy" content="${MAIL_CSP(false)}">`;

  it("accepts only a document with the policy first and nothing armed", () => {
    expect(stillArmed(parse(`<head>${policy}</head><p>plain</p>`))).toBe(false);
    expect(stillArmed(parse("<p>no policy at all</p>"))).toBe(true);
    expect(stillArmed(parse(`<head><title>x</title>${policy}</head>`))).toBe(true);
    expect(stillArmed(parse(`<head>${policy}${policy}</head>`))).toBe(true);
  });

  it("is true for a link address, a template, a second meta or a name that hides the document", () => {
    for (const body of [
      '<a href="https://example.com">x</a>',
      "<div><template><b>x</b></template></div>",
      '<meta http-equiv="refresh" content="1">',
      '<img name="head">',
    ]) {
      expect(stillArmed(parse(`<head>${policy}</head>${body}`)), body).toBe(true);
    }
  });
});

describe("focusedAddress", () => {
  it("is the address of the link that has focus, and empty otherwise", () => {
    document.body.innerHTML = '<a tabindex="0" data-mail-href="https://example.com/a">Read</a><p>text</p>';
    expect(focusedAddress(document)).toBe("");
    document.querySelector("a")!.focus();
    expect(focusedAddress(document)).toBe("https://example.com/a");
    releaseFocus(document);
    expect(focusedAddress(document)).toBe("");
  });
});

describe("linkAddresses", () => {
  it("lists each link address once, in the order they appear", () => {
    const doc = parse(
      disarmEmail('<a href="https://a.example/">a</a><a href="https://b.example/">b</a><a href="https://a.example/">again</a>')!,
    );
    expect(linkAddresses(doc)).toEqual(["https://a.example/", "https://b.example/"]);
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run (in `surfaces/gui`): `npx vitest run src/components/mail/disarm.test.ts`
Expected: FAIL, `Failed to resolve import "./disarm"`.

- [ ] **Step 3: Write `disarm.ts`**

```ts
// An email is untrusted HTML. The reader's rule is that nothing in it ever runs, loads or
// navigates, and the app acts on it only from outside. The sandboxed frame stops scripts
// and forms; this file stops the two things the sandbox does not: a clicked link, which
// would load a remote page inside the reader, and remote content, which tells the sender
// the email was opened. It works on a parsed copy that runs and loads nothing, so the
// frame only ever receives the inert result.

// The sandbox already refuses forms; `form-action` says so a second time, because it is
// the one fetch a `default-src` does not cover.
export const MAIL_CSP = (images: boolean): string =>
  `default-src 'none'; img-src data:${images ? " https:" : ""}; style-src 'unsafe-inline'; form-action 'none'`;

// Each of these can run, load a page, hand a link its address after the document has
// loaded, or be read differently by two parsers: a `template` can become a shadow root
// the app cannot look into, an SVG animation can set `href` on a link with no script at
// all, and `noscript` is markup to one parser and text to another.
const DROP =
  "script, noscript, base, template, iframe, frame, frameset, object, embed, " +
  "animate, set, animateMotion, animateTransform";
const POLICY = 'meta[http-equiv="Content-Security-Policy"]';
// An element carrying one of these names answers in place of the document's own property
// of that name: <img name="head"> becomes `document.head`.
const NAMED = "form[name], img[name]";
// What a person clicks. Anything else with an address (a stylesheet link, an SVG image)
// only loads, so its address is dropped, not kept.
const LINKS = new Set(["a", "area"]);

// Because of those names, nothing here reads a property off an email's document or its
// elements. It calls the real one, taken from the prototype, which an email cannot reach.
const own = <T>(proto: object, name: string) => {
  const read = Object.getOwnPropertyDescriptor(proto, name)!.get!;
  return (target: unknown): T => read.call(target);
};
const rootOf = own<HTMLElement | null>(Document.prototype, "documentElement");
const headOf = own<HTMLHeadElement | null>(Document.prototype, "head");
const focusOf = own<Element | null>(Document.prototype, "activeElement");
const tagOf = own<string>(Element.prototype, "localName");
const markupOf = own<string>(Element.prototype, "outerHTML");
const heightOf = own<number>(Element.prototype, "scrollHeight");
const urlOf = own<string>(Document.prototype, "URL");
const stateOf = own<string>(Document.prototype, "readyState");
const all = (doc: Document, selector: string): Element[] =>
  Array.from(Document.prototype.querySelectorAll.call(doc, selector));
const names = (el: Element): string[] => Element.prototype.getAttributeNames.call(el);
const read = (el: Element, name: string): string | null => Element.prototype.getAttribute.call(el, name);
const write = (el: Element, name: string, value: string): void =>
  Element.prototype.setAttribute.call(el, name, value);
const strip = (el: Element, name: string): void => Element.prototype.removeAttribute.call(el, name);
// "href", and the SVG spelling "xlink:href".
const isAddress = (name: string): boolean => name === "href" || name.endsWith(":href");

/** True unless a document is exactly the inert shape `disarmEmail` gives back. */
export function stillArmed(doc: Document): boolean {
  if (all(doc, `${DROP}, ${NAMED}, meta[http-equiv]:not(${POLICY})`).length) return true;
  // The policy is what keeps remote content out, so it must be there, once, and first.
  if (all(doc, POLICY).length !== 1 || all(doc, `head > ${POLICY}:first-child`).length !== 1) return true;
  return all(doc, "*").some((el) => names(el).some(isAddress));
}

/** The email as an inert document for a frame's `srcdoc`, or null when it cannot be
 *  made inert, in which case the reader shows its plain text. */
export function disarmEmail(html: string, opts: { images?: boolean } = {}): string | null {
  const doc = new DOMParser().parseFromString(html, "text/html");
  all(doc, `${DROP}, meta[http-equiv]`).forEach((el) => Element.prototype.remove.call(el));
  all(doc, NAMED).forEach((el) => strip(el, "name"));
  for (const el of all(doc, "*")) {
    // An email may not plant an address where the app looks for one.
    strip(el, "data-mail-href");
    for (const name of names(el)) {
      if (!isAddress(name)) continue;
      const address = read(el, name) ?? "";
      strip(el, name);
      if (!LINKS.has(tagOf(el))) continue;
      write(el, "data-mail-href", address);
      write(el, "tabindex", "0");
    }
  }
  const head = headOf(doc);
  const root = rootOf(doc);
  if (!head || !root) return null;
  const policy = Document.prototype.createElement.call(doc, "meta");
  write(policy, "http-equiv", "Content-Security-Policy");
  write(policy, "content", MAIL_CSP(!!opts.images));
  Element.prototype.prepend.call(head, policy);
  const out = "<!doctype html>" + markupOf(root);
  // Writing a document out and reading it back can rebuild it differently. Read it back
  // the way the frame will, and refuse the email if anything armed has reappeared.
  return stillArmed(new DOMParser().parseFromString(out, "text/html")) ? null : out;
}

// -- reading a shown email from outside ---------------------------------------------------
// Scripts are off inside the frame, so listeners the app adds there never fire. The app
// asks instead, on a timer, with these.

/** The address of the link that has focus in a shown email, or "". */
export function focusedAddress(doc: Document): string {
  const el = focusOf(doc);
  return (el && read(el, "data-mail-href")) || "";
}

/** How tall the email is, so the frame can be sized to it and the page scrolls, not the frame.
 *  The scroll height, because an email that sizes itself to its window ("height: 100%")
 *  reports only the frame's own height any other way. */
export function contentHeight(doc: Document): number {
  const root = rootOf(doc);
  return root ? heightOf(root) : 0;
}

/** True once the frame holds the email itself, read to the end. Its remote images may
 *  still be on their way: with Show images on, waiting for the last of them would keep
 *  the whole email hidden behind one slow picture. */
export function isParsed(doc: Document): boolean {
  return urlOf(doc) === "about:srcdoc" && stateOf(doc) !== "loading";
}

/** Take focus off the focused link, which is how the address card is closed. */
export function releaseFocus(doc: Document): void {
  const el = focusOf(doc);
  if (!el) return;
  // An HTML link and an SVG link each have their own `blur`, and each refuses the other's.
  for (const proto of [HTMLElement.prototype, SVGElement.prototype]) {
    try {
      return proto.blur.call(el);
    } catch {
      continue;
    }
  }
}

/** Every link address in a shown email, in order, each once. */
export function linkAddresses(doc: Document): string[] {
  const found = all(doc, "[data-mail-href]").map((el) => read(el, "data-mail-href") || "");
  return [...new Set(found)].filter(Boolean);
}
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `npx vitest run src/components/mail/disarm.test.ts`
Expected: PASS, 13 tests.

- [ ] **Step 5: Write the probe page for the real window**

`surfaces/gui/probe/mail.html`:

```html
<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Mail reader probe</title>
    <style>
      body { font: 13px/1.5 system-ui; margin: 16px; background: #fff; color: #111; }
      iframe { width: 100%; height: 300px; border: 1px solid #999; }
      pre { background: #f3f3f3; padding: 8px; white-space: pre-wrap; }
      h2 { font-size: 14px; margin: 18px 0 6px; }
    </style>
  </head>
  <body>
    <h1>Mail reader probe</h1>
    <p>
      Start <code>python3 -m http.server 8799</code> in an empty folder first. Click every link
      in both frames, then read that terminal. Lines for <code>/raw-…</code> are expected: they
      prove the listener sees a request. Any line for <code>/hit-…</code> is a failure.
    </p>
    <h2>Disarmed (what Mail will show)</h2>
    <iframe id="safe" sandbox="allow-same-origin"></iframe>
    <h2>Raw (control: shows what the sandbox alone allows)</h2>
    <iframe id="raw" sandbox="allow-same-origin"></iframe>
    <h2>What the app can see from outside</h2>
    <pre id="report">starting…</pre>
    <script type="module" src="./mail.ts"></script>
  </body>
</html>
```

`surfaces/gui/probe/mail.ts`:

```ts
// A hand-run check of the real app window, kept so it can be repeated on Windows. Served
// by the dev server only; the production build has one entry, index.html.
import { disarmEmail, focusedAddress, stillArmed } from "../src/components/mail/disarm";

const hostile = (tag: string): string => {
  const at = (path: string) => `http://127.0.0.1:8799/${tag}-${path}`;
  return `<html><head>
<meta http-equiv="refresh" content="3;url=${at("refresh")}">
<link rel="stylesheet" href="${at("stylesheet")}">
<style>@import url(${at("import")}); body { background: url(${at("background")}); font: 14px system-ui; }</style>
<script>window.__ran = "script"; parent.__probeRan = "${tag} script"; fetch("${at("script")}");</script>
</head><body>
<p>Hostile test email (${tag}).</p>
<img src="${at("pixel")}" onerror="window.__ran = 'onerror'">
<img name="head" src="${at("named-head")}">
<img name="documentElement" src="${at("named-root")}">
<form name="querySelectorAll"><input name="getAttribute"></form>
<noscript><style></noscript><a href="${at("noscript")}">Noscript link</a></style></noscript>
<p><a href="${at("plain")}">Plain link</a></p>
<p><a target="_self" href="${at("self")}">Same-frame link</a></p>
<div><template shadowrootmode="closed"><p><a href="${at("shadow")}">Shadow link</a></p></template></div>
<svg width="220" height="28"><a xlink:href="${at("svg")}"><text x="0" y="20">SVG link</text></a></svg>
<svg width="220" height="28"><a><animate attributeName="href" to="${at("smil")}" fill="freeze"/><text x="0" y="20">Animated link</text></a></svg>
</body></html>`;
};

const safe = document.getElementById("safe") as HTMLIFrameElement;
const raw = document.getElementById("raw") as HTMLIFrameElement;
const report = document.getElementById("report") as HTMLPreElement;
safe.srcdoc = disarmEmail(hostile("hit")) ?? "<p>refused: could not be made inert</p>";
raw.srcdoc = hostile("raw");

let heard = 0;
safe.addEventListener("load", () => {
  // Expected never to fire: a frame without allow-scripts silences listeners added inside it.
  safe.contentDocument?.addEventListener("click", () => (heard += 1));
});

setInterval(() => {
  const doc = safe.contentDocument;
  const win = safe.contentWindow as (Window & { __ran?: string; __TAURI__?: unknown }) | null;
  if (!doc) return;
  report.textContent = [
    `disarmed frame still armed:        ${stillArmed(doc)}   (want false)`,
    `a script ran in the disarmed frame: ${win?.__ran ?? "no"}   (want no)`,
    `a frame reached the app window:     ${(window as { __probeRan?: string }).__probeRan ?? "no"}   (want no)`,
    `the frame has the Tauri API:        ${win?.__TAURI__ ? "yes" : "no"}   (unusable either way: no script runs)`,
    `clicks heard by a listener inside:  ${heard}   (want 0, which is why Mail asks on a timer)`,
    `focused element's address:          ${focusedAddress(doc) || "(none)"}`,
    `text selected in the frame:         ${JSON.stringify(Document.prototype.getSelection.call(doc)?.toString() ?? "")}`,
  ].join("\n");
}, 250);
```

- [ ] **Step 6: Check the probe files are lint-clean**

Run (in `surfaces/gui`): `npx eslint probe src/components/mail`
Expected: no output.

- [ ] **Step 7: Run the probe in the real app window**

This needs a person, or computer control of the desktop, because the point is a real pointer click.

1. In an empty scratch folder: `python3 -m http.server 8799`. Leave it running and visible.
2. In `surfaces/gui`: `npm run tauri dev`. Wait for the MimiWork window.
3. Right-click in the window, choose Inspect Element, and in the Console run `location.assign("/probe/mail.html")`.
4. In the **Disarmed** frame: click Plain link, Same-frame link, SVG link and Animated link. Select a few words of text.
5. In the **Raw** frame: click Plain link once.

Expected:

| Check | Want |
|---|---|
| Listener terminal after step 4 | no line containing `/hit-` |
| Listener terminal after step 5 | a line `GET /raw-plain`, which shows the listener works and that the sandbox alone does not stop a link |
| "Shadow link" and "Noscript link" in the Disarmed frame | not shown at all |
| Listener terminal, for `/hit-named-head`, `/hit-named-root`, `/hit-pixel` | no such line: the policy held although the email named its images `head` and `documentElement` |
| Report, first three lines | `false`, `no`, `no` |
| Report, clicks heard | `0` |
| Report, focused element's address, after clicking Plain link | `http://127.0.0.1:8799/hit-plain` |
| Report, text selected | the words selected |

Close the dev app and stop the listener afterwards.

- [ ] **Step 8: Decide how links open, from the focus line**

- **The focused element's address appears after a click:** links open the way Task 12 is written. Nothing to change.
- **It stays `(none)`:** the macOS webview does not focus a clicked element. Then apply Task 12, Step 5 when you reach it: it replaces `MailFrame`'s focus reading with a list of the message's links beneath the frame.

- [ ] **Step 9: Record the results and commit**

Add what Step 7 showed to the `## Probe results` section of the spec: the date, macOS version, each row of the table as found, and which way Step 8 went. Say that Windows was not probed.

```bash
git add surfaces/gui/src/components/mail/disarm.ts surfaces/gui/src/components/mail/disarm.test.ts surfaces/gui/probe docs/superpowers/specs/2026-11-10-mail-client-design.md
git commit -m "Make an email inert before a frame loads it, and probe the real window"
```

## Chunk 2: One send path

### Task 3: One send path for the agent's tools and for Mail

`_compose`, the send path and the save-draft path are closures inside `make_email_tools`. They move to module level so Mail can call the same code in Plan B, and compose learns to thread a reply from headers it is handed. The six tools must behave as before: their existing tests are the proof and are not edited. One thing changes on purpose. A reply to a message whose `References` header is folded over several lines, as it is in any long thread, used to fail with "Header values may not contain linefeed or carriage return characters"; the reply headers are now unfolded, so it threads.

**Files:**
- Modify: `coworker/connectors/email_tools.py` (imports; a new block above `# -- the tools`; the bodies of `make_email_tools`'s closures, lines 392–799)
- Test: `tests/test_email_tools.py` (four tests appended)

- [ ] **Step 1: Write the failing tests**

Change the import at the top of `tests/test_email_tools.py` to:

```python
from coworker.connectors.email_tools import (
    build_search_criteria,
    compose_message,
    decode_mime_header,
    extract_text_body,
    load_profile,
    make_email_tools,
    resolve_servers,
    send_message,
)
```

Append at the end of the file:

```python
# -- the path Mail shares with the tools ---------------------------------------------
def _no_imap(host, port):
    raise AssertionError("the original must not be looked up")


def test_a_reply_composed_from_its_headers_threads_without_looking_the_original_up(tmp_path):
    profile, servers, err = load_profile(_connected_secrets(tmp_path))
    assert err is None
    msg = compose_message(
        profile,
        servers,
        to="ana@example.com",
        subject="",
        body="re!",
        reply_headers={
            "message_id": "<orig-123@example.com>",
            "references": "<root@example.com>",
            "subject": "Quarterly report",
        },
        imap_factory=_no_imap,
    )
    assert msg["In-Reply-To"] == "<orig-123@example.com>"
    assert msg["References"] == "<root@example.com> <orig-123@example.com>"
    assert msg["Subject"] == "Re: Quarterly report"


def test_a_reply_in_a_long_thread_whose_headers_are_folded_still_threads(tmp_path):
    profile, servers, _ = load_profile(_connected_secrets(tmp_path))
    msg = compose_message(
        profile,
        servers,
        to="ana@example.com",
        subject="",
        body="re!",
        reply_headers={
            "message_id": "<c@example.com>",
            "references": "<a@example.com>\r\n <b@example.com>",
            "subject": "A long\r\n subject",
        },
        imap_factory=_no_imap,
    )
    assert msg["References"] == "<a@example.com> <b@example.com> <c@example.com>"
    assert msg["Subject"] == "Re: A long subject"


def test_a_composed_message_is_sent_and_filed_by_the_shared_path(tmp_path):
    imap, smtp = PrivateEmailIMAP(), FakeSMTP()
    profile, servers, _ = load_profile(_private_email_secrets(tmp_path))
    msg = compose_message(profile, servers, to="ana@example.com", subject="Hi", body="Hello")
    result = send_message(
        profile,
        servers,
        msg,
        imap_factory=lambda h, p: imap,
        smtp_factory=lambda h, p: smtp,
    )
    assert result["ok"] and result["sent_copy"] == "filed in Sent"
    assert smtp.sent == [msg]


def test_a_missing_connection_is_reported_in_the_tools_own_words(tmp_path):
    profile, servers, err = load_profile(SecretStore(tmp_path / "secrets.json"))
    assert profile is None and servers is None
    assert "not connected" in err["error"]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_email_tools.py -q`
Expected: an error collecting the file, `ImportError: cannot import name 'compose_message'`.

- [ ] **Step 3: Add the module-level functions**

In `coworker/connectors/email_tools.py`, add `import mimetypes` to the imports (after `import imaplib`). Then insert this block directly above the line `# -- the tools ----…`:

```python
# -- shared by the agent's tools and the Mail section --------------------------------
_NOT_CONNECTED = "email is not connected; add it in Manage → Integrations"


def load_profile(
    secrets: SecretStore,
) -> tuple[Optional[dict[str, Any]], Optional[EmailServers], Optional[dict[str, Any]]]:
    """(profile, servers, error) — error is a tool-result dict."""
    profile = secrets.get("email:default") or {}
    if not profile.get("address") or not profile.get("app_password"):
        return None, None, {"error": _NOT_CONNECTED}
    servers, err = resolve_servers(profile)
    if servers is None:
        return None, None, {"error": err}
    return profile, servers, None


def open_imap(profile, servers, imap_factory):
    """(imap, error) — error is a tool-result dict."""
    try:
        return _imap_login(profile, servers, imap_factory), None
    except Exception as exc:
        return None, {"error": f"IMAP login failed: {exc}.{_auth_hint(servers)}"}


def _logout(imap) -> None:
    try:
        imap.logout()
    except Exception:
        pass


def _one_line(value: Any) -> str:
    """A header value without its folding. A long header arrives split over several
    lines, and a header set with a line break in it is refused."""
    return " ".join(str(value or "").split())


def _reply_headers_from_server(profile, servers, uid: str, folder: str, imap_factory):
    """(headers, error): what a reply needs from the message it answers."""
    imap, err = open_imap(profile, servers, imap_factory)
    if err:
        return None, err
    try:
        sel_err = _select_readonly(imap, folder)
        if sel_err:
            return None, {"error": sel_err}
        status, data = imap.uid(
            "FETCH",
            str(uid),
            "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID REFERENCES SUBJECT)])",
        )
        if status != "OK" or not data or not isinstance(data[0], tuple):
            return None, {"error": f"reply target {uid} not found in {folder}"}
        orig = email_lib.message_from_bytes(data[0][1])
        return {
            "message_id": _one_line(orig.get("Message-ID")),
            "references": _one_line(orig.get("References")),
            "subject": decode_mime_header(orig.get("Subject", "")),
        }, None
    except Exception as exc:
        return None, {"error": str(exc)}
    finally:
        _logout(imap)


def compose_message(
    profile: dict[str, Any],
    servers: EmailServers,
    *,
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    reply_to_uid: str = "",
    reply_to_folder: str = "INBOX",
    reply_headers: Optional[dict[str, str]] = None,
    attachments: Optional[list[str]] = None,
    roots: Optional[list[RootDir]] = None,
    imap_factory: Callable[[str, int], imaplib.IMAP4] = _default_imap_factory,
) -> EmailMessage | dict[str, Any]:
    """The finished message, or a tool-result error dict.

    A reply takes its threading from `reply_headers` when given (`message_id`,
    `references`, `subject`), else looks them up by uid and folder. Mail hands the headers
    over, because the message it answers may have been moved since it was read.
    """
    msg = EmailMessage()
    display = str(profile.get("display_name") or "").strip()
    msg["From"] = (
        formataddr((display, profile["address"])) if display else profile["address"]
    )
    msg["To"] = to
    if cc:
        msg["Cc"] = cc
    if bcc:
        msg["Bcc"] = bcc
    msg["Message-ID"] = make_msgid(domain=profile["address"].rsplit("@", 1)[-1])

    final_subject = subject
    if reply_headers is None and reply_to_uid:
        reply_headers, err = _reply_headers_from_server(
            profile, servers, reply_to_uid, reply_to_folder, imap_factory
        )
        if err:
            return err
    if reply_headers:
        orig_id = _one_line(reply_headers.get("message_id"))
        if orig_id:
            msg["In-Reply-To"] = orig_id
            refs = _one_line(reply_headers.get("references"))
            msg["References"] = f"{refs} {orig_id}".strip()
        if not subject:
            orig_subject = _one_line(reply_headers.get("subject"))
            final_subject = (
                orig_subject
                if orig_subject.lower().startswith("re:")
                else f"Re: {orig_subject}"
            )
    msg["Subject"] = final_subject
    msg.set_content(body)

    allowed_roots = [r.path for r in (roots or [])]
    for raw_path in attachments or []:
        path = Path(str(raw_path)).expanduser().resolve()
        if not any(path.is_relative_to(root) for root in allowed_roots):
            return {
                "error": f"attachment {raw_path} is outside the session's directories"
            }
        if not path.is_file():
            return {"error": f"attachment not found: {raw_path}"}
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )
    return msg


def send_message(
    profile: dict[str, Any],
    servers: EmailServers,
    msg: EmailMessage,
    *,
    imap_factory: Callable[[str, int], imaplib.IMAP4] = _default_imap_factory,
    smtp_factory: Callable[[str, int], smtplib.SMTP] = _default_smtp_factory,
) -> dict[str, Any]:
    """Send a composed message and file its Sent copy where the host does not."""
    try:
        smtp = _smtp_login(profile, servers, smtp_factory)
    except Exception as exc:
        return {"error": f"SMTP login failed: {exc}.{_auth_hint(servers)}"}
    try:
        smtp.send_message(msg)
    except Exception as exc:
        return {"error": f"send failed: {exc}"}
    finally:
        try:
            smtp.quit()
        except Exception:
            pass
    result = {"ok": True, "message_id": msg["Message-ID"], "subject": msg["Subject"]}
    if servers.imap_host.endswith(_SERVER_FILES_SENT):
        return result
    imap, err = open_imap(profile, servers, imap_factory)
    if err:
        result["sent_copy"] = "delivered, but no copy was filed in Sent"
        return result
    try:
        folder = _find_folder(imap, rb"\Sent", _SENT_NAMES)
        if folder is None:
            result["sent_copy"] = "delivered, but the mailbox has no Sent folder"
        else:
            status, _ = imap.append(
                _quote(folder),
                r"(\Seen)",
                imaplib.Time2Internaldate(time.time()),
                msg.as_bytes(),
            )
            result["sent_copy"] = (
                f"filed in {folder}"
                if status == "OK"
                else f"delivered, but filing a copy in {folder} failed"
            )
    except Exception as exc:
        result["sent_copy"] = f"delivered, but filing a copy in Sent failed: {exc}"
    finally:
        _logout(imap)
    return result


def save_draft(
    profile: dict[str, Any],
    servers: EmailServers,
    msg: EmailMessage,
    *,
    imap_factory: Callable[[str, int], imaplib.IMAP4] = _default_imap_factory,
) -> dict[str, Any]:
    """File a composed message in the mailbox's Drafts folder. Nothing is sent."""
    imap, err = open_imap(profile, servers, imap_factory)
    if err:
        return err
    try:
        folder = _find_folder(imap, rb"\Drafts", _DRAFTS_NAMES)
        if folder is None:
            return {"error": "the mailbox has no Drafts folder"}
        status, _ = imap.append(
            _quote(folder),
            r"(\Draft \Seen)",
            imaplib.Time2Internaldate(time.time()),
            msg.as_bytes(),
        )
    except Exception as exc:
        return {"error": f"saving the draft failed: {exc}"}
    finally:
        _logout(imap)
    if status != "OK":
        return {"error": f"saving the draft in {folder} failed"}
    return {"ok": True, "folder": folder, "subject": msg["Subject"]}
```

- [ ] **Step 4: Make the tools wrap them**

Inside `make_email_tools`, make four edits.

(a) Replace the whole `_connect_imap` closure and the `_logout` closure beneath it with:

```python
    def _connect_imap():
        """(imap, profile, servers, error) — error is a tool-result dict."""
        profile, servers, err = load_profile(secrets)
        if err:
            return None, None, None, err
        imap, err = open_imap(profile, servers, imap_factory)
        if err:
            return None, None, None, err
        return imap, profile, servers, None
```

The read tools keep calling `_logout(imap)`; it now resolves to the module-level function.

(b) Delete the `_compose` closure and the `_profile` closure entirely.

(c) Replace the body of `email_send` (keep its signature) with:

```python
        profile, servers, err = load_profile(secrets)
        if err:
            return err
        msg = compose_message(
            profile,
            servers,
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            reply_to_uid=reply_to_uid,
            reply_to_folder=reply_to_folder,
            attachments=attachments,
            roots=roots,
            imap_factory=imap_factory,
        )
        if isinstance(msg, dict):
            return msg
        return send_message(
            profile, servers, msg, imap_factory=imap_factory, smtp_factory=smtp_factory
        )
```

(d) Replace the body of `email_save_draft` (keep its signature) with:

```python
        profile, servers, err = load_profile(secrets)
        if err:
            return err
        msg = compose_message(
            profile,
            servers,
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            reply_to_uid=reply_to_uid,
            reply_to_folder=reply_to_folder,
            attachments=attachments,
            roots=roots,
            imap_factory=imap_factory,
        )
        if isinstance(msg, dict):
            return msg
        return save_draft(profile, servers, msg, imap_factory=imap_factory)
```

Leave the `return [ _attach(…), … ]` list and every schema untouched.

- [ ] **Step 5: Run the whole email test file**

Run: `.venv/bin/pytest tests/test_email_tools.py -q`
Expected: PASS, 31 tests (27 that existed, 4 new). No existing test was edited.

- [ ] **Step 6: Run the Python gates**

Run: `.venv/bin/ruff check coworker tests scripts && .venv/bin/pytest -q`
Expected: `All checks passed!`, and pytest green.

- [ ] **Step 7: Commit**

```bash
git add coworker/connectors/email_tools.py tests/test_email_tools.py
git commit -m "Lift compose, send and save-draft out of the mail tools so Mail can share them"
```

## Chunk 3: Mail's connection to the mailbox

### Task 4: One reused connection, and a mail server for the tests

`MailConnection` is the only code in Mail that speaks IMAP. Everything above it (sync, the facade, the routes) is tested against the in-memory server written here, through the same `imap_factory` injection `email_tools.py` already has.

**Files:**
- Create: `coworker/mail/__init__.py` (empty)
- Create: `coworker/mail/imap.py`
- Create: `tests/mail_fakes.py`
- Test: `tests/test_mail_imap.py`

- [ ] **Step 1: Write the in-memory mail server**

`tests/mail_fakes.py`. It keeps folders, uids and flags, and answers the handful of commands `imap.py` sends. It answers a header fetch the awkward ways real servers do: partly before the headers and partly after, with an attachment's file name sent as a separate literal ahead of the headers, and with a flag change made elsewhere arriving unasked at the front of a reply (`server.unasked`). Tests import it as `from mail_fakes import …`, the way `tests/helpers.py` is imported.

```python
"""A mail server in memory for the Mail tests: folders, uids, flags, and the handful of
IMAP commands `coworker/mail/imap.py` sends. No network, no real mailbox."""

from __future__ import annotations

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
```

- [ ] **Step 2: Write the failing tests**

`tests/test_mail_imap.py`:

```python
"""Mail's own connection to the mailbox: one login, reused, each operation in its folder."""

from __future__ import annotations

import pytest
from mail_fakes import ADDRESS, GMAIL_FOLDERS, FakeMailServer, connected_secrets, mail

from coworker.mail.imap import MailConnection, MailError
from coworker.secrets import SecretStore


def _conn(tmp_path, **server_options):
    server = FakeMailServer(**server_options)
    return server, MailConnection(connected_secrets(tmp_path), imap_factory=server.connect)


def test_the_connection_logs_in_once_and_is_reused(tmp_path):
    server, conn = _conn(tmp_path)
    server.add("INBOX", mail("One"))
    assert conn.describe()["account"] == ADDRESS
    conn.window("INBOX")
    conn.message("INBOX", 1)
    assert server.logins == 1


def test_a_mailbox_that_is_not_connected_says_so(tmp_path):
    conn = MailConnection(
        SecretStore(tmp_path / "secrets.json"), imap_factory=FakeMailServer().connect
    )
    with pytest.raises(MailError, match="not connected"):
        conn.describe()


def test_a_wrong_password_carries_the_connectors_hint(tmp_path):
    server = FakeMailServer()
    conn = MailConnection(
        connected_secrets(tmp_path, password="wrong"), imap_factory=server.connect
    )
    with pytest.raises(MailError, match="app password"):
        conn.describe()


def test_a_dropped_connection_is_replaced_once_and_the_call_succeeds(tmp_path):
    server, conn = _conn(tmp_path)
    server.add("INBOX", mail("One"))
    conn.window("INBOX")
    server.drops = 1
    assert conn.message("INBOX", 1)["Subject"] == "One"
    assert server.logins == 2
    # Closed, not logged out: a logout on a dead line waits a full timeout for a goodbye.
    assert server.commands("shutdown") and not server.commands("logout")


def test_a_server_that_keeps_dropping_is_reported_not_retried_without_end(tmp_path):
    server, conn = _conn(tmp_path)
    server.add("INBOX", mail("One"))
    server.drops = 5
    with pytest.raises(MailError, match="stopped answering"):
        conn.message("INBOX", 1)
    assert server.logins == 2


def test_a_changed_password_is_used_on_the_next_operation(tmp_path):
    server = FakeMailServer()
    secrets = connected_secrets(tmp_path)
    conn = MailConnection(secrets, imap_factory=server.connect)
    conn.describe()
    server.password = "new pass"
    secrets.put("email:default", {**secrets.get("email:default"), "app_password": "new pass"})
    conn.describe()
    assert server.logins == 2


def test_an_operation_on_inbox_between_two_on_sent_leaves_each_in_its_own_folder(tmp_path):
    server, conn = _conn(tmp_path)
    server.add("INBOX", mail("In the inbox"))
    server.add("Sent", mail("In sent"))
    assert conn.message("Sent", 1)["Subject"] == "In sent"
    conn.set_seen("INBOX", [1], True)
    assert conn.message("Sent", 1)["Subject"] == "In sent"
    assert server.flags("INBOX", 1) == {"\\Seen"}
    assert server.flags("Sent", 1) == set()
    assert [entry[1] for entry in server.commands("select")] == ["Sent", "INBOX", "Sent"]


def test_a_folder_already_selected_is_not_selected_again(tmp_path):
    server, conn = _conn(tmp_path)
    server.add("INBOX", mail("One"))
    conn.message("INBOX", 1)
    conn.message("INBOX", 1)
    assert len(server.commands("select")) == 1


def test_the_window_is_the_newest_few_or_the_recent_days_whichever_reaches_further(tmp_path):
    server, conn = _conn(tmp_path)
    for days in (400, 300, 200, 30, 20, 10):
        server.add("INBOX", mail(f"{days} days old", days_ago=days))
    assert conn.window("INBOX", days=60, newest=2) == (1, [4, 5, 6])
    assert conn.window("INBOX", days=5, newest=4) == (1, [3, 4, 5, 6])
    assert conn.window("INBOX", days=500, newest=2, cap=3) == (1, [4, 5, 6])
    assert conn.window("Sent") == (1, [])


def test_headers_carry_flags_size_attachments_and_the_newsletter_header(tmp_path):
    server, conn = _conn(tmp_path)
    server.add("INBOX", mail("Plain", message_id="<a@x>"), seen=True)
    server.add(
        "INBOX",
        mail(
            "News",
            attachment="report.pdf",
            headers={"List-Unsubscribe": "<mailto:off@news.example>"},
        ),
    )
    first, second = conn.headers("INBOX", [1, 2])
    assert (first["uid"], first["flags"], first["has_attachments"]) == (1, "\\Seen", False)
    assert first["size"] > 0
    assert first["received"] == 1780999200.0  # 09-Jun-2026 10:00 UTC, as the server stamped it
    assert first["headers"]["Message-ID"] == "<a@x>"
    assert (second["uid"], second["flags"], second["has_attachments"]) == (2, "", True)
    assert second["headers"]["List-Unsubscribe"] == "<mailto:off@news.example>"


def test_flags_are_read_as_one_range(tmp_path):
    server, conn = _conn(tmp_path)
    for n in range(3):
        server.add("INBOX", mail(f"M{n}"), seen=(n == 1))
    assert conn.flags("INBOX", 2) == {2: "\\Seen", 3: ""}
    assert server.commands("FETCH")[-1][2] == "2:*"
    # Asking from past the newest message still brings the newest back; it is not wanted.
    assert conn.flags("INBOX", 9) == {}


def test_a_flag_change_made_elsewhere_arriving_mid_reply_does_not_hide_a_message(tmp_path):
    server, conn = _conn(tmp_path)
    server.add("INBOX", mail("One", attachment="report.pdf"))
    server.unasked.append(b"7 (FLAGS (\\Seen))")
    assert conn.message("INBOX", 1)["Subject"] == "One"
    server.unasked.append(b"7 (FLAGS (\\Seen))")
    assert [item["uid"] for item in conn.headers("INBOX", [1])] == [1]
    server.unasked.append(b"7 (FLAGS (\\Seen))")
    assert conn.flags("INBOX", 1) == {1: ""}


def test_a_message_that_is_not_there_reads_as_none(tmp_path):
    server, conn = _conn(tmp_path)
    server.add("INBOX", mail("One"))
    assert conn.message("INBOX", 99) is None


def test_marking_read_and_unread_changes_the_server(tmp_path):
    server, conn = _conn(tmp_path)
    server.add("INBOX", mail("One"))
    conn.set_seen("INBOX", [1], True)
    assert server.flags("INBOX", 1) == {"\\Seen"}
    conn.set_seen("INBOX", [1], False)
    assert server.flags("INBOX", 1) == set()


def test_a_folder_that_cannot_be_changed_is_reported_plainly_without_logging_in_again(tmp_path):
    server, conn = _conn(tmp_path)
    server.add("INBOX", mail("One"))
    server.read_only.add("INBOX")
    assert conn.message("INBOX", 1)["Subject"] == "One"  # it can still be read
    with pytest.raises(MailError, match="cannot be changed"):
        conn.set_seen("INBOX", [1], True)
    assert server.logins == 1


def test_archive_moves_to_the_archive_folder_and_bin_to_the_bin(tmp_path):
    server, conn = _conn(tmp_path)
    for subject in ("Keep", "Old news", "Junk"):
        server.add("INBOX", mail(subject))
    conn.move("INBOX", [2], "archive")
    conn.move("INBOX", [3], "bin")
    assert server.subjects("INBOX") == ["Keep"]
    assert server.subjects("Archive") == ["Old news"]
    assert server.subjects("Trash") == ["Junk"]


def test_on_gmail_archiving_means_all_mail(tmp_path):
    _, conn = _conn(tmp_path, folders=GMAIL_FOLDERS)
    assert conn.describe()["roles"] == {
        "inbox": "INBOX",
        "sent": "[Gmail]/Sent Mail",
        "all": "[Gmail]/All Mail",
        "archive": "[Gmail]/All Mail",
        "bin": "[Gmail]/Trash",
    }


def test_special_folders_without_flags_are_found_by_their_usual_names(tmp_path):
    _, conn = _conn(
        tmp_path, folders={"INBOX": "", "Sent Items": "", "Archives": "", "Deleted Items": ""}
    )
    roles = conn.describe()["roles"]
    assert (roles["sent"], roles["archive"], roles["bin"], roles["all"]) == (
        "Sent Items",
        "Archives",
        "Deleted Items",
        None,
    )


def test_a_server_without_move_reports_that_it_cannot_move_mail(tmp_path):
    server, conn = _conn(tmp_path, move=False)
    server.add("INBOX", mail("Stay"))
    assert conn.describe()["can_move"] is False
    with pytest.raises(MailError, match="cannot move mail"):
        conn.move("INBOX", [1], "archive")
    assert server.subjects("INBOX") == ["Stay"]
    assert not server.commands("MOVE")


def test_search_returns_the_newest_matches_first(tmp_path):
    server, conn = _conn(tmp_path)
    for subject in ("Invoice 1", "Lunch", "Invoice 2", "Invoice 3"):
        server.add("INBOX", mail(subject))
    assert conn.search("INBOX", "invoice") == [4, 3, 1]
    assert conn.search("INBOX", "invoice", limit=2) == [4, 3]
```

- [ ] **Step 3: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_mail_imap.py -q`
Expected: an error collecting the file, `ModuleNotFoundError: No module named 'coworker.mail'`.

- [ ] **Step 4: Write the connection**

Create an empty `coworker/mail/__init__.py`, then `coworker/mail/imap.py`:

```python
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
```

Notes for the implementer:

- `load_profile` comes from Task 3. Its error text is the tools' own "email is not connected; add it in Manage → Integrations".
- `imaplib` raises `IMAP4.abort` when the line drops and `IMAP4.error` when the server refuses a command. `abort` is a subclass of `error`, and `readonly` a subclass of `abort`, so the three `except` clauses must stay in the order written.
- `imaplib` cuts a FETCH reply at every literal and hands back any flag change the server had queued. `_answers` regroups the pieces by message; do not go back to reading `data[0]`, which is how `email_tools._fetch_message` reads and why Mail does not use it.
- A dead connection is closed with `shutdown()`, not `logout()`: a logout waits for the server's goodbye, which on a silent line is another 30 seconds with the lock held.
- A retry after a drop can repeat a `STORE` or a `MOVE`. Both are safe to repeat: setting a flag twice changes nothing, and moving uids that have already gone moves nothing.
- If Task 1's probe showed a server answering a header fetch in a shape `_parse_headers` would not read (no `UID` in either the tuple or the item after it), add that shape to `FakeMailConnection._fetch` and a test before changing the parser.

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/bin/pytest tests/test_mail_imap.py -q`
Expected: PASS, 20 tests.

- [ ] **Step 6: Run the Python gates**

Run: `.venv/bin/ruff check coworker tests scripts && .venv/bin/pytest -q`
Expected: `All checks passed!`, and pytest green.

- [ ] **Step 7: Commit**

```bash
git add coworker/mail/__init__.py coworker/mail/imap.py tests/mail_fakes.py tests/test_mail_imap.py
git commit -m "Give Mail one reused connection to the mailbox, with read, flag and move operations"
```

## Chunk 4: Threads, the cache, and preparing an email

Three small units with no network in them. Each is written test-first and committed on its own.

### Task 5: Which conversation a message belongs to

**Files:**
- Create: `coworker/mail/threads.py`
- Test: `tests/test_mail_threads.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_mail_threads.py`:

```python
"""Which conversation a message belongs to."""

from __future__ import annotations

import re

from coworker.mail.threads import thread_key


def test_a_reply_joins_the_conversation_its_references_start_with():
    first = {"Message-ID": "<root@x>"}
    reply = {"Message-ID": "<b@x>", "References": "<root@x> <a@x>", "In-Reply-To": "<a@x>"}
    assert thread_key(reply) == thread_key(first)


def test_a_reply_with_only_in_reply_to_joins_its_original():
    assert thread_key({"Message-ID": "<b@x>", "In-Reply-To": "<root@x>"}) == thread_key(
        {"Message-ID": "<root@x>"}
    )


def test_a_references_header_folded_over_two_lines_still_finds_its_root():
    folded = {"Message-ID": "<c@x>", "References": "\r\n <root@x>\r\n <a@x>"}
    assert thread_key(folded) == thread_key({"Message-ID": "<root@x>"})


def test_a_message_with_no_ids_is_a_conversation_of_its_own():
    one = thread_key({}, account="me@x", folder="INBOX", uid=1)
    two = thread_key({}, account="me@x", folder="INBOX", uid=2)
    assert one != two


def test_a_message_id_holding_a_slash_gives_a_key_that_is_safe_in_a_url():
    key = thread_key({"Message-ID": "<a/b+c=@x>"})
    assert re.fullmatch(r"[0-9a-f]{16}", key)
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_mail_threads.py -q`
Expected: an error collecting the file, `ModuleNotFoundError: No module named 'coworker.mail.threads'`.

- [ ] **Step 3: Write `coworker/mail/threads.py`**

```python
"""Which conversation a message belongs to: a pure function of its headers."""

from __future__ import annotations

import hashlib
import re
from typing import Any

_ID = re.compile(r"<[^<>\s]+>")


def _first_id(value: Any) -> str:
    text = " ".join(str(value or "").split())
    found = _ID.search(text)
    return found.group(0) if found else text


def thread_key(headers: Any, *, account: str = "", folder: str = "", uid: int = 0) -> str:
    """The conversation's key: 16 hex characters, the same for every message in it.

    The root is the first id in References, else In-Reply-To, else the message's own id,
    else a made-up one. It is hashed because a Message-ID can hold any character,
    including "/", and the key travels in URLs.
    """
    # ponytail: References root only; no subject matching.
    # Add a subject fallback if split threads are seen in real mailboxes.
    root = (
        _first_id(headers.get("References"))
        or _first_id(headers.get("In-Reply-To"))
        or _first_id(headers.get("Message-ID"))
        or f"{account}/{folder}/{uid}"
    )
    return hashlib.sha256(root.encode("utf-8", "replace")).hexdigest()[:16]
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/pytest tests/test_mail_threads.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check coworker tests scripts && .venv/bin/pytest -q
git add coworker/mail/threads.py tests/test_mail_threads.py
git commit -m "Group mail into conversations by the first message they refer back to"
```

### Task 6: The cache

One SQLite file. The mailbox is the truth, so everything in it but `setting` can be thrown away and rebuilt. It keeps a revision number that moves only when something the screen shows has changed, which is how the screen knows to reload.

**Files:**
- Create: `coworker/mail/store.py`
- Test: `tests/test_mail_store.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_mail_store.py`:

```python
"""Mail's local cache: what it lists, what it forgets, and when the screen should reload."""

from __future__ import annotations

from coworker.mail.store import MailStore

ME = "user@example.com"
DAY = 86400.0


def _row(folder, uid, *, key="k1", message_id="", sender="Ana <ana@example.com>",
         subject="Hello", date=100.0, flags="", account=ME):
    return {
        "account": account, "folder": folder, "uid": uid,
        "message_id": message_id or f"<{folder}-{uid}@x>", "thread_key": key,
        "sender": sender, "recipients": ME, "cc": "", "subject": subject, "date": date,
        "flags": flags, "size": 10, "has_attachments": 0, "bulk": 0,
    }


def _store(tmp_path) -> MailStore:
    return MailStore(tmp_path / "mail.db")


def test_the_list_is_the_inbox_conversations_newest_first(tmp_path):
    store = _store(tmp_path)
    store.add(
        [
            _row("INBOX", 1, key="old", subject="Old", date=100.0, flags="\\Seen"),
            _row("INBOX", 2, key="new", subject="New", date=300.0),
            _row("Sent", 1, key="mine", subject="Only sent", date=400.0),
        ]
    )
    threads = store.threads(ME, "INBOX")
    assert [t["subject"] for t in threads] == ["New", "Old"]
    assert [t["unread"] for t in threads] == [True, False]


def test_a_conversation_shows_your_reply_and_names_the_other_person(tmp_path):
    store = _store(tmp_path)
    store.add(
        [
            _row("INBOX", 1, subject="Lunch?", date=100.0, flags="\\Seen"),
            _row("Sent", 7, sender="Me <user@example.com>", subject="Re: Lunch?", date=200.0),
        ]
    )
    (thread,) = store.threads(ME, "INBOX")
    assert (thread["sender"], thread["subject"], thread["count"]) == (
        "Ana <ana@example.com>",
        "Re: Lunch?",
        2,
    )
    assert [(m["folder"], m["uid"]) for m in store.thread(ME, "k1", "INBOX")] == [
        ("INBOX", 1),
        ("Sent", 7),
    ]


def test_mail_sent_to_yourself_shows_once_as_the_inbox_copy(tmp_path):
    store = _store(tmp_path)
    store.add(
        [
            _row("Sent", 3, message_id="<self@x>", date=100.0),
            _row("INBOX", 9, message_id="<self@x>", date=100.0),
        ]
    )
    assert [(m["folder"], m["uid"]) for m in store.thread(ME, "k1", "INBOX")] == [("INBOX", 9)]
    assert store.threads(ME, "INBOX")[0]["count"] == 1


def test_the_revision_moves_only_when_something_changed(tmp_path):
    store = _store(tmp_path)
    store.add([_row("INBOX", 1)])
    before = store.revision
    store.set_flags(ME, "INBOX", {1: ""})
    store.set_flags(ME, "INBOX", {99: "\\Seen"})
    store.remove(ME, "INBOX", [42])
    assert store.revision == before
    store.set_flags(ME, "INBOX", {1: "\\Seen"})
    assert store.revision == before + 1


def test_marking_seen_keeps_a_messages_other_flags(tmp_path):
    store = _store(tmp_path)
    store.add([_row("INBOX", 1, flags="\\Answered")])
    store.set_seen(ME, "INBOX", [1], True)
    assert store.row(ME, "INBOX", 1)["flags"] == "\\Answered \\Seen"
    store.set_seen(ME, "INBOX", [1], False)
    assert store.row(ME, "INBOX", 1)["flags"] == "\\Answered"


def test_removing_a_message_removes_its_text_too(tmp_path):
    store = _store(tmp_path)
    store.add([_row("INBOX", 1)])
    store.put_body(ME, "INBOX", 1, {"html": "<p>x</p>", "text": "x", "attachments": []}, 0.0)
    store.remove(ME, "INBOX", [1])
    assert store.row(ME, "INBOX", 1) is None
    assert store.body(ME, "INBOX", 1, 0.0) is None


def test_a_new_uidvalidity_empties_that_folder_and_no_other(tmp_path):
    store = _store(tmp_path)
    assert store.folder_validity(ME, "INBOX") is None
    store.reset_folder(ME, "INBOX", "inbox", 1)
    store.add([_row("INBOX", 1), _row("Sent", 1)])
    store.reset_folder(ME, "INBOX", "inbox", 2)
    assert store.folder_validity(ME, "INBOX") == 2
    assert store.uids(ME, "INBOX") == set()
    assert store.uids(ME, "Sent") == {1}


def test_message_text_is_forgotten_thirty_days_after_it_was_last_opened(tmp_path):
    store = _store(tmp_path)
    body = {"html": "<p>x</p>", "text": "x", "attachments": [{"filename": "a.pdf"}]}
    store.put_body(ME, "INBOX", 1, body, 0.0)
    store.put_body(ME, "INBOX", 2, body, 0.0)
    assert store.body(ME, "INBOX", 2, 20 * DAY) == body  # opening it starts the clock again
    store.prune(31 * DAY)
    assert store.body(ME, "INBOX", 1, 31 * DAY) is None
    assert store.body(ME, "INBOX", 2, 31 * DAY) == body


def test_only_the_connected_mailbox_is_kept_and_disconnecting_empties_everything(tmp_path):
    store = _store(tmp_path)
    store.add([_row("INBOX", 1), _row("INBOX", 1, account="old@example.com")])
    store.put("last_sync", "5")
    store.forget_others(ME)
    assert store.uids("old@example.com", "INBOX") == set()
    assert store.uids(ME, "INBOX") == {1}
    store.clear()
    assert store.uids(ME, "INBOX") == set()
    assert store.get("last_sync") == ""


def test_a_change_acts_on_every_copy_while_the_reader_shows_one(tmp_path):
    store = _store(tmp_path)
    store.add(
        [
            _row("INBOX", 4, message_id="<twice@x>"),  # sent to you
            _row("INBOX", 5, message_id="<twice@x>"),  # and to a list you are on
            _row("Sent", 1, message_id="<mine@x>"),
        ]
    )
    assert len(store.thread(ME, "k1", "INBOX")) == 2
    assert sorted(row["uid"] for row in store.thread_rows(ME, "k1", "INBOX")) == [4, 5]


def test_mail_under_a_folder_that_is_no_longer_synced_is_dropped(tmp_path):
    store = _store(tmp_path)
    store.reset_folder(ME, "Sent", "sent", 1)
    store.add([_row("INBOX", 1), _row("Sent", 1)])
    store.keep_folders(ME, ["INBOX", "Sent Items"])
    assert store.uids(ME, "Sent") == set()
    assert store.folder_validity(ME, "Sent") is None
    assert store.uids(ME, "INBOX") == {1}


def test_a_write_from_a_pass_is_refused_once_the_user_has_changed_something(tmp_path):
    store = _store(tmp_path)
    store.add([_row("INBOX", 1), _row("INBOX", 2)])
    mark = store.touched
    assert store.set_flags(ME, "INBOX", {1: "\\Seen"}, expect=mark) is True
    with store.changing():  # the user marks a message read
        store.set_seen(ME, "INBOX", [2], True)
        during = store.touched
        # A pass that starts while the server has not yet answered is refused too.
        assert store.set_flags(ME, "INBOX", {2: ""}, expect=during) is False
    assert store.set_flags(ME, "INBOX", {2: ""}, expect=mark) is False
    assert store.set_flags(ME, "INBOX", {2: ""}, expect=during) is False
    assert store.remove(ME, "INBOX", [1], expect=mark) is False
    assert store.add([_row("INBOX", 3)], expect=mark) is False
    assert store.uids(ME, "INBOX") == {1, 2}
    assert store.row(ME, "INBOX", 2)["flags"] == "\\Seen"
    assert store.set_flags(ME, "INBOX", {2: ""}, expect=store.touched) is True


def test_emptying_the_cache_makes_a_pass_still_running_out_of_date(tmp_path):
    store = _store(tmp_path)
    mark = store.touched
    store.clear()
    assert store.add([_row("INBOX", 1)], expect=mark) is False
    assert store.uids(ME, "INBOX") == set()
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_mail_store.py -q`
Expected: an error collecting the file, `ModuleNotFoundError: No module named 'coworker.mail.store'`.

- [ ] **Step 3: Write `coworker/mail/store.py`**

```python
"""Mail's local cache: what the list and the reader show without asking the server.

The mailbox is the truth. Every table here except `setting` can be deleted and rebuilt
from it. Rows are keyed by where the server keeps a message (folder and uid), which
changes when the message moves; anything that must outlive a move is keyed by
`thread_key` or `Message-ID` instead. Thread-safe (check_same_thread=False and a lock),
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


class MailStore:
    def __init__(self, path: str | Path) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
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

    def _write(self, statements: list[tuple[str, list]], expect: Optional[int]) -> bool:
        """Run each statement for each of its rows, as one change. With `expect` (a sync
        pass), nothing is written and False comes back if the user has changed something
        since the pass noted `touched`, or is changing something now. The revision moves
        only if a row changed."""
        with self._lock, self._conn:
            if expect is not None and (self._changing or expect != self.touched):
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

    def add(self, rows: list[dict[str, Any]], expect: Optional[int] = None) -> bool:
        return self._write([(_INSERT, rows)], expect)

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
        self, account: str, folder: str, uid: int, rendered: dict[str, Any], now: float
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO body (account, folder, uid, html, text, attachments, opened_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (account, folder, uid, rendered["html"], rendered["text"],
                 json.dumps(rendered["attachments"]), now),
            )

    def prune(self, now: float) -> None:
        """Forget message text nobody has opened for 30 days. The cache must not only grow."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM body WHERE opened_at < ?", (now - _BODY_SECONDS,))

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
        """Drop every other mailbox's mail: only one is connected at a time."""
        with self._lock, self._conn:
            changed = sum(
                self._conn.execute(f"DELETE FROM {table} WHERE account != ?", (account,)).rowcount
                for table in ("folder", "message", "body")
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
            for table in ("folder", "message", "body", "setting"):
                self._conn.execute(f"DELETE FROM {table}")
            self.revision += 1
            # A pass still running when the mailbox was disconnected must not write its
            # mail back, so everything it noted is made out of date.
            self.touched += 1


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
```

Notes for the implementer:

- `sender` and `recipients` are the columns for From and To, because `from` and `to` are SQL keywords.
- `add` takes whole rows (they carry their own `account` and `folder`), so a row taken out by an archive can be put straight back if the server refuses.
- `prune` and `put_body` do not move the revision: neither changes what the list shows.
- The facade wraps each change in `store.changing()`; `add`, `remove` and `set_flags` take `expect` from a sync pass and nothing from the facade. That is what stops a pass that read the mailbox a moment ago from undoing an archive or a mark the user has just made; keep the check and the write inside the one lock.
- `thread` is for showing (one row for each message); `thread_rows` is for acting (every copy in a folder). Do not act on de-duplicated rows.
- `clear` empties `setting` too. Every setting in Plan A describes the mailbox. Plan C adds preferences (the sorting switch, excluded senders); it must decide there whether a disconnect should wipe them.
- Plans B and C add `comment`, `draft` and `thread_ai`. They must not be keyed by folder and uid; see the module docstring.

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/pytest tests/test_mail_store.py -q`
Expected: PASS, 13 tests.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check coworker tests scripts && .venv/bin/pytest -q
git add coworker/mail/store.py tests/test_mail_store.py
git commit -m "Add Mail's local cache, which forgets what the retention rules say it should"
```

### Task 7: Preparing an email for the screen

A pure function from a parsed message to its HTML, its text and its attachment list. It does not try to make the HTML safe; that is `disarm.ts` and the sandboxed frame. An attached email (a forward, a bounce) is one attachment: its body is never shown as this message's.

**Files:**
- Create: `coworker/mail/render.py`
- Test: `tests/test_mail_render.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_mail_render.py`:

```python
"""Preparing one email for the screen."""

from __future__ import annotations

import base64
from email.message import EmailMessage

from mail_fakes import mail

from coworker.mail import render
from coworker.mail.render import render_message

PNG = b"\x89PNG-not-really"


def _with_inline_image(payload: bytes = PNG) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = "Logo"
    msg.set_content("See the logo.")
    msg.add_alternative('<p>Hi <img src="cid:logo@x"> <img src="cid:missing@x"></p>', subtype="html")
    msg.get_payload()[1].add_related(payload, maintype="image", subtype="png", cid="<logo@x>")
    return msg


def test_an_emails_own_inline_image_travels_inside_the_html():
    out = render_message(_with_inline_image())
    assert f'src="data:image/png;base64,{base64.b64encode(PNG).decode()}"' in out["html"]
    assert 'src=""' in out["html"]  # a cid with no part behind it loads nothing
    assert "cid:" not in out["html"]
    assert out["text"].strip() == "See the logo."


def test_the_letters_cid_outside_an_image_address_are_left_alone():
    msg = _with_inline_image()
    html = '<p>Ref cid:12345, acid:rain. <a href="cid:logo@x">logo</a> <img src="cid:logo%40x"></p>'
    msg.get_payload()[1].get_payload()[0].set_content(html, subtype="html")
    out = render_message(msg)["html"]
    assert "Ref cid:12345, acid:rain." in out
    assert 'href="cid:logo@x"' in out
    assert out.count("data:image/png;base64,") == 1  # the one image address, percent-encoded


def test_an_attached_email_is_an_attachment_and_its_body_is_not_shown_as_this_one(tmp_path):
    inner = mail("The original", body="Inner text.", html="<p>INNER HTML</p>")
    outer = EmailMessage()
    outer["Subject"] = "Fwd: The original"
    outer.set_content("See the attached email.")
    outer.add_attachment(inner, filename="original.eml")
    out = render_message(outer)
    assert "See the attached email." in out["html"]
    assert "INNER HTML" not in out["html"]
    assert "Inner text." not in out["text"]
    (listed,) = out["attachments"]
    assert (listed["filename"], listed["content_type"]) == ("original.eml", "message/rfc822")
    assert listed["size"] > 0


def test_an_html_only_email_carrying_another_gives_its_own_text_not_the_attached_ones():
    outer = EmailMessage()
    outer["Subject"] = "Fwd"
    outer.set_content("<p>Mine <b>only</b>.</p>", subtype="html")
    outer.add_attachment(mail("The original", body="Inner text."), filename="original.eml")
    out = render_message(outer)
    assert out["text"] == "Mine only."


def test_text_written_around_an_attachment_is_all_shown():
    msg = EmailMessage()
    msg["Subject"] = "Photos"
    msg.set_content("<p>Before the photo.</p>", subtype="html")
    msg.add_attachment(b"%PDF-fake", maintype="application", subtype="pdf", filename="photo.pdf")
    from email.mime.text import MIMEText

    msg.attach(MIMEText("<p>After the photo.</p>", "html"))
    out = render_message(msg)
    assert "Before the photo." in out["html"] and "After the photo." in out["html"]
    assert out["html"].index("Before") < out["html"].index("After")
    assert "After the photo." in out["text"]
    assert [a["filename"] for a in out["attachments"]] == ["photo.pdf"]


def test_a_bounce_lists_the_original_it_carries_under_its_subject():
    from email.mime.message import MIMEMessage
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    bounce = MIMEMultipart("report")
    bounce["Subject"] = "Undelivered"
    bounce.attach(MIMEText("Your message could not be delivered.", "plain"))
    bounce.attach(MIMEMessage(mail("Lunch on Friday", body="Inner text.")))
    out = render_message(bounce)
    assert "could not be delivered" in out["html"]
    assert "Inner text." not in out["html"] and "Inner text." not in out["text"]
    assert [a["filename"] for a in out["attachments"]] == ["Lunch on Friday.eml"]


def test_an_email_that_is_wholly_a_forwarded_email_shows_that_email():
    from email.mime.message import MIMEMessage

    wrapper = MIMEMessage(mail("Inside", body="The real words."))
    wrapper["Subject"] = "Fwd: Inside"
    assert "The real words." in render_message(wrapper)["html"]


def test_inline_images_past_the_limit_are_left_out(monkeypatch):
    monkeypatch.setattr(render, "_INLINE_LIMIT", 4)
    out = render_message(_with_inline_image())
    assert "data:image" not in out["html"]
    assert "<p>Hi" in out["html"]


def test_a_plain_text_email_is_shown_escaped_with_its_line_breaks():
    out = render_message(mail(body="Line one\n<b>not bold</b>\n"))
    assert "Line one\n&lt;b&gt;not bold&lt;/b&gt;" in out["html"]
    assert out["html"].startswith("<pre")
    assert out["attachments"] == []


def test_attachments_are_listed_with_their_size_and_not_shown_as_the_body():
    out = render_message(mail(body="See attached.", html="<p>See attached.</p>", attachment="report.pdf"))
    assert out["html"].strip() == "<p>See attached.</p>"
    assert out["attachments"] == [
        {"filename": "report.pdf", "content_type": "application/pdf", "size": 9}
    ]
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_mail_render.py -q`
Expected: an error collecting the file, `ModuleNotFoundError: No module named 'coworker.mail.render'`.

- [ ] **Step 3: Write `coworker/mail/render.py`**

```python
"""Prepare one email for the screen: its HTML, its text, and its attachment list.

Nothing here tries to make the HTML safe. An email is untrusted and stays untrusted;
confining it is the reader's job (`disarm.ts` and the sandboxed frame), where the
browser's own parser does the work. This only chooses the parts to show and brings the
email's own inline images along, so the reader need not load anything.

An attached email (a forward, a bounce's original) is one attachment. Its insides are
never walked: not for the body, not for the text, not for the attachment list.
"""

from __future__ import annotations

import base64
import email as email_lib
import re
from html import escape
from typing import Any, Iterator
from urllib.parse import unquote

from ..connectors.email_tools import (
    _BODY_CHAR_LIMIT,
    _decode_payload,
    _strip_html,
    decode_mime_header,
)

Message = email_lib.message.Message

# All of one message's inline images together. Past this they are left out, so a single
# email cannot make the cache or the page enormous.
_INLINE_LIMIT = 5 * 1024 * 1024
# Only where an image's address goes. The letters "cid:" also turn up in ordinary text
# and inside other addresses, and those must be left as they are.
_CID_SRC = re.compile(r"(\bsrc\s*=\s*[\"']?)cid:([^\"'\s>]+)", re.IGNORECASE)
_PLAIN_STYLE = "white-space:pre-wrap;font:14px/1.5 system-ui,sans-serif;margin:0"


def _is_attachment(part: Message) -> bool:
    disposition = str(part.get("Content-Disposition", ""))
    return (
        part.get_content_maintype() == "message"
        or "attachment" in disposition
        or bool(part.get_filename() and "inline" in disposition)
    )


def _own_parts(msg: Message) -> Iterator[Message]:
    """The message's own leaf parts, with an attached email counting as one leaf."""
    if msg.is_multipart() and msg.get_content_maintype() != "message":
        for part in msg.get_payload():
            yield from _own_parts(part)
    else:
        yield msg


def _body_parts(msg: Message, prefer: str) -> list[Message]:
    """What the sender wrote, in order: every text part that is not an attachment. Where
    the email offers the same thing two ways (`multipart/alternative`), the `prefer` kind."""
    if _is_attachment(msg):
        return []
    if not msg.is_multipart():
        return [msg] if msg.get_content_type() in ("text/html", "text/plain") else []
    children = msg.get_payload()
    if msg.get_content_subtype() == "alternative":
        other = "text/plain" if prefer == "text/html" else "text/html"
        for kind in (prefer, other):
            for child in reversed(children):  # the richest version comes last
                found = _body_parts(child, prefer)
                if any(part.get_content_type() == kind for part in found):
                    return found
        return []
    # Mixed, related, signed: everything in turn. A mail app that puts an attachment in
    # the middle of the text sends the text as two parts, and both are the message.
    return [part for child in children for part in _body_parts(child, prefer)]


def attachments(msg: Message) -> list[tuple[str, Message]]:
    """(name, part) for each attachment, in order. `render_message` lists them and
    `MailService.save_attachment` saves by place in this same list."""
    out = []
    for part in _own_parts(msg):
        if not _is_attachment(part):
            continue
        name = decode_mime_header(part.get_filename() or "")
        if not name and part.get_content_type() == "message/rfc822" and part.is_multipart():
            # A bounce carries the original with no file name; name it after its subject.
            subject = decode_mime_header(part.get_payload(0).get("Subject", "")).strip()
            name = f"{subject or 'Attached message'}.eml"
        out.append((name or "attachment", part))
    return out


def attachment_bytes(part: Message) -> bytes:
    """An attachment's content. An attached email is a message inside a part, not a payload."""
    if part.get_content_maintype() == "message" and part.is_multipart():
        return part.get_payload(0).as_bytes()
    return part.get_payload(decode=True) or b""


def render_message(msg: Message) -> dict[str, Any]:
    if msg.get_content_type() == "message/rfc822" and msg.is_multipart():
        # The whole email is one forwarded email: show that, or there is nothing to show.
        msg = msg.get_payload(0)
    inline = {
        str(part.get("Content-ID", "")).strip("<> "): part
        for part in _own_parts(msg)
        if part.get("Content-ID") and part.get_content_maintype() == "image"
    }
    left = _INLINE_LIMIT

    def embed(match: re.Match) -> str:
        nonlocal left
        part = inline.get(unquote(match.group(2)))
        payload = (part.get_payload(decode=True) or b"") if part is not None else b""
        if not payload or len(payload) > left:
            return match.group(1)
        left -= len(payload)
        data = base64.b64encode(payload).decode()
        return f"{match.group(1)}data:{part.get_content_type()};base64,{data}"

    shown = []
    for part in _body_parts(msg, "text/html"):
        if part.get_content_type() == "text/html":
            shown.append(_CID_SRC.sub(embed, _decode_payload(part)))
        else:
            # Plain text has no look of its own, so it gets the app's plain one.
            shown.append(f'<pre style="{_PLAIN_STYLE}">{escape(_decode_payload(part))}</pre>')

    words = [
        _decode_payload(part) if part.get_content_type() == "text/plain" else _strip_html(_decode_payload(part))
        for part in _body_parts(msg, "text/plain")
    ]
    text = "\n\n".join(piece.strip() for piece in words if piece.strip())
    if len(text) > _BODY_CHAR_LIMIT:
        text = text[:_BODY_CHAR_LIMIT] + "\n…[truncated]"

    return {
        "html": "\n".join(shown),
        "text": text,
        "attachments": [
            {"filename": name, "content_type": part.get_content_type(), "size": len(attachment_bytes(part))}
            for name, part in attachments(msg)
        ],
    }
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/pytest tests/test_mail_render.py -q`
Expected: PASS, 10 tests.

- [ ] **Step 5: Run the Python gates and commit**

Run: `.venv/bin/ruff check coworker tests scripts && .venv/bin/pytest -q`
Expected: `All checks passed!`, and pytest green.

```bash
git add coworker/mail/render.py tests/test_mail_render.py
git commit -m "Prepare an email for the screen with its own inline images inside it"
```

## Chunk 5: Sync

### Task 8: A sync pass

One background thread brings the cache up to date. A second request while a pass runs starts nothing but leaves a mark, so one more pass runs afterwards.

**Files:**
- Create: `coworker/mail/sync.py`
- Test: `tests/test_mail_sync.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_mail_sync.py`:

```python
"""A sync pass: the cache ends up matching the mailbox, one pass at a time."""

from __future__ import annotations

import threading
import time

from mail_fakes import ADDRESS, FakeMailServer, connected_secrets, mail

from coworker.mail.imap import MailConnection
from coworker.mail.store import MailStore
from coworker.mail.sync import MailSync


def _setup(tmp_path, **server_options):
    server = FakeMailServer(**server_options)
    secrets = connected_secrets(tmp_path)
    conn = MailConnection(secrets, imap_factory=server.connect)
    store = MailStore(tmp_path / "mail.db")
    return server, secrets, store, MailSync(conn, store)


def _subjects(store):
    return [t["subject"] for t in store.threads(ADDRESS, "INBOX")]


def _wait_until_idle(sync):
    deadline = time.time() + 5
    while sync.running and time.time() < deadline:
        time.sleep(0.01)
    assert not sync.running


def test_a_pass_picks_up_new_mail_flag_changes_made_elsewhere_and_mail_moved_away(tmp_path):
    server, _, store, sync = _setup(tmp_path)
    server.add("INBOX", mail("First", days_ago=2))
    server.add("INBOX", mail("Second", days_ago=1))
    sync.run_once()
    assert _subjects(store) == ["Second", "First"]
    assert all(t["unread"] for t in store.threads(ADDRESS, "INBOX"))

    server.add("INBOX", mail("Third"))
    server.flags("INBOX", 1).add("\\Seen")  # read in another mail app
    del server.folders["INBOX"][2]  # archived in another mail app
    sync.run_once()
    assert _subjects(store) == ["Third", "First"]
    assert [t["unread"] for t in store.threads(ADDRESS, "INBOX")] == [True, False]


def test_a_pass_with_nothing_new_changes_nothing(tmp_path):
    server, _, store, sync = _setup(tmp_path)
    server.add("INBOX", mail("Only"))
    sync.run_once()
    before = store.revision
    sync.run_once()
    assert store.revision == before
    assert _subjects(store) == ["Only"]


def test_a_changed_uidvalidity_rebuilds_the_folder(tmp_path):
    server, _, store, sync = _setup(tmp_path)
    server.add("INBOX", mail("Before"))
    sync.run_once()
    server.folders["INBOX"].clear()
    server.uidvalidity["INBOX"] = 2
    server._next["INBOX"] = 1
    server.add("INBOX", mail("After"))  # the same uid now names another message
    sync.run_once()
    assert _subjects(store) == ["After"]
    assert store.folder_validity(ADDRESS, "INBOX") == 2


def test_mail_that_leaves_the_window_leaves_the_cache(tmp_path, monkeypatch):
    server, _, store, sync = _setup(tmp_path)
    for subject in ("One", "Two", "Three"):
        server.add("INBOX", mail(subject))
    sync.run_once()
    monkeypatch.setattr(
        sync._conn, "window", lambda folder: (1, [2, 3] if folder == "INBOX" else [])
    )
    sync.run_once()
    assert store.uids(ADDRESS, "INBOX") == {2, 3}


def test_your_sent_reply_joins_the_conversation_it_answers(tmp_path):
    server, _, store, sync = _setup(tmp_path)
    server.add("INBOX", mail("Lunch?", message_id="<q@x>", days_ago=1))
    server.add(
        "Sent",
        mail("Re: Lunch?", sender=ADDRESS, to="ana@example.com", message_id="<a@x>",
             references="<q@x>", in_reply_to="<q@x>"),
        seen=True,
    )
    sync.run_once()
    (thread,) = store.threads(ADDRESS, "INBOX")
    assert (thread["count"], thread["subject"], thread["sender"]) == (
        2,
        "Re: Lunch?",
        "Ana <ana@example.com>",
    )


def test_a_newsletter_is_marked_from_its_headers(tmp_path):
    server, _, store, sync = _setup(tmp_path)
    server.add("INBOX", mail("Weekly", headers={"List-Unsubscribe": "<mailto:off@n.example>"}))
    server.add("INBOX", mail("Personal"))
    sync.run_once()
    assert [store.row(ADDRESS, "INBOX", uid)["bulk"] for uid in (1, 2)] == [1, 0]


def test_a_pass_records_whether_the_mailbox_can_archive_and_bin(tmp_path):
    _, _, store, sync = _setup(tmp_path)
    sync.run_once()
    assert (store.get("can_archive"), store.get("can_bin")) == ("1", "1")
    _, _, store, sync = _setup(tmp_path / "other", move=False)
    sync.run_once()
    assert (store.get("can_archive"), store.get("can_bin")) == ("", "")


def test_connecting_a_different_mailbox_forgets_the_old_ones_mail(tmp_path):
    server, secrets, store, sync = _setup(tmp_path)
    server.add("INBOX", mail("Old mailbox"))
    sync.run_once()
    secrets.put("email:default", {**secrets.get("email:default"), "address": "other@example.com"})
    sync.run_once()
    assert store.uids(ADDRESS, "INBOX") == set()
    assert store.uids("other@example.com", "INBOX") == {1}


def test_a_second_request_during_a_pass_starts_nothing_and_one_more_pass_runs_after(
    tmp_path, monkeypatch
):
    _, _, _, sync = _setup(tmp_path)
    started, release, passes = threading.Event(), threading.Event(), []

    def slow_pass(now=None):
        passes.append(1)
        started.set()
        release.wait(5)

    monkeypatch.setattr(sync, "run_once", slow_pass)
    assert sync.request() is True
    assert started.wait(5)
    assert sync.request() is False
    assert sync.request() is False
    assert sync.running
    release.set()
    _wait_until_idle(sync)
    assert len(passes) == 2


def test_a_pass_that_fails_says_why_and_keeps_what_was_cached(tmp_path):
    server, _, store, sync = _setup(tmp_path)
    server.add("INBOX", mail("Still here"))
    sync.request()
    _wait_until_idle(sync)
    assert store.get("last_error") == ""
    assert float(store.get("last_sync")) > 0

    server.password = "changed elsewhere"
    sync._conn.close()
    sync.request()
    _wait_until_idle(sync)
    assert "app password" in store.get("last_error")
    assert _subjects(store) == ["Still here"]


def test_a_pass_that_cannot_even_record_its_failure_still_lets_the_next_one_start(
    tmp_path, monkeypatch
):
    server, _, store, sync = _setup(tmp_path)
    server.add("INBOX", mail("Here"))

    def broken(key, value):
        raise RuntimeError("the cache is closed")

    monkeypatch.setattr(store, "put", broken)
    sync.request()
    _wait_until_idle(sync)
    monkeypatch.undo()
    assert sync.request() is True
    _wait_until_idle(sync)
    assert _subjects(store) == ["Here"]


def test_stopping_ends_the_pass_under_way_so_nothing_is_written_afterwards(tmp_path, monkeypatch):
    server, _, store, sync = _setup(tmp_path)
    for n in range(3):
        server.add("INBOX", mail(f"Mail {n}"))
    reading, release = threading.Event(), threading.Event()
    real_headers = sync._conn.headers

    def slow_headers(folder, uids):
        reading.set()
        release.wait(5)
        return real_headers(folder, uids)

    monkeypatch.setattr(sync._conn, "headers", slow_headers)
    sync.request()
    assert reading.wait(5)
    threading.Timer(0.05, release.set).start()
    sync.stop()  # the mailbox was disconnected mid-pass
    store.clear()
    assert not sync.running
    assert store.uids(ADDRESS, "INBOX") == set()
    assert store.get("last_error") == ""
    monkeypatch.undo()
    assert sync.request() is True  # and Mail can sync again afterwards
    _wait_until_idle(sync)
    assert len(_subjects(store)) == 3


def test_a_date_without_a_zone_is_read_as_utc_not_as_this_computers_time():
    from email.message import EmailMessage

    from coworker.mail.sync import message_row

    headers = EmailMessage()
    headers["Date"] = "Mon, 09 Jun 2026 10:00:00 -0000"
    row = message_row(ADDRESS, "INBOX", {"uid": 1, "flags": "", "size": 0, "has_attachments": False, "headers": headers})
    assert row["date"] == 1780999200.0


def test_a_change_made_while_a_pass_is_reading_is_not_undone_by_that_pass(tmp_path, monkeypatch):
    server, _, store, sync = _setup(tmp_path)
    server.add("INBOX", mail("One"), seen=True)
    sync.run_once()
    real_flags = sync._conn.flags

    def flags_then_the_user_acts(folder, low_uid):
        read = real_flags(folder, low_uid)  # the server still says "read"...
        if folder == "INBOX":
            with store.changing():  # ...and now the user marks it unread
                store.set_seen(ADDRESS, "INBOX", [1], False)
        return read

    monkeypatch.setattr(sync._conn, "flags", flags_then_the_user_acts)
    sync.request()  # the pass ends early, quietly, when its write is refused
    _wait_until_idle(sync)
    assert store.threads(ADDRESS, "INBOX")[0]["unread"] is True


def test_a_pass_that_starts_while_a_change_is_on_its_way_to_the_server_cannot_undo_it(tmp_path):
    server, _, store, sync = _setup(tmp_path)
    server.add("INBOX", mail("One"))
    sync.run_once()
    with store.changing():  # archived here; the server has not been told yet
        store.remove(ADDRESS, "INBOX", [1])
        sync.request()  # a pass begins now and still finds the message in the inbox
        _wait_until_idle(sync)
        assert store.uids(ADDRESS, "INBOX") == set()
    del server.folders["INBOX"][1]  # the move lands
    sync.run_once()
    assert store.uids(ADDRESS, "INBOX") == set()


def test_a_pass_that_outlives_the_wait_to_stop_still_writes_nothing(tmp_path, monkeypatch):
    server, _, store, sync = _setup(tmp_path)
    server.add("INBOX", mail("Slow to arrive"))
    reading, release = threading.Event(), threading.Event()
    real_headers = sync._conn.headers

    def stuck_headers(folder, uids):
        reading.set()
        release.wait(5)
        return real_headers(folder, uids)

    monkeypatch.setattr(sync._conn, "headers", stuck_headers)
    sync.request()
    assert reading.wait(5)
    sync.stop(timeout=0.05)  # gives up waiting while the fetch is still out
    store.clear()
    release.set()
    _wait_until_idle(sync)
    assert store.uids(ADDRESS, "INBOX") == set()
    assert store.get("last_error") == ""


def test_a_message_with_no_readable_date_is_dated_by_when_the_server_received_it():
    from email.message import EmailMessage

    from coworker.mail.sync import message_row

    item = {"uid": 1, "flags": "", "size": 0, "has_attachments": False, "headers": EmailMessage(), "received": 1780999200.0}
    assert message_row(ADDRESS, "INBOX", item)["date"] == 1780999200.0
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_mail_sync.py -q`
Expected: an error collecting the file, `ModuleNotFoundError: No module named 'coworker.mail.sync'`.

- [ ] **Step 3: Write `coworker/mail/sync.py`**

```python
"""Bring the cache up to date with the mailbox, one pass at a time, off the request path."""

from __future__ import annotations

import threading
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

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
    def __init__(self, conn: MailConnection, store: MailStore) -> None:
        self._conn = conn
        self._store = store
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
```

Notes for the implementer:

- Plan C adds sorting as a second phase of `run_once`. Leave room for it by keeping `run_once` a plain sequence; do not add it now.
- The pass never holds the connection's lock across steps. Each call into `self._conn` takes and releases it, so a click on the screen waits for one step at most.
- Every write the pass makes from what it read off the server carries `expect=mark`. If the user marked or moved something meanwhile, the write is refused and the folder is left for the pass their change asked for. Without this a pass in flight puts back what the user just changed.
- `stop()` exists for disconnecting and closing. It must be called before the cache is emptied or closed, or a pass still running writes a disconnected mailbox's mail back to disk.
- `_running` is cleared in the same locked step that decides not to run again, and again if the loop itself fails, so it can never stay on.

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/pytest tests/test_mail_sync.py -q`
Expected: PASS, 17 tests.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check coworker tests scripts && .venv/bin/pytest -q
git add coworker/mail/sync.py tests/test_mail_sync.py
git commit -m "Sync the inbox and sent mail into the cache, one pass at a time"
```

## Chunk 6: The facade

### Task 9: What the screen can ask for

`MailService` is the one object the routes talk to. It answers every failure as `{ok: False, error: "…"}` in plain language. Changes are made to the cache first so the list responds at once, then to the server, and put back if the server refuses.

**Files:**
- Create: `coworker/mail/service.py`
- Test: `tests/test_mail_service.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_mail_service.py`:

```python
"""What the Mail screen can ask for, against a mail server in memory."""

from __future__ import annotations

import pytest
from mail_fakes import ADDRESS, GMAIL_FOLDERS, FakeMailServer, connected_secrets, mail

from coworker.mail.service import MailService
from coworker.mail.sync import _Stopped
from coworker.secrets import SecretStore


def _service(tmp_path, **server_options):
    server = FakeMailServer(**server_options)
    service = MailService(
        connected_secrets(tmp_path),
        tmp_path / "mail.db",
        imap_factory=server.connect,
        downloads=tmp_path / "Downloads",
    )
    return server, service


def _synced(service):
    service._sync.run_once()
    return service.threads()["threads"]


def test_a_mailbox_that_is_not_connected_is_reported_without_asking_any_server(tmp_path):
    server = FakeMailServer()
    service = MailService(
        SecretStore(tmp_path / "secrets.json"), tmp_path / "mail.db", imap_factory=server.connect
    )
    status = service.status()
    assert (status["connected"], status["address"], status["syncing"]) == (False, "", False)
    assert service.sync()["ok"] is False
    assert server.logins == 0


def test_status_after_a_pass_says_what_the_mailbox_can_do(tmp_path):
    _, service = _service(tmp_path)
    _synced(service)
    status = service.status()
    assert (status["connected"], status["address"]) == (True, ADDRESS)
    assert (status["can_archive"], status["can_bin"], status["last_error"]) == (True, True, "")
    assert status["last_sync"] > 0


def test_a_conversation_lists_its_messages_and_each_opens_from_the_cache_the_second_time(tmp_path):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("Plan", body="Shall we?", html="<p>Shall we?</p>", attachment="plan.pdf"))
    (row,) = _synced(service)
    thread = service.thread(row["key"])
    assert (thread["ok"], thread["subject"], thread["in_inbox"]) == (True, "Plan", True)
    (envelope,) = thread["messages"]
    assert (envelope["folder"], envelope["uid"], envelope["unread"]) == ("INBOX", 1, True)

    first = service.message("INBOX", 1)
    assert first["ok"] and first["html"].startswith("<p>Shall we?</p>")
    assert first["text"].strip() == "Shall we?"
    assert first["attachments"][0]["filename"] == "plan.pdf"
    assert first["thread_key"] == row["key"]
    fetches = len(server.commands("FETCH"))
    assert service.message("INBOX", 1) == first
    assert len(server.commands("FETCH")) == fetches
    assert server.flags("INBOX", 1) == set()  # reading the text does not mark it read


def test_a_conversation_whose_message_id_holds_a_slash_opens(tmp_path):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("Odd id", message_id="<a/b@x>"))
    (row,) = _synced(service)
    assert "/" not in row["key"]
    assert service.thread(row["key"])["messages"][0]["message_id"] == "<a/b@x>"


def test_a_conversation_that_is_gone_says_so(tmp_path):
    _, service = _service(tmp_path)
    assert service.thread("0123456789abcdef")["ok"] is False
    assert "no longer" in service.message("INBOX", 99)["error"]


def test_marking_a_conversation_read_and_unread_reaches_the_server(tmp_path):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("One", message_id="<1@x>"))
    server.add("INBOX", mail("Two", message_id="<2@x>", references="<1@x>"))
    (row,) = _synced(service)
    assert service.mark_thread(row["key"], True) == {"ok": True}
    assert service.threads()["threads"][0]["unread"] is False
    assert server.flags("INBOX", 1) == server.flags("INBOX", 2) == {"\\Seen"}
    service.mark_thread(row["key"], False)
    assert service.threads()["threads"][0]["unread"] is True
    assert server.flags("INBOX", 1) == set()


def test_the_same_message_twice_in_the_inbox_is_marked_and_moved_as_both_copies(tmp_path):
    server, service = _service(tmp_path)
    for _ in range(2):  # sent to you, and to a list you are on
        server.add("INBOX", mail("Notice", message_id="<twice@x>"))
    (row,) = _synced(service)
    service.mark_thread(row["key"], True)
    assert server.flags("INBOX", 1) == server.flags("INBOX", 2) == {"\\Seen"}
    assert service.threads()["threads"][0]["unread"] is False
    assert service.archive(row["key"]) == {"ok": True}
    assert server.subjects("INBOX") == []
    assert server.subjects("Archive") == ["Notice", "Notice"]


def test_a_change_asks_for_a_pass_so_one_already_under_way_cannot_undo_it(tmp_path, monkeypatch):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("One"))
    (row,) = _synced(service)
    asked = []
    monkeypatch.setattr(service._sync, "request", lambda: asked.append(1) or True)
    service.mark_thread(row["key"], True)
    service.mark_message_read("INBOX", 1)
    service.archive(row["key"])
    assert len(asked) == 3


def test_a_refused_flag_change_puts_the_list_back_and_says_why(tmp_path):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("One"))
    (row,) = _synced(service)
    server.drops = 5
    result = service.mark_thread(row["key"], True)
    assert result["ok"] is False and "stopped answering" in result["error"]
    assert service.threads()["threads"][0]["unread"] is True


def test_archiving_moves_the_inbox_messages_and_the_conversation_leaves_the_list(tmp_path):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("Done with this"))
    server.add("INBOX", mail("Keep"))
    rows = _synced(service)
    key = next(r["key"] for r in rows if r["subject"] == "Done with this")
    assert service.archive(key) == {"ok": True}
    assert [t["subject"] for t in service.threads()["threads"]] == ["Keep"]
    assert server.subjects("Archive") == ["Done with this"]
    assert server.subjects("INBOX") == ["Keep"]


def test_moving_to_the_bin_uses_the_bin_folder(tmp_path):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("Junk"))
    (row,) = _synced(service)
    assert service.bin(row["key"]) == {"ok": True}
    assert server.subjects("Trash") == ["Junk"]


def test_a_refused_move_puts_the_conversation_back_and_says_why(tmp_path):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("Stay"))
    (row,) = _synced(service)
    server.capabilities = "IMAP4rev1"
    service._conn.close()  # the next login learns the server cannot move
    result = service.archive(row["key"])
    assert result == {"ok": False, "error": "this mailbox cannot move mail"}
    assert [t["subject"] for t in service.threads()["threads"]] == ["Stay"]
    assert server.subjects("INBOX") == ["Stay"]


def test_search_reaches_archived_mail_and_opens_and_marks_a_message_that_is_not_cached(tmp_path):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("Invoice March", days_ago=1))
    old = server.add("Archive", mail("Invoice January", days_ago=300, body="Paid in full."))
    server.add("Sent", mail("Lunch", sender=ADDRESS))
    found = service.search("invoice")
    assert [(r["subject"], r["folder"]) for r in found["results"]] == [
        ("Invoice March", "INBOX"),
        ("Invoice January", "Archive"),
    ]
    opened = service.message("Archive", old)
    assert opened["ok"] and "Paid in full." in opened["html"]
    assert len(opened["thread_key"]) == 16
    assert service.mark_message_read("Archive", old) == {"ok": True}
    assert server.flags("Archive", old) == {"\\Seen"}
    assert service.search("   ") == {"ok": True, "results": []}


def test_on_gmail_search_looks_in_all_mail_only(tmp_path):
    server, service = _service(tmp_path, folders=GMAIL_FOLDERS)
    server.add("INBOX", mail("Invoice"))
    server.add("[Gmail]/All Mail", mail("Invoice"))
    found = service.search("invoice")
    assert [r["folder"] for r in found["results"]] == ["[Gmail]/All Mail"]


def test_saving_an_attachment_writes_it_to_downloads_without_replacing_a_file(tmp_path):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("Report", attachment="report.pdf"))
    first = service.save_attachment("INBOX", 1, 0)
    second = service.save_attachment("INBOX", 1, 0)
    assert first == {"ok": True, "path": str(tmp_path / "Downloads" / "report.pdf")}
    assert second["path"] == str(tmp_path / "Downloads" / "report-1.pdf")
    assert (tmp_path / "Downloads" / "report-1.pdf").read_bytes() == b"%PDF-fake"
    assert service.save_attachment("INBOX", 1, 1)["ok"] is False


def test_two_attachments_with_one_name_are_both_saved_and_an_attached_email_is_saved_whole(tmp_path):
    server, service = _service(tmp_path)
    message = mail("Scans", attachment="scan.pdf")
    message.add_attachment(b"second scan", maintype="application", subtype="pdf", filename="scan.pdf")
    message.add_attachment(mail("The original", body="Inner text."), filename="original.eml")
    server.add("INBOX", message)
    paths = [service.save_attachment("INBOX", 1, index)["path"] for index in (0, 1, 2)]
    assert [p.rsplit("/", 1)[1] for p in paths] == ["scan.pdf", "scan-1.pdf", "original.eml"]
    assert (tmp_path / "Downloads" / "scan-1.pdf").read_bytes() == b"second scan"
    assert b"Inner text." in (tmp_path / "Downloads" / "original.eml").read_bytes()


def test_a_file_that_cannot_be_written_is_reported_and_a_very_long_name_is_shortened(tmp_path):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("Long", attachment="x" * 300 + ".pdf"))
    saved = service.save_attachment("INBOX", 1, 0)
    assert saved["ok"] and saved["path"].endswith("x" * 120 + ".pdf")
    (tmp_path / "blocked").write_text("a file where the folder should be")
    service._downloads = tmp_path / "blocked"
    refused = service.save_attachment("INBOX", 1, 0)
    assert refused["ok"] is False and refused["error"].startswith("Could not save the file")


def test_disconnecting_empties_the_cache(tmp_path):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("Private"))
    _synced(service)
    service.forget()
    assert service.threads()["threads"] == []
    assert service.status()["last_sync"] == 0


def test_disconnecting_during_a_pass_leaves_no_mail_behind(tmp_path, monkeypatch):
    import threading

    server, service = _service(tmp_path)
    for n in range(3):
        server.add("INBOX", mail(f"Mail {n}"))
    reading, release = threading.Event(), threading.Event()
    real_headers = service._conn.headers

    def slow_headers(folder, uids):
        reading.set()
        release.wait(5)
        return real_headers(folder, uids)

    monkeypatch.setattr(service._conn, "headers", slow_headers)
    service.sync()
    assert reading.wait(5)
    service._secrets.delete("email:default")
    threading.Timer(0.05, release.set).start()
    service.forget()
    assert service._store.uids(ADDRESS, "INBOX") == set()
    assert service._store.get("last_error") == ""
    assert service.status()["syncing"] is False


def test_a_pass_reading_the_mailbox_while_an_archive_is_on_its_way_does_not_bring_it_back(
    tmp_path, monkeypatch
):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("Archived"))
    (row,) = _synced(service)
    real_move = service._conn.move

    def move_while_a_pass_reads(folder, uids, role):
        # The pass begins after the cache was changed and reads the server before the move.
        # Its write is refused, which ends it.
        with pytest.raises(_Stopped):
            service._sync.run_once()
        return real_move(folder, uids, role)

    monkeypatch.setattr(service._conn, "move", move_while_a_pass_reads)
    monkeypatch.setattr(service._sync, "request", lambda: True)
    assert service.archive(row["key"]) == {"ok": True}
    assert service.threads()["threads"] == []


def test_a_file_name_cannot_hide_what_kind_of_file_it_is(tmp_path):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("Trick", attachment="invoice\u202efdp.exe"))
    saved = service.save_attachment("INBOX", 1, 0)
    assert saved["path"].endswith("invoicefdp.exe")
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_mail_service.py -q`
Expected: an error collecting the file, `ModuleNotFoundError: No module named 'coworker.mail.service'`.

- [ ] **Step 3: Write `coworker/mail/service.py`**

```python
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
        account = self._account()
        row = self._store.row(account, folder, uid)
        rendered = self._store.body(account, folder, uid, time.time()) if row else None
        if rendered is None:
            msg = self._conn.message(folder, uid)
            if msg is None:
                return {"ok": False, "error": _GONE}
            rendered = render_message(msg)
            if row:
                self._store.put_body(account, folder, uid, rendered, time.time())
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
        uids = [row["uid"] for row in rows]
        try:
            with self._store.changing():
                self._store.remove(account, INBOX, uids)
                try:
                    self._conn.move(INBOX, uids, role)
                except MailError:
                    self._store.add(rows)
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
```

Notes for the implementer:

- `status()` must never touch the mail server. The screen calls it every two seconds.
- Every change ends with `self._sync.request()`, in a `finally`, whether it worked or not. A refused move has put its rows back; the pass confirms what the server really holds.
- An attachment is saved by its place in the list, because two can share a name. The list comes from `render.attachments` in both `render.py` and here, so the places agree.
- `forget()` is called after the Email secret has been deleted (Task 10), so the pass it stops cannot log in again.
- Saving an attachment writes to `~/Downloads`, as `export_agent_system` does. It is the user's own click on a file they can see named, so it is not an approval-gated action; the agent's `email_download_attachment` is unchanged and still is.
- Do not route any of this through `risk.py`. The module docstring says why, and the spec records it as decision 4.

- [ ] **Step 4: Run the tests to see them pass**

Run: `.venv/bin/pytest tests/test_mail_service.py -q`
Expected: PASS, 21 tests.

- [ ] **Step 5: Commit**

```bash
.venv/bin/ruff check coworker tests scripts && .venv/bin/pytest -q
git add coworker/mail/service.py tests/test_mail_service.py
git commit -m "Add the Mail facade: list, open, search, mark, archive, bin, save an attachment"
```

## Chunk 7: The routes, and the screen's calls

After Task 10 the backend is complete for Plan A. Nothing is visible yet.

### Task 10: The manager holds Mail, and the routes reach it

**Files:**
- Modify: `coworker/server/manager.py` (three places: after `self.task_store = …` in `__init__`; `disconnect_connector`; `aclose`)
- Modify: `coworker/server/app.py` (a new block above `# -- apps (Mimi-written HTML tools)`)
- Test: `tests/test_mail_routes.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_mail_routes.py`:

```python
"""Mail over REST, the way the screen reaches it."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient
from helpers import CapturingProvider
from mail_fakes import ADDRESS, PASSWORD, FakeMailServer, mail

from coworker.mail.service import MailService
from coworker.server import SessionManager, create_app


def _client(tmp_path, server):
    manager = SessionManager(workspace=tmp_path, provider=CapturingProvider())
    manager.secrets.put(
        "email:default",
        {
            "address": ADDRESS,
            "app_password": PASSWORD,
            "imap_host": "mail.example.com",
            "smtp_host": "mail.example.com",
        },
    )
    manager.mail.close()
    manager.mail = MailService(
        manager.secrets,
        tmp_path / "mail-test.db",
        imap_factory=server.connect,
        downloads=tmp_path / "Downloads",
    )
    return TestClient(create_app(manager))


def _sync(client):
    assert client.post("/v1/mail/sync").json()["ok"]
    deadline = time.time() + 5
    while client.get("/v1/mail/status").json()["syncing"] and time.time() < deadline:
        time.sleep(0.01)
    status = client.get("/v1/mail/status").json()
    assert not status["syncing"] and status["last_error"] == ""
    return status


def test_the_screen_can_sync_list_open_and_mark_a_conversation(tmp_path):
    server = FakeMailServer()
    server.add("INBOX", mail("Plan", html="<p>Shall we?</p>", attachment="plan.pdf"))
    client = _client(tmp_path, server)

    before = client.get("/v1/mail/status").json()
    assert (before["connected"], before["address"], before["revision"]) == (True, ADDRESS, 0)
    after = _sync(client)
    assert after["revision"] > before["revision"]
    assert (after["can_archive"], after["can_bin"]) == (True, True)

    (row,) = client.get("/v1/mail/threads").json()["threads"]
    assert (row["subject"], row["unread"]) == ("Plan", True)
    thread = client.get(f"/v1/mail/threads/{row['key']}").json()
    assert thread["messages"][0]["uid"] == 1

    message = client.get("/v1/mail/message", params={"folder": "INBOX", "uid": 1}).json()
    assert message["ok"] and message["html"].startswith("<p>Shall we?</p>")

    assert client.post(f"/v1/mail/threads/{row['key']}/read", json={"read": True}).json()["ok"]
    assert client.get("/v1/mail/threads").json()["threads"][0]["unread"] is False
    assert server.flags("INBOX", 1) == {"\\Seen"}

    saved = client.post(
        "/v1/mail/attachments/save", json={"folder": "INBOX", "uid": 1, "index": 0}
    ).json()
    assert saved == {"ok": True, "path": str(tmp_path / "Downloads" / "plan.pdf")}


def test_archive_and_bin_move_the_conversation_and_the_list_follows(tmp_path):
    server = FakeMailServer()
    server.add("INBOX", mail("To archive", days_ago=2))
    server.add("INBOX", mail("To bin", days_ago=1))
    client = _client(tmp_path, server)
    _sync(client)
    keys = {t["subject"]: t["key"] for t in client.get("/v1/mail/threads").json()["threads"]}

    assert client.post(f"/v1/mail/threads/{keys['To archive']}/archive").json() == {"ok": True}
    assert client.post(f"/v1/mail/threads/{keys['To bin']}/bin").json() == {"ok": True}
    assert client.get("/v1/mail/threads").json()["threads"] == []
    assert server.subjects("Archive") == ["To archive"]
    assert server.subjects("Trash") == ["To bin"]
    assert client.post(f"/v1/mail/threads/{keys['To bin']}/bin").json()["ok"] is False


def test_search_finds_mail_outside_the_inbox_and_a_result_opens_and_is_marked_read(tmp_path):
    server = FakeMailServer()
    uid = server.add("Archive", mail("Invoice January", days_ago=300, body="Paid in full."))
    client = _client(tmp_path, server)

    (result,) = client.get("/v1/mail/search", params={"q": "invoice"}).json()["results"]
    assert (result["subject"], result["folder"], result["uid"]) == ("Invoice January", "Archive", uid)
    opened = client.get("/v1/mail/message", params={"folder": "Archive", "uid": uid}).json()
    assert "Paid in full." in opened["html"]
    assert client.post("/v1/mail/message/read", json={"folder": "Archive", "uid": uid}).json() == {
        "ok": True
    }
    assert server.flags("Archive", uid) == {"\\Seen"}


def test_a_request_that_names_no_message_is_refused_plainly(tmp_path):
    client = _client(tmp_path, FakeMailServer())
    assert client.post("/v1/mail/message/read", json={}).json()["ok"] is False
    assert client.post("/v1/mail/attachments/save", json={"folder": "INBOX"}).json()["ok"] is False
    assert client.get("/v1/mail/threads/0000000000000000").json()["ok"] is False


def test_disconnecting_the_email_connector_empties_mail(tmp_path):
    server = FakeMailServer()
    server.add("INBOX", mail("Private"))
    client = _client(tmp_path, server)
    _sync(client)
    assert client.get("/v1/mail/threads").json()["threads"]

    client.post("/v1/connectors/email/disconnect")
    status = client.get("/v1/mail/status").json()
    assert (status["connected"], status["address"], status["last_sync"]) == (False, "", 0)
    assert client.get("/v1/mail/threads").json()["threads"] == []
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/bin/pytest tests/test_mail_routes.py -q`
Expected: FAIL, `AttributeError: 'SessionManager' object has no attribute 'mail'`.

- [ ] **Step 3: Give the manager its Mail**

In `coworker/server/manager.py`, directly after the line `self.task_store = TaskStore(base / "automation.db")` in `__init__`, add:

```python
        # Mail: the connection and cache behind the Mail section (coworker/mail/).
        from ..mail.service import MailService

        self.mail = MailService(self.secrets, base / "mail.db")
```

Replace the last line of `disconnect_connector`, `return disconnect_connector(self.secrets, name)`, with:

```python
        result = disconnect_connector(self.secrets, name)
        if name == "email":
            # Mail must not keep a logged-in connection, or anyone's mail on disk, for a
            # mailbox the user has disconnected.
            self.mail.forget()
        return result
```

In `aclose`, after `self.audit_store.close()`, add:

```python
        self.mail.close()
```

- [ ] **Step 4: Add the routes**

In `coworker/server/app.py`, directly above the line `# -- apps (Mimi-written HTML tools) ---…`, add:

```python
    # -- mail (the Mail section) -----------------------------------------------------
    # Plain REST: nothing here goes over the websocket. Each route is one call into
    # manager.mail, which answers a failure as {ok: False, error} in plain language.
    @app.get("/v1/mail/status")
    def mail_status() -> dict[str, Any]:
        return manager.mail.status()

    @app.post("/v1/mail/sync")
    def mail_sync() -> dict[str, Any]:
        return manager.mail.sync()

    @app.get("/v1/mail/threads")
    def mail_threads() -> dict[str, Any]:
        return manager.mail.threads()

    @app.get("/v1/mail/threads/{key}")
    def mail_thread(key: str) -> dict[str, Any]:
        return manager.mail.thread(key)

    @app.post("/v1/mail/threads/{key}/read")
    def mail_thread_read(key: str, body: dict) -> dict[str, Any]:
        return manager.mail.mark_thread(key, bool((body or {}).get("read", True)))

    @app.post("/v1/mail/threads/{key}/archive")
    def mail_thread_archive(key: str) -> dict[str, Any]:
        return manager.mail.archive(key)

    @app.post("/v1/mail/threads/{key}/bin")
    def mail_thread_bin(key: str) -> dict[str, Any]:
        return manager.mail.bin(key)

    @app.get("/v1/mail/message")
    def mail_message(folder: str = "", uid: int = 0) -> dict[str, Any]:
        return manager.mail.message(folder, uid)

    @app.post("/v1/mail/message/read")
    def mail_message_read(body: dict) -> dict[str, Any]:
        body = body or {}
        return manager.mail.mark_message_read(str(body.get("folder") or ""), body.get("uid") or 0)

    @app.get("/v1/mail/search")
    def mail_search(q: str = "") -> dict[str, Any]:
        return manager.mail.search(q)

    @app.post("/v1/mail/attachments/save")
    def mail_attachment_save(body: dict) -> dict[str, Any]:
        body = body or {}
        return manager.mail.save_attachment(
            str(body.get("folder") or ""), body.get("uid") or 0, body.get("index", -1)
        )
```

Nothing is added to the websocket validator: Mail sends no websocket frame.

- [ ] **Step 5: Run the tests to see them pass**

Run: `.venv/bin/pytest tests/test_mail_routes.py -q`
Expected: PASS, 5 tests.

- [ ] **Step 6: Run the Python gates**

Run: `.venv/bin/ruff check coworker tests scripts && .venv/bin/pytest -q`
Expected: `All checks passed!`, and pytest green. The whole suite matters here: every test that builds a `SessionManager` now also builds a `MailService`.

- [ ] **Step 7: Commit**

```bash
git add coworker/server/manager.py coworker/server/app.py tests/test_mail_routes.py
git commit -m "Reach Mail over REST, and empty it when the Email connector is disconnected"
```

### Task 11: The screen's calls

`api.ts` is the only file that talks to the sidecar, so Mail's types and calls go there. No test of its own: the components that use them are tested in the next chunk, and the compiler checks the shapes.

**Files:**
- Modify: `surfaces/gui/src/api.ts` (append at the end)

- [ ] **Step 1: Append the Mail block to `api.ts`**

```ts

// -- Mail (the Mail section) ---------------------------------------------------------------
// Every Mail call answers `{ ok: false, error }` in plain language when it cannot do what
// was asked, so the screen shows the reason as it is.

export interface MailStatus {
  ok: boolean;
  connected: boolean;
  address: string;
  syncing: boolean;
  /** Moves whenever the list may have changed; the screen reloads when it differs. */
  revision: number;
  last_sync: number;
  last_error: string;
  can_archive: boolean;
  can_bin: boolean;
}

export interface MailThreadRow {
  key: string;
  subject: string;
  sender: string;
  date: number;
  unread: boolean;
  count: number;
  has_attachments: boolean;
}

export interface MailEnvelope {
  folder: string;
  uid: number;
  message_id: string;
  from: string;
  to: string;
  cc: string;
  subject: string;
  date: number;
  unread: boolean;
  has_attachments: boolean;
}

export interface MailThread {
  ok: boolean;
  error?: string;
  key: string;
  subject: string;
  in_inbox: boolean;
  messages: MailEnvelope[];
}

export interface MailAttachment {
  filename: string;
  content_type: string;
  size: number;
}

export interface MailMessage extends MailEnvelope {
  ok: boolean;
  error?: string;
  thread_key: string;
  html: string;
  text: string;
  attachments: MailAttachment[];
}

export interface MailReply {
  ok: boolean;
  error?: string;
}

const mailUrl = (path: string) => `${httpBase()}/v1/mail${path}`;
const mailThreadUrl = (key: string, action = "") =>
  mailUrl(`/threads/${encodeURIComponent(key)}${action}`);

async function mailPost<T = MailReply>(url: string, body: unknown = {}): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

export async function getMailStatus(): Promise<MailStatus> {
  return (await fetch(mailUrl("/status"))).json();
}

/** Start a sync pass. Returns at once; `getMailStatus().syncing` says when it has ended. */
export function syncMail(): Promise<MailReply> {
  return mailPost(mailUrl("/sync"));
}

export async function getMailThreads(): Promise<MailThreadRow[]> {
  return (await (await fetch(mailUrl("/threads"))).json()).threads ?? [];
}

export async function getMailThread(key: string): Promise<MailThread> {
  return (await fetch(mailThreadUrl(key))).json();
}

/** One message with its body. Also how a search result is opened. */
export async function getMailMessage(folder: string, uid: number): Promise<MailMessage> {
  const query = `folder=${encodeURIComponent(folder)}&uid=${uid}`;
  return (await fetch(mailUrl(`/message?${query}`))).json();
}

export function markMailThread(key: string, read: boolean): Promise<MailReply> {
  return mailPost(mailThreadUrl(key, "/read"), { read });
}

export function markMailMessageRead(folder: string, uid: number): Promise<MailReply> {
  return mailPost(mailUrl("/message/read"), { folder, uid });
}

export function archiveMailThread(key: string): Promise<MailReply> {
  return mailPost(mailThreadUrl(key, "/archive"));
}

export function binMailThread(key: string): Promise<MailReply> {
  return mailPost(mailThreadUrl(key, "/bin"));
}

export async function searchMail(q: string): Promise<MailReply & { results?: MailEnvelope[] }> {
  return (await fetch(mailUrl(`/search?q=${encodeURIComponent(q)}`))).json();
}

/** Save the attachment at `index` in the message's list into Downloads. By place, not by
 *  name, because two attachments can share a name. The reply carries the saved path. */
export function saveMailAttachment(
  folder: string,
  uid: number,
  index: number,
): Promise<MailReply & { path?: string }> {
  return mailPost(mailUrl("/attachments/save"), { folder, uid, index });
}
```

The module-local `fetch` at the top of `api.ts` adds the launch token, so these calls need nothing extra. The search words and a folder name travel in the query string of a loopback request to the app's own sidecar, as the spec's routes say.

- [ ] **Step 2: Check it compiles and lints**

Run (in `surfaces/gui`): `npx tsc --noEmit && npx eslint src/api.ts`
Expected: no output from either.

- [ ] **Step 3: Commit**

```bash
git add surfaces/gui/src/api.ts
git commit -m "Add the Mail calls to the one file that talks to the sidecar"
```

## Chunk 8: The frame and the list

The first two of four components under `surfaces/gui/src/components/mail/`. All commands in this chunk run in `surfaces/gui`.

### Task 12: The frame an email is shown in

`MailFrame` is the only component that touches an email's HTML. It hands the frame the disarmed document, keeps it hidden until it has been checked from outside, and then asks it four times a second how tall it is and which link has focus. `linkTarget`, in the same file, decides how a link's address is shown and whether it may be opened.

**Files:**
- Create: `surfaces/gui/src/components/mail/MailFrame.tsx`
- Test: `surfaces/gui/src/components/mail/MailFrame.test.tsx`

- [ ] **Step 1: Write the failing tests**

```tsx
/** The frame an email is shown in: what it is given, and what it is never given. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

vi.mock("./disarm", async (original) => {
  const real = await original<typeof import("./disarm")>();
  return {
    ...real,
    // Stands in for an email that cannot be made inert.
    disarmEmail: (html: string, opts?: { images?: boolean }) =>
      html.includes("CANNOT-BE-MADE-SAFE") ? null : real.disarmEmail(html, opts),
  };
});

import { linkTarget, MailFrame } from "./MailFrame";

afterEach(cleanup);

const frame = () => screen.getByTestId("mail-frame") as HTMLIFrameElement;

describe("MailFrame", () => {
  it("turns scripts off in the frame and hands it only the disarmed email", () => {
    render(<MailFrame html='<p>Hi <a href="https://example.com/x">link</a></p>' text="Hi link" />);
    expect(frame().getAttribute("sandbox")).toBe("allow-same-origin");
    const given = frame().getAttribute("srcdoc")!;
    expect(given).toContain("Content-Security-Policy");
    expect(given).toContain('data-mail-href="https://example.com/x"');
    expect(given).not.toMatch(/\shref=/);
  });

  it("keeps remote images out until Show images is pressed", () => {
    render(<MailFrame html='<p><img src="https://x.example/logo.png"></p>' text="" />);
    expect(frame().getAttribute("srcdoc")).toContain("img-src data:;");
    fireEvent.click(screen.getByTestId("mail-show-images"));
    expect(frame().getAttribute("srcdoc")).toContain("img-src data: https:;");
    expect(screen.queryByTestId("mail-show-images")).toBeNull();
  });

  it("does not offer Show images for an email with nothing remote to show", () => {
    render(<MailFrame html='<p><img src="data:image/png;base64,AAAA"></p>' text="" />);
    expect(screen.queryByTestId("mail-show-images")).toBeNull();
  });

  it("shows the plain text, and no frame, for an email that cannot be made inert", () => {
    render(<MailFrame html="<p>CANNOT-BE-MADE-SAFE</p>" text="Only the words." />);
    expect(screen.queryByTestId("mail-frame")).toBeNull();
    expect(screen.getByTestId("mail-plain").textContent).toContain("Only the words.");
  });
});

describe("linkTarget", () => {
  it("shows a web address the way the browser reads it, and lets it be opened", () => {
    expect(linkTarget("HTTPS://Example.com/a b")).toEqual({ shown: "https://example.com/a%20b", openable: true });
    expect(linkTarget("mailto:ana@example.com").openable).toBe(true);
  });

  it("shows a look-alike host for what it is", () => {
    // The first letter is the Cyrillic letter that looks like a Latin a.
    expect(linkTarget("https://\u0430pple.com/").shown).toBe("https://xn--pple-43d.com/");
  });

  it("shows anything else without offering to open it, and without hidden marks", () => {
    expect(linkTarget("javascript:alert(1)")).toEqual({ shown: "javascript:alert(1)", openable: false });
    expect(linkTarget("#top")).toEqual({ shown: "#top", openable: false });
    expect(linkTarget("file\u202egpj.exe")).toEqual({ shown: "filegpj.exe", openable: false });
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `npx vitest run src/components/mail/MailFrame.test.tsx`
Expected: FAIL, `Failed to resolve import "./MailFrame"`.

- [ ] **Step 3: Write `MailFrame.tsx`**

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { useT } from "../../i18n";
import { openExternal } from "../../tauri";
import { contentHeight, disarmEmail, focusedAddress, isParsed, releaseFocus, stillArmed } from "./disarm";

const MAX_HEIGHT = 20_000;
// How many times the frame may grow to fit its email. An email sized to its own window
// ("min-height: 100vh" plus padding) is a little taller every time the frame is made to
// fit it; after this many rounds the frame stops following and scrolls instead.
const MAX_GROWTHS = 12;
const REMOTE_IMAGE = /<img[^>]+src\s*=\s*["']?https?:|url\(\s*["']?https?:/i;
const HIDDEN_MARKS = /[\u0000-\u001f\u007f\u200e\u200f\u202a-\u202e\u2066-\u2069]/g;

/** How a link's address is shown, and whether the app will hand it to the browser. An
 *  address is shown as the browser itself reads it, so characters that reorder text or
 *  look like other letters cannot make it pass for another site. Only web and mail
 *  addresses can be opened; anything else is shown, with no button. */
export function linkTarget(address: string): { shown: string; openable: boolean } {
  try {
    const url = new URL(address);
    if (["http:", "https:", "mailto:"].includes(url.protocol)) return { shown: url.href, openable: true };
  } catch {
    // Not a full address (a bare "#top", say): shown as written, never opened.
  }
  return { shown: address.replace(HIDDEN_MARKS, ""), openable: false };
}

/** One email, shown as it was sent, in a frame where nothing can run, load or navigate. */
export function MailFrame({ html, text }: { html: string; text: string }) {
  const t = useT();
  const frame = useRef<HTMLIFrameElement>(null);
  const growths = useRef(0);
  const tallest = useRef(80);
  const [images, setImages] = useState(false);
  const safe = useMemo(() => disarmEmail(html, { images }), [html, images]);
  // Which document passed, or failed, the look from outside. Held as the document itself,
  // so a new email, or Show images, starts unchecked again.
  const [checked, setChecked] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [height, setHeight] = useState(80);
  const [link, setLink] = useState("");
  const ready = safe !== null && checked === safe;

  useEffect(() => {
    if (safe === null) return;
    growths.current = 0;
    // Scripts are off inside the frame, so a listener added there never fires. The app
    // asks from outside instead, four times a second.
    const timer = window.setInterval(() => {
      const doc = frame.current?.contentDocument;
      if (!doc || !isParsed(doc)) return;
      // Looked at as soon as it has been read, not when its last image arrives: with Show
      // images on, one slow picture would otherwise keep the whole email hidden.
      if (stillArmed(doc)) return setRefused(safe);
      setChecked(safe);
      const wanted = Math.min(MAX_HEIGHT, Math.max(80, contentHeight(doc)));
      if (wanted > tallest.current && growths.current < MAX_GROWTHS) {
        growths.current += 1;
        tallest.current = wanted;
        setHeight(wanted);
      }
      setLink(focusedAddress(doc));
    }, 250);
    return () => window.clearInterval(timer);
  }, [safe]);

  if (safe === null || refused === safe) {
    return (
      <div data-testid="mail-plain">
        <p className="mail-note">{t("This message could not be shown safely, so here is its text.")}</p>
        <pre className="mail-plain">{text}</pre>
      </div>
    );
  }

  const target = ready && link ? linkTarget(link) : null;
  return (
    <div className="mail-frame-wrap">
      {target && (
        <div className="mail-link-card" role="status" data-testid="mail-link-card">
          <span className="mail-link-label">{t("This link goes to")}</span>
          <span className="mail-link-address" data-testid="mail-link-address">{target.shown}</span>
          {target.openable && (
            <button className="btn sm" data-testid="mail-link-open" onClick={() => openExternal(target.shown)}>
              {t("Open in browser")}
            </button>
          )}
          <button
            className="btn sm"
            onClick={() => {
              // Letting go of the link is what closes the card, so clicking the same link
              // again shows it again.
              const doc = frame.current?.contentDocument;
              if (doc) releaseFocus(doc);
              setLink("");
            }}
          >
            {t("Close")}
          </button>
        </div>
      )}
      {!images && REMOTE_IMAGE.test(html) && (
        <button className="btn sm mail-show-images" data-testid="mail-show-images" onClick={() => setImages(true)}>
          {t("Show images")}
        </button>
      )}
      <iframe
        // A new frame for each document, so a check can never vouch for the wrong one.
        key={safe}
        ref={frame}
        className="mail-frame"
        data-testid="mail-frame"
        title={t("Message")}
        // These two go together and must never be changed apart. `allow-same-origin` is
        // what lets the app read the frame from outside; it is safe only because, with no
        // `allow-scripts`, nothing inside the frame can run to use it.
        sandbox="allow-same-origin"
        srcDoc={safe}
        // Hidden until it has been looked at from outside, so nothing can be clicked first.
        style={{ height, visibility: ready ? "visible" : "hidden" }}
      />
    </div>
  );
}
```

Notes for the implementer:

- Never read `frame.current.contentDocument.something` here. Use the readers `disarm.ts` exports; Task 2 explains why.
- `sandbox` must stay exactly `"allow-same-origin"`. Adding `allow-scripts` to a frame that also has `allow-same-origin` would let an email run with the app's own reach.
- The email is checked as soon as it has been read (`isParsed`), not on the frame's `load` event. `load` waits for every image, so with Show images on, one slow picture would keep the whole email hidden.
- The frame follows the email's height upward only, and only `MAX_GROWTHS` times. An email sized to its own window grows a little each time the frame is made to fit it; without the limit the frame would creep to its maximum.
- The address card shows `new URL(address).href`, which is the address as the browser reads it, so a look-alike host appears in its plain form. Only `http`, `https` and `mailto` get an Open button.
- The unit tests cannot show the frame's contents loading: that, the address card and Show images loading real images are covered by the browser tests in the last chunk.

- [ ] **Step 4: Run the tests to see them pass**

Run: `npx vitest run src/components/mail/MailFrame.test.tsx`
Expected: PASS, 7 tests.

- [ ] **Step 5: Only if Task 2, Step 8 found that a click does not give focus**

Skip this step if the probe showed the focused element's address. Otherwise links cannot open through focus, and the message's links are listed beneath it instead. `linkAddresses` is already in `disarm.ts`, with its test. The change below to `MailFrame.tsx` is the one piece of code in this plan that was not run while the plan was written, so run the GUI gates after it.

In `MailFrame.tsx`: import `linkAddresses` in place of `focusedAddress` and `releaseFocus`; replace the `link` state with `const [links, setLinks] = useState<string[]>([]);`; in the timer replace `setLink(focusedAddress(doc));` with

```ts
      const now = linkAddresses(doc);
      setLinks((before) => (before.join("\n") === now.join("\n") ? before : now));
```

remove the `target` constant and the whole `mail-link-card` block, and add this directly after the `<iframe … />`:

```tsx
      {ready && links.length > 0 && (
        <ul className="mail-links" data-testid="mail-links">
          {links.map(linkTarget).map((target) => (
            <li key={target.shown}>
              <span className="mail-link-address">{target.shown}</span>
              {target.openable && (
                <button className="btn sm" onClick={() => openExternal(target.shown)}>{t("Open in browser")}</button>
              )}
            </li>
          ))}
        </ul>
      )}
```

Append to `src/styles.css`:

```css
.mail-links { list-style: none; margin: 0; padding: 8px 14px; display: flex; flex-direction: column; gap: 6px; border-top: 1px solid var(--line); }
.mail-links li { display: flex; align-items: center; gap: 8px; }
```

Run `npx tsc --noEmit && npm run lint && npx vitest run src/components/mail`. In the last chunk, the tests that look for `mail-link-address` inside `mail-link-card` must then look for the address inside `mail-links`, and the Close step goes. Add `src/styles.css` to this task's commit, and record the change in the spec's Probe results.

- [ ] **Step 6: Commit**

```bash
npx tsc --noEmit && npx eslint src/components/mail
git add surfaces/gui/src/components/mail/MailFrame.tsx surfaces/gui/src/components/mail/MailFrame.test.tsx
git commit -m "Show an email in a frame where nothing can run, checked from outside before it is seen"
```

### Task 13: The list

**Files:**
- Create: `surfaces/gui/src/components/mail/MailList.tsx`
- Test: `surfaces/gui/src/components/mail/MailList.test.tsx`

- [ ] **Step 1: Write the failing tests**

```tsx
/** The rows of the Mail list. */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { formatMailDate, MailList, senderName, type MailRow } from "./MailList";

afterEach(cleanup);

const ROWS: MailRow[] = [
  { id: "k1", sender: "Ana Lopez <ana@example.com>", subject: "Plan for Friday", date: 0, unread: true, count: 3 },
  { id: "k2", sender: "billing@example.com", subject: "", date: 0, unread: false, error: "this mailbox cannot move mail" },
];

describe("MailList", () => {
  it("shows who it is from, the subject, and which rows are unread or selected", () => {
    render(<MailList rows={ROWS} selected="k2" onOpen={() => {}} empty="No mail here yet." />);
    const [first, second] = screen.getAllByTestId("mail-row");
    expect(first.textContent).toContain("Ana Lopez");
    expect(first.textContent).not.toContain("ana@example.com");
    expect(first.textContent).toContain("Plan for Friday");
    expect(first.textContent).toContain("3");
    expect(first.className).toContain("unread");
    expect(first.textContent).toContain("Unread");
    expect(second.textContent).toContain("billing@example.com");
    expect(second.className).not.toContain("unread");
    expect(second.getAttribute("aria-current")).toBe("true");
  });

  it("shows on the row why a change to it did not go through", () => {
    render(<MailList rows={ROWS} selected="" onOpen={() => {}} empty="" />);
    expect(screen.getByRole("alert").textContent).toBe("this mailbox cannot move mail");
  });

  it("opens the row that is clicked", () => {
    const onOpen = vi.fn();
    render(<MailList rows={ROWS} selected="" onOpen={onOpen} empty="" />);
    fireEvent.click(screen.getAllByTestId("mail-row")[0]);
    expect(onOpen).toHaveBeenCalledWith("k1");
  });

  it("says so when there is nothing to list", () => {
    render(<MailList rows={[]} selected="" onOpen={() => {}} empty="No mail here yet." />);
    expect(screen.getByTestId("mail-list-empty").textContent).toBe("No mail here yet.");
  });
});

describe("senderName", () => {
  it("is the name when there is one, and the address when there is not", () => {
    expect(senderName('"Ana Lopez" <ana@example.com>')).toBe("Ana Lopez");
    expect(senderName("Ana <ana@example.com>")).toBe("Ana");
    expect(senderName("<ana@example.com>")).toBe("ana@example.com");
    expect(senderName("ana@example.com")).toBe("ana@example.com");
  });
});

describe("formatMailDate", () => {
  it("is a time for today, a day for this year, and empty for no date", () => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 9, 5).getTime() / 1000;
    expect(formatMailDate(today)).toMatch(/9.05/);
    expect(formatMailDate(new Date(2001, 2, 4).getTime() / 1000)).toContain("2001");
    expect(formatMailDate(0)).toBe("");
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `npx vitest run src/components/mail/MailList.test.tsx`
Expected: FAIL, `Failed to resolve import "./MailList"`.

- [ ] **Step 3: Write `MailList.tsx`**

```tsx
import { useT } from "../../i18n";
import { Icon } from "../Icon";

/** One row of the list: a conversation, or a search result. */
export interface MailRow {
  id: string;
  sender: string;
  subject: string;
  date: number;
  unread: boolean;
  count?: number;
  has_attachments?: boolean;
  /** Where a search result sits, shown because it may not be the inbox. */
  folder?: string;
  /** Why the last archive, bin or mark on this row did not go through. */
  error?: string;
}

/** "Ana Lopez <ana@example.com>" as "Ana Lopez"; a bare address stays as it is. */
export function senderName(from: string): string {
  const named = from.match(/^\s*"?([^"<]*?)"?\s*<[^>]*>\s*$/);
  return (named && named[1].trim()) || from.replace(/[<>]/g, "").trim();
}

/** Seconds since 1970 as a time today, a day this year, or a full date. */
export function formatMailDate(seconds: number, long = false): string {
  if (!seconds) return "";
  const date = new Date(seconds * 1000);
  const now = new Date();
  if (long) return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  const sameYear = date.getFullYear() === now.getFullYear();
  return date.toLocaleDateString(
    undefined,
    sameYear ? { month: "short", day: "numeric" } : { year: "numeric", month: "short", day: "numeric" },
  );
}

export function MailList({
  rows,
  selected,
  onOpen,
  empty,
}: {
  rows: MailRow[];
  selected: string;
  onOpen: (id: string) => void;
  empty: string;
}) {
  const t = useT();
  if (!rows.length) {
    return <div className="mail-list-empty" data-testid="mail-list-empty">{empty}</div>;
  }
  return (
    <ul className="mail-list" data-testid="mail-list">
      {rows.map((row) => (
        <li key={row.id}>
          <button
            className={"mail-row" + (row.unread ? " unread" : "") + (row.id === selected ? " selected" : "")}
            data-testid="mail-row"
            aria-current={row.id === selected ? "true" : undefined}
            onClick={() => onOpen(row.id)}
          >
            <span className="mail-row-top">
              <span className="mail-row-dot" aria-hidden="true" />
              {row.unread ? <span className="sr-only">{t("Unread")}</span> : null}
              <span className="mail-row-sender">{senderName(row.sender)}</span>
              {row.count && row.count > 1 ? <span className="mail-row-count">{row.count}</span> : null}
              {row.has_attachments ? (
                <span className="mail-row-clip" title={t("Has an attachment")}>
                  <Icon name="file" size={12} />
                  <span className="sr-only">{t("Has an attachment")}</span>
                </span>
              ) : null}
              <span className="mail-row-date">{formatMailDate(row.date)}</span>
            </span>
            <span className="mail-row-subject">{row.subject || "—"}</span>
            {row.folder ? <span className="mail-row-folder">{row.folder}</span> : null}
            {row.error ? <span className="mail-row-error" role="alert">{row.error}</span> : null}
          </button>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `npx vitest run src/components/mail/MailList.test.tsx`
Expected: PASS, 6 tests.

- [ ] **Step 5: Commit**

```bash
npx tsc --noEmit && npx eslint src/components/mail
git add surfaces/gui/src/components/mail/MailList.tsx surfaces/gui/src/components/mail/MailList.test.tsx
git commit -m "List mail as rows that say who, what, when, and whether it is unread"
```

## Chunk 9: The reader, the section, and the navigation

The other two components, then the navigation row that makes Mail visible. All commands in this chunk run in `surfaces/gui`.

### Task 14: The reader and the section

`MailReader` shows a conversation (or one search result) and its actions. `MailView` is the section: it asks for status, starts sync passes, holds what is open, and makes changes to the list at once. They are written together because `MailView`'s tests drive both.

**Files:**
- Create: `surfaces/gui/src/components/mail/MailReader.tsx`
- Create: `surfaces/gui/src/components/mail/MailView.tsx`
- Modify: `surfaces/gui/src/styles.css` (append), `surfaces/gui/src/i18n.tsx` (new rows at the end of `D`)
- Test: `surfaces/gui/src/components/mail/MailView.test.tsx`

- [ ] **Step 1: Write the failing tests**

`MailView.test.tsx`:

```tsx
/** The Mail section: what it shows when nothing is connected, the list, and its actions. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const STATUS = {
  ok: true, connected: true, address: "me@example.com", syncing: false, revision: 1,
  last_sync: 0, last_error: "", can_archive: true, can_bin: true,
};
const ROW = { key: "k1", subject: "Plan for Friday", sender: "Ana <ana@example.com>", date: 0, unread: false, count: 1, has_attachments: false };
const ENVELOPE = {
  folder: "INBOX", uid: 1, message_id: "<1@x>", from: "Ana <ana@example.com>", to: "me@example.com",
  cc: "", subject: "Plan for Friday", date: 0, unread: false, has_attachments: false,
};

const api = vi.hoisted(() => ({
  getMailStatus: vi.fn(),
  getMailThreads: vi.fn(),
  syncMail: vi.fn(),
  archiveMailThread: vi.fn(),
  binMailThread: vi.fn(),
  markMailThread: vi.fn(),
  searchMail: vi.fn(),
  getMailThread: vi.fn(),
  getMailMessage: vi.fn(),
  markMailMessageRead: vi.fn(),
  saveMailAttachment: vi.fn(),
}));
vi.mock("../../api", () => api);

import { MailView } from "./MailView";

beforeEach(() => {
  api.getMailStatus.mockResolvedValue(STATUS);
  api.getMailThreads.mockResolvedValue([ROW]);
  api.syncMail.mockResolvedValue({ ok: true });
  api.archiveMailThread.mockResolvedValue({ ok: true });
  api.binMailThread.mockResolvedValue({ ok: true });
  api.markMailThread.mockResolvedValue({ ok: true });
  api.markMailMessageRead.mockResolvedValue({ ok: true });
  api.getMailThread.mockResolvedValue({ ok: true, key: "k1", subject: "Plan for Friday", in_inbox: true, messages: [ENVELOPE] });
  api.getMailMessage.mockResolvedValue({ ...ENVELOPE, ok: true, thread_key: "k1", html: "<p>Shall we?</p>", text: "Shall we?", attachments: [] });
  api.searchMail.mockResolvedValue({ ok: true, results: [{ ...ENVELOPE, folder: "Archive", uid: 9, subject: "Invoice January" }] });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("MailView", () => {
  it("explains what to connect when no mailbox is connected, and syncs nothing", async () => {
    api.getMailStatus.mockResolvedValue({ ...STATUS, connected: false, address: "" });
    const onOpenConnectors = vi.fn();
    render(<MailView onOpenConnectors={onOpenConnectors} />);
    expect((await screen.findByTestId("mail-not-connected")).textContent).toContain("Connectors, Email");
    fireEvent.click(screen.getByTestId("mail-open-connectors"));
    expect(onOpenConnectors).toHaveBeenCalled();
    expect(api.syncMail).not.toHaveBeenCalled();
    expect(api.getMailThreads).not.toHaveBeenCalled();
  });

  it("lists the inbox and starts one sync when it opens", async () => {
    render(<MailView onOpenConnectors={() => {}} />);
    expect((await screen.findByTestId("mail-row")).textContent).toContain("Plan for Friday");
    expect(screen.getByTestId("mail-sync-line").textContent).toContain("me@example.com");
    await waitFor(() => expect(api.syncMail).toHaveBeenCalledTimes(1));
  });

  it("shows why the last sync failed while still listing what it has", async () => {
    api.getMailStatus.mockResolvedValue({ ...STATUS, last_error: "could not reach the mail server: offline" });
    render(<MailView onOpenConnectors={() => {}} />);
    expect((await screen.findByTestId("mail-error")).textContent).toContain("could not reach the mail server");
    expect(screen.getByTestId("mail-row")).toBeTruthy();
  });

  it("archiving takes the conversation out of the list at once", async () => {
    render(<MailView onOpenConnectors={() => {}} />);
    fireEvent.click(await screen.findByTestId("mail-row"));
    api.getMailThreads.mockResolvedValue([]);
    fireEvent.click(await screen.findByTestId("mail-archive"));
    await waitFor(() => expect(screen.queryByTestId("mail-row")).toBeNull());
    expect(api.archiveMailThread).toHaveBeenCalledWith("k1");
    expect(screen.queryByTestId("mail-reader")).toBeNull();
  });

  it("a refused archive brings the conversation back with the reason on its row", async () => {
    api.archiveMailThread.mockResolvedValue({ ok: false, error: "this mailbox cannot move mail" });
    render(<MailView onOpenConnectors={() => {}} />);
    fireEvent.click(await screen.findByTestId("mail-row"));
    fireEvent.click(await screen.findByTestId("mail-archive"));
    expect((await screen.findByRole("alert")).textContent).toBe("this mailbox cannot move mail");
    expect(screen.getByTestId("mail-row").textContent).toContain("Plan for Friday");
  });

  it("moving to the bin and marking unread each call their own action", async () => {
    render(<MailView onOpenConnectors={() => {}} />);
    fireEvent.click(await screen.findByTestId("mail-row"));
    fireEvent.click(await screen.findByTestId("mail-unread"));
    await waitFor(() => expect(api.markMailThread).toHaveBeenCalledWith("k1", false));
    expect(screen.getByTestId("mail-row")).toBeTruthy(); // still listed: it was only marked

    fireEvent.click(screen.getByTestId("mail-row"));
    api.getMailThreads.mockResolvedValue([]);
    fireEvent.click(await screen.findByTestId("mail-bin"));
    await waitFor(() => expect(screen.queryByTestId("mail-row")).toBeNull());
    expect(api.binMailThread).toHaveBeenCalledWith("k1");
  });

  it("offers Archive and Bin only when the mailbox can move mail", async () => {
    api.getMailStatus.mockResolvedValue({ ...STATUS, can_archive: false, can_bin: false });
    render(<MailView onOpenConnectors={() => {}} />);
    fireEvent.click(await screen.findByTestId("mail-row"));
    expect(await screen.findByTestId("mail-unread")).toBeTruthy();
    expect(screen.queryByTestId("mail-archive")).toBeNull();
    expect(screen.queryByTestId("mail-bin")).toBeNull();
  });

  it("search lists what the server found, opens a result alone, and goes back to the inbox", async () => {
    render(<MailView onOpenConnectors={() => {}} />);
    await screen.findByTestId("mail-row");
    fireEvent.change(screen.getByTestId("mail-search"), { target: { value: "invoice" } });
    fireEvent.submit(screen.getByRole("search"));
    await waitFor(() => expect(screen.getByTestId("mail-row").textContent).toContain("Invoice January"));
    expect(api.searchMail).toHaveBeenCalledWith("invoice");
    expect(screen.getByTestId("mail-row").textContent).toContain("Archive");

    fireEvent.click(screen.getByTestId("mail-row"));
    await waitFor(() => expect(api.getMailMessage).toHaveBeenCalledWith("Archive", 9));
    await waitFor(() => expect(api.markMailMessageRead).toHaveBeenCalledWith("Archive", 9));
    expect(screen.queryByTestId("mail-archive")).toBeNull();

    fireEvent.click(screen.getByTestId("mail-search-clear"));
    await waitFor(() => expect(screen.getByTestId("mail-row").textContent).toContain("Plan for Friday"));
  });

  it("a search that fails shows the reason in place of results", async () => {
    api.searchMail.mockResolvedValue({ ok: false, error: "the mail server could not search this folder" });
    render(<MailView onOpenConnectors={() => {}} />);
    await screen.findByTestId("mail-row");
    fireEvent.change(screen.getByTestId("mail-search"), { target: { value: "invoice" } });
    fireEvent.submit(screen.getByRole("search"));
    expect((await screen.findByTestId("mail-search-error")).textContent).toContain("could not search");
    expect(screen.queryByTestId("mail-list-empty")).toBeNull();
    expect(screen.queryByTestId("mail-row")).toBeNull();
  });

  it("an answer to a search that was left does not replace the inbox", async () => {
    let answer: (reply: unknown) => void = () => {};
    api.searchMail.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    render(<MailView onOpenConnectors={() => {}} />);
    await screen.findByTestId("mail-row");
    fireEvent.change(screen.getByTestId("mail-search"), { target: { value: "invoice" } });
    fireEvent.submit(screen.getByRole("search"));
    fireEvent.change(screen.getByTestId("mail-search"), { target: { value: "" } });
    fireEvent.submit(screen.getByRole("search"));
    answer({ ok: true, results: [{ ...ENVELOPE, folder: "Archive", uid: 9, subject: "Invoice January" }] });
    await waitFor(() => expect(screen.getByTestId("mail-row").textContent).toContain("Plan for Friday"));
    expect(screen.queryByText("Search results")).toBeNull();
  });
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `npx vitest run src/components/mail/MailView.test.tsx`
Expected: FAIL, `Failed to resolve import "./MailView"`.

- [ ] **Step 3: Write `MailReader.tsx`**

```tsx
import { useEffect, useState } from "react";
import {
  getMailMessage,
  getMailThread,
  markMailMessageRead,
  markMailThread,
  saveMailAttachment,
  type MailEnvelope,
  type MailMessage,
  type MailThread,
} from "../../api";
import { useT } from "../../i18n";
import { Icon } from "../Icon";
import { MailFrame } from "./MailFrame";
import { formatMailDate, senderName } from "./MailList";

/** What the reader is showing: a conversation from the inbox, or one message from search. */
export type Opened =
  | { kind: "thread"; key: string }
  | { kind: "message"; folder: string; uid: number };

const OFFLINE = "Could not reach MimiWork. Try again.";
const messageId = (m: { folder: string; uid: number }) => `${m.folder}/${m.uid}`;

function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/** One message. Its body is fetched the first time it is opened, not before. */
function MessageCard({
  folder,
  uid,
  summary,
  open,
  onToggle,
  alone = false,
}: {
  folder: string;
  uid: number;
  summary?: MailEnvelope;
  open: boolean;
  onToggle?: () => void;
  /** A search result: shown by itself under its own subject, and marked read by itself.
   *  A conversation has one subject above all its messages and is marked as a whole. */
  alone?: boolean;
}) {
  const t = useT();
  const [message, setMessage] = useState<MailMessage | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState<Record<number, string>>({});

  useEffect(() => {
    if (!open || message || error) return;
    let alive = true;
    getMailMessage(folder, uid)
      .then((reply) => {
        if (!alive) return;
        if (!reply.ok) return setError(reply.error || OFFLINE);
        setMessage(reply);
        if (alone) void markMailMessageRead(folder, uid).catch(() => undefined);
      })
      .catch(() => alive && setError(OFFLINE));
    return () => {
      alive = false;
    };
  }, [open, message, error, folder, uid, alone]);

  const save = async (index: number) => {
    const reply = await saveMailAttachment(folder, uid, index).catch(() => ({ ok: false, error: OFFLINE, path: "" }));
    const note = reply.ok ? `${t("Saved to")} ${reply.path}` : t(reply.error || OFFLINE);
    setSaved((notes) => ({ ...notes, [index]: note }));
  };

  const shown = message ?? summary;
  return (
    <article className={"mail-message" + (open ? " open" : "")} data-testid="mail-message">
      {alone && message && (
        <h2 className="mail-subject mail-subject-alone" data-testid="mail-subject">{message.subject || "—"}</h2>
      )}
      <button className="mail-message-head" onClick={onToggle} disabled={!onToggle} aria-expanded={open}>
        <span className="mail-message-from">{shown ? senderName(shown.from) : ""}</span>
        <span className="mail-message-date">{shown ? formatMailDate(shown.date, true) : ""}</span>
      </button>
      {open && shown && (
        <div className="mail-message-to">
          {t("To")}: {[shown.to, shown.cc].filter(Boolean).join(", ")}
        </div>
      )}
      {open && error && <div className="mail-error" role="alert">{t(error)}</div>}
      {open && !message && !error && <div className="mail-note">{t("Loading…")}</div>}
      {open && message && message.attachments.length > 0 && (
        <ul className="mail-attachments" data-testid="mail-attachments">
          {message.attachments.map((file, index) => (
            <li key={index}>
              <Icon name="file" size={13} />
              <span className="mail-attachment-name">{file.filename}</span>
              <span className="mail-attachment-size">{fileSize(file.size)}</span>
              <button className="btn sm" data-testid="mail-attachment-save" onClick={() => save(index)}>
                {t("Save")}
              </button>
              {saved[index] && (
                <span className="mail-attachment-note" role="status">{saved[index]}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {open && message && <MailFrame html={message.html} text={message.text} />}
    </article>
  );
}

/** The middle pane. Give it a `key` that names what is open, so each opening starts fresh. */
export function MailReader({
  opened,
  canArchive,
  canBin,
  onArchive,
  onBin,
  onUnread,
  onChanged,
}: {
  opened: Opened;
  canArchive: boolean;
  canBin: boolean;
  onArchive: (key: string) => void;
  onBin: (key: string) => void;
  onUnread: (key: string) => void;
  /** The reader changed something the list shows (it marked the conversation read). */
  onChanged: () => void;
}) {
  const t = useT();
  const [thread, setThread] = useState<MailThread | null>(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const key = opened.kind === "thread" ? opened.key : "";

  useEffect(() => {
    if (!key) return;
    let alive = true;
    getMailThread(key)
      .then((reply) => {
        if (!alive) return;
        if (!reply.ok) return setError(reply.error || OFFLINE);
        setThread(reply);
        // Open what has not been read, and always the newest.
        const last = reply.messages.length - 1;
        setExpanded(new Set(reply.messages.filter((m, i) => m.unread || i === last).map(messageId)));
        if (reply.messages.some((m) => m.unread)) {
          void markMailThread(key, true).then(onChanged).catch(() => undefined);
        }
      })
      .catch(() => alive && setError(OFFLINE));
    return () => {
      alive = false;
    };
  }, [key, onChanged]);

  if (opened.kind === "message") {
    // A search result is shown alone. Archive and Bin are not offered: it may already be
    // archived, or sit in a folder Mail does not manage.
    return (
      <div className="mail-reader" data-testid="mail-reader">
        <MessageCard folder={opened.folder} uid={opened.uid} open alone />
      </div>
    );
  }
  if (error) return <div className="mail-error" role="alert">{t(error)}</div>;
  if (!thread) return <div className="mail-note">{t("Loading…")}</div>;

  const toggle = (id: string) =>
    setExpanded((now) => {
      const next = new Set(now);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  return (
    <div className="mail-reader" data-testid="mail-reader">
      <div className="mail-reader-head">
        <h2 className="mail-subject" data-testid="mail-subject">{thread.subject || "—"}</h2>
        {thread.in_inbox && (
          <div className="mail-actions">
            {canArchive && (
              <button className="btn sm" data-testid="mail-archive" onClick={() => onArchive(key)}>
                <Icon name="archive" size={14} /> {t("Archive")}
              </button>
            )}
            {canBin && (
              <button className="btn sm" data-testid="mail-bin" onClick={() => onBin(key)}>
                <Icon name="trash" size={14} /> {t("Move to bin")}
              </button>
            )}
            <button className="btn sm" data-testid="mail-unread" onClick={() => onUnread(key)}>
              {t("Mark unread")}
            </button>
          </div>
        )}
      </div>
      {thread.messages.map((m) => (
        <MessageCard
          key={messageId(m)}
          folder={m.folder}
          uid={m.uid}
          summary={m}
          open={expanded.has(messageId(m))}
          onToggle={() => toggle(messageId(m))}
        />
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Write `MailView.tsx`**

```tsx
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import {
  archiveMailThread,
  binMailThread,
  getMailStatus,
  getMailThreads,
  markMailThread,
  searchMail,
  syncMail,
  type MailEnvelope,
  type MailReply,
  type MailStatus,
  type MailThreadRow,
} from "../../api";
import { useT } from "../../i18n";
import { Icon } from "../Icon";
import { formatMailDate, MailList, type MailRow } from "./MailList";
import { MailReader, type Opened } from "./MailReader";

const POLL_MS = 2000;
const SYNC_EVERY_MS = 120_000;
const OFFLINE = "Could not reach MimiWork. Try again.";

const openedId = (opened: Opened | null): string =>
  !opened ? "" : opened.kind === "thread" ? opened.key : `${opened.folder}/${opened.uid}`;

/** The Mail section: the connected mailbox's inbox, a reader, and search. */
export function MailView({ onOpenConnectors }: { onOpenConnectors: () => void }) {
  const t = useT();
  const [status, setStatus] = useState<MailStatus | null>(null);
  const [threads, setThreads] = useState<MailThreadRow[]>([]);
  const [opened, setOpened] = useState<Opened | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MailEnvelope[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const revision = useRef(-1);
  const lastSync = useRef(0);
  const searchRun = useRef(0);

  const refresh = useCallback(async (force = false): Promise<MailStatus | null> => {
    const next = await getMailStatus().catch(() => null);
    if (!next) return null;
    setStatus(next);
    if (next.connected && (force || next.revision !== revision.current)) {
      const rows = await getMailThreads().catch(() => null);
      // A list that failed to load is asked for again on the next tick.
      revision.current = rows ? next.revision : -1;
      if (rows) setThreads(rows);
    }
    return next;
  }, []);

  const startSync = useCallback(() => {
    lastSync.current = Date.now();
    void syncMail()
      .then(() => refresh())
      .catch(() => undefined);
  }, [refresh]);

  useEffect(() => {
    let alive = true;
    void refresh(true).then((now) => {
      if (alive && now?.connected) startSync();
    });
    // ponytail: asks for status every two seconds for as long as Mail is open, and syncs
    // every two minutes. Move to a pushed event if the polling is ever seen to cost anything.
    const timer = window.setInterval(() => {
      void refresh().then((now) => {
        const due = Date.now() - lastSync.current > SYNC_EVERY_MS;
        if (alive && now?.connected && !now.syncing && due) startSync();
      });
    }, POLL_MS);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, [refresh, startSync]);

  const reload = useCallback(() => void refresh(true), [refresh]);

  // The list changes first so it answers at once. If the server refuses, the reload
  // brings the row back and it carries the reason.
  const change = async (key: string, call: () => Promise<MailReply>, leavesList: boolean) => {
    setOpened(null);
    if (leavesList) setThreads((rows) => rows.filter((row) => row.key !== key));
    const reply = await call().catch((): MailReply => ({ ok: false, error: OFFLINE }));
    setRowErrors((errors) => {
      const next = { ...errors };
      if (reply.ok) delete next[key];
      else next[key] = t(reply.error || OFFLINE);
      return next;
    });
    // If this reload cannot reach the sidecar either, the next tick must still fetch the
    // list, or a row taken out a moment ago would stay missing.
    revision.current = -1;
    await refresh(true);
  };

  const clearSearch = () => {
    searchRun.current += 1;
    setSearching(false);
    setQuery("");
    setResults(null);
    setSearchError("");
    setOpened(null);
  };

  const search = async (event: FormEvent) => {
    event.preventDefault();
    const words = query.trim();
    if (!words) return clearSearch();
    const run = (searchRun.current += 1);
    setSearching(true);
    setSearchError("");
    setOpened(null);
    const reply = await searchMail(words).catch(() => ({ ok: false, error: OFFLINE, results: [] }));
    // An answer to a search that has since been replaced, or left, is dropped.
    if (run !== searchRun.current) return;
    setSearching(false);
    setResults(reply.ok ? (reply.results ?? []) : []);
    if (!reply.ok) setSearchError(t(reply.error || OFFLINE));
  };

  if (!status) return <main className="app-page mail-page" data-testid="mail-page" />;

  if (!status.connected) {
    return (
      <main className="app-page mail-page" data-testid="mail-page">
        <div className="mail-welcome" data-testid="mail-not-connected">
          <h2>{t("Mail")}</h2>
          <p>{t("Mail reads the mailbox you connect under Connectors, Email.")}</p>
          <p>{t("Sign-in for Gmail and Outlook is on its way. A personal Gmail works today with an app password.")}</p>
          <button className="btn-primary" data-testid="mail-open-connectors" onClick={onOpenConnectors}>
            {t("Open Connectors")}
          </button>
        </div>
      </main>
    );
  }

  const rows: MailRow[] = results
    ? results.map((r) => ({
        id: `${r.folder}/${r.uid}`,
        sender: r.from,
        subject: r.subject,
        date: r.date,
        unread: r.unread,
        has_attachments: r.has_attachments,
        folder: r.folder,
      }))
    : threads.map((row) => ({ ...row, id: row.key, error: rowErrors[row.key] }));

  const open = (id: string) => {
    // Opening a row is the user having seen why its last change failed.
    setRowErrors((errors) => {
      if (!(id in errors)) return errors;
      const next = { ...errors };
      delete next[id];
      return next;
    });
    const result = results?.find((r) => `${r.folder}/${r.uid}` === id);
    setOpened(result ? { kind: "message", folder: result.folder, uid: result.uid } : { kind: "thread", key: id });
  };

  const syncLine = status.syncing
    ? t("Syncing…")
    : status.last_sync
      ? `${t("Last synced")} ${formatMailDate(status.last_sync)}`
      : "";
  const empty = searching ? t("Searching…") : results ? t("Nothing found.") : t("No mail here yet.");

  return (
    <main className="app-page mail-page" data-testid="mail-page">
      <div className="app-head">
        <div className="app-head-text">
          <span className="app-title">{t("Mail")}</span>
          <span className="app-desc" data-testid="mail-sync-line">
            {[status.address, syncLine].filter(Boolean).join(" · ")}
          </span>
        </div>
        <form className="mail-search" role="search" onSubmit={search}>
          <input
            className="tmpl-input"
            type="search"
            data-testid="mail-search"
            placeholder={t("Search mail")}
            aria-label={t("Search mail")}
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              if (!event.target.value && results) clearSearch();
            }}
          />
        </form>
        <div className="app-head-actions">
          <button className="btn sm" data-testid="mail-refresh" disabled={status.syncing} onClick={startSync}>
            <Icon name="refresh" size={14} /> {t("Refresh")}
          </button>
        </div>
      </div>
      {status.last_error && (
        <div className="mail-error mail-banner" role="alert" data-testid="mail-error">
          {status.last_error}{" "}
          <button className="mail-inline-link" onClick={onOpenConnectors}>{t("Open Connectors")}</button>
        </div>
      )}
      <div className="mail-body">
        <div className="mail-list-pane">
          {results && (
            <div className="mail-search-head">
              <span>{t("Search results")}</span>
              <button className="mail-inline-link" data-testid="mail-search-clear" onClick={clearSearch}>
                {t("Back to inbox")}
              </button>
            </div>
          )}
          {/* A search that failed shows why in place of results, not "Nothing found." */}
          {searchError ? (
            <div className="mail-error" role="alert" data-testid="mail-search-error">{searchError}</div>
          ) : (
            <MailList rows={searching ? [] : rows} selected={openedId(opened)} onOpen={open} empty={empty} />
          )}
        </div>
        <div className="mail-reader-pane">
          {opened ? (
            <MailReader
              key={openedId(opened)}
              opened={opened}
              canArchive={status.can_archive}
              canBin={status.can_bin}
              onArchive={(key) => change(key, () => archiveMailThread(key), true)}
              onBin={(key) => change(key, () => binMailThread(key), true)}
              onUnread={(key) => change(key, () => markMailThread(key, false), false)}
              onChanged={reload}
            />
          ) : (
            <div className="mail-placeholder">{t("Select a conversation to read it.")}</div>
          )}
        </div>
      </div>
    </main>
  );
}
```

Notes for the implementer:

- `MailReader` is given `key={openedId(opened)}`, so opening something else starts it afresh. Do not replace that with state resets inside an effect.
- `onChanged` must stay a stable function (`reload` is wrapped in `useCallback`), because the reader's loading effect depends on it.
- `npm run lint` reports one warning for `MailView.tsx` (`react-hooks/set-state-in-effect`, on the first status request). That rule is a warning in this repo and the other sections that poll trip it the same way. There must be no errors.
- A search answer is used only if it belongs to the search still on screen (`searchRun`). A search that fails shows its reason in place of the list.
- After any change, `revision.current` is set to -1 before the reload, so a reload that fails is tried again on the next tick and a row taken out of the list cannot stay missing.
- Errors from the backend arrive as English sentences and are passed through `t(…)`, which leaves an untranslated sentence as it is.

- [ ] **Step 5: Add the styles**

Append to `surfaces/gui/src/styles.css`:

```css

/* ── Mail ─────────────────────────────────────────────────────────────────────────────
   List on the left, the email in the middle. Plan B adds a comments column on the right. */
.mail-page { overflow: hidden; }
.mail-search { flex: 0 1 280px; }
.mail-search .tmpl-input { width: 100%; }
.mail-page .app-head-actions .btn { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }
.mail-body { flex: 1; min-height: 0; display: flex; }
.mail-list-pane { flex: none; width: 340px; overflow-y: auto; border-right: 1px solid var(--line); background: var(--panel); }
.mail-reader-pane { flex: 1; min-width: 0; overflow-y: auto; padding: 16px 20px 28px; }
.mail-list { list-style: none; margin: 0; padding: 0; }
.mail-row {
  width: 100%; display: flex; flex-direction: column; gap: 2px; padding: 9px 14px; text-align: left;
  background: none; border: 0; border-bottom: 1px solid var(--line); cursor: pointer; font: inherit; color: var(--muted);
}
.mail-row:hover { background: var(--paper); }
.mail-row.selected { background: var(--accent-soft); }
.mail-row-top { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.mail-row-dot { flex: none; width: 7px; height: 7px; border-radius: 50%; background: transparent; }
.mail-row.unread .mail-row-dot { background: var(--accent); }
.mail-row-sender { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mail-row.unread .mail-row-sender, .mail-row.unread .mail-row-subject { color: var(--ink); font-weight: 600; }
.mail-row-count { flex: none; font-size: 11px; color: var(--faint); }
.mail-row-clip { flex: none; display: inline-flex; color: var(--faint); }
.mail-row-date { flex: none; font-size: 11.5px; color: var(--faint); }
.mail-row-subject { font-size: 12.5px; padding-left: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mail-row-folder { font-size: 11px; color: var(--faint); padding-left: 13px; }
.mail-row-error { font-size: 11.5px; color: var(--danger); padding-left: 13px; }
.mail-list-empty, .mail-placeholder, .mail-note { padding: 18px 14px; font-size: 13px; color: var(--faint); }
.mail-search-head { display: flex; justify-content: space-between; padding: 8px 14px; font-size: 12px; color: var(--muted); border-bottom: 1px solid var(--line); }
.mail-inline-link { background: none; border: 0; padding: 0; font: inherit; color: var(--accent); cursor: pointer; text-decoration: underline; }
.mail-error { padding: 8px 14px; font-size: 12.5px; color: var(--danger); background: var(--danger-soft); border-radius: 8px; }
.mail-banner { margin: 10px 16px 0; }
.mail-welcome { max-width: 460px; margin: 64px auto; padding: 0 20px; display: flex; flex-direction: column; gap: 10px; font-size: 13.5px; color: var(--muted); }
.mail-welcome h2 { font-size: 18px; font-weight: 600; color: var(--ink); margin: 0; }
.mail-welcome p { margin: 0; }
.mail-reader { max-width: 860px; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; }
.mail-reader-head { display: flex; align-items: flex-start; gap: 12px; flex-wrap: wrap; }
.mail-subject { flex: 1; min-width: 200px; margin: 0; font-size: 17px; font-weight: 600; color: var(--ink); }
.mail-subject-alone { padding: 12px 14px 0; }
.mail-actions { display: flex; gap: 6px; flex: none; }
.mail-actions .btn { display: inline-flex; align-items: center; gap: 5px; }
.mail-message { border: 1px solid var(--line); border-radius: 10px; background: var(--panel); overflow: hidden; }
.mail-message-head {
  width: 100%; display: flex; justify-content: space-between; gap: 10px; padding: 10px 14px;
  background: none; border: 0; font: inherit; font-size: 13px; color: var(--ink); cursor: pointer; text-align: left;
}
.mail-message-head:disabled { cursor: default; }
.mail-message-from { font-weight: 600; }
.mail-message-date { color: var(--faint); font-size: 12px; flex: none; }
.mail-message-to { padding: 0 14px 8px; font-size: 12px; color: var(--faint); }
.mail-message .mail-error { margin: 0 14px 12px; }
.mail-attachments { list-style: none; margin: 0; padding: 0 14px 10px; display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; color: var(--muted); }
.mail-attachments li { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.mail-attachment-size, .mail-attachment-note { color: var(--faint); font-size: 11.5px; }
.mail-frame-wrap { border-top: 1px solid var(--line); }
/* An email is designed for a white page, so it gets one in dark mode too. */
.mail-frame { display: block; width: 100%; border: 0; background: #fff; }
.mail-show-images { margin: 8px 14px; }
.mail-link-card {
  position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px 14px; font-size: 12.5px; background: var(--accent-soft); color: var(--ink);
}
.mail-link-label { color: var(--muted); flex: none; }
.mail-link-address { flex: 1; min-width: 160px; font-family: var(--mono); font-size: 12px; overflow-wrap: anywhere; }
.mail-plain { margin: 0; padding: 0 14px 14px; white-space: pre-wrap; font: inherit; font-size: 13px; color: var(--ink); }
@media (max-width: 900px) {
  .mail-list-pane { width: 240px; }
}
```

- [ ] **Step 6: Add the strings**

In `surfaces/gui/src/i18n.tsx`, add these rows at the end of the `D` dictionary, just before its closing `};`. The order of each row is the file's: zh, no, fr, es, ja, ar, de, pt. `Refresh`, `Save`, `Close`, `Message` and `Loading…` are already there.

```ts
  "Mail": ["邮件", "E-post", "Courrier", "Correo", "メール", "البريد", "Mail", "E-mail"],
  "Search mail": ["搜索邮件", "Søk i e-post", "Rechercher dans le courrier", "Buscar en el correo", "メールを検索", "البحث في البريد", "Mails durchsuchen", "Pesquisar e-mails"],
  "Syncing…": ["正在同步…", "Synkroniserer…", "Synchronisation…", "Sincronizando…", "同期中…", "جارٍ المزامنة…", "Synchronisiere…", "Sincronizando…"],
  "Last synced": ["上次同步", "Sist synkronisert", "Dernière synchronisation", "Última sincronización", "最終同期", "آخر مزامنة", "Zuletzt synchronisiert", "Última sincronização"],
  "Archive": ["归档", "Arkiver", "Archiver", "Archivar", "アーカイブ", "أرشفة", "Archivieren", "Arquivar"],
  "Move to bin": ["移到废纸篓", "Flytt til papirkurven", "Mettre à la corbeille", "Mover a la papelera", "ゴミ箱に移動", "نقل إلى سلة المهملات", "In den Papierkorb", "Mover para a lixeira"],
  "Mark unread": ["标为未读", "Merk som ulest", "Marquer comme non lu", "Marcar como no leído", "未読にする", "تحديد كغير مقروء", "Als ungelesen markieren", "Marcar como não lido"],
  "Show images": ["显示图片", "Vis bilder", "Afficher les images", "Mostrar imágenes", "画像を表示", "إظهار الصور", "Bilder anzeigen", "Mostrar imagens"],
  "Open in browser": ["在浏览器中打开", "Åpne i nettleseren", "Ouvrir dans le navigateur", "Abrir en el navegador", "ブラウザで開く", "فتح في المتصفح", "Im Browser öffnen", "Abrir no navegador"],
  "This link goes to": ["此链接指向", "Denne lenken går til", "Ce lien mène à", "Este enlace lleva a", "このリンクの行き先", "هذا الرابط يؤدي إلى", "Dieser Link führt zu", "Este link leva a"],
  "Saved to": ["已保存到", "Lagret i", "Enregistré dans", "Guardado en", "保存先", "تم الحفظ في", "Gespeichert in", "Salvo em"],
  "To": ["收件人", "Til", "À", "Para", "宛先", "إلى", "An", "Para"],
  "No mail here yet.": ["这里还没有邮件。", "Ingen e-post her ennå.", "Aucun courrier ici pour l’instant.", "Aún no hay correo aquí.", "まだメールはありません。", "لا يوجد بريد هنا بعد.", "Noch keine Mails hier.", "Ainda não há e-mails aqui."],
  "Nothing found.": ["没有找到结果。", "Ingenting funnet.", "Aucun résultat.", "No se encontró nada.", "何も見つかりませんでした。", "لم يُعثر على شيء.", "Nichts gefunden.", "Nada encontrado."],
  "Searching…": ["正在搜索…", "Søker…", "Recherche…", "Buscando…", "検索中…", "جارٍ البحث…", "Suche…", "Pesquisando…"],
  "Search results": ["搜索结果", "Søkeresultater", "Résultats de recherche", "Resultados de búsqueda", "検索結果", "نتائج البحث", "Suchergebnisse", "Resultados da pesquisa"],
  "Back to inbox": ["返回收件箱", "Tilbake til innboksen", "Retour à la boîte de réception", "Volver a la bandeja de entrada", "受信トレイに戻る", "العودة إلى البريد الوارد", "Zurück zum Posteingang", "Voltar à caixa de entrada"],
  "Select a conversation to read it.": ["选择一封邮件即可阅读。", "Velg en samtale for å lese den.", "Sélectionnez une conversation pour la lire.", "Selecciona una conversación para leerla.", "会話を選ぶと読めます。", "اختر محادثة لقراءتها.", "Wähle eine Unterhaltung aus, um sie zu lesen.", "Selecione uma conversa para lê-la."],
  "Mail reads the mailbox you connect under Connectors, Email.": ["“邮件”会读取你在“连接器”的“电子邮箱”中连接的邮箱。", "E-post leser postkassen du kobler til under Koblinger, E-post.", "Courrier lit la boîte que vous connectez dans Connecteurs, E-mail.", "Correo lee el buzón que conectas en Conectores, Correo electrónico.", "メールは、コネクタの「メール」で接続したメールボックスを読み込みます。", "يقرأ البريد صندوق البريد الذي تربطه من الموصلات، البريد الإلكتروني.", "Mail liest das Postfach, das du unter Konnektoren, E-Mail verbindest.", "O E-mail lê a caixa que você conecta em Conectores, E-mail."],
  "Sign-in for Gmail and Outlook is on its way. A personal Gmail works today with an app password.": ["Gmail 和 Outlook 的登录方式即将推出。个人 Gmail 现在可以用应用专用密码使用。", "Pålogging for Gmail og Outlook er på vei. En personlig Gmail fungerer i dag med et app-passord.", "La connexion pour Gmail et Outlook arrive bientôt. Un compte Gmail personnel fonctionne dès aujourd’hui avec un mot de passe d’application.", "El inicio de sesión para Gmail y Outlook está en camino. Un Gmail personal funciona hoy con una contraseña de aplicación.", "Gmail と Outlook のサインインは準備中です。個人の Gmail はアプリ パスワードで今すぐ使えます。", "تسجيل الدخول إلى Gmail وOutlook في الطريق. يعمل حساب Gmail الشخصي اليوم بكلمة مرور التطبيق.", "Die Anmeldung für Gmail und Outlook kommt bald. Ein privates Gmail-Konto funktioniert schon heute mit einem App-Passwort.", "O login para Gmail e Outlook está a caminho. Um Gmail pessoal já funciona hoje com uma senha de app."],
  "Open Connectors": ["打开连接器", "Åpne Koblinger", "Ouvrir les connecteurs", "Abrir Conectores", "コネクタを開く", "فتح الموصلات", "Konnektoren öffnen", "Abrir Conectores"],
  "This message could not be shown safely, so here is its text.": ["这封邮件无法安全显示，下面是它的文字内容。", "Denne meldingen kunne ikke vises trygt, så her er teksten.", "Ce message n’a pas pu être affiché en toute sécurité ; voici son texte.", "Este mensaje no se pudo mostrar de forma segura, así que aquí está su texto.", "このメッセージは安全に表示できなかったため、本文のテキストを表示しています。", "تعذّر عرض هذه الرسالة بأمان، وهذا نصها.", "Diese Nachricht konnte nicht sicher angezeigt werden, hier ist ihr Text.", "Esta mensagem não pôde ser exibida com segurança, então aqui está o texto."],
  "Could not reach MimiWork. Try again.": ["无法连接到 MimiWork，请重试。", "Kunne ikke nå MimiWork. Prøv igjen.", "Impossible de joindre MimiWork. Réessayez.", "No se pudo contactar con MimiWork. Inténtalo de nuevo.", "MimiWork に接続できませんでした。もう一度お試しください。", "تعذّر الوصول إلى MimiWork. حاول مرة أخرى.", "MimiWork ist nicht erreichbar. Versuche es erneut.", "Não foi possível acessar o MimiWork. Tente novamente."],
  "Unread": ["未读", "Ulest", "Non lu", "No leído", "未読", "غير مقروء", "Ungelesen", "Não lido"],
  "Has an attachment": ["有附件", "Har et vedlegg", "Contient une pièce jointe", "Tiene un adjunto", "添付ファイルあり", "يحتوي على مرفق", "Hat einen Anhang", "Tem um anexo"],
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `npx vitest run src/components/mail`
Expected: PASS, 4 files, 36 tests (13 + 7 + 6 + 10).

- [ ] **Step 8: Run the GUI gates and commit**

Run: `npx tsc --noEmit && npm run lint && npm test`
Expected: no type errors; lint with 0 errors; every vitest file passing.

```bash
git add surfaces/gui/src/components/mail/MailReader.tsx surfaces/gui/src/components/mail/MailView.tsx surfaces/gui/src/components/mail/MailView.test.tsx surfaces/gui/src/styles.css surfaces/gui/src/i18n.tsx
git commit -m "Add the Mail reader and section: open, search, save, archive, bin, mark unread"
```

### Task 15: Make Mail visible

Until now nothing in the app leads to Mail. This task adds its icon, its row in the navigation, and its place in the app shell.

**Files:**
- Modify: `surfaces/gui/src/components/Icon.tsx`
- Modify: `surfaces/gui/src/components/Sidebar.tsx`, `surfaces/gui/src/components/Sidebar.test.tsx`
- Modify: `surfaces/gui/src/App.tsx`

- [ ] **Step 1: The icon**

In `Icon.tsx`, add `| "mail"` to the `IconName` union directly after `| "inbox"`, and add this case directly above `case "inbox":`:

```tsx
    case "mail":
      return (
        <svg {...s}>
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="m3.5 7 8.5 6 8.5-6" />
        </svg>
      );
```

- [ ] **Step 2: The navigation row**

In `Sidebar.tsx`, add two props to the props type: `onOpenMail: () => void;` after `onOpenInbox: () => void;`, and `mailActive: boolean;` after `inboxActive: boolean;`.

Then find the block that begins with the comment `Automations: a first-class nav row`. Directly inside its `<div className="px-2.5 mt-1">`, above the Automations button, add:

```tsx
        <button
          className={
            "w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-[13px] text-left hover:bg-paper hover:text-ink " +
            (props.mailActive ? "text-ink bg-paper" : "text-muted")
          }
          data-testid="nav-mail"
          onClick={props.onOpenMail}
        >
          <Icon name="mail" size={15} className="shrink-0" />
          <span className="flex-1">{t("Mail")}</span>
        </button>
```

In `Sidebar.test.tsx`, the shared props object needs the two new props: add `onOpenMail: vi.fn(),` after `onOpenInbox: vi.fn(),` and `mailActive: false,` after `inboxActive: false,`.

- [ ] **Step 3: The app shell**

In `App.tsx`, make five edits:

1. Import: after `import { InboxView } from "./components/InboxView";` add `import { MailView } from "./components/mail/MailView";`
2. The `Surface` type: add `| "mail"` after `| "inbox"`.
3. The `<Sidebar … />` props: add `onOpenMail={() => setSurface("mail")}` after `onOpenInbox={() => setSurface("inbox")}`, and `mailActive={surface === "mail"}` after `inboxActive={surface === "inbox"}`.
4. `surfaceTitles`: add `mail: "Mail",` after `inbox: "Inbox",`.
5. The view chain: after the two lines

```tsx
      ) : surface === "inbox" ? (
        <InboxView onOpenSession={openSessionFromInbox} />
```

add

```tsx
      ) : surface === "mail" ? (
        <MailView onOpenConnectors={() => setSurface("integrations")} />
```

- [ ] **Step 4: Run the GUI gates**

Run: `npx tsc --noEmit && npm run lint && npm test`
Expected: no type errors (the compiler insists every `Surface` has a title, so a missed edit shows here); lint with 0 errors; every vitest file passing, `Sidebar.test.tsx` included.

- [ ] **Step 5: Commit**

```bash
git add surfaces/gui/src/components/Icon.tsx surfaces/gui/src/components/Sidebar.tsx surfaces/gui/src/components/Sidebar.test.tsx surfaces/gui/src/App.tsx
git commit -m "Put Mail in the navigation"
```

## Chunk 10: Mail in the browser tests, and the safety tests in WebKit

All commands in this chunk run in `surfaces/gui`.

### Task 16: The mocked mailbox, and the main path

The browser tests are hermetic: `e2e/fixtures.ts` answers every `/v1` request. Mail gets its answers there, and a spec that walks the reader's main path and takes a picture of every new state.

**Files:**
- Create: `surfaces/gui/e2e/mail-data.ts`
- Modify: `surfaces/gui/e2e/fixtures.ts` (one import, one state line, one block of routes)
- Create: `surfaces/gui/e2e/mail.spec.ts`

- [ ] **Step 1: Write the mailbox the mock serves**

`e2e/mail-data.ts`. One of its three conversations is hostile; Task 17 uses it.

```ts
// What the mocked backend answers for the Mail section: three inbox conversations (one of
// them hostile), their messages, and one archived message that only search can reach.

export const TRACKER = "https://tracker.invalid";
const NOW = Math.floor(Date.now() / 1000);

const envelope = (uid: number, from: string, subject: string, date: number, extra: object = {}) => ({
  folder: "INBOX", uid, message_id: `<${uid}@example.com>`, from, to: "me@example.com", cc: "",
  subject, date, unread: false, has_attachments: false, ...extra,
});

// Everything an email can try. Each address is unique, so a test can say exactly what
// was, and was not, requested.
export const HOSTILE_HTML = `<html><head>
<meta http-equiv="refresh" content="0;url=${TRACKER}/refresh">
<base href="${TRACKER}/base/">
<link rel="stylesheet" href="${TRACKER}/style.css">
<style>@import url(${TRACKER}/import.css); body { background: url(${TRACKER}/bg.png); font: 14px system-ui; }</style>
<script>window.__ran = "script"; fetch("${TRACKER}/script");</script>
</head><body>
<p id="hello">You have won. Claim your prize today.</p>
<img src="${TRACKER}/pixel.png" onerror="window.__ran = 'onerror'; fetch('${TRACKER}/onerror')">
<img name="head" src="${TRACKER}/named-head.png">
<img name="documentElement" src="${TRACKER}/named-root.png">
<form name="querySelectorAll" action="${TRACKER}/form"><input name="getAttribute" value="x"></form>
<noscript><style></noscript><a href="${TRACKER}/noscript">Noscript link</a></style></noscript>
<p><a id="plain" href="${TRACKER}/plain">Plain link</a></p>
<p><a id="self" target="_self" href="${TRACKER}/self">Same-frame link</a></p>
<div><template shadowrootmode="closed"><p><a href="${TRACKER}/shadow">Shadow link</a></p></template></div>
<svg width="220" height="28"><a xlink:href="${TRACKER}/svg"><text id="svg-text" x="0" y="20">SVG link</text></a></svg>
<svg width="220" height="28"><a><animate attributeName="href" to="${TRACKER}/smil" fill="freeze"/><text id="smil-text" x="0" y="20">Animated link</text></a></svg>
</body></html>`;

export const MAIL_THREADS = [
  { key: "a1a1a1a1a1a1a1a1", subject: "Plan for Friday", sender: "Ana Lopez <ana@example.com>", date: NOW - 3600, unread: true, count: 2, has_attachments: true },
  { key: "b2b2b2b2b2b2b2b2", subject: "Your invoice for October", sender: "Billing <billing@example.com>", date: NOW - 86400, unread: false, count: 1, has_attachments: false },
  { key: "c3c3c3c3c3c3c3c3", subject: "You have won", sender: "Prize Desk <win@tracker.invalid>", date: NOW - 2 * 86400, unread: false, count: 1, has_attachments: false },
];

export const MAIL_THREAD_MESSAGES: Record<string, ReturnType<typeof envelope>[]> = {
  a1a1a1a1a1a1a1a1: [
    envelope(1, "Ana Lopez <ana@example.com>", "Plan for Friday", NOW - 7200),
    envelope(2, "Ana Lopez <ana@example.com>", "Re: Plan for Friday", NOW - 3600, { unread: true, has_attachments: true }),
  ],
  b2b2b2b2b2b2b2b2: [envelope(3, "Billing <billing@example.com>", "Your invoice for October", NOW - 86400)],
  c3c3c3c3c3c3c3c3: [envelope(4, "Prize Desk <win@tracker.invalid>", "You have won", NOW - 2 * 86400)],
};

const message = (key: string, index: number, html: string, text: string, attachments: object[] = []) => ({
  ...MAIL_THREAD_MESSAGES[key][index], thread_key: key, html, text, attachments,
});

export const MAIL_MESSAGES: Record<string, object> = {
  "INBOX/1": message("a1a1a1a1a1a1a1a1", 0, "<p>Can we plan Friday?</p>", "Can we plan Friday?"),
  "INBOX/2": message(
    "a1a1a1a1a1a1a1a1", 1,
    '<p>Hi,</p><p>Shall we meet on <a id="agenda" href="https://example.com/agenda">Friday at ten</a>? The plan is attached.</p>',
    "Hi,\nShall we meet on Friday at ten? The plan is attached.",
    [{ filename: "plan.pdf", content_type: "application/pdf", size: 48213 }],
  ),
  "INBOX/3": message("b2b2b2b2b2b2b2b2", 0, "<p>Your invoice for October is ready.</p>", "Your invoice for October is ready."),
  "INBOX/4": message("c3c3c3c3c3c3c3c3", 0, HOSTILE_HTML, "You have won. Claim your prize today."),
  "Archive/40": {
    ...envelope(40, "Billing <billing@example.com>", "Invoice January", NOW - 300 * 86400, { folder: "Archive" }),
    thread_key: "d4d4d4d4d4d4d4d4", html: "<p>Paid in full.</p>", text: "Paid in full.", attachments: [],
  },
};

export const MAIL_SEARCH = [
  envelope(40, "Billing <billing@example.com>", "Invoice January", NOW - 300 * 86400, { folder: "Archive" }),
];
```

- [ ] **Step 2: Teach the mock to answer Mail**

In `e2e/fixtures.ts`, add at the very top of the file:

```ts
import { MAIL_MESSAGES, MAIL_SEARCH, MAIL_THREADS, MAIL_THREAD_MESSAGES } from "./mail-data";
```

Directly inside `mockApi`, as the first lines of its body:

```ts
  // Mail — per-test state, so an archive or a mark in one test never leaks into another.
  const mail = { threads: MAIL_THREADS.map((t) => ({ ...t })), revision: 1 };
```

And directly above the line `    // agent systems` inside the `page.route("**/v1/**", …)` handler:

```ts
    // mail
    if (p.endsWith("/v1/mail/status")) {
      return json({
        ok: true, connected: true, address: "me@example.com", syncing: false, revision: mail.revision,
        last_sync: Math.floor(Date.now() / 1000) - 60, last_error: "", can_archive: true, can_bin: true,
      });
    }
    if (p.endsWith("/v1/mail/sync")) return json({ ok: true, started: true });
    if (p.endsWith("/v1/mail/threads")) return json({ ok: true, threads: mail.threads });
    if (p.endsWith("/v1/mail/message/read")) return json({ ok: true });
    if (p.endsWith("/v1/mail/message")) {
      const q = new URL(req.url()).searchParams;
      const found = MAIL_MESSAGES[`${q.get("folder")}/${q.get("uid")}`];
      return json(found ? { ok: true, ...found } : { ok: false, error: "This message is no longer in the mailbox." });
    }
    if (p.endsWith("/v1/mail/search")) {
      const words = (new URL(req.url()).searchParams.get("q") || "").toLowerCase();
      return json({ ok: true, results: MAIL_SEARCH.filter((r) => r.subject.toLowerCase().includes(words)) });
    }
    if (p.endsWith("/v1/mail/attachments/save")) return json({ ok: true, path: "/Users/me/Downloads/plan.pdf" });
    {
      const mm = p.match(/\/v1\/mail\/threads\/([^/]+)(\/read|\/archive|\/bin)?$/);
      if (mm) {
        const row = mail.threads.find((t) => t.key === mm[1]);
        if (!row) return json({ ok: false, error: "This conversation is no longer in the mailbox." });
        if (!mm[2]) {
          return json({ ok: true, key: row.key, subject: row.subject, in_inbox: true, messages: MAIL_THREAD_MESSAGES[row.key] });
        }
        // Like the backend: a change moves the revision, which is what makes the list reload.
        if (mm[2] === "/read") row.unread = !(req.postDataJSON() || {}).read;
        else mail.threads.splice(mail.threads.indexOf(row), 1);
        mail.revision += 1;
        return json({ ok: true });
      }
    }
```

- [ ] **Step 3: Write the spec**

`e2e/mail.spec.ts`:

```ts
import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

// Mail as a reader: the inbox as conversations, an email shown as it was sent, an
// attachment saved, a conversation archived, and search reaching mail outside the inbox.

async function openMail(page: Page) {
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("/");
  await page.getByTestId("nav-mail").click();
  await expect(page.getByTestId("mail-row")).toHaveCount(3);
}

// The email sits in a frame where nothing can run, so the test reads and clicks it the
// way the app does: from outside.
const frameText = (page: Page) =>
  page.evaluate(() => {
    const frame = document.querySelector<HTMLIFrameElement>('[data-testid="mail-frame"]');
    return frame?.contentDocument?.body?.innerText ?? "";
  });

async function clickInFrame(page: Page, selector: string) {
  const point = await page.evaluate((sel) => {
    const frame = document.querySelector<HTMLIFrameElement>('[data-testid="mail-frame"]')!;
    const target = frame.contentDocument!.querySelector(sel)!;
    target.scrollIntoView({ block: "center" });
    const outer = frame.getBoundingClientRect();
    const inner = target.getBoundingClientRect();
    return { x: outer.x + inner.x + inner.width / 2, y: outer.y + inner.y + inner.height / 2 };
  }, selector);
  await page.mouse.click(point.x, point.y);
}

test("the inbox lists conversations, and one opens, saves its attachment and is archived", async ({ page }, testInfo) => {
  await openMail(page);
  const rows = page.getByTestId("mail-row");
  await expect(rows.first()).toContainText("Ana Lopez");
  await expect(rows.first()).toContainText("Plan for Friday");
  await expect(rows.first()).toHaveClass(/unread/);
  await expect(page.getByTestId("mail-sync-line")).toContainText("me@example.com");
  await expect(page.getByTestId("mail-sync-line")).toContainText("Last synced");
  await page.screenshot({ path: testInfo.outputPath("mail-list.png") });

  await rows.first().click();
  await expect(page.getByTestId("mail-subject")).toHaveText("Plan for Friday");
  // Two messages; the newest, unread one is open and the earlier one is folded.
  await expect(page.getByTestId("mail-message")).toHaveCount(2);
  await expect(page.getByTestId("mail-frame")).toBeVisible();
  await expect.poll(() => frameText(page)).toContain("Friday at ten");
  // Opening it marks it read, and the list follows.
  await expect(rows.first()).not.toHaveClass(/unread/);
  await page.screenshot({ path: testInfo.outputPath("mail-reader.png") });

  await page.getByTestId("mail-attachment-save").click();
  await expect(page.getByTestId("mail-attachments")).toContainText("Saved to /Users/me/Downloads/plan.pdf");

  await page.getByTestId("mail-archive").click();
  await expect(rows).toHaveCount(2);
  await expect(page.getByTestId("mail-reader")).toHaveCount(0);
  await expect(rows.first()).toContainText("Your invoice for October");
});

test("a clicked link is not followed: the app shows where it goes and offers to open it", async ({ page }, testInfo) => {
  await openMail(page);
  await page.getByTestId("mail-row").first().click();
  await expect(page.getByTestId("mail-frame")).toBeVisible();
  await expect(page.getByTestId("mail-link-card")).toHaveCount(0);

  await clickInFrame(page, "#agenda");
  await expect(page.getByTestId("mail-link-address")).toHaveText("https://example.com/agenda");
  await expect(page.getByTestId("mail-link-open")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("mail-link-card.png") });
  // Still the email, not the page the link points at.
  expect(await frameText(page)).toContain("Friday at ten");

  await page.getByTestId("mail-link-card").getByRole("button", { name: "Close" }).click();
  await expect(page.getByTestId("mail-link-card")).toHaveCount(0);
  // Closing lets go of the link, so clicking the same one again shows its address again.
  await clickInFrame(page, "#agenda");
  await expect(page.getByTestId("mail-link-address")).toHaveText("https://example.com/agenda");
});

test("search reaches mail outside the inbox and opens it alone, without Archive or Bin", async ({ page }, testInfo) => {
  await openMail(page);
  await page.getByTestId("mail-search").fill("invoice");
  await page.getByTestId("mail-search").press("Enter");
  const rows = page.getByTestId("mail-row");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Invoice January");
  await expect(rows.first()).toContainText("Archive");

  await rows.first().click();
  await expect(page.getByTestId("mail-frame")).toBeVisible();
  await expect.poll(() => frameText(page)).toContain("Paid in full.");
  await expect(page.getByTestId("mail-subject")).toHaveText("Invoice January");
  await expect(page.getByTestId("mail-archive")).toHaveCount(0);
  await expect(page.getByTestId("mail-bin")).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("mail-search.png") });

  await page.getByTestId("mail-search-clear").click();
  await expect(rows).toHaveCount(3);
});

test("with no mailbox connected, Mail says what to connect and where", async ({ page }, testInfo) => {
  await page.route("**/v1/mail/status", (route) =>
    route.fulfill({
      json: {
        ok: true, connected: false, address: "", syncing: false, revision: 0,
        last_sync: 0, last_error: "", can_archive: false, can_bin: false,
      },
    }),
  );
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("/");
  await page.getByTestId("nav-mail").click();
  const welcome = page.getByTestId("mail-not-connected");
  await expect(welcome).toContainText("Connectors, Email");
  await expect(welcome).toContainText("app password");
  await page.screenshot({ path: testInfo.outputPath("mail-not-connected.png") });

  await page.getByTestId("mail-open-connectors").click();
  await expect(page.getByTestId("mail-page")).toHaveCount(0);
});
```

The email is clicked by its position on the page (`page.mouse.click`), not through a frame locator. That is a real pointer event through the browser's input path, and it does not depend on the test tool being able to run code inside a frame that has scripts turned off.

- [ ] **Step 4: Run it**

Run: `npx playwright test --project=chromium e2e/mail.spec.ts`
Expected: 4 passed.

- [ ] **Step 5: Look at every new state**

The spec wrote `mail-list.png`, `mail-reader.png`, `mail-link-card.png`, `mail-search.png` and `mail-not-connected.png` under `test-results/`. Open each one and look at it: the list rows, the unread dot, the action buttons on one line, the address card above the email, the search results naming their folder, the not-connected page. Fix what looks wrong before going on. The owner judges this by look.

- [ ] **Step 6: Commit**

```bash
npx tsc --noEmit && npx eslint e2e/mail.spec.ts e2e/mail-data.ts e2e/fixtures.ts
git add surfaces/gui/e2e/mail-data.ts surfaces/gui/e2e/mail.spec.ts surfaces/gui/e2e/fixtures.ts
git commit -m "Walk the Mail reader's main path in the browser tests"
```

### Task 17: The safety tests, in Chromium and WebKit

Three tests open the hostile email and check that nothing in it runs, loads or navigates. They must also pass in WebKit, because the macOS app is a WebKit webview and it does not treat a sandboxed frame the way Chromium does. Chromium alone passing proves nothing about the Mac app.

**Files:**
- Create: `surfaces/gui/e2e/mail-safety.spec.ts`
- Modify: `surfaces/gui/playwright.config.ts`
- Modify: `.github/workflows/ci.yml`, `.github/workflows/release.yml`

- [ ] **Step 1: Write the spec**

`e2e/mail-safety.spec.ts`:

```ts
import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";
import { TRACKER } from "./mail-data";

// An email is untrusted. These three tests open a hostile one and check that nothing in it
// runs, loads or navigates. They run in WebKit as well as Chromium (see playwright.config.ts),
// because the macOS app is a WebKit webview and the two treat a sandboxed frame differently.

// A retry would let a test that fails only sometimes pass, and "sometimes unsafe" is unsafe.
test.describe.configure({ retries: 0 });

const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

/** Open the hostile email and return the list every request to its sender's server lands in. */
async function openHostile(page: Page): Promise<string[]> {
  const asked: string[] = [];
  // Counted where a request would leave the browser. A request the policy refuses never
  // gets this far, though the browser still reports having considered it.
  await page.route(`${TRACKER}/**`, (route) => {
    asked.push(new URL(route.request().url()).pathname);
    return route.fulfill({ status: 200, contentType: "image/png", body: PIXEL });
  });
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto("/");
  await page.getByTestId("nav-mail").click();
  await page.getByTestId("mail-row").filter({ hasText: "You have won" }).click();
  await expect(page.getByTestId("mail-frame")).toBeVisible();
  return asked;
}

const inFrame = <T>(page: Page, read: string) =>
  page.evaluate(`(() => {
    const frame = document.querySelector('[data-testid="mail-frame"]');
    const doc = frame.contentDocument, win = frame.contentWindow;
    return (${read});
  })()`) as Promise<T>;

async function clickInFrame(page: Page, selector: string) {
  const point = await page.evaluate((sel) => {
    const frame = document.querySelector<HTMLIFrameElement>('[data-testid="mail-frame"]')!;
    const target = Document.prototype.querySelector.call(frame.contentDocument!, sel)!;
    target.scrollIntoView({ block: "center" });
    const outer = frame.getBoundingClientRect();
    const inner = target.getBoundingClientRect();
    return { x: outer.x + inner.x + inner.width / 2, y: outer.y + inner.y + inner.height / 2 };
  }, selector);
  await page.mouse.click(point.x, point.y);
}

test("an email's script, its onerror handler and its meta refresh do not run", async ({ page }) => {
  const asked = await openHostile(page);
  // Long enough for a refresh set to zero seconds, and for a script, to have acted.
  await page.waitForTimeout(1500);
  expect(asked).toEqual([]);
  expect(await inFrame<string>(page, "String(win.__ran)")).toBe("undefined");
  expect(await inFrame<string>(page, "win.location.href")).toBe("about:srcdoc");
  expect(await inFrame<string>(page, "Document.prototype.querySelector.call(doc, '#hello').textContent")).toContain("You have won");
});

test("an email's remote image, stylesheet and background are not requested until Show images", async ({ page }) => {
  const asked = await openHostile(page);
  await page.waitForTimeout(1000);
  expect(asked).toEqual([]);

  await page.getByTestId("mail-show-images").click();
  await expect.poll(() => asked).toContain("/pixel.png");
  await page.waitForTimeout(500);
  // Images, and nothing else: no stylesheet, no script, no page.
  expect(asked.filter((path) => !path.endsWith(".png"))).toEqual([]);
});

test("clicking a link in an email requests nothing and shows the address instead", async ({ page }) => {
  const asked = await openHostile(page);
  for (const [selector, address] of [
    ["#plain", `${TRACKER}/plain`],
    ["#self", `${TRACKER}/self`],
    ["#svg-text", `${TRACKER}/svg`],
  ]) {
    await clickInFrame(page, selector);
    await expect(page.getByTestId("mail-link-address")).toHaveText(address);
  }

  // A link that gets its address from an SVG animation has none here: the animation is gone.
  await clickInFrame(page, "#smil-text");
  await expect(page.getByTestId("mail-link-card")).toHaveCount(0);
  // A link inside a template, or after a noscript trick, is not in the email at all.
  const text = await inFrame<string>(page, "Document.prototype.querySelector.call(doc, 'body').innerText");
  expect(text).not.toContain("Shadow link");
  expect(text).not.toContain("Noscript link");

  await page.waitForTimeout(500);
  expect(asked).toEqual([]);
  expect(await inFrame<string>(page, "win.location.href")).toBe("about:srcdoc");
});
```

The spec turns retries off for itself: CI retries a failed test once, and a safety test that fails only sometimes must not pass. Requests are counted in the route handler, where a request would leave the browser. `page.on("request")` is no good for this: a browser reports a request it then refuses under the policy, so it would count requests that never went anywhere.

- [ ] **Step 2: Run it in Chromium**

Run: `npx playwright test --project=chromium e2e/mail-safety.spec.ts`
Expected: 3 passed.

- [ ] **Step 3: See that the tests can fail**

A safety test that cannot fail is worth nothing. Break the protection twice, on purpose, and watch.

First, in `disarm.ts`, change the start of the policy from `default-src 'none'; img-src data:` to `default-src *; img-src *`. Run Step 2 again.
Expected: all 3 fail, each listing `/pixel.png`, `/named-head.png`, `/named-root.png` and `/bg.png` as requested. Undo the change.

Second, comment out the line `strip(el, name);` inside the address loop, so links keep their addresses. Run Step 2 again.
Expected: all 3 fail with the frame never appearing. `disarmEmail` reads its own output back, finds an address still on a link, and refuses the email, so the reader shows its text. Undo the change.

Run Step 2 once more: 3 passed.

- [ ] **Step 4: Add the WebKit project**

In `playwright.config.ts`, change the first import to two:

```ts
import { existsSync } from "node:fs";
import { defineConfig, devices, webkit } from "@playwright/test";
```

and replace the line

```ts
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
```

with

```ts
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    // The macOS app runs in WebKit, and the email reader's safety rests on how the webview
    // treats a sandboxed frame. Chromium passing says nothing about that, so the safety
    // tests run in WebKit as well: always in CI, and on any machine that has it installed.
    ...(process.env.CI || existsSync(webkit.executablePath())
      ? [{ name: "webkit", use: { ...devices["Desktop Safari"] }, testMatch: /mail-safety\.spec\.ts/ }]
      : []),
  ],
```

The WebKit project is there in CI always, and on a developer's machine only once WebKit has been installed for the tests. So `npm run e2e` keeps working on a machine without it, and CI fails loudly if it is ever missing there.

Run: `npx playwright test --list | tail -1`
Expected on a machine without WebKit for the tests: the same total as before this step (the 3 safety tests listed once, under chromium).

- [ ] **Step 5: Install WebKit for the tests, with the owner's word**

This downloads a browser build (about 70 MB) from Playwright's servers. Ask the owner first. On a yes:

Run: `npx playwright install webkit`

On a no, skip Step 6 and say so in the final report: the safety tests then run in WebKit only in CI, on Linux, and Task 18's hand check in the real window is the only evidence from the Mac's own webview.

- [ ] **Step 6: Run the safety tests in WebKit**

Run: `npx playwright test --project=webkit`
Expected: 3 passed.

If a test fails here that passed in Chromium, that is the finding this task exists for. Do not weaken the test. Work out what WebKit did (the plan's reviewer already found one such case, the named elements in Task 2), fix `disarm.ts` or `MailFrame.tsx`, add the case to the hostile email in `mail-data.ts` and to `probe/mail.ts`, and record it in the spec's Probe results.

If the click tests fail only because a click does not give focus in WebKit, apply Task 12, Step 5 (the list of links) and change the third test to look for the addresses in `mail-links`.

- [ ] **Step 7: Install WebKit in CI**

In `.github/workflows/ci.yml`, change

```yaml
        run: npx playwright install --with-deps chromium
```

to

```yaml
        run: npx playwright install --with-deps chromium webkit
```

In `.github/workflows/release.yml`, change the line `          npx playwright install --with-deps chromium` to `          npx playwright install --with-deps chromium webkit`.

- [ ] **Step 8: Run the whole browser suite and commit**

Run: `npm run e2e`
Expected: every spec passing in Chromium, and `mail-safety.spec.ts` passing in WebKit too where WebKit is installed.

```bash
git add surfaces/gui/e2e/mail-safety.spec.ts surfaces/gui/playwright.config.ts .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "Guard the email reader with safety tests that also run in WebKit"
```

### Task 18: The whole thing, once, by hand

**Files:** none changed unless something is found.

- [ ] **Step 1: Run every gate**

Run, from the repository root: `.venv/bin/ruff check coworker tests scripts && .venv/bin/pytest -q`
Run, in `surfaces/gui`: `npx tsc --noEmit && npm run lint && npm test && npm run e2e`
Expected: all green; lint with 0 errors.

- [ ] **Step 2: Try it on a real mailbox, in the real window**

This needs a mailbox connected under Connectors, Email. If none is connected, ask the owner to connect one or to do this step himself; never ask for a password in chat.

Run (in `surfaces/gui`): `npm run tauri dev`. The dev shell starts the sidecar from the repository's `.venv`, so this runs the new backend; a packaged build would not until `packaging/build_dmg.sh` is run, which this plan does not do.

Check, and write down what happened for each:

1. Mail appears in the navigation and lists the inbox within a few seconds.
2. A real newsletter opens looking as it does in a mail app, with its images absent until Show images.
3. Clicking a link in it shows the address card and does not change the email. Open in browser opens the browser.
4. An attachment saves to Downloads and opens.
5. Mark unread, Archive and Move to bin each change the list at once, and the change is there in the mailbox's own web mail.
6. Searching for a word from an old, archived email finds it.
7. Turning the network off, then pressing Refresh, shows a reason and keeps the list.

- [ ] **Step 3: Record and report**

Add what Step 2 showed to the spec's `## Probe results`. Commit any fix with its own message. Then stop: do not build, tag, push or release. Report to the owner what was built, what was verified and how, and anything in Step 2 that could not be tried.
