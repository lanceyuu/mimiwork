from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest

from coworker.tools.office import slide_photos


def test_only_verified_originals_can_be_saved_with_their_credit(tmp_path, monkeypatch):
    image = pytest.importorskip("PIL.Image")
    raw = BytesIO()
    image.new("RGB", (1600, 900)).save(raw, "JPEG")
    payload = raw.getvalue()
    source = "https://commons.wikimedia.org/wiki/File:House.jpg"
    url = "https://upload.wikimedia.org/wikipedia/commons/example.jpg"

    def item(i, rights, width=1600, original=url):
        return {
            "pageid": i,
            "title": "File:House.jpg",
            "imageinfo": [
                {
                    "mime": "image/jpeg",
                    "width": width,
                    "height": 900,
                    "size": len(payload),
                    "url": original,
                    "descriptionurl": source,
                    "extmetadata": {
                        "LicenseShortName": {"value": rights},
                        "Artist": {"value": "Lee"},
                    },
                }
            ],
        }

    pages = [
        item(1, "CC0"),
        item(2, "CC BY-SA 4.0"),
        item(3, ""),
        item(4, "CC0", width=600),
        item(5, "Public domain", original="https://127.0.0.1/"),
    ]
    req = httpx.Request("GET", source)
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **kw: httpx.Response(200, request=req, json={"query": {"pages": pages}}),
    )

    @contextmanager
    def stream(method, actual, **kwargs):
        assert actual == url and kwargs["follow_redirects"] is False
        yield httpx.Response(200, request=req, content=payload)

    monkeypatch.setattr(httpx, "stream", stream)
    search, save = slide_photos.slide_photo_tools(SimpleNamespace(workspace=tmp_path))
    assert [photo["id"] for photo in search("house")["photos"]] == [1]
    assert "error" in save(2, "restricted.jpg")
    assert "error" in save(1, "../escape.jpg")
    result = save(1, "house.jpg")
    assert (result["rights"], result["creator"], result["source"]) == ("CC0", "Lee", source)
    assert (tmp_path / "house.jpg").read_bytes() == payload
    assert "error" in save(1, "house.jpg")
    payload = b"not an image"
    assert "error" in save(1, "bad.jpg")
    assert not (tmp_path / "bad.jpg").exists()
