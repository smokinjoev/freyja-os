from __future__ import annotations

from fastapi.testclient import TestClient

import freyja.freyja3_app as freyja3_app
from freyja.agent_runtime_v3 import AgentRuntimeV3
from freyja.freyja3_memory import Freyja3MemoryStore
from freyja.semantic_events import SemanticEventStore


def test_freyja3_app_canonical_route_uses_gateway_runtime(monkeypatch, tmp_path) -> None:
    memory_store = Freyja3MemoryStore(tmp_path / "memory.db")
    monkeypatch.setattr(freyja3_app, "agent_runtime", AgentRuntimeV3(memory_store=memory_store))
    client = TestClient(freyja3_app.app)

    response = client.post(
        "/canonical/route",
        json={
            "trace_id": "trace-f3-app",
            "message_id": "msg-f3-app",
            "channel": "imessage",
            "conversation_id": "conv-f3-app",
            "sender": {"channel_id": "sender", "address": "+1555"},
            "resolved_user_id": "joe",
            "text": "Inspect git status and search the web.",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["resolved_agent_id"] == "cloyd-gibbler"
    assert data["channel_metadata"]["freyja3"] is True
    assert data["channel_metadata"]["inference_machine_id"] == "vulcan"
    assert data["channel_metadata"]["written_memories"]


def test_freyja3_app_semantic_events_are_available(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja3_app, "semantic_event_store", SemanticEventStore(tmp_path / "events.db"))
    client = TestClient(freyja3_app.app)

    created = client.post(
        "/events/semantic",
        headers={"x-freyja-security-domain": "system"},
        json={
            "source_machine_id": "hera",
            "event_type": "person_present",
            "room": "kitchen",
            "subject": "beth",
            "confidence": 0.9,
        },
    )
    listed = client.get("/events/semantic?event_type=person_present")

    assert created.status_code == 200
    assert listed.status_code == 200
    assert listed.json()["count"] == 1


def test_freyja3_app_memory_enforces_domain_headers(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja3_app, "memory_store", Freyja3MemoryStore(tmp_path / "memory.db"))
    client = TestClient(freyja3_app.app)

    created = client.post(
        "/freyja3/memory",
        headers={"x-freyja-security-domain": "person.joe"},
        json={
            "owner_domain_id": "person.joe",
            "scope": "personal",
            "source_agent_id": "cloyd-gibbler",
            "content": "Private Joe memory.",
            "provenance": "unit-test",
            "classification": "private",
        },
    )
    joe_read = client.get("/freyja3/memory", headers={"x-freyja-security-domain": "person.joe"})
    beth_read = client.get("/freyja3/memory", headers={"x-freyja-security-domain": "person.beth"})

    assert created.status_code == 200
    assert joe_read.json()["count"] == 1
    assert beth_read.json()["count"] == 0
