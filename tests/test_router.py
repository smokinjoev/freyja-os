import json
from typing import Any
from unittest.mock import AsyncMock, patch

from unittest.mock import AsyncMock

import pytest

from freyja.config import Settings, settings
from freyja.memory.models import MemoryPrincipal, PutSharedMemoryRequest
from freyja.memory.store import MemoryStore, set_store
from freyja.router import RouteRequest, Router
from freyja.tools.builtin import register_builtin_tools
from freyja.tools.models import ToolDefinition, ToolExecutionRequest
from freyja.tools.registry import ToolRegistry


@pytest.fixture
def router() -> Router:
    r = Router()
    r.ollama_client = AsyncMock()
    r.openrouter_client = AsyncMock()
    return r


@pytest.fixture
def isolated_memory_store(tmp_path, monkeypatch: pytest.MonkeyPatch):
    db_path = str(tmp_path / "router_memory.db")
    monkeypatch.setattr(settings, "memory_database_path", db_path)
    monkeypatch.setattr(settings, "memory_enabled", True)
    store = MemoryStore(database_path=db_path, max_messages_per_conversation=1000, retention_days=90)
    set_store(store)
    store.initialize()
    yield store
    set_store(None)


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
        "ollama_reasoning_model": "gpt-oss:20b",
        "openrouter_model": "openai/gpt-4o-mini",
    }
    for key, value in defaults.items():
        monkeypatch.setattr(settings, key, value)


def _settings_with_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cloud_enabled", True)
    monkeypatch.setattr(settings, "openrouter_allowlist", "openai/gpt-4o-mini")


async def test_manual_local_override(router: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "local"},
        "prompt_eval_count": 4,
        "eval_count": 2,
        "latency_ms": 12,
    }

    req = RouteRequest(prompt="hi", provider="local")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert result.decision.reason == "manual local override"
    assert result.response == "local"
    assert result.runtime_evidence.provider_selected == "ollama"
    assert result.runtime_evidence.model_selected == "qwen2.5:7b"
    assert result.runtime_evidence.routing_reason == "manual local override"
    assert result.runtime_evidence.token_counts["total_tokens"] == 6
    assert result.runtime_evidence.timing["ollama_latency_ms"] == 12
    assert result.latency_ms is not None
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


async def test_quick_acknowledgement_stays_fast_tier(router: Router, reset_settings) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "ok"},
    }

    req = RouteRequest(prompt="ok thanks", task_type="chat")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert result.decision.model == "qwen2.5:7b"
    assert result.response == "ok"


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


async def test_sensitive_request_fails_closed_when_ollama_unhealthy(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.healthy.return_value = False
    router.openrouter_client.healthy.return_value = True

    req = RouteRequest(prompt="My SSN is 123-45-6789")
    result = await router.execute(req)

    assert result.decision.provider == "error"
    assert result.response == ""
    assert any(a["provider"] == "ollama" and a["outcome"] == "unhealthy" for a in result.decision.fallback_attempts)
    assert "requires internal model" in result.decision.reason
    router.openrouter_client.chat.assert_not_called()
    assert any(a["provider"] == "ollama" and a["outcome"] == "unhealthy" for a in result.runtime_evidence.fallback_events)


async def test_private_manual_cloud_override_routes_internal(router: Router) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "internal"},
    }

    req = RouteRequest(prompt="Use my private family context", provider="cloud", privacy="private")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert result.decision.privacy_classification == "private"
    assert "manual cloud override rejected" in result.decision.reason
    assert "privacy requires internal model" in result.decision.reason
    router.openrouter_client.chat.assert_not_called()


async def test_sensitive_complex_request_routes_internal_heavy(router: Router, reset_settings) -> None:
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "internal heavy"},
    }

    req = RouteRequest(prompt="Debug this private stack trace", task_type="debug", privacy="sensitive")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.decision.privacy_classification == "sensitive"
    assert "privacy requires internal local_reasoning" in result.decision.reason
    router.openrouter_client.chat.assert_not_called()


async def test_local_reasoning_uses_dedicated_reasoning_client(router: Router, reset_settings) -> None:
    reasoning_client = AsyncMock()
    reasoning_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "heavy"},
    }
    router.register_reasoning_client(reasoning_client)

    req = RouteRequest(prompt="Debug this stack trace", task_type="debug")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.response == "heavy"
    reasoning_client.chat.assert_awaited_once()
    router.ollama_client.chat.assert_not_called()


async def test_runtime_evidence_records_connector_origin(router: Router) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "signal reply"},
    }
    principal = MemoryPrincipal(
        client_type="signal",
        client_subject="subject-hash",
        conversation_id="conversation-hash",
    )

    result = await router.execute(RouteRequest(prompt="hello", provider="local"), memory_principal=principal)

    assert result.runtime_evidence.connector_operations == [
        {
            "connector": "signal",
            "operation": "route",
            "success": True,
            "conversation_id": "conversation-hash",
        }
    ]


async def test_complex_coding_routes_local_reasoning(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.healthy.return_value = True
    router.openrouter_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "local reasoning"},
    }

    req = RouteRequest(prompt="Debug this stack trace and propose a patch", task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.decision.model == "gpt-oss:20b"
    assert "complex local task" in result.decision.reason
    assert result.response == "local reasoning"
    router.openrouter_client.chat.assert_not_called()


async def test_cloud_disabled_blocks_auto_cloud(router: Router, disable_cloud) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "local"},
    }

    big_prompt = "x" * 9000
    req = RouteRequest(prompt=big_prompt, task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.decision.model == settings.ollama_reasoning_model


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

    assert result.decision.provider == "local_reasoning"
    assert result.decision.model == settings.ollama_reasoning_model


async def test_local_failure_falls_back_to_cloud(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {"error": "Ollama down"}
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud fallback",
    }

    req = RouteRequest(prompt="Debug this bug and propose a patch", task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "openrouter"
    assert any(a["provider"] == "local_reasoning" for a in result.decision.fallback_attempts)
    assert "fallback" in result.decision.reason


async def test_retry_exhaustion_falls_back_to_cloud(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.chat.return_value = {"error": "Ollama returned empty content", "status": "empty_content"}
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud fallback",
    }

    req = RouteRequest(prompt="Write code to fix this bug", task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "openrouter"
    assert result.response == "cloud fallback"
    assert any(a["provider"] == "local_reasoning" for a in result.decision.fallback_attempts)


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
    req = RouteRequest(prompt=big_prompt, provider="cloud")
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


async def test_native_tool_call_validated_and_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "chat_max_tool_iterations", 2)
    registry = ToolRegistry(audit_enabled=False)
    seen_arguments: list[dict[str, Any]] = []

    async def weather(request: ToolExecutionRequest) -> dict:
        seen_arguments.append(request.arguments)
        return {"summary": f"{request.arguments['unit']} in {request.arguments['location']}"}

    registry.register(
        ToolDefinition(
            name="get_weather",
            description="Weather",
            input_schema={
                "type": "object",
                "required": ["location", "unit"],
                "properties": {
                    "location": {"type": "string"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
            },
        ),
        weather,
    )
    r = Router(registry=registry)
    r.ollama_client = AsyncMock()
    r.openrouter_client = AsyncMock()
    r.ollama_client.chat.side_effect = [
        {
            "model": "gpt-oss:20b",
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_weather",
                            "arguments": {"location": "Boston", "unit": "F"},
                        }
                    }
                ],
            },
        },
        {
            "model": "gpt-oss:20b",
            "message": {"content": "It is fahrenheit in Boston."},
        },
    ]

    req = RouteRequest(
        prompt="What is the weather in Boston in Fahrenheit?",
        provider="local_reasoning",
        tools_required=True,
    )
    result = await r.execute(req)

    assert result.response == "It is fahrenheit in Boston."
    assert seen_arguments == [{"location": "Boston", "unit": "fahrenheit"}]
    first_call = r.ollama_client.chat.await_args_list[0].kwargs
    assert first_call["tools"]


async def test_native_tool_call_invalid_arguments_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "chat_max_tool_iterations", 2)
    registry = ToolRegistry(audit_enabled=False)

    async def weather(request: ToolExecutionRequest) -> dict:
        return {}

    registry.register(
        ToolDefinition(
            name="get_weather",
            description="Weather",
            input_schema={
                "type": "object",
                "required": ["location", "unit"],
                "properties": {
                    "location": {"type": "string"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
            },
        ),
        weather,
    )
    r = Router(registry=registry)
    r.ollama_client = AsyncMock()
    r.openrouter_client = AsyncMock()
    r.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "get_weather",
                        "arguments": {"location": "Boston", "unit": "kelvin"},
                    }
                }
            ],
        },
    }

    req = RouteRequest(
        prompt="What is the weather in Boston?",
        provider="local_reasoning",
        tools_required=True,
    )
    result = await r.execute(req)

    assert "Invalid arguments" in result.response
    assert result.tool_results[0]["error_code"] == "validation_error"
    assert result.runtime_evidence.tool_calls[0].name == "get_weather"
    assert result.runtime_evidence.tool_calls[0].success is False
    assert result.runtime_evidence.tool_calls[0].error == "validation_error"


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


async def test_tools_required_auto_falls_back_to_cloud_when_local_errors(
    router: Router,
    reset_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_allowlist(monkeypatch)
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
    router.ollama_client.chat.return_value = {"error": "All connection attempts failed"}
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud answer",
    }

    req = RouteRequest(prompt="say hello", provider="auto", tools_required=True)
    result = await router.execute(req)

    assert result.decision.provider == "openrouter"
    assert "fallback after ollama tool failure" in result.decision.reason
    assert result.response == "cloud answer"
    assert result.decision.limitation_notice == "Local provider failed; returned cloud response."
    assert result.decision.fallback_attempts == [
        {"provider": "ollama", "outcome": "All connection attempts failed"},
        {"provider": "openrouter", "outcome": "attempting fallback"},
    ]


async def test_weather_without_location_returns_deterministic_prompt(
    router: Router,
) -> None:
    req = RouteRequest(
        prompt="What's the weather for Xmas this year?",
        provider="auto",
        tools_required=True,
    )
    result = await router.execute(req)

    assert result.decision.provider == "deterministic"
    assert result.decision.reason == "deterministic weather capability"
    assert "Forecasts are only available up to 7 days out" in result.response
    assert "Please include a city or location" in result.response
    router.ollama_client.chat.assert_not_awaited()
    router.openrouter_client.chat.assert_not_awaited()


async def test_weather_with_location_bypasses_model(
    router: Router,
) -> None:
    req = RouteRequest(
        prompt="What's the weather for Xmas this year in Aiken, SC?",
        provider="auto",
        tools_required=True,
    )
    result = await router.execute(req)

    assert result.decision.provider == "deterministic"
    assert "Forecasts are only available up to 7 days out" in result.response
    router.ollama_client.chat.assert_not_awaited()
    router.openrouter_client.chat.assert_not_awaited()


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


class TestToolLoop:
    @pytest.fixture
    def registry(self) -> ToolRegistry:
        r = ToolRegistry(audit_enabled=False)
        register_builtin_tools(r)
        return r

    @pytest.fixture
    def router(self, registry: ToolRegistry) -> Router:
        r = Router(registry=registry)
        r.ollama_client = AsyncMock()
        r.openrouter_client = AsyncMock()
        return r

    @pytest.fixture(autouse=True)
    def _enable_tool_loop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "chat_max_tool_iterations", 3)

    def _tool_call(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        args = arguments or {}
        return f'<freyja_tool_call>{{"tool_name":"{name}","arguments":{json.dumps(args)}}}</freyja_tool_call>'

    async def test_successful_single_tool_request_local(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True

        calls: list[int] = []

        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(1)
            if len(calls) == 1:
                return {"model": "qwen2.5:7b", "message": {"content": self._tool_call("hostname")}}
            return {"model": "qwen2.5:7b", "message": {"content": "The host is Iris."}}

        router.ollama_client.chat.side_effect = _respond
        req = RouteRequest(prompt="What host am I on?", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.decision.provider == "ollama"
        assert "Iris" in result.response or "iris" in result.response.lower()
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool_name"] == "hostname"
        assert result.tool_results[0]["success"] is True
        assert result.tool_results[0]["duration_ms"] is not None
        assert result.runtime_evidence.tool_calls[0].name == "hostname"
        assert result.runtime_evidence.tool_calls[0].success is True

    async def test_home_assistant_read_slice_is_director_authorized_deterministic(
        self,
        router: Router,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "home_assistant_state_fixture", '{"light.downstairs":"on"}')
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": "model should not run"},
        }
        principal = MemoryPrincipal(
            client_type="imessage",
            client_subject="family-member:abc",
            conversation_id="imessage-conv:test",
        )

        result = await router.execute(
            RouteRequest(
                request_id="req-home-read",
                prompt="Are the downstairs lights on?",
                provider="auto",
                tools_required=True,
                include_trace=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
        )

        assert result.decision.request_id == "req-home-read"
        assert result.decision.provider == "deterministic"
        assert result.response == "Yes, the downstairs lights are on."
        assert result.tool_results[0]["tool_name"] == "home_assistant_read_state"
        assert result.tool_results[0]["success"] is True
        assert result.runtime_evidence.interface == "imessage"
        assert result.runtime_evidence.person == {"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"}
        assert result.runtime_evidence.capability_authorizations == [
            {
                "capability": "home_assistant_read_state",
                "allowed": True,
                "reason": "principal joe may read household state",
                "required_permission": "household:home.read",
            }
        ]
        router.ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_home_assistant_read_slice_survives_inference_outages(
        self,
        router: Router,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "home_assistant_state_fixture", '{"light.downstairs":"on"}')
        router.ollama_client.healthy.return_value = False
        router.reasoning_ollama_client = AsyncMock()
        router.reasoning_ollama_client.healthy.return_value = False
        router.openrouter_client.healthy.return_value = False
        principal = MemoryPrincipal(client_type="signal", client_subject="family-member:abc")

        result = await router.execute(
            RouteRequest(prompt="Are the downstairs lights on?", provider="auto", tools_required=True),
            memory_principal=principal,
            person_context={"person_id": "joe"},
        )

        assert result.decision.provider == "deterministic"
        assert result.response == "Yes, the downstairs lights are on."
        router.ollama_client.chat.assert_not_called()
        router.reasoning_ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_home_assistant_sensor_inventory_is_director_authorized_deterministic(
        self,
        router: Router,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            settings,
            "home_assistant_state_fixture",
            '{"sensor.kitchen_temperature":"72","sensor.front_door_battery":"88","light.downstairs":"on"}',
        )
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": "model should not run"},
        }
        principal = MemoryPrincipal(
            client_type="imessage",
            client_subject="family-member:abc",
            conversation_id="imessage-conv:test",
        )

        result = await router.execute(
            RouteRequest(
                request_id="req-home-sensors",
                prompt="What sensors can you see in Home Assistant?",
                provider="auto",
                tools_required=True,
                include_trace=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
        )

        assert result.decision.request_id == "req-home-sensors"
        assert result.decision.provider == "deterministic"
        assert result.tool_results[0]["tool_name"] == "home_assistant_list_states"
        assert result.tool_results[0]["success"] is True
        assert result.tool_results[0]["output"]["count"] == 2
        assert "kitchen_temperature" in result.response
        assert result.runtime_evidence.capability_authorizations == [
            {
                "capability": "home_assistant_list_states",
                "allowed": True,
                "reason": "principal joe may read household state",
                "required_permission": "household:home.read",
            }
        ]
        router.ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_home_assistant_inventory_changes_route_reports_new_devices(
        self,
        router: Router,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        monkeypatch.setattr(settings, "home_assistant_inventory_snapshot_path", str(tmp_path / "ha-inventory.json"))
        monkeypatch.setattr(settings, "home_assistant_state_fixture", '{"light.downstairs":"on"}')
        principal = MemoryPrincipal(client_type="imessage", client_subject="family-member:abc")
        await router.execute(
            RouteRequest(
                prompt="Have any Home Assistant devices changed?",
                provider="auto",
                tools_required=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe"},
        )

        monkeypatch.setattr(
            settings,
            "home_assistant_state_fixture",
            '{"light.downstairs":"on","sensor.front_door_battery":"88"}',
        )
        result = await router.execute(
            RouteRequest(
                request_id="req-ha-changes",
                prompt="Have any new Home Assistant devices been added?",
                provider="auto",
                tools_required=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe"},
        )

        assert result.decision.provider == "deterministic"
        assert result.tool_results[0]["tool_name"] == "home_assistant_inventory_changes"
        assert result.tool_results[0]["output"]["added"][0]["entity_id"] == "sensor.front_door_battery"
        assert "sensor.front_door_battery" in result.response
        router.ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_home_assistant_read_slice_denies_unknown_principal(self, router: Router) -> None:
        principal = MemoryPrincipal(client_type="signal", client_subject="family-member:abc")

        result = await router.execute(
            RouteRequest(prompt="Are the downstairs lights on?", provider="auto", tools_required=True),
            memory_principal=principal,
            person_context={"person_id": "unknown"},
        )

        assert result.decision.provider == "deterministic"
        assert result.tool_results[0]["error_code"] == "authorization_denied"
        assert "can't read household state" in result.response

    async def test_home_assistant_control_slice_requires_explicit_approval(self, router: Router) -> None:
        principal = MemoryPrincipal(client_type="imessage", client_subject="family-member:abc")

        result = await router.execute(
            RouteRequest(
                request_id="req-home-control",
                prompt="Turn off the downstairs lights.",
                provider="auto",
                tools_required=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
        )

        assert result.decision.provider == "deterministic"
        assert result.decision.reason == "deterministic Home Assistant control capability"
        assert result.tool_results[0]["tool_name"] == "home_assistant_control_state"
        assert result.tool_results[0]["success"] is False
        assert result.tool_results[0]["error_code"] == "authorization_denied"
        assert result.runtime_evidence.capability_authorizations == [
            {
                "capability": "home_assistant_control_state",
                "allowed": False,
                "reason": "explicit approval required for household control",
                "required_permission": "household:home.control",
            }
        ]
        assert "explicit approval" in result.response
        router.ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_calendar_read_slice_is_director_authorized_deterministic(self, router: Router) -> None:
        principal = MemoryPrincipal(
            client_type="imessage",
            client_subject="family-member:abc",
            conversation_id="imessage-conv:test",
        )

        result = await router.execute(
            RouteRequest(
                request_id="req-calendar-read",
                prompt="What is on my calendar today?",
                provider="auto",
                tools_required=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
        )

        assert result.decision.request_id == "req-calendar-read"
        assert result.decision.provider == "deterministic"
        assert result.decision.reason == "deterministic calendar read capability"
        assert result.tool_results[0]["tool_name"] == "calendar_today_schedule"
        assert result.tool_results[0]["success"] is True
        assert result.runtime_evidence.capability_authorizations == [
            {
                "capability": "calendar_today_schedule",
                "allowed": True,
                "reason": "principal joe may read household calendar",
                "required_permission": "household:calendar.read",
            }
        ]
        router.ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_calendar_read_slice_survives_inference_outages(self, router: Router) -> None:
        router.ollama_client.healthy.return_value = False
        router.reasoning_ollama_client = AsyncMock()
        router.reasoning_ollama_client.healthy.return_value = False
        router.openrouter_client.healthy.return_value = False
        principal = MemoryPrincipal(client_type="signal", client_subject="family-member:abc")

        result = await router.execute(
            RouteRequest(prompt="What is on my calendar today?", provider="auto", tools_required=True),
            memory_principal=principal,
            person_context={"person_id": "joe"},
        )

        assert result.decision.provider == "deterministic"
        assert "calendar" in result.response.lower()
        router.ollama_client.chat.assert_not_called()
        router.reasoning_ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_calendar_read_slice_denies_unknown_principal(self, router: Router) -> None:
        principal = MemoryPrincipal(client_type="signal", client_subject="family-member:abc")

        result = await router.execute(
            RouteRequest(prompt="What is on my calendar today?", provider="auto", tools_required=True),
            memory_principal=principal,
            person_context={"person_id": "unknown"},
        )

        assert result.decision.provider == "deterministic"
        assert result.tool_results[0]["error_code"] == "authorization_denied"
        assert "can't read calendar state" in result.response

    async def test_memory_read_slice_is_director_authorized_deterministic(
        self,
        router: Router,
        isolated_memory_store,
    ) -> None:
        principal = MemoryPrincipal(
            client_type="imessage",
            client_subject="family-member:abc",
            conversation_id="imessage-conv:test",
        )
        isolated_memory_store.put_shared_memory(
            principal,
            PutSharedMemoryRequest(
                memory_id="calendar-pref",
                kind="preference",
                content="Joe prefers morning calendar events.",
                source="test",
                metadata={"domain": "calendar"},
            ),
        )

        result = await router.execute(
            RouteRequest(
                request_id="req-memory-read",
                prompt="What do you remember about my preferences?",
                provider="auto",
                tools_required=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
        )

        assert result.decision.request_id == "req-memory-read"
        assert result.decision.provider == "deterministic"
        assert result.tool_results[0]["tool_name"] == "memory_recall_shared"
        assert result.tool_results[0]["success"] is True
        assert "Joe prefers morning calendar events." in result.response
        assert result.runtime_evidence.capability_authorizations == [
            {
                "capability": "memory_recall_shared",
                "allowed": True,
                "reason": "Director-authorized principal may read scoped memory",
                "required_permission": "personal:memory.read",
            }
        ]
        assert result.runtime_evidence.memory_lookups[0]["operation"] == "shared_capability_recall"
        router.ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_memory_read_slice_denies_unknown_principal(self, router: Router) -> None:
        principal = MemoryPrincipal(client_type="signal", client_subject="family-member:abc")

        result = await router.execute(
            RouteRequest(prompt="What do you remember about my preferences?", provider="auto", tools_required=True),
            memory_principal=principal,
            person_context={"person_id": "unknown"},
        )

        assert result.decision.provider == "deterministic"
        assert result.tool_results[0]["error_code"] == "authorization_denied"
        assert "can't read memory" in result.response

    async def test_tool_request_receives_resolved_person_context(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        captured: dict[str, Any] = {}

        async def _capture_person(request: ToolExecutionRequest) -> dict[str, Any]:
            captured.update(request.metadata)
            return {"ok": True}

        registry.register(
            ToolDefinition(name="capture_person", description="Capture person metadata."),
            _capture_person,
        )

        calls: list[int] = []

        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(1)
            if len(calls) == 1:
                return {"model": "qwen2.5:7b", "message": {"content": self._tool_call("capture_person")}}
            return {"model": "qwen2.5:7b", "message": {"content": "done"}}

        router.ollama_client.chat.side_effect = _respond
        principal = MemoryPrincipal(client_type="signal", client_subject="family-member:abc")
        result = await router.execute(
            RouteRequest(prompt="Use a tool.", provider="local", tools_required=True),
            memory_principal=principal,
            person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
        )

        assert result.response == "done"
        assert captured["person"]["person_id"] == "joe"
        assert captured["memory_principal"]["client_subject"] == "family-member:abc"

    async def test_tool_failure_returns_honest_error(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True

        async def _flaky_tool(request: Any) -> dict[str, Any]:
            raise RuntimeError("disk is gone")

        registry.unregister("disk_usage")
        registry.register(
            ToolDefinition(
                name="disk_usage",
                description="Flaky disk usage for testing.",
                input_schema={"type": "object", "properties": {}},
                risk_level=registry.get_tool("disk_usage").risk_level if registry.get_tool("disk_usage") else "read_only",
            ),
            _flaky_tool,
        )

        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": self._tool_call("disk_usage")},
        }

        req = RouteRequest(prompt="Check disk usage.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.tool_results[0]["tool_name"] == "disk_usage"
        assert result.tool_results[0]["success"] is False
        assert result.tool_results[0]["error_code"] == "tool_error"
        assert "failed" in result.response.lower()

    async def test_invalid_arguments_rejected(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {
                "content": self._tool_call("disk_usage", {"path": 123})
            },
        }

        req = RouteRequest(prompt="Check disk usage.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool_name"] == "disk_usage"
        assert result.tool_results[0]["success"] is False
        assert result.tool_results[0]["error_code"] == "validation_error"
        assert "Invalid arguments" in result.response

    async def test_unknown_tool_rejected(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": self._tool_call("nonexistent_tool")},
        }

        req = RouteRequest(prompt="Do something weird.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.tool_results[0]["tool_name"] == "nonexistent_tool"
        assert result.tool_results[0]["success"] is False
        assert result.tool_results[0]["error_code"] == "tool_not_found"
        assert "Unknown tool" in result.response

    async def test_tool_evidence_redacts_sensitive_arguments(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": self._tool_call("unknown_secret_tool", {"token": "sk-test", "query": "safe"})},
        }

        req = RouteRequest(prompt="Use a missing tool.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.runtime_evidence.tool_calls[0].name == "unknown_secret_tool"
        assert result.runtime_evidence.tool_calls[0].arguments == {"token": "<redacted>", "query": "safe"}

    async def test_iteration_limit_exhaustion(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        monkeypatch.setattr(settings, "chat_max_tool_iterations", 2)
        router.ollama_client.healthy.return_value = True
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": self._tool_call("hostname")},
        }

        req = RouteRequest(prompt="Keep asking tools.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert len(result.tool_results) == 2
        assert all(entry["tool_name"] == "hostname" for entry in result.tool_results)
        assert "iteration limit" in result.response.lower()

    async def test_normal_response_no_tool(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": "Just a regular answer."},
        }

        req = RouteRequest(prompt="Say hi.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.response == "Just a regular answer."
        assert result.tool_results == []

    async def test_tool_loop_openrouter_path(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "openrouter_allowlist", "openai/gpt-4o-mini")
        monkeypatch.setattr(settings, "cloud_enabled", True)
        router.ollama_client.healthy.return_value = False
        router.openrouter_client.healthy.return_value = True

        calls: list[int] = []

        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(1)
            if len(calls) == 1:
                return {"model": "openai/gpt-4o-mini", "response": self._tool_call("current_time")}
            return {"model": "openai/gpt-4o-mini", "response": "The time is now."}

        router.openrouter_client.chat.side_effect = _respond
        req = RouteRequest(prompt="What time is it?", provider="cloud", tools_required=True)
        result = await router.execute(req)

        assert result.decision.provider == "openrouter"
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool_name"] == "current_time"
        assert result.tool_results[0]["success"] is True

    async def test_oversized_tool_output_is_truncated(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        monkeypatch.setattr(settings, "chat_max_tool_output_chars", 50)
        router.ollama_client.healthy.return_value = True

        async def _big_output(request: Any) -> dict[str, Any]:
            return {"data": "x" * 1000}

        registry.unregister("hostname")
        registry.register(
            ToolDefinition(
                name="hostname",
                description="Big output test.",
                input_schema={"type": "object", "properties": {}},
            ),
            _big_output,
        )

        calls: list[int] = []

        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(1)
            if len(calls) == 1:
                return {"model": "qwen2.5:7b", "message": {"content": self._tool_call("hostname")}}
            return {"model": "qwen2.5:7b", "message": {"content": "Got it."}}

        router.ollama_client.chat.side_effect = _respond
        req = RouteRequest(prompt="Show me big data.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.response == "Got it."
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["success"] is True
        second_call_prompt = router.ollama_client.chat.call_args_list[1][1]["prompt"]
        assert '"truncated": true' in second_call_prompt.lower()

    async def test_malformed_marker_is_stripped(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": "I think <freyja_tool_call>not valid json</freyja_tool_call> is the answer."},
        }

        req = RouteRequest(prompt="What is the answer?", provider="local", tools_required=True)
        result = await router.execute(req)

        assert "<freyja_tool_call>" not in result.response
        assert result.tool_results == []

    async def test_multiple_markers_use_first(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True

        calls: list[int] = []

        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(1)
            if len(calls) == 1:
                return {
                    "model": "qwen2.5:7b",
                    "message": {
                        "content": (
                            self._tool_call("hostname") + " " + self._tool_call("current_time")
                        )
                    },
                }
            return {"model": "qwen2.5:7b", "message": {"content": "Used hostname only."}}

        router.ollama_client.chat.side_effect = _respond
        req = RouteRequest(prompt="Ask two tools.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.response == "Used hostname only."
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool_name"] == "hostname"

    @pytest.mark.parametrize("iterations", [0, -1, 1000])
    async def test_iteration_config_boundaries(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry, iterations: int) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        monkeypatch.setattr(settings, "chat_max_tool_iterations", iterations)
        router.ollama_client.healthy.return_value = True
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": self._tool_call("hostname")},
        }

        req = RouteRequest(prompt="Loop.", provider="local", tools_required=True)
        result = await router.execute(req)

        if iterations <= 0:
            assert len(result.tool_results) == 1
            assert "iteration limit" in result.response.lower()
        else:
            # Hard upper cap of 50 prevents 1000 actual iterations.
            assert len(result.tool_results) <= 50
            assert "iteration limit" in result.response.lower()

    async def test_tool_failure_grounds_final_answer(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True

        async def _failing_tool(request: Any) -> dict[str, Any]:
            raise RuntimeError("sensor offline")

        registry.unregister("hostname")
        registry.register(
            ToolDefinition(
                name="hostname",
                description="Failing tool for grounding test.",
                input_schema={"type": "object", "properties": {}},
            ),
            _failing_tool,
        )

        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": self._tool_call("hostname")},
        }

        req = RouteRequest(prompt="What host?", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.tool_results[0]["success"] is False
        assert "failed" in result.response.lower()
        assert "succeeded" not in result.response.lower()
        assert "success" not in result.response.lower()
