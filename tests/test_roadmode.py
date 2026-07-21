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
