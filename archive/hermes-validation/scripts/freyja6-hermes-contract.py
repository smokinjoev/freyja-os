#!/usr/bin/env python3
"""Validate the Freyja 6 Hermes runtime contract against tracked config."""

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

DEFAULT_CONTRACT = Path("config/freyja6/hermes-runtime-contract.yaml")
DEFAULT_AGENT_CONFIG = Path("config/freyja6/freyja-test.yaml")
DEFAULT_MCP_CONFIG = Path("config/freyja6/mcp/freyja-test.json")
DEFAULT_SCHEDULES = Path("config/freyja6/schedules.yaml")
DEFAULT_COMPOSE = Path("deploy/compose/freyja6/compose.yaml")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-hermes-contract.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Freyja 6 Hermes runtime contract drift.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--agent-config", type=Path, default=DEFAULT_AGENT_CONFIG)
    parser.add_argument("--mcp-config", type=Path, default=DEFAULT_MCP_CONFIG)
    parser.add_argument("--schedules", type=Path, default=DEFAULT_SCHEDULES)
    parser.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(
    *,
    contract: Path,
    agent_config: Path,
    mcp_config: Path,
    schedules: Path,
    compose: Path,
) -> dict[str, Any]:
    source_check = _check_files(contract, agent_config, mcp_config, schedules, compose)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-hermes-contract",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "blocked",
            "checks": [source_check],
            "failures": failures,
            "next_actions": _next_actions(failures),
        }
    contract_doc = _load_yaml(contract)
    agent_doc = _load_yaml(agent_config)
    mcp_doc = _load_json(mcp_config)
    schedules_doc = _load_yaml(schedules)
    compose_doc = _load_yaml(compose)
    checks = [
        source_check,
        _check_service_contract(contract_doc, compose_doc),
        _check_environment(contract_doc, compose_doc),
        _check_mounts(contract_doc, compose_doc),
        _check_agent_paths(contract_doc, agent_doc),
        _check_mcp_contract(contract_doc, agent_doc, mcp_doc),
        _check_schedule_contract(contract_doc, agent_doc, schedules_doc),
        _check_logging_contract(contract_doc, agent_doc),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-hermes-contract",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "ready" if ok else "blocked",
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required Hermes runtime contract source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required Hermes runtime contract source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Hermes runtime contract source files are present.")


def _check_service_contract(contract: dict[str, Any], compose: dict[str, Any]) -> dict[str, Any]:
    service_contract = contract.get("service", {})
    service_name = service_contract.get("name")
    services = compose.get("services", {})
    service = services.get(service_name, {})
    failures: list[str] = []
    if not service:
        failures.append(f"Compose service {service_name} is missing.")
    if service.get("image") != "${" + str(service_contract.get("image_env")) + "}":
        failures.append("Hermes service image must come from the configured image env var.")
    if service.get("restart") != service_contract.get("restart_policy"):
        failures.append("Hermes restart policy differs from the runtime contract.")
    depends_on = service.get("depends_on", {})
    for dependency, condition in service_contract.get("depends_on", {}).items():
        if depends_on.get(dependency, {}).get("condition") != condition:
            failures.append(f"Hermes dependency {dependency} must require {condition}.")
    if failures:
        return _failed_with("service", "Hermes compose service does not match the runtime contract.", failures)
    return _passed("service", "Hermes compose service matches the runtime contract.")


def _check_environment(contract: dict[str, Any], compose: dict[str, Any]) -> dict[str, Any]:
    service = _service(contract, compose)
    expected = contract.get("required_environment", {})
    actual = service.get("environment", {}) if isinstance(service, dict) else {}
    mismatches = [
        {"key": key, "expected": value, "actual": actual.get(key)}
        for key, value in expected.items()
        if actual.get(key) != value
    ]
    unexpected = sorted(key for key in actual if key not in expected)
    if mismatches or unexpected:
        return {
            "id": "environment",
            "status": "fail",
            "message": "Hermes environment does not match the runtime contract.",
            "mismatches": mismatches,
            "unexpected": unexpected,
        }
    return _passed("environment", "Hermes environment matches the runtime contract.")


def _check_mounts(contract: dict[str, Any], compose: dict[str, Any]) -> dict[str, Any]:
    service = _service(contract, compose)
    actual = set(service.get("volumes", [])) if isinstance(service, dict) else set()
    expected = {_mount_spec(mount) for mount in contract.get("required_mounts", [])}
    missing = sorted(expected - actual)
    unexpected = sorted(volume for volume in actual - expected if "/etc/hermes" in volume or "/var/lib/hermes" in volume or "/var/log/freyja6" in volume)
    if missing or unexpected:
        return {
            "id": "mounts",
            "status": "fail",
            "message": "Hermes mounts do not satisfy the runtime contract.",
            "missing": missing,
            "unexpected_sensitive_mounts": unexpected,
        }
    return _passed("mounts", "Hermes mounts satisfy the runtime contract.")


def _check_agent_paths(contract: dict[str, Any], agent_doc: dict[str, Any]) -> dict[str, Any]:
    paths = contract.get("runtime_paths", {})
    agent = _agent(agent_doc)
    memory = agent.get("memory", {})
    expected = {
        "identity_file": agent.get("identity_file"),
        "sessions_dir": agent.get("sessions_dir"),
        "private_memory_dir": memory.get("private_dir"),
        "approved_files_root": _first(agent.get("tools", {}).get("filesystem", {}).get("approved_roots", [])),
    }
    mismatches = [
        {"path": key, "contract": paths.get(key), "agent_config": value}
        for key, value in expected.items()
        if paths.get(key) != value
    ]
    if mismatches:
        return {
            "id": "agent_paths",
            "status": "fail",
            "message": "Agent persistence/tool paths drifted from the Hermes runtime contract.",
            "mismatches": mismatches,
        }
    return _passed("agent_paths", "Agent persistence and filesystem paths match the runtime contract.")


def _check_mcp_contract(contract: dict[str, Any], agent_doc: dict[str, Any], mcp_doc: dict[str, Any]) -> dict[str, Any]:
    paths = contract.get("runtime_paths", {})
    agent_mcp = _agent(agent_doc).get("tools", {}).get("mcp", {})
    servers = mcp_doc.get("mcpServers", {})
    failures: list[str] = []
    if agent_mcp.get("config_file") != paths.get("mcp_config_file"):
        failures.append("Agent MCP config_file does not match contract mcp_config_file.")
    for server in ("freyja-core-gateway", "freyja-terminal"):
        if server not in servers:
            failures.append(f"MCP server {server} is missing.")
    if failures:
        return _failed_with("mcp", "MCP runtime contract is not satisfied.", failures)
    return _passed("mcp", "MCP runtime contract is satisfied.")


def _check_schedule_contract(contract: dict[str, Any], agent_doc: dict[str, Any], schedules_doc: dict[str, Any]) -> dict[str, Any]:
    paths = contract.get("runtime_paths", {})
    agent_schedules = _agent(agent_doc).get("schedules", {})
    schedules = schedules_doc.get("schedules", [])
    failures: list[str] = []
    if agent_schedules.get("config_file") != paths.get("schedules_file"):
        failures.append("Agent schedules config_file does not match contract schedules_file.")
    if schedules_doc.get("agent_id") != contract.get("agent_id"):
        failures.append("Schedules file is not scoped to freyja-test.")
    if not schedules:
        failures.append("Schedules file must define at least one validation schedule.")
    if failures:
        return _failed_with("schedules", "Schedule runtime contract is not satisfied.", failures)
    return _passed("schedules", "Schedule runtime contract is satisfied.")


def _check_logging_contract(contract: dict[str, Any], agent_doc: dict[str, Any]) -> dict[str, Any]:
    paths = contract.get("runtime_paths", {})
    logging = _agent(agent_doc).get("logging", {})
    expected = {
        "tool_log": logging.get("tool_log"),
        "model_log": logging.get("model_log"),
        "acceptance_log": logging.get("acceptance_log"),
    }
    mismatches = [
        {"path": key, "contract": paths.get(key), "agent_config": value}
        for key, value in expected.items()
        if paths.get(key) != value
    ]
    if mismatches:
        return {
            "id": "logging",
            "status": "fail",
            "message": "Logging paths drifted from the Hermes runtime contract.",
            "mismatches": mismatches,
        }
    return _passed("logging", "Logging paths match the Hermes runtime contract.")


def _mount_spec(mount: dict[str, str]) -> str:
    if mount.get("source_env"):
        source = "${" + mount["source_env"] + "}"
    else:
        source = str(mount.get("source", ""))
    target = mount.get("target", "")
    mode = mount.get("mode", "rw")
    return f"{source}:{target}" + (":ro" if mode == "ro" else "")


def _service(contract: dict[str, Any], compose: dict[str, Any]) -> dict[str, Any]:
    name = contract.get("service", {}).get("name")
    return compose.get("services", {}).get(name, {})


def _agent(agent_doc: dict[str, Any]) -> dict[str, Any]:
    agents = agent_doc.get("agents", [])
    return next((agent for agent in agents if agent.get("id") == "freyja-test"), {})


def _first(values: list[Any]) -> Any:
    return values[0] if values else None


def _failed_with(check_id: str, message: str, failures: list[str]) -> dict[str, Any]:
    return {"id": check_id, "status": "fail", "message": message, "failures": failures}


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Use this contract when verifying or adapting the pinned Hermes Agent image."]


def _load_yaml(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    if not resolved.exists():
        return {}
    return yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}


def _load_json(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    if not resolved.exists():
        return {}
    return json.loads(resolved.read_text(encoding="utf-8"))


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
        "report_type": "freyja6-hermes-contract",
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
            contract=args.contract,
            agent_config=args.agent_config,
            mcp_config=args.mcp_config,
            schedules=args.schedules,
            compose=args.compose,
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
