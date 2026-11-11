"""A file dropped on a conversation that is too big to travel inside a message."""

from fastapi.testclient import TestClient

from coworker.conversations import SessionRecord
from coworker.server import SessionManager, create_app


def _fixture(tmp_path):
    manager = SessionManager(workspace=tmp_path, provider=None)
    folder = tmp_path / "chat"
    folder.mkdir()
    manager.session_store.save(
        SessionRecord(
            session_id="s-drop-1",
            workspace=str(folder.resolve()),
            model="m",
            mode="interactive",
            messages=[{"role": "user", "content": "hi"}],
            title="hi",
        )
    )
    return TestClient(create_app(manager)), folder


def test_a_dropped_file_is_saved_into_the_conversations_own_folder(tmp_path):
    client, folder = _fixture(tmp_path)
    body = b"%PDF-" + b"x" * (12 * 1024 * 1024)  # larger than a message frame allows

    out = client.post(
        "/v1/sessions/s-drop-1/files", params={"name": "big paper.pdf"}, content=body
    )

    assert out.status_code == 200
    assert out.json()["name"] == "big paper.pdf"
    assert (folder / "big paper.pdf").read_bytes() == body


def test_a_dropped_file_never_overwrites_one_already_there(tmp_path):
    client, folder = _fixture(tmp_path)
    (folder / "notes.pdf").write_bytes(b"mine")

    out = client.post("/v1/sessions/s-drop-1/files", params={"name": "notes.pdf"}, content=b"new")

    assert out.json()["name"] == "notes-1.pdf"
    assert (folder / "notes.pdf").read_bytes() == b"mine"


def test_a_dropped_files_name_cannot_place_it_outside_the_folder(tmp_path):
    client, folder = _fixture(tmp_path)

    out = client.post(
        "/v1/sessions/s-drop-1/files", params={"name": "../../escape.pdf"}, content=b"data"
    )

    assert out.json()["name"] == "escape.pdf"
    assert (folder / "escape.pdf").exists()
    assert not (tmp_path.parent / "escape.pdf").exists()


def test_an_empty_drop_or_an_odd_conversation_id_saves_nothing(tmp_path):
    client, folder = _fixture(tmp_path)

    def post(sid, body):
        return client.post(f"/v1/sessions/{sid}/files", params={"name": "a.pdf"}, content=body)

    assert post("s-drop-1", b"").status_code == 400
    assert post("a.b", b"x").status_code == 404
    assert list(folder.iterdir()) == []
