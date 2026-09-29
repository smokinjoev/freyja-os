#!/usr/bin/env python3
"""Audit Freyja 6 terminal/tool execution safety boundaries."""

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
DEFAULT_MCP_CONFIG = Path("config/freyja6/mcp/freyja-test.json")
DEFAULT_COMPOSE = Path("deploy/compose/freyja6/compose.yaml")
DEFAULT_TOOL_SMOKE = Path("scripts/freyja6-tool-smoke.py")
DEFAULT_TERMINAL_SERVER = Path("scripts/freyja-terminal-mcp-server.py")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-terminal-safety-audit.json")
EXPECTED_SAFE_COMMANDS = ["pwd", "date", "whoami", "ls", "rg"]
FORBIDDEN_COMMANDS = {
    "rm",
    "mv",
    "cp",
    "chmod",
    "chown",
    "sudo",
    "su",
    "ssh",
    "scp",
    "rsync",
    "curl",
    "wget",
    "python",
    "python3",
    "node",
    "npm",
    "docker",
    "docker-compose",
    "kill",
    "pkill",
    "launchctl",
}
EXPECTED_TERMINAL_TOOLS = [
    "terminal_start",
    "terminal_status",
    "terminal_send",
    "terminal_read",
    "terminal_ctrl_c",
    "terminal_stop",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 terminal safety boundaries.")
    parser.add_argument("--agent-config", type=Path, default=DEFAULT_AGENT_CONFIG)
    parser.add_argument("--tool-boundaries", type=Path, default=DEFAULT_TOOL_BOUNDARIES)
    parser.add_argument("--mcp-config", type=Path, default=DEFAULT_MCP_CONFIG)
    parser.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--tool-smoke", type=Path, default=DEFAULT_TOOL_SMOKE)
    parser.add_argument("--terminal-server", type=Path, default=DEFAULT_TERMINAL_SERVER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(*, agent_config: Path, tool_boundaries: Path, mcp_config: Path, compose: Path, tool_smoke: Path, terminal_server: Path = DEFAULT_TERMINAL_SERVER) -> dict[str, Any]:
    source_check = _check_files(agent_config, tool_boundaries, mcp_config, compose, tool_smoke, terminal_server)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-terminal-safety-audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "checks": [source_check],
            "failures": failures,
            "next_actions": _next_actions(failures),
        }
    agent_doc = _load_yaml(agent_config)
    boundary_doc = _load_yaml(tool_boundaries)
    mcp_doc = _load_json(mcp_config)
    compose_doc = _load_yaml(compose)
    smoke_commands = _tool_smoke_safe_commands(tool_smoke)
    terminal_server_text = _read_text(terminal_server)
    checks = [
        source_check,
        _check_safe_commands(agent_doc, boundary_doc, smoke_commands),
        _check_terminal_mcp_server(boundary_doc, mcp_doc, compose_doc),
        _check_terminal_server_source(terminal_server_text),
        _check_terminal_token_boundary(agent_doc, mcp_doc, compose_doc),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-terminal-safety-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_safe_commands(agent_doc: dict[str, Any], boundary_doc: dict[str, Any], smoke_commands: list[str]) -> dict[str, Any]:
    agent = _agent(agent_doc)
    agent_commands = agent.get("tools", {}).get("terminal", {}).get("safe_commands", [])
    boundary_commands = boundary_doc.get("tool_targets", {}).get("terminal", {}).get("safe_commands", [])
    failures: list[str] = []
    if agent.get("tools", {}).get("terminal", {}).get("enabled") is not True:
        failures.append("Terminal tool must be enabled explicitly for freyja-test validation.")
    if agent_commands != EXPECTED_SAFE_COMMANDS:
        failures.append("Agent terminal safe_commands must match the Freyja 6 non-mutating allowlist.")
    if boundary_commands != EXPECTED_SAFE_COMMANDS:
        failures.append("Tool-boundary terminal safe_commands must match the agent allowlist.")
    forbidden = sorted(FORBIDDEN_COMMANDS.intersection(agent_commands) | FORBIDDEN_COMMANDS.intersection(boundary_commands))
    if forbidden:
        failures.append(f"Forbidden terminal commands are present: {forbidden}.")
    if not set(smoke_commands).issubset(set(EXPECTED_SAFE_COMMANDS)):
        failures.append("Tool smoke safe-command choices must be a subset of the configured allowlist.")
    if "pwd" not in smoke_commands:
        failures.append("Tool smoke must retain pwd as the default safe terminal acceptance command.")
    if failures:
        return {"id": "safe_terminal_allowlist", "status": "fail", "message": "Terminal safe-command policy drifted.", "failures": failures}
    return _passed("safe_terminal_allowlist", "Terminal commands are limited to the Freyja 6 non-mutating allowlist.")


def _check_terminal_mcp_server(boundary_doc: dict[str, Any], mcp_doc: dict[str, Any], compose_doc: dict[str, Any]) -> dict[str, Any]:
    terminal_target = boundary_doc.get("tool_targets", {}).get("terminal", {})
    mcp_target = boundary_doc.get("tool_targets", {}).get("mcp", {})
    servers = mcp_doc.get("mcpServers") if isinstance(mcp_doc.get("mcpServers"), dict) else {}
    terminal = servers.get("freyja-terminal") if isinstance(servers.get("freyja-terminal"), dict) else {}
    compose_env = compose_doc.get("services", {}).get("hermes-freyja-test", {}).get("environment", {})
    failures: list[str] = []
    if terminal_target.get("boundary") != "mcp" or terminal_target.get("server") != "freyja-terminal":
        failures.append("Terminal boundary must be the freyja-terminal MCP server.")
    if "freyja-terminal" not in (mcp_target.get("servers") or []):
        failures.append("MCP tool boundary must include freyja-terminal.")
    if terminal.get("transport") != "streamable_http":
        failures.append("freyja-terminal MCP transport must be streamable_http.")
    if terminal.get("url") != "http://host.docker.internal:8765/mcp":
        failures.append("freyja-terminal MCP URL must stay on the Atlas host boundary.")
    if terminal.get("allowed_tools") != EXPECTED_TERMINAL_TOOLS:
        failures.append("freyja-terminal allowed_tools drifted.")
    if "FREYJA6_TERMINAL_MCP_TOKEN" not in compose_env:
        failures.append("Hermes compose environment must include the terminal MCP token placeholder.")
    if failures:
        return {"id": "terminal_mcp_boundary", "status": "fail", "message": "Terminal MCP boundary is incomplete.", "failures": failures}
    return _passed("terminal_mcp_boundary", "Terminal execution is routed through the freyja-terminal MCP server.")


def _check_terminal_server_source(text: str) -> dict[str, Any]:
    failures: list[str] = []
    required_snippets = [
        'agent not in {"qwen", "shell-test"}',
        'MAX_TEXT_CHARS = int(os.environ.get("FREYJA_TERMINAL_MAX_TEXT_CHARS", "20000"))',
        'MAX_READ_LINES = int(os.environ.get("FREYJA_TERMINAL_MAX_READ_LINES", "2000"))',
        'MAX_READ_CHARS = int(os.environ.get("FREYJA_TERMINAL_MAX_READ_CHARS", "50000"))',
        '["read", session, "--lines", str(bounded_lines), "--max-chars", str(MAX_READ_CHARS)]',
        '[sys.executable, str(BRIDGE), *args]',
        'BearerAuthMiddleware',
    ]
    for snippet in required_snippets:
        if snippet not in text:
            failures.append(f"Terminal MCP server is missing required safety snippet: {snippet}")
    forbidden_snippets = ["shell=True", 'agent == "shell"', '"bash"', '"zsh"']
    for snippet in forbidden_snippets:
        if snippet in text:
            failures.append(f"Terminal MCP server contains forbidden broad-shell snippet: {snippet}")
    if failures:
        return {"id": "terminal_server_source", "status": "fail", "message": "Terminal MCP server implementation is not bounded tightly enough.", "failures": failures}
    return _passed("terminal_server_source", "Terminal MCP server source keeps agent, bridge, auth, send, and read bounds in place.")


def _check_terminal_token_boundary(agent_doc: dict[str, Any], mcp_doc: dict[str, Any], compose_doc: dict[str, Any]) -> dict[str, Any]:
    rendered = json.dumps([agent_doc, mcp_doc, compose_doc], sort_keys=True)
    servers = mcp_doc.get("mcpServers") if isinstance(mcp_doc.get("mcpServers"), dict) else {}
    terminal = servers.get("freyja-terminal") if isinstance(servers.get("freyja-terminal"), dict) else {}
    headers = terminal.get("headers") if isinstance(terminal.get("headers"), dict) else {}
    failures: list[str] = []
    if headers.get("Authorization") != "Bearer ${FREYJA6_TERMINAL_MCP_TOKEN}":
        failures.append("freyja-terminal authorization must use only FREYJA6_TERMINAL_MCP_TOKEN.")
    if "terminal-mcp-local-secret" in rendered or "terminal-mcp-redacted-test" in rendered:
        failures.append("Tracked config must not contain concrete terminal MCP token values.")
    if failures:
        return {"id": "terminal_token_boundary", "status": "fail", "message": "Terminal MCP credential boundary drifted.", "failures": failures}
    return _passed("terminal_token_boundary", "Terminal MCP credentials are represented only as env placeholders.")


def _tool_smoke_safe_commands(path: Path) -> list[str]:
    resolved = _resolve(path)
    try:
        tree = ast.parse(resolved.read_text(encoding="utf-8"))
    except OSError:
        return []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SAFE_COMMANDS":
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        return []
                    return sorted(str(item) for item in value)
    return []


def _read_text(path: Path) -> str:
    resolved = _resolve(path)
    try:
        return resolved.read_text(encoding="utf-8")
    except OSError:
        return ""


def _agent(agent_doc: dict[str, Any]) -> dict[str, Any]:
    agents = agent_doc.get("agents") if isinstance(agent_doc.get("agents"), list) else []
    return next((agent for agent in agents if isinstance(agent, dict) and agent.get("id") == "freyja-test"), {})


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Keep terminal execution constrained to non-mutating MCP-mediated validation commands."]


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required terminal safety source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required terminal safety source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Terminal safety source files are present.")


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
        "report_type": "freyja6-terminal-safety-audit",
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
            mcp_config=args.mcp_config,
            compose=args.compose,
            tool_smoke=args.tool_smoke,
            terminal_server=args.terminal_server,
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
