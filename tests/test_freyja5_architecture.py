from __future__ import annotations

from pathlib import Path

import yaml

from freyja.agent_gateway import AgentGateway, GatewayRequest
from freyja.agent_runtime_v3 import AgentRuntimeV3
from certification.runner import Freyja5CertificationProvider, load_suite, run_suite_sync
from freyja.foundation_seed import INFERENCE_ENDPOINTS, PERSISTENT_AGENTS, TOOL_CAPABILITIES
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
    assert result.trace_summary["agent_logical_display_name"] == "Freyja"
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


def test_gateway_audit_event_records_ingress_trace_metadata() -> None:
    result = AgentGateway().handle(
        GatewayRequest(
            sender=_sender(),
            target_agent="freyja",
            prompt="Trace this important request.",
            conversation_id="conv-trace",
            channel="open-webui",
            message_id="msg-trace-1",
        )
    )

    assert result.handoff is not None
    metadata = result.audit_event.metadata
    assert metadata["handoff_id"] == result.handoff.handoff_id
    assert metadata["conversation_id"] == "conv-trace"
    assert metadata["channel"] == "open-webui"
    assert metadata["message_id"] == "msg-trace-1"
    assert metadata["source_domain"] == "household"
    assert metadata["target_domain"] == "household"
    assert metadata["authenticated_subject"] == "person:joe"
    assert "agent:freyja" in metadata["memory_scopes"]


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
    assert result.trace_summary["tool_boundaries"] == [
        {"tool_id": "filesystem.read", "protocol": "internal", "machine_affinity": None, "mutation": False}
    ]
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
    assert all(
        case.runtime_context["rev2_evidence"]["freyja5_mcp_topology"] == {
            "source": "config/freyja-5.0-mcp-topology.yaml",
            "available": True,
            "default_agent_mcp_servers": False,
            "mcp_hosts": ["atlas", "iris"],
            "mcp_tool_count": 12,
            "vulcan_protocol": "openai-compatible",
        }
        for case in report.cases
    )
    identity_case = next(case for case in report.cases if case.name == "e-multi-channel-household-identity")
    identity_channels = identity_case.runtime_context["rev2_evidence"]["freyja5_identity_channels"]
    assert [entry["channel"] for entry in identity_channels] == ["signal", "open-webui"]
    assert {entry["sender_id"] for entry in identity_channels} == {"person:joe"}
    assert {entry["authenticated_subject"] for entry in identity_channels} == {"person:joe"}
    assert all("agent:freyja" in entry["memory_scopes"] for entry in identity_channels)


def test_freyja5_agent_config_summary_matches_runtime_seed() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "freyja-5.0-agents.yaml").read_text(encoding="utf-8"))
    configured = {agent["id"]: agent for agent in config["agents"]}

    assert set(configured) == {agent.agent_id for agent in PERSISTENT_AGENTS}
    for seeded in PERSISTENT_AGENTS:
        summary = configured[seeded.agent_id]
        assert summary["display_name"] == seeded.display_name
        assert summary.get("logical_display_name") == seeded.logical_display_name
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


def test_freyja5_mcp_preferred_tool_boundary_is_explicit() -> None:
    protocols = {tool.tool_id: tool.protocol for tool in TOOL_CAPABILITIES}

    assert protocols["calendar.read"] == "mcp"
    assert protocols["calendar.write"] == "mcp"
    assert protocols["macagent.apple"] == "mcp"
    assert protocols["home-assistant.read"] == "mcp"
    assert protocols["filesystem.read"] == "internal"


def test_freyja5_mcp_topology_places_servers_by_capability_host() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "freyja-5.0-mcp-topology.yaml").read_text(encoding="utf-8"))
    servers = {server["id"]: server for server in config["servers"]}
    non_mcp = {boundary["id"]: boundary for boundary in config["non_mcp_boundaries"]}

    assert config["default_agent_mcp_servers"] is False
    assert config["policy"]["ownership"] == "capability_host"
    assert config["policy"]["consumption"] == "scoped_agent_tool_grants"
    assert servers["iris-apple-mcp"]["host"] == "iris"
    assert servers["atlas-household-mcp"]["host"] == "atlas"
    assert servers["atlas-media-mcp"]["host"] == "atlas"
    assert non_mcp["vulcan-nexus"]["host"] == "vulcan"
    assert non_mcp["vulcan-nexus"]["protocol"] == "openai-compatible"
    assert all(server["host"] != "vulcan" for server in config["servers"])


def test_freyja5_mcp_topology_matches_seeded_tool_affinity() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "freyja-5.0-mcp-topology.yaml").read_text(encoding="utf-8"))
    tools = {tool.tool_id: tool for tool in TOOL_CAPABILITIES}

    exposed_by_host = {
        tool_id: server["host"]
        for server in config["servers"]
        for tool_id in server["exposes"]
    }

    for tool_id, host in exposed_by_host.items():
        assert tool_id in tools
        assert tools[tool_id].protocol == "mcp"
        if tools[tool_id].machine_affinity is not None:
            assert tools[tool_id].machine_affinity == host

    seeded_mcp_tools = {tool.tool_id for tool in TOOL_CAPABILITIES if tool.protocol == "mcp"}
    assert seeded_mcp_tools == set(exposed_by_host)


def test_freyja5_agents_consume_mcp_through_scoped_grants() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "freyja-5.0-mcp-topology.yaml").read_text(encoding="utf-8"))
    exposed_tools = {tool_id for server in config["servers"] for tool_id in server["exposes"]}
    agents = {agent.agent_id: agent for agent in PERSISTENT_AGENTS}

    assert set(config["agent_consumption"]) == set(agents)
    assert set(config["agent_consumption"].values()) == {"scoped_agent_tool_grants"}
    for agent in agents.values():
        granted_mcp_tools = exposed_tools.intersection(agent.tool_grants)
        assert granted_mcp_tools
        assert granted_mcp_tools <= exposed_tools


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


def test_freyja5_trace_records_denied_cloud_egress_decision() -> None:
    registry = InferenceRegistryV3(
        endpoints=(
            InferenceEndpoint(
                endpoint_id="cloud-general",
                display_name="Cloud general",
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
            prompt="Summarize this legal case and api_key=secret.",
            conversation_id="conv-egress-denied",
            channel="test",
        )
    ).handoff
    assert handoff is not None

    result = AgentRuntimeV3(
        inference_registry=registry,
        run_inference=False,
        allow_cloud_fallback=True,
    ).run(handoff)

    assert result.inference_endpoint_id is None
    assert result.degraded is True
    assert result.egress_state == "local-only"
    egress_decision = result.trace_summary["egress_decisions"][0]
    assert egress_decision["event_type"] == "privacy_egress_denied"
    assert egress_decision["target_id"] == "cloud-frontier"
    assert egress_decision["allowed"] is False
    assert egress_decision["metadata"]["classification"] == "restricted"
    assert egress_decision["metadata"]["redacted"] is True
    assert "[REDACTED_SECRET]" in egress_decision["metadata"]["redacted_prompt_preview"]
    assert "api_key=secret" not in egress_decision["metadata"]["redacted_prompt_preview"]
