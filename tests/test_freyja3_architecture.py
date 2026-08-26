from __future__ import annotations

import pytest

from freyja.agent_gateway import AgentGateway, GatewayRequest
from freyja.agent_runtime_v3 import AgentRuntimeV3, MemoryBoundaryError
from freyja.foundation_models import GatewaySender, MemoryClassification, SecurityDomainId, SemanticEvent
from freyja.inference_registry_v3 import InferenceRegistryV3
from freyja.main import app
from fastapi.testclient import TestClient
from freyja.config import settings


def _sender(person: str = "joe") -> GatewaySender:
    return GatewaySender(
        sender_id=f"person:{person}",
        display_name=person.title(),
        security_domain_id={
            "joe": SecurityDomainId.PERSON_JOE,
            "beth": SecurityDomainId.PERSON_BETH,
            "liam": SecurityDomainId.PERSON_LIAM,
            "jenna": SecurityDomainId.PERSON_JENNA,
        }.get(person, SecurityDomainId.HOUSEHOLD),
    )


def test_gateway_selects_correct_agent_without_intent_routing() -> None:
    gateway = AgentGateway()

    result = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="Cloyd",
            prompt="Search weather and check this repo.",
            conversation_id="conv",
        )
    )

    assert result.handoff is not None
    assert result.handoff.target_agent_id == "cloyd-gibbler"
    assert result.handoff.prompt == "Search weather and check this repo."
    assert not any(name in dir(gateway) for name in ("classify_intent", "route_by_intent", "select_tool", "plan_task"))


def test_agent_receives_objective_and_independently_selects_tools() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(
            sender=_sender("joe"),
            target_agent="cloyd",
            prompt="Search the web, check weather, inspect git status, and run tests.",
            conversation_id="conv",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3().run(handoff)

    assert result.steps[0].detail == handoff.prompt
    assert "web.search" in result.selected_tools
    assert "weather.current" in result.selected_tools
    assert "git.inspect" in result.selected_tools
    assert "coding.execute" in result.selected_tools
    assert len(result.selected_tools) >= 4


def test_agents_use_vulcan_inference_and_identity_survives_endpoint_changes() -> None:
    gateway = AgentGateway()
    handoff = gateway.handle(
        GatewayRequest(sender=_sender("joe"), target_agent="cloyd", prompt="Build and test the repo.", conversation_id="conv")
    ).handoff
    assert handoff is not None

    normal = AgentRuntimeV3().run(handoff)
    recovered = AgentRuntimeV3(unhealthy_endpoint_ids={"vulcan-code"}).run(handoff)

    assert normal.agent_id == "cloyd-gibbler"
    assert normal.inference_endpoint_id == "vulcan-code"
    assert normal.inference_machine_id == "vulcan"
    assert recovered.agent_id == "cloyd-gibbler"
    assert recovered.inference_endpoint_id != "vulcan-code"
    assert recovered.degraded is False


def test_iris_apple_and_atlas_home_assistant_capabilities_are_agent_selected() -> None:
    runtime = AgentRuntimeV3()
    gateway = AgentGateway()
    freyja_handoff = gateway.handle(
        GatewayRequest(
            sender=GatewaySender(sender_id="person:family", display_name="Family", security_domain_id=SecurityDomainId.HOUSEHOLD),
            target_agent="freyja",
            prompt="Turn on the kitchen lights and send an iMessage.",
            conversation_id="home",
        )
    ).handoff
    cloyd_handoff = gateway.handle(
        GatewayRequest(sender=_sender("joe"), target_agent="cloyd", prompt="Open Safari on the Mac.", conversation_id="mac")
    ).handoff
    assert freyja_handoff is not None
    assert cloyd_handoff is not None

    freyja_result = runtime.run(freyja_handoff)
    cloyd_result = runtime.run(cloyd_handoff)

    assert "home-assistant.control" in freyja_result.selected_tools
    assert "messaging.send" in freyja_result.selected_tools
    assert "macagent.apple" in cloyd_result.selected_tools


def test_hera_semantic_perception_event_contract() -> None:
    event = SemanticEvent(
        source_machine_id="hera",
        event_type="person_present",
        room="kitchen",
        subject="joe",
        confidence=0.91,
    )

    assert event.source_machine_id == "hera"
    assert event.event_type == "person_present"
    assert event.confidence == 0.91


def test_memory_and_paralegal_boundaries_and_cloud_egress() -> None:
    runtime = AgentRuntimeV3()

    with pytest.raises(MemoryBoundaryError):
        runtime.assert_memory_read_allowed("benedict", "person:joe")

    denial = runtime.evaluate_cloud_request(
        agent_id="cloyd-gibbler",
        prompt="api_key=secret and my SSN is 123-45-6789",
        classification=MemoryClassification.RESTRICTED,
    )

    assert denial.allowed is False
    assert denial.audit_event.allowed is False
    assert "[REDACTED" in denial.redacted_prompt

    legal = InferenceRegistryV3().endpoints_for(capability="legal_research", domain_id=SecurityDomainId.HOUSEHOLD)
    assert legal == []


def test_canonical_route_can_use_freyja3_gateway_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "freyja3_canonical_enabled", True)
    client = TestClient(app)

    response = client.post(
        "/canonical/route",
        json={
            "trace_id": "trace-f3",
            "message_id": "msg-f3",
            "channel": "imessage",
            "conversation_id": "conv-f3",
            "sender": {"channel_id": "sender", "address": "+1555"},
            "resolved_user_id": "joe",
            "resolved_agent_id": "cloyd-gibbler",
            "text": "Search current weather and inspect git status.",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["resolved_agent_id"] == "cloyd-gibbler"
    assert data["conversation_id"] == "conv-f3"
    assert data["channel_metadata"]["freyja3"] is True
    assert "web.search" in {tool["tool_name"] for tool in data["tool_results"]}
    assert data["channel_metadata"]["inference_machine_id"] == "vulcan"
