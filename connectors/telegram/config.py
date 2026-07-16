"""Configuration for the Telegram gateway."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from freyja.config import settings as freyja_settings


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_allowed_user_ids: str = ""
    telegram_direct_messages_only: bool = True
    telegram_smith_read_only_enabled: bool = False
    telegram_tools_enabled: bool = False
    telegram_max_message_chars: int = 4000
    telegram_request_timeout_seconds: float = 30.0
    telegram_poll_interval_seconds: float = 5.0
    telegram_state_dir: str = str(freyja_settings.telegram_state_dir)
    freyja_director_url: str = "http://127.0.0.1:8000"

    @property
    def allowed_user_id_set(self) -> set[int]:
        ids: set[int] = set()
        for entry in self.telegram_allowed_user_ids.split(","):
            entry = entry.strip()
            if not entry:
                continue
            try:
                ids.add(int(entry))
            except ValueError:
                continue
        return ids

    @property
    def token_configured(self) -> bool:
        return bool(self.telegram_bot_token.strip())


settings = TelegramSettings()
