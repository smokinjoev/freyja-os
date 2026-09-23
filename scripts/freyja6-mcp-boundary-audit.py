#!/usr/bin/env python3
"""Audit Freyja 6 Freyja Core MCP tool boundaries."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

DEFAULT_TOOL_BOUNDARIES = Path("config/freyja6/tool-boundaries.yaml")
DEFAULT_MCP_CONFIG = Path("config/freyja6/mcp/freyja-test.json")
DEFAULT_CORE_SERVER = Path("scripts/freyja-core-mcp-server.py")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-mcp-boundary-audit.json")
DISCOVERY_TOOLS = ["tools.search", "tools.profile", "tools.call"]
REQUIRED_CORE_TOOLS = [
    "status.check",
    "calendar.resolve_date",
    "calendar.list_events",
    "calendar.create_event",
    "home_assistant.read_state",
    "home_assistant.list_states",
    "opencode.start",
    "opencode.status",
    "opencode.send",
    "opencode.read",
    "opencode.stop",
    "memory.search",
    "memory.write",
]
FORBIDDEN_FREYJA_TEST_TOOLS = [
    "calendar.delete_event",
    "home_assistant.control_state",
    "opencode.shell",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 MCP tool boundary posture.")
    parser.add_argument("--tool-boundaries", type=Path, default=DEFAULT_TOOL_BOUNDARIES)
    parser.add_argument("--mcp-config", type=Path, default=DEFAULT_MCP_CONFIG)
    parser.add_argument("--core-server", type=Path, default=DEFAULT_CORE_SERVER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(*, tool_boundaries: Path, mcp_config: Path, core_server: Path) -> dict[str, Any]:
    source_check = _check_files(tool_boundaries, mcp_config, core_server)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-mcp-boundary-audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "checks": [source_check],
            "failures": failures,
            "next_actions": _next_actions(failures),
        }
    boundary_doc = _load_yaml(tool_boundaries)
    mcp_doc = _load_json(mcp_config)
    gateway = _load_gateway()
    server_text = _read_text(core_server)
    checks = [
        source_check,
        _check_mcp_config(mcp_doc),
        _check_tool_boundaries(boundary_doc),
        _check_gateway_policy(gateway),
        _check_core_server_wrapper(server_text),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-mcp-boundary-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_mcp_config(mcp_doc: dict[str, Any]) -> dict[str, Any]:
    servers = mcp_doc.get("mcpServers") if isinstance(mcp_doc.get("mcpServers"), dict) else {}
    core = servers.get("freyja-core-gateway") if isinstance(servers.get("freyja-core-gateway"), dict) else {}
    failures: list[str] = []
    if core.get("transport") != "streamable_http":
        failures.append("freyja-core-gateway transport must be streamable_http.")
    if core.get("url") != "http://host.docker.internal:8766/mcp":
        failures.append("freyja-core-gateway URL must stay on the Atlas host MCP boundary.")
    if core.get("headers", {}).get("Authorization") != "Bearer ${FREYJA6_CORE_MCP_TOKEN}":
        failures.append("freyja-core-gateway authorization must use FREYJA6_CORE_MCP_TOKEN.")
    if core.get("allowed_tools") != DISCOVERY_TOOLS:
        failures.append("Hermes MCP config must expose only discovery/call wrapper tools for Freyja Core.")
    if failures:
        return {"id": "mcp_config", "status": "fail", "message": "Freyja Core MCP config drifted.", "failures": failures}
    return _passed("mcp_config", "Hermes sees Freyja Core through the discovery/call MCP wrapper only.")


def _check_tool_boundaries(boundary_doc: dict[str, Any]) -> dict[str, Any]:
    targets = boundary_doc.get("tool_targets") if isinstance(boundary_doc.get("tool_targets"), dict) else {}
    failures: list[str] = []
    expected = {
        "calendar": ["calendar.list_events", "calendar.resolve_date", "calendar.create_event"],
        "home_assistant": ["home_assistant.read_state", "home_assistant.list_states"],
        "coding_agent": ["opencode.start", "opencode.status", "opencode.send", "opencode.read", "opencode.stop"],
    }
    for target, tools in expected.items():
        config = targets.get(target, {})
        if config.get("boundary") != "mcp" or config.get("server") != "freyja-core-gateway":
            failures.append(f"{target} must route through freyja-core-gateway MCP.")
        if config.get("gateway_tool") != "tools.call":
            failures.append(f"{target} must use tools.call as the gateway tool.")
        if config.get("core_tools") != tools:
            failures.append(f"{target} core_tools drifted.")
    mcp_servers = targets.get("mcp", {}).get("servers") or []
    if "freyja-core-gateway" not in mcp_servers:
        failures.append("MCP target must include freyja-core-gateway.")
    if failures:
        return {"id": "tool_boundaries", "status": "fail", "message": "Freyja 6 tool-boundary manifest drifted.", "failures": failures}
    return _passed("tool_boundaries", "Calendar, Home Assistant, coding, and MCP surfaces route through Freyja Core MCP.")


def _check_gateway_policy(gateway: Any) -> dict[str, Any]:
    failures: list[str] = []
    visible = {tool.name for tool in gateway.TOOL_CATALOG if gateway.is_allowed("freyja-test", tool.name)}
    missing = sorted(set(REQUIRED_CORE_TOOLS) - visible)
    forbidden_visible = sorted(tool for tool in FORBIDDEN_FREYJA_TEST_TOOLS if tool in visible)
    if missing:
        failures.append(f"freyja-test policy is missing required tools: {missing}.")
    if forbidden_visible:
        failures.append(f"freyja-test policy exposes forbidden tools: {forbidden_visible}.")
    catalog = {tool.name: tool for tool in gateway.TOOL_CATALOG}
    if catalog.get("calendar.delete_event", None) is None or catalog["calendar.delete_event"].risk != "destructive":
        failures.append("calendar.delete_event must remain cataloged as destructive.")
    if gateway.current_agent() != "generic":
        failures.append("Gateway default agent context must fail closed to generic.")
    default_visible = {tool.name for tool in gateway.TOOL_CATALOG if gateway.is_allowed(gateway.current_agent(), tool.name)}
    if default_visible != {"status.check", "memory.search"}:
        failures.append(f"Default generic policy must expose only status.check and memory.search: {sorted(default_visible)}.")
    if failures:
        return {"id": "gateway_policy", "status": "fail", "message": "Freyja Core gateway policy is not correct for freyja-test.", "failures": failures}
    return _passed("gateway_policy", "freyja-test gets required explicit tools and unauthenticated callers fail closed to generic.")


def _check_core_server_wrapper(server_text: str) -> dict[str, Any]:
    failures: list[str] = []
    for tool_name in DISCOVERY_TOOLS + REQUIRED_CORE_TOOLS + ["calendar.delete_event"]:
        if f'name="{tool_name}"' not in server_text:
            failures.append(f"Freyja Core MCP server wrapper is missing {tool_name}.")
    if failures:
        return {"id": "core_server_wrapper", "status": "fail", "message": "Freyja Core MCP server wrapper is incomplete.", "failures": failures}
    return _passed("core_server_wrapper", "Freyja Core MCP server wrapper exposes the expected registered tools.")


def _load_gateway() -> Any:
    from freyja import mcp_gateway

    return mcp_gateway


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Keep Freyja 6 explicit tools mediated through Freyja Core MCP."]


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required Freyja Core MCP boundary source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required Freyja Core MCP boundary source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Freyja Core MCP boundary source files are present.")


def _load_yaml(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    try:
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_json(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    resolved = _resolve(path)
    try:
        return resolved.read_text(encoding="utf-8")
    except OSError:
        return ""


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _passed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "pass", "message": message}


def _output_path_failure(output: Path) -> str | None:
    if output.is_symlink():
        return f"output path must not be a symlink: {output.name}"
    if output.exists() and not output.is_file():
        return f"output path must be a regular file: {output.name}"
    return None


def _error_report(error: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-mcp-boundary-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "status": "fail",
        "error": error,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_failure = _output_path_failure(args.output)
    report = (
        _error_report(output_failure)
        if output_failure
        else build_report(tool_boundaries=args.tool_boundaries, mcp_config=args.mcp_config, core_server=args.core_server)
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
