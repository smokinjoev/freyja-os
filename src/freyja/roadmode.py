from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

roadmode_router = APIRouter(prefix="/road", tags=["road-mode"])

BOOKS = {
    "princess-of-mars": {"title": "A Princess of Mars", "author": "Edgar Rice Burroughs", "gutenberg_id": 62},
    "gods-of-mars": {"title": "The Gods of Mars", "author": "Edgar Rice Burroughs", "gutenberg_id": 64},
    "time-machine": {"title": "The Time Machine", "author": "H. G. Wells", "gutenberg_id": 35},
    "mysterious-island": {"title": "The Mysterious Island", "author": "Jules Verne", "gutenberg_id": 1268},
}

DATA_DIR = Path.home() / ".freyja" / "road-mode"
BOOK_DIR = DATA_DIR / "books"
PROGRESS_FILE = DATA_DIR / "progress.json"


class ProgressUpdate(BaseModel):
    chapter_index: int = Field(ge=0)
    paragraph_index: int = Field(ge=0)


class RoadChatRequest(BaseModel):
    prompt: str = Field(min_length=1)


def _ensure_dirs() -> None:
    BOOK_DIR.mkdir(parents=True, exist_ok=True)


def _progress() -> dict[str, dict[str, int]]:
    _ensure_dirs()
    if not PROGRESS_FILE.exists():
        return {}
    try:
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_progress(data: dict[str, dict[str, int]]) -> None:
    _ensure_dirs()
    temp = PROGRESS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(PROGRESS_FILE)


def _strip_gutenberg_wrappers(text: str) -> str:
    start = re.search(r"\*\*\* START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", text, re.I)
    if start:
        text = text[start.end():]
    end = re.search(r"\*\*\* END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK.*?\*\*\*", text, re.I)
    if end:
        text = text[: end.start()]
    return text.strip()


def _parse_chapters(text: str) -> list[dict[str, object]]:
    text = _strip_gutenberg_wrappers(text).replace("\r\n", "\n")
    pattern = re.compile(r"(?im)^(chapter[ \t]+(?:[ivxlcdm]+|\d+)(?:\.?[ \t]+[^\n]*)?|book[ \t]+(?:[ivxlcdm]+|\d+)(?:\.?[ \t]+[^\n]*)?)\s*$")
    matches = list(pattern.finditer(text))
    if not matches:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        return [{"title": "Book", "paragraphs": paragraphs}]

    chapters: list[dict[str, object]] = []
    for index, match in enumerate(matches):
        start = match.end()
        stop = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:stop].strip()
        paragraphs = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        if paragraphs:
            chapters.append({"title": re.sub(r"\s+", " ", match.group(1)).title(), "paragraphs": paragraphs})
    return chapters


async def _book_text(slug: str) -> str:
    if slug not in BOOKS:
        raise HTTPException(status_code=404, detail="Unknown book")
    _ensure_dirs()
    cache = BOOK_DIR / f"{slug}.txt"
    if cache.exists():
        return cache.read_text(encoding="utf-8")

    book_id = BOOKS[slug]["gutenberg_id"]
    urls = [
        f"https://www.gutenberg.org/cache/epub/{book_id}/pg{book_id}.txt",
        f"https://www.gutenberg.org/files/{book_id}/{book_id}-0.txt",
        f"https://www.gutenberg.org/files/{book_id}/{book_id}.txt",
    ]
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": "Freyja-OS/0.1"}) as client:
        for url in urls:
            response = await client.get(url)
            if response.status_code == 200 and len(response.text) > 1000:
                cache.write_text(response.text, encoding="utf-8")
                return response.text
    raise HTTPException(status_code=502, detail="Could not download the Gutenberg text")


@roadmode_router.get("", response_class=HTMLResponse)
async def road_mode_page() -> HTMLResponse:
    html_path = Path(__file__).with_name("roadmode.html")
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@roadmode_router.get("/api/books")
async def list_books() -> dict[str, object]:
    progress = _progress()
    return {
        "books": [
            {"slug": slug, **metadata, "progress": progress.get(slug, {"chapter_index": 0, "paragraph_index": 0})}
            for slug, metadata in BOOKS.items()
        ]
    }


@roadmode_router.get("/api/books/{slug}")
async def get_book(slug: str) -> dict[str, object]:
    text = await _book_text(slug)
    chapters = _parse_chapters(text)
    return {"slug": slug, **BOOKS[slug], "chapters": chapters, "progress": _progress().get(slug, {"chapter_index": 0, "paragraph_index": 0})}


@roadmode_router.put("/api/books/{slug}/progress")
async def update_progress(slug: str, update: ProgressUpdate) -> dict[str, object]:
    if slug not in BOOKS:
        raise HTTPException(status_code=404, detail="Unknown book")
    progress = _progress()
    progress[slug] = update.model_dump()
    _save_progress(progress)
    return {"saved": True, "progress": progress[slug]}


@roadmode_router.post("/api/chat")
async def road_chat(request: RoadChatRequest, raw_request: Request) -> dict[str, object]:
    from freyja.main import ShortcutMessageRequest, shortcut_message

    return await shortcut_message(
        ShortcutMessageRequest(
            prompt=request.prompt,
            conversation_id="road",
            sender="road-mode",
            tools_required=True,
        ),
        raw_request,
    )
