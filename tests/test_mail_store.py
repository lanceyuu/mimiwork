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


def test_mail_that_was_removed_or_disconnected_leaves_no_text_in_the_file(tmp_path):
    store = _store(tmp_path)
    store.add([_row("INBOX", n, subject=f"KEPT-{n}") for n in range(50)])
    store.add([_row("INBOX", 900, subject="ARCHIVED-SUBJECT-MARKER")])
    body = {"html": "<p>ARCHIVED-BODY-MARKER</p>" * 400, "text": "x", "attachments": []}
    store.put_body(ME, "INBOX", 900, body, 0.0)
    store.remove(ME, "INBOX", [900])  # archived: SQLite must not keep the text in a free page
    store._conn.commit()
    left = (tmp_path / "mail.db").read_bytes()
    assert b"ARCHIVED-SUBJECT-MARKER" not in left and b"ARCHIVED-BODY-MARKER" not in left
    assert b"KEPT-1" in left

    store.clear()  # disconnected
    store.close()
    left = (tmp_path / "mail.db").read_bytes()
    assert b"KEPT-" not in left
    # And the file gives the space back: it is no bigger than a cache that never held mail.
    MailStore(tmp_path / "never-used.db").close()
    assert len(left) <= (tmp_path / "never-used.db").stat().st_size


# -- comments and drafts ---------------------------------------------------------------
def _draft(draft_id, *, key="k1", account=ME, updated_at=1.0, **fields):
    row = dict.fromkeys(
        ("recipients", "cc", "subject", "body", "orig_message_id", "orig_references",
         "orig_subject", "orig_sender", "orig_date", "orig_text"),
        "",
    )
    return {**row, "id": draft_id, "account": account, "thread_key": key, "updated_at": updated_at, **fields}


COMMENT = {"message_id": "<INBOX-1@x>", "quote": "on Friday", "note": "Yes."}


def test_comments_come_back_in_the_order_made_with_the_free_note_apart(tmp_path):
    store = _store(tmp_path)
    assert store.comments(ME, "k1") == {"comments": [], "note": ""}
    second = {"message_id": "<INBOX-1@x>", "quote": "the budget", "note": ""}
    store.put_comments(ME, "k1", [COMMENT, second], "Say hello.")
    store.put_comments(ME, "k2", [second], "")
    assert store.comments(ME, "k1") == {"comments": [COMMENT, second], "note": "Say hello."}
    # Saving is always the whole list: what is left out is gone.
    store.put_comments(ME, "k1", [second], "")
    assert store.comments(ME, "k1") == {"comments": [second], "note": ""}
    assert store.comments(ME, "k2") == {"comments": [second], "note": ""}


def test_a_draft_is_kept_changed_listed_newest_first_and_deleted(tmp_path):
    store = _store(tmp_path)
    store.add_draft(_draft("d1", recipients="ana@example.com", orig_text="Shall we?"))
    store.add_draft(_draft("d2", key="", updated_at=2.0))
    assert [d["id"] for d in store.drafts(ME)] == ["d2", "d1"]
    assert store.reply_draft(ME, "k1")["id"] == "d1"
    # A draft of a new message belongs to no conversation, so it is nobody's reply.
    assert store.reply_draft(ME, "") is None

    assert store.update_draft(ME, "d1", {"body": "Yes.", "orig_text": "changed"}, 3.0) is True
    changed = store.draft(ME, "d1")
    assert (changed["body"], changed["updated_at"], changed["orig_text"]) == ("Yes.", 3.0, "Shall we?")
    assert [d["id"] for d in store.drafts(ME)] == ["d1", "d2"]
    assert store.update_draft(ME, "gone", {"body": "x"}, 4.0) is False
    assert store.update_draft("other@example.com", "d1", {"body": "x"}, 4.0) is False

    store.mark_sending("d1", 9.0)
    assert store.draft(ME, "d1")["send_started_at"] == 9.0
    store.mark_sending("d1", 0)
    assert store.draft(ME, "d1")["send_started_at"] == 0
    assert store.delete_draft(ME, "d1") is True
    assert store.delete_draft(ME, "d1") is False
    assert store.draft(ME, "d1") is None


def test_comments_go_thirty_days_after_their_conversation_left_the_cache(tmp_path):
    store = _store(tmp_path)
    store.add([_row("INBOX", 1, key="here")])
    for key in ("here", "gone", "back"):
        store.put_comments(ME, key, [COMMENT], "")

    store.prune(100 * DAY)  # "gone" and "back" are first found without mail: the clock starts
    store.prune(129 * DAY)
    assert all(store.comments(ME, key)["comments"] == [COMMENT] for key in ("here", "gone", "back"))
    store.add([_row("INBOX", 2, key="back")])  # its mail is back, so its clock stops
    store.prune(131 * DAY)
    assert store.comments(ME, "gone")["comments"] == []
    assert store.comments(ME, "back")["comments"] == [COMMENT]
    assert store.comments(ME, "here")["comments"] == [COMMENT]
    store.remove(ME, "INBOX", [2])
    store.prune(140 * DAY)  # gone again: thirty days from now, not from the first time
    store.prune(169 * DAY)
    assert store.comments(ME, "back")["comments"] == [COMMENT]
    store.prune(171 * DAY)
    assert store.comments(ME, "back")["comments"] == []


def test_a_draft_is_never_forgotten_and_keeps_the_comments_it_can_be_rewritten_from(tmp_path):
    store = _store(tmp_path)
    store.add_draft(_draft("d-reply", key="archived", body="Half a thought"))
    store.add_draft(_draft("d-new", key=""))
    store.put_comments(ME, "archived", [COMMENT], "A note.")
    store.put_comments(ME, "no-reply", [COMMENT], "")
    for day in (100, 131, 500, 5000):
        store.prune(day * DAY)
    # What the user wrote goes only when it is sent or discarded, however long ago
    # its conversation left the cache.
    assert {d["id"] for d in store.drafts(ME)} == {"d-reply", "d-new"}
    assert store.draft(ME, "d-reply")["body"] == "Half a thought"
    assert store.comments(ME, "archived") == {"comments": [COMMENT], "note": "A note."}
    assert store.comments(ME, "no-reply")["comments"] == []
    # Once the reply is gone, its comments follow the thirty-day rule again.
    store.delete_draft(ME, "d-reply")
    store.prune(5001 * DAY)
    assert store.comments(ME, "archived")["comments"] == []


def test_a_conversation_has_one_reply_draft_and_none_is_kept_once_the_cache_was_emptied(tmp_path):
    import sqlite3

    import pytest

    store = _store(tmp_path)
    assert store.add_draft(_draft("d1")) is True
    with pytest.raises(sqlite3.IntegrityError):
        store.add_draft(_draft("d2"))
    assert store.add_draft(_draft("d3", key="")) is True and store.add_draft(_draft("d4", key="")) is True
    noted = store.epoch
    store.clear()
    assert store.add_draft(_draft("d5", key="k5"), epoch=noted) is False
    assert store.drafts(ME) == []


def test_a_folder_read_again_from_scratch_keeps_comments_and_drafts(tmp_path):
    store = _store(tmp_path)
    store.reset_folder(ME, "INBOX", "inbox", 1)
    store.add([_row("INBOX", 1)])
    store.put_comments(ME, "k1", [COMMENT], "Note.")
    store.add_draft(_draft("d1"))
    store.reset_folder(ME, "INBOX", "inbox", 2)
    assert store.uids(ME, "INBOX") == set()
    assert store.comments(ME, "k1") == {"comments": [COMMENT], "note": "Note."}
    assert store.draft(ME, "d1") is not None


def test_another_mailbox_or_a_disconnect_takes_comments_and_drafts_with_it(tmp_path):
    store = _store(tmp_path)
    for account in (ME, "old@example.com"):
        store.put_comments(account, "k1", [COMMENT], "")
        store.add_draft(_draft(f"d-{account}", account=account))
    store.forget_others(ME)
    assert store.comments("old@example.com", "k1")["comments"] == []
    assert store.drafts("old@example.com") == []
    assert store.comments(ME, "k1")["comments"] == [COMMENT]
    store.clear()
    assert store.comments(ME, "k1")["comments"] == []
    assert store.drafts(ME) == []


# -- sorting -----------------------------------------------------------------------------
def test_what_sorting_said_is_shown_only_while_it_is_about_the_newest_message(tmp_path):
    store = _store(tmp_path)
    store.add([_row("INBOX", 1, key="k1", message_id="<a@x>", date=100.0)])
    assert store.threads(ME, "INBOX")[0]["category"] == ""
    (waiting,) = store.to_sort(ME, "INBOX", 3)
    assert (waiting["key"], waiting["for_message"], waiting["newest"]["uid"]) == ("k1", "<a@x>", 1)

    before = store.revision
    said = {"key": "k1", "category": "needs_reply", "summary": "Ana asks to meet.", "for_message": "<a@x>"}
    assert store.put_sorted(ME, [said], store.epoch) is True
    assert store.revision == before + 1  # the list on screen should reload
    row = store.threads(ME, "INBOX")[0]
    assert (row["category"], row["summary"]) == ("needs_reply", "Ana asks to meet.")
    assert store.to_sort(ME, "INBOX", 3) == []

    # A newer message arrives: the old answer is about an email that is no longer the last word.
    store.add([_row("INBOX", 2, key="k1", message_id="<b@x>", date=200.0)])
    row = store.threads(ME, "INBOX")[0]
    assert (row["category"], row["summary"]) == ("", "")
    assert store.to_sort(ME, "INBOX", 3)[0]["for_message"] == "<b@x>"


def test_a_conversation_the_model_never_answers_about_is_tried_three_times_and_then_left(tmp_path):
    store = _store(tmp_path)
    store.add([_row("INBOX", 1, key="k1", message_id="<a@x>")])
    for _ in range(3):
        (item,) = store.to_sort(ME, "INBOX", 3)
        store.note_unsorted(ME, [item], store.epoch)
    assert store.to_sort(ME, "INBOX", 3) == []
    # A new message in it is a new question, counted from the start.
    store.add([_row("INBOX", 2, key="k1", message_id="<b@x>", date=200.0)])
    (item,) = store.to_sort(ME, "INBOX", 3)
    store.note_unsorted(ME, [item], store.epoch)
    assert len(store.to_sort(ME, "INBOX", 3)) == 1


def test_what_sorting_said_goes_with_the_mail_with_the_mailbox_and_when_sorting_is_turned_off(tmp_path):
    store = _store(tmp_path)
    said = {"category": "fyi", "summary": "A receipt.", "for_message": "<INBOX-1@x>"}
    for key in ("here", "gone"):
        store.put_sorted(ME, [{**said, "key": key}], store.epoch)
    store.put_sorted("old@example.com", [{**said, "key": "theirs"}], store.epoch)
    store.add([_row("INBOX", 1, key="here")])
    count = lambda: len(store._all("SELECT thread_key FROM thread_ai"))  # noqa: E731
    assert count() == 3
    store.prune(DAY)  # "gone" and "theirs" have no mail in the cache
    assert count() == 1
    store.put_sorted("old@example.com", [{**said, "key": "theirs"}], store.epoch)
    store.add([_row("INBOX", 1, key="theirs", account="old@example.com")])
    # What the other mailbox's owner agreed to was an answer about that mailbox.
    for key, value in (("sorting", "on"), ("excluded", '["@x.example"]'), ("sort_error", "x"), ("last_sync", "5")):
        store.put(key, value)
    store.forget_others(ME)
    assert count() == 1
    assert (store.get("sorting"), store.get("excluded"), store.get("sort_error")) == ("", "", "")
    assert store.get("last_sync") == "5"
    # With no other mailbox to forget, the answer stands.
    store.put("sorting", "on")
    store.forget_others(ME)
    assert store.get("sorting") == "on"
    store.put_sorted(ME, [{**said, "key": "one"}, {**said, "key": "two"}], store.epoch)
    store.forget_sorting(ME, ["one", "never-there"])
    assert count() == 2

    noted = store.epoch
    store.forget_sorting(ME)
    assert count() == 0
    store.clear()
    # Nothing sorting learned is written back once the mailbox has been disconnected.
    assert store.put_sorted(ME, [{**said, "key": "here"}], noted) is False
    store.note_unsorted(ME, [{"key": "here", "for_message": "<x>"}], noted)
    assert count() == 0

