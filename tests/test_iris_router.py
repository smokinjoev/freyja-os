from unittest.mock import AsyncMock, patch

import httpx

from freyja.iris_router import IRIS_ROUTER_SYSTEM_PROMPT, IrisRouterClient


class _Response:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "http://iris:11434")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self) -> dict:
        return self._payload


async def test_healthy_requires_configured_model() -> None:
    client = IrisRouterClient(base_url="http://iris:11434", model="qwen2.5:7b")
    mock_http = AsyncMock()
    mock_http.get.return_value = _Response({"models": [{"name": "qwen2.5:7b"}]})

    with patch("freyja.iris_router.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = mock_http
        assert await client.healthy() is True


def test_system_prompt_prefers_upward_routing_when_uncertain() -> None:
    assert "When uncertain, route upward" in IRIS_ROUTER_SYSTEM_PROMPT
    assert "avoid under-routing" in IRIS_ROUTER_SYSTEM_PROMPT
    assert "complexity" in IRIS_ROUTER_SYSTEM_PROMPT


async def test_warm_requests_indefinite_residency() -> None:
    client = IrisRouterClient(base_url="http://iris:11434", model="qwen2.5:7b")
    mock_http = AsyncMock()
    mock_http.post.return_value = _Response({"done": True})

    with patch("freyja.iris_router.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = mock_http
        assert await client.warm() is True

    _, kwargs = mock_http.post.call_args
    assert kwargs["json"]["model"] == "qwen2.5:7b"
    assert kwargs["json"]["keep_alive"] == -1


async def test_model_resident_checks_ollama_ps() -> None:
    client = IrisRouterClient(base_url="http://iris:11434", model="qwen2.5:7b")
    mock_http = AsyncMock()
    mock_http.get.return_value = _Response({"models": [{"name": "qwen2.5:7b"}]})

    with patch("freyja.iris_router.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = mock_http
        assert await client.model_resident() is True

    mock_http.get.assert_awaited_once_with("http://iris:11434/api/ps")


async def test_recommend_parses_strict_route_json() -> None:
    client = IrisRouterClient(base_url="http://iris:11434", model="qwen2.5:7b")
    mock_http = AsyncMock()
    mock_http.post.return_value = _Response(
        {
            "model": "qwen2.5:7b",
            "message": {
                "content": (
                    '{"tier":3,"task":"coding","complexity":4,"needs_tools":false,'
                    '"sensitivity":"routine","confidence":0.96,'
                    '"preferred_target":"local_heavy",'
                    '"reason":"Requires complex coding reasoning"}'
                )
            },
        }
    )

    with patch("freyja.iris_router.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = mock_http
        result = await client.recommend("debug this stack trace", task_type="debug")

    assert result.ok is True
    assert result.recommendation is not None
    assert result.recommendation.tier == 3
    assert result.recommendation.complexity == 4
    assert result.recommendation.preferred_target == "local_heavy"

    _, kwargs = mock_http.post.call_args
    payload = kwargs["json"]
    assert payload["think"] is False
    assert payload["keep_alive"] == -1
    assert payload["format"] == "json"
    assert payload["options"]["num_predict"] == 100


async def test_recommend_rejects_invalid_model_output() -> None:
    client = IrisRouterClient(base_url="http://iris:11434", model="qwen2.5:7b")
    mock_http = AsyncMock()
    mock_http.post.return_value = _Response(
        {"model": "qwen2.5:7b", "message": {"content": "I think tier three is best."}}
    )

    with patch("freyja.iris_router.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.return_value = mock_http
        result = await client.recommend("debug this")

    assert result.ok is False
    assert result.recommendation is None
    assert "invalid routing JSON" in (result.error or "")


async def test_recommend_failure_is_non_authoritative() -> None:
    client = IrisRouterClient(base_url="http://iris:11434", model="qwen2.5:7b")

    with patch("freyja.iris_router.httpx.AsyncClient") as async_client:
        async_client.return_value.__aenter__.side_effect = httpx.ConnectError("offline")
        result = await client.recommend("hello")

    assert result.ok is False
    assert result.recommendation is None
    assert "offline" in (result.error or "")
