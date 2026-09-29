#!/usr/bin/env python3
"""Audit future-agent gateway isolation without enabling future agents."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AGENT_CONFIG = Path("config/freyja6/freyja-test.yaml")
DEFAULT_ISOLATION = Path("config/freyja6/future-agent-isolation.yaml")
DEFAULT_COMPOSE = Path("deploy/compose/freyja6/compose.yaml")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-gateway-isolation-audit.json")
EXPECTED_FUTURE = ["Freyja", "Cloyd", "Benedict", "Agent 44", "Agent Smith"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 future-agent isolation reservations.")
    parser.add_argument("--agent-config", type=Path, default=DEFAULT_AGENT_CONFIG)
    parser.add_argument("--isolation", type=Path, default=DEFAULT_ISOLATION)
    parser.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(*, agent_config: Path, isolation: Path, compose: Path) -> dict[str, Any]:
    source_check = _check_files(agent_config, isolation, compose)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-gateway-isolation-audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "checks": [source_check],
            "failures": failures,
            "next_actions": _next_actions(failures),
        }
    agent_doc = _load_yaml(agent_config)
    isolation_doc = _load_yaml(isolation)
    compose_doc = _load_yaml(compose)
    checks = [
        source_check,
        _check_phase_one(agent_doc, isolation_doc, compose_doc),
        _check_future_agent_roster(agent_doc, isolation_doc),
        _check_unique_boundaries(isolation_doc),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-gateway-isolation-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_phase_one(agent_doc: dict[str, Any], isolation_doc: dict[str, Any], compose_doc: dict[str, Any]) -> dict[str, Any]:
    live_agents = [agent.get("id") for agent in agent_doc.get("agents", []) if isinstance(agent, dict)]
    reserved_live = isolation_doc.get("live_agents") if isinstance(isolation_doc.get("live_agents"), list) else []
    services = compose_doc.get("services") if isinstance(compose_doc.get("services"), dict) else {}
    hermes_services = sorted(name for name in services if name.startswith("hermes-"))
    failures: list[str] = []
    if live_agents != ["freyja-test"]:
        failures.append("Agent config must instantiate only freyja-test.")
    if reserved_live != ["freyja-test"]:
        failures.append("Isolation manifest must mark only freyja-test live.")
    if hermes_services != ["hermes-freyja-test"]:
        failures.append("Compose must run only the hermes-freyja-test service.")
    if failures:
        return {"id": "phase_one_single_live_agent", "status": "fail", "message": "Phase 1 instantiated extra agents.", "failures": failures}
    return _passed("phase_one_single_live_agent", "Only freyja-test is live; future agents remain reservations.")


def _check_future_agent_roster(agent_doc: dict[str, Any], isolation_doc: dict[str, Any]) -> dict[str, Any]:
    config_future = agent_doc.get("future_agents") if isinstance(agent_doc.get("future_agents"), list) else []
    future_agents = isolation_doc.get("future_agents") if isinstance(isolation_doc.get("future_agents"), list) else []
    names = [agent.get("display_name") for agent in future_agents if isinstance(agent, dict)]
    statuses = {agent.get("display_name"): agent.get("status") for agent in future_agents if isinstance(agent, dict)}
    failures: list[dict[str, Any]] = []
    if config_future != EXPECTED_FUTURE:
        failures.append({"reason": "agent_config_future_roster_drift", "actual": config_future})
    if names != EXPECTED_FUTURE:
        failures.append({"reason": "isolation_roster_drift", "actual": names})
    non_reserved = sorted(name for name, status in statuses.items() if status != "reserved")
    if non_reserved:
        failures.append({"reason": "future_agents_not_reserved", "agents": non_reserved})
    if failures:
        return {"id": "future_agent_roster", "status": "fail", "message": "Future-agent reservations drifted.", "failures": failures}
    return _passed("future_agent_roster", "Future family agents are named and reserved, not instantiated.")


def _check_unique_boundaries(isolation_doc: dict[str, Any]) -> dict[str, Any]:
    future_agents = [agent for agent in isolation_doc.get("future_agents", []) if isinstance(agent, dict)]
    fields = [
        "slug",
        "identity_file",
        "sessions_dir",
        "private_memory_dir",
        "credentials_env_prefix",
        "mcp_token_env",
    ]
    failures: list[dict[str, Any]] = []
    for field in fields:
        values = [str(agent.get(field) or "") for agent in future_agents]
        failures.extend(_duplicate_failures(field, values))
        missing = [agent.get("display_name") for agent in future_agents if not agent.get(field)]
        if missing:
            failures.append({"reason": "missing_boundary", "field": field, "agents": missing})
    token_envs = [str(agent.get("messaging", {}).get("token_env") or "") for agent in future_agents]
    channel_envs = [str(agent.get("messaging", {}).get("channel_env") or "") for agent in future_agents]
    failures.extend(_duplicate_failures("messaging.token_env", token_envs))
    failures.extend(_duplicate_failures("messaging.channel_env", channel_envs))
    for agent in future_agents:
        slug = str(agent.get("slug") or "")
        expected_root = f"/var/lib/hermes/agents/{slug}/"
        for field in ("identity_file", "sessions_dir", "private_memory_dir"):
            value = str(agent.get(field) or "")
            if value and not value.startswith(expected_root):
                failures.append({"reason": "path_outside_agent_root", "agent": agent.get("display_name"), "field": field, "value": value})
        messaging = agent.get("messaging") if isinstance(agent.get("messaging"), dict) else {}
        if messaging.get("gateway") != "discord":
            failures.append({"reason": "unexpected_gateway", "agent": agent.get("display_name"), "gateway": messaging.get("gateway")})
        if agent.get("shared_memory") != "authorized_household_only":
            failures.append({"reason": "shared_memory_not_authorized_only", "agent": agent.get("display_name")})
    if failures:
        return {"id": "unique_future_boundaries", "status": "fail", "message": "Future agents do not have unique reserved boundaries.", "failures": failures}
    return _passed("unique_future_boundaries", "Reserved agents have separate identity, session, memory, credential, MCP, and channel boundaries.")


def _duplicate_failures(field: str, values: list[str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if not value:
            continue
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return [{"reason": "duplicate_boundary", "field": field, "values": sorted(duplicates)}] if duplicates else []


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Keep future agents reserved until freyja-test completes repeated live validation."]


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required gateway isolation source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required gateway isolation source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Gateway isolation source files are present.")


def _load_yaml(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    try:
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except OSError:
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
        "report_type": "freyja6-gateway-isolation-audit",
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
        else build_report(agent_config=args.agent_config, isolation=args.isolation, compose=args.compose)
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
