from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from freyja.config import settings
from freyja.inference_gateway import InferenceGateway, InferenceRequest, InferenceTier


@pytest.fixture
def reset_gateway_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    defaults = {
        "cloud_enabled": True,
        "inference_gateway_enabled": True,
        "inference_gateway_monthly_hard_limit": 20.0,
        "inference_gateway_per_request_limit": 1.0,
        "inference_gateway_default_tier": "FAST",
        "inference_gateway_local_model": "qwen2.5:7b",
        "inference_gateway_free_model": "",
        "inference_gateway_fast_model": "qwen/qwen3.5-flash-02-23",
        "inference_gateway_reasoning_model": "moonshotai/kimi-k2.5",
        "inference_gateway_deep_model": "z-ai/glm-5",
        "inference_gateway_frontier_model": "openai/gpt-5.4",
        "inference_gateway_ollama_cloud_model": "",
        "inference_gateway_ollama_cloud_base_url": "",
        "inference_gateway_ollama_cloud_api_key": "",
        "inference_gateway_openrouter_allowlist": "",
        "openrouter_allowlist": "",
        "inference_gateway_fast_input_per_m": 0.065,
        "inference_gateway_fast_output_per_m": 0.26,
    }
    for key, value in defaults.items():
        monkeypatch.setattr(settings, key, value)


def test_fast_tier_maps_to_qwen_flash(reset_gateway_settings) -> None:
    gateway = InferenceGateway(ollama_client=AsyncMock(), openrouter_client=AsyncMock())

    decision = gateway.decide(InferenceRequest(prompt="Summarize this.", output_tokens_estimate=1000))

    assert decision.tier == InferenceTier.FAST
    assert decision.provider == "openrouter"
    assert decision.model == "qwen/qwen3.5-flash-02-23"
    assert 0 < decision.estimated_cost_usd < 0.001


def test_sensitive_cloud_request_falls_back_to_local(reset_gateway_settings) -> None:
    gateway = InferenceGateway(ollama_client=AsyncMock(), openrouter_client=AsyncMock())

    decision = gateway.decide(InferenceRequest(prompt="My password is secret", tier=InferenceTier.DEEP))

    assert decision.tier == InferenceTier.LOCAL
    assert decision.provider == "ollama"
    assert decision.model == "qwen2.5:7b"
    assert decision.estimated_cost_usd == 0.0
    assert decision.fallback_attempts[0]["outcome"] == "sensitive request kept local"


def test_free_tier_requires_configured_model(reset_gateway_settings) -> None:
    gateway = InferenceGateway(ollama_client=AsyncMock(), openrouter_client=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        gateway.decide(InferenceRequest(prompt="try a free model", tier=InferenceTier.FREE))

    assert exc.value.status_code == 503
    assert "FREE tier is not configured" in exc.value.detail


def test_frontier_requires_explicit_approval(reset_gateway_settings) -> None:
    gateway = InferenceGateway(ollama_client=AsyncMock(), openrouter_client=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        gateway.decide(InferenceRequest(prompt="hard problem", tier=InferenceTier.FRONTIER))

    assert exc.value.status_code == 403
    assert "explicit approval" in exc.value.detail


def test_frontier_approval_selects_premium_model(reset_gateway_settings) -> None:
    gateway = InferenceGateway(ollama_client=AsyncMock(), openrouter_client=AsyncMock())

    decision = gateway.decide(
        InferenceRequest(prompt="hard problem", tier=InferenceTier.FRONTIER, frontier_approved=True)
    )

    assert decision.tier == InferenceTier.FRONTIER
    assert decision.provider == "openrouter"
    assert decision.model == "openai/gpt-5.4"


def test_gateway_allowlist_blocks_unapproved_cloud_model(reset_gateway_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "inference_gateway_openrouter_allowlist", "qwen/qwen3.5-flash-02-23")
    gateway = InferenceGateway(ollama_client=AsyncMock(), openrouter_client=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        gateway.decide(InferenceRequest(prompt="deep work", tier=InferenceTier.DEEP))

    assert exc.value.status_code == 403


def test_ollama_cloud_requires_config(reset_gateway_settings) -> None:
    gateway = InferenceGateway(ollama_client=AsyncMock(), openrouter_client=AsyncMock())

    with pytest.raises(HTTPException) as exc:
        gateway.decide(InferenceRequest(prompt="long job", tier=InferenceTier.OLLAMA_CLOUD))

    assert exc.value.status_code == 503
    assert "OLLAMA_CLOUD tier is not configured" in exc.value.detail


@pytest.mark.asyncio
async def test_chat_uses_openrouter_for_fast_tier(reset_gateway_settings) -> None:
    openrouter = AsyncMock()
    openrouter.chat.return_value = {
        "model": "qwen/qwen3.5-flash-02-23",
        "response": "done",
        "usage": {"total_tokens": 12},
    }
    gateway = InferenceGateway(ollama_client=AsyncMock(), openrouter_client=openrouter)

    result = await gateway.chat(InferenceRequest(prompt="hello", tier=InferenceTier.FAST))

    assert result.response == "done"
    assert result.decision.provider == "openrouter"
    openrouter.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_uses_ollama_for_local_tier(reset_gateway_settings) -> None:
    ollama = AsyncMock()
    ollama.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "local"},
        "usage": {"total_tokens": 4},
    }
    gateway = InferenceGateway(ollama_client=ollama, openrouter_client=AsyncMock())

    result = await gateway.chat(InferenceRequest(prompt="hello", tier=InferenceTier.LOCAL))

    assert result.response == "local"
    assert result.decision.provider == "ollama"
    ollama.chat.assert_awaited_once()
