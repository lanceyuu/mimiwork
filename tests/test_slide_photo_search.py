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
    # Seen on a real run (2026-11-19): saving into a folder that did not exist yet failed
    # with "file not found", and the deck went out without its photograph.
    assert "error" not in save(1, "assets/house.jpg")
    assert (tmp_path / "assets" / "house.jpg").read_bytes() == payload
    payload = b"not an image"
    assert "error" in save(1, "bad.jpg")
    assert not (tmp_path / "bad.jpg").exists()


def _jpeg(width, height):
    image = pytest.importorskip("PIL.Image")
    raw = BytesIO()
    image.new("RGB", (width, height), "#7aa").save(raw, "JPEG")
    return raw.getvalue()


def _stock_item(n, **changes):
    return {
        "id": f"00000000-0000-0000-0000-00000000000{n}", "title": f"Team Meeting {n}", "creator": "Startup Stock Photos",
        "foreign_landing_url": f"https://stocksnap.io/photo/team-meeting-{n}", "url": f"https://cdn.stocksnap.io/img-thumbs/960w/{n}.jpg",
        "license": "cc0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/", "source": "stocksnap",
        "filetype": "jpg", "width": 5472, "height": 3648, "thumbnail": f"https://api.openverse.org/v1/images/{n}/thumb/",
        **changes,
    }


def test_stock_photographs_free_of_copyright_come_first_with_a_sheet_to_choose_from(tmp_path, monkeypatch):
    """Six real decks on 19 November 2026 had no photograph between them: the only library
    searched was Commons, which answered "remote team meeting" with a FEMA rescue briefing.
    The owner: "the default slide style should still be image first. we should linked it
    with a copyright free library"."""
    image = pytest.importorskip("PIL.Image")
    asked = []

    def get(url, **kw):
        request = httpx.Request("GET", url)
        if "openverse" in url and "/thumb/" not in url:
            asked.append(kw["params"])
            return httpx.Response(200, request=request, json={"results": [
                _stock_item(1), _stock_item(2, license="by"), _stock_item(3, filetype="svg", url="https://x.example/3.svg"),
                _stock_item(4, url="http://plain.example/4.jpg"),
            ]})
        if "/thumb/" in url:
            return httpx.Response(200, request=request, content=_jpeg(320, 200))
        return httpx.Response(200, request=request, json={"query": {"pages": []}})

    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr(slide_photos, "_fetch_original", lambda url: _jpeg(960, 640))
    search, save = slide_photos.slide_photo_tools(SimpleNamespace(workspace=tmp_path))
    found = search("team meeting")
    assert asked[0]["license"] == "cc0,pdm" and asked[0]["q"] == "team meeting"
    assert [(p["id"], p["rights"], p["collection"]) for p in found["photos"]] == [(1, "CC0", "stocksnap")]
    with image.open(found["_images"][0]) as sheet:
        assert sheet.width > sheet.height
    saved = save(1, "assets/meeting.jpg")
    assert (tmp_path / "assets" / "meeting.jpg").is_file()
    assert (saved["width"], saved["height"]) == (960, 640)  # what was really saved, not the catalogue's figure
    assert "Startup Stock Photos" in saved["credit"] and "CC0" in saved["credit"] and "stocksnap.io" in saved["credit"]


def test_a_subject_given_in_too_many_words_is_searched_again_in_fewer(tmp_path, monkeypatch):
    """Live, 2026-11-19: "remote team video meeting" found nothing in the stock library and
    "team meeting" found 139, and a model that got nothing gave up on photographs."""
    asked = []

    def get(url, **kw):
        request = httpx.Request("GET", url)
        if "openverse" in url and "/thumb/" not in url:
            asked.append(kw["params"]["q"])
            hits = [_stock_item(1)] if kw["params"]["q"] == "video meeting" else []
            return httpx.Response(200, request=request, json={"results": hits})
        if "/thumb/" in url:
            return httpx.Response(404, request=request)
        return httpx.Response(200, request=request, json={"query": {"pages": []}})

    monkeypatch.setattr(httpx, "get", get)
    search, _ = slide_photos.slide_photo_tools(SimpleNamespace(workspace=tmp_path))
    found = search("remote team video meeting")
    assert asked == ["remote team video meeting", "video meeting"]
    assert len(found["photos"]) == 1 and found["searched_for"] == "video meeting"


def test_the_older_library_still_answers_when_the_stock_library_turns_the_search_away(tmp_path, monkeypatch):
    """The stock library allows 200 searches a day from one address without a key; a class
    on one network can use that up."""
    def get(url, **kw):
        request = httpx.Request("GET", url)
        if "openverse" in url:
            return httpx.Response(429, request=request)
        return httpx.Response(200, request=request, json={"query": {"pages": [{
            "pageid": 77, "title": "File:House.jpg", "imageinfo": [{
                "mime": "image/jpeg", "width": 1600, "height": 900, "size": 5000,
                "url": "https://upload.wikimedia.org/wikipedia/commons/example.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:House.jpg",
                "extmetadata": {"LicenseShortName": {"value": "CC0"}, "Artist": {"value": "Lee"}}}]}]}})

    monkeypatch.setattr(httpx, "get", get)
    search, _ = slide_photos.slide_photo_tools(SimpleNamespace(workspace=tmp_path))
    assert [p["collection"] for p in search("house")["photos"]] == ["wikimedia"]


def test_a_stock_picture_too_small_for_a_slide_is_not_saved(tmp_path, monkeypatch):
    def get(url, **kw):
        request = httpx.Request("GET", url)
        if "openverse" in url and "/thumb/" not in url:
            return httpx.Response(200, request=request, json={"results": [_stock_item(1)]})
        return httpx.Response(404, request=request)

    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setattr(slide_photos, "_fetch_original", lambda url: _jpeg(400, 300))
    search, save = slide_photos.slide_photo_tools(SimpleNamespace(workspace=tmp_path))
    search("team meeting")
    assert "small" in save(1, "tiny.jpg")["error"] and not (tmp_path / "tiny.jpg").exists()
