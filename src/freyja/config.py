from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    freyja_env: str = "development"
    freyja_host: str = "127.0.0.1"
    freyja_port: int = 8000

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:1.5b"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"

    cloud_enabled: bool = True
    openrouter_monthly_soft_limit: float = 20.0
    openrouter_monthly_hard_limit: float = 30.0
    openrouter_per_request_limit: float = 1.0
    local_max_prompt_chars: int = 8000
    openrouter_allowlist: str = Field(default="", alias="OPENROUTER_ALLOWLIST")

    memory_enabled: bool = True
    memory_database_path: str = "/Users/freyja/freyja-os/data/freyja.db"
    memory_max_messages_per_conversation: int = 1000
    memory_retention_days: int = 90

    tools_enabled: bool = True
    tools_default_timeout_seconds: int = 30
    tools_audit_log_enabled: bool = True

    @property
    def approved_openrouter_models(self) -> list[str]:
        if not self.openrouter_allowlist:
            return []
        return [model.strip() for model in self.openrouter_allowlist.split(",") if model.strip()]


settings = Settings()
