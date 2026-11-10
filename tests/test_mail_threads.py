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
