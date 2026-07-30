from __future__ import annotations

import logging
from collections import deque

import httpx

from connectors.signal.config import settings
from connectors.signal.models import InboundMessage, OutboundResponse

logger = logging.getLogger(__name__)

_MAX_RECENT_IDS = 1000
_SAFE_ERROR_TEXT = "Freyja could not process your message. Please try again later."


class RejectionReason:
    DISABLED = "gateway_disabled"
    UNKNOWN_SENDER = "unknown_sender"
    GROUP_MESSAGE = "group_message"
    EMPTY_MESSAGE = "empty_message"
    OVERSIZED_MESSAGE = "oversized_message"
    ATTACHMENT_ONLY = "attachment_only"
    DUPLICATE_MESSAGE = "duplicate_message"


class SignalGateway:
    """Receive normalized Signal messages, enforce policy, and forward to the Director."""

    def __init__(self) -> None:
        self._enabled = settings.signal_enabled
        self._allowed_senders = settings.allowed_sender_set
        self._max_message_chars = settings.signal_max_message_chars
        self._director_url = settings.freyja_director_url.rstrip("/")
        self._director_token = settings.freyja_connector_token
        self._timeout = settings.signal_request_timeout_seconds
        self._recent_message_ids: deque[str] = deque(maxlen=_MAX_RECENT_IDS)
        self._http_client: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def _client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)
        return self._http_client

    async def handle(self, message: InboundMessage) -> OutboundResponse:
        if not self._enabled:
            logger.info({
                "event": "signal_gateway_rejected",
                "reason": RejectionReason.DISABLED,
                "sender": message.sender,
                "message_id": message.message_id,
            })
            return OutboundResponse(
                recipient=message.sender,
                text=_SAFE_ERROR_TEXT,
                reply_to_message_id=message.message_id,
                success=False,
            )

        if message.group_id is not None:
            return self._reject(message, RejectionReason.GROUP_MESSAGE)

        if message.sender not in self._allowed_senders:
            logger.info({
                "event": "signal_gateway_rejected",
                "reason": RejectionReason.UNKNOWN_SENDER,
                "sender": message.sender,
                "message_id": message.message_id,
            })
            return OutboundResponse(
                recipient=message.sender,
                text="You are not authorized to use this gateway.",
                reply_to_message_id=message.message_id,
                success=False,
            )

        if not message.has_text:
            return self._reject(message, RejectionReason.EMPTY_MESSAGE)

        if message.is_attachment_only:
            return self._reject(message, RejectionReason.ATTACHMENT_ONLY)

        if len(message.text) > self._max_message_chars:
            return self._reject(message, RejectionReason.OVERSIZED_MESSAGE)

        if message.message_id in self._recent_message_ids:
            return self._reject(message, RejectionReason.DUPLICATE_MESSAGE)

        self._recent_message_ids.append(message.message_id)

        return await self._forward(message)

    def _reject(self, message: InboundMessage, reason: str) -> OutboundResponse:
        logger.info({
            "event": "signal_gateway_rejected",
            "reason": reason,
            "sender": message.sender,
            "message_id": message.message_id,
            "text_length": len(message.text),
        })
        return OutboundResponse(
            recipient=message.sender,
            text=_SAFE_ERROR_TEXT,
            reply_to_message_id=message.message_id,
            success=False,
        )

    async def _forward(self, message: InboundMessage) -> OutboundResponse:
        payload = {
            "prompt": message.text,
            "provider": "auto",
        }

        try:
            client = await self._client()
            headers = (
                {"Authorization": f"Bearer {self._director_token}"}
                if self._director_token
                else None
            )
            response = await client.post(
                f"{self._director_url}/route",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            text = data.get("response", "")
            if not text:
                return self._safe_error_response(message)

            return OutboundResponse(
                recipient=message.sender,
                text=text,
                reply_to_message_id=message.message_id,
                success=True,
            )

        except httpx.TimeoutException:
            logger.warning({
                "event": "signal_gateway_director_timeout",
                "sender": message.sender,
                "message_id": message.message_id,
            })
            return self._safe_error_response(message)

        except httpx.HTTPStatusError as exc:
            logger.warning({
                "event": "signal_gateway_director_error",
                "sender": message.sender,
                "message_id": message.message_id,
                "status_code": exc.response.status_code,
            })
            return self._safe_error_response(message)

        except Exception:
            logger.exception({
                "event": "signal_gateway_unexpected_error",
                "sender": message.sender,
                "message_id": message.message_id,
            })
            return self._safe_error_response(message)

    def _safe_error_response(self, message: InboundMessage) -> OutboundResponse:
        return OutboundResponse(
            recipient=message.sender,
            text=_SAFE_ERROR_TEXT,
            reply_to_message_id=message.message_id,
            success=False,
        )

    async def close(self) -> None:
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()


gateway = SignalGateway()
