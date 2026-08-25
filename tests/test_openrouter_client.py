"""Tests for the OpenRouter client, especially system-prompt injection."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from freyja.openrouter_client import OpenRouterClient
from freyja.media import ImageInput
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
async def test_chat_no_api_key_returns_error() -> None:
    c = OpenRouterClient(base_url="https://openrouter.ai/api/v1", api_key="", model="openai/gpt-4o-mini")
    result = await c.chat("hi")
    assert "error" in result
    assert "OpenRouter API key not configured" in result["error"]


@pytest.mark.asyncio
async def test_chat_sends_images_as_multimodal_content(client: OpenRouterClient) -> None:
    captured: dict[str, object] = {}

    def _capture(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        captured["payload"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={
                "model": "openai/gpt-4o-mini",
                "choices": [{"message": {"content": "a red square"}}],
                "usage": {},
            },
            request=request,
        )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_capture):
        result = await client.chat(
            "Identify this image",
            images=[ImageInput(mime_type="image/png", data_base64="ZmFrZQ==", filename="photo.png")],
        )

    assert result["response"] == "a red square"
    content = captured["payload"]["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "Identify this image"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == "data:image/png;base64,ZmFrZQ=="


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


@pytest.mark.asyncio
async def test_healthy_returns_false_without_api_key() -> None:
    c = OpenRouterClient(base_url="https://openrouter.ai/api/v1", api_key="", model="openai/gpt-4o-mini")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mocked_get:
        assert await c.healthy() is False

    mocked_get.assert_not_called()


@pytest.mark.asyncio
async def test_healthy_retries_transient_failure(client: OpenRouterClient) -> None:
    responses = [
        httpx.ConnectTimeout("temporary"),
        httpx.Response(200, json={"data": []}),
    ]

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=responses) as mocked_get:
        assert await client.healthy() is True

    assert mocked_get.await_count == 2
