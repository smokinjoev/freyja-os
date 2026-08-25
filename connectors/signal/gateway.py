from __future__ import annotations

import logging
import hashlib
from collections import deque
from dataclasses import dataclass

import httpx

from connectors.signal.config import settings
from connectors.signal.models import InboundMessage, OutboundResponse
from connectors.messaging import AuthorizedSender, household_agent_for_sender
from freyja.agents.coder_access import is_coding_request
from freyja.agents.household import HouseholdAgent
from freyja.media import AttachmentInput, images_from_attachments
from freyja.memory.principal import build_memory_principal

logger = logging.getLogger(__name__)

_MAX_RECENT_IDS = 1000
_SAFE_ERROR_TEXT = "Freyja could not process your message. Please try again later."


@dataclass(frozen=True)
class _DirectorRouteMode:
    prompt: str
    provider: str = "auto"
    task_type: str | None = None
    tools_required: bool = False


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
        self._allowed_identities = settings.allowed_sender_identities
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

    async def handle(self, message: InboundMessage) -> OutboundResponse | None:
        if not self._enabled:
            logger.info({
                "event": "signal_gateway_rejected",
                "reason": RejectionReason.DISABLED,
                "sender_hash": self._safe_sender_hash(message.sender),
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

        identity = self._identity_for_sender(message.sender)
        if identity is None:
            logger.info({
                "event": "signal_gateway_rejected",
                "reason": RejectionReason.UNKNOWN_SENDER,
                "sender_hash": self._safe_sender_hash(message.sender),
                "message_id": message.message_id,
            })
            return OutboundResponse(
                recipient=message.sender,
                text="You are not authorized to use this gateway.",
                reply_to_message_id=message.message_id,
                success=False,
            )

        if not message.has_text and not message.attachments:
            return self._reject(message, RejectionReason.EMPTY_MESSAGE)

        prompt_text = self._message_text(message)
        if len(prompt_text) > self._max_message_chars:
            return self._reject(message, RejectionReason.OVERSIZED_MESSAGE)

        if message.message_id in self._recent_message_ids:
            return self._reject(message, RejectionReason.DUPLICATE_MESSAGE)

        self._recent_message_ids.append(message.message_id)

        return await self._forward(message, identity)

    def _reject(self, message: InboundMessage, reason: str) -> OutboundResponse:
        logger.info({
            "event": "signal_gateway_rejected",
            "reason": reason,
            "sender_hash": self._safe_sender_hash(message.sender),
            "message_id": message.message_id,
            "text_length": len(message.text),
        })
        return OutboundResponse(
            recipient=message.sender,
            text=_SAFE_ERROR_TEXT,
            reply_to_message_id=message.message_id,
            success=False,
        )

    def _identity_for_sender(self, sender: str) -> AuthorizedSender | None:
        if self._allowed_identities:
            return self._allowed_identities.get(sender)
        if sender in self._allowed_senders:
            return AuthorizedSender(platform="signal", address=sender)
        return None

    async def _forward(self, message: InboundMessage, identity: AuthorizedSender) -> OutboundResponse | None:
        agent_context = self._agent_context(identity)
        try:
            principal = build_memory_principal(
                client_type="signal",
                client_subject=f"agent:{agent_context.agent_id}",
                account_owner=agent_context.owner,
                conversation_id=identity.conversation_id,
            )
        except ValueError:
            return self._safe_error_response(message)

        route_mode = self._route_mode(message, agent_context)
        images = [
            image.model_dump(mode="json", exclude_none=True)
            for image in self._images_for_message(message)
        ]
        payload = {
            "prompt": route_mode.prompt,
            "provider": route_mode.provider,
            "task_type": route_mode.task_type,
            "tools_required": route_mode.tools_required,
            "privacy": "private",
            "conversation_id": principal.conversation_id,
        }
        if images:
            payload["images"] = images

        logger.info(
            {
                "event": "signal_gateway_director_request",
                "sender_hash": self._safe_sender_hash(message.sender),
                "message_id": message.message_id,
                "client_subject": principal.client_subject,
                "conversation_id": principal.conversation_id,
                "account_owner": principal.account_owner,
                "family_member": identity.member_id,
                "person_id": agent_context.person_id,
                "agent_id": agent_context.agent_id,
                "text_length": len(message.text),
            }
        )

        try:
            client = await self._client()
            headers = identity.safe_headers()
            headers["X-Freyja-Client-Type"] = principal.client_type
            headers["X-Freyja-Client-Subject"] = principal.client_subject
            headers["X-Freyja-Conversation-Id"] = principal.conversation_id or ""
            headers["X-Freyja-Account-Owner"] = principal.account_owner or ""
            headers["X-Freyja-Agent-Id"] = agent_context.agent_id
            headers["X-Freyja-Agent-Display-Name"] = agent_context.display_name
            headers["X-Freyja-Person-Id"] = agent_context.person_id
            if self._director_token:
                headers["Authorization"] = f"Bearer {self._director_token}"
            response = await client.post(
                f"{self._director_url}/route",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            text = data.get("response", "")
            if not text:
                logger.warning({
                    "event": "signal_gateway_empty_director_response",
                    "sender_hash": self._safe_sender_hash(message.sender),
                    "message_id": message.message_id,
                })
                return None

            logger.info(
                {
                    "event": "signal_gateway_director_response",
                    "sender_hash": self._safe_sender_hash(message.sender),
                    "message_id": message.message_id,
                    "director_request_id": data.get("request_id"),
                    "provider": data.get("provider"),
                    "model": data.get("model"),
                    "agent_id": agent_context.agent_id,
                    "person_id": agent_context.person_id,
                    "reply_length": len(text),
                }
            )
            return OutboundResponse(
                recipient=message.sender,
                text=text,
                reply_to_message_id=message.message_id,
                success=True,
            )

        except httpx.TimeoutException:
            logger.warning({
                "event": "signal_gateway_director_timeout",
                "sender_hash": self._safe_sender_hash(message.sender),
                "message_id": message.message_id,
            })
            return None

        except httpx.HTTPStatusError as exc:
            logger.warning({
                "event": "signal_gateway_director_error",
                "sender_hash": self._safe_sender_hash(message.sender),
                "message_id": message.message_id,
                "status_code": exc.response.status_code,
            })
            return None

        except Exception:
            logger.exception({
                "event": "signal_gateway_unexpected_error",
                "sender_hash": self._safe_sender_hash(message.sender),
                "message_id": message.message_id,
            })
            return None

    def _safe_error_response(self, message: InboundMessage) -> OutboundResponse:
        return OutboundResponse(
            recipient=message.sender,
            text=_SAFE_ERROR_TEXT,
            reply_to_message_id=message.message_id,
            success=False,
        )

    @staticmethod
    def _safe_sender_hash(sender: str) -> str:
        return hashlib.sha256(sender.encode("utf-8")).hexdigest()[:16]

    def _agent_context(self, identity: AuthorizedSender) -> HouseholdAgent:
        return household_agent_for_sender(identity)

    def _route_mode(self, message: InboundMessage, agent_context: HouseholdAgent) -> _DirectorRouteMode:
        prompt = self._message_text(message)
        if agent_context.agent_id == "cloyd-gibbler" and is_coding_request(message.text):
            return _DirectorRouteMode(
                prompt=(
                    "SIGNAL CODING REQUEST CONTEXT (trusted gateway metadata):\n"
                    "The authenticated sender is addressing the local coding agent. "
                    "Director owns final routing and agent identity.\n\n"
                    + prompt
                ),
                provider="local_reasoning",
                task_type="coding",
                tools_required=True,
            )
        return _DirectorRouteMode(prompt=prompt)

    @staticmethod
    def _images_for_message(message: InboundMessage):
        attachments = [
            AttachmentInput(
                filename=attachment.filename,
                mime_type=attachment.mime_type,
                path=attachment.path,
                data_base64=attachment.data_base64,
                size_bytes=attachment.size_bytes,
            )
            for attachment in message.attachments
        ]
        return images_from_attachments(attachments)

    @staticmethod
    def _message_text(message: InboundMessage) -> str:
        if not message.attachments:
            return message.text
        lines = []
        for index, attachment in enumerate(message.attachments, start=1):
            label = attachment.mime_type or "attachment"
            name = attachment.filename or "unnamed"
            lines.append(f"{index}. {label}: {name}")
        if message.has_text:
            return f"{message.text}\n\nTrusted Signal metadata: attachment(s):\n" + "\n".join(lines)
        return (
            "The sender sent photo or attachment content in this same Signal conversation. "
            "No readable caption text was included.\n\nTrusted Signal metadata: attachment(s):\n"
            + "\n".join(lines)
        )

    async def close(self) -> None:
        if self._http_client is not None and not self._http_client.is_closed:
            await self._http_client.aclose()


gateway = SignalGateway()
