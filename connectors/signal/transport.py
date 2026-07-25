from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from connectors.signal.config import SignalSettings
from connectors.signal.models import InboundMessage, OutboundResponse

logger = logging.getLogger(__name__)


class SignalMessageHandler(Protocol):
    async def handle(self, message: InboundMessage) -> OutboundResponse: ...


class SignalTransportError(RuntimeError):
    """A recoverable signal-cli REST transport failure."""


class UnsupportedSignalEvent(ValueError):
    """Signal traffic that is not a supported inbound data message."""


class SignalRestTransport:
    """HTTP adapter for bbernhard/signal-cli-rest-api.

    The adapter owns wire-format parsing and delivery. SignalGateway remains
    responsible for authorization, duplicate suppression, and message policy.
    """

    def __init__(
        self,
        gateway: SignalMessageHandler,
        settings: SignalSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._gateway = gateway
        self._settings = settings or SignalSettings()
        self._base_url = self._settings.signal_rest_api_url.rstrip("/")
        self._account_number = self._settings.signal_account_number.strip()
        self._http_client = http_client
        self._owns_http_client = http_client is None

    async def _client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=self._settings.signal_transport_timeout_seconds
            )
            self._owns_http_client = True
        return self._http_client

    @staticmethod
    def parse_event(event: Any) -> InboundMessage:
        """Normalize a receive response event or JSON-RPC receive notification."""
        if not isinstance(event, dict):
            raise UnsupportedSignalEvent("event is not an object")

        payload = event
        params = payload.get("params")
        if isinstance(params, dict):
            payload = params
            result = payload.get("result")
            if isinstance(result, dict):
                payload = result

        envelope = payload.get("envelope")
        if not isinstance(envelope, dict):
            raise UnsupportedSignalEvent("event has no envelope")

        data_message = envelope.get("dataMessage")
        if not isinstance(data_message, dict):
            raise UnsupportedSignalEvent("event is not a data message")

        sender = envelope.get("sourceNumber") or envelope.get("source")
        timestamp_ms = data_message.get("timestamp") or envelope.get("timestamp")
        if not isinstance(sender, str) or not sender.strip():
            raise UnsupportedSignalEvent("data message has no sender")
        if not isinstance(timestamp_ms, int):
            raise UnsupportedSignalEvent("data message has no timestamp")

        text = data_message.get("message")
        if not isinstance(text, str):
            text = ""

        group_id: str | None = None
        group_info = data_message.get("groupInfo")
        if isinstance(group_info, dict):
            raw_group_id = group_info.get("groupId")
            if isinstance(raw_group_id, str) and raw_group_id:
                group_id = raw_group_id

        try:
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise UnsupportedSignalEvent("data message has an invalid timestamp") from exc

        return InboundMessage(
            sender=sender,
            text=text,
            message_id=f"{sender}:{timestamp_ms}",
            timestamp=timestamp,
            group_id=group_id,
        )

    async def poll_once(self) -> list[OutboundResponse]:
        """Fetch available events, forward supported messages, and send replies."""
        if not self._account_number:
            raise SignalTransportError("SIGNAL_ACCOUNT_NUMBER is not configured")

        account = quote(self._account_number, safe="")
        try:
            client = await self._client()
            response = await client.get(f"{self._base_url}/v1/receive/{account}")
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                {
                    "event": "signal_transport_receive_failed",
                    "error_type": type(exc).__name__,
                }
            )
            raise SignalTransportError("Signal receive failed") from exc

        if payload is None:
            events: list[Any] = []
        elif isinstance(payload, list):
            events = payload
        elif isinstance(payload, dict) and "envelope" in payload:
            events = [payload]
        else:
            raise SignalTransportError("Signal receive returned an unexpected payload")

        replies: list[OutboundResponse] = []
        for event in events:
            try:
                message = self.parse_event(event)
            except UnsupportedSignalEvent as exc:
                logger.info(
                    {
                        "event": "signal_transport_event_rejected",
                        "reason": str(exc),
                    }
                )
                continue

            reply = await self._gateway.handle(message)
            await self.send(reply)
            replies.append(reply)

        return replies

    async def send(self, response: OutboundResponse) -> None:
        """Deliver a normalized gateway response through the REST wrapper."""
        if not self._account_number:
            raise SignalTransportError("SIGNAL_ACCOUNT_NUMBER is not configured")

        payload = {
            "message": response.text,
            "number": self._account_number,
            "recipients": [response.recipient],
        }
        try:
            client = await self._client()
            result = await client.post(f"{self._base_url}/v2/send", json=payload)
            result.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                {
                    "event": "signal_transport_send_failed",
                    "recipient": response.recipient,
                    "error_type": type(exc).__name__,
                }
            )
            raise SignalTransportError("Signal send failed") from exc

    async def close(self) -> None:
        if (
            self._owns_http_client
            and self._http_client is not None
            and not self._http_client.is_closed
        ):
            await self._http_client.aclose()
