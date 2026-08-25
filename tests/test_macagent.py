from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from freyja.macagent import MacAgentClient, MacAgentHealth, MacAgentOperationRequest
from freyja.macagent_app import app as macagent_app
from freyja.main import app


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://iris:8765/health")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> dict:
        return self._payload


async def test_macagent_disabled_reports_no_reachability() -> None:
    client = MacAgentClient(enabled=False, token="secret")

    health = await client.health()

    assert health.enabled is False
    assert health.reachable is False
    assert health.authenticated is False
    assert health.error == "macagent disabled"


async def test_macagent_requires_token_even_on_local_network() -> None:
    client = MacAgentClient(enabled=True, token="")

    health = await client.health()

    assert health.enabled is True
    assert health.reachable is False
    assert health.authenticated is False
    assert health.error == "macagent token not configured"


async def test_macagent_health_uses_bearer_token_and_strict_capabilities() -> None:
    client = MacAgentClient(enabled=True, token="secret", base_url="http://iris:8765")
    mock_http = AsyncMock()
    mock_http.get.return_value = _Response(
        {
            "enabled": True,
            "reachable": True,
            "authenticated": True,
            "host": "iris",
            "capabilities": ["apple.messages.read", "apple.calendar.read", "apple.contacts.read"],
            "error": None,
        }
    )

    with patch("freyja.macagent.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = mock_http
        health = await client.health()

    assert health.reachable is True
    assert health.authenticated is True
    assert health.capabilities == ["apple.messages.read", "apple.calendar.read", "apple.contacts.read"]
    mock_http.get.assert_awaited_once_with(
        "http://iris:8765/health",
        headers={"Authorization": "Bearer secret"},
    )


def test_macagent_capability_model_covers_rev2_families() -> None:
    health = MacAgentHealth(
        enabled=True,
        reachable=True,
        authenticated=True,
        capabilities=[
            "apple.messages.read",
            "apple.messages.send",
            "apple.calendar.read",
            "apple.calendar.write",
            "apple.contacts.read",
            "apple.shortcuts.run",
        ],
    )

    families = {capability.rsplit(".", 1)[0] for capability in health.capabilities}
    assert families == {
        "apple.messages",
        "apple.calendar",
        "apple.contacts",
        "apple.shortcuts",
    }


async def test_macagent_rejects_unknown_capability_from_iris() -> None:
    client = MacAgentClient(enabled=True, token="secret", base_url="http://iris:8765")
    mock_http = AsyncMock()
    mock_http.get.return_value = _Response(
        {
            "enabled": True,
            "reachable": True,
            "authenticated": True,
            "host": "iris",
            "capabilities": ["apple.root.shell"],
            "error": None,
        }
    )

    with patch("freyja.macagent.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = mock_http
        health = await client.health()

    assert health.reachable is False
    assert "invalid macagent health payload" in (health.error or "")


def _operation_request(*, director_authorized: bool = True) -> MacAgentOperationRequest:
    return MacAgentOperationRequest(
        capability="apple.calendar.read",
        operation="list_events",
        arguments={"calendar_ids": ["family"]},
        request_id="req-macagent",
        actor="atlas_director",
        director_authorized=director_authorized,
        required_permission="household:calendar.read",
        principal={"client_type": "imessage", "client_subject": "family-member:abc"},
        person={"person_id": "joe"},
    )


async def test_macagent_invoke_requires_director_authorization() -> None:
    client = MacAgentClient(enabled=True, token="secret")

    result = await client.invoke(_operation_request(director_authorized=False))

    assert result.ok is False
    assert result.error == "director authorization required"


async def test_macagent_invoke_posts_authorized_envelope_with_bearer_token() -> None:
    client = MacAgentClient(enabled=True, token="secret", base_url="http://iris:8765")
    mock_http = AsyncMock()
    mock_http.post.return_value = _Response(
        {
            "ok": True,
            "capability": "apple.calendar.read",
            "operation": "list_events",
            "output": {"events": []},
            "error": None,
            "duration_ms": 12,
        }
    )

    with patch("freyja.macagent.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = mock_http
        result = await client.invoke(_operation_request())

    assert result.ok is True
    assert result.output == {"events": []}
    mock_http.post.assert_awaited_once()
    _, kwargs = mock_http.post.call_args
    assert kwargs["headers"] == {"Authorization": "Bearer secret"}
    assert kwargs["json"]["director_authorized"] is True
    assert kwargs["json"]["actor"] == "atlas_director"
    assert kwargs["json"]["required_permission"] == "household:calendar.read"
    assert kwargs["json"]["principal"]["client_type"] == "imessage"


async def test_macagent_invoke_rejects_invalid_operation_payload() -> None:
    client = MacAgentClient(enabled=True, token="secret", base_url="http://iris:8765")
    mock_http = AsyncMock()
    mock_http.post.return_value = _Response({"ok": True, "capability": "apple.root.shell"})

    with patch("freyja.macagent.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = mock_http
        result = await client.invoke(_operation_request())

    assert result.ok is False
    assert "invalid macagent operation payload" in (result.error or "")


def test_director_macagent_health_does_not_grant_authorization() -> None:
    test_client = TestClient(app)
    with patch("freyja.main.macagent.health", new_callable=AsyncMock) as mock_health:
        mock_health.return_value = MacAgentHealth(
            enabled=True,
            reachable=True,
            authenticated=True,
            host="iris",
            capabilities=["apple.calendar.read"],
        )
        response = test_client.get("/macagent/health")

    assert response.status_code == 200
    data = response.json()
    assert data["authority"] == "atlas_director"
    assert data["authorization_granted_by_macagent"] is False


def test_macagent_app_health_requires_bearer_token(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "macagent_token", "secret")
    test_client = TestClient(macagent_app)

    response = test_client.get("/health")

    assert response.status_code == 401


def test_macagent_app_health_reports_rev2_capabilities(monkeypatch) -> None:
    from certification.rev2_readiness import REQUIRED_REV2_CAPABILITIES
    from freyja.config import settings

    monkeypatch.setattr(settings, "macagent_token", "secret")
    test_client = TestClient(macagent_app)

    response = test_client.get("/health", headers={"Authorization": "Bearer secret"})

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["reachable"] is True
    assert data["authenticated"] is True
    assert set(REQUIRED_REV2_CAPABILITIES).issubset(set(data["capabilities"]))


def test_macagent_app_rejects_unauthorized_operation(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "macagent_token", "secret")
    test_client = TestClient(macagent_app)
    request = _operation_request(director_authorized=False)

    response = test_client.post(
        f"/capabilities/{request.capability}",
        headers={"Authorization": "Bearer secret"},
        json=request.model_dump(mode="json"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "director authorization required"


def test_macagent_app_lists_calendar_events(monkeypatch) -> None:
    from freyja.config import settings
    from freyja.calendar.models import CalendarEvent

    monkeypatch.setattr(settings, "macagent_token", "secret")
    test_client = TestClient(macagent_app)
    request = _operation_request()
    request.arguments.update(
        {
            "calendar_selectors": ["iCloud::Family"],
            "start": "2026-08-24T10:00:00+00:00",
            "end": "2026-08-25T10:00:00+00:00",
        }
    )
    event = CalendarEvent(
        event_id="event-1",
        calendar_id="iCloud::Family",
        title="Soccer",
        start=datetime(2026, 8, 24, 12, tzinfo=UTC),
        end=datetime(2026, 8, 24, 13, tzinfo=UTC),
    )

    class Provider:
        async def list_events(self, **kwargs):
            assert kwargs["calendar_ids"] == ["iCloud::Family"]
            return [event]

    with patch("freyja.macagent_app.AppleCalendarProvider", return_value=Provider()):
        response = test_client.post(
            f"/capabilities/{request.capability}",
            headers={"Authorization": "Bearer secret"},
            json=request.model_dump(mode="json"),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["output"]["events"][0]["event_id"] == "event-1"


def test_macagent_app_calendar_write_requires_director_approval(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "macagent_token", "secret")
    test_client = TestClient(macagent_app)
    request = MacAgentOperationRequest(
        capability="apple.calendar.write",
        operation="delete_event",
        arguments={"event_id": "event-1"},
        request_id="req-write",
        actor="atlas_director",
        director_authorized=True,
        required_permission="household:calendar.write",
        approval_granted=False,
    )

    response = test_client.post(
        f"/capabilities/{request.capability}",
        headers={"Authorization": "Bearer secret"},
        json=request.model_dump(mode="json"),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is False
    assert data["error"] == "director approval required"


def test_macagent_app_sends_imessage_reply_after_approval(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "macagent_token", "secret")
    sent = {}

    class Transport:
        async def send(self, reply):
            sent["chat_id"] = reply.chat_id
            sent["text"] = reply.text

    test_client = TestClient(macagent_app)
    request = MacAgentOperationRequest(
        capability="apple.messages.send",
        operation="send_reply",
        arguments={"chat_id": 123, "text": "On it"},
        request_id="req-msg",
        actor="atlas_director",
        director_authorized=True,
        required_permission="apple.messages.send",
        approval_granted=True,
    )

    with patch("freyja.macagent_app.IMessageTransport", return_value=Transport()):
        response = test_client.post(
            f"/capabilities/{request.capability}",
            headers={"Authorization": "Bearer secret"},
            json=request.model_dump(mode="json"),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["output"] == {"sent": True, "chat_id": 123}
    assert sent == {"chat_id": 123, "text": "On it"}


def test_macagent_app_reads_recent_messages(monkeypatch) -> None:
    from connectors.imessage.models import IMessage
    from freyja.config import settings

    monkeypatch.setattr(settings, "macagent_token", "secret")
    message = IMessage(
        sender="joe@example.com",
        text="hi",
        message_id="guid-1",
        chat_id=1,
        chat_identifier="chat-1",
        timestamp=datetime(2026, 8, 24, 12, tzinfo=UTC),
    )

    class Transport:
        async def recent_messages(self):
            return [message]

    test_client = TestClient(macagent_app)
    request = MacAgentOperationRequest(
        capability="apple.messages.read",
        operation="recent_messages",
        arguments={"limit": 10},
        request_id="req-read-msg",
        actor="atlas_director",
        director_authorized=True,
    )

    with patch("freyja.macagent_app.IMessageTransport", return_value=Transport()):
        response = test_client.post(
            f"/capabilities/{request.capability}",
            headers={"Authorization": "Bearer secret"},
            json=request.model_dump(mode="json"),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["output"]["messages"][0]["message_id"] == "guid-1"


def test_macagent_app_reads_contacts_without_identifiers_by_default(monkeypatch) -> None:
    from freyja.config import settings
    from freyja.identity.models import Identity, Person

    monkeypatch.setattr(settings, "macagent_token", "secret")
    person = Person(
        person_id="apple-1",
        display_name="Joe",
        identities=(Identity(kind="email", value="joe@example.com"),),
    )
    test_client = TestClient(macagent_app)
    request = MacAgentOperationRequest(
        capability="apple.contacts.read",
        operation="list_contacts",
        arguments={},
        request_id="req-contacts",
        actor="atlas_director",
        director_authorized=True,
    )

    with patch("freyja.macagent_app.load_apple_contacts", return_value=[person]):
        response = test_client.post(
            f"/capabilities/{request.capability}",
            headers={"Authorization": "Bearer secret"},
            json=request.model_dump(mode="json"),
        )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["output"]["contacts"][0]["person_id"] == "apple-1"
    assert data["output"]["contacts"][0]["identity_kinds"] == ["email"]
    assert "identities" not in data["output"]["contacts"][0]
