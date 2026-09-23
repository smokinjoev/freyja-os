#!/usr/bin/env python3
"""Audit Freyja 6 approved filesystem read boundary."""

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
DEFAULT_CONTRACT = Path("config/freyja6/hermes-runtime-contract.yaml")
DEFAULT_COMPOSE = Path("deploy/compose/freyja6/compose.yaml")
DEFAULT_BOOTSTRAP = Path("scripts/freyja6-bootstrap-atlas.py")
DEFAULT_TOOL_SMOKE = Path("scripts/freyja6-tool-smoke.py")
DEFAULT_APPROVED_SMOKE = Path("config/freyja6/bootstrap/approved-smoke.txt")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-filesystem-boundary-audit.json")
APPROVED_ROOT = "/workspace/approved"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 approved filesystem boundary.")
    parser.add_argument("--agent-config", type=Path, default=DEFAULT_AGENT_CONFIG)
    parser.add_argument("--tool-boundaries", type=Path, default=DEFAULT_TOOL_BOUNDARIES)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--bootstrap", type=Path, default=DEFAULT_BOOTSTRAP)
    parser.add_argument("--tool-smoke", type=Path, default=DEFAULT_TOOL_SMOKE)
    parser.add_argument("--approved-smoke", type=Path, default=DEFAULT_APPROVED_SMOKE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(
    *,
    agent_config: Path,
    tool_boundaries: Path,
    contract: Path,
    compose: Path,
    bootstrap: Path,
    tool_smoke: Path,
    approved_smoke: Path,
) -> dict[str, Any]:
    source_check = _check_files(agent_config, tool_boundaries, contract, compose, bootstrap, tool_smoke, approved_smoke)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-filesystem-boundary-audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "checks": [source_check],
            "failures": failures,
            "next_actions": _next_actions(failures),
        }
    agent_doc = _load_yaml(agent_config)
    boundary_doc = _load_yaml(tool_boundaries)
    contract_doc = _load_yaml(contract)
    compose_doc = _load_yaml(compose)
    checks = [
        source_check,
        _check_agent_filesystem(agent_doc, boundary_doc, contract_doc),
        _check_compose_mount(contract_doc, compose_doc),
        _check_smoke_seed(approved_smoke, bootstrap),
        _check_tool_smoke_redaction(tool_smoke),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-filesystem-boundary-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_agent_filesystem(agent_doc: dict[str, Any], boundary_doc: dict[str, Any], contract_doc: dict[str, Any]) -> dict[str, Any]:
    agent = _agent(agent_doc)
    filesystem = agent.get("tools", {}).get("filesystem", {})
    boundary = boundary_doc.get("tool_targets", {}).get("filesystem", {})
    runtime_paths = contract_doc.get("runtime_paths", {})
    failures: list[str] = []
    if filesystem.get("approved_roots") != [APPROVED_ROOT]:
        failures.append("Agent filesystem approved_roots must be exactly /workspace/approved.")
    if filesystem.get("mode") != "read-only":
        failures.append("Agent filesystem mode must be read-only.")
    if boundary.get("boundary") != "docker_bind_mount":
        failures.append("Filesystem boundary must be the Docker bind mount.")
    if boundary.get("mode") != "read_only":
        failures.append("Tool boundary filesystem mode must be read_only.")
    if boundary.get("approved_roots") != [APPROVED_ROOT]:
        failures.append("Tool boundary approved_roots must match the agent config.")
    if runtime_paths.get("approved_files_root") != APPROVED_ROOT:
        failures.append("Runtime contract approved_files_root must be /workspace/approved.")
    if failures:
        return {"id": "approved_filesystem_policy", "status": "fail", "message": "Approved filesystem policy drifted.", "failures": failures}
    return _passed("approved_filesystem_policy", "freyja-test can read only the approved read-only filesystem root.")


def _check_compose_mount(contract_doc: dict[str, Any], compose_doc: dict[str, Any]) -> dict[str, Any]:
    service = compose_doc.get("services", {}).get("hermes-freyja-test", {})
    volumes = service.get("volumes") if isinstance(service.get("volumes"), list) else []
    required_mounts = contract_doc.get("required_mounts") if isinstance(contract_doc.get("required_mounts"), list) else []
    failures: list[str] = []
    if "${FREYJA6_APPROVED_FILES_ROOT}:/workspace/approved:ro" not in volumes:
        failures.append("Compose must mount FREYJA6_APPROVED_FILES_ROOT at /workspace/approved:ro.")
    if "../../..:/workspace/repo:ro" not in volumes:
        failures.append("Compose must mount the repository at /workspace/repo read-only.")
    approved_mount = next((mount for mount in required_mounts if mount.get("target") == APPROVED_ROOT), {})
    if approved_mount.get("source_env") != "FREYJA6_APPROVED_FILES_ROOT" or approved_mount.get("mode") != "ro":
        failures.append("Runtime contract must declare the approved files mount as FREYJA6_APPROVED_FILES_ROOT read-only.")
    write_like = sorted(volume for volume in volumes if "/workspace/approved" in volume and not str(volume).endswith(":ro"))
    if write_like:
        failures.append(f"Approved filesystem has non-read-only mount entries: {write_like}.")
    writable_workspace = sorted(
        volume
        for volume in volumes
        if ":/workspace/" in str(volume) and not str(volume).endswith(":ro") and "/workspace/approved" not in str(volume)
    )
    if writable_workspace:
        failures.append(f"Workspace mounts must be read-only outside approved runtime data: {writable_workspace}.")
    if failures:
        return {"id": "approved_filesystem_mount", "status": "fail", "message": "Approved filesystem mount is not read-only and env-scoped.", "failures": failures}
    return _passed("approved_filesystem_mount", "Approved filesystem is mounted from FREYJA6_APPROVED_FILES_ROOT as read-only.")


def _check_smoke_seed(approved_smoke: Path, bootstrap: Path) -> dict[str, Any]:
    resolved_seed = _resolve(approved_smoke)
    resolved_bootstrap = _resolve(bootstrap)
    failures: list[str] = []
    try:
        seed_text = resolved_seed.read_text(encoding="utf-8")
    except OSError:
        seed_text = ""
    if "Freyja 6 approved filesystem smoke file." not in seed_text:
        failures.append("Approved smoke seed text is missing or unexpected.")
    lowered_seed = seed_text.lower().replace("no credentials", "")
    if any(marker in lowered_seed for marker in ("token", "password", "secret")):
        failures.append("Approved smoke seed must not contain credential markers.")
    try:
        bootstrap_text = resolved_bootstrap.read_text(encoding="utf-8")
    except OSError:
        bootstrap_text = ""
    if "APPROVED_SMOKE_TEMPLATE" not in bootstrap_text or "smoke.txt" not in bootstrap_text:
        failures.append("Bootstrap script must seed smoke.txt from the approved smoke template.")
    if failures:
        return {"id": "approved_smoke_seed", "status": "fail", "message": "Approved filesystem smoke seed is not safe or bootstrap-aligned.", "failures": failures}
    return _passed("approved_smoke_seed", "Approved filesystem smoke seed is safe and created by bootstrap.")


def _check_tool_smoke_redaction(tool_smoke: Path) -> dict[str, Any]:
    markers = _redaction_markers(tool_smoke)
    missing = sorted({"/srv/freyja6/approved-files", "/workspace/approved"} - set(markers))
    if missing:
        return {
            "id": "tool_smoke_redaction",
            "status": "fail",
            "message": "Tool smoke must redact both host and container approved filesystem roots.",
            "missing_markers": missing,
        }
    return _passed("tool_smoke_redaction", "Tool smoke redacts approved filesystem paths in evidence.")


def _redaction_markers(path: Path) -> list[str]:
    resolved = _resolve(path)
    try:
        tree = ast.parse(resolved.read_text(encoding="utf-8"))
    except OSError:
        return []
    markers: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in {"/srv/freyja6/approved-files", "/workspace/approved"}:
            markers.append(node.value)
    return sorted(set(markers))


def _agent(agent_doc: dict[str, Any]) -> dict[str, Any]:
    agents = agent_doc.get("agents") if isinstance(agent_doc.get("agents"), list) else []
    return next((agent for agent in agents if isinstance(agent, dict) and agent.get("id") == "freyja-test"), {})


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Keep filesystem access restricted to the read-only approved root."]


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required filesystem boundary source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required filesystem boundary source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Filesystem boundary source files are present.")


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
        "report_type": "freyja6-filesystem-boundary-audit",
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
            contract=args.contract,
            compose=args.compose,
            bootstrap=args.bootstrap,
            tool_smoke=args.tool_smoke,
            approved_smoke=args.approved_smoke,
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
