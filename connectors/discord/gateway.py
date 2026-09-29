from __future__ import annotations

import base64
import asyncio
from io import BytesIO
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx
from PIL import Image, ImageOps, UnidentifiedImageError

from connectors.discord.config import DiscordSettings
from connectors.messaging import (
    AuthorizedSender,
    NormalizedAttachment,
    NormalizedMessage,
    canonical_director_payload,
    director_headers,
    director_response_text,
    post_canonical_to_director,
)
from freyja.agents.household import household_agents


logger = logging.getLogger(__name__)

DISCORD_AGENT_DISPLAY_NAMES = {
    "freyja": "Freyja",
    "cloyd-gibbler": "Cloyd Gibbler",
    "benedict": "Benedict",
    "agent-47": "Agent 44",
    "smith": "Agent Smith",
}

SUPPORTED_ATTACHMENT_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/heic",
        "image/heif",
    }
)
MAX_ROUTED_IMAGE_SIDE = 1280
MAX_ROUTED_IMAGE_BYTES = 1_500_000
RECENT_ATTACHMENT_CONTEXT_SECONDS = 20 * 60
DIRECTOR_ROUTE_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class DiscordInboundMessage:
    message_id: str
    author_id: str
    channel_id: str
    channel_type: str
    content: str
    author_is_bot: bool = False
    attachments: tuple[dict[str, Any], ...] = ()
    embeds: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class DiscordOutboundReply:
    text: str
    message_reference_id: str
    agent_id: str
    trace_id: str


@dataclass(frozen=True)
class DiscordUnsupportedMessageReply:
    text: str
    message_reference_id: str


@dataclass(frozen=True)
class RecentAttachmentContext:
    attachments: list[NormalizedAttachment]
    created_at: datetime


class DiscordAttachmentError(Exception):
    pass


class DiscordGateway:
    """DM-only Discord ingress that routes one approved user to one agent."""

    def __init__(
        self,
        settings: DiscordSettings,
        *,
        client: httpx.AsyncClient | None = None,
        director_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._client = client
        self._director_client = director_client
        self._bindings = {binding.discord_user_id: binding.agent_id for binding in settings.user_agent_bindings}
        self._recent_attachments_by_conversation: dict[str, RecentAttachmentContext] = {}

    def validate_startup(self) -> list[str]:
        failures: list[str] = []
        if not self.settings.enabled:
            failures.append("Discord transport is disabled.")
        if not self.settings.bot_token:
            failures.append("DISCORD_BOT_TOKEN is missing.")
        if not self.settings.connector_token:
            failures.append("FREYJA_CONNECTOR_TOKEN is missing.")
        if not self._bindings:
            failures.append("DISCORD_USER_AGENT_MAP is empty.")
        if not self.settings.dm_only:
            failures.append("Discord transport must be DM-only.")
        if not self.settings.text_only and not self.settings.media_intake_enabled:
            failures.append("Discord transport must be text-only unless media intake is enabled.")
        if not self.settings.final_only:
            failures.append("Discord transport must emit final responses only.")
        return failures

    def would_route(self, message: DiscordInboundMessage) -> bool:
        if message.author_is_bot:
            return False
        if message.channel_type != "dm":
            return False
        if message.embeds:
            return False
        if message.attachments and not self._attachments_supported(message):
            return False
        if not message.content.strip() and not message.attachments:
            return False
        return message.author_id in self._bindings

    def unsupported_message_reply(self, message: DiscordInboundMessage) -> DiscordUnsupportedMessageReply | None:
        if message.author_is_bot:
            return None
        if message.channel_type != "dm":
            return None
        if message.author_id not in self._bindings:
            return None
        if message.attachments and not self._attachments_supported(message):
            return DiscordUnsupportedMessageReply(
                text=(
                    "I saw the attachment, but this Discord connector can only intake PDFs, DOCX files, and common image files right now. "
                    "Send a PDF, DOCX, image, or paste the text you want me to work from."
                ),
                message_reference_id=message.message_id,
            )
        if message.embeds:
            return DiscordUnsupportedMessageReply(
                text=(
                    "I saw the embedded content, but Discord embed intake is not enabled for this connector yet. "
                    "Send the text directly if you want me to answer from it."
                ),
                message_reference_id=message.message_id,
            )
        return None

    async def handle_message(self, message: DiscordInboundMessage) -> DiscordOutboundReply | None:
        if not self.would_route(message):
            return None
        text = message.content.strip()
        agent_id = self._bindings.get(message.author_id)
        if agent_id is None:
            return None

        agent = _agent_by_id(agent_id)
        trace_id = f"discord-{uuid4().hex}"
        identity = AuthorizedSender(platform="discord", address=message.author_id, member_id=agent.person_id)
        conversation_id = identity.conversation_id_for_thread(message.channel_id)
        try:
            attachments = await self._download_attachments(message)
        except DiscordAttachmentError:
            return DiscordOutboundReply(
                text=(
                    "I saw the attachment, but Discord timed out while I was downloading it. "
                    "Please resend the file and ask the question again."
                ),
                message_reference_id=message.message_id,
                agent_id=agent.agent_id,
                trace_id=trace_id,
            )
        now = datetime.now(UTC)
        if attachments:
            self._recent_attachments_by_conversation[conversation_id] = RecentAttachmentContext(
                attachments=attachments,
                created_at=now,
            )
        else:
            attachments = self._recent_attachments_for_followup(conversation_id, text, now=now)
        normalized = NormalizedMessage(
            transport="discord",
            sender=message.author_id,
            conversation_id=conversation_id,
            message_id=message.message_id,
            text=text,
            timestamp=now,
            authorized=True,
            attachments=attachments,
        )
        prompt_text = normalized.prompt_text(
            empty_caption=(
                "The sender sent Discord file or image content in this same DM. "
                "No readable caption text was included."
            ),
            metadata_label="Trusted Discord metadata: attachment(s)",
        )
        request = normalized.to_canonical_request(
            authorized_sender=identity,
            resolved_user_id=agent.person_id,
            resolved_agent_id=agent.agent_id,
            permissions=sorted(agent.tool_grants),
            channel_metadata={
                "discord_channel_type": "dm",
                "discord_text_only": not bool(attachments),
                "discord_media_intake": bool(attachments),
                "discord_final_only": True,
            },
        )
        headers = director_headers(
            identity=identity,
            client_type="discord",
            client_subject=f"agent:{agent.agent_id}",
            conversation_id=normalized.conversation_id,
            trace_id=trace_id,
            connector_token=self.settings.connector_token,
            account_owner=agent.owner,
            agent_id=agent.agent_id,
            agent_display_name=DISCORD_AGENT_DISPLAY_NAMES.get(agent.agent_id, agent.display_name),
            person_id=agent.person_id,
        )
        client = self._director_client or self._client or httpx.AsyncClient(timeout=DIRECTOR_ROUTE_TIMEOUT_SECONDS)
        close_client = self._director_client is None and self._client is None
        try:
            logger.info("Discord director route start message_id=%s attachments=%s", message.message_id, len(attachments))
            data = await asyncio.wait_for(
                post_canonical_to_director(
                    client=client,
                    director_url=self.settings.director_url,
                    payload=canonical_director_payload(request, text=prompt_text),
                    headers=headers,
                ),
                timeout=DIRECTOR_ROUTE_TIMEOUT_SECONDS,
            )
            logger.info("Discord director route completed message_id=%s", message.message_id)
        except (asyncio.TimeoutError, httpx.HTTPError):
            logger.exception("Discord director route failed message_id=%s attachments=%s", message.message_id, len(attachments))
            return DiscordOutboundReply(
                text=(
                    "I received the attachment, but the vision route timed out before I could finish reading it. "
                    "Please resend it or send a smaller crop."
                ),
                message_reference_id=message.message_id,
                agent_id=agent.agent_id,
                trace_id=trace_id,
            )
        finally:
            if close_client:
                await client.aclose()
        reply = director_response_text(data).strip()
        if not reply:
            return None
        reply = _discord_safe_reply(reply, has_attachments=bool(attachments))
        return DiscordOutboundReply(
            text=reply,
            message_reference_id=message.message_id,
            agent_id=agent.agent_id,
            trace_id=trace_id,
        )

    def _attachments_supported(self, message: DiscordInboundMessage) -> bool:
        if not self.settings.media_intake_enabled:
            return False
        if not message.attachments:
            return True
        for attachment in message.attachments:
            filename = str(attachment.get("filename") or "")
            mime_type = str(attachment.get("content_type") or _mime_from_name(filename) or "").lower()
            if mime_type not in SUPPORTED_ATTACHMENT_MIME_TYPES:
                return False
            size = attachment.get("size")
            if isinstance(size, int) and size > self.settings.media_max_bytes:
                return False
            if not str(attachment.get("url") or ""):
                return False
        return True

    async def _download_attachments(self, message: DiscordInboundMessage) -> list[NormalizedAttachment]:
        if not message.attachments:
            return []
        client = self._client or httpx.AsyncClient(timeout=30)
        close_client = self._client is None
        normalized: list[NormalizedAttachment] = []
        try:
            for attachment in message.attachments:
                filename = str(attachment.get("filename") or "attachment")
                mime_type = str(attachment.get("content_type") or _mime_from_name(filename) or "application/octet-stream")
                size = attachment.get("size")
                if isinstance(size, int) and size > self.settings.media_max_bytes:
                    raise DiscordAttachmentError(f"attachment too large: {filename}")
                logger.info("Discord attachment download start message_id=%s filename=%s size=%s", message.message_id, filename, size)
                response = await _get_attachment_with_retries(client, str(attachment.get("url") or ""))
                content = response.content
                if len(content) > self.settings.media_max_bytes:
                    raise DiscordAttachmentError(f"attachment too large after download: {filename}")
                if mime_type.startswith("image/"):
                    content, filename, mime_type = _prepare_image_for_vision(
                        content=content,
                        filename=filename,
                        mime_type=mime_type,
                    )
                logger.info("Discord attachment download completed message_id=%s filename=%s bytes=%s", message.message_id, filename, len(content))
                normalized.append(
                    NormalizedAttachment(
                        filename=filename,
                        mime_type=mime_type,
                        data_base64=base64.b64encode(content).decode("ascii"),
                        size_bytes=len(content),
                    )
                )
        finally:
            if close_client:
                await client.aclose()
        return normalized

    def _recent_attachments_for_followup(
        self,
        conversation_id: str,
        text: str,
        *,
        now: datetime,
    ) -> list[NormalizedAttachment]:
        context = self._recent_attachments_by_conversation.get(conversation_id)
        if context is None:
            return []
        age_seconds = (now - context.created_at).total_seconds()
        if age_seconds > RECENT_ATTACHMENT_CONTEXT_SECONDS:
            self._recent_attachments_by_conversation.pop(conversation_id, None)
            return []
        if _starts_new_topic(text):
            return []
        if _refers_to_recent_attachment(text):
            return context.attachments
        if any(attachment.is_document or attachment.is_image for attachment in context.attachments):
            return context.attachments
        return []


def _agent_by_id(agent_id: str):
    for agent in household_agents.all():
        if agent.agent_id == agent_id:
            return agent
    raise ValueError(f"Discord binding references unknown agent: {agent_id}")


def _discord_safe_reply(text: str, *, has_attachments: bool) -> str:
    if not _looks_like_internal_status_reply(text):
        return text
    if has_attachments:
        return (
            "I received the attachment, but I couldn't produce a useful reading from it yet. "
            "Ask me a specific question about the file and I'll try again."
        )
    return "I received it, but I couldn't produce a useful answer yet. Try rephrasing with a bit more detail."


def _looks_like_internal_status_reply(text: str) -> bool:
    lower = text.lower()
    return (
        "received the objective and selected" in lower
        and ("using vulcan-" in lower or " using qwen" in lower)
    ) or "selected no tools" in lower


def _refers_to_recent_attachment(text: str) -> bool:
    normalized = f" {text.lower()} "
    if any(
        phrase in normalized
        for phrase in (
            " what do you see",
            " what can you see",
            " what are you seeing",
            " what do you notice",
            " look at it",
            " take a look",
        )
    ):
        return True
    reference_terms = (
        " attachment",
        " file",
        " pdf",
        " photo",
        " image",
        " picture",
        " screenshot",
        " document",
    )
    if not any(term in normalized for term in reference_terms):
        return False
    return any(
        marker in normalized
        for marker in (
            " the ",
            " this ",
            " that ",
            " it ",
            " above",
            " previous",
            " last ",
            " what is",
            " what's",
            " whats",
            " tell me",
            " describe",
            " see",
            " seeing",
            " look",
            " looking",
            " read ",
            " summarize",
        )
    )


def _starts_new_topic(text: str) -> bool:
    normalized = f" {text.lower()} "
    new_topic_terms = (
        " home assistant",
        " lights",
        " thermostat",
        " weather",
        " calendar",
        " remind me",
        " text ",
        " message ",
        " call ",
        " docker",
        " git ",
        " commit",
        " service",
        " restart",
    )
    return any(term in normalized for term in new_topic_terms)


def _prepare_image_for_vision(*, content: bytes, filename: str, mime_type: str) -> tuple[bytes, str, str]:
    if len(content) <= MAX_ROUTED_IMAGE_BYTES:
        return content, filename, mime_type
    try:
        with Image.open(BytesIO(content)) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            if max(image.size) > MAX_ROUTED_IMAGE_SIDE:
                image.thumbnail((MAX_ROUTED_IMAGE_SIDE, MAX_ROUTED_IMAGE_SIDE))
            output = BytesIO()
            image.save(output, format="JPEG", quality=82, optimize=True)
    except (OSError, UnidentifiedImageError):
        logger.warning("Discord image could not be normalized filename=%s bytes=%s", filename, len(content))
        return content, filename, mime_type
    prepared = output.getvalue()
    if len(prepared) >= len(content):
        return content, filename, mime_type
    stem = filename.rsplit(".", 1)[0] or "image"
    logger.info("Discord image normalized filename=%s original_bytes=%s routed_bytes=%s", filename, len(content), len(prepared))
    return prepared, f"{stem}.jpg", "image/jpeg"


async def _get_attachment_with_retries(client: httpx.AsyncClient, url: str) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = await asyncio.wait_for(client.get(url, timeout=20), timeout=25)
            response.raise_for_status()
            return response
        except (asyncio.TimeoutError, httpx.HTTPError) as exc:
            last_error = exc
            if attempt < 2:
                await asyncio.sleep(0.25 * (attempt + 1))
    raise DiscordAttachmentError(f"attachment download failed: {url}") from last_error


def _mime_from_name(filename: str) -> str | None:
    lowered = filename.lower()
    if lowered.endswith(".pdf"):
        return "application/pdf"
    if lowered.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if lowered.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".gif"):
        return "image/gif"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith(".heic"):
        return "image/heic"
    if lowered.endswith(".heif"):
        return "image/heif"
    return None
