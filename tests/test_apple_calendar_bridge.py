from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from freyja.apple_calendar_app import app
from freyja.calendar.apple_eventkit import run_eventkit
from freyja.calendar.models import CalendarEvent
from freyja.calendar.providers import AppleCalendarProvider


def _dt(hour: int) -> datetime:
    return datetime(2026, 8, 8, hour, tzinfo=UTC)


def test_native_helper_uses_json_stdin_and_does_not_request_permission_by_default(monkeypatch, tmp_path) -> None:
    helper = tmp_path / "helper.swift"
    helper.write_text("// synthetic")
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(command=command, kwargs=kwargs)
        return subprocess.CompletedProcess(command, 0, stdout='{"events":[]}', stderr="")

    monkeypatch.setattr("freyja.calendar.apple_eventkit.subprocess.run", fake_run)
    assert run_eventkit("list", {"start": "a", "end": "b"}, helper_path=helper) == {"events": []}
    assert seen["command"] == ["/usr/bin/swift", str(helper), "list"]
    assert json.loads(seen["kwargs"]["input"]) == {"start": "a", "end": "b"}


def test_native_helper_uses_configured_executable(monkeypatch, tmp_path) -> None:
    helper = tmp_path / "apple-eventkit"
    helper.write_text("binary")
    helper.chmod(0o700)
    monkeypatch.setenv("FREYJA_APPLE_CALENDAR_HELPER", str(helper))
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        return subprocess.CompletedProcess(command, 0, stdout='{"available":true}', stderr="")

    monkeypatch.setattr("freyja.calendar.apple_eventkit.subprocess.run", fake_run)
    assert run_eventkit("status") == {"available": True}
    assert seen["command"] == [str(helper), "status"]


def test_bridge_rejects_missing_or_wrong_token(monkeypatch) -> None:
    monkeypatch.setenv("FREYJA_APPLE_CALENDAR_TOKEN", "correct")
    client = TestClient(app)
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_bridge_returns_synthetic_health_without_calendar_access(monkeypatch) -> None:
    monkeypatch.setenv("FREYJA_APPLE_CALENDAR_TOKEN", "correct")
    monkeypatch.setattr("freyja.apple_calendar_app.run_eventkit", lambda operation, **kwargs: {"authorization": "fullAccess", "available": True})
    response = TestClient(app).get("/health", headers={"Authorization": "Bearer correct"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "authorization": "fullAccess", "available": True}


@pytest.mark.asyncio
async def test_provider_sends_bearer_token_and_requires_real_event_id() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json={"event": {"event_id": "apple-real-id", "calendar_id": "cal", "title": "Buy a chair", "start": "2026-08-08T12:00:00Z", "end": "2026-08-08T13:00:00Z"}})

    provider = AppleCalendarProvider(base_url="http://iris:8765", token="secret", transport=httpx.MockTransport(handler))
    created = await provider.create_event(CalendarEvent("", "cal", "Buy a chair", _dt(12), _dt(13)))
    assert created.event_id == "apple-real-id"
    assert created.provider == "apple"
    assert seen["authorization"] == "Bearer secret"


@pytest.mark.asyncio
async def test_provider_refuses_false_success_without_event_id() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"event": {"event_id": "", "calendar_id": "cal", "title": "No receipt", "start": "2026-08-08T12:00:00Z", "end": "2026-08-08T13:00:00Z"}}))
    provider = AppleCalendarProvider(base_url="http://iris:8765", token="secret", transport=transport)
    with pytest.raises(RuntimeError, match="confirmed event ID"):
        await provider.create_event(CalendarEvent("", "cal", "No receipt", _dt(12), _dt(13)))


@pytest.mark.asyncio
async def test_service_uses_default_apple_calendar_when_no_calendar_id() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"event": {"event_id": "apple-real-id", "calendar_id": "default-cal", "title": "Default calendar", "start": "2026-08-08T12:00:00Z", "end": "2026-08-08T13:00:00Z"}})

    from freyja.calendar import CalendarService

    provider = AppleCalendarProvider(base_url="http://iris:8765", token="secret", transport=httpx.MockTransport(handler))
    service = CalendarService(providers={"apple": provider})
    created = await service.create_event(
        title="Default calendar",
        start=_dt(12),
        end=_dt(13),
        provider_name="apple",
    )

    assert created.event_id == "apple-real-id"
    assert seen["payload"]["calendar_id"] is None


def test_event_update_discards_unapproved_fields(monkeypatch) -> None:
    monkeypatch.setenv("FREYJA_APPLE_CALENDAR_TOKEN", "correct")
    seen = {}

    def fake_run(operation, arguments=None, **kwargs):
        seen.update(operation=operation, arguments=arguments)
        return {"event": {"event_id": "id"}}

    monkeypatch.setattr("freyja.apple_calendar_app.run_eventkit", fake_run)
    response = TestClient(app).request(
        "PATCH",
        "/events",
        headers={"Authorization": "Bearer correct"},
        json={"event_id": "id", "updates": {"title": "Allowed", "calendar_id": "blocked", "provider": "blocked"}},
    )
    assert response.status_code == 200
    assert seen == {"operation": "modify", "arguments": {"event_id": "id", "title": "Allowed"}}


def test_bridge_get_event_by_real_identifier(monkeypatch) -> None:
    monkeypatch.setenv("FREYJA_APPLE_CALENDAR_TOKEN", "correct")
    seen = {}

    def fake_run(operation, arguments=None, **kwargs):
        seen.update(operation=operation, arguments=arguments)
        return {"event": {"event_id": "id", "calendar_id": "cal", "title": "Found", "start": "2026-08-08T12:00:00Z", "end": "2026-08-08T13:00:00Z"}}

    monkeypatch.setattr("freyja.apple_calendar_app.run_eventkit", fake_run)
    response = TestClient(app).get("/events/id", headers={"Authorization": "Bearer correct"})

    assert response.status_code == 200
    assert response.json()["event"]["event_id"] == "id"
    assert seen == {"operation": "get", "arguments": {"event_id": "id"}}
