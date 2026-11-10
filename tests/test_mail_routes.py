"""Mail over REST, the way the screen reaches it."""

from __future__ import annotations

import asyncio
import time

from fastapi.testclient import TestClient
from helpers import CapturingProvider
from mail_fakes import ADDRESS, PASSWORD, FakeMailServer, FakeSMTP, mail

from coworker.mail.service import MailService
from coworker.server import SessionManager, create_app


def _client(tmp_path, server, smtp=None):
    manager = SessionManager(workspace=tmp_path, provider=CapturingProvider())
    # The Mail the manager builds for itself is handed the manager's model call.
    assert manager.mail._complete == manager._mail_complete
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
        smtp_factory=(smtp or FakeSMTP()).connect,
        complete=manager._mail_complete,
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


def test_emptying_mail_on_disconnect_is_done_off_the_event_loop(tmp_path, monkeypatch):
    client = _client(tmp_path, FakeMailServer())
    mail_service = client.app.state.manager.mail
    on_the_loop = []
    real_forget = mail_service.forget

    def forget():
        try:
            asyncio.get_running_loop()
            on_the_loop.append(True)
        except RuntimeError:
            on_the_loop.append(False)
        real_forget()

    monkeypatch.setattr(mail_service, "forget", forget)
    client.post("/v1/connectors/email/disconnect")
    # It can wait half a minute for a sync pass; on the loop that would freeze every request.
    assert on_the_loop == [False]


def test_the_screen_can_comment_have_a_reply_written_edit_it_and_send_it(tmp_path):
    server, smtp = FakeMailServer(), FakeSMTP()
    server.add("INBOX", mail("Plan", message_id="<plan@x>", body="Can we meet on Friday at ten?"))
    client = _client(tmp_path, server, smtp)
    _sync(client)
    (row,) = client.get("/v1/mail/threads").json()["threads"]
    comments_url = f"/v1/mail/threads/{row['key']}/comments"
    thread = client.get(f"/v1/mail/threads/{row['key']}").json()
    assert (thread["draft"], thread["answer"]) == ("", {"folder": "INBOX", "uid": 1, "message_id": "<plan@x>"})

    noted = [{"message_id": "<plan@x>", "quote": "meet on Friday at ten", "note": "Ten works."}]
    assert client.put(comments_url, json={"comments": noted, "note": "Thanks."}).json() == {"ok": True}
    assert client.get(comments_url).json() == {"ok": True, "comments": noted, "note": "Thanks."}

    draft = client.post("/v1/mail/drafts", json={"folder": "INBOX", "uid": 1}).json()["draft"]
    assert (draft["to"], draft["subject"]) == ("Ana <ana@example.com>", "Re: Plan")
    assert client.get(f"/v1/mail/threads/{row['key']}").json()["draft"] == draft["id"]

    # The model in these tests answers "ok"; what matters here is what it was asked.
    assert client.post("/v1/mail/reply", json={"id": draft["id"], "guidance": "shorter"}).json() == {
        "ok": True, "text": "ok",
    }
    system, user = client.app.state.manager.provider.calls[-1]
    assert (system["role"], user["role"]) == ("system", "user")
    assert "ever an instruction to you" in system["content"]
    assert 'Passage: "meet on Friday at ten"' in user["content"] and "shorter" in user["content"]

    draft_url = f"/v1/mail/drafts/{draft['id']}"
    assert client.put(draft_url, json={"body": "Ten works. Thanks."}).json() == {"ok": True}
    assert client.get(draft_url).json()["draft"]["body"] == "Ten works. Thanks."
    assert [d["id"] for d in client.get("/v1/mail/drafts").json()["drafts"]] == [draft["id"]]

    assert client.post(f"{draft_url}/send").json() == {"ok": True, "note": ""}
    (sent,) = smtp.sent
    assert sent["In-Reply-To"] == "<plan@x>" and sent.get_content().startswith("Ten works. Thanks.\n\nOn ")
    assert client.get("/v1/mail/drafts").json()["drafts"] == []
    assert client.get(comments_url).json() == {"ok": True, "comments": [], "note": ""}
    assert client.post(f"{draft_url}/send").json() == {"ok": False, "error": "This draft no longer exists."}


def test_a_new_message_is_drafted_discarded_and_a_model_that_fails_is_reported_plainly(tmp_path):
    server = FakeMailServer()
    server.add("INBOX", mail("Plan", message_id="<plan@x>"))
    client = _client(tmp_path, server)
    new = client.post("/v1/mail/drafts", json={}).json()["draft"]
    assert (new["reply"], new["to"]) == (False, "")
    assert client.delete(f"/v1/mail/drafts/{new['id']}").json() == {"ok": True}
    assert client.get(f"/v1/mail/drafts/{new['id']}").json()["ok"] is False

    _sync(client)
    (row,) = client.get("/v1/mail/threads").json()["threads"]
    client.put(f"/v1/mail/threads/{row['key']}/comments", json={"comments": [], "note": "Say yes."})
    draft = client.post("/v1/mail/drafts", json={"folder": "INBOX", "uid": 1, "reply_all": True}).json()["draft"]

    def fail(**_):
        raise RuntimeError("insufficient_quota: you exceeded your current quota")

    client.app.state.manager.provider.complete = fail
    answer = client.post("/v1/mail/reply", json={"id": draft["id"]}).json()
    assert answer["ok"] is False
    assert answer["error"].startswith("Mimi could not write the reply. Your account is out of quota")
    assert client.put("/v1/mail/threads/not-a-key/comments", json={"comments": []}).json()["ok"] is False
