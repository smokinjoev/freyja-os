from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class IMessageSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    imessage_enabled: bool = False
    imessage_imsg_path: str = "/opt/homebrew/bin/imsg"
    imessage_database_path: str = str(
        Path.home() / "Library" / "Messages" / "chat.db"
    )
    imessage_allowed_senders: str = ""
    imessage_max_message_chars: int = 4000

    @property
    def allowed_sender_set(self) -> set[str]:
        return {
            entry.strip()
            for entry in self.imessage_allowed_senders.split(",")
            if entry.strip()
        }


settings = IMessageSettings()
