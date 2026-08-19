from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from connectors.messaging import AuthorizedSender, parse_allowed_senders


class GmailSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gmail_enabled: bool = False
    gmail_identity: str = ""
    gmail_allowed_senders: str = ""
    gmail_max_message_chars: int = 12000
    gmail_request_timeout_seconds: float = 120.0
    freyja_director_url: str = "http://127.0.0.1:8000"
    freyja_connector_token: str = ""

    @property
    def allowed_sender_set(self) -> set[str]:
        return set(self.allowed_sender_identities)

    @property
    def allowed_sender_identities(self) -> dict[str, AuthorizedSender]:
        return parse_allowed_senders(self.gmail_allowed_senders, "gmail")


settings = GmailSettings()
