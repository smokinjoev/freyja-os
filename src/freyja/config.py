import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_state_dir() -> Path:
    """Return a user-scoped external state directory outside the repository."""
    home = Path.home()
    xdg_state = os.environ.get("XDG_STATE_HOME")
    if xdg_state:
        base = Path(xdg_state)
    else:
        base = home / ".local" / "state"
    return base / "freyja"


def _repo_root() -> Path:
    """Return the repository root for repo-scoped default files."""
    return Path(__file__).resolve().parents[2]


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
    freyja_connector_token: str = ""

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_reasoning_base_url: str = ""
    ollama_model: str = "qwen2.5:7b"
    ollama_chat_model: str = "qwen2.5:7b"
    ollama_classification_model: str = "qwen2.5:1.5b"
    ollama_reasoning_model: str = "gpt-oss:20b"
    ollama_min_output_tokens: int = 160
    ollama_default_output_tokens: int = 512
    ollama_retry_output_tokens: int = 1024
    ollama_min_chat_parameters_b: int = 3

    # Rev 2: Iris is the always-hot routing/reflex node. These settings are
    # intentionally separate from the legacy Ollama provider so Iris can be
    # introduced in shadow mode without changing production routing behavior.
    iris_router_enabled: bool = False
    iris_router_shadow_enabled: bool = False
    iris_ollama_base_url: str = "http://iris:11434"
    iris_router_model: str = "qwen2.5:7b"
    iris_router_timeout_seconds: float = 4.0
    iris_router_keep_alive: str = "-1"
    iris_router_max_prompt_chars: int = 12000

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
    memory_database_path: str = str(_repo_root() / "data" / "freyja.db")
    memory_max_messages_per_conversation: int = 1000
    memory_retention_days: int = 90
    memory_shared_enabled: bool = True
    memory_shared_max_items_per_principal: int = 200
    memory_shared_max_global_items: int = 10000
    memory_shared_max_item_chars: int = 2000
    memory_recall_max_items: int = 12
    memory_recall_max_item_chars: int = 500
    memory_recall_max_total_chars: int = 3000
    memory_recall_include_in_cloud: bool = False

    identity_provider: str = "seeded"
    identity_database_path: str = str(_default_state_dir() / "identity.sqlite3")
    identity_seed_fallback: bool = True

    tools_enabled: bool = True
    tools_default_timeout_seconds: int = 30
    tools_audit_log_enabled: bool = True

    agent_smith_enabled: bool = False
    agent_smith_dry_run_enabled: bool = False
    agent_smith_read_only_enabled: bool = False
    agent_smith_write_pilot_enabled: bool = False
    agent_smith_policy_path: str = "config/agent-smith-policy.yaml"
    agent_smith_max_retries: int = 3
    agent_smith_dry_run_max_retries: int = 2
    agent_smith_max_steps: int = 20
    agent_smith_audit_enabled: bool = True
    agent_smith_audit_log_path: str = str(_repo_root() / "logs" / "agent-smith-audit.jsonl")
    agent_smith_approval_ttl_seconds: int = 900
    agent_smith_approval_db_path: str = str(_default_state_dir() / "smith-approvals.sqlite3")
    agent_smith_approval_loopback_only: bool = True

    chat_max_tool_iterations: int = 3
    chat_max_tool_output_chars: int = 4000

    telegram_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_allowed_user_ids: str = ""
    telegram_direct_messages_only: bool = True
    telegram_smith_read_only_enabled: bool = False
    telegram_max_message_chars: int = 4000
    telegram_request_timeout_seconds: float = 30.0
    telegram_poll_interval_seconds: float = 5.0
    telegram_state_dir: str = str(_default_state_dir() / "telegram")

    weather_tool_enabled: bool = False

    @property
    def approved_openrouter_models(self) -> list[str]:
        if not self.openrouter_allowlist:
            return []
        return [model.strip() for model in self.openrouter_allowlist.split(",") if model.strip()]


settings = Settings()
