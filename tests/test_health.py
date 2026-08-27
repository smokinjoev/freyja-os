from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from freyja.main import app
from freyja.router import RoutingDecision, RoutingResult, router
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


def test_protected_endpoint_accepts_connector_x_api_key(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    with patch("freyja.ollama_client.OllamaClient.tags", new_callable=AsyncMock) as mock_tags:
        mock_tags.return_value = {"models": [{"name": "tinyllama:latest"}]}
        response = client.get(
            "/ollama/models",
            headers={"x-api-key": "test-connector-token"},
        )
    assert response.status_code == 200
    assert response.json() == {"models": ["tinyllama:latest"]}


def test_shortcut_message_requires_connector_token(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    response = client.post("/shortcuts/message", json={"prompt": "What is next?"})

    assert response.status_code == 401


def test_shortcut_message_routes_private_voice_request(monkeypatch) -> None:
    from freyja.config import settings
    from freyja import main as director_main

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    monkeypatch.setattr(settings, "freyja3_canonical_enabled", False)
    decision = RoutingDecision(
        request_id="shortcut-req",
        provider="ollama",
        model="qwen2.5:7b",
        reason="auto default",
        privacy_classification="private",
    )
    with patch.object(director_main.router, "execute", new_callable=AsyncMock) as mock_execute:
        mock_execute.return_value = RoutingResult(
            decision=decision,
            response="  Dinner is at 6.\nI will keep it brief.  ",
        )
        response = client.post(
            "/shortcuts/message",
            headers={"Authorization": "Bearer test-connector-token"},
            json={"prompt": "What is next?", "conversation_id": "kitchen", "request_id": "shortcut-req"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Dinner is at 6. I will keep it brief."
    assert data["spoken"] == data["response"]
    assert data["conversation_id"] == "shortcut-conv:kitchen"
    route_request = mock_execute.await_args.args[0]
    assert route_request.prompt == "What is next?"
    assert route_request.request_id == "shortcut-req"
    assert route_request.provider == "auto"
    assert route_request.privacy == "private"
    assert route_request.task_type == "voice"
    assert route_request.tools_required is True
    assert route_request.conversation_id == "shortcut-conv:kitchen"


def test_openai_models_exposes_agent_smith(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    response = client.get(
        "/v1/models",
        headers={"Authorization": "Bearer test-connector-token"},
    )

    assert response.status_code == 200
    assert response.json()["data"][0]["id"] == "agent-smith"


def test_openai_chat_completion_runs_agent_smith_read_only(monkeypatch) -> None:
    from freyja import main as director_main
    from freyja.agents.models import SmithRunSummary
    from freyja.config import settings

    class FakeSmithRuntime:
        async def run_read_only(self, objective, actor=None, request_id=None):
            assert "system: You are in a coding console." in objective
            assert "user: Inspect repo status." in objective
            assert actor == "agent_smith:openai-compatible:open-webui"
            return SmithRunSummary(
                request_id=request_id or "smith-test",
                objective=objective,
                total_tasks=1,
                completed_tasks=1,
                failed_tasks=0,
                escalated_tasks=0,
                approval_required_count=0,
                status="completed",
                message="Read-only inspection complete.",
                duration_ms=12,
            )

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_read_only_enabled", True)
    monkeypatch.setattr(director_main, "SmithRuntime", FakeSmithRuntime)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-connector-token"},
        json={
            "model": "agent-smith",
            "user": "open-webui",
            "messages": [
                {"role": "system", "content": "You are in a coding console."},
                {"role": "user", "content": "Inspect repo status."},
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["object"] == "chat.completion"
    assert data["model"] == "agent-smith"
    assert data["choices"][0]["message"]["role"] == "assistant"
    assert "Read-only inspection complete." in data["choices"][0]["message"]["content"]
    assert data["freyja"]["smith_mode"] == "read_only"


def test_openai_chat_completion_plain_prompt_uses_configured_ollama(monkeypatch) -> None:
    from freyja.config import settings

    seen = {}

    async def fake_chat(self, prompt, **kwargs):
        seen["base_url"] = self.base_url
        seen["model"] = self.model
        seen["prompt"] = prompt
        return {"message": {"role": "assistant", "content": "test"}}

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_read_only_enabled", True)
    monkeypatch.setattr(settings, "ollama_base_url", "http://100.115.228.56:11434")
    monkeypatch.setattr(settings, "ollama_chat_model", "qwen2.5:7b")
    monkeypatch.setattr("freyja.main.OllamaClient.chat", fake_chat)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-connector-token"},
        json={
            "model": "agent-smith",
            "messages": [{"role": "user", "content": "say test"}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] == "test"
    assert data["freyja"]["smith_mode"] == "chat"
    assert seen == {
        "base_url": "http://100.115.228.56:11434",
        "model": "qwen2.5:7b",
        "prompt": "user: say test",
    }


def test_openai_chat_completion_website_rebuild_uses_chat_model(monkeypatch) -> None:
    from freyja.config import settings

    seen = {}

    async def fake_chat(self, prompt, **kwargs):
        seen["prompt"] = prompt
        return {"message": {"role": "assistant", "content": "Yes. Tell me what stack and files to use."}}

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_read_only_enabled", True)
    monkeypatch.setattr("freyja.main.OllamaClient.chat", fake_chat)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-connector-token"},
        json={
            "model": "agent-smith",
            "messages": [{"role": "user", "content": "can you help me rebuild my website?"}],
            "stream": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["message"]["content"] == "Yes. Tell me what stack and files to use."
    assert data["freyja"]["smith_mode"] == "chat"
    assert seen["prompt"] == "user: can you help me rebuild my website?"


def test_openai_chat_completion_streams_sse_when_requested(monkeypatch) -> None:
    from freyja.config import settings

    async def fake_chat(self, prompt, **kwargs):
        return {"message": {"role": "assistant", "content": "streamed test"}}

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_read_only_enabled", True)
    monkeypatch.setattr("freyja.main.OllamaClient.chat", fake_chat)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-connector-token"},
        json={
            "model": "agent-smith",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"object":"chat.completion.chunk"' in response.text
    assert '"content":"streamed test"' in response.text
    assert "data: [DONE]" in response.text


def test_openai_chat_completion_accepts_common_client_fields(monkeypatch) -> None:
    from freyja import main as director_main
    from freyja.agents.models import SmithRunSummary
    from freyja.config import settings

    class FakeSmithRuntime:
        async def run_read_only(self, objective, actor=None, request_id=None):
            return SmithRunSummary(
                request_id=request_id or "smith-test",
                objective=objective,
                total_tasks=1,
                completed_tasks=1,
                failed_tasks=0,
                escalated_tasks=0,
                approval_required_count=0,
                status="completed",
                message="Accepted common client fields.",
                duration_ms=12,
            )

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_read_only_enabled", True)
    monkeypatch.setattr(director_main, "SmithRuntime", FakeSmithRuntime)

    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-connector-token"},
        json={
            "model": "agent-smith",
            "stream": True,
            "temperature": 0.1,
            "max_tokens": 128,
            "top_p": 0.9,
            "tools": [],
            "tool_choice": "auto",
            "stop": ["done"],
            "presence_penalty": 0,
            "frequency_penalty": 0,
            "unknown_client_field": "ignored",
            "messages": [{"role": "user", "content": "Inspect repo status."}],
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"object":"chat.completion.chunk"' in response.text
    assert "Accepted common client fields." in response.text
    assert "data: [DONE]" in response.text


def test_openai_chat_completion_accepts_structured_content(monkeypatch) -> None:
    from freyja.config import settings

    seen = {}

    async def fake_chat(self, prompt, **kwargs):
        seen["prompt"] = prompt
        return {"message": {"role": "assistant", "content": "Accepted structured content."}}

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    monkeypatch.setattr(settings, "agent_smith_enabled", True)
    monkeypatch.setattr(settings, "agent_smith_read_only_enabled", True)
    monkeypatch.setattr("freyja.main.OllamaClient.chat", fake_chat)

    response = client.post(
        "/v1/chat/completions",
        headers={"x-api-key": "test-connector-token"},
        json={
            "model": "agent-smith",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
        },
    )

    assert response.status_code == 200
    assert seen["prompt"] == "user: hello"
    assert "Accepted structured content." in response.json()["choices"][0]["message"]["content"]


def test_openai_chat_completion_rejects_unknown_model(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "freyja_connector_token", "test-connector-token")
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-connector-token"},
        json={"model": "qwen", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 404


def test_ollama_health_reachable(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:11434")
    with patch("freyja.ollama_client.OllamaClient.healthy", new_callable=AsyncMock) as mock_healthy:
        mock_healthy.return_value = True
        response = client.get("/ollama/health")

    assert response.status_code == 200
    data = response.json()
    assert data["ollama_reachable"] is True
    assert data["base_url"] == "http://127.0.0.1:11434"


def test_local_reasoning_health_available(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "ollama_reasoning_base_url", "http://odin:11434")
    monkeypatch.setattr(settings, "ollama_reasoning_model", "gpt-oss:20b")
    with patch("freyja.ollama_client.OllamaClient.healthy", new_callable=AsyncMock) as mock_healthy, patch(
        "freyja.ollama_client.OllamaClient.has_model", new_callable=AsyncMock
    ) as mock_has_model:
        mock_healthy.return_value = True
        mock_has_model.return_value = True
        response = client.get("/local-reasoning/health")

    assert response.status_code == 200
    data = response.json()
    assert data["local_reasoning_reachable"] is True
    assert data["base_url"] == "http://odin:11434"
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


def test_local_reasoning_warm(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "ollama_reasoning_base_url", "http://odin:11434")
    monkeypatch.setattr(settings, "ollama_reasoning_model", "gpt-oss:20b")
    with patch("freyja.ollama_client.OllamaClient.warm", new_callable=AsyncMock) as mock_warm:
        mock_warm.return_value = True
        response = client.post("/local-reasoning/warm")

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "warmed": True,
        "base_url": "http://odin:11434",
        "model": "gpt-oss:20b",
        "keep_alive": "-1",
    }
    mock_warm.assert_awaited_once_with("gpt-oss:20b")


def test_providers_health_reports_enabled_profiles(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "iris_router_enabled", False)
    monkeypatch.setattr(settings, "cloud_enabled", True)
    monkeypatch.setattr(settings, "ollama_chat_model", "qwen2.5:7b")
    monkeypatch.setattr(settings, "ollama_reasoning_model", "gpt-oss:20b")
    monkeypatch.setattr(settings, "ollama_coding_model", "qwen2.5-coder:14b-q3")
    with patch("freyja.ollama_client.OllamaClient.healthy", new_callable=AsyncMock) as mock_healthy, patch(
        "freyja.ollama_client.OllamaClient.has_model", new_callable=AsyncMock
    ) as mock_has_model, patch(
        "freyja.openrouter_client.OpenRouterClient.healthy", new_callable=AsyncMock
    ) as mock_openrouter_healthy:
        mock_healthy.side_effect = [True, True, True, True]
        mock_has_model.side_effect = [True, True, True, True]
        mock_openrouter_healthy.return_value = False
        response = client.get("/providers/health")

    assert response.status_code == 200
    providers = {entry["provider_id"]: entry for entry in response.json()["providers"]}
    assert set(providers) == {"legacy_ollama", "local_vision", "heavy_local", "qwen_coding", "openrouter_frontier"}
    assert providers["legacy_ollama"]["locality"] == "iris"
    assert providers["legacy_ollama"]["logical_profile"] == "fast"
    assert providers["legacy_ollama"]["tier"] == 1
    assert providers["legacy_ollama"]["ready"] is True
    assert providers["local_vision"]["locality"] == "iris"
    assert providers["local_vision"]["tier"] == 2
    assert providers["local_vision"]["ready"] is True
    assert providers["heavy_local"]["locality"] == "local_heavy"
    assert providers["heavy_local"]["logical_profile"] == "reason"
    assert providers["heavy_local"]["tier"] == 3
    assert providers["heavy_local"]["ready"] is True
    assert providers["qwen_coding"]["locality"] == "local_heavy"
    assert providers["qwen_coding"]["logical_profile"] == "code"
    assert providers["qwen_coding"]["tier"] == 3
    assert providers["qwen_coding"]["ready"] is True
    assert providers["openrouter_frontier"]["locality"] == "cloud"
    assert providers["openrouter_frontier"]["tier"] == 4
    assert providers["openrouter_frontier"]["ready"] is False


def test_providers_health_reports_iris_router_residency(monkeypatch) -> None:
    from freyja.config import settings
    from freyja import main as director_main

    monkeypatch.setattr(settings, "iris_router_enabled", True)
    monkeypatch.setattr(settings, "cloud_enabled", False)
    with patch.object(director_main.iris_router, "healthy", new_callable=AsyncMock) as mock_healthy, patch.object(
        director_main.iris_router, "model_resident", new_callable=AsyncMock
    ) as mock_resident, patch(
        "freyja.ollama_client.OllamaClient.healthy", new_callable=AsyncMock
    ) as mock_ollama_healthy, patch(
        "freyja.ollama_client.OllamaClient.has_model", new_callable=AsyncMock
    ) as mock_has_model:
        mock_healthy.return_value = True
        mock_resident.return_value = True
        mock_ollama_healthy.return_value = True
        mock_has_model.return_value = True
        response = client.get("/providers/health")

    assert response.status_code == 200
    providers = {entry["provider_id"]: entry for entry in response.json()["providers"]}
    iris = providers["iris_router"]
    assert iris["ready"] is True
    assert iris["readiness"]["model_resident"] is True


def test_iris_router_health_endpoint_reports_router_status(monkeypatch) -> None:
    from freyja.config import settings
    from freyja import main as director_main

    monkeypatch.setattr(settings, "iris_router_enabled", True)
    monkeypatch.setattr(settings, "iris_router_advisory_enabled", True)
    with patch.object(director_main.iris_router, "healthy", new_callable=AsyncMock) as mock_healthy:
        mock_healthy.return_value = True
        response = client.get("/iris-router/health")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["advisory_enabled"] is True
    assert data["available"] is True
    assert data["reachable"] is True
    assert data["model"] == settings.iris_router_model


def test_iris_router_warm_endpoint_reports_warm_result(monkeypatch) -> None:
    from freyja.config import settings
    from freyja import main as director_main

    with patch.object(director_main.iris_router, "warm", new_callable=AsyncMock) as mock_warm:
        mock_warm.return_value = True
        response = client.post("/iris-router/warm")

    assert response.status_code == 200
    assert response.json() == {
        "warmed": True,
        "model": settings.iris_router_model,
        "keep_alive": settings.iris_router_keep_alive,
    }


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


def test_route_trace_includes_provider_profile_metadata(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
    monkeypatch.setattr(settings, "freyja3_canonical_enabled", False)
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"role": "assistant", "content": "Local hello"},
        }
        response = client.post("/route", json={"prompt": "Say hello", "provider": "local", "include_trace": True})

    assert response.status_code == 200
    trace = response.json()["trace"]
    assert trace["provider_selected"] == "ollama"
    assert trace["provider_profile_id"] == "legacy_ollama"
    assert trace["model_profile"] == "fast"
    assert trace["provider_locality"] == "iris"
    assert trace["selected_tier"] == 1
    assert trace["provider_readiness"] == {
        "ready": True,
        "host_reachable": True,
        "endpoint_healthy": True,
        "model_available": True,
        "model_resident": None,
        "observed_latency_ms": None,
        "detail": "provider response ok",
    }


def test_canonical_route_preserves_trace_and_returns_canonical_response(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
    monkeypatch.setattr(settings, "freyja3_canonical_enabled", False)
    payload = {
        "trace_id": "trace-canonical-1",
        "message_id": "message-canonical-1",
        "channel": "signal",
        "conversation_id": "conversation-canonical-1",
        "sender": {"channel_id": "sender-1", "address": "+15550000000"},
        "resolved_user_id": "joe",
        "resolved_agent_id": "cloyd-gibbler",
        "text": "Say hello",
        "permissions": ["private"],
    }
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"role": "assistant", "content": "Canonical hello"},
        }
        response = client.post("/canonical/route", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["trace_id"] == "trace-canonical-1"
    assert data["request_message_id"] == "message-canonical-1"
    assert data["channel"] == "signal"
    assert data["conversation_id"] == "conversation-canonical-1"
    assert data["resolved_user_id"] == "joe"
    assert data["resolved_agent_id"] == "cloyd-gibbler"
    assert data["text"] == "Canonical hello"
    trace = data["channel_metadata"]["trace"]
    assert trace["request_id"] == "trace-canonical-1"
    assert trace["model_profile"] == "reason"
    assert data["tool_results"] == []


def test_canonical_route_with_tools_required_returns_sanitized_tool_results(monkeypatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "freyja3_canonical_enabled", False)
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
            "hostname": "vulcan",
            "status": "ok",
            "status_code": 200,
            "iso_timestamp": "2024-01-01T00:00:00",
            "stdout": "raw internal stdout must not leak",
            "stderr": "raw internal stderr must not leak",
        },
        duration_ms=120,
        request_id="trace-canonical-tools",
    )
    payload = {
        "trace_id": "trace-canonical-tools",
        "message_id": "message-canonical-tools",
        "channel": "signal",
        "conversation_id": "conversation-canonical-tools",
        "sender": {"channel_id": "sender-1", "address": "+15550000000"},
        "resolved_user_id": "joe",
        "resolved_agent_id": "cloyd-gibbler",
        "text": "weather in Oslo",
        "channel_metadata": {"provider": "local", "tools_required": True},
        "permissions": ["private"],
    }

    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat, patch.object(
        router._registry, "execute", new_callable=AsyncMock
    ) as mock_execute:
        mock_chat.side_effect = [first_response, second_response]
        mock_execute.return_value = tool_result
        response = client.post("/canonical/route", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["text"] == "It is sunny in Oslo."
    assert data["tool_results"] == [
        {
            "tool_name": "get_weather",
            "success": True,
            "hostname": "vulcan",
            "status": "ok",
            "status_code": 200,
            "iso_timestamp": "2024-01-01T00:00:00",
            "duration_ms": 120,
        }
    ]
    raw_response = str(data)
    assert "stdout" not in raw_response
    assert "stderr" not in raw_response


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
    assert data["provider"] == "local_reasoning"
    assert data["response"] == "Local auto hello"
    mock_openrouter.assert_not_called()


def test_route_auto_does_not_fallback_to_openrouter() -> None:
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_ollama, patch(
        "freyja.openrouter_client.OpenRouterClient.chat", new_callable=AsyncMock
    ) as mock_openrouter:
        mock_ollama.return_value = {"error": "Ollama unreachable"}
        mock_openrouter.return_value = {
            "model": "openai/gpt-4o-mini",
            "response": "Unexpected cloud hello",
        }
        response = client.post("/route", json={"prompt": "Say hello", "provider": "auto"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Local model provider is unavailable."
    mock_openrouter.assert_not_called()


def test_route_auto_returns_503_when_selected_local_provider_fails() -> None:
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_ollama, patch(
        "freyja.openrouter_client.OpenRouterClient.chat", new_callable=AsyncMock
    ) as mock_openrouter:
        mock_ollama.return_value = {"error": "Ollama unreachable"}
        mock_openrouter.return_value = {"error": "OpenRouter API key not configured"}
        response = client.post("/route", json={"prompt": "Say hello", "provider": "auto"})

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail == "Local model provider is unavailable."
    mock_openrouter.assert_not_called()


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
    assert detail == "Local model provider is unavailable."
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
        mock_chat.side_effect = [
            first_response,
            {
                "model": "qwen2.5:1.5b",
                "message": {
                    "role": "assistant",
                    "content": "The disk usage tool timed out, so I cannot verify disk usage from the tool result.",
                },
            },
        ]
        mock_execute.return_value = tool_result
        response = client.post(
            "/route",
            json={"prompt": "check disk usage", "provider": "local", "tools_required": True},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "The disk usage tool timed out, so I cannot verify disk usage from the tool result."
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
