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
    with pytest.raises(MailError, match="The mail server stopped answering"):
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
    with pytest.raises(MailError, match="This folder cannot be changed"):
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
