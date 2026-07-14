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
