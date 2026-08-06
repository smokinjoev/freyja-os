from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from freyja.apple_reminders_app import app
from freyja.reminders.apple_eventkit import run_eventkit
from freyja.reminders.models import Reminder
from freyja.reminders.providers import AppleReminderProvider


def test_native_helper_uses_json_stdin_and_does_not_request_permission_by_default(monkeypatch, tmp_path) -> None:
    helper = tmp_path / "helper.swift"
    helper.write_text("// synthetic")
    seen = {}

    def fake_run(command, **kwargs):
        seen.update(command=command, kwargs=kwargs)
        return subprocess.CompletedProcess(command, 0, stdout='{"reminders":[]}', stderr="")

    monkeypatch.setattr("freyja.reminders.apple_eventkit.subprocess.run", fake_run)
    assert run_eventkit("list", {"list_ids": ["home"]}, helper_path=helper) == {"reminders": []}
    assert seen["command"] == ["/usr/bin/swift", str(helper), "list"]
    assert json.loads(seen["kwargs"]["input"]) == {"list_ids": ["home"]}


def test_bridge_rejects_missing_or_wrong_token(monkeypatch) -> None:
    monkeypatch.setenv("FREYJA_APPLE_REMINDERS_TOKEN", "correct")
    client = TestClient(app)
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_bridge_returns_synthetic_health_without_reminders_access(monkeypatch) -> None:
    monkeypatch.setenv("FREYJA_APPLE_REMINDERS_TOKEN", "correct")
    monkeypatch.setattr("freyja.apple_reminders_app.run_eventkit", lambda operation, **kwargs: {"authorization": "authorized", "available": True})
    response = TestClient(app).get("/health", headers={"Authorization": "Bearer correct"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "authorization": "authorized", "available": True}


@pytest.mark.asyncio
async def test_provider_sends_bearer_token_and_requires_real_reminder_id() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "reminder": {
                    "reminder_id": "apple-reminder-id",
                    "list_id": "home",
                    "title": "Buy milk",
                    "due": "2026-08-08T12:00:00Z",
                    "completed": False,
                }
            },
        )

    provider = AppleReminderProvider(base_url="http://iris:8766", token="secret", transport=httpx.MockTransport(handler))
    created = await provider.create_reminder(Reminder("", "home", "Buy milk", due=datetime(2026, 8, 8, 12, tzinfo=UTC)))
    assert created.reminder_id == "apple-reminder-id"
    assert created.provider == "apple"
    assert seen["authorization"] == "Bearer secret"


@pytest.mark.asyncio
async def test_provider_refuses_false_success_without_reminder_id() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"reminder": {"reminder_id": "", "list_id": "home", "title": "No receipt"}})
    )
    provider = AppleReminderProvider(base_url="http://iris:8766", token="secret", transport=transport)
    with pytest.raises(RuntimeError, match="incomplete"):
        await provider.create_reminder(Reminder("", "home", "No receipt"))
