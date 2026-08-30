import os

import freyja.agent_runtime_v3
from freyja.agent_gateway import AgentGateway, GatewayRequest
from freyja.agent_runtime_v3 import AgentRuntimeV3, _openai_compatible_api_key, _openai_compatible_base_url
from freyja.config import Settings
from freyja.foundation_models import GatewaySender, InferenceEndpoint, SecurityDomainId
from freyja.inference_registry_v3 import InferenceRegistryV3


def test_settings_expose_nexus_gateway_without_secret_default() -> None:
    config = Settings(nexus_base_url="http://100.94.80.21:3939")

    assert config.nexus_base_url == "http://100.94.80.21:3939"
    assert config.nexus_api_key == ""


def test_nexus_provider_uses_nexus_token_not_litellm_key(monkeypatch) -> None:
    monkeypatch.setattr("freyja.agent_runtime_v3.settings.nexus_base_url", "http://nexus.test:3939")
    monkeypatch.setattr("freyja.agent_runtime_v3.settings.nexus_api_key", "settings-token")
    monkeypatch.setattr("freyja.agent_runtime_v3.settings.litellm_master_key", "litellm-token")
    monkeypatch.delenv("NEXUS_API_KEY", raising=False)
    monkeypatch.setenv("LITELLM_MASTER_KEY", "litellm-env-token")

    assert _openai_compatible_base_url("nexus") == "http://nexus.test:3939"
    assert _openai_compatible_api_key("nexus") == "settings-token"

    monkeypatch.setenv("NEXUS_API_KEY", "nexus-env-token")

    assert _openai_compatible_api_key("nexus") == "nexus-env-token"
    assert _openai_compatible_api_key("nexus") != os.environ["LITELLM_MASTER_KEY"]


def test_nexus_provider_calls_openai_compatible_chat_completions(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "nexus ok"}}]}

    class FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict, json: dict):
            calls.append({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr(freyja.agent_runtime_v3.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setenv("NEXUS_API_KEY", "nexus-env-token")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "litellm-env-token")
    registry = InferenceRegistryV3(
        endpoints=(
            InferenceEndpoint(
                endpoint_id="vulcan-nexus-fast-test",
                display_name="Vulcan Nexus fast test",
                provider="nexus",
                machine_id="vulcan",
                base_url="http://100.94.80.21:3939",
                model="@preset/freyja-fast-local",
                capabilities=frozenset({"general.local"}),
                security_domain_id=SecurityDomainId.HOUSEHOLD,
                priority=1,
            ),
        ),
        include_configured=False,
    )
    sender = GatewaySender(sender_id="person:joe", display_name="Joe", security_domain_id=SecurityDomainId.HOUSEHOLD)
    handoff = AgentGateway().handle(GatewayRequest(sender=sender, target_agent="freyja", prompt="hello", conversation_id="conv")).handoff
    assert handoff is not None

    result = AgentRuntimeV3(inference_registry=registry, run_inference=True).run(handoff)

    assert result.inference_status == "ok"
    assert result.response_text == "nexus ok"
    assert calls[0]["url"] == "http://100.94.80.21:3939/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer nexus-env-token"
    assert calls[0]["headers"]["Authorization"] != "Bearer litellm-env-token"
    assert calls[0]["json"]["model"] == "@preset/freyja-fast-local"
