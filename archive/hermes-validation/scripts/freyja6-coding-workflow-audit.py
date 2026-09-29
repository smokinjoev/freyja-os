#!/usr/bin/env python3
"""Audit Freyja 6 coding workflow delegation through OpenCode."""

from __future__ import annotations

import argparse
import ast
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

DEFAULT_AGENT_CONFIG = Path("config/freyja6/freyja-test.yaml")
DEFAULT_TOOL_BOUNDARIES = Path("config/freyja6/tool-boundaries.yaml")
DEFAULT_CORE = Path("src/freyja/core.py")
DEFAULT_CORE_SERVER = Path("scripts/freyja-core-mcp-server.py")
DEFAULT_TOOL_SMOKE = Path("scripts/freyja6-tool-smoke.py")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-coding-workflow-audit.json")
EXPECTED_OPENCODE_TOOLS = ["opencode.start", "opencode.status", "opencode.send", "opencode.read", "opencode.stop"]
FORBIDDEN_CODING_TOOLS = ["opencode.shell"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 OpenCode coding workflow boundary.")
    parser.add_argument("--agent-config", type=Path, default=DEFAULT_AGENT_CONFIG)
    parser.add_argument("--tool-boundaries", type=Path, default=DEFAULT_TOOL_BOUNDARIES)
    parser.add_argument("--core", type=Path, default=DEFAULT_CORE)
    parser.add_argument("--core-server", type=Path, default=DEFAULT_CORE_SERVER)
    parser.add_argument("--tool-smoke", type=Path, default=DEFAULT_TOOL_SMOKE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(*, agent_config: Path, tool_boundaries: Path, core: Path, core_server: Path, tool_smoke: Path) -> dict[str, Any]:
    source_check = _check_files(agent_config, tool_boundaries, core, core_server, tool_smoke)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-coding-workflow-audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "checks": [source_check],
            "failures": failures,
            "next_actions": _next_actions(failures),
        }
    agent_doc = _load_yaml(agent_config)
    boundary_doc = _load_yaml(tool_boundaries)
    core_text = _read_text(core)
    server_text = _read_text(core_server)
    smoke_text = _read_text(tool_smoke)
    checks = [
        source_check,
        _check_agent_executor(agent_doc, boundary_doc),
        _check_core_opencode_mapping(core_text),
        _check_core_server_tools(server_text),
        _check_tool_smoke(smoke_text),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-coding-workflow-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_agent_executor(agent_doc: dict[str, Any], boundary_doc: dict[str, Any]) -> dict[str, Any]:
    agent = _agent(agent_doc)
    coding = agent.get("tools", {}).get("coding_agent", {})
    target = boundary_doc.get("tool_targets", {}).get("coding_agent", {})
    failures: list[str] = []
    if coding.get("enabled") is not True:
        failures.append("Agent coding_agent must be enabled for Phase 1 validation.")
    if coding.get("executor") != "opencode":
        failures.append("Agent coding executor must remain opencode.")
    if target.get("boundary") != "mcp" or target.get("server") != "freyja-core-gateway":
        failures.append("Coding workflow must route through freyja-core-gateway MCP.")
    if target.get("gateway_tool") != "tools.call":
        failures.append("Coding workflow must use tools.call.")
    if target.get("executor") != "opencode":
        failures.append("Tool-boundary coding executor must remain opencode.")
    if target.get("core_tools") != EXPECTED_OPENCODE_TOOLS:
        failures.append("Coding core_tools must match the approved OpenCode actions.")
    if failures:
        return {"id": "agent_coding_executor", "status": "fail", "message": "Freyja 6 coding executor boundary drifted.", "failures": failures}
    return _passed("agent_coding_executor", "freyja-test delegates coding through OpenCode via Freyja Core MCP.")


def _check_core_opencode_mapping(core_text: str) -> dict[str, Any]:
    failures: list[str] = []
    for import_name in ("_opencode_start", "_opencode_send", "_opencode_status", "_opencode_output", "_opencode_stop"):
        if import_name not in core_text:
            failures.append(f"Freyja Core is missing {import_name}.")
    for tool_name in EXPECTED_OPENCODE_TOOLS:
        if f'"{tool_name}"' not in core_text:
            failures.append(f"Freyja Core is missing {tool_name}.")
    for forbidden in FORBIDDEN_CODING_TOOLS:
        if f'"{forbidden}"' in core_text:
            failures.append(f"Forbidden coding tool is exposed in Freyja Core: {forbidden}.")
    if 'action_map = {"read": "output"}' not in core_text:
        failures.append("Freyja Core must map opencode.read to agent_control output.")
    if failures:
        return {"id": "core_opencode_mapping", "status": "fail", "message": "Freyja Core OpenCode mapping drifted.", "failures": failures}
    return _passed("core_opencode_mapping", "Freyja Core maps approved opencode tools to agent_control actions.")


def _check_core_server_tools(server_text: str) -> dict[str, Any]:
    failures: list[str] = []
    for tool_name in EXPECTED_OPENCODE_TOOLS:
        if f'name="{tool_name}"' not in server_text:
            failures.append(f"Freyja Core MCP wrapper is missing {tool_name}.")
    for forbidden in FORBIDDEN_CODING_TOOLS:
        if f'name="{forbidden}"' in server_text:
            failures.append(f"Forbidden coding tool is exposed by MCP wrapper: {forbidden}.")
    if failures:
        return {"id": "core_server_opencode_tools", "status": "fail", "message": "Freyja Core MCP OpenCode wrapper drifted.", "failures": failures}
    return _passed("core_server_opencode_tools", "Freyja Core MCP wrapper exposes only approved OpenCode tools.")


def _check_tool_smoke(smoke_text: str) -> dict[str, Any]:
    failures: list[str] = []
    if '"opencode.status"' not in smoke_text:
        failures.append("Tool smoke must validate coding workflow with opencode.status.")
    if '"executor": "opencode"' not in smoke_text:
        failures.append("Tool smoke acceptance evidence must record executor=opencode.")
    if "freyja-core-coder" not in smoke_text:
        failures.append("Tool smoke must use the freyja-core-coder alias.")
    if "_coding_workflow_result_ok" not in smoke_text:
        failures.append("Tool smoke must guard coding workflow acceptance with a dedicated OpenCode alias validator.")
    if "coding workflow must target freyja-core-coder" not in smoke_text:
        failures.append("Tool smoke logs must explain coding workflow alias failures.")
    for forbidden in FORBIDDEN_CODING_TOOLS:
        if forbidden in smoke_text:
            failures.append(f"Tool smoke must not use forbidden coding tool {forbidden}.")
    if failures:
        return {"id": "tool_smoke_coding", "status": "fail", "message": "Coding workflow smoke drifted.", "failures": failures}
    return _passed("tool_smoke_coding", "Tool smoke records the OpenCode coding workflow through opencode.status.")


def _agent(agent_doc: dict[str, Any]) -> dict[str, Any]:
    agents = agent_doc.get("agents") if isinstance(agent_doc.get("agents"), list) else []
    return next((agent for agent in agents if isinstance(agent, dict) and agent.get("id") == "freyja-test"), {})


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Keep coding work delegated through Freyja Core OpenCode tools."]


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required coding workflow source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required coding workflow source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Coding workflow source files are present.")


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
        "report_type": "freyja6-coding-workflow-audit",
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
        else build_report(
            agent_config=args.agent_config,
            tool_boundaries=args.tool_boundaries,
            core=args.core,
            core_server=args.core_server,
            tool_smoke=args.tool_smoke,
        )
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
