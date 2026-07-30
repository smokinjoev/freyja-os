import os
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from freyja.config import settings
from freyja.main import app
from freyja.memory.store import MemoryStore, get_store, set_store


client = TestClient(app)


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    db_path = str(tmp_path / "route_memory.db")
    monkeypatch.setattr(settings, "memory_database_path", db_path)
    monkeypatch.setattr(settings, "memory_enabled", True)
    store = MemoryStore(database_path=db_path, max_messages_per_conversation=1000, retention_days=90)
    set_store(store)
    store.initialize()
    yield store
    set_store(None)
    if os.path.exists(db_path):
        os.remove(db_path)


def test_route_with_conversation_id_persists_messages(isolated_store):
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"role": "assistant", "content": "Hello from memory"},
        }
        response = client.post("/route", json={
            "prompt": "Say hello",
            "provider": "local",
            "conversation_id": "conv-chat-1",
        })

    assert response.status_code == 200
    messages = isolated_store.get_messages("conv-chat-1").messages
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "Say hello"
    assert messages[1].role == "assistant"
    assert messages[1].content == "Hello from memory"
    assert messages[1].model == "qwen2.5:7b"


def test_route_without_conversation_id_does_not_persist(isolated_store):
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "model": "qwen2.5:1.5b",
            "message": {"role": "assistant", "content": "Hello"},
        }
        response = client.post("/route", json={
            "prompt": "Say hello",
            "provider": "local",
        })

    assert response.status_code == 200
    assert isolated_store.list_conversations().conversations == []


def test_route_memory_failure_does_not_crash(isolated_store):
    def broken_append(request):
        raise RuntimeError("memory append failed")

    isolated_store.append_message = broken_append

    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "model": "qwen2.5:1.5b",
            "message": {"role": "assistant", "content": "Hello despite memory"},
        }
        response = client.post("/route", json={
            "prompt": "Say hello",
            "provider": "local",
            "conversation_id": "conv-crash",
        })

    assert response.status_code == 200
    assert response.json()["response"] == "Hello despite memory"


def test_route_secrets_redacted_in_memory(isolated_store):
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_chat:
        mock_chat.return_value = {
            "model": "qwen2.5:1.5b",
            "message": {"role": "assistant", "content": "OK"},
        }
        response = client.post("/route", json={
            "prompt": "My token is sk-12345 and api_key=secret-value",
            "provider": "local",
            "conversation_id": "conv-secret",
        })

    assert response.status_code == 200
    messages = isolated_store.get_messages("conv-secret").messages
    assert len(messages) == 2
    user_content = messages[0].content
    assert "sk-12345" not in user_content
    assert "secret-value" not in user_content
    assert "<redacted>" in user_content


def test_route_raw_provider_error_redacted_in_memory(isolated_store):
    with patch("freyja.ollama_client.OllamaClient.chat", new_callable=AsyncMock) as mock_ollama, \
         patch("freyja.openrouter_client.OpenRouterClient.healthy", new_callable=AsyncMock) as mock_openrouter_healthy, \
         patch("freyja.openrouter_client.OpenRouterClient.chat", new_callable=AsyncMock) as mock_openrouter:
        mock_ollama.return_value = {"error": "Authorization: Bearer sk-bad"}
        mock_openrouter_healthy.return_value = True
        mock_openrouter.return_value = {"error": "Provider Error: timeout"}
        response = client.post("/route", json={
            "prompt": "large prompt " + "x" * 9000,
            "provider": "auto",
            "task_type": "coding",
            "conversation_id": "conv-error",
        })

    assert response.status_code == 503
    messages = isolated_store.get_messages("conv-error").messages
    if messages:
        assert "sk-bad" not in messages[0].content
        assert "Authorization" not in messages[0].content
