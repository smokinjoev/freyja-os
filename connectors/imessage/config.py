from __future__ import annotations

from pathlib import Path
from shutil import which

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    freyja_director_url: str = "http://127.0.0.1:8000"
    freyja_connector_token: str = ""
    imessage_request_timeout_seconds: float = 30.0
    imessage_send_timeout_seconds: float = 30.0
    imessage_poll_interval_seconds: float = 5.0
    imessage_poll_chat_limit: int = 10
    imessage_poll_history_limit: int = 3

    @property
    def allowed_sender_set(self) -> set[str]:
        return {
            entry.strip()
            for entry in self.imessage_allowed_senders.split(",")
            if entry.strip()
        }

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
