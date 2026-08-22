from unittest.mock import AsyncMock, patch

import httpx
import pytest

from freyja.local_openai_client import LocalOpenAIClient


@pytest.fixture
def client() -> LocalOpenAIClient:
    return LocalOpenAIClient("http://100.87.242.99:8088/v1", "Qwen3-30B-A3B")


@pytest.mark.asyncio
async def test_healthy_hits_llama_server_health(client: LocalOpenAIClient) -> None:
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=httpx.Response(200, text='{"status":"ok"}')):
        assert await client.healthy() is True


@pytest.mark.asyncio
async def test_chat_sends_openai_compatible_payload(client: LocalOpenAIClient) -> None:
    captured: dict[str, object] = {}

    def _capture(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        captured["url"] = str(args[0])
        captured["payload"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={
                "model": "Qwen3-30B-A3B",
                "choices": [{"finish_reason": "stop", "message": {"content": "hello"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            },
            request=request,
        )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_capture):
        result = await client.chat("hi", output_tokens=160)

    assert captured["url"] == "http://100.87.242.99:8088/v1/chat/completions"
    payload = captured["payload"]
    assert payload["model"] == "Qwen3-30B-A3B"
    assert payload["messages"][0]["role"] == "system"
    assert "Freyja" in payload["messages"][0]["content"]
    assert payload["messages"][1] == {"role": "user", "content": "hi"}
    assert payload["max_tokens"] == 160
    assert result["response"] == "hello"
    assert result["usage"]["total_tokens"] == 12


@pytest.mark.asyncio
async def test_vision_chat_sends_multimodal_payload() -> None:
    vision_client = LocalOpenAIClient("http://100.87.242.99:8091/v1", "gemma-3-27b-it")
    captured: dict[str, object] = {}

    def _capture(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        captured["url"] = str(args[0])
        captured["payload"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={
                "model": "gemma-3-27b-it",
                "choices": [{"finish_reason": "stop", "message": {"content": '{"total":"42.19"}'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
            },
            request=request,
        )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_capture):
        result = await vision_client.vision_chat(
            prompt="extract total",
            image_url="data:image/png;base64,abc",
            output_tokens=160,
        )

    assert captured["url"] == "http://100.87.242.99:8091/v1/chat/completions"
    payload = captured["payload"]
    assert payload["model"] == "gemma-3-27b-it"
    assert payload["messages"][1]["content"] == [
        {"type": "text", "text": "extract total"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ]
    assert payload["temperature"] == 0.0
    assert result["status"] == "ok"
    assert result["response"] == '{"total":"42.19"}'
