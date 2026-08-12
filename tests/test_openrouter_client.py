"""Tests for the OpenRouter client, especially system-prompt injection."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from freyja.openrouter_client import OpenRouterClient
from freyja.system_prompt import FREYJA_SYSTEM_PROMPT


@pytest.fixture
def client() -> OpenRouterClient:
    return OpenRouterClient(
        base_url="https://openrouter.ai/api/v1",
        api_key="fake-key",
        model="openai/gpt-4o-mini",
    )


@pytest.mark.asyncio
async def test_chat_sends_system_prompt_first(client: OpenRouterClient) -> None:
    captured: dict[str, object] = {}

    def _capture(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        captured["payload"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={
                "model": "openai/gpt-4o-mini",
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"total_tokens": 10},
            },
            request=request,
        )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_capture):
        result = await client.chat("hi")

    assert result.get("response") == "hello"
    payload = captured["payload"]
    assert payload is not None
    messages = payload["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == FREYJA_SYSTEM_PROMPT
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "hi"


@pytest.mark.asyncio
async def test_chat_strips_reasoning_block(client: OpenRouterClient) -> None:
    def _respond(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        return httpx.Response(
            200,
            json={
                "model": "qwen/qwen3.5-flash-02-23",
                "choices": [
                    {
                        "message": {
                            "content": "Thinking Process:\nprivate reasoning\n</think>\n\nfast route ok"
                        }
                    }
                ],
                "usage": {"total_tokens": 10},
            },
            request=request,
        )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_respond):
        result = await client.chat("hi")

    assert result.get("response") == "fast route ok"


@pytest.mark.asyncio
async def test_chat_no_api_key_returns_error() -> None:
    c = OpenRouterClient(base_url="https://openrouter.ai/api/v1", api_key="", model="openai/gpt-4o-mini")
    result = await c.chat("hi")
    assert "error" in result
    assert "OpenRouter API key not configured" in result["error"]


@pytest.mark.asyncio
async def test_chat_no_model_returns_error(client: OpenRouterClient) -> None:
    c = OpenRouterClient(base_url="https://openrouter.ai/api/v1", api_key="fake-key", model="")
    result = await c.chat("hi")
    assert "error" in result
    assert "No OpenRouter model configured" in result["error"]


@pytest.mark.asyncio
async def test_healthy_hits_models_endpoint(client: OpenRouterClient) -> None:
    with patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        return_value=httpx.Response(200, json={"data": []}),
    ):
        assert await client.healthy() is True
