from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from certification.runner import load_suite
from freyja.router import RouteRequest, Router


def test_voice_assistant_suite_has_100_cases_and_coverage() -> None:
    suite = load_suite("voice/assistant_conversations")

    assert len(suite.cases) == 100
    prefixes = {case.name.rsplit("-", 1)[0] for case in suite.cases}
    assert prefixes == {
        "hera-voice",
        "voice-calendar",
        "voice-home",
        "voice-odin",
        "voice-private",
        "voice-quick",
        "voice-repair",
        "voice-weather",
    }


@pytest.mark.asyncio
async def test_voice_assistant_suite_matches_atlas_routing_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "cloud_enabled", True)
    monkeypatch.setattr(settings, "openrouter_allowlist", "openai/gpt-4o-mini")
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
    monkeypatch.setattr(settings, "ollama_chat_model", "qwen2.5:7b")
    monkeypatch.setattr(settings, "ollama_reasoning_model", "gpt-oss:20b")

    router = Router()
    router.ollama_client = AsyncMock()
    router.ollama_client.healthy.return_value = True
    router.reasoning_ollama_client = AsyncMock()
    router.openrouter_client = AsyncMock()

    suite = load_suite("voice/assistant_conversations")
    mismatches = []
    for case in suite.cases:
        request_data = {"prompt": case.prompt, "provider": "auto"}
        request_data.update(case.route_request)
        request_data["prompt"] = case.prompt
        decision = await router.decide(RouteRequest(**request_data))
        expected = case.expects.get("provider")
        if decision.provider != expected:
            mismatches.append((case.name, expected, decision.provider, decision.reason))
        if case.expects.get("provider_not") == decision.provider:
            mismatches.append((case.name, f"not {case.expects['provider_not']}", decision.provider, decision.reason))
        if case.expects.get("privacy_local") and decision.provider not in {"ollama", "local_reasoning"}:
            mismatches.append((case.name, "internal provider", decision.provider, decision.reason))

    assert mismatches == []
