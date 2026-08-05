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
    telegram_agent_name: str = "freyja"
    telegram_person_name: str = "joe"
    telegram_person_user_id: int | None = None
    telegram_agent_display_name: str = "Freyja"
    telegram_model: str = ""
    telegram_benedict_enabled: bool = False
    telegram_benedict_bot_token: str = ""
    telegram_benedict_allowed_user_ids: str = ""
    telegram_benedict_person_user_id: int | None = None
    telegram_benedict_tools_enabled: bool = False
    telegram_benedict_state_dir: str = ""
    telegram_benedict_model: str = "benedict-qwen2.5:7b"

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


def configured_telegram_settings() -> list[TelegramSettings]:
    """Return enabled bot identities without ever combining their credentials."""
    primary = TelegramSettings()
    configured = [primary]
    if primary.telegram_benedict_enabled:
        configured.append(
            TelegramSettings(
                telegram_enabled=True,
                telegram_bot_token=primary.telegram_benedict_bot_token,
                telegram_allowed_user_ids=primary.telegram_benedict_allowed_user_ids,
                telegram_direct_messages_only=True,
                telegram_smith_read_only_enabled=False,
                telegram_tools_enabled=primary.telegram_benedict_tools_enabled,
                telegram_max_message_chars=primary.telegram_max_message_chars,
                telegram_request_timeout_seconds=primary.telegram_request_timeout_seconds,
                telegram_poll_interval_seconds=primary.telegram_poll_interval_seconds,
                telegram_state_dir=(
                    primary.telegram_benedict_state_dir
                    or f"{primary.telegram_state_dir}-benedict"
                ),
                freyja_director_url=primary.freyja_director_url,
                telegram_agent_name="benedict",
                telegram_person_name="beth",
                telegram_person_user_id=primary.telegram_benedict_person_user_id,
                telegram_agent_display_name="Benedict",
                telegram_model=primary.telegram_benedict_model,
            )
        )
    return configured


settings = TelegramSettings()
