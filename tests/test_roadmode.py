from fastapi.testclient import TestClient

from freyja.roadmode import _parse_chapters
from freyja.roadmode_app import app


def test_parse_chapters_splits_numbered_chapters() -> None:
    text = """
*** START OF THE PROJECT GUTENBERG EBOOK TEST ***

CHAPTER I

First paragraph.

Second paragraph.

CHAPTER II

Third paragraph.

*** END OF THE PROJECT GUTENBERG EBOOK TEST ***
"""
    chapters = _parse_chapters(text)
    assert [chapter["title"] for chapter in chapters] == ["Chapter I", "Chapter Ii"]
    assert chapters[0]["paragraphs"] == ["First paragraph.", "Second paragraph."]
    assert chapters[1]["paragraphs"] == ["Third paragraph."]


def test_road_mode_page_is_available() -> None:
    client = TestClient(app)
    response = client.get("/road")
    assert response.status_code == 200
    assert "Freyja Road Mode" in response.text
    assert "Talk to Freyja" in response.text
    assert "/road/api/chat" in response.text
    assert "SpeechRecognition" in response.text


def test_road_mode_page_loads_when_connector_auth_is_enabled(monkeypatch) -> None:
    import freyja.main as main

    monkeypatch.setattr(main.settings, "freyja_connector_token", "secret")
    client = TestClient(app)
    response = client.get("/road")
    assert response.status_code == 200


def test_library_lists_seed_books(tmp_path, monkeypatch) -> None:
    import freyja.roadmode as roadmode

    monkeypatch.setattr(roadmode, "DATA_DIR", tmp_path)
    monkeypatch.setattr(roadmode, "BOOK_DIR", tmp_path / "books")
    monkeypatch.setattr(roadmode, "PROGRESS_FILE", tmp_path / "progress.json")

    client = TestClient(app)
    response = client.get("/road/api/books")
    assert response.status_code == 200
    slugs = {book["slug"] for book in response.json()["books"]}
    assert {"princess-of-mars", "gods-of-mars", "time-machine", "mysterious-island"} <= slugs


def test_progress_round_trip(tmp_path, monkeypatch) -> None:
    import freyja.roadmode as roadmode

    monkeypatch.setattr(roadmode, "DATA_DIR", tmp_path)
    monkeypatch.setattr(roadmode, "BOOK_DIR", tmp_path / "books")
    monkeypatch.setattr(roadmode, "PROGRESS_FILE", tmp_path / "progress.json")

    client = TestClient(app)
    saved = client.put(
        "/road/api/books/princess-of-mars/progress",
        json={"chapter_index": 2, "paragraph_index": 7},
    )
    assert saved.status_code == 200

    library = client.get("/road/api/books").json()["books"]
    princess = next(book for book in library if book["slug"] == "princess-of-mars")
    assert princess["progress"] == {"chapter_index": 2, "paragraph_index": 7}


def test_road_chat_uses_voice_shortcut_contract(monkeypatch) -> None:
    captured = {}

    async def fake_shortcut_message(request, raw_request):
        captured["request"] = request
        return {"spoken": "Road mode is online.", "conversation_id": "shortcut-conv:road"}

    class FakeShortcutMessageRequest:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setattr("freyja.main.ShortcutMessageRequest", FakeShortcutMessageRequest)
    monkeypatch.setattr("freyja.main.shortcut_message", fake_shortcut_message)

    client = TestClient(app)
    response = client.post("/road/api/chat", json={"prompt": "Are you there?"})

    assert response.status_code == 200
    assert response.json()["spoken"] == "Road mode is online."
    assert captured["request"].prompt == "Are you there?"
    assert captured["request"].conversation_id == "road"
    assert captured["request"].sender == "road-mode"
    assert captured["request"].tools_required is True
