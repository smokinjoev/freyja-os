from __future__ import annotations

from freyja.agent_gateway import AgentGateway, GatewayRequest
from freyja.agent_runtime_v3 import AgentRuntimeV3
from certification.runner import Freyja5CertificationProvider, load_suite, run_suite_sync
from freyja.foundation_models import GatewaySender, SecurityDomainId
from freyja.semantic_routes import SemanticRoute, capability_for_route


def _sender(domain: SecurityDomainId = SecurityDomainId.HOUSEHOLD) -> GatewaySender:
    return GatewaySender(sender_id="person:joe", display_name="Joe", security_domain_id=domain)


def test_freyja5_semantic_routes_are_stable_contract() -> None:
    assert [route.value for route in SemanticRoute] == [
        "fast",
        "general",
        "deep",
        "code",
        "vision",
        "embedding",
        "private",
    ]
    assert capability_for_route(SemanticRoute.CODE) == "route.code"


def test_gateway_handoff_trace_summary_carries_freyja5_route_and_egress() -> None:
    handoff = AgentGateway().handle(
        GatewayRequest(
            sender=_sender(),
            target_agent="freyja",
            prompt="Please build and test this repo.",
            conversation_id="conv-f5",
            channel="test",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(run_inference=False).run(handoff)

    assert result.requested_route == "code"
    assert result.inference_endpoint_id == "vulcan-nexus-coder"
    assert result.inference_provider == "nexus"
    assert result.egress_state == "local-only"
    assert result.trace_summary["trace_id"] == handoff.handoff_id
    assert result.trace_summary["channel"] == "test"
    assert result.trace_summary["resolved_user"] == "person:joe"
    assert result.trace_summary["agent"] == "freyja"
    assert result.trace_summary["requested_route"] == "code"
    assert result.trace_summary["actual_endpoint"] == "vulcan-nexus-coder"


def test_benedict_paralegal_uses_private_local_only_route() -> None:
    handoff = AgentGateway().handle(
        GatewayRequest(
            sender=GatewaySender(
                sender_id="enclave:paralegal",
                display_name="Paralegal",
                security_domain_id=SecurityDomainId.PARALEGAL,
            ),
            target_agent="benedict-paralegal",
            prompt="Review this legal case document.",
            conversation_id="conv-paralegal",
            channel="test",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(run_inference=False).run(handoff)

    assert result.requested_route == "private"
    assert result.inference_provider == "nexus"
    assert result.inference_endpoint_id == "benedict-paralegal-nexus"
    assert result.egress_state == "local-only"


def test_freyja5_certification_suite_tracks_architecture_cases_a_through_g() -> None:
    suite = load_suite("routing/freyja5_architecture")

    assert suite.name == "freyja5-architecture"
    assert [case.name[0] for case in suite.cases] == ["a", "b", "c", "d", "e", "f", "g"]


def test_freyja5_certification_provider_exercises_gateway_runtime() -> None:
    suite = load_suite("routing/freyja5_architecture")

    report = run_suite_sync(suite=suite, provider=Freyja5CertificationProvider())

    assert report.passed is True
    assert report.metadata.provider == "local_reasoning"
    assert {case.runtime_context["interface"] for case in report.cases} == {"freyja5"}
    assert all(case.runtime_context["rev2_evidence"]["freyja5_trace_id"] for case in report.cases)
