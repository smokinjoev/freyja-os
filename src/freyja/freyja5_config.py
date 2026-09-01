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
