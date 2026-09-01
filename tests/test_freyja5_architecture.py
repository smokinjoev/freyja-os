from __future__ import annotations

from pathlib import Path

import yaml

from freyja.agent_gateway import AgentGateway, GatewayRequest
from freyja.agent_runtime_v3 import AgentRuntimeV3
from certification.runner import Freyja5CertificationProvider, load_suite, run_suite_sync
from freyja.freyja5_config import (
    freyja5_agent_evidence,
    freyja5_certification_evidence,
    freyja5_certification_live_blocker_ids,
    freyja5_certification_target_blockers,
    freyja5_gateway_evidence,
    freyja5_live_blocker_evidence,
    freyja5_mcp_topology_evidence,
    freyja5_plane_evidence,
    freyja5_semantic_route_evidence,
    freyja5_traceability_evidence,
    freyja5_webgui_evidence,
)
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
    traceability = freyja5_traceability_evidence()
    assert set(traceability["important_request_fields"]) <= set(result.trace_summary)


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
    evidence = freyja5_certification_evidence()

    assert suite.name == "freyja5-architecture"
    assert [case.name[0] for case in suite.cases] == ["a", "b", "c", "d", "e", "f", "g"]
    assert evidence["source"] == "certification/suites/routing/freyja5_architecture.yaml"
    assert evidence["suite"] == suite.name
    assert [target["target"] for target in evidence["targets"]] == ["A", "B", "C", "D", "E", "F", "G"]
    assert [target["case"] for target in evidence["targets"]] == [case.name for case in suite.cases]
    assert evidence["live_blockers"] == freyja5_certification_live_blocker_ids()


def test_freyja5_certification_provider_exercises_gateway_runtime() -> None:
    suite = load_suite("routing/freyja5_architecture")

    report = run_suite_sync(suite=suite, provider=Freyja5CertificationProvider())

    assert report.passed is True
    assert report.metadata.provider == "local_reasoning"
    assert {case.runtime_context["interface"] for case in report.cases} == {"freyja5"}
    assert all(case.runtime_context["rev2_evidence"]["freyja5_trace_id"] for case in report.cases)
    assert all("latency_ms" in case.runtime_context["rev2_evidence"]["freyja5_trace_summary"] for case in report.cases)
    assert all(
        case.runtime_context["rev2_evidence"]["freyja5_audit_chain"][0]["event_type"] == "gateway_handoff_created"
        for case in report.cases
    )
    assert all(
        case.runtime_context["rev2_evidence"]["freyja5_audit_chain"][0]["metadata"]["handoff_id"]
        == case.runtime_context["rev2_evidence"]["freyja5_trace_id"]
        for case in report.cases
    )
    assert all(
        case.runtime_context["rev2_evidence"]["freyja5_audit_chain"][-1]["event_type"]
        in {"agent_inference_completed", "agent_memory_candidate_proposed"}
        for case in report.cases
    )
    assert all(
        {agent["id"] for agent in case.runtime_context["rev2_evidence"]["freyja5_agents"]}
        >= {"freyja", "cloyd-gibbler", "benedict-paralegal", "agent-47", "jennacide"}
        for case in report.cases
    )
    expected_agents = freyja5_agent_evidence()
    assert all(
        case.runtime_context["rev2_evidence"]["freyja5_agents"] == expected_agents
        for case in report.cases
    )
    agent_evidence = {agent["id"]: agent for agent in expected_agents}
    assert agent_evidence["freyja"] == {
        "id": "freyja",
        "display_name": "Freyja",
        "logical_display_name": "Freyja",
        "owner": "household",
        "security_domain": "household",
        "home_machine": "atlas",
        "private_memory_scope": "agent:freyja",
        "shared_memory_scopes": ["family", "system"],
        "tool_grant_count": 15,
        "cloud_egress_policy": "household-default",
    }
    assert agent_evidence["benedict-paralegal"]["owner"] == "enclave:paralegal"
    assert agent_evidence["benedict-paralegal"]["private_memory_scope"] == "enclave:paralegal"
    assert agent_evidence["benedict-paralegal"]["cloud_egress_policy"] == "paralegal-local-only"
    assert agent_evidence["agent-47"]["logical_display_name"] == "Agent 44"
    assert agent_evidence["jennacide"]["logical_display_name"] == "Jenna agent"
    expected_planes = freyja5_plane_evidence()
    assert all(
        case.runtime_context["rev2_evidence"]["freyja5_planes"] == expected_planes
        for case in report.cases
    )
    plane_evidence = report.cases[0].runtime_context["rev2_evidence"]["freyja5_planes"]
    assert plane_evidence["atlas"]["role"] == "persistent-agent-plane"
    assert plane_evidence["atlas"]["recoverable_fallback_tag"] == "freyja-4.1-baseline-before-5.0-20260831-161448"
    assert plane_evidence["iris"]["role"] == "apple-macos-capability-server"
    assert plane_evidence["hera"]["role"] == "avatar-voice-channel-edge"
    assert plane_evidence["vulcan"]["local_by_default"] is True
    expected_semantic_routes = freyja5_semantic_route_evidence()
    assert all(
        case.runtime_context["rev2_evidence"]["freyja5_semantic_routes"] == expected_semantic_routes
        for case in report.cases
    )
    assert expected_semantic_routes["owner"] == "nexus"
    assert expected_semantic_routes["cloud_fallback"] == "explicit_only"
    assert set(expected_semantic_routes["routes"]) == {route.value for route in SemanticRoute}
    assert expected_semantic_routes["routes"]["private"]["egress_policy"] == "local_only"
    expected_gateway = freyja5_gateway_evidence()
    assert all(
        case.runtime_context["rev2_evidence"]["freyja5_gateway"] == expected_gateway
        for case in report.cases
    )
    assert expected_gateway["host"] == "atlas"
    assert expected_gateway["role"] == "deterministic-ingress-boundary"
    assert expected_gateway["policy"]["forwards_to"] == "agent-runtime-v3"
    assert expected_gateway["policy"]["physical_model_selection_owner"] == "nexus"
    assert expected_gateway["policy"]["cloud_fallback"] == "explicit_only"
    assert all(expected_gateway["policy"][key] is True for key in (
        "no_agent_reasoning",
        "no_arbitrary_tool_orchestration",
        "no_physical_model_selection",
        "no_implicit_cloud_fallback",
    ))
    expected_mcp_topology = freyja5_mcp_topology_evidence()
    assert all(
        case.runtime_context["rev2_evidence"]["freyja5_mcp_topology"] == expected_mcp_topology
        for case in report.cases
    )
    assert expected_mcp_topology["source"] == "config/freyja-5.0-mcp-topology.yaml"
    assert expected_mcp_topology["available"] is True
    assert expected_mcp_topology["default_agent_mcp_servers"] is False
    assert expected_mcp_topology["mcp_hosts"] == ["atlas", "iris"]
    assert expected_mcp_topology["mcp_tool_count"] == 12
    assert expected_mcp_topology["vulcan_protocol"] == "openai-compatible"
    assert expected_mcp_topology["gateway_policy"]["no_agent_reasoning"] is True
    assert expected_mcp_topology["gateway_policy"]["no_physical_model_selection"] is True
    expected_live_blockers = {
        "source": "FREYJA-5.0-BLOCKERS.md",
        "joe_required": [
            {
                "id": "msty_go_always_on_linux_validation",
                "component": "atlas",
                "requires": [
                    "install_path",
                    "service_definition",
                    "restart_behavior",
                    "local_config_export_story",
                    "health_endpoint_or_equivalent",
                    "source_controlled_agent_definition_compatibility",
                ],
            },
            {
                "id": "vulcan_nexus_presets",
                "component": "vulcan",
                "requires": [
                    "local_only_fast_preset",
                    "local_only_general_preset",
                    "local_only_deep_preset",
                    "local_only_code_preset",
                    "local_only_vision_preset",
                    "local_only_embedding_preset",
                    "local_only_private_preset",
                ],
            },
            {
                "id": "iris_apple_session",
                "component": "iris",
                "requires": ["live_apple_calendar_mcp_or_macagent_session"],
            },
            {
                "id": "hera_voice_avatar_hardware",
                "component": "hera",
                "requires": ["microphone", "speaker", "avatar_runtime", "physical_session_validation"],
            },
            {
                "id": "live_tool_sessions",
                "component": "atlas",
                "requires": ["live_mcp_tool_sessions", "cloyd_delegation_tool_smoke", "tool_call_trace_evidence"],
            },
            {
                "id": "vulcan_nexus_private_preset",
                "component": "vulcan",
                "requires": [
                    "local_only_private_preset",
                    "benedict_enclave_no_cloud_egress_smoke",
                    "private_route_trace_evidence",
                ],
            },
        ],
        "secrets_in_source": False,
        "continue_independent_work": True,
    }
    assert all(
        case.runtime_context["rev2_evidence"]["freyja5_live_blockers"] == expected_live_blockers
        for case in report.cases
    )
    expected_webgui = {
        "source": "config/freyja-5.0-webgui.yaml",
        "openai_compatible": True,
        "default_model_preserved": "agent-smith",
        "freyja5_model": "freyja-5",
        "freyja5_opt_in": True,
        "media_content_parts": ["image_url", "input_image", "file", "input_file"],
        "inline_data_url_only": True,
        "cloud_fallback": False,
        "live_inference_default": False,
    }
    assert all(
        case.runtime_context["rev2_evidence"]["freyja5_webgui"] == expected_webgui
        for case in report.cases
    )
    expected_traceability = {
        "source": "config/freyja-5.0-traceability.yaml",
        "important_request_fields": [
            "trace_id",
            "channel",
            "resolved_user",
            "authenticated_subject",
            "agent",
            "requested_route",
            "actual_endpoint",
            "actual_provider",
            "actual_model",
            "actual_runtime",
            "selected_tools",
            "tool_calls",
            "delegation",
            "machine",
            "latency_ms",
            "failures",
            "fallbacks",
            "inference_status",
            "egress_state",
        ],
        "audit_chain": {
            "starts_with": "gateway_handoff_created",
            "includes": ["gateway_handoff_created", "agent_task_started"],
            "terminal_events": ["agent_inference_completed", "agent_memory_candidate_proposed"],
        },
        "egress_events": {
            "include_allowed": True,
            "include_denied": True,
            "redact_prompt_preview": True,
        },
    }
    assert all(
        case.runtime_context["rev2_evidence"]["freyja5_traceability"] == expected_traceability
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
    evidence = {agent["id"]: agent for agent in freyja5_agent_evidence()}

    assert set(configured) == {agent.agent_id for agent in PERSISTENT_AGENTS}
    assert set(evidence) == set(configured)
    for seeded in PERSISTENT_AGENTS:
        summary = configured[seeded.agent_id]
        agent_evidence = evidence[seeded.agent_id]
        assert summary["display_name"] == seeded.display_name
        assert summary.get("logical_display_name") == seeded.logical_display_name
        assert summary["owner"] == seeded.owner
        assert summary["home_machine"] == seeded.home_machine_id
        assert set(summary["memory"]) == {
            scope
            for scope in (seeded.private_memory_scope, *seeded.shared_memory_scopes)
            if scope
        }
        assert agent_evidence["display_name"] == seeded.display_name
        assert agent_evidence["logical_display_name"] == (seeded.logical_display_name or seeded.display_name)
        assert agent_evidence["owner"] == seeded.owner
        assert agent_evidence["security_domain"] == seeded.security_domain_id.value
        assert agent_evidence["home_machine"] == seeded.home_machine_id
        assert agent_evidence["private_memory_scope"] == seeded.private_memory_scope
        assert agent_evidence["shared_memory_scopes"] == sorted(seeded.shared_memory_scopes)
        assert agent_evidence["tool_grant_count"] == len(seeded.tool_grants)
        assert agent_evidence["cloud_egress_policy"] == seeded.cloud_egress_policy_id


def test_freyja5_semantic_route_config_has_seeded_endpoint_for_each_route() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "freyja-5.0-semantic-routes.yaml").read_text(encoding="utf-8"))
    routes = config["routes"]
    evidence = freyja5_semantic_route_evidence()
    capabilities_by_endpoint = {endpoint.endpoint_id: endpoint.capabilities for endpoint in INFERENCE_ENDPOINTS}

    assert evidence["source"] == "config/freyja-5.0-semantic-routes.yaml"
    assert evidence["owner"] == "nexus"
    assert evidence["cloud_fallback"] == "explicit_only"
    assert set(routes) == {route.value for route in SemanticRoute}
    assert set(evidence["routes"]) == set(routes)
    for route_name, route_config in routes.items():
        endpoint_id = route_config["preferred_runtime"]
        assert endpoint_id in capabilities_by_endpoint
        assert route_config["capability"] in capabilities_by_endpoint[endpoint_id], route_name
        assert evidence["routes"][route_name]["preferred_runtime"] == endpoint_id


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


def test_freyja5_plane_config_matches_mcp_topology_boundaries() -> None:
    topology = yaml.safe_load((REPO_ROOT / "config" / "freyja-5.0-mcp-topology.yaml").read_text(encoding="utf-8"))
    planes = freyja5_plane_evidence()
    non_mcp = {boundary["id"]: boundary for boundary in topology["non_mcp_boundaries"]}

    assert planes["source"] == "config/freyja-5.0-planes.yaml"
    assert planes["atlas"]["host"] == non_mcp["freyja-gateway"]["host"]
    assert planes["atlas"]["role"] == "persistent-agent-plane"
    assert planes["atlas"]["msty_go"]["boundary_preserved"] is True
    assert planes["atlas"]["recoverable_fallback_tag"] == "freyja-4.1-baseline-before-5.0-20260831-161448"
    assert planes["hera"]["host"] == non_mcp["hera-channel-edge"]["host"]
    assert planes["hera"]["protocol"] == non_mcp["hera-channel-edge"]["protocol"]
    assert planes["hera"]["general_tool_server"] is False
    assert planes["iris"]["host"] == "iris"
    assert planes["iris"]["protocol"] == "mcp"
    assert planes["iris"]["atlas_authorizes_operations"] is True
    assert planes["vulcan"]["local_by_default"] is True
    assert planes["vulcan"]["live_blockers"] == ["vulcan_nexus_presets"]


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


def test_freyja5_live_blocker_config_matches_blocker_doc() -> None:
    blocker_doc = (REPO_ROOT / "FREYJA-5.0-BLOCKERS.md").read_text(encoding="utf-8")
    blocker_config = yaml.safe_load(
        (REPO_ROOT / "config" / "freyja-5.0-live-blockers.yaml").read_text(encoding="utf-8")
    )
    evidence = freyja5_live_blocker_evidence()

    assert blocker_config["version"] == "freyja-5.0"
    assert blocker_config["source_document"] == "FREYJA-5.0-BLOCKERS.md"
    assert evidence["source"] == "FREYJA-5.0-BLOCKERS.md"
    assert evidence["secrets_in_source"] is False
    assert evidence["continue_independent_work"] is True
    assert [blocker["id"] for blocker in evidence["joe_required"]] == [
        "msty_go_always_on_linux_validation",
        "vulcan_nexus_presets",
        "iris_apple_session",
        "hera_voice_avatar_hardware",
        "live_tool_sessions",
        "vulcan_nexus_private_preset",
    ]
    assert freyja5_certification_live_blocker_ids() == [
        "msty_go_always_on_linux_validation",
        "vulcan_nexus_presets",
        "iris_apple_session",
        "hera_voice_avatar_hardware",
        "live_tool_sessions",
        "vulcan_nexus_private_preset",
    ]
    assert freyja5_certification_target_blockers() == {
        "a": ["vulcan_nexus_presets"],
        "b": ["vulcan_nexus_presets", "live_tool_sessions"],
        "c": ["iris_apple_session"],
        "d": ["vulcan_nexus_presets"],
        "e": [],
        "f": ["vulcan_nexus_private_preset"],
        "g": [],
    }
    joe_required_ids = {blocker["id"] for blocker in evidence["joe_required"]}
    for blockers in freyja5_certification_target_blockers().values():
        assert set(blockers) <= joe_required_ids
    for blocker in evidence["joe_required"]:
        assert blocker["component"] in {"atlas", "vulcan", "iris", "hera"}
        assert blocker["requires"]
        assert blocker["id"] in blocker_doc


def test_freyja5_webgui_config_preserves_open_webui_default() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "freyja-5.0-webgui.yaml").read_text(encoding="utf-8"))
    evidence = freyja5_webgui_evidence()

    assert config["version"] == "freyja-5.0"
    assert evidence == {
        "source": "config/freyja-5.0-webgui.yaml",
        "openai_compatible": True,
        "default_model_preserved": "agent-smith",
        "freyja5_model": "freyja-5",
        "freyja5_opt_in": True,
        "media_content_parts": ["image_url", "input_image", "file", "input_file"],
        "inline_data_url_only": True,
        "cloud_fallback": False,
        "live_inference_default": False,
    }
    assert evidence["default_model_preserved"] != evidence["freyja5_model"]
    assert evidence["freyja5_opt_in"] is True


def test_freyja5_traceability_config_matches_runtime_trace_contract() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "freyja-5.0-traceability.yaml").read_text(encoding="utf-8"))
    evidence = freyja5_traceability_evidence()

    assert config["version"] == "freyja-5.0"
    assert evidence["source"] == "config/freyja-5.0-traceability.yaml"
    assert set(evidence["important_request_fields"]) >= {
        "trace_id",
        "channel",
        "resolved_user",
        "agent",
        "requested_route",
        "actual_endpoint",
        "actual_model",
        "tool_calls",
        "machine",
        "latency_ms",
        "failures",
        "egress_state",
    }
    assert evidence["audit_chain"]["starts_with"] == "gateway_handoff_created"
    assert "agent_task_started" in evidence["audit_chain"]["includes"]
    assert evidence["egress_events"] == {
        "include_allowed": True,
        "include_denied": True,
        "redact_prompt_preview": True,
    }


def test_freyja5_gateway_config_is_non_director_boundary() -> None:
    config = yaml.safe_load((REPO_ROOT / "config" / "freyja-5.0-gateway.yaml").read_text(encoding="utf-8"))
    evidence = freyja5_gateway_evidence()

    assert config["version"] == "freyja-5.0"
    assert evidence["source"] == "config/freyja-5.0-gateway.yaml"
    assert evidence["host"] == "atlas"
    assert evidence["role"] == "deterministic-ingress-boundary"
    assert set(evidence["allowed_responsibilities"]) == {
        "channel_normalization",
        "identity_resolution",
        "authentication",
        "deterministic_policy",
        "attachment_normalization",
        "trace_envelope",
        "handoff_forwarding",
    }
    assert set(evidence["forbidden_responsibilities"]) == {
        "agent_reasoning",
        "arbitrary_tool_orchestration",
        "physical_model_selection",
        "implicit_cloud_fallback",
    }
    assert evidence["policy"] == {
        "no_agent_reasoning": True,
        "no_arbitrary_tool_orchestration": True,
        "no_physical_model_selection": True,
        "no_implicit_cloud_fallback": True,
        "forwards_to": "agent-runtime-v3",
        "physical_model_selection_owner": "nexus",
        "cloud_fallback": "explicit_only",
    }


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
