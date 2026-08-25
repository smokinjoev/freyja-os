"""Tests for the Ollama client, especially system-prompt injection."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from freyja.ollama_client import OllamaClient
from freyja.media import ImageInput
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
    assert captured["payload"]["options"]["num_predict"] >= 160


@pytest.mark.asyncio
async def test_chat_excludes_thinking_from_result(client: OllamaClient) -> None:
    def _capture(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b",
                "message": {
                    "content": "visible",
                    "thinking": "private chain of thought",
                },
                "done_reason": "stop",
                "prompt_eval_count": 12,
                "eval_count": 3,
                "eval_duration": 1_000_000_000,
            },
            request=request,
        )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_capture):
        result = await client.chat("hi")

    assert result["message"]["content"] == "visible"
    assert "thinking" not in result["message"]
    assert "private chain of thought" not in str(result)


@pytest.mark.asyncio
async def test_chat_sends_images_to_ollama_message(client: OllamaClient) -> None:
    captured: dict[str, object] = {}

    def _capture(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        captured["payload"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={"model": "llava:latest", "message": {"content": "a red square"}},
            request=request,
        )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_capture):
        result = await client.chat(
            "Identify this image",
            model="llava:latest",
            images=[ImageInput(mime_type="image/png", data_base64="ZmFrZQ==")],
        )

    assert result["message"]["content"] == "a red square"
    user_message = captured["payload"]["messages"][1]
    assert user_message["content"] == "Identify this image"
    assert user_message["images"] == ["ZmFrZQ=="]


@pytest.mark.asyncio
async def test_empty_content_length_retries_once_success(client: OllamaClient) -> None:
    responses = [
        {
            "model": "qwen2.5:7b",
            "message": {"content": "", "thinking": "still thinking"},
            "done_reason": "length",
            "eval_count": 160,
            "eval_duration": 1_000_000_000,
        },
        {
            "model": "qwen2.5:7b",
            "message": {"content": "done", "thinking": "hidden"},
            "done_reason": "stop",
            "eval_count": 2,
            "eval_duration": 1_000_000_000,
        },
    ]
    budgets: list[int] = []

    def _capture(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        budgets.append(kwargs["json"]["options"]["num_predict"])
        return httpx.Response(200, json=responses.pop(0), request=request)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_capture) as post:
        result = await client.chat("hi", output_tokens=160)

    assert post.await_count == 2
    assert result["message"]["content"] == "done"
    assert result["retried"] is True
    assert budgets == [160, 1024]


@pytest.mark.asyncio
async def test_empty_content_retry_exhaustion_returns_provider_failure(client: OllamaClient) -> None:
    def _capture(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b",
                "message": {"content": "", "thinking": "hidden"},
                "done_reason": "length",
                "eval_count": 160,
                "eval_duration": 1_000_000_000,
            },
            request=request,
        )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_capture) as post:
        result = await client.chat("hi", output_tokens=160)

    assert post.await_count == 2
    assert result["status"] == "empty_content"
    assert result["error"] == "Ollama returned empty content"
    assert "thinking" not in result["message"]


@pytest.mark.asyncio
async def test_chat_unavailable_returns_error(client: OllamaClient) -> None:
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=httpx.ConnectError("refused")):
        result = await client.chat("hi")

    assert "error" in result


@pytest.mark.asyncio
async def test_warm_sends_numeric_indefinite_keep_alive(client: OllamaClient) -> None:
    captured: dict[str, object] = {}

    def _capture(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        captured["payload"] = kwargs.get("json")
        return httpx.Response(200, json={"done": True}, request=request)

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_capture):
        assert await client.warm("gpt-oss:20b", keep_alive="-1") is True

    assert captured["payload"]["model"] == "gpt-oss:20b"
    assert captured["payload"]["keep_alive"] == -1


@pytest.mark.asyncio
async def test_has_model_accepts_exact_or_tag_prefix(client: OllamaClient) -> None:
    with patch.object(client, "tags", new_callable=AsyncMock) as tags:
        tags.return_value = {"models": [{"name": "gpt-oss:20b"}, {"name": "qwen2.5:7b"}]}
        assert await client.has_model("gpt-oss:20b")
        assert await client.has_model("qwen2.5")
        assert not await client.has_model("missing:latest")


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
