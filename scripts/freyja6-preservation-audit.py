#!/usr/bin/env python3
"""Audit Freyja 6 side-by-side preservation guardrails."""

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

DEFAULT_OUTPUT = Path("certification/reports/freyja6-preservation-audit.json")
DEFAULT_AGENT_CONFIG = Path("config/freyja6/freyja-test.yaml")
DEFAULT_COMPOSE = Path("deploy/compose/freyja6/compose.yaml")
EXPECTED_PRESERVED_SYSTEMS = ["Freyja 4", "Freyja 5", "Msty Nexus", "Msty Go", "OpenWebUI"]
FREYJA6_SERVICES = {"litellm-db", "litellm", "hermes-freyja-test"}
FORBIDDEN_SERVICES = {"freyja", "cloyd", "benedict", "agent-44", "smith", "open-webui", "msty-go", "msty-nexus"}
LEGACY_RUNTIME_MARKERS = (
    "FREYJA_DISCORD",
    "FREYJA4",
    "FREYJA5",
    "MSTY",
    "OPENWEBUI",
    "OPEN_WEBUI",
    "open-webui",
    "msty-go",
    "msty-nexus",
    "Library/Application Support/Msty Go",
)
LEGACY_EVIDENCE = {
    "freyja4_nexus_docs": ["docs/FREYJA_4_NEXUS_DECISION.md", "docs/FREYJA_4_NEXUS_TEST_RESULTS.md"],
    "freyja5_config": ["config/freyja-5.0-agents.yaml", "config/freyja-5.0-gateway.yaml", "config/freyja-5.0-planes.yaml"],
    "freyja5_status_docs": ["docs/FREYJA-5.0-STATUS.md", "docs/FREYJA_5_MSTY_GO_NEXUS_VULCAN.md"],
    "openwebui_config": ["deploy/compose/open-webui", "config/open-webui-home-agents.yaml", "config/open-webui-home-resources.yaml"],
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 side-by-side preservation posture.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(*, agent_config_path: Path = DEFAULT_AGENT_CONFIG, compose_path: Path = DEFAULT_COMPOSE) -> dict[str, Any]:
    source_check = _check_files(agent_config_path, compose_path)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-preservation-audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "secrets_included": False,
            "checks": [source_check],
            "failures": failures,
            "next_actions": _next_actions(failures),
        }
    agent_config = _load_yaml(agent_config_path)
    compose = _load_yaml(compose_path)
    checks = [
        source_check,
        _check_guardrails(agent_config),
        _check_single_test_agent(agent_config),
        _check_compose_is_side_by_side(compose),
        _check_no_legacy_runtime_coupling(compose),
        _check_legacy_evidence(),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-preservation-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": not failures,
        "status": "pass" if not failures else "fail",
        "secrets_included": False,
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_guardrails(agent_config: dict[str, Any]) -> dict[str, Any]:
    guardrails = agent_config.get("guardrails") if isinstance(agent_config.get("guardrails"), dict) else {}
    preserved = guardrails.get("preserve_existing_systems")
    missing = [item for item in EXPECTED_PRESERVED_SYSTEMS if item not in (preserved or [])]
    required_bools = [
        "do_not_modify_existing_bots_or_credentials",
        "do_not_migrate_existing_systems",
        "local_private_data_default",
        "cloud_model_use_requires_explicit_approval",
    ]
    falsey = [key for key in required_bools if guardrails.get(key) is not True]
    if missing or falsey:
        return {
            "id": "guardrails",
            "status": "fail",
            "message": "Freyja 6 preservation guardrails are incomplete.",
            "missing_preserved_systems": missing,
            "missing_boolean_guardrails": falsey,
        }
    return {
        "id": "guardrails",
        "status": "pass",
        "message": "Freyja 6 preservation guardrails are explicit.",
        "preserved_systems": EXPECTED_PRESERVED_SYSTEMS,
    }


def _check_single_test_agent(agent_config: dict[str, Any]) -> dict[str, Any]:
    agents = agent_config.get("agents") if isinstance(agent_config.get("agents"), list) else []
    live_agent_ids = [agent.get("id") for agent in agents if isinstance(agent, dict)]
    future_agents = agent_config.get("future_agents") if isinstance(agent_config.get("future_agents"), list) else []
    if live_agent_ids != ["freyja-test"]:
        return {"id": "phase_one_agent_scope", "status": "fail", "message": "Phase 1 must instantiate only freyja-test.", "live_agent_ids": live_agent_ids}
    if future_agents != ["Freyja", "Cloyd", "Benedict", "Agent 44", "Agent Smith"]:
        return {"id": "phase_one_agent_scope", "status": "fail", "message": "Future agents must remain reserved by name only.", "future_agents": future_agents}
    return _passed("phase_one_agent_scope", "Only freyja-test is instantiated; family agents remain reserved.")


def _check_compose_is_side_by_side(compose: dict[str, Any]) -> dict[str, Any]:
    services = set((compose.get("services") or {}).keys())
    unexpected = sorted(services - FREYJA6_SERVICES)
    missing = sorted(FREYJA6_SERVICES - services)
    forbidden = sorted(FORBIDDEN_SERVICES.intersection(services))
    if unexpected or missing or forbidden:
        return {
            "id": "compose_side_by_side",
            "status": "fail",
            "message": "Freyja 6 compose must remain a side-by-side validation stack.",
            "missing": missing,
            "unexpected": unexpected,
            "forbidden": forbidden,
        }
    return {"id": "compose_side_by_side", "status": "pass", "message": "Freyja 6 compose creates only validation services.", "services": sorted(services)}


def _check_no_legacy_runtime_coupling(compose: dict[str, Any]) -> dict[str, Any]:
    services = compose.get("services") if isinstance(compose.get("services"), dict) else {}
    findings: list[dict[str, str]] = []
    for service_name, service in services.items():
        if not isinstance(service, dict):
            continue
        findings.extend(_legacy_marker_findings(str(service_name), "environment", service.get("environment")))
        findings.extend(_legacy_marker_findings(str(service_name), "volumes", service.get("volumes")))
        findings.extend(_legacy_marker_findings(str(service_name), "labels", service.get("labels")))
    if findings:
        return {
            "id": "legacy_runtime_coupling",
            "status": "fail",
            "message": "Freyja 6 runtime must not reuse legacy system paths, credentials, or channel variables.",
            "findings": findings,
        }
    return _passed("legacy_runtime_coupling", "Freyja 6 runtime uses only Freyja 6-specific credentials, paths, and labels.")


def _legacy_marker_findings(service: str, field: str, value: Any) -> list[dict[str, str]]:
    rendered = _string_values(value)
    findings: list[dict[str, str]] = []
    for text in rendered:
        lowered = text.lower()
        for marker in LEGACY_RUNTIME_MARKERS:
            if marker.lower() in lowered:
                findings.append({"service": service, "field": field, "marker": marker})
                break
    return findings


def _string_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        rendered: list[str] = []
        for key, item in value.items():
            rendered.append(str(key))
            rendered.extend(_string_values(item))
        return rendered
    if isinstance(value, list):
        rendered = []
        for item in value:
            rendered.extend(_string_values(item))
        return rendered
    if value is None:
        return []
    return [str(value)]


def _check_legacy_evidence() -> dict[str, Any]:
    missing: dict[str, list[str]] = {}
    present: dict[str, list[str]] = {}
    for group, paths in LEGACY_EVIDENCE.items():
        for path_text in paths:
            path = REPO_ROOT / path_text
            if path.exists():
                present.setdefault(group, []).append(path_text)
            else:
                missing.setdefault(group, []).append(path_text)
    if missing:
        return {
            "id": "legacy_evidence_present",
            "status": "fail",
            "message": "One or more legacy preservation artifacts are missing.",
            "missing": missing,
            "present": present,
        }
    return {
        "id": "legacy_evidence_present",
        "status": "pass",
        "message": "Legacy Freyja/Msty/OpenWebUI artifacts remain present for rollback and comparison.",
        "present": present,
    }


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Continue Freyja 6 validation without migrating existing systems."]


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required preservation audit source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required preservation audit source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Preservation audit source files are present.")


def _load_yaml(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
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
        "report_type": "freyja6-preservation-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "status": "fail",
        "error": error,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_failure = _output_path_failure(args.output)
    report = _error_report(output_failure) if output_failure else build_report()
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
