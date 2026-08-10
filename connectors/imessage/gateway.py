from __future__ import annotations

import logging
from collections import deque

import httpx

from connectors.imessage.config import settings
from connectors.imessage.models import IMessage, IMessageReply
from connectors.messaging import AuthorizedSender
from freyja.memory.principal import build_memory_principal

logger = logging.getLogger(__name__)

_MAX_RECENT_IDS = 1000
_SAFE_ERROR_TEXT = "Freyja could not process your message. Please try again later."


class RejectionReason:
    DISABLED = "gateway_disabled"
    UNKNOWN_SENDER = "unknown_sender"
    GROUP_MESSAGE = "group_message"
    SELF_MESSAGE = "self_message"
    EMPTY_MESSAGE = "empty_message"
    OVERSIZED_MESSAGE = "oversized_message"
    DUPLICATE_MESSAGE = "duplicate_message"


class IMessageGateway:
    """Authorize native iMessage events and forward them to the Director."""

    def __init__(self) -> None:
        self._enabled = settings.imessage_enabled
        self._allowed_senders = settings.allowed_sender_set
        self._allowed_identities = settings.allowed_sender_identities
        self._max_message_chars = settings.imessage_max_message_chars
        self._director_url = settings.freyja_director_url.rstrip("/")
        self._director_token = settings.freyja_connector_token
        self._timeout = settings.imessage_request_timeout_seconds
        self._recent_message_ids: deque[str] = deque(maxlen=_MAX_RECENT_IDS)
        self._http_client: httpx.AsyncClient | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def _client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=self._timeout)
        return self._http_client

    async def handle(self, message: IMessage) -> IMessageReply | None:
        if not self._enabled:
            self._log_rejection(message, RejectionReason.DISABLED)
            return None

        if message.is_from_me:
            self._log_rejection(message, RejectionReason.SELF_MESSAGE)
            return None

        if message.is_group:
            self._log_rejection(message, RejectionReason.GROUP_MESSAGE)
            return None

        identity = self._identity_for_sender(message.sender)
        if identity is None:
            self._log_rejection(message, RejectionReason.UNKNOWN_SENDER)
            return None

        if not message.text.strip():
            self._log_rejection(message, RejectionReason.EMPTY_MESSAGE)
            return None

        if len(message.text) > self._max_message_chars:
            self._log_rejection(message, RejectionReason.OVERSIZED_MESSAGE)
            return self._safe_error_response(message)

        if message.message_id in self._recent_message_ids:
            self._log_rejection(message, RejectionReason.DUPLICATE_MESSAGE)
            return None

        self._recent_message_ids.append(message.message_id)
        return await self._forward(message, identity)

    def _log_rejection(self, message: IMessage, reason: str) -> None:
        logger.info(
            {
                "event": "imessage_gateway_rejected",
                "reason": reason,
                "sender": message.sender,
                "message_id": message.message_id,
                "text_length": len(message.text),
            }
        )

    def _identity_for_sender(self, sender: str) -> AuthorizedSender | None:
        if self._allowed_identities:
            return self._allowed_identities.get(sender)
        if sender in self._allowed_senders:
            return AuthorizedSender(platform="imessage", address=sender)
        return None

    async def _forward(self, message: IMessage, identity: AuthorizedSender) -> IMessageReply | None:
        try:
            principal = build_memory_principal(
                client_type="imessage",
                client_subject=identity.subject,
                conversation_id=identity.conversation_id,
            )
        except ValueError:
            return self._safe_error_response(message)

        payload = {
            "prompt": message.text,
            "provider": "auto",
            "tools_required": True,
            "conversation_id": principal.conversation_id,
        }

        try:
            client = await self._client()
            headers = identity.safe_headers()
            if self._director_token:
                headers["Authorization"] = f"Bearer {self._director_token}"
            response = await client.post(
                f"{self._director_url}/route",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            logger.warning(
                {
                    "event": "imessage_gateway_director_timeout",
                    "sender": message.sender,
                    "message_id": message.message_id,
                }
            )
            return self._safe_error_response(message)
        except httpx.HTTPStatusError as exc:
            logger.warning(
                {
                    "event": "imessage_gateway_director_error",
                    "sender": message.sender,
                    "message_id": message.message_id,
                    "status_code": exc.response.status_code,
                }
            )
            return self._safe_error_response(message)
        except Exception:
            logger.exception(
                {
                    "event": "imessage_gateway_unexpected_error",
                    "sender": message.sender,
                    "message_id": message.message_id,
                }
            )
            return self._safe_error_response(message)

        text = data.get("response", "")
        if not text:
            return self._safe_error_response(message)

        return IMessageReply(chat_id=message.chat_id, text=text)

    def _safe_error_response(self, message: IMessage) -> IMessageReply:
        return IMessageReply(chat_id=message.chat_id, text=_SAFE_ERROR_TEXT)

    async def close(self) -> None:
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()


gateway = IMessageGateway()
