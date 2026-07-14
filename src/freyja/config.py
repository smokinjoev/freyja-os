from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    freyja_env: str = "development"
    freyja_host: str = "127.0.0.1"
    freyja_port: int = 8000

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = ""


settings = Settings()
