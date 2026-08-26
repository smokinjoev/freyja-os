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

    assert [endpoint.endpoint_id for endpoint in household_coding] == ["vulcan-code"]
    assert household_legal == []
    assert [endpoint.endpoint_id for endpoint in enclave_legal] == ["paralegal-local"]
    assert not hasattr(registry, "classify_intent")
    assert not hasattr(registry, "choose_agent")


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
