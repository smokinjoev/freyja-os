#!/usr/bin/env python3
"""Audit Freyja 6 Phase 1 Discord gateway isolation."""

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

DEFAULT_AGENT_CONFIG = Path("config/freyja6/freyja-test.yaml")
DEFAULT_CONTRACT = Path("config/freyja6/hermes-runtime-contract.yaml")
DEFAULT_COMPOSE = Path("deploy/compose/freyja6/compose.yaml")
DEFAULT_ENV_EXAMPLE = Path("deploy/compose/freyja6/.env.example")
DEFAULT_ISOLATION = Path("config/freyja6/future-agent-isolation.yaml")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-messaging-gateway-audit.json")
LIVE_DISCORD_ENVS = {"FREYJA6_DISCORD_BOT_TOKEN", "FREYJA6_DISCORD_CHANNEL_ID"}
HERMES_DISCORD_ALIAS_ENVS = {
    "DISCORD_BOT_TOKEN": "${FREYJA6_DISCORD_BOT_TOKEN}",
    "DISCORD_HOME_CHANNEL": "${FREYJA6_DISCORD_CHANNEL_ID}",
    "DISCORD_ALLOWED_CHANNELS": "${FREYJA6_DISCORD_CHANNEL_ID}",
    "DISCORD_FREE_RESPONSE_CHANNELS": "${FREYJA6_DISCORD_CHANNEL_ID}",
    "DISCORD_ALLOW_ALL_USERS": "true",
}
DISCORD_EVIDENCE_ENVS = {
    "FREYJA6_DISCORD_MANUAL_CONFIRMATION",
    "FREYJA6_DISCORD_MESSAGE_TRACE_ID",
    "FREYJA6_DISCORD_REPLY_AFTER_REBOOT_TRACE_ID",
    "FREYJA6_DISCORD_REPLY_AFTER_REBOOT_VERIFICATION",
    "FREYJA6_DISCORD_REPLY_TRACE_ID",
    "FREYJA6_DISCORD_SMOKE_MESSAGE_ID",
    "FREYJA6_DISCORD_SMOKE_REPLY_ID",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 dedicated Discord gateway posture.")
    parser.add_argument("--agent-config", type=Path, default=DEFAULT_AGENT_CONFIG)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--env-example", type=Path, default=DEFAULT_ENV_EXAMPLE)
    parser.add_argument("--isolation", type=Path, default=DEFAULT_ISOLATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(*, agent_config: Path, contract: Path, compose: Path, env_example: Path, isolation: Path) -> dict[str, Any]:
    source_check = _check_files(agent_config, contract, compose, env_example, isolation)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-messaging-gateway-audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "checks": [source_check],
            "failures": failures,
            "next_actions": _next_actions(failures),
        }
    agent_doc = _load_yaml(agent_config)
    contract_doc = _load_yaml(contract)
    compose_doc = _load_yaml(compose)
    env_values = _load_env(env_example)
    isolation_doc = _load_yaml(isolation)
    checks = [
        source_check,
        _check_live_discord_agent(agent_doc, contract_doc, compose_doc),
        _check_env_example(env_values),
        _check_future_agent_messaging(isolation_doc),
        _check_no_hardcoded_discord_credentials(agent_doc, contract_doc, compose_doc, isolation_doc),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-messaging-gateway-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_live_discord_agent(agent_doc: dict[str, Any], contract_doc: dict[str, Any], compose_doc: dict[str, Any]) -> dict[str, Any]:
    agent = _agent(agent_doc)
    messaging = agent.get("messaging") if isinstance(agent.get("messaging"), dict) else {}
    env = messaging.get("env") if isinstance(messaging.get("env"), dict) else {}
    contract_env = contract_doc.get("required_environment") if isinstance(contract_doc.get("required_environment"), dict) else {}
    services = compose_doc.get("services") if isinstance(compose_doc.get("services"), dict) else {}
    hermes_env = services.get("hermes-freyja-test", {}).get("environment", {}) if isinstance(services.get("hermes-freyja-test"), dict) else {}
    failures: list[str] = []
    if messaging.get("gateway") != "discord":
        failures.append("freyja-test messaging gateway must be Discord.")
    if messaging.get("channel_scope") != "dedicated-test-channel":
        failures.append("freyja-test must be scoped to one dedicated test channel.")
    if messaging.get("credentials_source") != "environment":
        failures.append("Discord credentials must come from environment only.")
    if env.get("token") != "FREYJA6_DISCORD_BOT_TOKEN" or env.get("channel_id") != "FREYJA6_DISCORD_CHANNEL_ID":
        failures.append("Agent config must reference the Freyja 6 Discord env vars.")
    for key in LIVE_DISCORD_ENVS:
        if contract_env.get(key) != "${" + key + "}":
            failures.append(f"Runtime contract must declare {key} as an env placeholder.")
        if hermes_env.get(key) != "${" + key + "}":
            failures.append(f"Compose Hermes env must pass {key} as an env placeholder.")
    for key, expected in HERMES_DISCORD_ALIAS_ENVS.items():
        if contract_env.get(key) != expected:
            failures.append(f"Runtime contract must declare Hermes Discord alias {key}.")
        if hermes_env.get(key) != expected:
            failures.append(f"Compose Hermes env must pass Hermes Discord alias {key}.")
    extra_live_discord = sorted(
        key for key in hermes_env if "DISCORD" in key and key not in LIVE_DISCORD_ENVS and key not in HERMES_DISCORD_ALIAS_ENVS
    )
    if extra_live_discord:
        failures.append(f"Compose includes unexpected live Discord env vars: {extra_live_discord}.")
    if failures:
        return {"id": "live_discord_gateway", "status": "fail", "message": "freyja-test Discord gateway is not isolated to one env-scoped test channel.", "failures": failures}
    return _passed("live_discord_gateway", "freyja-test uses one environment-scoped dedicated Discord test channel.")


def _check_env_example(env_values: dict[str, str]) -> dict[str, Any]:
    missing = sorted(key for key in LIVE_DISCORD_ENVS if key not in env_values)
    non_blank = sorted(key for key in LIVE_DISCORD_ENVS if env_values.get(key, "") not in {"", '""', "''"})
    future_live = sorted(
        key
        for key in env_values
        if key.startswith("FREYJA6_") and "DISCORD" in key and key not in LIVE_DISCORD_ENVS and key not in DISCORD_EVIDENCE_ENVS
    )
    if missing or non_blank or future_live:
        return {
            "id": "env_example_discord",
            "status": "fail",
            "message": ".env.example must keep live Discord credentials blank and limit additional Discord keys to evidence-only fields.",
            "missing": missing,
            "non_blank": non_blank,
            "future_live": future_live,
        }
    return _passed("env_example_discord", ".env.example keeps live Discord placeholders blank and evidence fields non-live.")


def _check_future_agent_messaging(isolation_doc: dict[str, Any]) -> dict[str, Any]:
    future_agents = [agent for agent in isolation_doc.get("future_agents", []) if isinstance(agent, dict)]
    token_envs = [str(agent.get("messaging", {}).get("token_env") or "") for agent in future_agents]
    channel_envs = [str(agent.get("messaging", {}).get("channel_env") or "") for agent in future_agents]
    failures: list[dict[str, Any]] = []
    token_duplicates = _duplicates(token_envs)
    channel_duplicates = _duplicates(channel_envs)
    if token_duplicates:
        failures.append({"reason": "duplicate_future_token_env", "values": token_duplicates})
    if channel_duplicates:
        failures.append({"reason": "duplicate_future_channel_env", "values": channel_duplicates})
    for agent in future_agents:
        messaging = agent.get("messaging") if isinstance(agent.get("messaging"), dict) else {}
        if messaging.get("gateway") != "discord":
            failures.append({"reason": "unexpected_future_gateway", "agent": agent.get("display_name"), "gateway": messaging.get("gateway")})
        if messaging.get("token_env") in LIVE_DISCORD_ENVS or messaging.get("channel_env") in LIVE_DISCORD_ENVS:
            failures.append({"reason": "future_agent_reuses_live_discord_env", "agent": agent.get("display_name")})
    if failures:
        return {"id": "future_discord_reservations", "status": "fail", "message": "Future Discord reservations can collide with live or future agents.", "failures": failures}
    return _passed("future_discord_reservations", "Future agents reserve separate Discord token and channel env vars without enabling them.")


def _check_no_hardcoded_discord_credentials(*docs: dict[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    _walk_for_discord_values(docs, findings)
    if findings:
        return {
            "id": "no_hardcoded_discord_credentials",
            "status": "fail",
            "message": "Discord token/channel values must not be hardcoded in tracked config.",
            "findings": findings,
        }
    return _passed("no_hardcoded_discord_credentials", "Tracked Discord config contains env names/placeholders only.")


def _walk_for_discord_values(value: Any, findings: list[str], path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _walk_for_discord_values(child, findings, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _walk_for_discord_values(child, findings, f"{path}[{index}]")
        return
    if not isinstance(value, str):
        return
    upper = value.upper()
    path_upper = path.upper()
    if ".ENV" not in path_upper and "ENVIRONMENT" not in path_upper:
        return
    if "DISCORD" not in upper and "DISCORD" not in path_upper:
        return
    if value.startswith("FREYJA6_") or value.startswith("${FREYJA6_"):
        return
    if value == "discord" or value == "dedicated-test-channel":
        return
    if value in {"true", "false"}:
        return
    findings.append(path)


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if not value:
            continue
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _agent(agent_doc: dict[str, Any]) -> dict[str, Any]:
    agents = agent_doc.get("agents") if isinstance(agent_doc.get("agents"), list) else []
    return next((agent for agent in agents if isinstance(agent, dict) and agent.get("id") == "freyja-test"), {})


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Keep Discord validation isolated to the dedicated freyja-test channel until repeated live evidence passes."]


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required messaging gateway source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required messaging gateway source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Messaging gateway source files are present.")


def _load_yaml(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    try:
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_env(path: Path) -> dict[str, str]:
    resolved = _resolve(path)
    values: dict[str, str] = {}
    try:
        lines = resolved.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


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
        "report_type": "freyja6-messaging-gateway-audit",
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
            contract=args.contract,
            compose=args.compose,
            env_example=args.env_example,
            isolation=args.isolation,
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
