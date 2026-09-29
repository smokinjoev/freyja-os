#!/usr/bin/env python3
"""Audit Freyja 6 scheduled validation boundaries."""

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
DEFAULT_SCHEDULES = Path("config/freyja6/schedules.yaml")
DEFAULT_CONTRACT = Path("config/freyja6/hermes-runtime-contract.yaml")
DEFAULT_COMPOSE = Path("deploy/compose/freyja6/compose.yaml")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-schedule-boundary-audit.json")
EXPECTED_SCHEDULES = {
    "freyja-test-health-heartbeat": {
        "cron": "*/15 * * * *",
        "log": "/var/log/freyja6/freyja-test-acceptance.jsonl",
        "acceptance_item": "scheduled_validation",
    },
    "freyja-test-daily-tool-smoke": {
        "cron": "17 7 * * *",
        "log": "/var/log/freyja6/freyja-test-tools.jsonl",
        "acceptance_items": [
            "approved_file_read",
            "safe_terminal",
            "mcp_tool",
            "calendar_read",
            "home_assistant_query",
            "coding_workflow",
        ],
    },
}
FORBIDDEN_FUTURE_AGENT_TERMS = ("Cloyd", "Benedict", "Agent 44", "Agent Smith")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 validation schedules.")
    parser.add_argument("--agent-config", type=Path, default=DEFAULT_AGENT_CONFIG)
    parser.add_argument("--schedules", type=Path, default=DEFAULT_SCHEDULES)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(*, agent_config: Path, schedules: Path, contract: Path, compose: Path) -> dict[str, Any]:
    source_check = _check_files(agent_config, schedules, contract, compose)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-schedule-boundary-audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "checks": [source_check],
            "failures": failures,
            "next_actions": _next_actions(failures),
        }
    agent_doc = _load_yaml(agent_config)
    schedules_doc = _load_yaml(schedules)
    contract_doc = _load_yaml(contract)
    compose_doc = _load_yaml(compose)
    checks = [
        source_check,
        _check_agent_schedule_contract(agent_doc, contract_doc, compose_doc),
        _check_schedule_scope(schedules_doc),
        _check_schedule_definitions(schedules_doc),
        _check_schedule_prompts(schedules_doc),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-schedule-boundary-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_agent_schedule_contract(agent_doc: dict[str, Any], contract_doc: dict[str, Any], compose_doc: dict[str, Any]) -> dict[str, Any]:
    agent = _agent(agent_doc)
    schedule_config = agent.get("schedules") if isinstance(agent.get("schedules"), dict) else {}
    runtime_paths = contract_doc.get("runtime_paths") if isinstance(contract_doc.get("runtime_paths"), dict) else {}
    services = compose_doc.get("services") if isinstance(compose_doc.get("services"), dict) else {}
    volumes = services.get("hermes-freyja-test", {}).get("volumes", []) if isinstance(services.get("hermes-freyja-test"), dict) else []
    failures: list[str] = []
    if schedule_config.get("enabled") is not True:
        failures.append("freyja-test schedules must be enabled.")
    if schedule_config.get("config_file") != "/etc/hermes/schedules/freyja-test.yaml":
        failures.append("Agent schedule config_file must point to /etc/hermes/schedules/freyja-test.yaml.")
    if schedule_config.get("host_config_source") != "config/freyja6/schedules.yaml":
        failures.append("Agent schedule host_config_source must be config/freyja6/schedules.yaml.")
    if runtime_paths.get("schedules_file") != "/etc/hermes/schedules/freyja-test.yaml":
        failures.append("Runtime contract schedules_file must match the agent schedule config.")
    if "../../../config/freyja6/schedules.yaml:/etc/hermes/schedules/freyja-test.yaml:ro" not in volumes:
        failures.append("Compose must mount the Freyja 6 schedules file read-only.")
    if failures:
        return {"id": "agent_schedule_contract", "status": "fail", "message": "Hermes schedule contract drifted.", "failures": failures}
    return _passed("agent_schedule_contract", "Hermes loads the freyja-test schedule config read-only.")


def _check_schedule_scope(schedules_doc: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    if schedules_doc.get("agent_id") != "freyja-test":
        failures.append("Schedules must be scoped to freyja-test.")
    if schedules_doc.get("phase") != "validation":
        failures.append("Schedules must remain in validation phase.")
    if schedules_doc.get("timezone") != "America/New_York":
        failures.append("Schedules must use America/New_York timezone.")
    if schedules_doc.get("enabled_by_default") is not True:
        failures.append("Validation schedules must be enabled by default.")
    if failures:
        return {"id": "schedule_scope", "status": "fail", "message": "Schedule scope drifted.", "failures": failures}
    return _passed("schedule_scope", "Schedules are scoped to freyja-test validation in America/New_York.")


def _check_schedule_definitions(schedules_doc: dict[str, Any]) -> dict[str, Any]:
    schedules = schedules_doc.get("schedules") if isinstance(schedules_doc.get("schedules"), list) else []
    by_id = {item.get("id"): item for item in schedules if isinstance(item, dict)}
    failures: list[dict[str, Any]] = []
    if list(by_id) != list(EXPECTED_SCHEDULES):
        failures.append({"reason": "unexpected_schedule_ids", "ids": list(by_id)})
    for schedule_id, expected in EXPECTED_SCHEDULES.items():
        item = by_id.get(schedule_id) or {}
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        if item.get("kind") != "cron":
            failures.append({"id": schedule_id, "reason": "not_cron"})
        if item.get("cron") != expected["cron"]:
            failures.append({"id": schedule_id, "reason": "cron_drift", "actual": item.get("cron")})
        if item.get("enabled") is not True:
            failures.append({"id": schedule_id, "reason": "not_enabled"})
        if evidence.get("log") != expected["log"]:
            failures.append({"id": schedule_id, "reason": "log_drift", "actual": evidence.get("log")})
        if "acceptance_item" in expected and evidence.get("acceptance_item") != expected["acceptance_item"]:
            failures.append({"id": schedule_id, "reason": "acceptance_item_drift", "actual": evidence.get("acceptance_item")})
        if "acceptance_items" in expected and evidence.get("acceptance_items") != expected["acceptance_items"]:
            failures.append({"id": schedule_id, "reason": "acceptance_items_drift", "actual": evidence.get("acceptance_items")})
    if failures:
        return {"id": "schedule_definitions", "status": "fail", "message": "Validation schedule definitions drifted.", "failures": failures}
    return _passed("schedule_definitions", "Only the expected freyja-test validation schedules are configured.")


def _check_schedule_prompts(schedules_doc: dict[str, Any]) -> dict[str, Any]:
    schedules = schedules_doc.get("schedules") if isinstance(schedules_doc.get("schedules"), list) else []
    failures: list[dict[str, str]] = []
    for item in schedules:
        if not isinstance(item, dict):
            continue
        text = f"{item.get('id', '')} {item.get('purpose', '')} {item.get('prompt', '')}"
        for term in FORBIDDEN_FUTURE_AGENT_TERMS:
            if term in text:
                failures.append({"id": str(item.get("id") or ""), "reason": "future_or_migration_term", "term": term})
        if item.get("id") == "freyja-test-daily-tool-smoke":
            prompt = str(item.get("prompt") or "")
            for required in ("Do not create calendar", "modify files", "control Home Assistant", "start migration"):
                if required not in prompt:
                    failures.append({"id": str(item.get("id") or ""), "reason": "missing_read_only_guard", "term": required})
    if failures:
        return {"id": "schedule_prompt_guardrails", "status": "fail", "message": "Schedule prompts are not safely scoped.", "failures": failures}
    return _passed("schedule_prompt_guardrails", "Schedule prompts stay validation-only and include read-only guards.")


def _agent(agent_doc: dict[str, Any]) -> dict[str, Any]:
    agents = agent_doc.get("agents") if isinstance(agent_doc.get("agents"), list) else []
    return next((agent for agent in agents if isinstance(agent, dict) and agent.get("id") == "freyja-test"), {})


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Keep scheduled work limited to freyja-test validation until live evidence passes."]


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required schedule boundary source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required schedule boundary source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Schedule boundary source files are present.")


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
        "report_type": "freyja6-schedule-boundary-audit",
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
        else build_report(agent_config=args.agent_config, schedules=args.schedules, contract=args.contract, compose=args.compose)
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
