#!/usr/bin/env python3
"""Audit Freyja 6 memory boundaries for local Hermes-native validation."""

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
DEFAULT_ISOLATION = Path("config/freyja6/future-agent-isolation.yaml")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-memory-boundary-audit.json")
CLOUD_MEMORY_MARKERS = ("mem0", "honcho", "pinecone", "weaviate", "qdrant-cloud", "redis-cloud", "supabase", "upstash")
LIVE_AGENT_MEMORY_ROOT = "/var/lib/hermes/agents/freyja-test/"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 local memory boundary posture.")
    parser.add_argument("--agent-config", type=Path, default=DEFAULT_AGENT_CONFIG)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--isolation", type=Path, default=DEFAULT_ISOLATION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(*, agent_config: Path, contract: Path, compose: Path, isolation: Path) -> dict[str, Any]:
    source_check = _check_files(agent_config, contract, compose, isolation)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-memory-boundary-audit",
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
    isolation_doc = _load_yaml(isolation)
    checks = [
        source_check,
        _check_live_agent_memory(agent_doc, contract_doc),
        _check_local_mounts(contract_doc, compose_doc),
        _check_future_memory_reservations(isolation_doc),
        _check_no_cloud_memory(agent_doc, contract_doc, compose_doc, isolation_doc),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-memory-boundary-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_live_agent_memory(agent_doc: dict[str, Any], contract_doc: dict[str, Any]) -> dict[str, Any]:
    agent = _agent(agent_doc)
    memory = agent.get("memory") if isinstance(agent.get("memory"), dict) else {}
    runtime_paths = contract_doc.get("runtime_paths") if isinstance(contract_doc.get("runtime_paths"), dict) else {}
    failures: list[str] = []
    if memory.get("provider") != "hermes-native":
        failures.append("freyja-test memory provider must be hermes-native.")
    if memory.get("private_dir") != "/var/lib/hermes/agents/freyja-test/memory/private":
        failures.append("freyja-test private memory path must stay under its Hermes agent root.")
    if memory.get("shared_household_dir") is not None:
        failures.append("Shared household memory must remain disabled during Phase 1 validation.")
    if runtime_paths.get("private_memory_dir") != memory.get("private_dir"):
        failures.append("Runtime contract private memory path must match the agent config.")
    if failures:
        return {"id": "live_agent_memory", "status": "fail", "message": "freyja-test memory boundary drifted.", "failures": failures}
    return _passed("live_agent_memory", "freyja-test uses Hermes-native private local memory with shared memory disabled.")


def _check_local_mounts(contract_doc: dict[str, Any], compose_doc: dict[str, Any]) -> dict[str, Any]:
    services = compose_doc.get("services") if isinstance(compose_doc.get("services"), dict) else {}
    hermes = services.get("hermes-freyja-test") if isinstance(services.get("hermes-freyja-test"), dict) else {}
    volumes = hermes.get("volumes") if isinstance(hermes.get("volumes"), list) else []
    required_mounts = contract_doc.get("required_mounts") if isinstance(contract_doc.get("required_mounts"), list) else []
    failures: list[str] = []
    if "${FREYJA6_HERMES_DATA}:/var/lib/hermes" not in volumes:
        failures.append("Compose must mount FREYJA6_HERMES_DATA at /var/lib/hermes.")
    hermes_mount = next((mount for mount in required_mounts if mount.get("target") == "/var/lib/hermes"), {})
    if hermes_mount.get("source_env") != "FREYJA6_HERMES_DATA" or hermes_mount.get("mode") != "rw":
        failures.append("Runtime contract must declare FREYJA6_HERMES_DATA as the rw Hermes data mount.")
    if failures:
        return {"id": "local_memory_mount", "status": "fail", "message": "Hermes memory is not clearly mounted as local Atlas storage.", "failures": failures}
    return _passed("local_memory_mount", "Hermes memory persists through the local FREYJA6_HERMES_DATA mount.")


def _check_future_memory_reservations(isolation_doc: dict[str, Any]) -> dict[str, Any]:
    if isolation_doc.get("phase") != "reservation_only":
        return {"id": "future_memory_reservations", "status": "fail", "message": "Future-agent memory manifest must remain reservation-only."}
    future_agents = [agent for agent in isolation_doc.get("future_agents", []) if isinstance(agent, dict)]
    failures: list[dict[str, Any]] = []
    private_dirs = [str(agent.get("private_memory_dir") or "") for agent in future_agents]
    duplicates = _duplicates(private_dirs)
    if duplicates:
        failures.append({"reason": "duplicate_private_memory_dir", "values": duplicates})
    for agent in future_agents:
        slug = str(agent.get("slug") or "")
        private_dir = str(agent.get("private_memory_dir") or "")
        if agent.get("status") != "reserved":
            failures.append({"reason": "future_agent_not_reserved", "agent": agent.get("display_name"), "status": agent.get("status")})
        if slug == "freyja-test" or private_dir.startswith(LIVE_AGENT_MEMORY_ROOT):
            failures.append({"reason": "future_memory_collides_with_live_agent", "agent": agent.get("display_name"), "private_memory_dir": private_dir})
        if not private_dir.startswith(f"/var/lib/hermes/agents/{slug}/memory/private"):
            failures.append({"reason": "private_memory_outside_agent_root", "agent": agent.get("display_name"), "private_memory_dir": private_dir})
        if agent.get("shared_memory") != "authorized_household_only":
            failures.append({"reason": "future_shared_memory_not_authorized_only", "agent": agent.get("display_name")})
    if failures:
        return {"id": "future_memory_reservations", "status": "fail", "message": "Future-agent memory reservations are not isolated.", "failures": failures}
    return _passed("future_memory_reservations", "Future agents reserve separate private memory and authorized-only shared memory.")


def _check_no_cloud_memory(*docs: dict[str, Any]) -> dict[str, Any]:
    rendered = json.dumps(docs, sort_keys=True).lower()
    markers = sorted(marker for marker in CLOUD_MEMORY_MARKERS if marker in rendered)
    if markers:
        return {
            "id": "no_cloud_memory",
            "status": "fail",
            "message": "Cloud or experimental memory provider markers are present in Phase 1 config.",
            "markers": markers,
        }
    return _passed("no_cloud_memory", "No cloud-hosted or experimental memory provider is configured for Phase 1.")


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
    return ["Keep Freyja 6 private memory local and Hermes-native until freyja-test is stable."]


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required memory boundary source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required memory boundary source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Memory boundary source files are present.")


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
        "report_type": "freyja6-memory-boundary-audit",
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
        else build_report(agent_config=args.agent_config, contract=args.contract, compose=args.compose, isolation=args.isolation)
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
