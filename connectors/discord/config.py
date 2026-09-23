from __future__ import annotations

import os
from dataclasses import dataclass


APPROVED_AGENT_IDS = frozenset({"freyja", "cloyd-gibbler", "benedict", "agent-47", "smith"})


@dataclass(frozen=True)
class DiscordUserBinding:
    discord_user_id: str
    agent_id: str


@dataclass(frozen=True)
class DiscordSettings:
    enabled: bool
    bot_token: str
    director_url: str
    connector_token: str
    user_agent_bindings: tuple[DiscordUserBinding, ...]
    dm_only: bool = True
    text_only: bool = True
    final_only: bool = True

    @classmethod
    def from_env(cls) -> "DiscordSettings":
        return cls(
            enabled=_truthy(os.environ.get("DISCORD_ENABLED", "")),
            bot_token=os.environ.get("DISCORD_BOT_TOKEN", "").strip(),
            director_url=os.environ.get("FREYJA_DIRECTOR_URL", "http://127.0.0.1:8000").strip(),
            connector_token=os.environ.get("FREYJA_CONNECTOR_TOKEN", "").strip(),
            user_agent_bindings=parse_user_agent_bindings(os.environ.get("DISCORD_USER_AGENT_MAP", "")),
        )

    @property
    def ready_for_live_transport(self) -> bool:
        return (
            self.enabled
            and bool(self.bot_token)
            and bool(self.connector_token)
            and bool(self.user_agent_bindings)
            and self.dm_only
            and self.text_only
            and self.final_only
        )


def parse_user_agent_bindings(raw: str) -> tuple[DiscordUserBinding, ...]:
    bindings: list[DiscordUserBinding] = []
    seen_users: set[str] = set()
    for entry in raw.split(","):
        value = entry.strip()
        if not value:
            continue
        if "=" not in value:
            raise ValueError("Discord user bindings must use discord_user_id=agent_id entries.")
        user_id, agent_id = (part.strip() for part in value.split("=", 1))
        if not user_id.isdecimal():
            raise ValueError("Discord user ids must be numeric snowflakes.")
        if user_id in seen_users:
            raise ValueError("Each approved Discord user must be mapped exactly once.")
        if agent_id not in APPROVED_AGENT_IDS:
            raise ValueError(f"Discord agent binding uses an unapproved agent id: {agent_id}.")
        seen_users.add(user_id)
        bindings.append(DiscordUserBinding(discord_user_id=user_id, agent_id=agent_id))
    return tuple(bindings)


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
