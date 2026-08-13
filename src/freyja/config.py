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
    ollama_model: str = "qwen2.5:7b"
    ollama_chat_model: str = "qwen2.5:7b"
    ollama_classification_model: str = "qwen2.5:1.5b"
    ollama_reasoning_model: str = "gpt-oss:20b"
    ollama_min_output_tokens: int = 160
    ollama_default_output_tokens: int = 512
    ollama_retry_output_tokens: int = 1024
    ollama_min_chat_parameters_b: int = 3
    ollama_keep_alive: str = "30m"
    ollama_warmup_enabled: bool = False
    ollama_warmup_models: str = Field(default="", alias="OLLAMA_WARMUP_MODELS")
    ollama_warmup_interval_seconds: float = 1200.0
    ollama_warmup_timeout_seconds: float = 90.0

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"

    cloud_enabled: bool = True
    openrouter_monthly_soft_limit: float = 20.0
    openrouter_monthly_hard_limit: float = 30.0
    openrouter_per_request_limit: float = 1.0
    local_max_prompt_chars: int = 8000
    openrouter_allowlist: str = Field(default="", alias="OPENROUTER_ALLOWLIST")

    inference_gateway_enabled: bool = False
    inference_gateway_monthly_hard_limit: float = 20.0
    inference_gateway_per_request_limit: float = 1.0
    inference_gateway_default_tier: str = "FAST"
    inference_gateway_local_model: str = "qwen2.5:7b"
    inference_gateway_free_model: str = ""
    inference_gateway_fast_model: str = "qwen/qwen3.5-flash-02-23"
    inference_gateway_reasoning_model: str = "moonshotai/kimi-k2.5"
    inference_gateway_deep_model: str = "z-ai/glm-5"
    inference_gateway_frontier_model: str = "openai/gpt-5.4"
    inference_gateway_ollama_cloud_model: str = ""
    inference_gateway_ollama_cloud_base_url: str = ""
    inference_gateway_ollama_cloud_api_key: str = ""
    inference_gateway_openrouter_allowlist: str = Field(default="", alias="INFERENCE_GATEWAY_OPENROUTER_ALLOWLIST")
    inference_gateway_fast_input_per_m: float = 0.065
    inference_gateway_fast_output_per_m: float = 0.26
    inference_gateway_reasoning_input_per_m: float = 0.375
    inference_gateway_reasoning_output_per_m: float = 2.025
    inference_gateway_deep_input_per_m: float = 0.60
    inference_gateway_deep_output_per_m: float = 1.92
    inference_gateway_frontier_input_per_m: float = 2.50
    inference_gateway_frontier_output_per_m: float = 15.0

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

    apple_calendar_bridge_url: str = ""
    apple_calendar_bridge_token: str = ""
    apple_calendar_bridge_timeout_seconds: float = 15.0
    apple_reminders_bridge_url: str = ""
    apple_reminders_bridge_token: str = ""
    apple_reminders_bridge_timeout_seconds: float = 15.0

    home_assistant_base_url: str = "http://127.0.0.1:8123"
    home_assistant_token: str = ""
    home_assistant_timeout_seconds: float = 10.0
    home_assistant_entity_allowlist: str = ""

    @property
    def approved_openrouter_models(self) -> list[str]:
        if not self.openrouter_allowlist:
            return []
        return [model.strip() for model in self.openrouter_allowlist.split(",") if model.strip()]

    @property
    def approved_inference_gateway_models(self) -> list[str]:
        if not self.inference_gateway_openrouter_allowlist:
            return []
        return [model.strip() for model in self.inference_gateway_openrouter_allowlist.split(",") if model.strip()]

    @property
    def ollama_warmup_model_names(self) -> list[str]:
        configured = [model.strip() for model in self.ollama_warmup_models.split(",") if model.strip()]
        candidates = configured or [
            self.ollama_chat_model,
            self.inference_gateway_local_model,
        ]
        models: list[str] = []
        for model in candidates:
            if model and model not in models:
                models.append(model)
        return models


settings = Settings()
