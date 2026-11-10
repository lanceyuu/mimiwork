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
