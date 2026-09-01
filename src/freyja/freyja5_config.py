from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
FREYJA5_LIVE_BLOCKERS_PATH = REPO_ROOT / "config" / "freyja-5.0-live-blockers.yaml"
FREYJA5_SEMANTIC_ROUTES_PATH = REPO_ROOT / "config" / "freyja-5.0-semantic-routes.yaml"
FREYJA5_WEBGUI_PATH = REPO_ROOT / "config" / "freyja-5.0-webgui.yaml"
FREYJA5_TRACEABILITY_PATH = REPO_ROOT / "config" / "freyja-5.0-traceability.yaml"
FREYJA5_PLANES_PATH = REPO_ROOT / "config" / "freyja-5.0-planes.yaml"
FREYJA5_GATEWAY_PATH = REPO_ROOT / "config" / "freyja-5.0-gateway.yaml"
FREYJA5_CERTIFICATION_SUITE_PATH = REPO_ROOT / "certification" / "suites" / "routing" / "freyja5_architecture.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def freyja5_live_blocker_evidence() -> dict[str, Any]:
    data = _load_yaml(FREYJA5_LIVE_BLOCKERS_PATH)
    joe_required = data.get("joe_required") if isinstance(data.get("joe_required"), list) else []
    return {
        "source": str(data.get("source_document") or "FREYJA-5.0-BLOCKERS.md"),
        "joe_required": [
            {
                "id": str(entry.get("id")),
                "component": str(entry.get("component")),
                "requires": [str(item) for item in entry.get("requires") or []],
                "next_actions": [str(item) for item in entry.get("next_actions") or []],
            }
            for entry in joe_required
            if isinstance(entry, dict) and entry.get("id") and entry.get("component")
        ],
        "secrets_in_source": bool(data.get("secrets_in_source") is True),
        "continue_independent_work": bool(data.get("continue_independent_work")),
    }


def freyja5_certification_target_blockers() -> dict[str, list[str]]:
    data = _load_yaml(FREYJA5_LIVE_BLOCKERS_PATH)
    targets = data.get("certification_targets") if isinstance(data.get("certification_targets"), dict) else {}
    return {
        str(target): [str(blocker) for blocker in (details.get("live_blockers") or [])]
        for target, details in targets.items()
        if isinstance(details, dict)
    }


def freyja5_certification_live_blocker_ids() -> list[str]:
    blockers = freyja5_live_blocker_evidence()["joe_required"]
    return [str(blocker["id"]) for blocker in blockers]


def freyja5_semantic_route_evidence() -> dict[str, Any]:
    data = _load_yaml(FREYJA5_SEMANTIC_ROUTES_PATH)
    routes = data.get("routes") if isinstance(data.get("routes"), dict) else {}
    return {
        "source": "config/freyja-5.0-semantic-routes.yaml",
        "owner": str(data.get("owner") or ""),
        "cloud_fallback": str(data.get("cloud_fallback") or ""),
        "routes": {
            str(route): {
                "capability": str(details.get("capability") or ""),
                "preferred_runtime": str(details.get("preferred_runtime") or ""),
                **(
                    {"egress_policy": str(details["egress_policy"])}
                    if isinstance(details, dict) and details.get("egress_policy")
                    else {}
                ),
            }
            for route, details in sorted(routes.items())
            if isinstance(details, dict)
        },
    }


def freyja5_webgui_evidence() -> dict[str, Any]:
    data = _load_yaml(FREYJA5_WEBGUI_PATH)
    return {
        "source": "config/freyja-5.0-webgui.yaml",
        "openai_compatible": str(data.get("surface") or "") == "openai-compatible",
        "default_model_preserved": str(data.get("default_model_preserved") or ""),
        "freyja5_model": str(data.get("freyja5_model") or ""),
        "freyja5_opt_in": bool(data.get("freyja5_opt_in")),
        "media_content_parts": [str(part) for part in data.get("media_content_parts") or []],
        "inline_data_url_only": bool(data.get("inline_data_url_only")),
        "cloud_fallback": bool(data.get("cloud_fallback") is True),
        "live_inference_default": bool(data.get("live_inference_default") is True),
    }


def freyja5_traceability_evidence() -> dict[str, Any]:
    data = _load_yaml(FREYJA5_TRACEABILITY_PATH)
    audit_chain = data.get("audit_chain") if isinstance(data.get("audit_chain"), dict) else {}
    egress_events = data.get("egress_events") if isinstance(data.get("egress_events"), dict) else {}
    return {
        "source": "config/freyja-5.0-traceability.yaml",
        "important_request_fields": [str(field) for field in data.get("important_request_fields") or []],
        "audit_chain": {
            "starts_with": str(audit_chain.get("starts_with") or ""),
            "includes": [str(event) for event in audit_chain.get("includes") or []],
            "terminal_events": [str(event) for event in audit_chain.get("terminal_events") or []],
        },
        "egress_events": {
            "include_allowed": bool(egress_events.get("include_allowed")),
            "include_denied": bool(egress_events.get("include_denied")),
            "redact_prompt_preview": bool(egress_events.get("redact_prompt_preview")),
        },
    }


def freyja5_plane_evidence() -> dict[str, Any]:
    data = _load_yaml(FREYJA5_PLANES_PATH)
    return {
        "source": "config/freyja-5.0-planes.yaml",
        "atlas": dict(data.get("atlas") or {}),
        "iris": dict(data.get("iris") or {}),
        "hera": dict(data.get("hera") or {}),
        "vulcan": dict(data.get("vulcan") or {}),
    }


def freyja5_live_inference_evidence(
    *,
    enabled: bool,
    nexus_base_url: str | None,
    nexus_api_key: str | None,
) -> dict[str, Any]:
    nexus_base_url_configured = bool(nexus_base_url)
    return {
        "enabled": bool(enabled),
        "nexus_base_url_configured": nexus_base_url_configured,
        "nexus_api_key_configured": bool(nexus_api_key),
        "cloud_fallback": False,
        "ready": bool(enabled) and nexus_base_url_configured,
    }


def freyja5_iris_readiness_evidence(
    *,
    macagent_enabled: bool,
    macagent_base_url: str | None,
    macagent_token: str | None,
) -> dict[str, Any]:
    planes = freyja5_plane_evidence()
    iris_plane = dict(planes["iris"])
    iris_plane.update(
        {
            "macagent_base_url_configured": bool(macagent_base_url),
            "macagent_enabled": bool(macagent_enabled),
            "macagent_token_configured": bool(macagent_token),
        }
    )
    return iris_plane


def freyja5_gateway_evidence() -> dict[str, Any]:
    data = _load_yaml(FREYJA5_GATEWAY_PATH)
    policy = data.get("policy") if isinstance(data.get("policy"), dict) else {}
    return {
        "source": "config/freyja-5.0-gateway.yaml",
        "host": str(data.get("host") or ""),
        "role": str(data.get("role") or ""),
        "protocol": str(data.get("protocol") or ""),
        "allowed_responsibilities": [str(item) for item in data.get("allowed_responsibilities") or []],
        "forbidden_responsibilities": [str(item) for item in data.get("forbidden_responsibilities") or []],
        "policy": {
            "no_agent_reasoning": bool(policy.get("no_agent_reasoning")),
            "no_arbitrary_tool_orchestration": bool(policy.get("no_arbitrary_tool_orchestration")),
            "no_physical_model_selection": bool(policy.get("no_physical_model_selection")),
            "no_implicit_cloud_fallback": bool(policy.get("no_implicit_cloud_fallback")),
            "forwards_to": str(policy.get("forwards_to") or ""),
            "physical_model_selection_owner": str(policy.get("physical_model_selection_owner") or ""),
            "cloud_fallback": str(policy.get("cloud_fallback") or ""),
        },
    }


def freyja5_agent_evidence() -> list[dict[str, Any]]:
    from freyja.foundation_seed import PERSISTENT_AGENTS

    return [
        {
            "id": agent.agent_id,
            "display_name": agent.display_name,
            "logical_display_name": agent.logical_display_name or agent.display_name,
            "owner": agent.owner,
            "security_domain": agent.security_domain_id.value,
            "home_machine": agent.home_machine_id,
            "private_memory_scope": agent.private_memory_scope,
            "shared_memory_scopes": sorted(agent.shared_memory_scopes),
            "tool_grant_count": len(agent.tool_grants),
            "cloud_egress_policy": agent.cloud_egress_policy_id,
        }
        for agent in PERSISTENT_AGENTS
    ]


def freyja5_mcp_topology_evidence() -> dict[str, Any]:
    from freyja.foundation_seed import PERSISTENT_AGENTS, TOOL_CAPABILITIES

    data = _load_yaml(REPO_ROOT / "config" / "freyja-5.0-mcp-topology.yaml")
    servers = data.get("servers") if isinstance(data.get("servers"), list) else []
    non_mcp_boundaries = data.get("non_mcp_boundaries") if isinstance(data.get("non_mcp_boundaries"), list) else []
    policy = data.get("policy") if isinstance(data.get("policy"), dict) else {}
    mcp_hosts_by_tool = {
        str(tool_id): str(server.get("host"))
        for server in servers
        if isinstance(server, dict) and server.get("host") and isinstance(server.get("exposes"), list)
        for tool_id in server["exposes"]
    }
    mcp_tool_ids = {tool.tool_id for tool in TOOL_CAPABILITIES if tool.protocol == "mcp"}
    return {
        "source": "config/freyja-5.0-mcp-topology.yaml",
        "available": bool(servers),
        "default_agent_mcp_servers": bool(data.get("default_agent_mcp_servers")),
        "mcp_hosts": sorted({str(server.get("host")) for server in servers if isinstance(server, dict) and server.get("host")}),
        "servers": [
            {
                "id": str(server.get("id")),
                "host": str(server.get("host")),
                "protocol": str(server.get("protocol")),
                "role": str(server.get("role")),
                "status": str(server.get("status")),
                "exposes": [str(tool_id) for tool_id in server.get("exposes") or []],
                "consumers": str(server.get("consumers") or ""),
                "egress": str(server.get("egress") or ""),
            }
            for server in servers
            if isinstance(server, dict) and server.get("id") and server.get("host")
        ],
        "mcp_tool_count": sum(
            len(server.get("exposes") or ())
            for server in servers
            if isinstance(server, dict) and isinstance(server.get("exposes"), list)
        ),
        "vulcan_protocol": next(
            (
                str(boundary.get("protocol"))
                for boundary in non_mcp_boundaries
                if isinstance(boundary, dict) and boundary.get("id") == "vulcan-nexus"
            ),
            None,
        ),
        "agent_consumption": dict(sorted((data.get("agent_consumption") or {}).items())),
        "agent_grants": [
            {
                "agent_id": agent.agent_id,
                "mcp_tool_ids": sorted(mcp_tool_ids.intersection(agent.tool_grants)),
                "mcp_tool_count": len(mcp_tool_ids.intersection(agent.tool_grants)),
                "mcp_hosts": sorted(
                    {
                        mcp_hosts_by_tool[tool_id]
                        for tool_id in mcp_tool_ids.intersection(agent.tool_grants)
                        if tool_id in mcp_hosts_by_tool
                    }
                ),
            }
            for agent in PERSISTENT_AGENTS
        ],
        "gateway_policy": {
            "host": "atlas",
            "role": "deterministic-ingress-boundary",
            "no_agent_reasoning": bool(policy.get("no_agent_reasoning_in_mcp_servers")),
            "no_physical_model_selection": bool(policy.get("no_physical_model_selection_in_gateway")),
            "forbidden_responsibilities": [
                "agent_reasoning",
                "arbitrary_tool_orchestration",
                "physical_model_selection",
                "implicit_cloud_fallback",
            ],
        },
    }


def freyja5_readiness_mcp_evidence() -> dict[str, Any]:
    evidence = freyja5_mcp_topology_evidence()
    return {
        "default_agent_mcp_servers": evidence["default_agent_mcp_servers"],
        "hosts": evidence["mcp_hosts"],
        "tool_count": evidence["mcp_tool_count"],
        "source_controlled_grants": True,
        "agent_consumption": evidence["agent_consumption"],
        "agent_grants": evidence["agent_grants"],
    }


def freyja5_readiness_ok() -> bool:
    route_evidence = freyja5_semantic_route_evidence()
    topology_evidence = freyja5_mcp_topology_evidence()
    routes = route_evidence.get("routes") if isinstance(route_evidence.get("routes"), dict) else {}
    return bool(routes) and bool(topology_evidence.get("mcp_hosts"))


def freyja5_vulcan_evidence() -> dict[str, Any] | None:
    route_evidence = freyja5_semantic_route_evidence()
    plane_evidence = freyja5_plane_evidence()
    topology = _load_yaml(REPO_ROOT / "config" / "freyja-5.0-mcp-topology.yaml")
    raw_boundaries = topology.get("non_mcp_boundaries")
    non_mcp_boundaries = raw_boundaries if isinstance(raw_boundaries, list) else []
    routes = route_evidence["routes"] if isinstance(route_evidence.get("routes"), dict) else {}
    vulcan_plane = plane_evidence["vulcan"] if isinstance(plane_evidence.get("vulcan"), dict) else {}
    return next(
        (
            {
                "host": str(boundary.get("host") or ""),
                "protocol": str(boundary.get("protocol") or ""),
                "role": str(boundary.get("role") or ""),
                "owner": route_evidence["owner"],
                "owns": [str(item) for item in boundary.get("owns") or []],
                "semantic_route_presets": {
                    str(route): str(details.get("preferred_runtime"))
                    for route, details in sorted(routes.items())
                    if isinstance(details, dict) and details.get("preferred_runtime")
                },
                "route_count": len(routes),
                "local_by_default": bool(vulcan_plane.get("local_by_default")),
                "cloud_fallback": route_evidence["cloud_fallback"],
                "live_blockers": [str(blocker) for blocker in vulcan_plane.get("live_blockers") or []],
            }
            for boundary in non_mcp_boundaries
            if isinstance(boundary, dict) and boundary.get("id") == "vulcan-nexus"
        ),
        None,
    )


def freyja5_certification_evidence() -> dict[str, Any]:
    suite = _load_yaml(FREYJA5_CERTIFICATION_SUITE_PATH)
    cases = suite.get("cases") if isinstance(suite.get("cases"), list) else []
    live_blockers_by_target = freyja5_certification_target_blockers()
    targets: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        name = str(case.get("name") or "")
        target = name.split("-", 1)[0]
        if target not in live_blockers_by_target:
            continue
        targets.append(
            {
                "target": target.upper(),
                "case": name,
                "skeleton": "covered",
                "live": "blocked" if live_blockers_by_target[target] else "not_required",
                "live_blockers": live_blockers_by_target[target],
            }
        )
    return {
        "source": "certification/suites/routing/freyja5_architecture.yaml",
        "suite": str(suite.get("name") or ""),
        "targets": targets,
        "live_blockers": freyja5_certification_live_blocker_ids(),
    }


def freyja5_readiness_certification_evidence() -> dict[str, Any]:
    evidence = freyja5_certification_evidence()
    return {
        "suite": evidence["suite"],
        "targets": evidence["targets"],
        "live_blockers": evidence["live_blockers"],
    }
