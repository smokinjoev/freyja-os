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
    assert captured["payload"]["keep_alive"] == "30m"
    assert captured["payload"]["options"]["num_predict"] >= 160


@pytest.mark.asyncio
async def test_warm_loads_model_with_minimal_prompt(client: OllamaClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr("freyja.config.settings.ollama_warmup_timeout_seconds", 12.0)

    def _capture(*args, **kwargs):
        request = httpx.Request("POST", str(args[0]))
        captured["payload"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={"model": "qwen2.5:7b", "message": {"content": "ok"}},
            request=request,
        )

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_capture):
        result = await client.warm("qwen2.5:7b")

    assert result["status"] == "ok"
    assert result["model"] == "qwen2.5:7b"
    payload = captured["payload"]
    assert payload["messages"] == [{"role": "user", "content": "."}]
    assert payload["keep_alive"] == "30m"
    assert payload["options"]["num_predict"] == 1


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
    assert result["model"] == "qwen2.5:7b"


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
async def test_tool_prompt_allows_explicit_reminder_writes(client: OllamaClient) -> None:
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
        await client.chat("remind me to get a chair Saturday", tools_required=True)

    system_content = captured["payload"]["messages"][0]["content"]
    assert "controlled-write tool" in system_content
    assert "Do not ask whether to use the tool" in system_content
    assert "reminder or calendar event" in system_content
    assert "calendar_create_event" in system_content
    assert "08:00 America/New_York" in system_content


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
