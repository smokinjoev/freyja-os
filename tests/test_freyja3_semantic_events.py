from __future__ import annotations

import freyja.main as freyja_main
from fastapi.testclient import TestClient

from freyja.foundation_models import SecurityDomainId, SemanticEvent
from freyja.semantic_events import SemanticEventQuery, SemanticEventStore


def test_semantic_event_store_accepts_hera_system_events(tmp_path) -> None:
    store = SemanticEventStore(tmp_path / "events.db")
    event = SemanticEvent(
        source_machine_id="hera",
        event_type="person_present",
        room="kitchen",
        subject="joe",
        confidence=0.91,
        metadata={"source": "unit-test"},
    )

    stored = store.publish(event, publisher_domain_id=SecurityDomainId.SYSTEM)
    events = store.list_events(SemanticEventQuery(event_type="person_present"), reader_domain_id=SecurityDomainId.HOUSEHOLD)

    assert stored.event_id == event.event_id
    assert len(events) == 1
    assert events[0].source_machine_id == "hera"
    assert events[0].subject == "joe"
    assert events[0].metadata == {"source": "unit-test"}


def test_semantic_event_api_publishes_and_lists_hera_events(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja_main, "semantic_event_store_v3", SemanticEventStore(tmp_path / "events.db"))
    client = TestClient(freyja_main.app)

    created = client.post(
        "/events/semantic",
        headers={"x-freyja-security-domain": "system"},
        json={
            "source_machine_id": "hera",
            "event_type": "occupancy_changed",
            "room": "living_room",
            "subject": "occupied",
            "confidence": 0.88,
        },
    )
    listed = client.get(
        "/events/semantic?room=living_room",
        headers={"x-freyja-security-domain": "household"},
    )

    assert created.status_code == 200
    assert listed.status_code == 200
    data = listed.json()
    assert data["count"] == 1
    assert data["events"][0]["event_type"] == "occupancy_changed"


def test_semantic_event_api_denies_non_hera_publish_and_private_reader(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja_main, "semantic_event_store_v3", SemanticEventStore(tmp_path / "events.db"))
    client = TestClient(freyja_main.app)

    publish = client.post(
        "/events/semantic",
        headers={"x-freyja-security-domain": "system"},
        json={
            "source_machine_id": "iris",
            "event_type": "person_present",
            "room": "office",
            "confidence": 0.5,
        },
    )
    read = client.get(
        "/events/semantic",
        headers={"x-freyja-security-domain": "person.joe"},
    )

    assert publish.status_code == 403
    assert read.status_code == 403
