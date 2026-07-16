"""Tests for the Ollama client, especially system-prompt injection."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from freyja.ollama_client import OllamaClient
from freyja.system_prompt import FREYJA_SYSTEM_PROMPT


@pytest.fixture
def client() -> OllamaClient:
    return OllamaClient(base_url="http://127.0.0.1:11434", model="qwen2.5:7b")


@pytest.mark.asyncio
async def test_chat_sends_system_prompt_first(client: OllamaClient) -> None:
    captured: dict[str, object] = {}

    def _capture(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        captured["payload"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={"model": "qwen2.5:7b", "message": {"content": "hello"}},
            request=request,
        )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_capture):
        result = await client.chat("hi")

    assert result.get("message", {}).get("content") == "hello"
    payload = captured["payload"]
    assert payload is not None
    messages = payload["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "Freyja" in messages[0]["content"]
    assert "Do not claim to be Qwen" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "hi"


@pytest.mark.asyncio
async def test_chat_includes_maintenance_workflow(client: OllamaClient) -> None:
    captured: dict[str, object] = {}

    def _capture(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        captured["payload"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={"model": "qwen2.5:7b", "message": {"content": "ok"}},
            request=request,
        )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_capture):
        await client.chat("fix this")

    system_content = captured["payload"]["messages"][0]["content"]
    assert "inspect the current state" in system_content
    assert "one small step at a time" in system_content
    assert "run relevant tests" in system_content
    assert "do not commit until tests pass" in system_content


@pytest.mark.asyncio
async def test_chat_no_model_returns_error() -> None:
    c = OllamaClient(base_url="http://127.0.0.1:11434", model="")
    result = await c.chat("hi")
    assert "error" in result
    assert "No Ollama model configured" in result["error"]


@pytest.mark.asyncio
async def test_healthy_hits_root(client: OllamaClient) -> None:
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=httpx.Response(200, text="Ollama is running")):
        assert await client.healthy() is True


@pytest.mark.asyncio
async def test_healthy_false_on_error(client: OllamaClient) -> None:
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=httpx.ConnectError("refused")):
        assert await client.healthy() is False


@pytest.mark.asyncio
async def test_tags_parses_model_list(client: OllamaClient) -> None:
    data = {"models": [{"name": "qwen2.5:7b"}, {"name": "qwen2.5:1.5b"}]}

    def _capture(*args, **kwargs):
        request = httpx.Request("GET", str(args[0]))
        return httpx.Response(200, json=data, request=request)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=_capture):
        result = await client.tags()
    assert result["models"][0]["name"] == "qwen2.5:7b"
