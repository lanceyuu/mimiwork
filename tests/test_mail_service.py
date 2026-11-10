"""What the Mail screen can ask for, against a mail server in memory."""

from __future__ import annotations

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
def _writer(tmp_path, *, model=None, display_name="Shubin", **server_options):
    server, smtp = FakeMailServer(**server_options), FakeSMTP()
    secrets = connected_secrets(tmp_path)
    secrets.put("email:default", {**secrets.get("email:default"), "display_name": display_name})
    service = MailService(
        secrets, tmp_path / "mail.db", imap_factory=server.connect, smtp_factory=smtp.connect,
        complete=model, downloads=tmp_path / "Downloads",
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
