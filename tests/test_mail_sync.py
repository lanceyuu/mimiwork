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
