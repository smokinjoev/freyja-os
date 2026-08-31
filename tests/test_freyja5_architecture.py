from __future__ import annotations

from pathlib import Path

import yaml

from freyja.agent_gateway import AgentGateway, GatewayRequest
from freyja.agent_runtime_v3 import AgentRuntimeV3
from certification.runner import Freyja5CertificationProvider, load_suite, run_suite_sync
from freyja.foundation_seed import INFERENCE_ENDPOINTS, PERSISTENT_AGENTS
from freyja.foundation_models import GatewaySender, InferenceEndpoint, SecurityDomainId
from freyja.inference_registry_v3 import InferenceRegistryV3
from freyja.semantic_routes import SemanticRoute, capability_for_route


REPO_ROOT = Path(__file__).resolve().parents[1]


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
    assert result.trace_summary["actual_provider"] == "nexus"
    assert result.trace_summary["actual_model"] == "@preset/freyja-coder"
    assert result.trace_summary["actual_runtime"] == "nexus"
    assert result.trace_summary["machine"] == "vulcan"
    assert result.trace_summary["inference_status"] == "not_run"
    assert result.trace_summary["selected_tools"] == []
    assert result.trace_summary["tool_calls"] == []
    assert isinstance(result.trace_summary["latency_ms"], float)


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
    assert result.trace_summary["machine"] == "vulcan"
    assert result.trace_summary["egress_state"] == "local-only"


def test_cloyd_delegation_trace_records_selected_tools() -> None:
    handoff = AgentGateway().handle(
        GatewayRequest(
            sender=_sender(SecurityDomainId.PERSON_JOE),
            target_agent="cloyd",
            prompt="Freyja delegates repo inspection to Cloyd.",
            conversation_id="conv-cloyd",
            channel="test",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(run_inference=False).run(handoff)

    assert result.agent_id == "cloyd-gibbler"
    assert result.trace_summary["selected_tools"] == ["filesystem.read"]
    assert result.trace_summary["tool_calls"] == ["filesystem.read"]
    assert result.trace_summary["delegation"] == [
        {"from": "freyja", "to": "cloyd-gibbler", "reason": "explicit Cloyd delegation request"}
    ]


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
    assert all("latency_ms" in case.runtime_context["rev2_evidence"]["freyja5_trace_summary"] for case in report.cases)


def test_freyja5_agent_config_summary_matches_runtime_seed() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "freyja-5.0-agents.yaml").read_text(encoding="utf-8"))
    configured = {agent["id"]: agent for agent in config["agents"]}

    assert set(configured) == {agent.agent_id for agent in PERSISTENT_AGENTS}
    for seeded in PERSISTENT_AGENTS:
        summary = configured[seeded.agent_id]
        assert summary["display_name"] == seeded.display_name
        assert summary["owner"] == seeded.owner
        assert summary["home_machine"] == seeded.home_machine_id
        assert set(summary["memory"]) == {
            scope
            for scope in (seeded.private_memory_scope, *seeded.shared_memory_scopes)
            if scope
        }


def test_freyja5_semantic_route_config_has_seeded_endpoint_for_each_route() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "freyja-5.0-semantic-routes.yaml").read_text(encoding="utf-8"))
    routes = config["routes"]
    capabilities_by_endpoint = {endpoint.endpoint_id: endpoint.capabilities for endpoint in INFERENCE_ENDPOINTS}

    assert set(routes) == {route.value for route in SemanticRoute}
    for route_name, route_config in routes.items():
        endpoint_id = route_config["preferred_runtime"]
        assert endpoint_id in capabilities_by_endpoint
        assert route_config["capability"] in capabilities_by_endpoint[endpoint_id], route_name


def test_freyja5_mode_does_not_use_implicit_cloud_fallback() -> None:
    registry = InferenceRegistryV3(
        endpoints=(
            InferenceEndpoint(
                endpoint_id="cloud-only",
                display_name="Cloud only",
                provider="openrouter",
                model="cloud",
                capabilities=frozenset({"general.cloud"}),
                security_domain_id=SecurityDomainId.SYSTEM,
                priority=1,
            ),
        ),
        include_configured=False,
    )
    handoff = AgentGateway().handle(
        GatewayRequest(
            sender=_sender(SecurityDomainId.PERSON_JOE),
            target_agent="cloyd",
            prompt="Public summary of model routing.",
            conversation_id="conv-no-cloud",
            channel="test",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(
        inference_registry=registry,
        run_inference=False,
        allow_cloud_fallback=False,
    ).run(handoff)

    assert result.inference_endpoint_id is None
    assert result.degraded is True
    assert result.egress_state == "local-only"
    assert result.trace_summary["actual_provider"] is None
    assert result.trace_summary["fallbacks"] == []
