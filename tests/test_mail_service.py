"""What the Mail screen can ask for, against a mail server in memory."""

from __future__ import annotations

import json
import re
import threading

import pytest
from mail_fakes import ADDRESS, GMAIL_FOLDERS, FakeMailServer, FakeSMTP, connected_secrets, mail

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
    assert result == {"ok": False, "error": "This mailbox cannot move mail"}
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


def test_a_message_being_opened_while_the_mailbox_is_disconnected_is_not_kept(tmp_path, monkeypatch):
    server, service = _service(tmp_path)
    server.add("INBOX", mail("Private", body="Secret words."))
    _synced(service)
    real_message = service._conn.message

    def fetched_then_disconnected(folder, uid):
        fetched = real_message(folder, uid)
        service._store.clear()  # the disconnect lands while the message is being prepared
        return fetched

    monkeypatch.setattr(service._conn, "message", fetched_then_disconnected)
    service.message("INBOX", 1)
    assert service._store.body(ADDRESS, "INBOX", 1, 0.0) is None


def test_saving_from_an_email_that_is_wholly_a_forwarded_email_saves_the_file_that_was_listed(tmp_path):
    from email.mime.message import MIMEMessage

    server, service = _service(tmp_path)
    wrapper = MIMEMessage(mail("Inside", attachment="inner.pdf"))
    wrapper["Subject"], wrapper["From"], wrapper["Date"] = "Fwd: Inside", ADDRESS, mail()["Date"]
    server.add("INBOX", wrapper)
    assert service.message("INBOX", 1)["attachments"][0]["filename"] == "inner.pdf"
    saved = service.save_attachment("INBOX", 1, 0)
    assert saved["path"].endswith("inner.pdf")
    assert (tmp_path / "Downloads" / "inner.pdf").read_bytes() == b"%PDF-fake"


# -- comments, drafts, writing a reply, sending ------------------------------------------
def _writer(tmp_path, *, model=None, sorter=None, language="en", display_name="Shubin", **server_options):
    server, smtp = FakeMailServer(**server_options), FakeSMTP()
    secrets = connected_secrets(tmp_path)
    secrets.put("email:default", {**secrets.get("email:default"), "display_name": display_name})
    service = MailService(
        secrets, tmp_path / "mail.db", imap_factory=server.connect, smtp_factory=smtp.connect,
        complete=model, sort_complete=sorter, language=lambda: language, downloads=tmp_path / "Downloads",
    )
    return server, smtp, service


PLAN = dict(
    sender="Ana Lopez <ana@example.com>", to=f"{ADDRESS}, Ben <ben@example.com>", message_id="<plan@x>",
    references="<root@x>", body="Can we meet on Friday at ten?\nThe budget is due on the 14th.",
    headers={"Cc": "Cy <cy@example.com>"},
)


def _reply_draft(service, server, **options):
    """A conversation in the inbox, synced, with a reply draft started on it."""
    server.add("INBOX", mail("Plan", **PLAN))
    (row,) = _synced(service)
    draft = service.create_draft("INBOX", 1, **options)["draft"]
    return row["key"], draft


def test_comments_are_saved_by_conversation_and_tidied_on_the_way_in(tmp_path):
    _, _, service = _writer(tmp_path)
    key = "a" * 16
    assert service.comments(key) == {"ok": True, "comments": [], "note": ""}
    saved = service.put_comments(
        key,
        [
            {"message_id": "<1@x>", "quote": "  meet on\n Friday ", "note": "Yes.\nTen."},
            {"message_id": "<1@x>", "quote": "", "note": "a comment on nothing is dropped"},
            {"message_id": "<1@x>", "quote": "q" * 5000, "note": ""},
            "not a comment",
        ],
        "Say hello.",
    )
    assert saved == {"ok": True}
    got = service.comments(key)
    assert got["comments"][0] == {"message_id": "<1@x>", "quote": "meet on Friday", "note": "Yes.\nTen."}
    assert len(got["comments"]) == 2 and len(got["comments"][1]["quote"]) == 1000
    assert got["note"] == "Say hello."
    for bad in (service.put_comments("../etc", [], ""), service.put_comments(key, "x", ""), service.put_comments(key, [{}] * 101, "")):
        assert bad == {"ok": False, "error": "These comments could not be saved."}


def test_reply_answers_the_sender_and_reply_all_adds_everyone_else_but_you(tmp_path):
    server, _, service = _writer(tmp_path)
    _, draft = _reply_draft(service, server)
    assert (draft["to"], draft["cc"], draft["subject"]) == ("Ana Lopez <ana@example.com>", "", "Re: Plan")
    assert (draft["reply"], draft["answers"], draft["body"], draft["interrupted"]) == (
        True, "Ana Lopez <ana@example.com>", "", False,
    )

    server.add("INBOX", mail("Re: Other", **{**PLAN, "message_id": "<other@x>", "references": "<other-root@x>"}))
    all_of_them = service.create_draft("INBOX", 2, reply_all=True)["draft"]
    assert all_of_them["to"] == "Ana Lopez <ana@example.com>"
    assert all_of_them["cc"] == "Ben <ben@example.com>, Cy <cy@example.com>"
    assert all_of_them["subject"] == "Re: Other"


def test_a_reply_goes_where_the_message_asks_and_a_follow_up_to_your_own_goes_to_its_recipients(tmp_path):
    server, _, service = _writer(tmp_path)
    server.add("INBOX", mail("List", sender="Ana <ana@example.com>", headers={"Reply-To": '"Team, The" <team@example.com>'}))
    server.add("Sent", mail("Mine", sender=f"Me <{ADDRESS}>", to="Ana <ana@example.com>", message_id="<mine@x>"))
    assert service.create_draft("INBOX", 1)["draft"]["to"] == '"Team, The" <team@example.com>'
    assert service.create_draft("Sent", 1)["draft"]["to"] == "Ana <ana@example.com>"


def test_a_conversation_has_one_reply_draft_and_the_reader_is_told_of_it(tmp_path):
    server, _, service = _writer(tmp_path)
    key, draft = _reply_draft(service, server)
    assert service.create_draft("INBOX", 1, reply_all=True)["draft"]["id"] == draft["id"]
    thread = service.thread(key)
    assert (thread["draft"], thread["answer"]) == (
        draft["id"], {"folder": "INBOX", "uid": 1, "message_id": "<plan@x>"},
    )
    assert draft["answers_id"] == "<plan@x>"
    assert service.message("INBOX", 1)["draft"] == draft["id"]
    assert service.draft(draft["id"])["draft"]["id"] == draft["id"]
    assert [d["id"] for d in service.drafts()["drafts"]] == [draft["id"]]
    assert service.create_draft("INBOX", 99) == {"ok": False, "error": "This message is no longer in the mailbox."}
    assert service.create_draft("INBOX", 0)["ok"] is False


def test_a_reply_answers_the_newest_message_that_came_in_not_your_own_last_word(tmp_path):
    server, _, service = _writer(tmp_path)
    server.add("INBOX", mail("Plan", message_id="<a@x>", days_ago=2))
    server.add("Sent", mail("Re: Plan", sender=ADDRESS, to="ana@example.com", message_id="<b@x>", references="<a@x>", days_ago=1))
    (row,) = _synced(service)
    assert service.thread(row["key"])["answer"] == {"folder": "INBOX", "uid": 1, "message_id": "<a@x>"}


def test_a_reply_left_empty_on_an_earlier_message_is_started_again_for_the_newest(tmp_path):
    server, _, service = _writer(tmp_path)
    server.add("INBOX", mail("Plan", sender="Ana <ana@example.com>", message_id="<a@x>", body="First.", days_ago=2))
    (row,) = _synced(service)
    old = service.create_draft("INBOX", 1)["draft"]
    server.add("INBOX", mail("Re: Plan", sender="Ben <ben@example.com>", message_id="<b@x>", references="<a@x>", body="Second.", days_ago=1))
    _synced(service)
    assert service.thread(row["key"])["answer"]["message_id"] == "<b@x>"

    # Nothing was written in it, so it would only answer the wrong message.
    new = service.create_draft("INBOX", 2)["draft"]
    assert (new["to"], new["answers_id"]) == ("Ben <ben@example.com>", "<b@x>")
    assert new["id"] != old["id"] and [d["id"] for d in service.drafts()["drafts"]] == [new["id"]]
    assert service._store.draft(ADDRESS, new["id"])["orig_text"] == "Second."

    # Once it holds the user's words it is kept, and says which message it answers.
    service.update_draft(new["id"], {"body": "Half a thought"})
    server.add("INBOX", mail("Re: Plan", sender="Ana <ana@example.com>", message_id="<c@x>", references="<a@x> <b@x>"))
    _synced(service)
    kept = service.create_draft("INBOX", 3)["draft"]
    assert (kept["id"], kept["answers_id"], kept["body"]) == (new["id"], "<b@x>", "Half a thought")
    assert service.thread(row["key"])["answer"]["message_id"] == "<c@x>"


def test_an_address_that_is_not_what_it_looks_like_is_left_out_of_a_reply():
    import email

    from coworker.mail.service import reply_recipients

    # As the bytes arrive from a server: an encoded word where the name of the mailbox
    # should be is shown one way and sent another, so it is not offered at all.
    raw = email.message_from_string(
        "From: Ana <ana@example.com>\n"
        "Reply-To: =?utf-8?q?x?=@evil.example, Billing <billing@example.com>\n"
        f"To: {ADDRESS}, Odd <o\tdd@example.com>, Cy <cy@example.com>\n\nHello."
    )
    assert reply_recipients(raw, ADDRESS, True) == ("Billing <billing@example.com>", "Cy <cy@example.com>")


def test_a_reply_to_someone_who_asks_for_answers_at_your_own_address_still_goes_to_them(tmp_path):
    server, _, service = _writer(tmp_path)
    server.add("INBOX", mail("Trick", sender="Ana <ana@example.com>", to="Ben <ben@example.com>", headers={"Reply-To": ADDRESS}))
    # Not a follow-up to your own message: it is theirs, so it does not go to its recipients.
    assert service.create_draft("INBOX", 1)["draft"]["to"] == ADDRESS


def test_a_draft_started_while_the_mailbox_is_being_disconnected_is_not_kept(tmp_path, monkeypatch):
    server, _, service = _writer(tmp_path)
    server.add("INBOX", mail("Plan", message_id="<plan@x>", body="Private words."))
    fetch = service._conn.message

    def fetch_then_disconnect(folder, uid):
        msg = fetch(folder, uid)
        service._store.clear()
        return msg

    monkeypatch.setattr(service._conn, "message", fetch_then_disconnect)
    assert service.create_draft("INBOX", 1) == {"ok": False, "error": "Email is not connected."}
    assert service._store._all("SELECT id FROM draft") == []


def test_new_message_gives_back_the_one_still_empty_instead_of_another(tmp_path):
    _, _, service = _writer(tmp_path)
    first = service.create_draft()["draft"]
    assert (first["reply"], first["to"], first["thread_key"]) == (False, "", "")
    assert service.create_draft()["draft"]["id"] == first["id"]
    assert service.update_draft(first["id"], {"to": "ana@example.com"}) == {"ok": True}
    assert service.create_draft()["draft"]["id"] != first["id"]


def test_a_draft_keeps_what_is_typed_with_each_header_on_one_line(tmp_path):
    _, _, service = _writer(tmp_path)
    draft = service.create_draft()["draft"]
    service.update_draft(draft["id"], {"to": "ana@example.com\nBcc: x@example.com", "subject": "Hi\r\nthere", "body": "Line one\nLine two", "id": "other"})
    kept = service.draft(draft["id"])["draft"]
    assert (kept["id"], kept["to"], kept["subject"]) == (draft["id"], "ana@example.com Bcc: x@example.com", "Hi there")
    assert kept["body"] == "Line one\nLine two"
    assert service.update_draft("gone", {"body": "x"}) == {"ok": False, "error": "This draft no longer exists."}

    # A long list of recipients is kept whole. One that is too long is refused, never cut:
    # cut short, it would be sent to the wrong people.
    sixty = ", ".join(f"Person Number {n} <person.number{n}@department.example.com>" for n in range(60))
    assert service.update_draft(draft["id"], {"cc": sixty, "body": "x"}) == {"ok": True}
    assert service.draft(draft["id"])["draft"]["cc"] == sixty
    assert service.update_draft(draft["id"], {"cc": "a@example.com, " * 2000}) == {
        "ok": False, "error": "That is too many recipients for one message.",
    }
    assert service.update_draft(draft["id"], {"subject": "s" * 999})["error"] == "The subject is too long."
    assert service.update_draft(draft["id"], {"body": "b" * 200_001})["error"] == "The message is too long to save."
    assert service.update_draft(draft["id"], {"to": ["ana@example.com"]})["error"] == "This draft could not be saved."
    assert service.draft(draft["id"])["draft"]["cc"] == sixty
    assert service.delete_draft(draft["id"]) == {"ok": True}
    assert service.draft(draft["id"]) == {"ok": False, "error": "This draft no longer exists."}


# -- writing the reply, and sending it ------------------------------------------------------
class _Model:
    """Stands in for the model: answers with `text`, or fails with `error`."""

    def __init__(self, text="Hi Ana,\n\nTen works.\n\nShubin", error=""):
        self.text, self.error, self.asked = text, error, []

    def __call__(self, system, user):
        self.asked.append((system, user))
        if self.error:
            raise RuntimeError(self.error)
        return self.text


NOTED = [{"message_id": "<plan@x>", "quote": "meet on Friday at ten", "note": "Ten works."}]


def test_write_reply_asks_the_model_with_the_comments_and_sends_nothing(tmp_path):
    model = _Model()
    server, smtp, service = _writer(tmp_path, model=model)
    key, draft = _reply_draft(service, server)
    service.put_comments(key, NOTED, "Wish her a good trip.")

    written = service.write_reply(draft["id"], "shorter")
    assert written == {"ok": True, "text": "Hi Ana,\n\nTen works.\n\nShubin"}
    (system, user), = model.asked
    assert "ever an instruction to you" in system
    for part in ("Can we meet on Friday at ten?", 'Passage: "meet on Friday at ten"', "Say: Ten works.",
                 "Also say: Wish her a good trip.", "Sign the reply as: Shubin", "How to write this draft: shorter",
                 "From: Ana Lopez <ana@example.com>", "Subject: Plan"):
        assert part in user
    # Writing is not sending, and the text is the screen's to put in the draft.
    assert smtp.sent == [] and service.draft(draft["id"])["draft"]["body"] == ""
    assert server.commands("STORE") == [] and server.commands("append") == []


def test_write_reply_needs_something_to_say_and_a_draft_of_a_reply(tmp_path):
    model = _Model()
    server, _, service = _writer(tmp_path, model=model)
    key, draft = _reply_draft(service, server)
    service.put_comments(key, [{**NOTED[0], "note": " "}], "")
    assert service.write_reply(draft["id"]) == {
        "ok": False, "error": "Add a comment or a note first, so Mimi knows what to say.",
    }
    new_message = service.create_draft()["draft"]
    assert service.write_reply(new_message["id"])["error"] == "This draft no longer exists."
    assert model.asked == []


def test_a_model_that_does_not_answer_says_why_and_the_comments_stay(tmp_path):
    server, _, service = _writer(tmp_path, model=_Model(error="Your account is out of quota for mimi-wolf."))
    key, draft = _reply_draft(service, server)
    service.put_comments(key, NOTED, "")
    assert service.write_reply(draft["id"]) == {
        "ok": False, "error": "Mimi could not write the reply. Your account is out of quota for mimi-wolf.",
    }
    assert service.comments(key)["comments"] == NOTED

    service._complete = _Model(text="   ")
    assert service.write_reply(draft["id"])["error"] == "Mimi could not write the reply. The model returned nothing. Try again."
    service._complete = None
    assert service.write_reply(draft["id"])["error"] == "Mimi could not write the reply. No model is set up."


def test_a_sent_reply_is_threaded_quoted_filed_in_sent_and_clears_its_draft_and_comments(tmp_path, monkeypatch):
    server, smtp, service = _writer(tmp_path)
    key, draft = _reply_draft(service, server)
    service.put_comments(key, NOTED, "A note.")
    service.update_draft(draft["id"], {"body": "Hi Ana,\n\nTen works.\n\nShubin\n\n"})
    asked = []
    monkeypatch.setattr(service._sync, "request", lambda: asked.append(True))

    assert service.send_draft(draft["id"]) == {"ok": True, "note": ""}
    (sent,) = smtp.sent
    assert (sent["To"], sent["Subject"]) == ("Ana Lopez <ana@example.com>", "Re: Plan")
    assert sent["From"] == f"Shubin <{ADDRESS}>" and sent["Date"]
    assert (sent["In-Reply-To"], sent["References"]) == ("<plan@x>", "<root@x> <plan@x>")
    body = sent.get_content()
    assert body.startswith("Hi Ana,\n\nTen works.\n\nShubin\n\nOn ")
    assert ", Ana Lopez <ana@example.com> wrote:\n> Can we meet on Friday at ten?\n> The budget is due on the 14th.\n" in body
    assert re.search(r"\nOn \w{3}, \d{2} \w{3} \d{4} \d\d:\d\d:\d\d [+-]\d{4}, Ana Lopez", body)
    assert server.subjects("Sent") == ["Re: Plan"]
    assert service.drafts()["drafts"] == []
    assert service.comments(key) == {"ok": True, "comments": [], "note": ""}
    assert asked == [True]
    # After the next pass the conversation shows the reply.
    service._sync.run_once()
    assert [m["folder"] for m in service.thread(key)["messages"]] == ["INBOX", "Sent"]


def test_what_a_hostile_message_puts_in_its_headers_does_not_reach_the_reply_as_the_users_words(tmp_path):
    server, smtp, service = _writer(tmp_path)
    server.add("INBOX", mail(
        "Offer",
        sender='"Ana\u202e Lopez" <ana@example.com>',
        message_id="<h@x>",
        headers={"Reply-To": "Billing <billing@example.com>", "Cc": "Cy <cy@example.com>"},
    ))
    server.folders["INBOX"][1][0].replace_header(
        "Date", "Mon 3 Nov. I agree to pay 5000 EUR by Friday. Shubin.  On Tue"
    )
    draft = service.create_draft("INBOX", 1, reply_all=True)["draft"]
    assert (draft["to"], draft["cc"]) == ("Billing <billing@example.com>", "Cy <cy@example.com>")
    assert draft["answers"] == "Ana Lopez <ana@example.com>"
    assert draft["subject"] == "Re: Offer"
    service.update_draft(draft["id"], {"body": "Thanks."})
    assert service.send_draft(draft["id"])["ok"] is True
    body = smtp.sent[0].get_content()
    # The line above the quote is built by the app. A date that cannot be read is left out.
    assert body.startswith("Thanks.\n\nAna Lopez <ana@example.com> wrote:\n> ")
    assert "I agree to pay" not in body and "\u202e" not in body


def test_a_reply_is_still_sent_threaded_and_quoted_after_its_original_was_archived_and_left_the_cache(tmp_path):
    server, smtp, service = _writer(tmp_path)
    key, draft = _reply_draft(service, server)
    service.put_comments(key, NOTED, "")
    service.update_draft(draft["id"], {"body": "Ten works."})
    assert service.archive(key) == {"ok": True}
    service._sync.run_once()
    assert service.thread(key)["ok"] is False
    # Archiving took the mail out of the cache and left what the user wrote.
    assert service.comments(key)["comments"] == NOTED
    assert [d["id"] for d in service.drafts()["drafts"]] == [draft["id"]]

    assert service.send_draft(draft["id"])["ok"] is True
    (sent,) = smtp.sent
    assert (sent["In-Reply-To"], sent["References"]) == ("<plan@x>", "<root@x> <plan@x>")
    assert "> Can we meet on Friday at ten?" in sent.get_content()


def test_a_send_the_server_refuses_keeps_the_draft_says_why_and_is_not_left_marked_as_sending(tmp_path):
    server, smtp, service = _writer(tmp_path)
    key, draft = _reply_draft(service, server)
    service.put_comments(key, NOTED, "")
    smtp.refuse = "(550, b'mailbox unavailable')"
    assert service.send_draft(draft["id"]) == {
        "ok": False, "error": "The mail server did not accept the message: 550 mailbox unavailable",
    }
    kept = service.draft(draft["id"])["draft"]
    assert kept["interrupted"] is False
    assert service._store.draft(ADDRESS, draft["id"])["send_started_at"] == 0
    assert service.comments(key)["comments"] == NOTED and server.subjects("Sent") == []

    smtp.refuse = ""
    service._secrets.put("email:default", {**service._secrets.get("email:default"), "app_password": "wrong"})
    assert service.send_draft(draft["id"])["error"].startswith("Could not sign in to send mail: 535 authentication failed")


def test_a_send_that_got_no_answer_is_not_called_a_refusal(tmp_path, monkeypatch):
    server, smtp, service = _writer(tmp_path)
    _, draft = _reply_draft(service, server)
    # The message was handed over and nothing came back: it may have gone.
    smtp.refuse = "timed out"
    assert service.send_draft(draft["id"]) == {
        "ok": False,
        "error": "The connection was lost while sending, so the message may or may not have gone. "
        "Check Sent before sending again.",
    }
    # The server was never reached: nothing went.
    smtp.refuse, smtp.unreachable = "", "[Errno 8] nodename nor servname provided, or not known"
    assert service.send_draft(draft["id"]) == {
        "ok": False,
        "error": "Could not reach the mail server, so nothing was sent. Check your connection and try again.",
    }
    # One recipient refused by name.
    smtp.unreachable, smtp.refuse = "", "{'ana@example.com': (550, b'5.1.1 No such user')}"
    assert service.send_draft(draft["id"])["error"] == (
        "The mail server did not accept the message: ana@example.com: 550 5.1.1 No such user"
    )
    assert smtp.sent == [] and service.draft(draft["id"])["ok"] is True


def test_a_message_that_cannot_be_put_together_is_never_marked_as_on_its_way(tmp_path, monkeypatch):
    from coworker.mail import service as service_module

    server, smtp, service = _writer(tmp_path)
    _, draft = _reply_draft(service, server)
    marks = []
    monkeypatch.setattr(service._store, "mark_sending", lambda *args: marks.append(args))

    def broken(*args, **kwargs):
        raise ValueError("Header values may not contain linefeed or carriage return characters")

    monkeypatch.setattr(service_module, "compose_message", broken)
    answer = service.send_draft(draft["id"])
    assert answer["ok"] is False and answer["error"].startswith("This message could not be put together: ")
    assert marks == [] and smtp.sent == [] and service.draft(draft["id"])["ok"] is True


def test_a_message_the_server_accepted_is_a_success_even_when_no_copy_could_be_filed(tmp_path):
    server, smtp, service = _writer(tmp_path)
    _, draft = _reply_draft(service, server)
    server.read_only.add("Sent")
    assert service.send_draft(draft["id"]) == {
        "ok": True, "note": "Sent, but no copy could be saved in your Sent folder.",
    }
    assert len(smtp.sent) == 1 and service.drafts()["drafts"] == []


def test_a_second_send_of_a_draft_already_on_its_way_is_refused(tmp_path):
    server, smtp, service = _writer(tmp_path)
    _, draft = _reply_draft(service, server)
    on_its_way, let_go, results = threading.Event(), threading.Event(), []

    def hold():
        on_its_way.set()
        assert let_go.wait(5)

    smtp.before_accepting = hold
    first = threading.Thread(target=lambda: results.append(service.send_draft(draft["id"])))
    first.start()
    assert on_its_way.wait(5)
    assert service.send_draft(draft["id"]) == {"ok": False, "error": "This message is already being sent."}
    # A send under way is not a send cut short.
    assert service.draft(draft["id"])["draft"]["interrupted"] is False
    let_go.set()
    first.join(5)
    assert results == [{"ok": True, "note": ""}] and len(smtp.sent) == 1


def test_a_second_send_arriving_just_as_the_first_ends_does_not_find_the_draft(tmp_path, monkeypatch):
    server, smtp, service = _writer(tmp_path)
    _, draft = _reply_draft(service, server)
    delete, late = service._store.delete_draft, []

    def delete_while_another_send_arrives(account, draft_id):
        # The server has accepted the message and the draft is about to go.
        late.append(service.send_draft(draft_id))
        return delete(account, draft_id)

    monkeypatch.setattr(service._store, "delete_draft", delete_while_another_send_arrives)
    assert service.send_draft(draft["id"])["ok"] is True
    assert late == [{"ok": False, "error": "This message is already being sent."}]
    assert len(smtp.sent) == 1


def test_a_draft_whose_send_was_cut_short_carries_the_warning_and_can_be_sent_again(tmp_path):
    server, smtp, service = _writer(tmp_path)
    _, draft = _reply_draft(service, server)
    service._store.mark_sending(draft["id"], 123.0)  # as a send leaves it when the app stops
    assert service.draft(draft["id"])["draft"]["interrupted"] is True
    assert service.drafts()["drafts"][0]["interrupted"] is True
    assert service.send_draft(draft["id"])["ok"] is True
    assert len(smtp.sent) == 1


def test_a_message_with_no_recipient_or_a_bad_one_is_refused_before_any_server_is_asked(tmp_path):
    _, smtp, service = _writer(tmp_path)
    draft = service.create_draft()["draft"]
    assert service.send_draft(draft["id"]) == {"ok": False, "error": "Add at least one recipient."}
    service.update_draft(draft["id"], {"subject": "Hello", "body": "Hi."})
    for typed, said in (
        ("ana@example.com, ben", '"ben" is not an email address.'),
        ("Ana Lopez ana@example.com", '"Ana Lopez ana@example.com" is not an email address.'),
        ("@example.com", '"@example.com" is not an email address.'),
        ("Ana <ana@example.com> and friends", '"Ana <ana@example.com> and friends" is not an email address.'),
        (" , ; ", "Add at least one recipient."),
    ):
        service.update_draft(draft["id"], {"to": typed})
        assert service.send_draft(draft["id"]) == {"ok": False, "error": said}
    assert smtp.sent == []
    # People separate addresses with semicolons and leave one at the end; a comma inside
    # a quoted name belongs to the name.
    service.update_draft(draft["id"], {"to": '"Lopez, Ana" <ana@example.com>; Zoë <zoe@example.com>,', "cc": "ben@example.com;"})
    assert service.send_draft(draft["id"]) == {"ok": True, "note": ""}
    (sent,) = smtp.sent
    assert (sent["To"], sent["Cc"]) == ('"Lopez, Ana" <ana@example.com>, Zoë <zoe@example.com>', "ben@example.com")
    assert (sent["Subject"], sent["In-Reply-To"]) == ("Hello", None)
    assert sent.get_content() == "Hi.\n"
    assert service.send_draft("gone") == {"ok": False, "error": "This draft no longer exists."}


def test_a_search_result_takes_comments_and_a_written_reply_like_any_other_message(tmp_path):
    model = _Model()
    server, smtp, service = _writer(tmp_path, model=model)
    uid = server.add("Archive", mail("Invoice January", sender="Billing <billing@example.com>", message_id="<inv@x>", body="Paid in full."))
    opened = service.message("Archive", uid)
    assert opened["draft"] == ""
    key = opened["thread_key"]
    service.put_comments(key, [{"message_id": "<inv@x>", "quote": "Paid in full", "note": "Thank you."}], "")
    draft = service.create_draft("Archive", uid)["draft"]
    assert draft["thread_key"] == key and service.message("Archive", uid)["draft"] == draft["id"]
    assert service.write_reply(draft["id"])["ok"] is True
    assert 'Passage: "Paid in full"' in model.asked[0][1]
    service.update_draft(draft["id"], {"body": "Thank you."})
    assert service.send_draft(draft["id"])["ok"] is True
    assert smtp.sent[0]["In-Reply-To"] == "<inv@x>"


def test_disconnecting_takes_comments_and_drafts_and_nothing_is_saved_while_disconnected(tmp_path):
    server, _, service = _writer(tmp_path)
    key, draft = _reply_draft(service, server)
    service.put_comments(key, NOTED, "")
    service._secrets.delete("email:default")
    # Still on disk until the cache is emptied: reading by account would say "nothing"
    # either way, so the tables themselves are looked at.
    assert service._store._all("SELECT id FROM draft") and service._store._all("SELECT quote FROM comment")
    service.forget()
    assert service._store._all("SELECT id FROM draft") == []
    assert service._store._all("SELECT quote FROM comment") == []
    not_connected = {"ok": False, "error": "Email is not connected."}
    assert service.put_comments(key, NOTED, "") == not_connected
    assert service.create_draft() == not_connected
    assert service.update_draft(draft["id"], {"body": "x"}) == not_connected
    assert service.delete_draft(draft["id"]) == not_connected
    assert service.write_reply(draft["id"]) == not_connected
    assert service.send_draft(draft["id"]) == not_connected


# -- sorting -----------------------------------------------------------------------------
class _Sorter:
    """Stands in for the model that sorts: says "needs_reply" for every conversation asked
    about, unless told to fail or to answer something else."""

    def __init__(self, error="", answer=None):
        self.error, self.answer, self.asked = error, answer, []

    def __call__(self, system, user):
        self.asked.append((system, user))
        if self.error:
            raise RuntimeError(self.error)
        if self.answer is not None:
            return self.answer
        keys = [line.split()[2] for line in user.splitlines() if line.startswith("===== CONVERSATION ")]
        return json.dumps([{"key": key, "category": "needs_reply", "summary": f"About {key[:4]}."} for key in keys])


def _inbox_for_sorting(server):
    server.add("INBOX", mail("Friday?", sender="Ana <ana@example.com>", message_id="<ana@x>", body="Can we meet?", days_ago=3))
    server.add("INBOX", mail("Weekly digest", sender="News <news@example.com>", message_id="<news@x>", headers={"List-Unsubscribe": "<mailto:u@example.com>"}, days_ago=2))
    server.add("INBOX", mail("Budget", sender="Ben <ben@secret.example>", message_id="<ben@x>", body="Confidential numbers.", days_ago=1))
    server.add("INBOX", mail("Plan", sender="Cy <cy@example.com>", message_id="<cy@x>", days_ago=5))
    server.add("Sent", mail("Re: Plan", sender=ADDRESS, to="cy@example.com", message_id="<me@x>", references="<cy@x>", days_ago=4))


def _turn_sorting_on(service, monkeypatch):
    """As the screen does, minus the pass that turning it on asks for: the tests run their
    passes themselves, one at a time."""
    monkeypatch.setattr(service._sync, "request", lambda: False)
    assert service.put_settings({"sorting": True})["sorting"] is True


def _by_subject(service, tab="all"):
    return {t["subject"]: (t["category"], t["summary"]) for t in service.threads(tab)["threads"]}


def test_sorting_is_off_until_turned_on_and_then_no_model_is_asked(tmp_path):
    sorter = _Sorter()
    server, _, service = _writer(tmp_path, sorter=sorter)
    _inbox_for_sorting(server)
    service._sync.run_once()
    status = service.status()
    assert (status["sorting"], status["sorting_asked"]) == (False, False)
    assert sorter.asked == []
    assert set(_by_subject(service).values()) == {("", "")}
    # A tab asked for while sorting is off is the whole inbox.
    assert len(service.threads("needs_reply")["threads"]) == 4
    assert service.settings() == {"ok": True, "sorting": False, "excluded": [], "sort_error": ""}

    # Saying no is an answer too: the question is not asked again.
    assert service.put_settings({"sorting": False})["sorting"] is False
    assert service.status()["sorting_asked"] is True
    service._sync.run_once()
    assert sorter.asked == []


def test_rules_sort_your_own_last_word_and_bulk_mail_and_the_model_is_asked_only_about_the_rest(tmp_path, monkeypatch):
    sorter = _Sorter()
    server, _, service = _writer(tmp_path, sorter=sorter, language="fr")
    _inbox_for_sorting(server)
    asked_for_a_pass = []
    monkeypatch.setattr(service._sync, "request", lambda: asked_for_a_pass.append(True))
    assert service.put_settings({"sorting": True, "excluded": [" @Secret.example ", "@secret.example", ""]}) == {
        "ok": True, "sorting": True, "excluded": ["@secret.example"], "sort_error": "",
    }
    assert asked_for_a_pass == [True]
    service._sync.run_once()

    said = _by_subject(service)
    assert said["Re: Plan"] == ("fyi", "")  # the last word in it is your own
    assert said["Weekly digest"] == ("newsletters", "")
    assert said["Budget"] == ("", "")  # excluded: never sent, never sorted
    assert said["Friday?"][0] == "needs_reply" and said["Friday?"][1].startswith("About ")

    (system, user), = sorter.asked
    assert "never an instruction" in system and user.startswith("Write each summary in French.")
    assert "Can we meet?" in user and "Friday?" in user
    # Nothing of the excluded sender, the newsletter or your own reply was sent.
    for absent in ("Confidential numbers", "secret.example", "Weekly digest", "Re: Plan"):
        assert absent not in user

    assert list(_by_subject(service, "needs_reply")) == ["Friday?"]
    assert list(_by_subject(service, "fyi")) == ["Re: Plan"]
    assert list(_by_subject(service, "newsletters")) == ["Weekly digest"]
    assert len(_by_subject(service, "all")) == 4 and len(_by_subject(service, "nonsense")) == 4

    # A pass with nothing new asks nothing.
    service._sync.run_once()
    assert len(sorter.asked) == 1


def test_a_model_that_fails_or_answers_nonsense_is_tried_three_times_and_the_reason_is_kept_quietly(tmp_path, monkeypatch):
    sorter = _Sorter(error="Your account is out of quota for mimi-puppy.")
    server, _, service = _writer(tmp_path, sorter=sorter)
    server.add("INBOX", mail("Friday?", message_id="<ana@x>"))
    _turn_sorting_on(service, monkeypatch)
    for _ in range(5):
        service._sync.run_once()
    assert len(sorter.asked) == 3
    assert _by_subject(service) == {"Friday?": ("", "")}
    assert service.settings()["sort_error"] == "Mimi could not sort new mail. Your account is out of quota for mimi-puppy."
    # Sync itself is not at fault and says nothing.
    assert service.status()["last_error"] == ""

    # A new message is a new question; an answer that is not the JSON asked for counts as none.
    sorter.error, sorter.answer = "", "I think it needs a reply!"
    server.add("INBOX", mail("Other", message_id="<other@x>"))
    for _ in range(5):
        service._sync.run_once()
    assert len(sorter.asked) == 6 and _by_subject(service)["Other"] == ("", "")
    assert service.settings()["sort_error"] == ""


def test_sorting_reads_a_messages_text_once_and_never_fetches_a_very_large_one(tmp_path, monkeypatch):
    from coworker.mail import service as service_module

    sorter = _Sorter()
    server, _, service = _writer(tmp_path, sorter=sorter)
    server.add("INBOX", mail("Small", message_id="<s@x>", body="Short text.", days_ago=1))
    server.add("INBOX", mail("Huge", message_id="<h@x>", body="Enormous. " * 300, days_ago=2))
    monkeypatch.setattr(service_module, "_SORT_MAX_BYTES", 1000)
    _turn_sorting_on(service, monkeypatch)
    service._sync.run_once()
    user = sorter.asked[0][1]
    assert "Short text." in user and "Enormous." not in user and "Subject: Huge" in user
    fetched = [entry for entry in server.commands("FETCH") if "BODY.PEEK[]" in str(entry)]
    assert len(fetched) == 1
    # Sorting keeps no copy of mail the user has not opened.
    assert service._store._all("SELECT uid FROM body") == []
    # Once opened, the text is in the cache, and sorting a later message reads it from there.
    assert service.message("INBOX", 1)["text"].strip() == "Short text."
    assert [row["uid"] for row in service._store._all("SELECT uid FROM body")] == [1]


def test_sixty_conversations_are_sorted_in_a_pass_twenty_to_a_request(tmp_path, monkeypatch):
    sorter = _Sorter()
    server, _, service = _writer(tmp_path, sorter=sorter)
    for n in range(70):
        server.add("INBOX", mail(f"Subject {n}", message_id=f"<{n}@x>", days_ago=n / 100))
    _turn_sorting_on(service, monkeypatch)
    service._sync.run_once()
    assert len(sorter.asked) == 3
    assert [user.count("===== CONVERSATION ") for _, user in sorter.asked] == [20, 20, 20]
    sorted_now = [t for t in service.threads()["threads"] if t["category"]]
    assert len(sorted_now) == 60
    # Newest first: the ten left for the next pass are the oldest.
    assert {t["subject"] for t in service.threads()["threads"] if not t["category"]} == {f"Subject {n}" for n in range(60, 70)}
    service._sync.run_once()
    assert len(sorter.asked) == 4 and all(t["category"] for t in service.threads()["threads"])


def test_turning_sorting_off_forgets_what_it_said_and_excluding_a_sender_hides_it(tmp_path, monkeypatch):
    sorter = _Sorter()
    server, _, service = _writer(tmp_path, sorter=sorter)
    server.add("INBOX", mail("Friday?", sender="Ana <ana@example.com>", message_id="<ana@x>"))
    _turn_sorting_on(service, monkeypatch)
    service._sync.run_once()
    assert _by_subject(service)["Friday?"][0] == "needs_reply"

    service.put_settings({"excluded": ["ana@example.com"]})
    assert _by_subject(service)["Friday?"] == ("", "")
    assert _by_subject(service, "needs_reply") == {}
    # Gone from the cache, not only from sight: un-excluding does not bring it back.
    assert service._store._all("SELECT thread_key FROM thread_ai") == []
    service.put_settings({"excluded": []})
    assert _by_subject(service)["Friday?"] == ("", "")
    service._sync.run_once()
    assert _by_subject(service)["Friday?"][0] == "needs_reply" and len(sorter.asked) == 2

    service.put_settings({"sorting": False})
    assert _by_subject(service)["Friday?"] == ("", "")
    assert service._store._all("SELECT thread_key FROM thread_ai") == []
    service._sync.run_once()
    assert len(sorter.asked) == 2


def test_turning_sorting_off_or_excluding_a_sender_stops_a_pass_that_is_under_way(tmp_path, monkeypatch):
    server, _, service = _writer(tmp_path)
    for n in range(25):
        server.add("INBOX", mail(f"From Ana {n}", sender="Ana <ana@example.com>", message_id=f"<a{n}@x>", days_ago=n / 100))
    for n in range(25):
        server.add("INBOX", mail(f"From Ben {n}", sender="Ben <ben@secret.example>", message_id=f"<b{n}@x>", days_ago=1 + n / 100))
    asked = []

    def exclude_ben_during_the_first_request(system, user):
        asked.append(user)
        if len(asked) == 1:
            service.put_settings({"excluded": ["@secret.example"]})
        return _Sorter()(system, user)

    service._sort_complete = exclude_ben_during_the_first_request
    _turn_sorting_on(service, monkeypatch)
    service._sync.run_once()
    # The first request held Ana's twenty newest; the five of hers left go next; none of
    # Ben's is sent once he is excluded.
    assert len(asked) == 2 and all("secret.example" not in user for user in asked)
    assert {t["subject"] for t in service.threads()["threads"] if t["category"]} == {f"From Ana {n}" for n in range(25)}

    def turn_off_during_the_request(system, user):
        asked.append(user)
        service.put_settings({"sorting": False})
        return _Sorter()(system, user)

    for n in range(45):
        server.add("INBOX", mail(f"New {n}", message_id=f"<n{n}@x>", days_ago=n / 1000))
    service._sort_complete = turn_off_during_the_request
    service.put_settings({"excluded": []})
    service._sync.run_once()
    # One request was already on its way. Its answer is not written, and no more are sent.
    assert len(asked) == 3
    assert service._store._all("SELECT thread_key FROM thread_ai") == []


def test_mail_from_excluded_senders_does_not_use_up_what_a_pass_may_sort(tmp_path, monkeypatch):
    sorter = _Sorter()
    server, _, service = _writer(tmp_path, sorter=sorter)
    for n in range(65):
        server.add("INBOX", mail(f"Work {n}", sender="Boss <boss@work.example>", message_id=f"<w{n}@x>", days_ago=n / 100))
    for n in range(5):
        server.add("INBOX", mail(f"Ana {n}", sender="Ana <ana@example.com>", message_id=f"<a{n}@x>", days_ago=5 + n))
    service.put_settings({"excluded": ["@work.example"]})
    _turn_sorting_on(service, monkeypatch)
    service._sync.run_once()
    assert len(sorter.asked) == 1 and "work.example" not in sorter.asked[0][1]
    assert {t["subject"] for t in service.threads()["threads"] if t["category"]} == {f"Ana {n}" for n in range(5)}


def test_one_message_that_cannot_be_read_and_one_bad_line_in_the_answer_cost_only_themselves(tmp_path, monkeypatch):
    from coworker.mail import service as service_module

    server, _, service = _writer(tmp_path)
    for n in range(3):
        server.add("INBOX", mail(f"Mail {n}", message_id=f"<m{n}@x>", body=f"Text {n}.", days_ago=n))
    render = service_module.render_message

    def render_all_but_one(msg):
        if msg["Message-ID"] == "<m1@x>":
            raise ValueError("bad mime")
        return render(msg)

    monkeypatch.setattr(service_module, "render_message", render_all_but_one)
    asked = []

    def answer_with_one_bad_line(system, user):
        asked.append(user)
        good = json.loads(_Sorter()(system, user))
        return json.dumps([{"key": {}, "category": "fyi", "summary": "not for any conversation"}, *good])

    service._sort_complete = answer_with_one_bad_line
    _turn_sorting_on(service, monkeypatch)
    service._sync.run_once()
    # All three were asked about, the unreadable one by its sender and subject alone.
    assert len(asked) == 1 and "Subject: Mail 1" in asked[0] and "Text 1." not in asked[0]
    assert all(t["category"] == "needs_reply" for t in service.threads()["threads"])
    assert service.settings()["sort_error"] == ""


def test_connecting_another_mailbox_asks_about_sorting_afresh(tmp_path, monkeypatch):
    sorter = _Sorter()
    server, _, service = _writer(tmp_path, sorter=sorter)
    server.add("INBOX", mail("Friday?", message_id="<ana@x>"))
    _turn_sorting_on(service, monkeypatch)
    service.put_settings({"excluded": ["@bank.example"]})
    service._sync.run_once()
    assert len(sorter.asked) == 1 and service.status()["sorting"] is True

    # The address is changed without a disconnect: the same server, another owner's answer.
    service._secrets.put("email:default", {**service._secrets.get("email:default"), "address": "other@example.com"})
    service._conn.close()
    service._sync.run_once()
    status = service.status()
    assert (status["sorting"], status["sorting_asked"]) == (False, False)
    assert service.settings()["excluded"] == [] and len(sorter.asked) == 1


def test_a_list_of_excluded_senders_that_is_not_addresses_or_domains_is_refused(tmp_path):
    _, _, service = _writer(tmp_path)
    for bad in (["ana"], ["ana @example.com"], "ana@example.com", ["a@example.com"] * 201,
                ["@"], ["a@"], ["a@b@c.example"], ["<ana@example.com>"], ["*@example.com"], ["ana@example"]):
        answer = service.put_settings({"excluded": bad})
        assert answer["ok"] is False, bad
    # Anything but a plain yes or no for the switch is refused, not taken as a no.
    service._store.put("sorting", "on")
    for bad in ("yes", 1, None, [True]):
        assert service.put_settings({"sorting": bad}) == {"ok": False, "error": "This setting could not be saved."}
    assert service.status()["sorting"] is True
    service._store.put("sorting", "")
    assert service.put_settings({"excluded": ["ana"]})["error"].startswith('"ana" is not an address or a domain.')
    assert service.settings()["excluded"] == []
    service._secrets.delete("email:default")
    assert service.put_settings({"sorting": True}) == {"ok": False, "error": "Email is not connected."}


def test_disconnecting_during_sorting_leaves_nothing_it_learned_behind(tmp_path):
    server, _, service = _writer(tmp_path)
    server.add("INBOX", mail("Friday?", message_id="<ana@x>"))

    def disconnect_then_answer(system, user):
        service._store.clear()
        key = next(line.split()[2] for line in user.splitlines() if line.startswith("===== CONVERSATION "))
        return json.dumps([{"key": key, "category": "fyi", "summary": "Private."}])

    service._sort_complete = disconnect_then_answer
    service._store.put("sorting", "on")
    service._sync.run_once()
    assert service._store._all("SELECT thread_key FROM thread_ai") == []
    assert service._store._all("SELECT uid FROM body") == []

    # Nor is why it failed, when the model fails after the disconnect.
    def disconnect_then_fail(system, user):
        service._store.clear()
        raise RuntimeError("provider said: something about the mail")

    service._sort_complete = disconnect_then_fail
    service._store.put("sorting", "on")
    service._sync.run_once()
    assert service._store.get("sort_error") == ""

