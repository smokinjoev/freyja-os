from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from connectors.gmail.gateway import GmailGateway
from connectors.gmail.models import GmailAttachment, GmailMessage
from connectors.messaging import parse_allowed_senders


def _make_request() -> httpx.Request:
    return httpx.Request("POST", "http://127.0.0.1:8000/route")


def _ok_response(data: dict) -> httpx.Response:
    return httpx.Response(200, json=data, request=_make_request())


def make_message(
    *,
    sender: str = "worker@example.com",
    text: str = "Hello Freyja",
    html: str | None = None,
    message_id: str = "gmail-001",
    thread_id: str = "thread-abc",
    attachments: list[GmailAttachment] | None = None,
) -> GmailMessage:
    return GmailMessage(
        message_id=message_id,
        thread_id=thread_id,
        sender=sender,
        recipients=["freyja@example.com"],
        subject="Status",
        text=text,
        html=html,
        received_at="2026-08-19T10:00:00Z",
        attachments=attachments or [],
    )


@pytest.fixture
async def enabled_gateway():
    gw = GmailGateway()
    gw._enabled = True
    gw._identity = "freyja@example.com"
    gw._allowed_senders = {"worker@example.com"}
    gw._allowed_identities = {}
    gw._max_message_chars = 12000
    gw._director_url = "http://127.0.0.1:8000"
    gw._timeout = 5.0
    yield gw
    await gw.close()


@pytest.mark.asyncio
async def test_approved_sender_is_forwarded_with_gmail_thread(enabled_gateway):
    message = make_message()

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "Hello from Director"})
        result = await enabled_gateway.handle(message)

    assert result is not None
    assert result.thread_id == "thread-abc"
    assert result.to == "worker@example.com"
    assert result.subject == "Re: Status"
    assert result.text == "Hello from Director"
    payload = mock_post.await_args.kwargs["json"]
    assert payload["provider"] == "auto"
    assert payload["tools_required"] is True
    assert payload["privacy"] == "private"
    assert payload["conversation_id"].startswith("gmail-thread:")
    assert "Hello Freyja" in payload["prompt"]
    headers = mock_post.await_args.kwargs["headers"]
    assert headers["X-Freyja-Client-Type"] == "gmail"
    assert headers["X-Freyja-Conversation-Id"] == payload["conversation_id"]
    assert headers["X-Freyja-Gmail-Identity"] == "freyja@example.com"


@pytest.mark.asyncio
async def test_html_is_sanitized_before_director(enabled_gateway):
    message = make_message(
        text="",
        html='<html><body><p>Hello</p><img src="https://tracker.example/pixel">'
        '<script>alert("x")</script><a href="https://example.com">there</a></body></html>',
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "Sanitized"})
        result = await enabled_gateway.handle(message)

    assert result is not None
    prompt = mock_post.await_args.kwargs["json"]["prompt"]
    assert "Hello" in prompt
    assert "there" in prompt
    assert "<script" not in prompt
    assert "tracker.example" not in prompt
    assert "https://example.com" not in prompt


@pytest.mark.asyncio
async def test_attachments_are_metadata_only(enabled_gateway):
    message = make_message(
        attachments=[
            GmailAttachment(
                filename="invoice.pdf",
                mime_type="application/pdf",
                size_bytes=42,
                attachment_id="att-secret",
            )
        ]
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "Got it"})
        result = await enabled_gateway.handle(message)

    assert result is not None
    prompt = mock_post.await_args.kwargs["json"]["prompt"]
    assert "invoice.pdf" in prompt
    assert "application/pdf" in prompt
    assert "untrusted input" in prompt
    assert "att-secret" not in prompt


@pytest.mark.asyncio
async def test_unknown_sender_is_not_forwarded(enabled_gateway):
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        result = await enabled_gateway.handle(make_message(sender="blocked@example.com"))

    assert result is None
    mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_family_alias_sets_shared_subject(enabled_gateway):
    enabled_gateway._allowed_identities = parse_allowed_senders(
        "joe=worker@example.com",
        "gmail",
    )
    enabled_gateway._allowed_senders = set(enabled_gateway._allowed_identities)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "Hi Joe"})
        result = await enabled_gateway.handle(make_message())

    assert result is not None
    headers = mock_post.await_args.kwargs["headers"]
    assert headers["X-Freyja-Family-Member"] == "joe"
    assert headers["X-Freyja-Client-Subject"].startswith("family-member:")
