import json
from typing import Any
from unittest.mock import AsyncMock, patch

from unittest.mock import AsyncMock

import pytest

from freyja.config import Settings, settings
from freyja.router import RouteRequest, Router
from freyja.tools.builtin import register_builtin_tools
from freyja.tools.models import ToolDefinition
from freyja.tools.registry import ToolRegistry


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
