from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from freyja.main import app
from freyja.router import router
from freyja.tools.models import ToolExecutionResult


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_health_remains_public_when_connector_auth_is_enabled(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    response = client.get("/health")
    assert response.status_code == 200


def test_endpoints_inventory_lists_vulcan_and_lmstudio(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "vulcan_enabled", True)
    monkeypatch.setattr(settings, "vulcan_coder_enabled", True)
    monkeypatch.setattr(settings, "lmstudio_enabled", True)
    monkeypatch.setattr(settings, "lmstudio_model", "manual-model")
    monkeypatch.setattr(settings, "vision_base_url", "http://100.87.242.99:8091/v1")
    monkeypatch.setattr(settings, "vision_model", "gemma-3-27b-it")
    with patch("freyja.local_openai_client.LocalOpenAIClient.healthy", new_callable=AsyncMock) as mock_healthy:
        mock_healthy.side_effect = [True, True, False, True]
        response = client.get("/endpoints")

    assert response.status_code == 200
    endpoints = {item["id"]: item for item in response.json()["endpoints"]}
    assert endpoints["vulcan-general"]["base_url"].endswith(":8088/v1")
    assert endpoints["vulcan-general"]["reachable"] is True
    assert endpoints["vulcan-coder"]["base_url"].endswith(":8090/v1")
    assert endpoints["vulcan-coder"]["reachable"] is True
    assert endpoints["lmstudio"]["base_url"].endswith(":1234/v1")
    assert endpoints["lmstudio"]["role"] == "wake-on-query experiments"
    assert endpoints["lmstudio"]["provider"] == "lmstudio-proxy"
    assert endpoints["lmstudio"]["wake_url"] == ""
    assert endpoints["lmstudio"]["model"] == "manual-model"
    assert endpoints["lmstudio"]["reachable"] is False
    assert endpoints["vision-docs"]["role"] == "vision/document inference"
    assert endpoints["vision-docs"]["base_url"].endswith(":8091/v1")
    assert endpoints["vision-docs"]["model"] == "gemma-3-27b-it"
    assert endpoints["vision-docs"]["reachable"] is True
    assert endpoints["audio"]["role"] == "speech and audio inference"


def test_endpoints_html_renders_table() -> None:
    with patch("freyja.local_openai_client.LocalOpenAIClient.healthy", new_callable=AsyncMock) as mock_healthy:
        mock_healthy.side_effect = [True, True]
        response = client.get("/endpoints.html")

    assert response.status_code == 200
    assert "Freyja Endpoints" in response.text
    assert "Vulcan Coder" in response.text
    assert "LM Studio" in response.text


def test_vision_health_reports_unconfigured(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "vision_base_url", "")
    response = client.get("/vision/health")

    assert response.status_code == 200
    assert response.json()["vision_configured"] is False
    assert response.json()["vision_reachable"] is False


def test_vision_extract_requires_configured_endpoint(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "vision_base_url", "")
    response = client.post(
        "/vision/extract",
        json={"prompt": "read it", "image_url": "data:image/png;base64,abc"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "No local vision endpoint configured"


def test_vision_extract_proxies_openai_compatible_vision(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "vision_base_url", "http://100.87.242.99:8091/v1")
    with patch("freyja.main.vision.vision_chat", new_callable=AsyncMock) as mock_vision_chat:
        mock_vision_chat.return_value = {
            "status": "ok",
            "model": "gemma-3-27b-it",
            "response": '{"total":"42.19"}',
            "latency_ms": 1200,
        }
        response = client.post(
            "/vision/extract",
            json={
                "prompt": "extract total",
                "image_url": "data:image/png;base64,abc",
                "output_tokens": 128,
            },
        )

    assert response.status_code == 200
    assert response.json()["response"] == '{"total":"42.19"}'
    mock_vision_chat.assert_awaited_once_with(
        prompt="extract total",
        image_url="data:image/png;base64,abc",
        model=None,
        output_tokens=128,
    )


def test_protected_endpoint_requires_connector_token(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    response = client.get("/ollama/models")
    assert response.status_code == 401
    assert response.json() == {"detail": "Connector authentication required."}
    assert response.headers["www-authenticate"] == "Bearer"


def test_protected_endpoint_rejects_wrong_connector_token(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    response = client.get(
        "/ollama/models",
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 401


def test_protected_endpoint_accepts_connector_token(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    with patch("freyja.ollama_client.OllamaClient.tags", new_callable=AsyncMock) as mock_tags:
        mock_tags.return_value = {"models": [{"name": "tinyllama:latest"}]}
        response = client.get(
            "/ollama/models",
            headers={"Authorization": "Bearer test-connector-token"},
        )
    assert response.status_code == 200
    assert response.json() == {"models": ["tinyllama:latest"]}


def test_ollama_health_reachable() -> None:
    from freyja.config import settings

    with patch("freyja.ollama_client.OllamaClient.healthy", new_callable=AsyncMock) as mock_healthy:
        mock_healthy.return_value = True
        response = client.get("/ollama/health")

    assert response.status_code == 200
    data = response.json()
    assert data["ollama_reachable"] is True
    assert data["base_url"] == settings.ollama_base_url


def test_local_reasoning_health_available(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "ollama_reasoning_model", "gpt-oss:20b")
    with patch("freyja.ollama_client.OllamaClient.healthy", new_callable=AsyncMock) as mock_healthy, patch(
        "freyja.ollama_client.OllamaClient.tags", new_callable=AsyncMock
    ) as mock_tags:
        mock_healthy.return_value = True
        mock_tags.return_value = {"models": [{"name": "gpt-oss:20b"}]}
        response = client.get("/local-reasoning/health")

    assert response.status_code == 200
    data = response.json()
    assert data["local_reasoning_reachable"] is True
    assert data["model"] == "gpt-oss:20b"
    assert data["model_available"] is True


def test_local_reasoning_health_unavailable(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "ollama_reasoning_model", "gpt-oss:20b")
    with patch("freyja.ollama_client.OllamaClient.healthy", new_callable=AsyncMock) as mock_healthy:
        mock_healthy.return_value = False
        response = client.get("/local-reasoning/health")

    assert response.status_code == 200
    data = response.json()
    assert data["local_reasoning_reachable"] is False
    assert data["ollama_reachable"] is False


def test_ollama_models_lists_models() -> None:
    with patch("freyja.ollama_client.OllamaClient.tags", new_callable=AsyncMock) as mock_tags:
        mock_tags.return_value = {"models": [{"name": "tinyllama:latest"}]}
        response = client.get("/ollama/models")

    assert response.status_code == 200
    assert response.json() == {"models": ["tinyllama:latest"]}


def test_ollama_models_returns_503_on_error() -> None:
    with patch("freyja.ollama_client.OllamaClient.tags", new_callable=AsyncMock) as mock_tags:
        mock_tags.return_value = {"error": "Connection refused"}
        response = client.get("/ollama/models")

    assert response.status_code == 503
    assert response.json()["detail"] == "Connection refused"


def test_chat_returns_response() -> None:
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "model": "tinyllama:latest",
            "message": {"role": "assistant", "content": "Hello, world!"},
        }
        response = client.post("/chat", json={"prompt": "Say hello"})

    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "tinyllama:latest"
    assert data["response"] == "Hello, world!"


def test_chat_returns_503_on_error() -> None:
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {"error": "No Ollama model configured"}
        response = client.post("/chat", json={"prompt": "Say hello"})

    assert response.status_code == 503
    assert response.json()["detail"] == "No Ollama model configured"


def test_openrouter_health_reachable() -> None:
    with patch("freyja.openrouter_client.OpenRouterClient.healthy", new_callable=AsyncMock) as mock_healthy:
        mock_healthy.return_value = True
        response = client.get("/openrouter/health")

    assert response.status_code == 200
    data = response.json()
    assert data["openrouter_reachable"] is True
    assert data["base_url"] == "https://openrouter.ai/api/v1"


def test_openrouter_chat_returns_response() -> None:
    with patch("freyja.openrouter_client.OpenRouterClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "model": "openai/gpt-4o-mini",
            "response": "Hello from the cloud!",
        }
        response = client.post("/openrouter/chat", json={"prompt": "Say hello"})

    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "openai/gpt-4o-mini"
    assert data["response"] == "Hello from the cloud!"


def test_openrouter_chat_returns_503_on_error() -> None:
    with patch("freyja.openrouter_client.OpenRouterClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {"error": "OpenRouter API key not configured"}
        response = client.post("/openrouter/chat", json={"prompt": "Say hello"})

    assert response.status_code == 503
    assert response.json()["detail"] == "OpenRouter API key not configured"


def test_route_local_uses_ollama() -> None:
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "model": "qwen2.5:1.5b",
            "message": {"role": "assistant", "content": "Local hello"},
        }
        response = client.post("/route", json={"prompt": "Say hello", "provider": "local"})

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "ollama"
    assert data["response"] == "Local hello"
    assert "tool_results" not in data


def test_route_cloud_uses_openrouter() -> None:
    with patch("freyja.openrouter_client.OpenRouterClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "model": "openai/gpt-4o-mini",
            "response": "Cloud hello",
        }
        response = client.post("/route", json={"prompt": "Say hello", "provider": "cloud"})

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "openrouter"
    assert data["response"] == "Cloud hello"


def test_route_auto_succeeds_locally_without_fallback() -> None:
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_ollama, patch(
        "freyja.openrouter_client.OpenRouterClient.chat", new_callable=AsyncMock
    ) as mock_openrouter:
        mock_ollama.return_value = {
            "model": "qwen2.5:1.5b",
            "message": {"role": "assistant", "content": "Local auto hello"},
        }
        response = client.post("/route", json={"prompt": "Say hello", "provider": "auto"})

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "ollama"
    assert data["response"] == "Local auto hello"
    mock_openrouter.assert_not_called()


def test_route_auto_falls_back_to_openrouter() -> None:
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_ollama, patch(
        "freyja.openrouter_client.OpenRouterClient.chat", new_callable=AsyncMock
    ) as mock_openrouter:
        mock_ollama.return_value = {"error": "Ollama unreachable"}
        mock_openrouter.return_value = {
            "model": "openai/gpt-4o-mini",
            "response": "Fallback hello",
        }
        response = client.post("/route", json={"prompt": "Say hello", "provider": "auto"})

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "openrouter"
    assert data["response"] == "Fallback hello"
    mock_openrouter.assert_called_once()


def test_route_auto_returns_503_when_both_fail() -> None:
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_ollama, patch(
        "freyja.openrouter_client.OpenRouterClient.chat", new_callable=AsyncMock
    ) as mock_openrouter:
        mock_ollama.return_value = {"error": "Ollama unreachable"}
        mock_openrouter.return_value = {"error": "OpenRouter API key not configured"}
        response = client.post("/route", json={"prompt": "Say hello", "provider": "auto"})

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail == "No approved provider is currently available."


def test_route_503_does_not_expose_credentials() -> None:
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_ollama, patch(
        "freyja.openrouter_client.OpenRouterClient.chat", new_callable=AsyncMock
    ) as mock_openrouter:
        mock_ollama.return_value = {"error": "Authorization: Bearer sk-secret-12345"}
        mock_openrouter.return_value = {"error": "Authorization: Bearer sk-cloud-67890"}
        response = client.post("/route", json={"prompt": "large prompt", "provider": "auto", "task_type": "coding"})

    assert response.status_code == 503
    body = response.json()
    detail = body["detail"]
    assert detail == "No approved provider is currently available."
    raw = str(body)
    assert "sk-" not in raw
    assert "Bearer" not in raw
    assert "Authorization" not in raw
    assert "secret" not in raw.lower()


def test_route_with_tools_required_false_omits_tool_results() -> None:
    model_response = {
        "model": "qwen2.5:1.5b",
        "message": {"role": "assistant", "content": "No tools needed."},
    }

    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = model_response
        response = client.post(
            "/route",
            json={"prompt": "weather in Oslo", "provider": "local", "tools_required": False},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "No tools needed."
    assert "tool_results" not in data


def test_route_with_tools_required_returns_sanitized_tool_results() -> None:
    first_response = {
        "model": "qwen2.5:1.5b",
        "message": {
            "role": "assistant",
            "content": 'I will check the weather.\n<freyja_tool_call>{"tool_name":"get_weather","arguments":{"location":"Oslo","request_type":"current"}}</freyja_tool_call>',
        },
    }
    second_response = {
        "model": "qwen2.5:1.5b",
        "message": {"role": "assistant", "content": "It is sunny in Oslo."},
    }
    tool_result = ToolExecutionResult(
        success=True,
        tool_name="get_weather",
        output={
            "hostname": "iris",
            "status": "ok",
            "status_code": 200,
            "iso_timestamp": "2024-01-01T00:00:00",
            "stdout": "raw internal stdout must not leak",
            "stderr": "raw internal stderr must not leak",
        },
        duration_ms=120,
        request_id="req-1",
    )

    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat, patch.object(
        router._registry, "execute", new_callable=AsyncMock
    ) as mock_execute:
        mock_chat.side_effect = [first_response, second_response]
        mock_execute.return_value = tool_result
        response = client.post(
            "/route",
            json={"prompt": "weather in Oslo", "provider": "local", "tools_required": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "ollama"
    assert data["response"] == "It is sunny in Oslo."
    assert "tool_results" in data
    tool_results = data["tool_results"]
    assert len(tool_results) == 1
    assert tool_results[0] == {
        "tool_name": "get_weather",
        "success": True,
        "hostname": "iris",
        "status": "ok",
        "status_code": 200,
        "iso_timestamp": "2024-01-01T00:00:00",
        "duration_ms": 120,
    }
    assert "output" not in tool_results[0]
    assert "stdout" not in tool_results[0]
    assert "stderr" not in tool_results[0]
    raw_response = str(response.json())
    assert "stdout" not in raw_response
    assert "stderr" not in raw_response


def test_route_with_tools_required_failed_tool_returns_error_category() -> None:
    first_response = {
        "model": "qwen2.5:1.5b",
        "message": {
            "role": "assistant",
            "content": '<freyja_tool_call>{"tool_name":"disk_usage","arguments":{"path":"/"}}</freyja_tool_call>',
        },
    }
    tool_result = ToolExecutionResult(
        success=False,
        tool_name="disk_usage",
        output={
            "stdout": "internal stdout",
            "stderr": "internal stderr",
        },
        error_code="tool_timeout",
        public_error_message="Tool timed out.",
        duration_ms=5000,
        request_id="req-2",
    )

    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat, patch.object(
        router._registry, "execute", new_callable=AsyncMock
    ) as mock_execute:
        mock_chat.return_value = first_response
        mock_execute.return_value = tool_result
        response = client.post(
            "/route",
            json={"prompt": "check disk usage", "provider": "local", "tools_required": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Tool 'disk_usage' failed (tool_timeout): Tool timed out."
    assert "tool_results" in data
    assert data["tool_results"][0] == {
        "tool_name": "disk_usage",
        "success": False,
        "error_category": "tool_timeout",
        "duration_ms": 5000,
    }
    assert "public_error_message" not in data["tool_results"][0]
    assert "stdout" not in data["response"].lower()
    assert "stderr" not in data["response"].lower()
    raw_response = str(response.json())
    assert "stdout" not in raw_response
    assert "stderr" not in raw_response


def test_route_with_tools_required_no_tool_call_omits_tool_results() -> None:
    model_response = {
        "model": "qwen2.5:1.5b",
        "message": {"role": "assistant", "content": "I don't need any tools for that."},
    }

    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = model_response
        response = client.post(
            "/route",
            json={"prompt": "say hello", "provider": "local", "tools_required": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "I don't need any tools for that."
    assert "tool_results" not in data


def test_route_with_tools_required_legitimate_json_passes_unchanged() -> None:
    model_response = {
        "model": "qwen2.5:1.5b",
        "message": {
            "role": "assistant",
            "content": 'Here is an example: {"tool_name": "example_tool", "enabled": true}.',
        },
    }

    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = model_response
        response = client.post(
            "/route",
            json={"prompt": "json example", "provider": "local", "tools_required": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert '{"tool_name": "example_tool", "enabled": true}' in data["response"]
    assert "<freyja_tool_call>" not in data["response"]


def test_route_with_tools_required_code_block_with_braces_passes_unchanged() -> None:
    code_block = "```c\nstruct Tool { char tool_name[32]; int enabled; };\n```"
    model_response = {
        "model": "qwen2.5:1.5b",
        "message": {"role": "assistant", "content": code_block},
    }

    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = model_response
        response = client.post(
            "/route",
            json={"prompt": "c struct", "provider": "local", "tools_required": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert "struct Tool" in data["response"]
    assert "char tool_name[32]" in data["response"]
    assert data["response"].count("```") == 2


def test_route_with_tools_required_sanitized_metadata_drops_unexpected_fields() -> None:
    first_response = {
        "model": "qwen2.5:1.5b",
        "message": {
            "role": "assistant",
            "content": '<freyja_tool_call>{"tool_name":"hostname","arguments":{}}</freyja_tool_call>',
        },
    }
    second_response = {
        "model": "qwen2.5:1.5b",
        "message": {"role": "assistant", "content": "Done."},
    }
    tool_result = ToolExecutionResult(
        success=True,
        tool_name="hostname",
        output={
            "hostname": "iris",
            "secret_key": "must-not-appear",
            "nested": {"password": "hunter2"},
            "stdout": "internal",
        },
        duration_ms=50,
        request_id="req-3",
    )

    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat, patch.object(
        router._registry, "execute", new_callable=AsyncMock
    ) as mock_execute:
        mock_chat.side_effect = [first_response, second_response]
        mock_execute.return_value = tool_result
        response = client.post(
            "/route",
            json={"prompt": "hostname", "provider": "local", "tools_required": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["tool_results"][0] == {
        "tool_name": "hostname",
        "success": True,
        "hostname": "iris",
        "duration_ms": 50,
    }
    assert "secret_key" not in data
    assert "password" not in str(data)
    assert "stdout" not in str(data)


def test_route_with_tools_required_strips_malformed_tool_markers() -> None:
    model_response = {
        "model": "qwen2.5:1.5b",
        "message": {
            "role": "assistant",
            "content": 'Oops <freyja_tool_call>{invalid json}</freyja_tool_call> here is the answer.',
        },
    }

    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = model_response
        response = client.post(
            "/route",
            json={"prompt": "question", "provider": "local", "tools_required": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert "<freyja_tool_call>" not in data["response"]
    assert "{invalid json}" not in data["response"]
    assert "tool_results" not in data


@pytest.mark.parametrize("bad_value", ["true", "false", 1, 0, None, [True], {"enabled": True}])
def test_route_rejects_non_boolean_tools_required(bad_value) -> None:
    response = client.post(
        "/route",
        json={"prompt": "hello", "provider": "local", "tools_required": bad_value},
    )

    assert response.status_code == 422
    assert "tools_required" in response.text or "bool" in response.text.lower()


def test_route_omitting_tools_required_preserves_prior_behavior() -> None:
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "model": "qwen2.5:1.5b",
            "message": {"role": "assistant", "content": "Prior behavior"},
        }
        response = client.post(
            "/route",
            json={"prompt": "hello", "provider": "local"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Prior behavior"
    assert "tool_results" not in data
    assert set(data.keys()) == {
        "provider",
        "model",
        "response",
        "reason",
        "privacy_classification",
        "estimated_cost_usd",
        "limitation_notice",
        "fallback_attempts",
        "request_id",
    }
