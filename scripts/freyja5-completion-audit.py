#!/usr/bin/env python3
"""Generate a Freyja 5 completion audit from current evidence artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from freyja.freyja5_config import (  # noqa: E402
    freyja5_agent_evidence,
    freyja5_certification_evidence,
    freyja5_gateway_evidence,
    freyja5_live_blocker_evidence,
    freyja5_mcp_topology_evidence,
    freyja5_plane_evidence,
    freyja5_semantic_route_evidence,
    freyja5_traceability_evidence,
    freyja5_vulcan_evidence,
    freyja5_webgui_evidence,
)


DEFAULT_BUNDLE = Path("certification/reports/freyja5-readiness-bundle-local.json")
DEFAULT_AGENT_EXPORT = Path("certification/reports/freyja5-agent-definitions.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a Freyja 5 completion audit.")
    parser.add_argument("--readiness-bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--agent-export", type=Path, default=DEFAULT_AGENT_EXPORT)
    parser.add_argument(
        "--live-evidence-status",
        type=Path,
        help="Optional freyja5-live-evidence-status JSON report to include in the audit.",
    )
    parser.add_argument("--output", type=Path, default=Path("certification/reports/freyja5-completion-audit.json"))
    return parser


def build_audit(
    *,
    readiness_bundle: Path,
    agent_export: Path | None = None,
    live_evidence_status: Path | None = None,
) -> dict[str, Any]:
    bundle = _load_json(readiness_bundle)
    live_blockers = freyja5_live_blocker_evidence()["joe_required"]
    configured_blocker_ids = [str(blocker["id"]) for blocker in live_blockers]
    live_status = _live_evidence_status(live_evidence_status)
    if live_status.get("status") not in {"not_supplied", "missing"} and not live_status.get("secrets_detected"):
        blocker_ids = [str(blocker) for blocker in live_status.get("remaining_blockers") or []]
    else:
        blocker_ids = configured_blocker_ids
    source_ready = bool(bundle.get("source_ready") is True)
    live_blocked = bool(blocker_ids)
    complete = source_ready and not live_blocked
    remaining_live_blockers = [
        blocker
        for blocker in live_blockers
        if str(blocker.get("id")) in set(blocker_ids)
    ]
    certification = freyja5_certification_evidence()
    webgui = freyja5_webgui_evidence()
    mcp = freyja5_mcp_topology_evidence()
    agent_export_status = _agent_export_status(agent_export) if agent_export else {"status": "not_supplied", "ok": False}
    requirements = [
        _requirement(
            "fallback-preserved",
            "Freyja 4.1 fallback is preserved before Freyja 5 migration work.",
            "complete",
            ["config/freyja-5.0-planes.yaml", "freyja-4.1-baseline-before-5.0-20260831-161448"],
        ),
        _requirement(
            "webgui-side-by-side",
            "WebGUI remains on the existing default model while Freyja 5 is opt-in.",
            "complete" if webgui["default_model_preserved"] == "agent-smith" and webgui["freyja5_opt_in"] else "partial",
            ["config/freyja-5.0-webgui.yaml", "deploy/compose/open-webui/model-proxy.py"],
        ),
        _requirement(
            "gateway-boundary",
            "Gateway is deterministic identity/auth/policy/channel/trace forwarding, not a Director.",
            "complete" if _gateway_policy_ok(freyja5_gateway_evidence()) else "partial",
            ["config/freyja-5.0-gateway.yaml", "src/freyja/agent_gateway.py"],
        ),
        _requirement(
            "semantic-routes",
            "Nexus owns semantic route to physical model/runtime selection.",
            "complete" if set(freyja5_semantic_route_evidence()["routes"]) == {"fast", "general", "deep", "code", "vision", "embedding", "private"} else "partial",
            ["config/freyja-5.0-semantic-routes.yaml", "src/freyja/foundation_seed.py"],
        ),
        _requirement(
            "persistent-agents",
            "Freyja, Cloyd, Benedict, Agent 44, Jenna agent, and Benedict Paralegal are source-controlled logical agents.",
            "complete" if {agent["id"] for agent in freyja5_agent_evidence()} >= {"freyja", "cloyd-gibbler", "benedict", "agent-47", "jennacide", "benedict-paralegal"} else "partial",
            ["src/freyja/foundation_seed.py", "config/freyja-5.0-agents.yaml"],
        ),
        _requirement(
            "mcp-boundaries",
            "MCP servers are placed by capability host and consumed through scoped agent grants.",
            "complete" if mcp["mcp_hosts"] == ["atlas", "iris"] and mcp["default_agent_mcp_servers"] is False else "partial",
            ["config/freyja-5.0-mcp-topology.yaml", "certification/reports/freyja5-agent-definitions.json"],
        ),
        _requirement(
            "traceability",
            "Important requests are traceable end to end with canonical fields.",
            "complete" if len(freyja5_traceability_evidence()["important_request_fields"]) >= 21 else "partial",
            ["config/freyja-5.0-traceability.yaml", "certification/reports/freyja5-readiness-bundle-local.json"],
        ),
        _requirement(
            "certification-targets-a-g",
            "Certification targets A through G are represented with source evidence.",
            "partial" if blocker_ids else "complete",
            ["config/freyja-5.0-certification-targets.yaml", "certification/suites/routing/freyja5_architecture.yaml"],
            blockers=blocker_ids,
        ),
        _requirement(
            "vulcan-live-nexus",
            "Vulcan provides live local-only Nexus presets for semantic routes.",
            "blocked"
            if {"vulcan_nexus_presets", "vulcan_nexus_private_preset"} & set(blocker_ids)
            else "complete",
            ["config/freyja-5.0-semantic-routes.yaml", "FREYJA-5.0-BLOCKERS.md"],
            blockers=[blocker for blocker in ["vulcan_nexus_presets", "vulcan_nexus_private_preset"] if blocker in blocker_ids],
        ),
        _requirement(
            "atlas-msty-go",
            "Atlas persistent agent plane validates Msty Go or preserves compatible substitute boundary.",
            "blocked" if "msty_go_always_on_linux_validation" in blocker_ids else "complete",
            ["scripts/freyja5-export-agent-definitions.py", "FREYJA-5.0-BLOCKERS.md"],
            blockers=["msty_go_always_on_linux_validation"],
        ),
        _requirement(
            "iris-live-apple-mcp",
            "Iris live Apple/macOS MCP session is validated for Calendar target C.",
            "blocked" if "iris_apple_session" in blocker_ids else "complete",
            ["config/freyja-5.0-mcp-topology.yaml", "FREYJA-5.0-BLOCKERS.md"],
            blockers=["iris_apple_session"] if "iris_apple_session" in blocker_ids else [],
        ),
        _requirement(
            "hera-live-voice-avatar",
            "Hera live voice/avatar hardware path is validated.",
            "blocked" if "hera_voice_avatar_hardware" in blocker_ids else "complete",
            ["config/freyja-5.0-planes.yaml", "FREYJA-5.0-BLOCKERS.md"],
            blockers=["hera_voice_avatar_hardware"] if "hera_voice_avatar_hardware" in blocker_ids else [],
        ),
        _requirement(
            "live-tool-sessions",
            "Live MCP-backed tool sessions are reachable from Atlas and proven through delegated tool-call trace evidence.",
            "blocked" if "live_tool_sessions" in blocker_ids else "complete",
            ["config/freyja-5.0-mcp-topology.yaml", "certification/reports/freyja5-live-evidence-status.json"],
            blockers=["live_tool_sessions"] if "live_tool_sessions" in blocker_ids else [],
        ),
    ]
    return {
        "schema_version": "1.0",
        "report_type": "freyja5-completion-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if complete else "source-ready-live-blocked",
        "source_ready": source_ready,
        "live_blocked": live_blocked,
        "readiness_bundle": str(readiness_bundle),
        "agent_export": agent_export_status,
        "live_evidence_status": live_status,
        "certification": {
            "suite": certification["suite"],
            "targets": [target["target"] for target in certification["targets"]],
            "live_blockers": blocker_ids,
        },
        "planes": {
            "atlas": freyja5_plane_evidence()["atlas"]["role"],
            "iris": freyja5_plane_evidence()["iris"]["role"],
            "hera": freyja5_plane_evidence()["hera"]["role"],
            "vulcan": freyja5_vulcan_evidence()["role"] if freyja5_vulcan_evidence() else None,
        },
        "requirements": requirements,
        "remaining_blockers": remaining_live_blockers,
    }


def _requirement(
    requirement_id: str,
    description: str,
    status: str,
    evidence: list[str],
    *,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": requirement_id,
        "description": description,
        "status": status,
        "evidence": evidence,
        "blockers": blockers or [],
    }


def _gateway_policy_ok(evidence: dict[str, Any]) -> bool:
    policy = evidence["policy"]
    return all(
        policy[key] is True
        for key in (
            "no_agent_reasoning",
            "no_arbitrary_tool_orchestration",
            "no_physical_model_selection",
            "no_implicit_cloud_fallback",
        )
    )


def _agent_export_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "ok": False, "status": "missing"}
    payload = _load_json(path)
    return {
        "path": str(path),
        "ok": payload.get("export_type") == "freyja5-agent-definitions"
        and payload.get("source_controlled") is True
        and payload.get("secrets_included") is False,
        "status": "valid" if payload.get("export_type") == "freyja5-agent-definitions" else "invalid",
    }


def _live_evidence_status(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"status": "not_supplied", "ok": False}
    if not path.exists():
        return {"path": str(path), "status": "missing", "ok": False}
    payload = _load_json(path)
    return {
        "path": str(path),
        "status": str(payload.get("status") or "unknown"),
        "ok": bool(payload.get("complete") is True and payload.get("secrets_detected") is not True),
        "closeable_blockers": [str(blocker) for blocker in payload.get("closeable_blockers") or []],
        "remaining_blockers": [str(blocker) for blocker in payload.get("remaining_blockers") or []],
        "unknown_blockers": [str(blocker) for blocker in payload.get("unknown_blockers") or []],
        "secrets_detected": bool(payload.get("secrets_detected") is True),
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audit = build_audit(
        readiness_bundle=args.readiness_bundle,
        agent_export=args.agent_export,
        live_evidence_status=args.live_evidence_status,
    )
    rendered = json.dumps(audit, indent=2, sort_keys=True)
    print(rendered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if audit["status"] == "complete" else 2 if audit["source_ready"] and audit["live_blocked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
