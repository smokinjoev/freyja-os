from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from freyja.main import app


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_ollama_health_reachable() -> None:
    with patch("freyja.ollama_client.OllamaClient.healthy", new_callable=AsyncMock) as mock_healthy:
        mock_healthy.return_value = True
        response = client.get("/ollama/health")

    assert response.status_code == 200
    data = response.json()
    assert data["ollama_reachable"] is True
    assert data["base_url"] == "http://127.0.0.1:11434"


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
    assert response.json()["detail"] == "OpenRouter API key not configured"
