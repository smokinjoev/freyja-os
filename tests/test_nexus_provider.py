import os

from freyja.agent_runtime_v3 import _openai_compatible_api_key, _openai_compatible_base_url
from freyja.config import Settings


def test_settings_expose_nexus_gateway_without_secret_default() -> None:
    config = Settings(nexus_base_url="http://100.94.80.21:3939")

    assert config.nexus_base_url == "http://100.94.80.21:3939"
    assert config.nexus_api_key == ""


def test_nexus_provider_uses_nexus_token_not_litellm_key(monkeypatch) -> None:
    monkeypatch.setattr("freyja.agent_runtime_v3.settings.nexus_base_url", "http://nexus.test:3939")
    monkeypatch.setattr("freyja.agent_runtime_v3.settings.nexus_api_key", "settings-token")
    monkeypatch.setattr("freyja.agent_runtime_v3.settings.litellm_master_key", "litellm-token")
    monkeypatch.delenv("NEXUS_API_KEY", raising=False)
    monkeypatch.setenv("LITELLM_MASTER_KEY", "litellm-env-token")

    assert _openai_compatible_base_url("nexus") == "http://nexus.test:3939"
    assert _openai_compatible_api_key("nexus") == "settings-token"

    monkeypatch.setenv("NEXUS_API_KEY", "nexus-env-token")

    assert _openai_compatible_api_key("nexus") == "nexus-env-token"
    assert _openai_compatible_api_key("nexus") != os.environ["LITELLM_MASTER_KEY"]
