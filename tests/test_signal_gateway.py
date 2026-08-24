from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from connectors.signal.config import SignalSettings
from connectors.signal.gateway import RejectionReason, SignalGateway
from connectors.signal.models import InboundMessage
from connectors.messaging import parse_allowed_senders


def _make_request() -> httpx.Request:
    return httpx.Request("POST", "http://127.0.0.1:8000/route")


def _ok_response(data: dict) -> httpx.Response:
    return httpx.Response(200, json=data, request=_make_request())


def _error_response(status: int, payload: dict | None = None, text: str = "") -> httpx.Response:
    body = payload or {}
    return httpx.Response(status, json=body, request=_make_request(), text=text)


@pytest.fixture
async def enabled_gateway(tmp_path, monkeypatch):
    monkeypatch.setenv("SIGNAL_ENABLED", "true")
    monkeypatch.setenv("SIGNAL_ALLOWED_SENDERS", "+15551234567")
    monkeypatch.setenv("SIGNAL_MAX_MESSAGE_CHARS", "4000")
    monkeypatch.setenv("FREYJA_DIRECTOR_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("SIGNAL_REQUEST_TIMEOUT_SECONDS", "5")

    gw = SignalGateway()
    gw._enabled = True
    gw._allowed_senders = {"+15551234567"}
    gw._max_message_chars = 4000
    gw._director_url = "http://127.0.0.1:8000"
    gw._timeout = 5.0
    yield gw
    if gw._http_client is not None and not gw._http_client.is_closed:
        await gw._http_client.aclose()


def make_message(sender: str, text: str, message_id: str, group_id: str | None = None) -> InboundMessage:
    return InboundMessage(
        sender=sender,
        text=text,
        message_id=message_id,
        group_id=group_id,
    )


@pytest.mark.asyncio
async def test_approved_sender_is_forwarded(enabled_gateway):
    message = make_message("+15551234567", "Hello Freyja", "msg-001")

    mock_response = _ok_response({
        "provider": "ollama",
        "model": "qwen2.5:1.5b",
        "response": "Local auto hello",
        "reason": "routine request defaults to local",
        "request_id": "req-001",
    })

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await enabled_gateway.handle(message)

    assert result.success is True
    assert result.recipient == "+15551234567"
    assert result.text == "Local auto hello"
    assert result.reply_to_message_id == "msg-001"
    mock_post.assert_awaited_once()
    _, kwargs = mock_post.call_args
    assert "Your name is Freyja" in kwargs["json"]["prompt"]
    assert kwargs["json"]["prompt"].endswith("Hello Freyja")
    assert kwargs["json"]["provider"] == "auto"
    assert kwargs["json"]["privacy"] == "private"
    assert kwargs["json"]["tools_required"] is False
    assert kwargs["json"]["conversation_id"].startswith("signal-conv:")
    headers = kwargs["headers"]
    assert headers["X-Freyja-Client-Type"] == "signal"
    assert headers["X-Freyja-Client-Subject"] == "agent:freyja"
    assert headers["X-Freyja-Account-Owner"] == "person:family"
    assert headers["X-Freyja-Agent-Id"] == "freyja"
    assert headers["X-Freyja-Conversation-Id"] == kwargs["json"]["conversation_id"]
    assert "+15551234567" not in str(headers)


@pytest.mark.asyncio
async def test_director_token_is_sent_as_bearer_header(enabled_gateway):
    enabled_gateway._director_token = "test-connector-token"
    message = make_message("+15551234567", "Hello Freyja", "msg-auth")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "Authenticated hello"})
        result = await enabled_gateway.handle(message)

    assert result.success is True
    headers = mock_post.await_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-connector-token"
    assert headers["X-Freyja-Client-Type"] == "signal"
    assert mock_post.await_args.kwargs["json"]["privacy"] == "private"


@pytest.mark.asyncio
async def test_signal_identity_mapping_happens_after_allowlist_validation(enabled_gateway):
    message = make_message("+19998887777", "Hello Freyja", "msg-unauthorized")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        result = await enabled_gateway.handle(message)

    assert result.success is False
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_blocked_sender_receives_rejection():
    gw = SignalGateway()
    gw._enabled = True
    gw._allowed_senders = {"+15551234567"}

    message = make_message("+19998887777", "Hello Freyja", "msg-002")
    result = await gw.handle(message)

    assert result.success is False
    assert "not authorized" in result.text.lower()


@pytest.mark.asyncio
async def test_rejection_logs_hash_sender_not_phone_number(caplog):
    gw = SignalGateway()
    gw._enabled = True
    gw._allowed_senders = {"+15551234567"}

    caplog.set_level(logging.INFO, logger="connectors.signal.gateway")
    result = await gw.handle(make_message("+19998887777", "Hello Freyja", "msg-log"))

    assert result.success is False
    assert "+19998887777" not in caplog.text
    assert "sender_hash" in caplog.text


@pytest.mark.asyncio
async def test_signal_director_trace_logs_agent_without_phone_number(enabled_gateway, caplog):
    enabled_gateway._allowed_identities = parse_allowed_senders("joe=+15551234567", "signal")
    enabled_gateway._allowed_senders = set(enabled_gateway._allowed_identities)
    caplog.set_level(logging.INFO, logger="connectors.signal.gateway")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response(
            {
                "provider": "ollama",
                "model": "qwen2.5:7b",
                "response": "Hi Joe",
                "request_id": "req-signal",
            }
        )
        result = await enabled_gateway.handle(make_message("+15551234567", "Hello", "msg-trace"))

    assert result.success is True
    assert "signal_gateway_director_request" in caplog.text
    assert "signal_gateway_director_response" in caplog.text
    assert "cloyd-gibbler" in caplog.text
    assert "req-signal" in caplog.text
    assert "+15551234567" not in caplog.text


@pytest.mark.asyncio
async def test_disabled_gateway_rejects_all():
    gw = SignalGateway()
    gw._enabled = False

    message = make_message("+15551234567", "Hello Freyja", "msg-003")
    result = await gw.handle(message)

    assert result.success is False
    assert result.text == "Freyja could not process your message. Please try again later."


@pytest.mark.asyncio
async def test_empty_message_is_rejected(enabled_gateway):
    message = make_message("+15551234567", "   ", "msg-004")
    result = await enabled_gateway.handle(message)

    assert result.success is False
    assert result.text == "Freyja could not process your message. Please try again later."


@pytest.mark.asyncio
async def test_oversized_message_is_rejected(enabled_gateway):
    long_text = "x" * 4001
    message = make_message("+15551234567", long_text, "msg-005")
    result = await enabled_gateway.handle(message)

    assert result.success is False
    assert result.text == "Freyja could not process your message. Please try again later."


@pytest.mark.asyncio
async def test_attachment_only_message_is_rejected(enabled_gateway):
    message = make_message("+15551234567", "", "msg-006")
    result = await enabled_gateway.handle(message)

    assert result.success is False
    assert result.text == "Freyja could not process your message. Please try again later."


@pytest.mark.asyncio
async def test_duplicate_message_is_rejected(enabled_gateway):
    message = make_message("+15551234567", "Hello again", "msg-007")

    mock_response = _ok_response({"response": "Hi"})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        first = await enabled_gateway.handle(message)
        second = await enabled_gateway.handle(message)

    assert first.success is True
    assert second.success is False
    assert mock_post.await_count == 1


@pytest.mark.asyncio
async def test_director_success_returns_response(enabled_gateway):
    message = make_message("+15551234567", "What is the weather?", "msg-008")
    mock_response = _ok_response({"response": "It is sunny."})

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        result = await enabled_gateway.handle(message)

    assert result.success is True
    assert result.text == "It is sunny."


@pytest.mark.asyncio
async def test_director_timeout_returns_safe_error(enabled_gateway):
    message = make_message("+15551234567", "Slow question", "msg-009")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Request timed out")
        result = await enabled_gateway.handle(message)

    assert result.success is False
    assert result.text == "Freyja could not process your message. Please try again later."


@pytest.mark.asyncio
async def test_director_503_returns_safe_error(enabled_gateway):
    message = make_message("+15551234567", "Broken question", "msg-010")

    error_response = _error_response(503, text="Service Unavailable")
    error_response.raise_for_status = lambda: (_ for _ in ()).throw(
        httpx.HTTPStatusError(
            "Service Unavailable",
            request=_make_request(),
            response=error_response,
        )
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = error_response
        result = await enabled_gateway.handle(message)

    assert result.success is False
    assert "sk-" not in result.text
    assert "Authorization" not in result.text
    assert "Bearer" not in result.text


@pytest.mark.asyncio
async def test_outbound_error_text_does_not_expose_internal_details(enabled_gateway):
    message = make_message("+15551234567", "Error question", "msg-011")

    error_response = _error_response(503, payload={"detail": "Authorization: Bearer sk-secret-12345"})
    error_response.raise_for_status = lambda: (_ for _ in ()).throw(
        httpx.HTTPStatusError(
            "Service Unavailable",
            request=_make_request(),
            response=error_response,
        )
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = error_response
        result = await enabled_gateway.handle(message)

    assert result.success is False
    assert "sk-" not in result.text
    assert "Authorization" not in result.text
    assert "Bearer" not in result.text
    assert "secret" not in result.text.lower()


@pytest.mark.asyncio
async def test_provider_defaults_to_auto(enabled_gateway):
    message = make_message("+15551234567", "Route me", "msg-012")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "OK"})
        await enabled_gateway.handle(message)

    _, kwargs = mock_post.call_args
    assert kwargs["json"]["provider"] == "auto"


@pytest.mark.asyncio
async def test_group_message_is_rejected(enabled_gateway):
    message = make_message("+15551234567", "Hello group", "msg-013", group_id="group-001")
    result = await enabled_gateway.handle(message)

    assert result.success is False
    assert result.text == "Freyja could not process your message. Please try again later."


def test_settings_allowed_sender_set():
    s = SignalSettings(signal_allowed_senders="+111,+222 , +333")
    assert s.allowed_sender_set == {"+111", "+222", "+333"}


def test_settings_allowed_sender_set_supports_family_aliases():
    s = SignalSettings(signal_allowed_senders="joe=+111,beth=+222")
    assert s.allowed_sender_set == {"+111", "+222"}
    assert s.allowed_sender_identities["+111"].member_id == "joe"


def test_settings_allowed_sender_set_empty():
    s = SignalSettings()
    assert s.allowed_sender_set == set()


@pytest.mark.asyncio
async def test_joe_alias_routes_to_cloyd_gibbler_private_agent(enabled_gateway):
    enabled_gateway._allowed_identities = parse_allowed_senders("joe=+15551234567,beth=+15557654321", "signal")
    enabled_gateway._allowed_senders = set(enabled_gateway._allowed_identities)
    message = make_message("+15551234567", "Hello from Joe", "msg-family")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "Hi Joe"})
        result = await enabled_gateway.handle(message)

    assert result.success is True
    payload = mock_post.await_args.kwargs["json"]
    headers = mock_post.await_args.kwargs["headers"]
    assert "Your name is Cloyd Gibbler" in payload["prompt"]
    assert "Required response identity: Cloyd Gibbler" in payload["prompt"]
    assert "Do not say you are Freyja" in payload["prompt"]
    assert payload["privacy"] == "private"
    assert payload["tools_required"] is False
    assert headers["X-Freyja-Family-Member"] == "joe"
    assert headers["X-Freyja-Client-Subject"] == "agent:cloyd-gibbler"
    assert headers["X-Freyja-Account-Owner"] == "person:joe"
    assert headers["X-Freyja-Agent-Id"] == "cloyd-gibbler"
    assert headers["X-Freyja-Person-Id"] == "joe"
    assert "+15551234567" not in str(headers)


@pytest.mark.asyncio
async def test_beth_alias_routes_to_benedict_private_agent(enabled_gateway):
    enabled_gateway._allowed_identities = parse_allowed_senders("joe=+15551234567,beth=+15557654321", "signal")
    enabled_gateway._allowed_senders = set(enabled_gateway._allowed_identities)
    message = make_message("+15557654321", "Hello from Beth", "msg-beth")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "Hi Beth"})
        result = await enabled_gateway.handle(message)

    assert result.success is True
    payload = mock_post.await_args.kwargs["json"]
    headers = mock_post.await_args.kwargs["headers"]
    assert "Your name is Benedict" in payload["prompt"]
    assert "Required response identity: Benedict" in payload["prompt"]
    assert "Do not say you are Freyja" in payload["prompt"]
    assert payload["privacy"] == "private"
    assert payload["tools_required"] is False
    assert headers["X-Freyja-Client-Subject"] == "agent:benedict"
    assert headers["X-Freyja-Account-Owner"] == "person:beth"
    assert headers["X-Freyja-Agent-Id"] == "benedict"


@pytest.mark.asyncio
async def test_family_alias_routes_to_freyja_household_agent(enabled_gateway):
    enabled_gateway._allowed_identities = parse_allowed_senders("family=+15551234567", "signal")
    enabled_gateway._allowed_senders = set(enabled_gateway._allowed_identities)
    message = make_message("+15551234567", "House status please", "msg-house")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "House is quiet"})
        result = await enabled_gateway.handle(message)

    assert result.success is True
    payload = mock_post.await_args.kwargs["json"]
    headers = mock_post.await_args.kwargs["headers"]
    assert "Your name is Freyja" in payload["prompt"]
    assert payload["privacy"] == "private"
    assert payload["tools_required"] is False
    assert headers["X-Freyja-Client-Subject"] == "agent:freyja"
    assert headers["X-Freyja-Account-Owner"] == "person:family"
    assert headers["X-Freyja-Agent-Id"] == "freyja"


@pytest.mark.asyncio
async def test_cloyd_coding_request_uses_local_reasoning_and_tools(enabled_gateway):
    enabled_gateway._allowed_identities = parse_allowed_senders(
        "joe=+15551234567",
        "signal",
    )
    enabled_gateway._allowed_senders = set(enabled_gateway._allowed_identities)
    message = make_message(
        "+15551234567",
        "Cloyd, fix this test and run pytest",
        "msg-cloyd-code",
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "I inspected the failure."})
        result = await enabled_gateway.handle(message)

    assert result.success is True
    payload = mock_post.await_args.kwargs["json"]
    assert payload["provider"] == "local_reasoning"
    assert payload["task_type"] == "coding"
    assert payload["tools_required"] is True
    assert "CLOYD LOCAL CODER MODE" in payload["prompt"]
    assert "inspect -> reason -> edit -> tests -> diff" in payload["prompt"]


@pytest.mark.asyncio
async def test_non_cloyd_coding_words_do_not_grant_coder_mode(enabled_gateway):
    enabled_gateway._allowed_identities = parse_allowed_senders(
        "beth=+15557654321",
        "signal",
    )
    enabled_gateway._allowed_senders = set(enabled_gateway._allowed_identities)
    message = make_message(
        "+15557654321",
        "Can you run pytest?",
        "msg-beth-code",
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "No coder access."})
        result = await enabled_gateway.handle(message)

    assert result.success is True
    payload = mock_post.await_args.kwargs["json"]
    assert payload["provider"] == "auto"
    assert payload["tools_required"] is False
    assert "CLOYD LOCAL CODER MODE" not in payload["prompt"]
