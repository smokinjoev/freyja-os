import pytest
from pydantic import ValidationError

from freyja.agent_gateway import AgentGateway, GatewayPermissionError, GatewayRequest
from freyja.foundation_models import (
    GatewaySender,
    MemoryClassification,
    MemoryRecordMetadata,
    MemoryScope,
    PersistentAgent,
    SecurityDomainId,
)
from freyja.foundation_seed import PARALEGAL_ENCLAVE_DOMAIN
from freyja.inference_registry_v3 import InferenceRegistryV3


def test_named_target_agents_resolve_correctly() -> None:
    gateway = AgentGateway()

    assert gateway.resolve_target_agent("Freyja").agent_id == "freyja"
    assert gateway.resolve_target_agent("Cloyd Gibbler").agent_id == "cloyd-gibbler"
    assert gateway.resolve_target_agent("Benedict").agent_id == "benedict"
    assert gateway.resolve_target_agent("Agent 44").agent_id == "agent-44"
    assert gateway.resolve_target_agent("Jenna").agent_id == "jenna"
    assert gateway.resolve_target_agent("Legal Benedict").agent_id == "benedict-paralegal"


def test_gateway_creates_handoff_and_audit_for_explicit_target() -> None:
    gateway = AgentGateway()
    result = gateway.handle(
        GatewayRequest(
            sender=GatewaySender(
                sender_id="person:joe",
                display_name="Joe",
                security_domain_id=SecurityDomainId.FREYJA_HOUSEHOLD,
            ),
            target_agent="Cloyd",
            prompt="Check the project state.",
            conversation_id="conv-3",
        )
    )

    assert result.handoff is not None
    assert result.handoff.target_agent_id == "cloyd-gibbler"
    assert result.handoff.conversation_id == "conv-3"
    assert result.audit_event.allowed is True
    assert result.audit_event.metadata["handoff_id"] == result.handoff.handoff_id


def test_gateway_does_not_perform_intent_planning() -> None:
    gateway = AgentGateway()

    forbidden_surface = {
        "classify_intent",
        "plan",
        "plan_task",
        "choose_strategy",
        "select_tool",
        "route_by_intent",
    }

    assert forbidden_surface.isdisjoint(set(dir(gateway)))


def test_freyja_domain_fixtures_cannot_access_paralegal_enclave_records() -> None:
    paralegal_agent = PersistentAgent(
        agent_id="paralegal-clerk",
        display_name="Paralegal Clerk",
        owner="enclave:paralegal",
        security_domain_id=SecurityDomainId.PARALEGAL_ENCLAVE,
    )
    gateway = AgentGateway(agents=(paralegal_agent,))

    with pytest.raises(GatewayPermissionError) as exc:
        gateway.handle(
            GatewayRequest(
                sender=GatewaySender(
                    sender_id="agent:freyja",
                    display_name="Freyja",
                    security_domain_id=SecurityDomainId.FREYJA_HOUSEHOLD,
                ),
                target_agent="Paralegal Clerk",
                prompt="Open enclave records.",
            )
        )

    denied = exc.value.audit_event
    assert denied.allowed is False
    assert denied.domain_id == SecurityDomainId.FREYJA_HOUSEHOLD
    assert denied.metadata == {}
    assert PARALEGAL_ENCLAVE_DOMAIN.domain_id == SecurityDomainId.PARALEGAL


def test_inference_endpoint_lookup_is_capability_domain_based_only() -> None:
    registry = InferenceRegistryV3()

    household_coding = registry.endpoints_for(
        capability="coding",
        domain_id=SecurityDomainId.FREYJA_HOUSEHOLD,
    )
    household_legal = registry.endpoints_for(
        capability="legal_research",
        domain_id=SecurityDomainId.FREYJA_HOUSEHOLD,
    )
    enclave_legal = registry.endpoints_for(
        capability="legal_research",
        domain_id=SecurityDomainId.PARALEGAL_ENCLAVE,
    )

    assert [endpoint.endpoint_id for endpoint in household_coding] == ["vulcan-nexus-coder", "vulcan-code"]
    assert household_legal == []
    assert [endpoint.endpoint_id for endpoint in enclave_legal] == ["benedict-paralegal-nexus", "paralegal-local"]
    assert not hasattr(registry, "classify_intent")
    assert not hasattr(registry, "choose_agent")


def test_inference_registry_loads_configured_openai_compatible_endpoints(monkeypatch) -> None:
    monkeypatch.setattr(
        "freyja.inference_registry_v3.settings.freyja3_inference_endpoints_json",
        """[
          {
            "endpoint_id": "vulcan-lmstudio",
            "display_name": "Vulcan LM Studio",
            "provider": "lmstudio",
            "machine_id": "vulcan",
            "base_url": "http://100.94.80.21:1234",
            "model": "local-model",
            "capabilities": ["general.large", "chat"],
            "security_domain_id": "household",
            "priority": 21
          }
        ]""",
    )

    registry = InferenceRegistryV3()
    endpoints = registry.endpoints_for(capability="general.large", domain_id=SecurityDomainId.HOUSEHOLD)

    assert [endpoint.endpoint_id for endpoint in endpoints] == ["vulcan-nexus-strong", "vulcan-reason", "vulcan-lmstudio"]


def test_memory_record_metadata_requires_scope_owner_provenance_confidence_classification() -> None:
    metadata = MemoryRecordMetadata(
        scope=MemoryScope.HOUSEHOLD,
        owner_domain_id=SecurityDomainId.FREYJA_HOUSEHOLD,
        provenance="user_confirmed_fact:joe",
        confidence=0.92,
        classification=MemoryClassification.PRIVATE,
    )

    assert metadata.scope == MemoryScope.HOUSEHOLD
    assert metadata.owner_domain_id == SecurityDomainId.FREYJA_HOUSEHOLD
    assert metadata.confidence == 0.92

    with pytest.raises(ValidationError):
        MemoryRecordMetadata.model_validate(
            {
                "scope": "household",
                "owner_domain_id": "freyja-household",
                "provenance": "user_confirmed_fact:joe",
                "classification": "private",
            }
        )


def test_iris_fast_endpoint_has_local_model_defaults() -> None:
    registry = InferenceRegistryV3()
    endpoints = registry.endpoints_for(capability="general.local", domain_id=SecurityDomainId.HOUSEHOLD)
    iris_fast = next(endpoint for endpoint in endpoints if endpoint.endpoint_id == "iris-fast")

    assert iris_fast.base_url == "http://100.115.228.56:11434"
    assert iris_fast.model == "qwen2.5:7b"


def test_vulcan_general_uses_32b_qwen_and_deep_uses_big_multimodal_model() -> None:
    registry = InferenceRegistryV3()
    general = registry.endpoints_for(capability="general.large", domain_id=SecurityDomainId.HOUSEHOLD)[0]
    deep = registry.endpoints_for(capability="general.deep", domain_id=SecurityDomainId.HOUSEHOLD)[0]
    vision = registry.endpoints_for(capability="vision.large", domain_id=SecurityDomainId.HOUSEHOLD)[0]

    assert general.endpoint_id == "vulcan-nexus-strong"
    assert general.provider == "nexus"
    assert general.model == "@preset/freyja-strong-local"
    assert deep.endpoint_id == "vulcan-deep"
    assert deep.model == "qwen2.5vl:72b"
    assert vision.endpoint_id == "vulcan-nexus-vision-docs"
    assert vision.model == "@preset/freyja-vision-docs"


def test_vulcan_coder_keeps_qwen_coder_model() -> None:
    registry = InferenceRegistryV3()
    coder = registry.endpoints_for(capability="code.large", domain_id=SecurityDomainId.HOUSEHOLD)[0]

    assert coder.endpoint_id == "vulcan-nexus-coder"
    assert coder.provider == "nexus"
    assert coder.model == "@preset/freyja-coder"


def test_nexus_presets_are_default_local_gateway_and_direct_ollama_remains_fallback() -> None:
    registry = InferenceRegistryV3()
    local = registry.endpoints_for(capability="general.local", domain_id=SecurityDomainId.HOUSEHOLD)
    strong = registry.endpoints_for(capability="general.large", domain_id=SecurityDomainId.HOUSEHOLD)
    legal = registry.endpoints_for(capability="legal_research", domain_id=SecurityDomainId.PARALEGAL)

    assert local[0].endpoint_id == "vulcan-nexus-fast"
    assert local[0].base_url == "http://100.94.80.21:3939"
    assert local[0].model == "@preset/freyja-fast-local"
    assert [endpoint.provider for endpoint in strong[:2]] == ["nexus", "ollama"]
    assert legal[0].endpoint_id == "benedict-paralegal-nexus"
    assert legal[0].security_domain_id == SecurityDomainId.PARALEGAL


def test_benedict_personal_agent_is_separate_from_paralegal_enclave() -> None:
    gateway = AgentGateway()
    beth_agent = gateway.resolve_target_agent("Benedict")
    legal_agent = gateway.resolve_target_agent("Paralegal")

    assert beth_agent.agent_id == "benedict"
    assert beth_agent.security_domain_id == SecurityDomainId.PERSON_BETH
    assert beth_agent.private_memory_scope == "person:beth"
    assert legal_agent.agent_id == "benedict-paralegal"
    assert legal_agent.security_domain_id == SecurityDomainId.PARALEGAL
    assert legal_agent.private_memory_scope == "enclave:paralegal"
    assert "family" not in legal_agent.shared_memory_scopes
