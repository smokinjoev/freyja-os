from __future__ import annotations

from pathlib import Path
from shutil import which

from pydantic_settings import BaseSettings, SettingsConfigDict

from connectors.messaging import AuthorizedSender, parse_allowed_senders


class IMessageSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    imessage_enabled: bool = False
    imessage_imsg_path: str = ""
    imessage_database_path: str = str(
        Path.home() / "Library" / "Messages" / "chat.db"
    )
    imessage_allowed_senders: str = ""
    imessage_max_message_chars: int = 4000
    imessage_model: str = ""
    imessage_tools_required_mode: str = "always"
    freyja_director_url: str = "http://127.0.0.1:8000"
    freyja_connector_token: str = ""
    imessage_request_timeout_seconds: float = 120.0
    imessage_command_timeout_seconds: float = 10.0
    imessage_send_timeout_seconds: float = 30.0
    imessage_provisional_reply_enabled: bool = False
    imessage_provisional_reply_delay_seconds: float = 2.0
    imessage_provisional_reply_text: str = "Working on it..."
    imessage_watch_enabled: bool = True
    imessage_poll_database_enabled: bool = True
    imessage_poll_interval_seconds: float = 5.0
    imessage_poll_chat_limit: int = 10
    imessage_poll_history_limit: int = 3
    imessage_family_observer_enabled: bool = False
    imessage_family_chat_identifiers: str = ""
    imessage_family_invocation_names: str = "freyja,@freyja"
    imessage_family_memory_enabled: bool = True
    imessage_seen_state_path: str = str(
        Path.home() / "Library" / "Application Support" / "Freyja" / "imessage-seen.json"
    )
    imessage_seen_state_limit: int = 5000

    @property
    def allowed_sender_set(self) -> set[str]:
        return set(self.allowed_sender_identities)

    @property
    def allowed_sender_identities(self) -> dict[str, AuthorizedSender]:
        return parse_allowed_senders(self.imessage_allowed_senders, "imessage")

    @property
    def family_chat_identifier_set(self) -> set[str]:
        return {value.strip() for value in self.imessage_family_chat_identifiers.split(",") if value.strip()}

    @property
    def family_invocation_names(self) -> tuple[str, ...]:
        return tuple(
            value.strip().lower()
            for value in self.imessage_family_invocation_names.split(",")
            if value.strip()
        )

    @property
    def resolved_imsg_path(self) -> str:
        if self.imessage_imsg_path.strip():
            return self.imessage_imsg_path.strip()

        discovered = which("imsg")
        if discovered:
            return discovered

        for candidate in ("/opt/homebrew/bin/imsg", "/usr/local/bin/imsg"):
            if Path(candidate).exists():
                return candidate

        return "imsg"


settings = IMessageSettings()
