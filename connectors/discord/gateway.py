from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import httpx

from connectors.discord.config import DiscordSettings
from connectors.messaging import (
    AuthorizedSender,
    NormalizedMessage,
    canonical_director_payload,
    director_headers,
    director_response_text,
    post_canonical_to_director,
)
from freyja.agents.household import household_agents


DISCORD_AGENT_DISPLAY_NAMES = {
    "freyja": "Freyja",
    "cloyd-gibbler": "Cloyd Gibbler",
    "benedict": "Benedict",
    "agent-47": "Agent 44",
    "smith": "Agent Smith",
}


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


class DiscordGateway:
    """DM-only Discord ingress that routes one approved user to one agent."""

    def __init__(self, settings: DiscordSettings, *, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client
        self._bindings = {binding.discord_user_id: binding.agent_id for binding in settings.user_agent_bindings}

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
        if not self.settings.text_only:
            failures.append("Discord transport must be text-only.")
        if not self.settings.final_only:
            failures.append("Discord transport must emit final responses only.")
        return failures

    async def handle_message(self, message: DiscordInboundMessage) -> DiscordOutboundReply | None:
        if message.author_is_bot:
            return None
        if message.channel_type != "dm":
            return None
        if message.attachments or message.embeds:
            return None
        text = message.content.strip()
        if not text:
            return None
        agent_id = self._bindings.get(message.author_id)
        if agent_id is None:
            return None

        agent = _agent_by_id(agent_id)
        trace_id = f"discord-{uuid4().hex}"
        identity = AuthorizedSender(platform="discord", address=message.author_id, member_id=agent.person_id)
        normalized = NormalizedMessage(
            transport="discord",
            sender=message.author_id,
            conversation_id=identity.conversation_id_for_thread(message.channel_id),
            message_id=message.message_id,
            text=text,
            timestamp=datetime.now(UTC),
            authorized=True,
        )
        request = normalized.to_canonical_request(
            authorized_sender=identity,
            resolved_user_id=agent.person_id,
            resolved_agent_id=agent.agent_id,
            permissions=sorted(agent.tool_grants),
            channel_metadata={
                "discord_channel_type": "dm",
                "discord_text_only": True,
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
        client = self._client or httpx.AsyncClient(timeout=30)
        close_client = self._client is None
        try:
            data = await post_canonical_to_director(
                client=client,
                director_url=self.settings.director_url,
                payload=canonical_director_payload(request),
                headers=headers,
            )
        finally:
            if close_client:
                await client.aclose()
        reply = director_response_text(data).strip()
        if not reply:
            return None
        return DiscordOutboundReply(
            text=reply[:2000],
            message_reference_id=message.message_id,
            agent_id=agent.agent_id,
            trace_id=trace_id,
        )


def _agent_by_id(agent_id: str):
    for agent in household_agents.all():
        if agent.agent_id == agent_id:
            return agent
    raise ValueError(f"Discord binding references unknown agent: {agent_id}")
