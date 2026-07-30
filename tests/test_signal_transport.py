from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from connectors.signal.config import SignalSettings
from connectors.signal.models import OutboundResponse
from connectors.signal.transport import (
    SignalRestTransport,
    SignalTransportError,
    UnsupportedSignalEvent,
)

ACCOUNT = "+15550000000"
SENDER = "+15551234567"
TIMESTAMP_MS = 1_721_908_800_123


def native_event(text: str = "Hello Freyja") -> dict:
    return {
        "envelope": {
            "source": SENDER,
            "sourceNumber": SENDER,
            "timestamp": TIMESTAMP_MS,
            "dataMessage": {
                "timestamp": TIMESTAMP_MS,
                "message": text,
                "attachments": [],
            },
        },
        "account": ACCOUNT,
    }


def transport_settings() -> SignalSettings:
    return SignalSettings(
        _env_file=None,
        signal_account_number=ACCOUNT,
        signal_rest_api_url="http://signal-api:8080",
    )


def test_parse_native_receive_payload():
    message = SignalRestTransport.parse_event(native_event())

    assert message.sender == SENDER
    assert message.text == "Hello Freyja"
    assert message.message_id == f"{SENDER}:{TIMESTAMP_MS}"
    assert message.timestamp is not None
    assert message.timestamp.tzinfo is not None
    assert message.group_id is None


def test_parse_json_rpc_wrapped_payload():
    event = {
        "jsonrpc": "2.0",
        "method": "receive",
        "params": {
            "envelope": native_event("Wrapped message")["envelope"],
            "account": ACCOUNT,
        },
    }

    message = SignalRestTransport.parse_event(event)

    assert message.sender == SENDER
    assert message.text == "Wrapped message"
    assert message.message_id == f"{SENDER}:{TIMESTAMP_MS}"


@pytest.mark.parametrize(
    "event",
    [
        {"envelope": {"sourceNumber": SENDER, "receiptMessage": {}}},
        {"envelope": {"sourceNumber": SENDER, "typingMessage": {}}},
        {"envelope": {"sourceNumber": SENDER, "syncMessage": {}}},
        {"account": ACCOUNT},
        "not-an-object",
    ],
)
def test_reject_unsupported_or_non_message_events(event):
    with pytest.raises(UnsupportedSignalEvent):
        SignalRestTransport.parse_event(event)


@pytest.mark.asyncio
async def test_poll_forwards_valid_message_and_sends_gateway_response():
    gateway = AsyncMock()
    gateway.handle.return_value = OutboundResponse(
        recipient=SENDER,
        text="Hello from Freyja",
        reply_to_message_id=f"{SENDER}:{TIMESTAMP_MS}",
    )
    requests: list[httpx.Request] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=[native_event()], request=request)
        return httpx.Response(201, json={"timestamp": "123"}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    transport = SignalRestTransport(gateway, transport_settings(), client)

    replies = await transport.poll_once()

    gateway.handle.assert_awaited_once()
    forwarded = gateway.handle.await_args.args[0]
    assert forwarded.sender == SENDER
    assert forwarded.text == "Hello Freyja"
    assert replies == [gateway.handle.return_value]
    assert [request.method for request in requests] == ["GET", "POST"]
    assert requests[0].url.path.endswith(f"/v1/receive/{ACCOUNT}")
    assert requests[1].url.path == "/v2/send"
    assert requests[1].content == (
        b'{"message":"Hello from Freyja","number":"+15550000000",'
        b'"recipients":["+15551234567"]}'
    )
    await client.aclose()


@pytest.mark.asyncio
async def test_unsupported_event_is_not_forwarded_or_replied_to():
    gateway = AsyncMock()
    request_methods: list[str] = []

    def handle_request(request: httpx.Request) -> httpx.Response:
        request_methods.append(request.method)
        return httpx.Response(
            200,
            json=[{"envelope": {"sourceNumber": SENDER, "receiptMessage": {}}}],
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    transport = SignalRestTransport(gateway, transport_settings(), client)

    replies = await transport.poll_once()

    assert replies == []
    gateway.handle.assert_not_awaited()
    assert request_methods == ["GET"]
    await client.aclose()


@pytest.mark.asyncio
async def test_self_message_is_not_forwarded_or_replied_to():
    gateway = AsyncMock()
    self_event = native_event("Sent from a linked device")
    self_event["envelope"]["source"] = ACCOUNT
    self_event["envelope"]["sourceNumber"] = ACCOUNT

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[self_event], request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    transport = SignalRestTransport(gateway, transport_settings(), client)

    replies = await transport.poll_once()

    assert replies == []
    gateway.handle.assert_not_awaited()
    await client.aclose()


@pytest.mark.asyncio
async def test_receive_http_failure_raises_transport_error():
    gateway = AsyncMock()

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    transport = SignalRestTransport(gateway, transport_settings(), client)

    with pytest.raises(SignalTransportError) as exc_info:
        await transport.poll_once()

    assert str(exc_info.value) == "Signal receive failed"
    gateway.handle.assert_not_awaited()
    await client.aclose()


@pytest.mark.asyncio
async def test_send_http_failure_raises_transport_error():
    gateway = AsyncMock()

    def handle_request(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "send failed"}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle_request))
    transport = SignalRestTransport(gateway, transport_settings(), client)
    response = OutboundResponse(recipient=SENDER, text="Safe reply")

    with pytest.raises(SignalTransportError) as exc_info:
        await transport.send(response)

    assert str(exc_info.value) == "Signal send failed"
    await client.aclose()
