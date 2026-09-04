from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from freyja.home_memory import home_memory_router
from freyja.memory import store as memory_store
from freyja.memory.store import MemoryStore


def _client(tmp_path) -> TestClient:
    test_store = MemoryStore(database_path=str(tmp_path / "home-memory.db"))
    test_store.initialize(force=True)
    memory_store.set_store(test_store)
    app = FastAPI()
    app.include_router(home_memory_router)
    return TestClient(app)


def _headers(subject: str) -> dict[str, str]:
    return {
        "x-freyja-client-type": "open-webui",
        "x-freyja-client-subject": subject,
    }


def test_home_memory_exposes_required_operations(tmp_path) -> None:
    response = _client(tmp_path).get("/freyja-home-memory/operations")

    assert response.status_code == 200
    assert set(response.json()["operations"]) == {
        "search",
        "remember",
        "update",
        "forget",
        "record-decision",
        "recent-events",
    }


def test_home_memory_enforces_personal_scope_reads(tmp_path) -> None:
    client = _client(tmp_path)
    write = client.post(
        "/freyja-home-memory/remember",
        headers=_headers("person:joe"),
        json={
            "scope": "personal:joe",
            "owner": "joe",
            "content": "Joe prefers local inference.",
            "provenance": "test",
            "sensitivity": "private",
        },
    )
    assert write.status_code == 200

    beth_read = client.get(
        "/freyja-home-memory/search?scope=personal:joe",
        headers=_headers("person:beth"),
    )
    assert beth_read.status_code == 403

    joe_read = client.get(
        "/freyja-home-memory/search?scope=personal:joe&q=local",
        headers=_headers("person:joe"),
    )
    assert joe_read.status_code == 200
    assert joe_read.json()["records"][0]["content"] == "Joe prefers local inference."


def test_benedict_can_only_write_restricted_benedict_scope(tmp_path) -> None:
    client = _client(tmp_path)
    denied = client.post(
        "/freyja-home-memory/remember",
        headers=_headers("agent:benedict"),
        json={
            "scope": "household",
            "owner": "beth",
            "content": "Do not allow this.",
            "provenance": "test",
        },
    )
    assert denied.status_code == 403

    allowed = client.post(
        "/freyja-home-memory/record-decision",
        headers=_headers("agent:benedict"),
        json={
            "scope": "restricted:benedict",
            "owner": "beth",
            "content": "Use local-only document analysis.",
            "provenance": "test",
            "sensitivity": "sensitive",
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["scope"] == "restricted:benedict"
    assert allowed.json()["operation"] == "record-decision"
