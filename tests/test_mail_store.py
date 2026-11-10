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
    mark, epoch = store.touched, store.epoch
    store.clear()
    assert store.add([_row("INBOX", 1)], expect=mark) is False
    # A request that was fetching a message, or undoing a refused move, writes nothing either.
    assert store.add([_row("INBOX", 1)], epoch=epoch) is False
    store.put_body(ME, "INBOX", 1, {"html": "<p>x</p>", "text": "x", "attachments": []}, 0.0, epoch=epoch)
    assert store.uids(ME, "INBOX") == set()
    assert store.body(ME, "INBOX", 1, 0.0) is None
