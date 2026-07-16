from unittest.mock import AsyncMock, patch

from unittest.mock import AsyncMock

import pytest

from freyja.config import Settings, settings
from freyja.router import RouteRequest, Router


@pytest.fixture
def router() -> Router:
    r = Router()
    r.ollama_client = AsyncMock()
    r.openrouter_client = AsyncMock()
    return r


@pytest.fixture
def disable_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cloud_enabled", False)


@pytest.fixture
def enable_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cloud_enabled", True)


@pytest.fixture
def reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    defaults = {
        "cloud_enabled": True,
        "openrouter_monthly_soft_limit": 20.0,
        "openrouter_monthly_hard_limit": 30.0,
        "openrouter_per_request_limit": 1.0,
        "local_max_prompt_chars": 8000,
        "openrouter_allowlist": "",
        "ollama_model": "qwen2.5:1.5b",
        "openrouter_model": "openai/gpt-4o-mini",
    }
    for key, value in defaults.items():
        monkeypatch.setattr(settings, key, value)


def _settings_with_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cloud_enabled", True)
    monkeypatch.setattr(settings, "openrouter_allowlist", "openai/gpt-4o-mini")


async def test_manual_local_override(router: Router) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "local"},
    }

    req = RouteRequest(prompt="hi", provider="local")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert result.decision.reason == "manual local override"
    assert result.response == "local"
    router.ollama_client.chat.assert_awaited_once()
    _, kwargs = router.ollama_client.chat.call_args
    assert kwargs["prompt"] == "hi"
    assert kwargs["model"] == "qwen2.5:7b"


async def test_manual_cloud_override_allowed(router: Router, monkeypatch: pytest.MonkeyPatch, reset_settings) -> None:
    _settings_with_allowlist(monkeypatch)
    router.openrouter_client.healthy.return_value = True
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud",
    }

    req = RouteRequest(prompt="hi", provider="cloud")
    result = await router.execute(req)

    assert result.decision.provider == "openrouter"
    assert "manual cloud override" in result.decision.reason
    assert result.response == "cloud"


async def test_manual_cloud_override_when_cloud_disabled(router: Router, disable_cloud) -> None:
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "local fallback"},
    }

    req = RouteRequest(prompt="hi", provider="cloud")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert "Cloud routing is currently disabled" in (result.decision.limitation_notice or "")
    router.openrouter_client.chat.assert_not_called()


async def test_manual_cloud_override_hard_budget_reached(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openrouter_allowlist", "openai/gpt-4o-mini")
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "local"},
    }

    req = RouteRequest(prompt="hi", provider="cloud")
    result = await router.execute(req, spent_this_month=30.0)

    assert result.decision.provider == "ollama"
    assert "hard budget reached" in result.decision.reason


async def test_routine_request_routes_local(router: Router) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "ok"},
    }

    req = RouteRequest(prompt="Summarize this article", task_type="summarize")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert "routine" in result.decision.reason.lower()
    router.openrouter_client.chat.assert_not_called()


async def test_sensitive_request_routes_local_when_ollama_healthy(router: Router) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "ok"},
    }

    req = RouteRequest(prompt="My SSN is 123-45-6789")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert result.decision.privacy_classification == "sensitive"
    assert "healthy local" in result.decision.reason


async def test_sensitive_request_falls_back_when_ollama_unhealthy(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.healthy.return_value = False
    router.openrouter_client.healthy.return_value = True
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud fallback",
    }

    req = RouteRequest(prompt="My SSN is 123-45-6789")
    result = await router.execute(req)

    assert result.decision.provider == "openrouter"
    assert any(a["provider"] == "ollama" and a["outcome"] == "unhealthy" for a in result.decision.fallback_attempts)


async def test_large_context_routes_cloud_when_healthy(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.healthy.return_value = True
    router.openrouter_client.healthy.return_value = True
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud large",
    }

    big_prompt = "x" * 9000
    req = RouteRequest(prompt=big_prompt, task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "openrouter"
    assert "cloud preferred" in result.decision.reason


async def test_cloud_disabled_blocks_auto_cloud(router: Router, disable_cloud) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "local"},
    }

    big_prompt = "x" * 9000
    req = RouteRequest(prompt=big_prompt, task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert "Cloud routing is currently disabled" in (result.decision.limitation_notice or "")


async def test_soft_budget_reached_routes_local(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cloud_enabled", True)
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "local"},
    }

    big_prompt = "x" * 9000
    req = RouteRequest(prompt=big_prompt, task_type="coding")
    result = await router.execute(req, spent_this_month=20.0)

    assert result.decision.provider == "ollama"
    assert "soft budget reached" in result.decision.reason


async def test_local_failure_falls_back_to_cloud(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {"error": "Ollama down"}
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud fallback",
    }

    req = RouteRequest(prompt="hi", task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "openrouter"
    assert any(a["provider"] == "ollama" for a in result.decision.fallback_attempts)
    assert "fallback" in result.decision.reason


async def test_cloud_failure_falls_back_to_local(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.healthy.return_value = True
    router.openrouter_client.healthy.return_value = True
    router.openrouter_client.chat.return_value = {"error": "OpenRouter down"}
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "local fallback"},
    }

    big_prompt = "x" * 9000
    req = RouteRequest(prompt=big_prompt, task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert any(a["provider"] == "openrouter" for a in result.decision.fallback_attempts)
    assert "Cloud provider failed" in (result.decision.limitation_notice or "")


async def test_audit_reason_and_request_id(router: Router, reset_settings) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "ok"},
    }

    req = RouteRequest(prompt="hi")
    result = await router.execute(req)

    assert result.decision.request_id
    assert result.decision.reason
    assert result.decision.privacy_classification in {"routine", "sensitive"}


async def test_logs_never_contain_api_keys(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.chat.return_value = {"error": "Authorization: Bearer secret-api-key"}
    router.openrouter_client.chat.return_value = {"error": "Authorization: Bearer secret-api-key"}

    req = RouteRequest(prompt="hi", task_type="coding")
    result = await router.execute(req)

    for attempt in result.decision.fallback_attempts:
        outcome = str(attempt.get("outcome", "")).lower()
        assert "api key" not in outcome
        assert "bearer" not in outcome
        assert "authorization" not in outcome


async def test_reason_describes_decision_not_provider_exception(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.chat.return_value = {"error": "Authorization: Bearer sk-12345"}
    router.openrouter_client.chat.return_value = {"error": "Authorization: Bearer sk-cloud-67890"}

    req = RouteRequest(prompt="hi", task_type="coding")
    result = await router.execute(req)

    assert not result.response
    assert result.decision.public_error_message == "No approved provider is currently available."
    reason = result.decision.reason.lower()
    assert "bearer" not in reason
    assert "authorization" not in reason
    assert "sk-" not in reason


def test_approved_allowlist_empty(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_ALLOWLIST", raising=False)
    s = Settings(_env_file=None)
    assert s.approved_openrouter_models == []


def test_approved_allowlist_parsing() -> None:
    s = Settings(OPENROUTER_ALLOWLIST="a/b, c/d ,", _env_file=None)
    assert s.approved_openrouter_models == ["a/b", "c/d"]


def test_approved_allowlist_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_ALLOWLIST", "openai/gpt-4o-mini,anthropic/claude-3.5-haiku")
    s = Settings()
    assert s.approved_openrouter_models == ["openai/gpt-4o-mini", "anthropic/claude-3.5-haiku"]


async def test_sub_3b_model_blocked_for_chat(router: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_chat_model", "qwen2.5:7b")
    monkeypatch.setattr(settings, "ollama_classification_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "seven-bee"},
    }

    req = RouteRequest(prompt="hi")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert "qwen2.5:7b" in result.decision.model
    router.ollama_client.chat.assert_awaited_once()
    _, kwargs = router.ollama_client.chat.call_args
    assert "qwen2.5:1.5b" not in kwargs.get("model", "")


async def test_1_5b_model_allowed_for_classification_only(router: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_chat_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_classification_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "classified"},
    }

    req = RouteRequest(prompt="hi", provider="local", model="qwen2.5:1.5b")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert result.decision.model == "qwen2.5:1.5b"


async def test_openrouter_fallback_avoids_sub_3b_chat(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_chat_model", "qwen2.5:7b")
    monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
    monkeypatch.setattr(settings, "openrouter_allowlist", "openai/gpt-4o-mini")
    router.ollama_client.chat.return_value = {"error": "Ollama down"}
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud hello",
    }

    req = RouteRequest(prompt="hello", task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "openrouter"
    assert "openai/gpt-4o-mini" in result.decision.model
    assert result.response == "cloud hello"
