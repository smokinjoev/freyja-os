from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from connectors.messaging import AuthorizedSender, parse_allowed_senders


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
    freyja_connector_token: str = ""
    signal_request_timeout_seconds: float = 30.0
    signal_rest_api_url: str = "http://127.0.0.1:8080"
    signal_account_number: str = ""
    signal_poll_interval_seconds: float = 5.0
    signal_transport_timeout_seconds: float = 60.0
    signal_reconnect_max_seconds: float = 60.0

    @property
    def allowed_sender_set(self) -> set[str]:
        return set(self.allowed_sender_identities)

    @property
    def allowed_sender_identities(self) -> dict[str, AuthorizedSender]:
        return parse_allowed_senders(self.signal_allowed_senders, "signal")

    @property
    def transport_configured(self) -> bool:
        return bool(self.signal_account_number.strip())


settings = SignalSettings()
