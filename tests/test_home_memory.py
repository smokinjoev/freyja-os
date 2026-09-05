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


def test_child_agents_cannot_write_household_memory(tmp_path) -> None:
    client = _client(tmp_path)

    denied = client.post(
        "/freyja-home-memory/remember",
        headers=_headers("agent:agent-44"),
        json={
            "scope": "household",
            "owner": "liam",
            "content": "Do not allow child agents to write shared memory directly.",
            "provenance": "unit-test",
        },
    )

    assert denied.status_code == 403


def test_home_memory_records_include_required_metadata_and_recent_events(tmp_path) -> None:
    client = _client(tmp_path)
    first = client.post(
        "/freyja-home-memory/remember",
        headers=_headers("person:joe"),
        json={
            "scope": "household",
            "owner": "joe",
            "content": "Router decision: keep inference local by default.",
            "provenance": "unit-test",
            "sensitivity": "private",
            "metadata": {"source_report": "test"},
        },
    )
    second = client.post(
        "/freyja-home-memory/record-decision",
        headers=_headers("person:joe"),
        json={
            "scope": "household",
            "owner": "joe",
            "content": "Decision: Open WebUI owns family-agent access.",
            "provenance": "unit-test",
            "sensitivity": "sensitive",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    record = first.json()
    assert record["scope"] == "household"
    assert record["owner"] == "joe"
    assert record["provenance"] == "unit-test"
    assert record["created_at"]
    assert record["updated_at"]
    assert record["sensitivity"] == "private"
    assert record["metadata"]["home_memory_scope"] == "household"
    assert record["metadata"]["home_memory_owner"] == "joe"
    assert record["metadata"]["home_memory_provenance"] == "unit-test"

    recent = client.get(
        "/freyja-home-memory/recent-events?scope=household&limit=5",
        headers=_headers("person:joe"),
    )

    assert recent.status_code == 200
    contents = [item["content"] for item in recent.json()["records"]]
    assert "Router decision: keep inference local by default." in contents
    assert "Decision: Open WebUI owns family-agent access." in contents


def test_home_memory_update_and_forget_are_scope_authorized(tmp_path) -> None:
    client = _client(tmp_path)
    create = client.post(
        "/freyja-home-memory/remember",
        headers=_headers("person:joe"),
        json={
            "scope": "personal:joe",
            "owner": "joe",
            "content": "Original preference.",
            "provenance": "unit-test",
            "sensitivity": "private",
        },
    )
    assert create.status_code == 200
    record_id = create.json()["id"]

    denied_update = client.post(
        "/freyja-home-memory/update",
        headers=_headers("person:beth"),
        json={
            "scope": "personal:joe",
            "owner": "joe",
            "record_id": record_id,
            "content": "Unauthorized update.",
            "provenance": "unit-test",
        },
    )
    assert denied_update.status_code == 403

    update = client.post(
        "/freyja-home-memory/update",
        headers=_headers("person:joe"),
        json={
            "scope": "personal:joe",
            "owner": "joe",
            "record_id": record_id,
            "content": "Updated preference.",
            "provenance": "unit-test",
        },
    )
    assert update.status_code == 200
    assert update.json()["id"] == record_id
    assert update.json()["content"] == "Updated preference."
    assert update.json()["operation"] == "update"

    denied_forget = client.request(
        "DELETE",
        f"/freyja-home-memory/forget/personal:joe/{record_id}",
        headers=_headers("person:beth"),
    )
    assert denied_forget.status_code == 403

    forget = client.request(
        "DELETE",
        f"/freyja-home-memory/forget/personal:joe/{record_id}",
        headers=_headers("person:joe"),
    )
    assert forget.status_code == 200
    assert forget.json() == {"deleted": True}
