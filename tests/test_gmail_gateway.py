from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from connectors.gmail.gateway import GmailGateway
from connectors.gmail.models import GmailAttachment, GmailMessage
from connectors.messaging import parse_allowed_senders
from tests.test_media import SIMPLE_PDF_BASE64


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
    assert mock_post.await_args.args[0].endswith("/canonical/route")
    payload = mock_post.await_args.kwargs["json"]
    assert payload["channel"] == "gmail"
    assert payload["permissions"] == ["director:route"]
    assert payload["channel_metadata"]["tools_required"] is True
    assert payload["channel_metadata"]["privacy"] == "private"
    assert payload["conversation_id"].startswith("gmail-thread:")
    assert "Hello Freyja" in payload["text"]
    headers = mock_post.await_args.kwargs["headers"]
    assert headers["X-Freyja-Client-Type"] == "gmail"
    assert headers["X-Freyja-Conversation-Id"] == payload["conversation_id"]
    assert headers["X-Freyja-Gmail-Identity"] == "freyja@example.com"
    assert headers["X-Freyja-Trace-Id"] == payload["trace_id"]


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
    prompt = mock_post.await_args.kwargs["json"]["text"]
    assert "Hello" in prompt
    assert "there" in prompt
    assert "<script" not in prompt
    assert "tracker.example" not in prompt
    assert "https://example.com" not in prompt


@pytest.mark.asyncio
async def test_image_only_gmail_message_forwards_image(enabled_gateway):
    message = make_message(
        text="",
        attachments=[
            GmailAttachment(
                filename="photo.jpg",
                mime_type="image/jpeg",
                size_bytes=4,
                data_base64="ZmFrZQ==",
            )
        ],
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "That is a photo."})
        result = await enabled_gateway.handle(message)

    assert result is not None
    payload = mock_post.await_args.kwargs["json"]
    assert "[No readable body text was provided.]" in payload["text"]
    assert payload["attachments"][0]["media_type"] == "image/jpeg"
    assert payload["attachments"][0]["data_base64"] == "ZmFrZQ=="
    assert payload["attachments"][0]["filename"] == "photo.jpg"


@pytest.mark.asyncio
async def test_gmail_missing_image_payload_is_not_sent_as_inspected_image(enabled_gateway):
    message = make_message(
        text="What is in this?",
        attachments=[
            GmailAttachment(
                filename="photo.jpg",
                mime_type="image/jpeg",
                size_bytes=1234,
                attachment_id="gmail-photo-id",
            )
        ],
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "I cannot inspect it."})
        result = await enabled_gateway.handle(message)

    assert result is not None
    payload = mock_post.await_args.kwargs["json"]
    assert payload["attachments"][0]["data_base64"] is None
    assert "image payload unavailable" in payload["text"]
    assert "Do not describe their contents" in payload["text"]
    assert "gmail-photo-id" not in payload["text"]


@pytest.mark.asyncio
async def test_gmail_missing_pdf_payload_gets_document_honesty_note(enabled_gateway):
    message = make_message(
        attachments=[
            GmailAttachment(
                filename="brief.pdf",
                mime_type="application/pdf",
                size_bytes=9876,
                attachment_id="gmail-pdf-id",
            )
        ],
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "I need the PDF bytes."})
        result = await enabled_gateway.handle(message)

    assert result is not None
    payload = mock_post.await_args.kwargs["json"]
    assert payload["attachments"][0]["data_base64"] is None
    assert "document payload unavailable" in payload["text"]
    assert "Do not describe their contents" in payload["text"]
    assert "gmail-pdf-id" not in payload["text"]


@pytest.mark.asyncio
async def test_gmail_pdf_payload_adds_extracted_document_text(enabled_gateway):
    message = make_message(
        text="What does this say?",
        attachments=[
            GmailAttachment(
                filename="plan.pdf",
                mime_type="application/pdf",
                data_base64=SIMPLE_PDF_BASE64,
            )
        ],
    )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = _ok_response({"response": "It mentions dinner Friday."})
        result = await enabled_gateway.handle(message)

    assert result is not None
    payload = mock_post.await_args.kwargs["json"]
    assert "Extracted PDF/document text" in payload["text"]
    assert "Family dinner Friday" in payload["text"]


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
    prompt = mock_post.await_args.kwargs["json"]["text"]
    assert "invoice.pdf" in prompt
    assert "application/pdf" in prompt
    assert "untrusted input" in prompt
    assert "att-secret" not in prompt


@pytest.mark.asyncio
async def test_gmail_director_errors_log_sender_hash_not_address(enabled_gateway, caplog):
    caplog.set_level(logging.WARNING, logger="connectors.gmail.gateway")

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
    assert result.success is False
    assert "gmail_gateway_director_error" in caplog.text
    assert "worker@example.com" not in caplog.text
    assert "sender_hash" in caplog.text


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
