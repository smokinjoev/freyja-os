#!/usr/bin/env python3
"""Run a Freyja 6 validation bundle and summarize redacted results."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_ENV_FILE = Path("deploy/compose/freyja6/.env")
DEFAULT_EVIDENCE = Path("certification/reports/freyja6-live-evidence.json")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-live-validation-bundle.json")
DEFAULT_LOG_ROOT = Path(os.environ.get("FREYJA6_LOG_ROOT", "/srv/freyja6/logs"))
REQUIRED_ACCEPTANCE_IDS = [
    "discord_reply",
    "restart_identity_session",
    "remember_fact",
    "litellm_to_vulcan",
    "model_switch",
    "approved_file_read",
    "safe_terminal",
    "mcp_tool",
    "calendar_read",
    "calendar_create_event",
    "home_assistant_query",
    "coding_workflow",
    "atlas_reboot_return",
]
REQUIRED_ACCEPTANCE_EVIDENCE_FIELDS = {
    "discord_reply": ["discord_channel_id_redacted", "message_trace_id", "reply_trace_id", "verification_method"],
    "restart_identity_session": ["restart_trace_id", "identity_before", "identity_after", "session_restored"],
    "remember_fact": ["stored_fact_label", "recall_trace_id", "memory_provider"],
    "litellm_to_vulcan": ["litellm_request_id", "model", "response_model", "vulcan_backend"],
    "model_switch": ["models_tested", "response_models", "gateway_trace_ids"],
    "approved_file_read": ["approved_path", "tool_trace_id", "bytes_read"],
    "safe_terminal": ["command", "tool_trace_id", "exit_code", "working_dir"],
    "mcp_tool": ["server", "tool", "tool_trace_id", "status_code"],
    "calendar_read": ["calendar_name_redacted", "tool_trace_id", "status_code"],
    "calendar_create_event": ["event_title", "event_date", "tool_trace_id", "created_event_id"],
    "home_assistant_query": ["entity_id_redacted", "tool_trace_id", "states_count"],
    "coding_workflow": ["executor", "handoff_trace_id", "result_summary", "status_keys"],
    "atlas_reboot_return": [
        "reboot_window",
        "container_status_after",
        "discord_reply_after_reboot",
        "discord_reply_after_reboot_verification",
    ],
}
REQUIRED_ACCEPTANCE_METADATA = ["captured_at", "source"]
EXPECTED_ACCEPTANCE_SOURCES = {
    "discord_reply": "freyja6-discord-smoke",
    "restart_identity_session": "freyja6-restart-evidence",
    "remember_fact": "freyja6-restart-evidence",
    "litellm_to_vulcan": "freyja6-litellm-smoke",
    "model_switch": "freyja6-litellm-smoke",
    "approved_file_read": "freyja6-tool-smoke",
    "safe_terminal": "freyja6-tool-smoke",
    "mcp_tool": "freyja6-tool-smoke",
    "calendar_read": "freyja6-tool-smoke",
    "calendar_create_event": "freyja6-calendar-write-smoke",
    "home_assistant_query": "freyja6-tool-smoke",
    "coding_workflow": "freyja6-tool-smoke",
    "atlas_reboot_return": "freyja6-restart-evidence",
}

Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Freyja 6 validation helpers in acceptance order.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--log-root", type=Path, default=None, help="Override FREYJA6_LOG_ROOT from the env file.")
    parser.add_argument("--live", action="store_true", help="Run live network/tool smokes after local readiness checks.")
    parser.add_argument("--create-dirs", action="store_true", help="Allow preflight/bootstrap to create Freyja 6 host directories.")
    parser.add_argument("--build-hermes-image", action="store_true", help="Build the pinned Hermes Agent image before preflight.")
    parser.add_argument("--calendar-write", action="store_true", help="Run the guarded calendar write smoke.")
    parser.add_argument("--prepare-restart-evidence", action="store_true", help="Seed restart/session/memory markers before restart validation.")
    parser.add_argument("--restart-evidence", action="store_true", help="Collect restart/reboot evidence from supplied env values.")
    parser.add_argument("--fail-fast", action="store_true")
    return parser


def run_bundle(
    *,
    env_file: Path,
    evidence: Path,
    output: Path,
    log_root: Path | None,
    live: bool = False,
    create_dirs: bool = False,
    build_hermes_image: bool = False,
    calendar_write: bool = False,
    prepare_restart_evidence: bool = False,
    restart_evidence: bool = False,
    fail_fast: bool = False,
    runner: Runner | None = None,
) -> dict[str, Any]:
    _validate_bundle_output_path(output)
    env_path = _resolve(env_file)
    source_failure = _env_source_file_failure(env_path)
    if source_failure:
        report = _blocked_report(
            env_file=env_file,
            evidence=evidence,
            output=output,
            log_root=log_root or DEFAULT_LOG_ROOT,
            failure=source_failure,
            live=live,
        )
        _write_bundle_report(output, report)
        return report
    env = _load_env(env_path)
    effective_log_root = _effective_log_root(log_root, env)
    run = runner or _run_command
    steps = _steps(
        env_file=env_file,
        evidence=evidence,
        output=output,
        log_root=effective_log_root,
        env=env,
        live=live,
        create_dirs=create_dirs,
        build_hermes_image=build_hermes_image,
        calendar_write=calendar_write,
        prepare_restart_evidence=prepare_restart_evidence,
        restart_evidence=restart_evidence,
    )
    step_definition_failures = _step_definition_failures(steps) + _side_report_path_failures(steps, output=output)
    results: list[dict[str, Any]] = []
    if step_definition_failures:
        results.append(
            {
                "id": "bundle_contract",
                "required": True,
                "status": "fail",
                "exit_code": None,
                "summary": "Live validation bundle step definitions are invalid.",
                "command": [],
                "failures": step_definition_failures,
            }
        )
    else:
        for step in steps:
            if not step["enabled"]:
                results.append(_skipped_result(step, step["reason"]))
                continue
            result = _execute_step(step, run)
            results.append(result)
            if fail_fast and result["required"] and result["status"] == "fail":
                break
    failed_required = [item for item in results if item["required"] and item["status"] == "fail"]
    skipped_required = [item for item in results if item["required"] and item["status"] == "skip"]
    report = {
        "schema_version": "1.0",
        "report_type": "freyja6-live-validation-bundle",
        "run_id": _new_run_id(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "env_file": str(env_file),
        "evidence": str(evidence),
        "log_root": _redact_log_root(effective_log_root),
        "live": live,
        "complete": not failed_required and not skipped_required,
        "status": "complete" if not failed_required and not skipped_required else "incomplete",
        "results": results,
        "failed_required": [item["id"] for item in failed_required],
        "skipped_required": [item["id"] for item in skipped_required],
        **({"step_definition_failures": step_definition_failures} if step_definition_failures else {}),
        "next_actions": _next_actions(failed_required, skipped_required, results),
    }
    _write_bundle_report(output, report)
    return report


def _validate_bundle_output_path(output: Path) -> None:
    if output.is_symlink():
        raise ValueError(f"Bundle output must not be a symlink: {output.name}.")
    if output.exists() and not output.is_file():
        raise ValueError(f"Bundle output must be a regular file: {output.name}.")


def _write_bundle_report(output: Path, report: dict[str, Any]) -> None:
    _validate_bundle_output_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _env_source_file_failure(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        return {
            "id": "env_source_file",
            "required": True,
            "status": "fail",
            "exit_code": None,
            "summary": "Freyja 6 validation bundle env file must be a regular file, not a symlink.",
            "command": [],
            "symlinks": [str(path)],
            "not_regular": [],
        }
    if path.exists() and not path.is_file():
        return {
            "id": "env_source_file",
            "required": True,
            "status": "fail",
            "exit_code": None,
            "summary": "Freyja 6 validation bundle env file must be a regular file, not a symlink.",
            "command": [],
            "symlinks": [],
            "not_regular": [str(path)],
        }
    return None


def _blocked_report(
    *,
    env_file: Path,
    evidence: Path,
    output: Path,
    log_root: Path,
    failure: dict[str, Any],
    live: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-live-validation-bundle",
        "run_id": _new_run_id(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "env_file": str(env_file),
        "evidence": str(evidence),
        "log_root": _redact_log_root(log_root),
        "live": live,
        "complete": False,
        "status": "incomplete",
        "results": [failure],
        "failed_required": [failure["id"]],
        "skipped_required": [],
        "next_actions": [failure["summary"]],
    }


def _steps(
    *,
    env_file: Path,
    evidence: Path,
    output: Path,
    log_root: Path,
    env: dict[str, str],
    live: bool,
    create_dirs: bool,
    build_hermes_image: bool,
    calendar_write: bool,
    prepare_restart_evidence: bool,
    restart_evidence: bool,
) -> list[dict[str, Any]]:
    py = str(VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable))
    steps: list[dict[str, Any]] = [
        {
            "id": "preservation_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-preservation-audit",
            "cmd": [py, "scripts/freyja6-preservation-audit.py", "--output", str(_side_report(output, "preservation-audit"))],
        },
        {
            "id": "env_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-env-audit",
            "cmd": [py, "scripts/freyja6-env-audit.py", "--env-file", str(env_file), "--output", str(_side_report(output, "env-audit"))],
        },
        {
            "id": "hermes_contract",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-hermes-contract",
            "cmd": [py, "scripts/freyja6-hermes-contract.py", "--output", str(_side_report(output, "hermes-contract"))],
        },
        {
            "id": "model_privacy_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-model-privacy-audit",
            "cmd": [py, "scripts/freyja6-model-privacy-audit.py", "--output", str(_side_report(output, "model-privacy-audit"))],
        },
        {
            "id": "gateway_isolation_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-gateway-isolation-audit",
            "cmd": [py, "scripts/freyja6-gateway-isolation-audit.py", "--output", str(_side_report(output, "gateway-isolation-audit"))],
        },
        {
            "id": "memory_boundary_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-memory-boundary-audit",
            "cmd": [py, "scripts/freyja6-memory-boundary-audit.py", "--output", str(_side_report(output, "memory-boundary-audit"))],
        },
        {
            "id": "messaging_gateway_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-messaging-gateway-audit",
            "cmd": [py, "scripts/freyja6-messaging-gateway-audit.py", "--output", str(_side_report(output, "messaging-gateway-audit"))],
        },
        {
            "id": "terminal_safety_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-terminal-safety-audit",
            "cmd": [py, "scripts/freyja6-terminal-safety-audit.py", "--output", str(_side_report(output, "terminal-safety-audit"))],
        },
        {
            "id": "filesystem_boundary_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-filesystem-boundary-audit",
            "cmd": [py, "scripts/freyja6-filesystem-boundary-audit.py", "--output", str(_side_report(output, "filesystem-boundary-audit"))],
        },
        {
            "id": "mcp_boundary_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-mcp-boundary-audit",
            "cmd": [py, "scripts/freyja6-mcp-boundary-audit.py", "--output", str(_side_report(output, "mcp-boundary-audit"))],
        },
        {
            "id": "coding_workflow_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-coding-workflow-audit",
            "cmd": [py, "scripts/freyja6-coding-workflow-audit.py", "--output", str(_side_report(output, "coding-workflow-audit"))],
        },
        {
            "id": "schedule_boundary_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-schedule-boundary-audit",
            "cmd": [py, "scripts/freyja6-schedule-boundary-audit.py", "--output", str(_side_report(output, "schedule-boundary-audit"))],
        },
        {
            "id": "calendar_boundary_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-calendar-boundary-audit",
            "cmd": [py, "scripts/freyja6-calendar-boundary-audit.py", "--output", str(_side_report(output, "calendar-boundary-audit"))],
        },
        {
            "id": "home_assistant_boundary_audit",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-home-assistant-boundary-audit",
            "cmd": [py, "scripts/freyja6-home-assistant-boundary-audit.py", "--output", str(_side_report(output, "home-assistant-boundary-audit"))],
        },
        {
            "id": "hermes_image",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-hermes-image",
            "cmd": [py, "scripts/freyja6-hermes-image.py", "--env-file", str(env_file), "--output", str(_side_report(output, "hermes-image"))]
            + (["--build"] if build_hermes_image else []),
        },
        {
            "id": "atlas_preflight",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-atlas-preflight",
            "cmd": [
                py,
                "scripts/freyja6-atlas-preflight.py",
                "--env-file",
                str(env_file),
                "--output",
                str(_side_report(output, "atlas-preflight")),
                "--check-images",
                "--check-vulcan",
            ]
            + (["--create-dirs"] if create_dirs else []),
        },
        {
            "id": "bootstrap_atlas",
            "required": live,
            "enabled": live,
            "reason": "Run with --live to seed Atlas directories.",
            "report_type": "freyja6-bootstrap-atlas",
            "cmd": [py, "scripts/freyja6-bootstrap-atlas.py", "--env-file", str(env_file), "--output", str(_side_report(output, "bootstrap-atlas"))],
        },
        {
            "id": "schedule_smoke",
            "required": True,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-schedule-smoke",
            "cmd": [
                py,
                "scripts/freyja6-schedule-smoke.py",
                "--log-root",
                str(log_root),
                "--output",
                str(_side_report(output, "schedule-smoke")),
            ]
            + (["--write-logs"] if live else []),
        },
        {
            "id": "stack_status",
            "required": live,
            "enabled": live,
            "reason": "Run with --live after compose is up.",
            "report_type": "freyja6-stack-status",
            "cmd": [
                py,
                "scripts/freyja6-stack-status.py",
                "--env-file",
                str(env_file),
                "--log-root",
                str(log_root),
                "--output",
                str(_side_report(output, "stack-status")),
            ],
        },
        {
            "id": "discord_reply",
            "required": live,
            "enabled": live and _discord_evidence_ready(env),
            "reason": "Set Discord bot token, channel ID, and message/reply IDs for API verification.",
            "cmd": _discord_cmd(py, env, evidence, log_root),
        },
        {
            "id": "litellm_vulcan",
            "required": live,
            "enabled": live,
            "reason": "Run with --live after compose is up.",
            "cmd": [
                py,
                "scripts/freyja6-litellm-smoke.py",
                "--evidence",
                str(evidence),
                "--base-url",
                env.get("FREYJA6_LITELLM_BASE_URL", "http://127.0.0.1:4600/v1"),
                "--api-key",
                env.get("LITELLM_MASTER_KEY", ""),
                "--log-root",
                str(log_root),
                "--models",
                "vulcan-general",
                "vulcan-fast",
                "vulcan-code",
            ],
        },
        {
            "id": "tool_smoke",
            "required": live,
            "enabled": live,
            "reason": "Run with --live after Freyja Core and MCP services are reachable.",
            "cmd": [
                py,
                "scripts/freyja6-tool-smoke.py",
                "--evidence",
                str(evidence),
                "--core-url",
                env.get("FREYJA6_CORE_URL", "http://127.0.0.1:8510"),
                "--core-mcp-health-url",
                env.get("FREYJA6_CORE_MCP_HEALTH_URL", "http://127.0.0.1:8766/healthz"),
                "--terminal-mcp-health-url",
                env.get("FREYJA6_TERMINAL_MCP_HEALTH_URL", "http://127.0.0.1:8765/healthz"),
                "--approved-file",
                env.get("FREYJA6_APPROVED_SMOKE_FILE", str(Path(env.get("FREYJA6_APPROVED_FILES_ROOT", "/srv/freyja6/approved-files")) / "smoke.txt")),
                "--calendar-start",
                env.get("FREYJA6_CALENDAR_SMOKE_START", "2026-09-19T00:00:00+00:00"),
                "--calendar-end",
                env.get("FREYJA6_CALENDAR_SMOKE_END", "2026-09-20T00:00:00+00:00"),
                "--home-domain",
                env.get("FREYJA6_HOME_SMOKE_DOMAIN", "sensor"),
                "--log-root",
                str(log_root),
            ],
        },
        {
            "id": "calendar_write",
            "required": live,
            "enabled": live and calendar_write,
            "reason": "Run with --calendar-write when ready to create the real validation event.",
            "cmd": [
                py,
                "scripts/freyja6-calendar-write-smoke.py",
                "--evidence",
                str(evidence),
                "--core-url",
                env.get("FREYJA6_CORE_URL", "http://127.0.0.1:8510"),
                "--calendar-id",
                env.get("FREYJA6_CALENDAR_WRITE_CALENDAR_ID", ""),
                "--base-date",
                env.get("FREYJA6_CALENDAR_WRITE_BASE_DATE", ""),
                "--start-time",
                env.get("FREYJA6_CALENDAR_WRITE_START_TIME", "09:00:00"),
                "--log-root",
                str(log_root),
                "--approval",
                "CREATE_BASEMENT_CLEANUP_TEST_EVENT",
            ],
        },
        {
            "id": "prepare_restart_evidence",
            "required": False,
            "enabled": live and prepare_restart_evidence,
            "reason": "Run with --prepare-restart-evidence before restarting Hermes or rebooting Atlas.",
            "cmd": [
                py,
                "scripts/freyja6-prepare-restart-evidence.py",
                "--evidence",
                str(evidence),
                "--hermes-data",
                env.get("FREYJA6_HERMES_DATA", "/srv/freyja6/hermes"),
                "--session-id",
                env.get("FREYJA6_RESTORED_SESSION_ID", ""),
                "--stored-fact-label",
                env.get("FREYJA6_MEMORY_FACT_LABEL", "freyja6-validation-basement-cleanup"),
            ],
        },
        {
            "id": "restart_evidence",
            "required": live,
            "enabled": live and restart_evidence,
            "reason": "Run with --restart-evidence after restart or Atlas reboot validation.",
            "cmd": _restart_cmd(py, env, evidence, log_root),
        },
        {
            "id": "log_audit",
            "required": live,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-log-audit",
            "cmd": [
                py,
                "scripts/freyja6-log-audit.py",
                "--log-root",
                str(log_root),
                "--output",
                str(_side_report(output, "log-audit")),
            ]
            + (["--require-entries"] if live else []),
        },
        {
            "id": "acceptance_status",
            "required": live,
            "enabled": True,
            "reason": "",
            "report_type": "freyja6-acceptance-status",
            "expected_evidence": evidence,
            "cmd": [py, "scripts/freyja6-acceptance-status.py", "--evidence", str(evidence), "--output", str(_side_report(output, "acceptance-status"))],
        },
    ]
    return steps


def _execute_step(step: dict[str, Any], runner: Runner) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    result = runner(step["cmd"])
    finished_at = datetime.now(timezone.utc)
    payload = _last_json(result.stdout)
    payload_missing = payload is None
    payload_failure = _payload_indicates_failure(payload)
    report_type_failure = _payload_report_type_mismatch(payload, step.get("report_type"))
    contract_failure = report_type_failure or _payload_contract_failure(payload, step, payload_failure=payload_failure)
    report_path = _output_report_from_command(step["cmd"])
    side_report_failure = "" if contract_failure or payload_failure else _side_report_contract_failure(report_path, payload, step)
    status = "fail" if result.returncode != 0 or payload_missing or payload_failure else "pass"
    if contract_failure or side_report_failure:
        status = "fail"
    return {
        "id": step["id"],
        "required": step["required"],
        "status": status,
        "exit_code": result.returncode,
        "summary": contract_failure or side_report_failure or (_summary_from_payload(payload) if payload else (result.stderr or result.stdout)[-500:]),
        "command": _redact_command(step["cmd"]),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        **({"report": _redact_artifact_path(report_path)} if report_path else {}),
        **({"payload_missing": payload_missing} if payload_missing else {}),
        **({"payload_failure": payload_failure} if payload_failure else {}),
        **({"report_type_failure": report_type_failure} if report_type_failure else {}),
        **({"contract_failure": contract_failure} if contract_failure and not report_type_failure else {}),
        **({"side_report_failure": side_report_failure} if side_report_failure else {}),
    }


def _step_definition_failures(steps: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    seen: dict[str, int] = {}
    for index, step in enumerate(steps, start=1):
        raw_step_id = step.get("id")
        if not isinstance(raw_step_id, str) or not raw_step_id:
            failures.append(f"step {index} must have an id.")
            continue
        step_id = raw_step_id
        seen[step_id] = seen.get(step_id, 0) + 1
        if not isinstance(step.get("required"), bool):
            failures.append(f"{step_id} required must be a boolean.")
        if not isinstance(step.get("enabled"), bool):
            failures.append(f"{step_id} enabled must be a boolean.")
        if not isinstance(step.get("reason"), str):
            failures.append(f"{step_id} reason must be a string.")
        report_type = step.get("report_type")
        if report_type is not None and (not isinstance(report_type, str) or not report_type):
            failures.append(f"{step_id} report_type must be a non-empty string when present.")
        cmd = step.get("cmd")
        if not isinstance(cmd, list):
            failures.append(f"{step_id} cmd must be a list.")
        elif not cmd or any(not isinstance(part, str) for part in cmd):
            failures.append(f"{step_id} cmd must contain string parts.")
        elif isinstance(report_type, str) and report_type and _output_report_from_command(cmd) is None:
            failures.append(f"{step_id} report-bearing command must include --output.")
    duplicates = sorted(step_id for step_id, count in seen.items() if count > 1)
    for step_id in duplicates:
        failures.append(f"{step_id} step id must be unique.")
    return failures


def _side_report_path_failures(steps: list[dict[str, Any]], *, output: Path) -> list[str]:
    failures = []
    expected_parent = _resolve(output).parent
    expected_prefix = f"{output.stem}-"
    expected_suffix = output.suffix
    for step in steps:
        if step.get("enabled") is not True or not step.get("report_type"):
            continue
        cmd = step.get("cmd")
        if not isinstance(cmd, list):
            continue
        report_path = _output_report_from_command(cmd)
        if report_path is None:
            continue
        resolved = _resolve(report_path)
        if resolved.parent != expected_parent or not report_path.name.startswith(expected_prefix) or report_path.suffix != expected_suffix:
            failures.append(f"{step.get('id')} side report output must stay next to the bundle output: {report_path.name}.")
            continue
        if resolved.is_symlink():
            failures.append(f"{step.get('id')} side report output must not be a symlink: {report_path.name}.")
        elif resolved.exists() and not resolved.is_file():
            failures.append(f"{step.get('id')} side report output must be a regular file: {report_path.name}.")
    return failures


def _skipped_result(step: dict[str, Any], reason: str) -> dict[str, Any]:
    report_path = _output_report_from_command(step["cmd"])
    return {
        "id": step["id"],
        "required": step["required"],
        "status": "skip",
        "exit_code": None,
        "summary": reason,
        "command": _redact_command(step["cmd"]),
        **({"report": _redact_artifact_path(report_path)} if report_path else {}),
    }


def _run_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False)


def _new_run_id() -> str:
    return f"freyja6-live-{uuid.uuid4()}"


def _discord_cmd(py: str, env: dict[str, str], evidence: Path, log_root: Path) -> list[str]:
    cmd = [
        py,
        "scripts/freyja6-discord-smoke.py",
        "--evidence",
        str(evidence),
        "--log-root",
        str(log_root),
        "--channel-id",
        env.get("FREYJA6_DISCORD_CHANNEL_ID", ""),
        "--bot-token",
        env.get("FREYJA6_DISCORD_BOT_TOKEN", ""),
    ]
    if env.get("FREYJA6_DISCORD_SMOKE_MESSAGE_ID") and env.get("FREYJA6_DISCORD_SMOKE_REPLY_ID"):
        cmd += [
            "--message-id",
            env["FREYJA6_DISCORD_SMOKE_MESSAGE_ID"],
            "--reply-id",
            env["FREYJA6_DISCORD_SMOKE_REPLY_ID"],
        ]
    else:
        cmd += [
            "--message-trace-id",
            env.get("FREYJA6_DISCORD_MESSAGE_TRACE_ID", ""),
            "--reply-trace-id",
            env.get("FREYJA6_DISCORD_REPLY_TRACE_ID", ""),
            "--manual-confirmation",
            env.get("FREYJA6_DISCORD_MANUAL_CONFIRMATION", ""),
        ]
    return cmd


def _restart_cmd(py: str, env: dict[str, str], evidence: Path, log_root: Path) -> list[str]:
    return [
        py,
        "scripts/freyja6-restart-evidence.py",
        "--evidence",
        str(evidence),
        "--log-root",
        str(log_root),
        "--hermes-data",
        env.get("FREYJA6_HERMES_DATA", "/srv/freyja6/hermes"),
        "--before-identity-sha256",
        env.get("FREYJA6_IDENTITY_SHA256_BEFORE", ""),
        "--session-id",
        env.get("FREYJA6_RESTORED_SESSION_ID", ""),
        "--stored-fact-label",
        env.get("FREYJA6_MEMORY_FACT_LABEL", ""),
        "--memory-recall-trace-id",
        env.get("FREYJA6_MEMORY_RECALL_TRACE_ID", ""),
        "--container-status",
        env.get("FREYJA6_CONTAINER_STATUS_AFTER", ""),
        "--reboot-start",
        env.get("FREYJA6_REBOOT_START", ""),
        "--reboot-end",
        env.get("FREYJA6_REBOOT_END", ""),
        "--discord-reply-trace-id",
        env.get("FREYJA6_DISCORD_REPLY_AFTER_REBOOT_TRACE_ID", ""),
        "--discord-reply-verification",
        env.get("FREYJA6_DISCORD_REPLY_AFTER_REBOOT_VERIFICATION", ""),
    ]


def _last_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    payload = None
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            candidate, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if not text[index + end :].strip():
            return candidate
        payload = candidate
    return payload


def _summary_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "completed"
    if isinstance(payload.get("next_actions"), list) and payload["next_actions"]:
        return str(payload["next_actions"][0])
    if isinstance(payload.get("blockers"), list) and payload["blockers"]:
        blocker = payload["blockers"][0]
        if isinstance(blocker, dict) and blocker.get("message"):
            return str(blocker["message"])
    if isinstance(payload.get("failures"), list) and payload["failures"]:
        failure = payload["failures"][0]
        if isinstance(failure, dict) and failure.get("message"):
            return str(failure["message"])
        return str(failure)
    if "ok" in payload:
        return "ok" if payload["ok"] else "not ok"
    if "ready" in payload:
        return "ready" if payload["ready"] else "not ready"
    if "complete" in payload:
        return "complete" if payload["complete"] else "incomplete"
    for key in ("status", "message"):
        if payload.get(key):
            return str(payload[key])
    return "completed"


def _payload_indicates_failure(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("ok") is False:
        return True
    if payload.get("complete") is False:
        return True
    if payload.get("ready") is False:
        return True
    if isinstance(payload.get("failures"), list) and payload["failures"]:
        return True
    if isinstance(payload.get("blockers"), list) and payload["blockers"]:
        return True
    if _nested_checks_indicate_failure(payload.get("checks")):
        return True
    status = str(payload.get("status") or "").lower()
    return status in {"fail", "failed", "error", "incomplete", "not_ready", "not-ready", "blocked"}


def _payload_report_type_mismatch(payload: Any, expected: Any) -> str:
    if not isinstance(payload, dict) or not expected:
        return ""
    actual = payload.get("report_type")
    if actual is None:
        return ""
    if actual != expected:
        return f"report_type must be {expected}, got {actual}."
    return ""


def _payload_contract_failure(payload: Any, step: dict[str, Any], *, payload_failure: bool) -> str:
    if not isinstance(payload, dict):
        return ""
    expected_report_type = step.get("report_type")
    if not payload_failure and expected_report_type and payload.get("report_type") == expected_report_type and not _payload_has_success_signal(payload):
        return f"{step.get('id')} payload must include an explicit success signal."
    expected = step.get("expected_evidence")
    if expected and "evidence" in payload and _normalize_reference(str(payload.get("evidence") or "")) != _normalize_reference(str(expected)):
        return f"{step.get('id')} evidence must match the bundle evidence path."
    return ""


def _side_report_contract_failure(report_path: Path | None, payload: Any, step: dict[str, Any]) -> str:
    expected = step.get("report_type")
    if not report_path or not isinstance(payload, dict) or not expected:
        return ""
    if payload.get("report_type") != expected:
        return ""
    resolved = _resolve(report_path)
    if resolved.is_symlink():
        return f"{report_path.name} side report must not be a symlink."
    if resolved.exists() and not resolved.is_file():
        return f"{report_path.name} side report must be a regular file."
    try:
        report_payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return f"{report_path.name} side report must exist and be valid JSON."
    if not isinstance(report_payload, dict):
        return f"{report_path.name} side report must be a JSON object."
    if report_payload.get("report_type") != expected:
        return f"{report_path.name} side report must have report_type {expected}."
    if report_payload.get("schema_version") != "1.0":
        return f"{report_path.name} side report schema_version must be 1.0."
    timestamp_failure = _side_report_timestamp_failure(report_payload)
    if timestamp_failure:
        return f"{report_path.name} side report {timestamp_failure}"
    if _payload_indicates_failure(report_payload):
        return f"{report_path.name} side report must not indicate failure."
    if not _payload_has_success_signal(report_payload):
        return f"{report_path.name} side report must include an explicit success signal."
    expected_evidence = step.get("expected_evidence")
    if expected_evidence and "evidence" in report_payload and _normalize_reference(str(report_payload.get("evidence") or "")) != _normalize_reference(str(expected_evidence)):
        return f"{report_path.name} side report evidence must match the bundle evidence path."
    acceptance_failure = _acceptance_status_side_report_failure(report_payload, expected)
    if acceptance_failure:
        return f"{report_path.name} side report {acceptance_failure}"
    return ""


def _acceptance_status_side_report_failure(payload: dict[str, Any], expected_report_type: Any) -> str:
    if expected_report_type != "freyja6-acceptance-status":
        return ""
    if payload.get("status") != "complete" or payload.get("complete") is not True:
        return "must report complete acceptance status."
    if payload.get("secrets_detected") is not False:
        return "must report secrets_detected false."
    remaining = payload.get("remaining_acceptance")
    if not isinstance(remaining, list) or remaining:
        return "remaining_acceptance must be an empty list."
    evidence_contract = payload.get("evidence_contract")
    if not isinstance(evidence_contract, dict) or evidence_contract.get("status") != "pass":
        return "evidence_contract status must be pass."
    acceptance = payload.get("acceptance")
    if not isinstance(acceptance, list) or not acceptance:
        return "acceptance must be a non-empty list."
    seen_ids: set[str] = set()
    for item in acceptance:
        if not isinstance(item, dict) or not item.get("id"):
            return "acceptance entries must be objects with ids."
        item_id = str(item.get("id"))
        if item_id not in REQUIRED_ACCEPTANCE_IDS:
            return f"acceptance {item_id} is not in the Freyja 6 acceptance contract."
        if item_id in seen_ids:
            return f"acceptance {item_id} must not be duplicated."
        seen_ids.add(item_id)
        if item.get("status") != "complete":
            return f"acceptance {item_id} status must be complete."
        for field in ("missing_evidence", "missing_metadata", "semantic_failures"):
            value = item.get(field)
            if not isinstance(value, list) or value:
                return f"acceptance {item_id} {field} must be an empty list."
        expected_evidence = REQUIRED_ACCEPTANCE_EVIDENCE_FIELDS[item_id]
        required_evidence = item.get("required_evidence")
        if not isinstance(required_evidence, list) or list(map(str, required_evidence)) != expected_evidence:
            return f"acceptance {item_id} required_evidence must match the Freyja 6 acceptance contract."
        present_evidence = item.get("present_evidence")
        if not isinstance(present_evidence, list) or set(map(str, present_evidence)) != set(expected_evidence):
            return f"acceptance {item_id} present_evidence must match required_evidence."
        required_metadata = item.get("required_metadata")
        if not isinstance(required_metadata, list) or list(map(str, required_metadata)) != REQUIRED_ACCEPTANCE_METADATA:
            return f"acceptance {item_id} required_metadata must match the Freyja 6 acceptance contract."
        metadata = item.get("metadata")
        if not isinstance(metadata, dict) or set(metadata) != {"captured_at", "source"}:
            return f"acceptance {item_id} metadata must contain captured_at and source."
        captured_at_failure = _acceptance_metadata_captured_at_failure(metadata.get("captured_at"))
        if captured_at_failure:
            return f"acceptance {item_id} metadata captured_at {captured_at_failure}"
        expected_source = EXPECTED_ACCEPTANCE_SOURCES[item_id]
        if metadata.get("source") != expected_source:
            return f"acceptance {item_id} metadata source must be {expected_source}."
    missing_ids = [item_id for item_id in REQUIRED_ACCEPTANCE_IDS if item_id not in seen_ids]
    if missing_ids:
        return f"acceptance must include {missing_ids[0]}."
    return ""


def _acceptance_metadata_captured_at_failure(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "must be a non-empty ISO timestamp."
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "must be an ISO timestamp with timezone."
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return "must be an ISO timestamp with timezone."
    if parsed > datetime.now(timezone.utc):
        return "must not be in the future."
    return ""


def _side_report_timestamp_failure(payload: dict[str, Any]) -> str:
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp:
        return "timestamp must be present."
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return "timestamp must be an ISO timestamp."
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return "timestamp must include a timezone offset."
    if parsed > datetime.now(timezone.utc):
        return "timestamp must not be in the future."
    return ""


def _payload_has_success_signal(payload: dict[str, Any]) -> bool:
    if payload.get("ok") is True:
        return True
    if payload.get("ready") is True:
        return True
    if payload.get("complete") is True:
        return True
    status = str(payload.get("status") or "").lower()
    return status in {"pass", "ready", "complete"}


def _normalize_reference(value: str) -> str:
    if not value:
        return ""
    path = Path(value)
    resolved = path if path.is_absolute() else REPO_ROOT / path
    try:
        return str(resolved.resolve())
    except OSError:
        return str(resolved)


def _nested_checks_indicate_failure(checks: Any) -> bool:
    if not isinstance(checks, list):
        return False
    for check in checks:
        if not isinstance(check, dict):
            continue
        status = str(check.get("status") or "").lower()
        if status in {"fail", "failed", "error", "blocked", "not_ready", "not-ready", "incomplete"}:
            return True
        if check.get("ok") is False or check.get("ready") is False or check.get("complete") is False:
            return True
    return False


def _redact_command(cmd: list[str]) -> list[str]:
    redacted: list[str] = []
    secret_next = False
    for part in cmd:
        if secret_next:
            redacted.append("<redacted>")
            secret_next = False
            continue
        redacted.append(part)
        if part in {"--api-key", "--bot-token"}:
            secret_next = True
    return redacted


def _output_report_from_command(cmd: list[str]) -> Path | None:
    try:
        index = cmd.index("--output")
    except ValueError:
        return None
    if index + 1 >= len(cmd):
        return None
    return Path(cmd[index + 1])


def _redact_artifact_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return path.name


def _effective_log_root(log_root: Path | None, env: dict[str, str]) -> Path:
    if log_root is not None:
        return log_root
    return Path(env.get("FREYJA6_LOG_ROOT", "") or DEFAULT_LOG_ROOT)


def _redact_log_root(path: Path) -> str:
    if str(path).startswith("/srv/freyja6/logs"):
        return "freyja6/logs"
    return path.name


def _has_all(env: dict[str, str], *keys: str) -> bool:
    return all(bool(env.get(key, "").strip()) for key in keys)


def _discord_evidence_ready(env: dict[str, str]) -> bool:
    return _has_all(
        env,
        "FREYJA6_DISCORD_BOT_TOKEN",
        "FREYJA6_DISCORD_CHANNEL_ID",
        "FREYJA6_DISCORD_SMOKE_MESSAGE_ID",
        "FREYJA6_DISCORD_SMOKE_REPLY_ID",
    )


def _side_report(output: Path, suffix: str) -> Path:
    return output.with_name(output.stem + f"-{suffix}" + output.suffix)


def _next_actions(failed_required: list[dict[str, Any]], skipped_required: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[str]:
    if failed_required:
        first = failed_required[0]
        return [f"Fix required step {first['id']}: {first['summary']}"]
    if skipped_required:
        first = skipped_required[0]
        return [f"Enable required step {first['id']}: {first['summary']}"]
    incomplete = next((item for item in results if item["id"] == "acceptance_status" and item["status"] != "pass"), None)
    if incomplete:
        return ["Capture the remaining live acceptance evidence reported by acceptance_status."]
    return ["Repeat the full live bundle before migration."]


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    resolved = _resolve(path)
    if not resolved.exists():
        return values
    for line in resolved.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = _expand_env_value(value.strip(), values)
    return values


def _expand_env_value(value: str, values: dict[str, str]) -> str:
    expanded = value
    for key, replacement in values.items():
        expanded = expanded.replace("${" + key + "}", replacement)
    return expanded


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_bundle(
            env_file=args.env_file,
            evidence=args.evidence,
            output=args.output,
            log_root=args.log_root,
            live=args.live,
            create_dirs=args.create_dirs,
            build_hermes_image=args.build_hermes_image,
            calendar_write=args.calendar_write,
            prepare_restart_evidence=args.prepare_restart_evidence,
            restart_evidence=args.restart_evidence,
            fail_fast=args.fail_fast,
        )
    except ValueError as exc:
        report = {
            "schema_version": "1.0",
            "report_type": "freyja6-live-validation-bundle",
            "run_id": _new_run_id(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "complete": False,
            "status": "incomplete",
            "error": str(exc),
        }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
