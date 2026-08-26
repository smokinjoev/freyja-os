from __future__ import annotations

from fastapi.testclient import TestClient

import freyja.freyja3_app as freyja3_app
from freyja.agent_runtime_v3 import AgentRuntimeV3
from freyja.semantic_events import SemanticEventStore


def test_freyja3_app_canonical_route_uses_gateway_runtime(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja3_app, "agent_runtime", AgentRuntimeV3())
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
