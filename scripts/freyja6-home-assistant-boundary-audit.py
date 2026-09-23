#!/usr/bin/env python3
"""Audit Freyja 6 Home Assistant read-only validation boundaries."""

from __future__ import annotations

import argparse
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
DEFAULT_TOOL_SMOKE = Path("scripts/freyja6-tool-smoke.py")
DEFAULT_CORE_MCP = Path("scripts/freyja-core-mcp-server.py")
DEFAULT_CORE = Path("src/freyja/core.py")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-home-assistant-boundary-audit.json")
EXPECTED_HOME_ASSISTANT_TOOLS = ["home_assistant.read_state", "home_assistant.list_states"]
FORBIDDEN_HOME_ASSISTANT_TOOLS = {
    "home_assistant.control_state",
    "home_assistant.inventory_changes",
    "home_assistant.service_call",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 Home Assistant read-only boundaries.")
    parser.add_argument("--tool-boundaries", type=Path, default=DEFAULT_TOOL_BOUNDARIES)
    parser.add_argument("--tool-smoke", type=Path, default=DEFAULT_TOOL_SMOKE)
    parser.add_argument("--core-mcp", type=Path, default=DEFAULT_CORE_MCP)
    parser.add_argument("--core", type=Path, default=DEFAULT_CORE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(*, tool_boundaries: Path, tool_smoke: Path, core_mcp: Path, core: Path) -> dict[str, Any]:
    source_check = _check_files(tool_boundaries, tool_smoke, core_mcp, core)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-home-assistant-boundary-audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "checks": [source_check],
            "failures": failures,
            "next_actions": _next_actions(failures),
        }
    boundary_doc = _load_yaml(tool_boundaries)
    tool_smoke_text = _read_text(tool_smoke)
    core_mcp_text = _read_text(core_mcp)
    core_text = _read_text(core)
    gateway = _load_gateway()
    checks = [
        source_check,
        _check_tool_boundaries(boundary_doc),
        _check_gateway_policy(gateway),
        _check_core_mcp_wrappers(core_mcp_text),
        _check_core_tools(core_text),
        _check_tool_smoke(tool_smoke_text),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-home-assistant-boundary-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_tool_boundaries(boundary_doc: dict[str, Any]) -> dict[str, Any]:
    home = boundary_doc.get("tool_targets", {}).get("home_assistant", {})
    failures: list[str] = []
    if home.get("status") != "configured":
        failures.append("Home Assistant must be configured for Phase 1 validation.")
    if home.get("boundary") != "mcp" or home.get("server") != "freyja-core-gateway":
        failures.append("Home Assistant must route through freyja-core-gateway MCP.")
    if home.get("gateway_tool") != "tools.call":
        failures.append("Home Assistant must use tools.call.")
    if home.get("core_tools") != EXPECTED_HOME_ASSISTANT_TOOLS:
        failures.append("Home Assistant core_tools must be read_state and list_states only.")
    if "home_assistant_query" not in (home.get("acceptance") or []):
        failures.append("Home Assistant acceptance must include home_assistant_query.")
    if failures:
        return {"id": "home_assistant_tool_boundaries", "status": "fail", "message": "Home Assistant tool boundary drifted.", "failures": failures}
    return _passed("home_assistant_tool_boundaries", "Home Assistant routes through Freyja Core MCP with read-only tools.")


def _check_gateway_policy(gateway: Any) -> dict[str, Any]:
    visible = {tool.name for tool in gateway.TOOL_CATALOG if gateway.is_allowed("freyja-test", tool.name)}
    catalog = {tool.name for tool in gateway.TOOL_CATALOG}
    failures: list[str] = []
    for tool in EXPECTED_HOME_ASSISTANT_TOOLS:
        if tool not in visible:
            failures.append(f"freyja-test policy is missing {tool}.")
    exposed_forbidden = sorted(tool for tool in FORBIDDEN_HOME_ASSISTANT_TOOLS if tool in visible)
    if exposed_forbidden:
        failures.append("freyja-test policy exposes forbidden Home Assistant tools: " + ", ".join(exposed_forbidden))
    cataloged_forbidden = sorted(tool for tool in FORBIDDEN_HOME_ASSISTANT_TOOLS if tool in catalog)
    if cataloged_forbidden:
        failures.append("Freyja 6 gateway catalog must not include Home Assistant mutation tools: " + ", ".join(cataloged_forbidden))
    if failures:
        return {"id": "home_assistant_gateway_policy", "status": "fail", "message": "Freyja Core Home Assistant policy drifted.", "failures": failures}
    return _passed("home_assistant_gateway_policy", "freyja-test can read/list Home Assistant state and cannot control devices.")


def _check_core_mcp_wrappers(text: str) -> dict[str, Any]:
    required = [
        '@mcp.tool(name="home_assistant.read_state"',
        '@mcp.tool(name="home_assistant.list_states"',
        '"home_assistant.read_state"',
        '"home_assistant.list_states"',
    ]
    missing = [item for item in required if item not in text]
    forbidden = sorted(tool for tool in FORBIDDEN_HOME_ASSISTANT_TOOLS if tool in text)
    if missing or forbidden:
        return {
            "id": "home_assistant_core_mcp_wrappers",
            "status": "fail",
            "message": "Home Assistant MCP wrapper drifted.",
            "missing": missing,
            "forbidden": forbidden,
        }
    return _passed("home_assistant_core_mcp_wrappers", "MCP wrapper exposes only read_state and list_states.")


def _check_core_tools(text: str) -> dict[str, Any]:
    required = [
        '"home_assistant.read_state"',
        '"home_assistant.list_states"',
        "home_assistant_read_state_tool",
        "home_assistant_list_states_tool",
    ]
    missing = [item for item in required if item not in text]
    forbidden = sorted(tool for tool in FORBIDDEN_HOME_ASSISTANT_TOOLS if tool in text)
    if missing or forbidden:
        return {
            "id": "home_assistant_core_tools",
            "status": "fail",
            "message": "Freyja Core Home Assistant surface drifted.",
            "missing": missing,
            "forbidden": forbidden,
        }
    return _passed("home_assistant_core_tools", "Freyja Core exposes only read-only Home Assistant tools for Freyja 6.")


def _check_tool_smoke(text: str) -> dict[str, Any]:
    required = [
        '"home_assistant.list_states"',
        '"source": "freyja6-tool-smoke"',
        '"home_assistant_query"',
        '"entity_id_redacted": "domain:"',
        '("states" in result_keys or "entities" in result_keys)',
        '"states_count"',
        'item["states_count"] > 0',
        'default=os.environ.get("FREYJA6_HOME_SMOKE_DOMAIN", "sensor")',
    ]
    missing = [item for item in required if item not in text]
    forbidden = sorted(tool for tool in FORBIDDEN_HOME_ASSISTANT_TOOLS if tool in text)
    if missing or forbidden:
        return {
            "id": "home_assistant_tool_smoke",
            "status": "fail",
            "message": "Home Assistant tool smoke drifted.",
            "missing": missing,
            "forbidden": forbidden,
        }
    return _passed("home_assistant_tool_smoke", "Tool smoke records redacted read-only Home Assistant list_states evidence.")


def _load_gateway() -> Any:
    from freyja import mcp_gateway

    return mcp_gateway


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Run the non-mutating tool smoke after Home Assistant is reachable through Freyja Core."]


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required Home Assistant boundary source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required Home Assistant boundary source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Home Assistant boundary source files are present.")


def _load_yaml(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    try:
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except OSError:
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
        "report_type": "freyja6-home-assistant-boundary-audit",
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
        else build_report(tool_boundaries=args.tool_boundaries, tool_smoke=args.tool_smoke, core_mcp=args.core_mcp, core=args.core)
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
