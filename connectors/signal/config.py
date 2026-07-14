from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class SignalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    signal_enabled: bool = False
    signal_allowed_senders: str = ""
    signal_max_message_chars: int = 4000
    freyja_director_url: str = "http://127.0.0.1:8000"
    signal_request_timeout_seconds: float = 30.0

    @property
    def allowed_sender_set(self) -> set[str]:
        return {entry.strip() for entry in self.signal_allowed_senders.split(",") if entry.strip()}


settings = SignalSettings()
