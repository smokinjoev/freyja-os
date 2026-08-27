import json
from typing import Any
from unittest.mock import AsyncMock, patch

from unittest.mock import AsyncMock

import pytest

from freyja.config import Settings, settings
from freyja.iris_router import IrisRouteRecommendation, IrisShadowResult
from freyja.media import ImageInput
from freyja.memory.models import MemoryPrincipal, PutSharedMemoryRequest
from freyja.memory.store import MemoryStore, set_store
from freyja.router import RouteRequest, Router
from freyja.tools.builtin import register_builtin_tools
from freyja.tools.models import ToolDefinition, ToolExecutionRequest
from freyja.tools.registry import ToolRegistry


@pytest.fixture
def router() -> Router:
    r = Router()
    r.ollama_client = AsyncMock()
    r.openrouter_client = AsyncMock()
    return r


@pytest.fixture
def isolated_memory_store(tmp_path, monkeypatch: pytest.MonkeyPatch):
    db_path = str(tmp_path / "router_memory.db")
    monkeypatch.setattr(settings, "memory_database_path", db_path)
    monkeypatch.setattr(settings, "memory_enabled", True)
    store = MemoryStore(database_path=db_path, max_messages_per_conversation=1000, retention_days=90)
    set_store(store)
    store.initialize()
    yield store
    set_store(None)


@pytest.fixture
def disable_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cloud_enabled", False)


@pytest.fixture
def enable_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cloud_enabled", True)


@pytest.fixture
def reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    defaults = {
        "cloud_enabled": True,
        "openrouter_monthly_soft_limit": 20.0,
        "openrouter_monthly_hard_limit": 30.0,
        "openrouter_per_request_limit": 1.0,
        "local_max_prompt_chars": 8000,
        "openrouter_allowlist": "",
        "ollama_model": "qwen2.5:1.5b",
        "ollama_vision_model": "moondream",
        "ollama_reasoning_model": "gpt-oss:20b",
        "openrouter_model": "openai/gpt-4o-mini",
        "iris_router_enabled": False,
        "iris_router_advisory_enabled": False,
        "iris_router_confidence_threshold": 0.8,
    }
    for key, value in defaults.items():
        monkeypatch.setattr(settings, key, value)


def _settings_with_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cloud_enabled", True)
    monkeypatch.setattr(settings, "openrouter_allowlist", "openai/gpt-4o-mini")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("prompt", "expected"),
    [
        ("Answer with only the number: 9 + 6 * 2.", "21"),
        ("The code is the second letter of 'chair'. Answer with one letter.", "h"),
        ("How many distinct vowel letters are in the word 'apple'? Answer with only the number.", "2"),
        ("Answer with exactly two words: local agent", "local agent"),
        ("Answer with the platform name in 'iMessage thread'.", "iMessage"),
    ],
)
async def test_exact_answer_requests_use_deterministic_path(prompt: str, expected: str) -> None:
    result = await Router().execute(RouteRequest(prompt=prompt, provider="local"))

    assert result.response == expected
    assert result.decision.provider == "deterministic"
    assert result.decision.reason == "deterministic exact-answer capability"


class _FakeIrisRouter:
    def __init__(self, result: IrisShadowResult) -> None:
        self.result = result
        self.recommend = AsyncMock(return_value=result)


def _iris_result(
    *,
    target: str,
    confidence: float,
    sensitivity: str = "routine",
    task: str = "chat",
    model: str = "qwen2.5:7b",
    latency_ms: int = 25,
    complexity: int = 2,
) -> IrisShadowResult:
    return IrisShadowResult(
        ok=True,
        model=model,
        latency_ms=latency_ms,
        recommendation=IrisRouteRecommendation(
            tier={"deterministic": 0, "iris": 1, "local_heavy": 3, "isolated_worker": 3, "cloud": 4}[target],
            task=task,
            complexity=complexity,
            needs_tools=False,
            sensitivity=sensitivity,
            confidence=confidence,
            preferred_target=target,
            reason="classifier route",
        ),
    )


def _assert_authorization_record(record: dict[str, Any], expected: dict[str, Any]) -> None:
    for key, value in expected.items():
        assert record[key] == value
    assert record["actor"] == "atlas_director"
    assert "risk_level" in record
    assert "confirmation_policy" in record
    assert "connector_trusted" in record
    assert "principal_subject_present" in record
    assert "target_scope" in record


async def test_manual_local_override(router: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "local"},
        "prompt_eval_count": 4,
        "eval_count": 2,
        "latency_ms": 12,
    }

    req = RouteRequest(prompt="hi", provider="local")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert result.decision.reason == "manual local override"
    assert result.response == "local"
    assert result.runtime_evidence.provider_selected == "ollama"
    assert result.runtime_evidence.model_selected == "qwen2.5:7b"
    assert result.runtime_evidence.routing_reason == "manual local override"
    assert result.runtime_evidence.token_counts["total_tokens"] == 6
    assert result.runtime_evidence.timing["ollama_latency_ms"] == 12
    assert result.runtime_evidence.timing["total_provider_latency_ms"] == 12
    assert result.runtime_evidence.timing["time_to_first_token_ms"] == 12
    assert result.latency_ms is not None
    router.ollama_client.chat.assert_awaited_once()
    _, kwargs = router.ollama_client.chat.call_args
    assert kwargs["prompt"] == "hi"
    assert kwargs["model"] == "qwen2.5:7b"


async def test_person_agent_context_is_added_by_director_for_imessage(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "memory_shared_enabled", False)
    monkeypatch.setattr(settings, "ollama_reasoning_model", "gpt-oss-freyja:20b-analysis-prefill")
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss-freyja:20b-analysis-prefill",
        "message": {"content": "noted"},
    }
    principal = MemoryPrincipal(
        client_type="imessage",
        client_subject="agent:cloyd-gibbler",
        account_owner="person:joe",
        conversation_id="imessage-conv:test",
    )

    result = await router.execute(
        RouteRequest(prompt="What is the plan?", provider="auto"),
        memory_principal=principal,
        person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
    )

    assert result.decision.provider == "local_reasoning"
    prompt = router.ollama_client.chat.await_args.kwargs["prompt"]
    assert "BEGIN FREYJA DIRECT AGENT CONTEXT" in prompt
    assert "Interface: imessage" in prompt
    assert "Addressing person: Joe (person_id=joe)" in prompt
    assert "Active agent: Cloyd Gibbler (agent_id=cloyd-gibbler)" in prompt
    assert "Required response identity: Cloyd Gibbler" in prompt
    assert "direct terminal session for this person" in prompt
    assert prompt.endswith("Current user request:\nWhat is the plan?")


async def test_image_request_routes_to_approved_cloud_vision_with_images(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_allowlist(monkeypatch)
    router.openrouter_client.chat.return_value = {"response": "The image shows a red square."}

    req = RouteRequest(
        prompt="Identify this image",
        provider="auto",
        images=[ImageInput(mime_type="image/png", data_base64="ZmFrZQ==", filename="photo.png")],
    )
    result = await router.execute(req)

    assert result.decision.provider == "openrouter"
    assert "approved cloud vision" in result.decision.reason
    assert result.response == "The image shows a red square."
    router.ollama_client.chat.assert_not_called()
    router.openrouter_client.chat.assert_awaited_once()
    assert router.openrouter_client.chat.await_args.kwargs["images"] == req.images


async def test_image_request_falls_back_to_cloud_when_local_vision_errors(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_allowlist(monkeypatch)
    monkeypatch.setattr(settings, "cloud_enabled", True)
    router.ollama_client.chat.return_value = {"error": "local vision unavailable"}
    router.openrouter_client.chat.return_value = {"response": "The image shows a costume."}

    req = RouteRequest(
        prompt="What do you see in this photo?",
        provider="local",
        images=[ImageInput(mime_type="image/heic", data_base64="ZmFrZQ==", filename="photo.heic")],
    )
    result = await router.execute(req)

    assert result.decision.provider == "openrouter"
    assert "cloud vision fallback" in result.decision.reason
    assert result.response == "The image shows a costume."
    assert any(attempt["provider"] == "local_vision" for attempt in result.decision.fallback_attempts)
    router.ollama_client.chat.assert_awaited_once()
    router.openrouter_client.chat.assert_awaited_once()
    assert router.openrouter_client.chat.await_args.kwargs["images"] == req.images


async def test_provider_latency_records_warm_and_cold_start_buckets(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "warm"},
        "latency_ms": 9,
        "time_to_first_token_ms": 4,
        "model_resident": True,
    }

    warm = await router.execute(RouteRequest(prompt="hi", provider="local"))

    assert warm.runtime_evidence.provider_readiness["model_resident"] is True
    assert warm.runtime_evidence.timing["warm_start_latency_ms"] == 9
    assert warm.runtime_evidence.timing["time_to_first_token_ms"] == 4
    assert "cold_start_latency_ms" not in warm.runtime_evidence.timing

    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "cold"},
        "latency_ms": 1250,
        "model_resident": False,
    }

    cold = await router.execute(RouteRequest(prompt="hi again", provider="local"))

    assert cold.runtime_evidence.provider_readiness["model_resident"] is False
    assert cold.runtime_evidence.timing["cold_start_latency_ms"] == 1250
    assert "warm_start_latency_ms" not in cold.runtime_evidence.timing


async def test_manual_cloud_override_allowed(router: Router, monkeypatch: pytest.MonkeyPatch, reset_settings) -> None:
    _settings_with_allowlist(monkeypatch)
    router.openrouter_client.healthy.return_value = True
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud",
    }

    req = RouteRequest(prompt="hi", provider="cloud")
    result = await router.execute(req)

    assert result.decision.provider == "openrouter"
    assert "manual cloud override" in result.decision.reason
    assert result.response == "cloud"


async def test_cloud_default_model_comes_from_provider_profile(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
    reset_settings,
) -> None:
    monkeypatch.setattr(settings, "cloud_enabled", True)
    monkeypatch.setattr(settings, "openrouter_allowlist", "")
    monkeypatch.setattr(settings, "openrouter_model", "anthropic/claude-3.5-haiku")
    router.openrouter_client.healthy.return_value = True
    router.openrouter_client.chat.return_value = {
        "model": "anthropic/claude-3.5-haiku",
        "response": "cloud",
    }

    result = await router.execute(RouteRequest(prompt="public hello", provider="cloud", privacy="public"))

    assert result.decision.provider == "openrouter"
    assert result.decision.model == "anthropic/claude-3.5-haiku"
    _, kwargs = router.openrouter_client.chat.call_args
    assert kwargs["model"] == "anthropic/claude-3.5-haiku"


async def test_iris_advisory_disabled_does_not_call_classifier(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
    reset_settings,
) -> None:
    monkeypatch.setattr(settings, "iris_router_enabled", True)
    monkeypatch.setattr(settings, "iris_router_advisory_enabled", False)
    fake_iris = _FakeIrisRouter(_iris_result(target="local_heavy", confidence=0.99, task="debug"))
    router.register_iris_router_client(fake_iris)
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "routine"},
    }

    result = await router.execute(RouteRequest(prompt="hello", provider="auto", task_type="chat"))

    assert result.decision.provider == "ollama"
    assert result.decision.reason == "instant response routed to Iris/local fast path"
    fake_iris.recommend.assert_not_awaited()


async def test_high_confidence_iris_advisory_can_route_to_heavy_local(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
    reset_settings,
) -> None:
    monkeypatch.setattr(settings, "iris_router_enabled", True)
    monkeypatch.setattr(settings, "iris_router_advisory_enabled", True)
    fake_iris = _FakeIrisRouter(_iris_result(target="local_heavy", confidence=0.94, task="debug"))
    router.register_iris_router_client(fake_iris)
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "heavy"},
    }

    result = await router.execute(RouteRequest(prompt="Investigate this issue", provider="auto", task_type="chat"))

    assert result.decision.provider == "local_reasoning"
    assert result.decision.reason.startswith("iris classifier selected local_reasoning")
    assert result.runtime_evidence.classifier_provider == "iris_router"
    assert result.runtime_evidence.classifier_model == "qwen2.5:7b"
    assert result.runtime_evidence.classifier_confidence == 0.94
    assert result.runtime_evidence.classifier_latency_ms == 25
    assert result.runtime_evidence.classifier_target == "local_heavy"
    assert result.runtime_evidence.classifier_complexity == 2


async def test_low_confidence_iris_advisory_falls_back_to_deterministic_heuristics(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
    reset_settings,
) -> None:
    monkeypatch.setattr(settings, "iris_router_enabled", True)
    monkeypatch.setattr(settings, "iris_router_advisory_enabled", True)
    monkeypatch.setattr(settings, "iris_router_confidence_threshold", 0.8)
    fake_iris = _FakeIrisRouter(_iris_result(target="local_heavy", confidence=0.42, task="debug"))
    router.register_iris_router_client(fake_iris)
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "routine"},
    }

    result = await router.execute(RouteRequest(prompt="hello", provider="auto", task_type="chat"))

    assert result.decision.provider == "ollama"
    assert result.decision.reason == "instant response routed to Iris/local fast path"
    assert result.runtime_evidence.classifier_confidence == 0.42
    assert result.runtime_evidence.classifier_target == "local_heavy"


async def test_iris_advisory_cannot_send_classifier_sensitive_request_to_cloud(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
    reset_settings,
) -> None:
    monkeypatch.setattr(settings, "iris_router_enabled", True)
    monkeypatch.setattr(settings, "iris_router_advisory_enabled", True)
    _settings_with_allowlist(monkeypatch)
    fake_iris = _FakeIrisRouter(_iris_result(target="cloud", confidence=0.99, sensitivity="sensitive"))
    router.register_iris_router_client(fake_iris)
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "internal"},
    }

    result = await router.execute(RouteRequest(prompt="summarize this note", provider="auto", task_type="chat"))

    assert result.decision.provider == "local_reasoning"
    assert result.decision.privacy_classification == "sensitive"
    assert result.runtime_evidence.classifier_target == "cloud"
    router.openrouter_client.chat.assert_not_called()


async def test_high_confidence_iris_advisory_can_route_public_request_to_cloud(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
    reset_settings,
) -> None:
    monkeypatch.setattr(settings, "iris_router_enabled", True)
    monkeypatch.setattr(settings, "iris_router_advisory_enabled", True)
    _settings_with_allowlist(monkeypatch)
    fake_iris = _FakeIrisRouter(_iris_result(target="cloud", confidence=0.91, sensitivity="public"))
    router.register_iris_router_client(fake_iris)
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud",
    }

    result = await router.execute(RouteRequest(prompt="public reasoning task", provider="auto", privacy="public"))

    assert result.decision.provider == "openrouter"
    assert result.decision.reason.startswith("iris classifier selected cloud")
    assert result.runtime_evidence.classifier_target == "cloud"
    assert result.response == "cloud"


async def test_manual_cloud_override_when_cloud_disabled(router: Router, disable_cloud) -> None:
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "local fallback"},
    }

    req = RouteRequest(prompt="hi", provider="cloud")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert "Cloud routing is currently disabled" in (result.decision.limitation_notice or "")
    router.openrouter_client.chat.assert_not_called()


async def test_manual_cloud_override_hard_budget_reached(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "openrouter_allowlist", "openai/gpt-4o-mini")
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "local"},
    }

    req = RouteRequest(prompt="hi", provider="cloud")
    result = await router.execute(req, spent_this_month=30.0)

    assert result.decision.provider == "ollama"
    assert "hard budget reached" in result.decision.reason


async def test_routine_request_routes_to_vulcan_by_default(router: Router) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "ok"},
    }

    req = RouteRequest(prompt="Summarize this article", task_type="summarize")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.decision.reason == "auto default routed to Vulcan/local_reasoning"
    router.openrouter_client.chat.assert_not_called()


async def test_auto_route_ignores_connector_model_override_for_vulcan(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ollama_reasoning_model", "gpt-oss-freyja:20b-analysis-prefill")
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss-freyja:20b-analysis-prefill",
        "message": {"content": "vulcan"},
    }

    req = RouteRequest(prompt="Summarize this article", provider="auto", model="qwen2.5:7b")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.decision.model == "gpt-oss-freyja:20b-analysis-prefill"
    assert result.response == "vulcan"
    assert router.ollama_client.chat.await_args.kwargs["model"] == "gpt-oss-freyja:20b-analysis-prefill"


async def test_quick_acknowledgement_stays_fast_tier(router: Router, reset_settings) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "ok"},
    }

    req = RouteRequest(prompt="ok thanks", task_type="chat")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert result.decision.model == "qwen2.5:7b"
    assert result.decision.reason == "instant response routed to Iris/local fast path"
    assert result.response == "ok"


async def test_sensitive_request_routes_to_vulcan_when_reasoning_healthy(router: Router) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "ok"},
    }

    req = RouteRequest(prompt="My SSN is 123-45-6789")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.decision.privacy_classification == "sensitive"
    assert "healthy local_reasoning" in result.decision.reason


async def test_sensitive_request_fails_closed_when_reasoning_unhealthy(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.healthy.return_value = False
    router.openrouter_client.healthy.return_value = True

    req = RouteRequest(prompt="My SSN is 123-45-6789")
    result = await router.execute(req)

    assert result.decision.provider == "error"
    assert result.response == ""
    assert any(a["provider"] == "local_reasoning" and a["outcome"] == "unhealthy" for a in result.decision.fallback_attempts)
    assert "requires internal model" in result.decision.reason
    router.openrouter_client.chat.assert_not_called()
    assert any(
        a["provider"] == "local_reasoning" and a["outcome"] == "unhealthy"
        for a in result.runtime_evidence.fallback_events
    )


async def test_private_manual_cloud_override_routes_internal(router: Router) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "internal"},
    }

    req = RouteRequest(prompt="Use my private family context", provider="cloud", privacy="private")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert result.decision.privacy_classification == "private"
    assert "manual cloud override rejected" in result.decision.reason
    assert "privacy requires internal model" in result.decision.reason
    router.openrouter_client.chat.assert_not_called()


async def test_sensitive_complex_request_routes_internal_heavy(router: Router, reset_settings) -> None:
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "internal heavy"},
    }

    req = RouteRequest(prompt="Debug this private stack trace", task_type="debug", privacy="sensitive")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.decision.privacy_classification == "sensitive"
    assert result.decision.reason == "coding request routed to Vulcan orchestrator with Agent Smith/Qwen coding lane"
    router.openrouter_client.chat.assert_not_called()


async def test_coding_request_routes_to_vulcan_with_qwen_smith_lane(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ollama_coding_model", "qwen2.5-coder:14b-q3")
    monkeypatch.setattr(settings, "ollama_reasoning_model", "gpt-oss-freyja:20b-analysis-prefill")
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss-freyja:20b-analysis-prefill",
        "message": {"content": "patch"},
    }

    req = RouteRequest(prompt="Fix this failing pytest", provider="auto", task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.decision.model == "gpt-oss-freyja:20b-analysis-prefill"
    assert result.decision.reason == "coding request routed to Vulcan orchestrator with Agent Smith/Qwen coding lane"
    assert result.response == "patch"
    assert router.ollama_client.chat.await_args.kwargs["model"] == "gpt-oss-freyja:20b-analysis-prefill"
    prompt = router.ollama_client.chat.await_args.kwargs["prompt"]
    assert "BEGIN AGENT SMITH QWEN CODING LANE" in prompt
    assert "Orchestrator: Vulcan/local_reasoning (gpt-oss-freyja:20b-analysis-prefill)" in prompt
    assert "Worker target: Agent Smith/Qwen coder (qwen2.5-coder:14b-q3), agent_id=cloyd-gibbler" in prompt
    assert "smith_qwen_action" in prompt
    assert "approval_required=true" in prompt
    assert "Do not invent shell access" in prompt
    assert "qwen2.5-coder:14b-q3" in prompt
    router.openrouter_client.chat.assert_not_called()


async def test_heavy_local_default_model_comes_from_provider_profile(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
    reset_settings,
) -> None:
    monkeypatch.setattr(settings, "ollama_reasoning_model", "deepseek-r1:32b")
    router.ollama_client.chat.return_value = {
        "model": "deepseek-r1:32b",
        "message": {"content": "heavy"},
    }

    result = await router.execute(RouteRequest(prompt="Debug this stack trace", task_type="debug"))

    assert result.decision.provider == "local_reasoning"
    assert result.decision.model == "deepseek-r1:32b"


async def test_configured_heavy_local_profile_controls_router_model(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
    reset_settings,
) -> None:
    monkeypatch.setattr(
        settings,
        "inference_provider_profiles_json",
        """[
          {
            "provider_id": "heavy_local",
            "kind": "ollama",
            "base_url": "http://odin:11434",
            "model": "deepseek-r1:32b",
            "capabilities": ["chat", "reasoning", "coding"],
            "locality": "local_heavy",
            "tier": 3,
            "priority": 25,
            "enabled": true
          }
        ]""",
    )
    router.ollama_client.chat.return_value = {
        "model": "deepseek-r1:32b",
        "message": {"content": "heavy"},
    }

    result = await router.execute(RouteRequest(prompt="Debug this stack trace", task_type="debug"))

    assert result.decision.provider == "local_reasoning"
    assert result.decision.model == "deepseek-r1:32b"


async def test_local_reasoning_uses_dedicated_reasoning_client(router: Router, reset_settings) -> None:
    reasoning_client = AsyncMock()
    reasoning_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "heavy"},
    }
    router.register_reasoning_client(reasoning_client)

    req = RouteRequest(prompt="Debug this stack trace", task_type="debug")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.response == "heavy"
    reasoning_client.chat.assert_awaited_once()
    router.ollama_client.chat.assert_not_called()


async def test_runtime_evidence_records_connector_origin(router: Router) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "signal reply"},
    }
    principal = MemoryPrincipal(
        client_type="signal",
        client_subject="subject-hash",
        conversation_id="conversation-hash",
    )

    result = await router.execute(RouteRequest(prompt="hello", provider="local"), memory_principal=principal)

    assert result.runtime_evidence.connector_operations == [
        {
            "connector": "signal",
            "operation": "route",
            "success": True,
            "conversation_id": "conversation-hash",
        }
    ]


async def test_complex_coding_routes_local_reasoning(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.healthy.return_value = True
    router.openrouter_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "local reasoning"},
    }

    req = RouteRequest(prompt="Debug this stack trace and propose a patch", task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.decision.model == "gpt-oss:20b"
    assert result.decision.reason == "coding request routed to Vulcan orchestrator with Agent Smith/Qwen coding lane"
    assert result.response == "local reasoning"
    router.openrouter_client.chat.assert_not_called()


async def test_cloud_disabled_blocks_auto_cloud(router: Router, disable_cloud) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "local"},
    }

    big_prompt = "x" * 9000
    req = RouteRequest(prompt=big_prompt, task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.decision.model == settings.ollama_reasoning_model


async def test_soft_budget_reached_routes_local(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cloud_enabled", True)
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "local"},
    }

    big_prompt = "x" * 9000
    req = RouteRequest(prompt=big_prompt, task_type="coding")
    result = await router.execute(req, spent_this_month=20.0)

    assert result.decision.provider == "local_reasoning"
    assert result.decision.model == settings.ollama_reasoning_model


async def test_local_failure_does_not_fallback_to_cloud(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {"error": "Ollama down"}
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "unexpected cloud answer",
    }

    req = RouteRequest(prompt="Debug this bug and propose a patch", task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.response == ""
    assert any(a["provider"] == "local_reasoning" for a in result.decision.fallback_attempts)
    router.openrouter_client.chat.assert_not_called()


async def test_retry_exhaustion_stays_with_selected_vulcan_path(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.chat.return_value = {"error": "Ollama returned empty content", "status": "empty_content"}
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "unexpected cloud answer",
    }

    req = RouteRequest(prompt="Write code to fix this bug", task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.response == ""
    assert any(a["provider"] == "local_reasoning" for a in result.decision.fallback_attempts)
    router.openrouter_client.chat.assert_not_called()


async def test_cloud_failure_does_not_fallback_to_local(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.healthy.return_value = True
    router.openrouter_client.healthy.return_value = True
    router.openrouter_client.chat.return_value = {"error": "OpenRouter down"}
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "local fallback"},
    }

    big_prompt = "x" * 9000
    req = RouteRequest(prompt=big_prompt, provider="cloud")
    result = await router.execute(req)

    assert result.decision.provider == "openrouter"
    assert result.response == ""
    assert any(a["provider"] == "openrouter" for a in result.decision.fallback_attempts)
    router.ollama_client.chat.assert_not_called()


async def test_audit_reason_and_request_id(router: Router, reset_settings) -> None:
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "ok"},
    }

    req = RouteRequest(prompt="hi")
    result = await router.execute(req)

    assert result.decision.request_id
    assert result.decision.reason
    assert result.decision.privacy_classification in {"routine", "sensitive"}


async def test_native_tool_call_validated_and_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "chat_max_tool_iterations", 2)
    registry = ToolRegistry(audit_enabled=False)
    seen_arguments: list[dict[str, Any]] = []

    async def weather(request: ToolExecutionRequest) -> dict:
        seen_arguments.append(request.arguments)
        return {"summary": f"{request.arguments['unit']} in {request.arguments['location']}"}

    registry.register(
        ToolDefinition(
            name="get_weather",
            description="Weather",
            input_schema={
                "type": "object",
                "required": ["location", "unit"],
                "properties": {
                    "location": {"type": "string"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
            },
        ),
        weather,
    )
    r = Router(registry=registry)
    r.ollama_client = AsyncMock()
    r.openrouter_client = AsyncMock()
    r.ollama_client.chat.side_effect = [
        {
            "model": "gpt-oss:20b",
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_weather",
                            "arguments": {"location": "Boston", "unit": "F"},
                        }
                    }
                ],
            },
        },
        {
            "model": "gpt-oss:20b",
            "message": {"content": "It is fahrenheit in Boston."},
        },
    ]

    req = RouteRequest(
        prompt="What is the weather in Boston in Fahrenheit?",
        provider="local_reasoning",
        tools_required=True,
    )
    result = await r.execute(req)

    assert result.response == "It is fahrenheit in Boston."
    assert seen_arguments == [{"location": "Boston", "unit": "fahrenheit"}]
    first_call = r.ollama_client.chat.await_args_list[0].kwargs
    assert first_call["tools"]


async def test_tool_required_web_lookup_runs_search_before_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
    monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
    monkeypatch.setattr(settings, "chat_max_tool_output_chars", 2000)
    registry = ToolRegistry(audit_enabled=False)
    seen_arguments: list[dict[str, Any]] = []

    async def search(request: ToolExecutionRequest) -> dict:
        seen_arguments.append(request.arguments)
        return {
            "query": request.arguments["query"],
            "results": [
                {
                    "title": "OpenClaw Web Tools",
                    "url": "https://docs.openclaw.ai/tools/web",
                    "snippet": "OpenClaw supports web search and fetch tools.",
                }
            ],
        }

    registry.register(
        ToolDefinition(
            name="web_search",
            description="Search the web.",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 10},
                },
            },
        ),
        search,
    )
    r = Router(registry=registry)
    r.ollama_client = AsyncMock()
    r.openrouter_client = AsyncMock()
    r.ollama_client.healthy.return_value = True
    r.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "OpenClaw documents web tools at https://docs.openclaw.ai/tools/web."},
    }

    req = RouteRequest(
        prompt="Freyja, look up OpenClaw tools",
        provider="local",
        tools_required=True,
    )
    result = await r.execute(req)

    assert seen_arguments == [{"query": "OpenClaw tools", "max_results": 5}]
    assert result.response == "OpenClaw documents web tools at https://docs.openclaw.ai/tools/web."
    assert len(result.tool_results) == 1
    assert result.tool_results[0]["tool_name"] == "web_search"
    assert result.tool_results[0]["success"] is True
    chat_kwargs = r.ollama_client.chat.await_args.kwargs
    assert chat_kwargs["tools_required"] is False
    assert "BEGIN VERIFIED LIVE WEB SEARCH RESULTS" in chat_kwargs["prompt"]
    assert "https://docs.openclaw.ai/tools/web" in chat_kwargs["prompt"]


async def test_native_tool_call_invalid_arguments_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "chat_max_tool_iterations", 2)
    registry = ToolRegistry(audit_enabled=False)

    async def weather(request: ToolExecutionRequest) -> dict:
        return {}

    registry.register(
        ToolDefinition(
            name="get_weather",
            description="Weather",
            input_schema={
                "type": "object",
                "required": ["location", "unit"],
                "properties": {
                    "location": {"type": "string"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
                },
            },
        ),
        weather,
    )
    r = Router(registry=registry)
    r.ollama_client = AsyncMock()
    r.openrouter_client = AsyncMock()
    r.ollama_client.chat.side_effect = [
        {
            "model": "gpt-oss:20b",
            "message": {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_weather",
                            "arguments": {"location": "Boston", "unit": "kelvin"},
                        }
                    }
                ],
            },
        },
        {
            "model": "gpt-oss:20b",
            "message": {"content": "The weather tool rejected kelvin as an invalid unit."},
        },
    ]

    req = RouteRequest(
        prompt="What is the weather in Boston?",
        provider="local_reasoning",
        tools_required=True,
    )
    result = await r.execute(req)

    assert result.response == "The weather tool rejected kelvin as an invalid unit."
    assert result.tool_results[0]["error_code"] == "validation_error"
    assert result.runtime_evidence.tool_calls[0].name == "get_weather"
    assert result.runtime_evidence.tool_calls[0].success is False
    assert result.runtime_evidence.tool_calls[0].error == "validation_error"


async def test_logs_never_contain_api_keys(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.chat.return_value = {"error": "Authorization: Bearer secret-api-key"}
    router.openrouter_client.chat.return_value = {"error": "Authorization: Bearer secret-api-key"}

    req = RouteRequest(prompt="hi", task_type="coding")
    result = await router.execute(req)

    for attempt in result.decision.fallback_attempts:
        outcome = str(attempt.get("outcome", "")).lower()
        assert "api key" not in outcome
        assert "bearer" not in outcome
        assert "authorization" not in outcome


async def test_reason_describes_decision_not_provider_exception(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings_with_allowlist(monkeypatch)
    router.ollama_client.chat.return_value = {"error": "Authorization: Bearer sk-12345"}
    router.openrouter_client.chat.return_value = {"error": "Authorization: Bearer sk-cloud-67890"}

    req = RouteRequest(prompt="hi", task_type="coding")
    result = await router.execute(req)

    assert not result.response
    assert result.decision.public_error_message == "Local model provider is unavailable."
    reason = result.decision.reason.lower()
    assert "bearer" not in reason
    assert "authorization" not in reason
    assert "sk-" not in reason


async def test_tools_required_auto_stays_with_vulcan_when_local_errors(
    router: Router,
    reset_settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _settings_with_allowlist(monkeypatch)
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
    router.ollama_client.chat.return_value = {"error": "All connection attempts failed"}
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud answer",
    }

    req = RouteRequest(prompt="say hello", provider="auto", tools_required=True)
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.response == ""
    assert result.decision.fallback_attempts == [
        {"provider": "local_reasoning", "outcome": "All connection attempts failed"},
    ]
    router.openrouter_client.chat.assert_not_called()


async def test_weather_routes_to_local_reasoning_when_tool_enabled(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "weather_tool_enabled", True)
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "Vulcan-handled enabled weather response."},
    }

    req = RouteRequest(
        prompt="What's the weather for Xmas this year?",
        provider="auto",
        tools_required=True,
    )
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert "local_reasoning preferred" in result.decision.reason
    assert result.response == "Vulcan-handled enabled weather response."
    router.ollama_client.chat.assert_awaited_once()
    router.openrouter_client.chat.assert_not_awaited()


async def test_weather_without_tools_required_routes_to_local_reasoning_when_tool_enabled(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "weather_tool_enabled", True)
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "Vulcan-handled normal weather response."},
    }

    req = RouteRequest(
        prompt="What's the weather tomorrow in Aiken, SC?",
        provider="auto",
        tools_required=False,
    )
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.response == "Vulcan-handled normal weather response."
    router.ollama_client.chat.assert_awaited_once()
    router.openrouter_client.chat.assert_not_awaited()


async def test_weather_adds_live_observation_for_vulcan_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "weather_tool_enabled", True)
    observed: dict[str, Any] = {}

    async def weather(
        location: str,
        *,
        request_type: str,
        target_date: Any = None,
        target_label: str = "",
    ) -> dict:
        observed["location"] = location
        observed["request_type"] = request_type
        return {
            "live_data_available": True,
            "location": location,
            "request_type": request_type,
            "target_label": target_label,
            "summary": "Sunny",
            "temperature_f": 76,
        }

    monkeypatch.setattr("freyja.router.get_weather", weather)
    r = Router()
    r.ollama_client = AsyncMock()
    r.openrouter_client = AsyncMock()
    r.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "Tomorrow in Aiken looks sunny."},
    }

    req = RouteRequest(
        prompt="What's the weather tomorrow in Aiken, SC?",
        provider="auto",
        tools_required=False,
    )
    result = await r.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.response == "Tomorrow in Aiken looks sunny."
    assert observed["location"] == "Aiken, SC"
    assert observed["request_type"] == "forecast"
    first_prompt = r.ollama_client.chat.await_args.kwargs["prompt"]
    assert "BEGIN VERIFIED LIVE WEATHER OBSERVATION" in first_prompt
    assert "Sunny" in first_prompt


async def test_next_weekend_weather_adds_live_observation_with_default_location(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "weather_tool_enabled", True)
    monkeypatch.setattr(settings, "home_assistant_location_name", "Atlanta")
    observed: dict[str, Any] = {}

    async def weather(
        location: str,
        *,
        request_type: str,
        target_date: Any = None,
        target_label: str = "",
    ) -> dict:
        observed["location"] = location
        observed["request_type"] = request_type
        observed["target_label"] = target_label
        return {
            "live_data_available": True,
            "location": location,
            "request_type": request_type,
            "target_label": target_label,
            "summary": "Warm weekend forecast",
            "high_f": 84,
        }

    monkeypatch.setattr("freyja.router.get_weather", weather)
    r = Router()
    r.ollama_client = AsyncMock()
    r.openrouter_client = AsyncMock()
    r.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "Next weekend in Atlanta looks warm."},
    }

    req = RouteRequest(
        prompt="What's the weather next weekend?",
        provider="auto",
        tools_required=False,
    )
    result = await r.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.response == "Next weekend in Atlanta looks warm."
    assert observed["location"] == "Atlanta"
    assert observed["request_type"] == "forecast"
    assert observed["target_label"] == "next weekend"
    first_prompt = r.ollama_client.chat.await_args.kwargs["prompt"]
    assert "BEGIN VERIFIED LIVE WEATHER OBSERVATION" in first_prompt
    assert "Warm weekend forecast" in first_prompt


async def test_weather_routes_to_local_reasoning_when_tool_disabled(
    router: Router,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "weather_tool_enabled", False)
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "Vulcan-handled weather response."},
    }

    req = RouteRequest(
        prompt="What's the weather tomorrow in Aiken, SC?",
        provider="auto",
        tools_required=False,
    )
    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.decision.model
    assert "local_reasoning preferred" in result.decision.reason
    assert result.response == "Vulcan-handled weather response."
    router.ollama_client.chat.assert_awaited_once()
    router.openrouter_client.chat.assert_not_awaited()


async def test_coding_request_does_not_take_memory_shortcut(router: Router, reset_settings) -> None:
    router.ollama_client.chat.return_value = {
        "model": "gpt-oss:20b",
        "message": {"content": "local coding"},
    }
    prompt = (
        "CLOYD LOCAL CODER MODE: Use memory-scoped context only as provided. "
        "Cloyd, code: inspect Freyja-OS, report the current commit, run the tests, "
        "and show me any failures. Do not modify files."
    )
    req = RouteRequest(
        prompt=prompt,
        provider="local_reasoning",
        task_type="coding",
        tools_required=True,
        privacy="private",
    )

    result = await router.execute(req)

    assert result.decision.provider == "local_reasoning"
    assert result.response == "local coding"


def test_approved_allowlist_empty(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_ALLOWLIST", raising=False)
    s = Settings(_env_file=None)
    assert s.approved_openrouter_models == []


def test_approved_allowlist_parsing() -> None:
    s = Settings(OPENROUTER_ALLOWLIST="a/b, c/d ,", _env_file=None)
    assert s.approved_openrouter_models == ["a/b", "c/d"]


def test_approved_allowlist_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_ALLOWLIST", "openai/gpt-4o-mini,anthropic/claude-3.5-haiku")
    s = Settings()
    assert s.approved_openrouter_models == ["openai/gpt-4o-mini", "anthropic/claude-3.5-haiku"]


async def test_sub_3b_model_blocked_for_chat(router: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_chat_model", "qwen2.5:7b")
    monkeypatch.setattr(settings, "ollama_classification_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:7b",
        "message": {"content": "seven-bee"},
    }

    req = RouteRequest(prompt="hi")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert "qwen2.5:7b" in result.decision.model
    router.ollama_client.chat.assert_awaited_once()
    _, kwargs = router.ollama_client.chat.call_args
    assert "qwen2.5:1.5b" not in kwargs.get("model", "")


async def test_local_default_model_comes_from_provider_profile(router: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_chat_model", "qwen2.5:14b")
    monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:14b",
        "message": {"content": "profile model"},
    }

    result = await router.execute(RouteRequest(prompt="hello", provider="local"))

    assert result.decision.provider == "ollama"
    assert result.decision.model == "qwen2.5:14b"
    _, kwargs = router.ollama_client.chat.call_args
    assert kwargs["model"] == "qwen2.5:14b"


async def test_1_5b_model_allowed_for_classification_only(router: Router, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_chat_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_classification_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
    router.ollama_client.healthy.return_value = True
    router.ollama_client.chat.return_value = {
        "model": "qwen2.5:1.5b",
        "message": {"content": "classified"},
    }

    req = RouteRequest(prompt="hi", provider="local", model="qwen2.5:1.5b")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert result.decision.model == "qwen2.5:1.5b"


async def test_auto_local_chat_avoids_sub_3b_without_cloud_fallback(router: Router, reset_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ollama_model", "qwen2.5:1.5b")
    monkeypatch.setattr(settings, "ollama_chat_model", "qwen2.5:7b")
    monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
    monkeypatch.setattr(settings, "openrouter_allowlist", "openai/gpt-4o-mini")
    router.ollama_client.chat.return_value = {"error": "Ollama down"}
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud hello",
    }

    req = RouteRequest(prompt="hello", task_type="coding")
    result = await router.execute(req)

    assert result.decision.provider == "ollama"
    assert result.decision.model == "qwen2.5:7b"
    assert result.response == ""
    router.openrouter_client.chat.assert_not_called()


async def test_auto_image_request_routes_to_local_vision_without_cloud(router: Router, reset_settings) -> None:
    settings.cloud_enabled = False
    router.ollama_client.chat.return_value = {
        "model": "moondream",
        "message": {"content": "red"},
    }
    router.openrouter_client.chat.return_value = {
        "model": "openai/gpt-4o-mini",
        "response": "cloud red",
    }

    req = RouteRequest(
        prompt="What color is this image?",
        provider="auto",
        images=[ImageInput(mime_type="image/png", data_base64="ZmFrZQ==")],
    )
    result = await router.execute(req)

    assert result.decision.provider == "local_vision"
    assert result.decision.model == "moondream"
    assert result.response == "red"
    router.openrouter_client.chat.assert_not_called()
    _, kwargs = router.ollama_client.chat.call_args
    assert kwargs["images"] == req.images
    assert result.runtime_evidence.provider_profile_id == "local_vision"
    assert result.runtime_evidence.provider_locality == "iris"


async def test_image_tool_request_passes_tools_to_local_vision(router: Router, reset_settings) -> None:
    settings.cloud_enabled = False
    registry = ToolRegistry(audit_enabled=False)
    register_builtin_tools(registry)
    router = Router(registry=registry)
    router.ollama_client = AsyncMock()
    router.openrouter_client = AsyncMock()
    router.ollama_client.chat.return_value = {
        "model": "moondream",
        "message": {"content": "I need live context, but no tool was used."},
    }

    req = RouteRequest(
        prompt="Look at this flyer and tell me the weather for the event.",
        provider="auto",
        tools_required=True,
        images=[ImageInput(mime_type="image/png", data_base64="ZmFrZQ==")],
    )
    result = await router.execute(req)

    assert result.decision.provider == "local_vision"
    _, kwargs = router.ollama_client.chat.call_args
    assert kwargs["tools_required"] is True
    assert kwargs["images"] == req.images
    assert {tool.name for tool in kwargs["tools"]} >= {"web_search", "get_weather", "event_weather"}


class TestToolLoop:
    @pytest.fixture
    def registry(self) -> ToolRegistry:
        r = ToolRegistry(audit_enabled=False)
        register_builtin_tools(r)
        return r

    @pytest.fixture
    def router(self, registry: ToolRegistry) -> Router:
        r = Router(registry=registry)
        r.ollama_client = AsyncMock()
        r.openrouter_client = AsyncMock()
        return r

    @pytest.fixture(autouse=True)
    def _enable_tool_loop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "chat_max_tool_iterations", 3)

    def _tool_call(self, name: str, arguments: dict[str, Any] | None = None) -> str:
        args = arguments or {}
        return f'<freyja_tool_call>{{"tool_name":"{name}","arguments":{json.dumps(args)}}}</freyja_tool_call>'

    async def test_successful_single_tool_request_local(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True

        calls: list[int] = []

        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(1)
            if len(calls) == 1:
                return {"model": "qwen2.5:7b", "message": {"content": self._tool_call("hostname")}}
            return {"model": "qwen2.5:7b", "message": {"content": "The host is Iris."}}

        router.ollama_client.chat.side_effect = _respond
        req = RouteRequest(prompt="What host am I on?", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.decision.provider == "ollama"
        assert "Iris" in result.response or "iris" in result.response.lower()
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool_name"] == "hostname"
        assert result.tool_results[0]["success"] is True
        assert result.tool_results[0]["duration_ms"] is not None
        assert result.runtime_evidence.tool_calls[0].name == "hostname"
        assert result.runtime_evidence.tool_calls[0].success is True

    async def test_home_assistant_read_slice_is_director_authorized_deterministic(
        self,
        router: Router,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "home_assistant_state_fixture", '{"light.downstairs":"on"}')
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": "model should not run"},
        }
        principal = MemoryPrincipal(
            client_type="imessage",
            client_subject="family-member:abc",
            conversation_id="imessage-conv:test",
        )

        result = await router.execute(
            RouteRequest(
                request_id="req-home-read",
                prompt="Are the downstairs lights on?",
                provider="auto",
                tools_required=True,
                include_trace=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
        )

        assert result.decision.request_id == "req-home-read"
        assert result.decision.provider == "deterministic"
        assert result.response == "Yes, the downstairs lights are on."
        assert result.tool_results[0]["tool_name"] == "home_assistant_read_state"
        assert result.tool_results[0]["success"] is True
        assert result.runtime_evidence.interface == "imessage"
        assert result.runtime_evidence.person == {"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"}
        assert len(result.runtime_evidence.capability_authorizations) == 1
        _assert_authorization_record(
            result.runtime_evidence.capability_authorizations[0],
            {
                "capability": "home_assistant_read_state",
                "allowed": True,
                "reason": "principal joe may read household state",
                "required_permission": "household:home.read",
                "connector": "imessage",
                "person_id": "joe",
            },
        )
        router.ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_home_assistant_read_slice_survives_inference_outages(
        self,
        router: Router,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "home_assistant_state_fixture", '{"light.downstairs":"on"}')
        router.ollama_client.healthy.return_value = False
        router.reasoning_ollama_client = AsyncMock()
        router.reasoning_ollama_client.healthy.return_value = False
        router.openrouter_client.healthy.return_value = False
        principal = MemoryPrincipal(client_type="signal", client_subject="family-member:abc")

        result = await router.execute(
            RouteRequest(prompt="Are the downstairs lights on?", provider="auto", tools_required=True),
            memory_principal=principal,
            person_context={"person_id": "joe"},
        )

        assert result.decision.provider == "deterministic"
        assert result.response == "Yes, the downstairs lights are on."
        router.ollama_client.chat.assert_not_called()
        router.reasoning_ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_home_assistant_sensor_inventory_is_director_authorized_deterministic(
        self,
        router: Router,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            settings,
            "home_assistant_state_fixture",
            '{"sensor.kitchen_temperature":"72","sensor.front_door_battery":"88","light.downstairs":"on"}',
        )
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": "model should not run"},
        }
        principal = MemoryPrincipal(
            client_type="imessage",
            client_subject="family-member:abc",
            conversation_id="imessage-conv:test",
        )

        result = await router.execute(
            RouteRequest(
                request_id="req-home-sensors",
                prompt="What sensors can you see in Home Assistant?",
                provider="auto",
                tools_required=True,
                include_trace=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
        )

        assert result.decision.request_id == "req-home-sensors"
        assert result.decision.provider == "deterministic"
        assert result.tool_results[0]["tool_name"] == "home_assistant_list_states"
        assert result.tool_results[0]["success"] is True
        assert result.tool_results[0]["output"]["count"] == 2
        assert "kitchen_temperature" in result.response
        assert len(result.runtime_evidence.capability_authorizations) == 1
        _assert_authorization_record(
            result.runtime_evidence.capability_authorizations[0],
            {
                "capability": "home_assistant_list_states",
                "allowed": True,
                "reason": "principal joe may read household state",
                "required_permission": "household:home.read",
                "connector": "imessage",
                "person_id": "joe",
            },
        )
        router.ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_home_assistant_inventory_changes_route_reports_new_devices(
        self,
        router: Router,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        monkeypatch.setattr(settings, "home_assistant_inventory_snapshot_path", str(tmp_path / "ha-inventory.json"))
        monkeypatch.setattr(settings, "home_assistant_state_fixture", '{"light.downstairs":"on"}')
        principal = MemoryPrincipal(client_type="imessage", client_subject="family-member:abc")
        await router.execute(
            RouteRequest(
                prompt="Have any Home Assistant devices changed?",
                provider="auto",
                tools_required=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe"},
        )

        monkeypatch.setattr(
            settings,
            "home_assistant_state_fixture",
            '{"light.downstairs":"on","sensor.front_door_battery":"88"}',
        )
        result = await router.execute(
            RouteRequest(
                request_id="req-ha-changes",
                prompt="Have any new Home Assistant devices been added?",
                provider="auto",
                tools_required=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe"},
        )

        assert result.decision.provider == "deterministic"
        assert result.tool_results[0]["tool_name"] == "home_assistant_inventory_changes"
        assert result.tool_results[0]["output"]["added"][0]["entity_id"] == "sensor.front_door_battery"
        assert "sensor.front_door_battery" in result.response
        router.ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_home_assistant_read_slice_denies_unknown_principal(self, router: Router) -> None:
        principal = MemoryPrincipal(client_type="signal", client_subject="family-member:abc")

        result = await router.execute(
            RouteRequest(prompt="Are the downstairs lights on?", provider="auto", tools_required=True),
            memory_principal=principal,
            person_context={"person_id": "unknown"},
        )

        assert result.decision.provider == "deterministic"
        assert result.tool_results[0]["error_code"] == "authorization_denied"
        assert "can't read household state" in result.response

    async def test_home_assistant_control_slice_requires_explicit_approval(self, router: Router) -> None:
        principal = MemoryPrincipal(client_type="imessage", client_subject="family-member:abc")

        result = await router.execute(
            RouteRequest(
                request_id="req-home-control",
                prompt="Turn off the downstairs lights.",
                provider="auto",
                tools_required=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
        )

        assert result.decision.provider == "deterministic"
        assert result.decision.reason == "deterministic Home Assistant control capability"
        assert result.tool_results[0]["tool_name"] == "home_assistant_control_state"
        assert result.tool_results[0]["success"] is False
        assert result.tool_results[0]["error_code"] == "authorization_denied"
        assert len(result.runtime_evidence.capability_authorizations) == 1
        _assert_authorization_record(
            result.runtime_evidence.capability_authorizations[0],
            {
                "capability": "home_assistant_control_state",
                "allowed": False,
                "reason": "explicit approval required for household control",
                "required_permission": "household:home.control",
                "connector": "imessage",
                "person_id": "joe",
                "approval_granted": False,
            },
        )
        authorization = result.runtime_evidence.capability_authorizations[0]
        assert authorization["risk_level"] == "controlled_write"
        assert authorization["confirmation_policy"] == "operator_approval_required"
        assert authorization["connector_trusted"] is True
        assert authorization["principal_subject_present"] is True
        assert authorization["target_scope"] == "household:home.control"
        assert "explicit approval" in result.response
        router.ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_calendar_read_slice_is_director_authorized_deterministic(self, router: Router) -> None:
        principal = MemoryPrincipal(
            client_type="imessage",
            client_subject="family-member:abc",
            conversation_id="imessage-conv:test",
        )

        result = await router.execute(
            RouteRequest(
                request_id="req-calendar-read",
                prompt="What is on my calendar today?",
                provider="auto",
                tools_required=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
        )

        assert result.decision.request_id == "req-calendar-read"
        assert result.decision.provider == "deterministic"
        assert result.decision.reason == "deterministic calendar read capability"
        assert result.tool_results[0]["tool_name"] == "calendar_today_schedule"
        assert result.tool_results[0]["success"] is True
        assert len(result.runtime_evidence.capability_authorizations) == 1
        _assert_authorization_record(
            result.runtime_evidence.capability_authorizations[0],
            {
                "capability": "calendar_today_schedule",
                "allowed": True,
                "reason": "principal joe may read household calendar",
                "required_permission": "household:calendar.read",
                "connector": "imessage",
                "person_id": "joe",
            },
        )
        router.ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_calendar_read_slice_survives_inference_outages(self, router: Router) -> None:
        router.ollama_client.healthy.return_value = False
        router.reasoning_ollama_client = AsyncMock()
        router.reasoning_ollama_client.healthy.return_value = False
        router.openrouter_client.healthy.return_value = False
        principal = MemoryPrincipal(client_type="signal", client_subject="family-member:abc")

        result = await router.execute(
            RouteRequest(prompt="What is on my calendar today?", provider="auto", tools_required=True),
            memory_principal=principal,
            person_context={"person_id": "joe"},
        )

        assert result.decision.provider == "deterministic"
        assert "calendar" in result.response.lower()
        router.ollama_client.chat.assert_not_called()
        router.reasoning_ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_calendar_read_slice_denies_unknown_principal(self, router: Router) -> None:
        principal = MemoryPrincipal(client_type="signal", client_subject="family-member:abc")

        result = await router.execute(
            RouteRequest(prompt="What is on my calendar today?", provider="auto", tools_required=True),
            memory_principal=principal,
            person_context={"person_id": "unknown"},
        )

        assert result.decision.provider == "deterministic"
        assert result.tool_results[0]["error_code"] == "authorization_denied"
        assert "can't read calendar state" in result.response

    async def test_memory_read_slice_is_director_authorized_deterministic(
        self,
        router: Router,
        isolated_memory_store,
    ) -> None:
        principal = MemoryPrincipal(
            client_type="imessage",
            client_subject="family-member:abc",
            conversation_id="imessage-conv:test",
        )
        isolated_memory_store.put_shared_memory(
            principal,
            PutSharedMemoryRequest(
                memory_id="calendar-pref",
                kind="preference",
                content="Joe prefers morning calendar events.",
                source="test",
                metadata={"domain": "calendar"},
            ),
        )

        result = await router.execute(
            RouteRequest(
                request_id="req-memory-read",
                prompt="What do you remember about my preferences?",
                provider="auto",
                tools_required=True,
            ),
            memory_principal=principal,
            person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
        )

        assert result.decision.request_id == "req-memory-read"
        assert result.decision.provider == "deterministic"
        assert result.tool_results[0]["tool_name"] == "memory_recall_shared"
        assert result.tool_results[0]["success"] is True
        assert "Joe prefers morning calendar events." in result.response
        assert len(result.runtime_evidence.capability_authorizations) == 1
        _assert_authorization_record(
            result.runtime_evidence.capability_authorizations[0],
            {
                "capability": "memory_recall_shared",
                "allowed": True,
                "reason": "Director-authorized principal may read scoped memory",
                "required_permission": "personal:memory.read",
                "connector": "imessage",
                "person_id": "joe",
            },
        )
        assert result.runtime_evidence.memory_lookups[0]["operation"] == "shared_capability_recall"
        router.ollama_client.chat.assert_not_called()
        router.openrouter_client.chat.assert_not_called()

    async def test_memory_read_slice_denies_unknown_principal(self, router: Router) -> None:
        principal = MemoryPrincipal(client_type="signal", client_subject="family-member:abc")

        result = await router.execute(
            RouteRequest(prompt="What do you remember about my preferences?", provider="auto", tools_required=True),
            memory_principal=principal,
            person_context={"person_id": "unknown"},
        )

        assert result.decision.provider == "deterministic"
        assert result.tool_results[0]["error_code"] == "authorization_denied"
        assert "can't read memory" in result.response

    async def test_tool_request_receives_resolved_person_context(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        captured: dict[str, Any] = {}

        async def _capture_person(request: ToolExecutionRequest) -> dict[str, Any]:
            captured.update(request.metadata)
            return {"ok": True}

        registry.register(
            ToolDefinition(name="capture_person", description="Capture person metadata."),
            _capture_person,
        )

        calls: list[int] = []

        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(1)
            if len(calls) == 1:
                return {"model": "qwen2.5:7b", "message": {"content": self._tool_call("capture_person")}}
            return {"model": "qwen2.5:7b", "message": {"content": "done"}}

        router.ollama_client.chat.side_effect = _respond
        principal = MemoryPrincipal(client_type="signal", client_subject="family-member:abc")
        result = await router.execute(
            RouteRequest(prompt="Use a tool.", provider="local", tools_required=True),
            memory_principal=principal,
            person_context={"person_id": "joe", "display_name": "Joe", "preferred_name": "Joe"},
        )

        assert result.response == "done"
        assert captured["person"]["person_id"] == "joe"
        assert captured["memory_principal"]["client_subject"] == "family-member:abc"

    async def test_tool_failure_returns_honest_error(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True

        async def _flaky_tool(request: Any) -> dict[str, Any]:
            raise RuntimeError("disk is gone")

        registry.unregister("disk_usage")
        registry.register(
            ToolDefinition(
                name="disk_usage",
                description="Flaky disk usage for testing.",
                input_schema={"type": "object", "properties": {}},
                risk_level=registry.get_tool("disk_usage").risk_level if registry.get_tool("disk_usage") else "read_only",
            ),
            _flaky_tool,
        )

        router.ollama_client.chat.side_effect = [
            {
                "model": "qwen2.5:7b",
                "message": {"content": self._tool_call("disk_usage")},
            },
            {
                "model": "qwen2.5:7b",
                "message": {"content": "The disk usage tool failed, so I cannot verify disk usage from the tool result."},
            },
        ]

        req = RouteRequest(prompt="Check disk usage.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.tool_results[0]["tool_name"] == "disk_usage"
        assert result.tool_results[0]["success"] is False
        assert result.tool_results[0]["error_code"] == "tool_error"
        assert "failed" in result.response.lower()
        assert router.ollama_client.chat.await_count == 2

    async def test_invalid_arguments_rejected(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        router.ollama_client.chat.side_effect = [
            {
                "model": "qwen2.5:7b",
                "message": {
                    "content": self._tool_call("disk_usage", {"path": 123})
                },
            },
            {
                "model": "qwen2.5:7b",
                "message": {"content": "The disk usage tool rejected the path argument."},
            },
        ]

        req = RouteRequest(prompt="Check disk usage.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool_name"] == "disk_usage"
        assert result.tool_results[0]["success"] is False
        assert result.tool_results[0]["error_code"] == "validation_error"
        assert result.response == "The disk usage tool rejected the path argument."

    async def test_coding_tool_aliases_are_normalized(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        calls: list[int] = []

        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(1)
            if len(calls) == 1:
                return {"model": "qwen2.5:7b", "message": {"content": self._tool_call("inspect_freyja_os")}}
            return {"model": "qwen2.5:7b", "message": {"content": "inspected"}}

        router.ollama_client.chat.side_effect = _respond
        req = RouteRequest(
            prompt="Cloyd, code: inspect Freyja-OS",
            provider="local",
            task_type="coding",
            tools_required=True,
        )
        result = await router.execute(req)

        assert result.response == "inspected"
        assert result.tool_results[0]["tool_name"] == "repository_status"
        assert result.runtime_evidence.tool_calls[0].name == "repository_status"


    async def test_unknown_tool_rejected(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        router.ollama_client.chat.side_effect = [
            {
                "model": "qwen2.5:7b",
                "message": {"content": self._tool_call("nonexistent_tool")},
            },
            {
                "model": "qwen2.5:7b",
                "message": {"content": "That requested tool is not available."},
            },
        ]

        req = RouteRequest(prompt="Do something weird.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.tool_results[0]["tool_name"] == "nonexistent_tool"
        assert result.tool_results[0]["success"] is False
        assert result.tool_results[0]["error_code"] == "tool_not_found"
        assert result.response == "That requested tool is not available."

    async def test_tool_evidence_redacts_sensitive_arguments(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": self._tool_call("unknown_secret_tool", {"token": "sk-test", "query": "safe"})},
        }

        req = RouteRequest(prompt="Use a missing tool.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.runtime_evidence.tool_calls[0].name == "unknown_secret_tool"
        assert result.runtime_evidence.tool_calls[0].arguments == {"token": "<redacted>", "query": "safe"}

    async def test_iteration_limit_exhaustion(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        monkeypatch.setattr(settings, "chat_max_tool_iterations", 2)
        router.ollama_client.healthy.return_value = True
        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            if kwargs.get("tools_required") is False:
                return {"model": "qwen2.5:7b", "message": {"content": "I reached the tool iteration limit and will answer from the gathered results."}}
            return {
                "model": "qwen2.5:7b",
                "message": {"content": self._tool_call("hostname")},
            }

        router.ollama_client.chat.side_effect = _respond

        req = RouteRequest(prompt="Keep asking tools.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert len(result.tool_results) == 2
        assert all(entry["tool_name"] == "hostname" for entry in result.tool_results)
        assert "iteration limit" in result.response.lower()

    async def test_normal_response_no_tool(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": "Just a regular answer."},
        }

        req = RouteRequest(prompt="Say hi.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.response == "Just a regular answer."
        assert result.tool_results == []

    async def test_tool_loop_openrouter_path(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "openrouter_allowlist", "openai/gpt-4o-mini")
        monkeypatch.setattr(settings, "cloud_enabled", True)
        router.ollama_client.healthy.return_value = False
        router.openrouter_client.healthy.return_value = True

        calls: list[int] = []

        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(1)
            if len(calls) == 1:
                return {"model": "openai/gpt-4o-mini", "response": self._tool_call("current_time")}
            return {"model": "openai/gpt-4o-mini", "response": "The time is now."}

        router.openrouter_client.chat.side_effect = _respond
        req = RouteRequest(prompt="What time is it?", provider="cloud", tools_required=True)
        result = await router.execute(req)

        assert result.decision.provider == "openrouter"
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool_name"] == "current_time"
        assert result.tool_results[0]["success"] is True

    async def test_oversized_tool_output_is_truncated(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        monkeypatch.setattr(settings, "chat_max_tool_output_chars", 50)
        router.ollama_client.healthy.return_value = True

        async def _big_output(request: Any) -> dict[str, Any]:
            return {"data": "x" * 1000}

        registry.unregister("hostname")
        registry.register(
            ToolDefinition(
                name="hostname",
                description="Big output test.",
                input_schema={"type": "object", "properties": {}},
            ),
            _big_output,
        )

        calls: list[int] = []

        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(1)
            if len(calls) == 1:
                return {"model": "qwen2.5:7b", "message": {"content": self._tool_call("hostname")}}
            return {"model": "qwen2.5:7b", "message": {"content": "Got it."}}

        router.ollama_client.chat.side_effect = _respond
        req = RouteRequest(prompt="Show me big data.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.response == "Got it."
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["success"] is True
        second_call_prompt = router.ollama_client.chat.call_args_list[1][1]["prompt"]
        assert '"truncated": true' in second_call_prompt.lower()

    async def test_malformed_marker_is_stripped(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True
        router.ollama_client.chat.return_value = {
            "model": "qwen2.5:7b",
            "message": {"content": "I think <freyja_tool_call>not valid json</freyja_tool_call> is the answer."},
        }

        req = RouteRequest(prompt="What is the answer?", provider="local", tools_required=True)
        result = await router.execute(req)

        assert "<freyja_tool_call>" not in result.response
        assert result.tool_results == []

    async def test_multiple_markers_use_first(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True

        calls: list[int] = []

        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            calls.append(1)
            if len(calls) == 1:
                return {
                    "model": "qwen2.5:7b",
                    "message": {
                        "content": (
                            self._tool_call("hostname") + " " + self._tool_call("current_time")
                        )
                    },
                }
            return {"model": "qwen2.5:7b", "message": {"content": "Used hostname only."}}

        router.ollama_client.chat.side_effect = _respond
        req = RouteRequest(prompt="Ask two tools.", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.response == "Used hostname only."
        assert len(result.tool_results) == 1
        assert result.tool_results[0]["tool_name"] == "hostname"

    @pytest.mark.parametrize("iterations", [0, -1, 1000])
    async def test_iteration_config_boundaries(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry, iterations: int) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        monkeypatch.setattr(settings, "chat_max_tool_iterations", iterations)
        router.ollama_client.healthy.return_value = True
        async def _respond(prompt: str, **kwargs: Any) -> dict[str, Any]:
            if kwargs.get("tools_required") is False:
                return {"model": "qwen2.5:7b", "message": {"content": "I reached the tool iteration limit."}}
            return {
                "model": "qwen2.5:7b",
                "message": {"content": self._tool_call("hostname")},
            }

        router.ollama_client.chat.side_effect = _respond

        req = RouteRequest(prompt="Loop.", provider="local", tools_required=True)
        result = await router.execute(req)

        if iterations <= 0:
            assert len(result.tool_results) == 1
            assert "iteration limit" in result.response.lower()
        else:
            # Hard upper cap of 50 prevents 1000 actual iterations.
            assert len(result.tool_results) <= 50
            assert "iteration limit" in result.response.lower()

    async def test_tool_failure_grounds_final_answer(self, router: Router, monkeypatch: pytest.MonkeyPatch, registry: ToolRegistry) -> None:
        monkeypatch.setattr(settings, "ollama_model", "qwen2.5:7b")
        monkeypatch.setattr(settings, "ollama_min_chat_parameters_b", 3)
        router.ollama_client.healthy.return_value = True

        async def _failing_tool(request: Any) -> dict[str, Any]:
            raise RuntimeError("sensor offline")

        registry.unregister("hostname")
        registry.register(
            ToolDefinition(
                name="hostname",
                description="Failing tool for grounding test.",
                input_schema={"type": "object", "properties": {}},
            ),
            _failing_tool,
        )

        router.ollama_client.chat.side_effect = [
            {
                "model": "qwen2.5:7b",
                "message": {"content": self._tool_call("hostname")},
            },
            {
                "model": "qwen2.5:7b",
                "message": {"content": "The hostname tool failed, so I cannot verify the host from that tool result."},
            },
        ]

        req = RouteRequest(prompt="What host?", provider="local", tools_required=True)
        result = await router.execute(req)

        assert result.tool_results[0]["success"] is False
        assert "failed" in result.response.lower()
        assert "succeeded" not in result.response.lower()
        assert "success" not in result.response.lower()
