from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from connectors.imessage.gateway import IMessageGateway
from connectors.imessage.models import IMessage
from connectors.messaging import parse_allowed_senders


def _make_request() -> httpx.Request:
    return httpx.Request("POST", "http://127.0.0.1:8000/route")


def _ok_response(data: dict) -> httpx.Response:
    return httpx.Response(200, json=data, request=_make_request())


def make_message(
    sender: str = "+15551234567",
    text: str = "Hello Freyja",
    message_id: str = "imsg-001",
    *,
    is_group: bool = False,
    is_from_me: bool = False,
) -> IMessage:
    return IMessage(
        sender=sender,
        text=text,
        message_id=message_id,
        chat_id=7,
        chat_identifier=sender,
        timestamp="2026-07-30T04:09:38.511Z",
        is_group=is_group,
        is_from_me=is_from_me,
    )


@pytest.fixture
async def enabled_gateway():
    gw = IMessageGateway()
    gw._enabled = True
    gw._allowed_senders = {"+15551234567"}
    gw._max_message_chars = 4000
    gw._director_url = "http://127.0.0.1:8000"
    gw._timeout = 5.0
    yield gw
    await gw.close()


@pytest.mark.asyncio
async def test_approved_sender_is_forwarded(enabled_gateway):
    message = make_message()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "Hello from Mars"})
        result = await enabled_gateway.handle(message)

    assert result is not None
    assert result.chat_id == 7
    assert result.text == "Hello from Mars"
    mock_post.assert_awaited_once()
    payload = mock_post.await_args.kwargs["json"]
    assert payload["prompt"] == "Hello Freyja"
    assert payload["provider"] == "auto"
    assert payload["tools_required"] is True
    assert payload["conversation_id"].startswith("imessage-conv:")
    headers = mock_post.await_args.kwargs["headers"]
    assert headers["X-Freyja-Client-Type"] == "imessage"
    assert headers["X-Freyja-Client-Subject"].startswith("imessage:")
    assert headers["X-Freyja-Conversation-Id"] == payload["conversation_id"]
    assert "+15551234567" not in str(headers)


@pytest.mark.asyncio
async def test_director_token_is_sent_as_bearer_header(enabled_gateway):
    enabled_gateway._director_token = "test-token"

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "Authenticated"})
        result = await enabled_gateway.handle(make_message())

    assert result is not None
    headers = mock_post.await_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["X-Freyja-Client-Type"] == "imessage"


@pytest.mark.asyncio
async def test_imessage_identity_mapping_happens_after_allowlist_validation(enabled_gateway):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        result = await enabled_gateway.handle(make_message(sender="+15559999999"))

    assert result is None
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_gateway_drops_message():
    gw = IMessageGateway()
    gw._enabled = False

    assert await gw.handle(make_message()) is None


@pytest.mark.asyncio
async def test_unknown_sender_is_dropped(enabled_gateway):
    assert await enabled_gateway.handle(make_message(sender="+15559999999")) is None


@pytest.mark.asyncio
async def test_group_message_is_dropped(enabled_gateway):
    assert await enabled_gateway.handle(make_message(is_group=True)) is None


@pytest.mark.asyncio
async def test_self_message_is_dropped(enabled_gateway):
    assert await enabled_gateway.handle(make_message(is_from_me=True)) is None


@pytest.mark.asyncio
async def test_prefixed_self_message_is_forwarded_without_prefix(enabled_gateway):
    message = make_message(text="Freyja: How many lights are on at home?", is_from_me=True)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "Home Assistant reports 2 visible lights currently on."})
        result = await enabled_gateway.handle(message)

    assert result is not None
    assert result.text == "Home Assistant reports 2 visible lights currently on."
    payload = mock_post.await_args.kwargs["json"]
    assert payload["prompt"] == "How many lights are on at home?"
    assert payload["tools_required"] is True


@pytest.mark.asyncio
async def test_empty_message_is_dropped(enabled_gateway):
    assert await enabled_gateway.handle(make_message(text=" ")) is None


@pytest.mark.asyncio
async def test_oversized_message_returns_safe_error(enabled_gateway):
    message = make_message(text="x" * 4001)

    result = await enabled_gateway.handle(message)

    assert result is not None
    assert result.chat_id == 7
    assert result.text == "Freyja could not process your message. Please try again later."


@pytest.mark.asyncio
async def test_duplicate_message_is_dropped_after_first_forward(enabled_gateway):
    message = make_message()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "First"})
        first = await enabled_gateway.handle(message)
        second = await enabled_gateway.handle(message)

    assert first is not None
    assert second is None
    assert mock_post.await_count == 1


@pytest.mark.asyncio
async def test_director_error_returns_safe_error(enabled_gateway):
    error_response = httpx.Response(503, json={}, request=_make_request())
    error_response.raise_for_status = lambda: (_ for _ in ()).throw(
        httpx.HTTPStatusError(
            "Service Unavailable",
            request=_make_request(),
            response=error_response,
        )
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = error_response
        result = await enabled_gateway.handle(make_message())

    assert result is not None
    assert result.text == "Freyja could not process your message. Please try again later."


@pytest.mark.asyncio
async def test_family_member_alias_uses_shared_memory_subject(enabled_gateway):
    enabled_gateway._allowed_identities = parse_allowed_senders("joe=+15551234567,beth=beth@example.com", "imessage")
    enabled_gateway._allowed_senders = set(enabled_gateway._allowed_identities)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "Hi Joe"})
        result = await enabled_gateway.handle(make_message(sender="+15551234567"))

    assert result is not None
    headers = mock_post.await_args.kwargs["headers"]
    assert headers["X-Freyja-Family-Member"] == "joe"
    assert headers["X-Freyja-Client-Subject"].startswith("family-member:")
    assert "+15551234567" not in str(headers)
