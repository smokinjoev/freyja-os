#!/usr/bin/env python3
"""Collect redacted Freyja 6 Docker stack status evidence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_ENV_FILE = Path("deploy/compose/freyja6/.env")
DEFAULT_COMPOSE_FILE = Path("deploy/compose/freyja6/compose.yaml")
FALLBACK_LOG_ROOT = Path("/srv/freyja6/logs")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-stack-status.json")
EXPECTED_SERVICES = ["litellm-db", "litellm", "hermes-freyja-test"]
EXPECTED_LOGS = ["freyja-test-tools.jsonl", "freyja-test-model-calls.jsonl", "freyja-test-acceptance.jsonl"]
Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect the Freyja 6 compose stack status.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--compose-file", type=Path, default=DEFAULT_COMPOSE_FILE)
    parser.add_argument("--log-root", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(
    *,
    env_file: Path,
    compose_file: Path,
    log_root: Path,
    runner: Runner | None = None,
) -> dict[str, Any]:
    run = runner or _run_command
    checks = [
        _check_docker_available(),
        _check_compose_ps(env_file=env_file, compose_file=compose_file, runner=run),
        _check_logs(log_root),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-stack-status",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": not failures,
        "status": "running" if not failures else "not-ready",
        "env_file": str(env_file),
        "compose_file": str(compose_file),
        "log_root_redacted": _redact_log_root(log_root),
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_docker_available() -> dict[str, Any]:
    if shutil.which("docker"):
        return _passed("docker_cli", "Docker CLI is available.")
    return _failed("docker_cli", "Docker CLI is not available.")


def _check_compose_ps(*, env_file: Path, compose_file: Path, runner: Runner) -> dict[str, Any]:
    cmd = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(_resolve(compose_file)),
        "ps",
        "--format",
        "json",
    ]
    result = runner(cmd)
    if result.returncode != 0:
        return {
            "id": "compose_ps",
            "status": "fail",
            "message": "Docker Compose could not report Freyja 6 service status.",
            "stderr_tail": result.stderr[-1000:],
        }
    services = _parse_compose_ps(result.stdout)
    by_service = {str(item.get("Service") or item.get("Name") or item.get("service") or item.get("name")): item for item in services}
    missing = [service for service in EXPECTED_SERVICES if service not in by_service]
    unexpected = sorted(service for service in by_service if service and service not in EXPECTED_SERVICES)
    not_running = []
    for service in EXPECTED_SERVICES:
        item = by_service.get(service)
        if not item:
            continue
        status = str(item.get("State") or item.get("Status") or item.get("Health") or item.get("status") or "")
        if not _status_is_running(status):
            not_running.append({"service": service, "status": _redact_status(status)})
    if missing or not_running or unexpected:
        return {
            "id": "compose_ps",
            "status": "fail",
            "message": "Freyja 6 compose services are missing, not running, or out of Phase 1 scope.",
            "missing": missing,
            "not_running": not_running,
            "unexpected": unexpected,
        }
    return {
        "id": "compose_ps",
        "status": "pass",
        "message": "Freyja 6 compose services are present and running.",
        "services": [{"service": service, "status": _redact_status(str(by_service[service].get("State") or by_service[service].get("Status") or ""))} for service in EXPECTED_SERVICES],
    }


def _check_logs(log_root: Path) -> dict[str, Any]:
    missing = [name for name in EXPECTED_LOGS if not (log_root / name).exists()]
    not_files = [name for name in EXPECTED_LOGS if (log_root / name).exists() and not (log_root / name).is_file()]
    symlinks = [name for name in EXPECTED_LOGS if (log_root / name).is_symlink()]
    if missing:
        return {
            "id": "logs",
            "status": "fail",
            "message": "One or more Freyja 6 log files are missing.",
            "missing": missing,
        }
    if not_files:
        return {
            "id": "logs",
            "status": "fail",
            "message": "One or more Freyja 6 log paths are not files.",
            "not_files": not_files,
        }
    if symlinks:
        return {
            "id": "logs",
            "status": "fail",
            "message": "Freyja 6 evidence logs must be regular files, not symlinks.",
            "symlinks": symlinks,
        }
    return _passed("logs", "Freyja 6 tool, model, and acceptance logs are present.")


def _parse_compose_ps(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    rows = []
    for line in stripped.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _status_is_running(status: str) -> bool:
    lowered = status.lower()
    if any(marker in lowered for marker in ("exited", "dead", "created", "paused", "restarting", "not running", "unhealthy")):
        return False
    return lowered in {"running", "healthy", "up"} or lowered.startswith("running ") or "running (" in lowered


def _redact_status(status: str) -> str:
    return " ".join(status.strip().split())[:120]


def _redact_log_root(path: Path) -> str:
    if str(path).startswith("/srv/freyja6/logs"):
        return "freyja6/logs"
    return path.name


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Run the live Freyja 6 acceptance smokes."]


def _run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False)


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _runtime_log_root(env_file: Path, requested: Path | None) -> Path:
    if requested is not None:
        return requested
    if configured := os.environ.get("FREYJA6_LOG_ROOT"):
        return Path(configured)
    resolved_env = _resolve(env_file)
    if resolved_env.exists():
        for line in resolved_env.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("FREYJA6_LOG_ROOT="):
                value = stripped.split("=", 1)[1].strip()
                if value:
                    return Path(value)
    return FALLBACK_LOG_ROOT


def _passed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "pass", "message": message}


def _failed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "fail", "message": message}


def _output_path_failure(output: Path) -> str | None:
    if output.is_symlink():
        return f"output path must not be a symlink: {output.name}"
    if output.exists() and not output.is_file():
        return f"output path must be a regular file: {output.name}"
    return None


def _error_report(error: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-stack-status",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "status": "not-ready",
        "error": error,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_failure = _output_path_failure(args.output)
    report = (
        _error_report(output_failure)
        if output_failure
        else build_report(
            env_file=args.env_file,
            compose_file=args.compose_file,
            log_root=_runtime_log_root(args.env_file, args.log_root),
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
