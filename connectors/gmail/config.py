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
    gmail_poll_interval_seconds: float = 10.0
    gmail_reconnect_max_seconds: float = 60.0
    gmail_imap_host: str = "imap.gmail.com"
    gmail_imap_port: int = 993
    gmail_imap_mailbox: str = "INBOX"
    gmail_imap_username: str = ""
    gmail_imap_password: str = ""
    gmail_smtp_host: str = "smtp.gmail.com"
    gmail_smtp_port: int = 587
    gmail_smtp_username: str = ""
    gmail_smtp_password: str = ""
    gmail_smtp_from_name: str = "Freyja"
    gmail_smtp_starttls: bool = True
    freyja_director_url: str = "http://127.0.0.1:8000"
    freyja_connector_token: str = ""

    @property
    def allowed_sender_set(self) -> set[str]:
        return set(self.allowed_sender_identities)

    @property
    def allowed_sender_identities(self) -> dict[str, AuthorizedSender]:
        return parse_allowed_senders(self.gmail_allowed_senders, "gmail")

    @property
    def transport_configured(self) -> bool:
        return bool(
            self.gmail_imap_username.strip()
            and self.gmail_imap_password
            and self.gmail_smtp_username.strip()
            and self.gmail_smtp_password
        )


settings = GmailSettings()
