#!/usr/bin/env python3
"""Gate Freyja 6 migration on repeated complete validation evidence."""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_ACCEPTANCE_STATUS = Path("certification/reports/freyja6-acceptance-status.json")
DEFAULT_PRESERVATION_REPORT = Path("certification/reports/freyja6-preservation-audit.json")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-migration-readiness.json")
DEFAULT_BUNDLE_GLOB = "certification/reports/freyja6-live-validation-bundle*.json"
MIN_REQUIRED_SUCCESSFUL_RUNS = 3
MIGRATION_ORDER = ["freyja-test", "Freyja", "Cloyd", "Benedict", "Agent 44", "Agent Smith"]
REQUIRED_PRESERVATION_CHECKS = [
    "source_files",
    "guardrails",
    "phase_one_agent_scope",
    "compose_side_by_side",
    "legacy_runtime_coupling",
    "legacy_evidence_present",
]
REQUIRED_LIVE_BUNDLE_STEPS = {
    "preservation_audit",
    "env_audit",
    "hermes_contract",
    "model_privacy_audit",
    "gateway_isolation_audit",
    "memory_boundary_audit",
    "messaging_gateway_audit",
    "terminal_safety_audit",
    "filesystem_boundary_audit",
    "mcp_boundary_audit",
    "coding_workflow_audit",
    "schedule_boundary_audit",
    "calendar_boundary_audit",
    "home_assistant_boundary_audit",
    "hermes_image",
    "atlas_preflight",
    "bootstrap_atlas",
    "schedule_smoke",
    "stack_status",
    "discord_reply",
    "litellm_vulcan",
    "tool_smoke",
    "calendar_write",
    "restart_evidence",
    "log_audit",
    "acceptance_status",
}
REQUIRED_LIVE_BUNDLE_REPORT_STEPS = REQUIRED_LIVE_BUNDLE_STEPS - {
    "discord_reply",
    "litellm_vulcan",
    "tool_smoke",
    "calendar_write",
    "restart_evidence",
}
REQUIRED_LIVE_BUNDLE_COMMAND_SCRIPTS = {
    "preservation_audit": "scripts/freyja6-preservation-audit.py",
    "env_audit": "scripts/freyja6-env-audit.py",
    "hermes_contract": "scripts/freyja6-hermes-contract.py",
    "model_privacy_audit": "scripts/freyja6-model-privacy-audit.py",
    "gateway_isolation_audit": "scripts/freyja6-gateway-isolation-audit.py",
    "memory_boundary_audit": "scripts/freyja6-memory-boundary-audit.py",
    "messaging_gateway_audit": "scripts/freyja6-messaging-gateway-audit.py",
    "terminal_safety_audit": "scripts/freyja6-terminal-safety-audit.py",
    "filesystem_boundary_audit": "scripts/freyja6-filesystem-boundary-audit.py",
    "mcp_boundary_audit": "scripts/freyja6-mcp-boundary-audit.py",
    "coding_workflow_audit": "scripts/freyja6-coding-workflow-audit.py",
    "schedule_boundary_audit": "scripts/freyja6-schedule-boundary-audit.py",
    "calendar_boundary_audit": "scripts/freyja6-calendar-boundary-audit.py",
    "home_assistant_boundary_audit": "scripts/freyja6-home-assistant-boundary-audit.py",
    "hermes_image": "scripts/freyja6-hermes-image.py",
    "atlas_preflight": "scripts/freyja6-atlas-preflight.py",
    "bootstrap_atlas": "scripts/freyja6-bootstrap-atlas.py",
    "schedule_smoke": "scripts/freyja6-schedule-smoke.py",
    "stack_status": "scripts/freyja6-stack-status.py",
    "discord_reply": "scripts/freyja6-discord-smoke.py",
    "litellm_vulcan": "scripts/freyja6-litellm-smoke.py",
    "tool_smoke": "scripts/freyja6-tool-smoke.py",
    "calendar_write": "scripts/freyja6-calendar-write-smoke.py",
    "restart_evidence": "scripts/freyja6-restart-evidence.py",
    "log_audit": "scripts/freyja6-log-audit.py",
    "acceptance_status": "scripts/freyja6-acceptance-status.py",
}
ALLOWED_LIVE_BUNDLE_PYTHON_LAUNCHERS = {".venv/bin/python", str(VENV_PYTHON)}
LIVE_BUNDLE_REPORT_SUFFIXES = {
    step: step.replace("_", "-")
    for step in REQUIRED_LIVE_BUNDLE_REPORT_STEPS
}
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate whether Freyja 6 is ready to start migration.")
    parser.add_argument("--acceptance-status", type=Path, default=DEFAULT_ACCEPTANCE_STATUS)
    parser.add_argument("--preservation-report", type=Path, default=DEFAULT_PRESERVATION_REPORT)
    parser.add_argument("--bundle-report", type=Path, action="append", default=[])
    parser.add_argument("--bundle-glob", default=DEFAULT_BUNDLE_GLOB)
    parser.add_argument(
        "--min-successful-runs",
        type=int,
        default=MIN_REQUIRED_SUCCESSFUL_RUNS,
        help="Require this many successful live runs; values below 3 are ignored because migration has a hard three-run floor.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(
    *,
    acceptance_status: Path,
    preservation_report: Path,
    bundle_reports: list[Path],
    bundle_glob: str,
    min_successful_runs: int,
) -> dict[str, Any]:
    bundle_paths = bundle_reports or _glob_bundle_reports(bundle_glob)
    required_successful_runs = max(min_successful_runs, MIN_REQUIRED_SUCCESSFUL_RUNS)
    expected_evidence = _acceptance_evidence_reference(acceptance_status)
    checks = [
        _check_preservation(preservation_report),
        _check_acceptance(acceptance_status),
        _check_repeated_live_bundles(bundle_paths, min_successful_runs=required_successful_runs, expected_evidence=expected_evidence),
    ]
    blockers = [check for check in checks if check["status"] == "fail"]
    ready = not blockers
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-migration-readiness",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ready": ready,
        "status": "ready" if ready else "not_ready",
        "migration_order": MIGRATION_ORDER,
        "next_migration_candidate": "Freyja" if ready else "",
        "min_successful_runs": required_successful_runs,
        "requested_min_successful_runs": min_successful_runs,
        "checks": checks,
        "blockers": blockers,
        "next_actions": _next_actions(blockers, ready),
    }


def _check_preservation(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if not payload:
        return _failed("preservation", f"Preservation audit report is missing or unreadable: {path}.")
    contract_failures = _preservation_contract_failures(payload)
    if contract_failures:
        return {
            "id": "preservation",
            "status": "fail",
            "message": "Preservation audit report must be a complete Freyja 6 preservation artifact.",
            "report": _redact_path(path),
            "contract_failures": contract_failures,
        }
    if payload.get("ok") is not True:
        return {
            "id": "preservation",
            "status": "fail",
            "message": "Preservation audit must pass before migration.",
            "report": _redact_path(path),
        }
    return {"id": "preservation", "status": "pass", "message": "Preservation audit passed.", "report": _redact_path(path)}


def _preservation_contract_failures(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    load_failure = payload.get("_load_failure")
    if isinstance(load_failure, str) and load_failure:
        failures.append(load_failure)
    if payload.get("schema_version") != "1.0":
        failures.append("schema_version must be 1.0.")
    if payload.get("report_type") != "freyja6-preservation-audit":
        failures.append("report_type must be freyja6-preservation-audit.")
    if payload.get("ok") is not True:
        failures.append("ok must be true.")
    if payload.get("status") != "pass":
        failures.append("status must be pass.")
    if payload.get("secrets_included") is not False:
        failures.append("secrets_included must be false.")
    summary_failures = payload.get("failures")
    if not isinstance(summary_failures, list):
        failures.append("failures must be a list.")
    elif summary_failures:
        failures.append("failures must be empty.")
    checks = payload.get("checks")
    if not isinstance(checks, list):
        failures.append("checks must be a list.")
    else:
        failures.extend(_preservation_check_failures(checks))
    return failures


def _preservation_check_failures(checks: list[Any]) -> list[str]:
    failures: list[str] = []
    required = set(REQUIRED_PRESERVATION_CHECKS)
    seen: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    malformed_count = 0
    unexpected_ids: set[str] = set()
    for check in checks:
        if not isinstance(check, dict):
            malformed_count += 1
            continue
        check_id = check.get("id")
        if not isinstance(check_id, str) or not check_id:
            malformed_count += 1
            continue
        if check_id in seen:
            duplicate_ids.add(check_id)
        else:
            seen[check_id] = check
        if check_id not in required:
            unexpected_ids.add(check_id)
        if not isinstance(check.get("status"), str):
            failures.append(f"check {check_id} status must be a string.")
    if malformed_count:
        failures.append("checks entries must be objects with string ids.")
    for check_id in sorted(unexpected_ids):
        failures.append(f"checks contain unexpected id {check_id}.")
    for check_id in sorted(duplicate_ids):
        failures.append(f"checks contain duplicate id {check_id}.")
    for check_id in REQUIRED_PRESERVATION_CHECKS:
        check = seen.get(check_id)
        if check is None:
            failures.append(f"checks must include {check_id}.")
        elif check.get("status") != "pass":
            failures.append(f"check {check_id} status must be pass.")
    return failures


def _check_acceptance(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if not payload:
        return _failed("acceptance", f"Acceptance status report is missing or unreadable: {path}.")
    contract_failures = _acceptance_status_contract_failures(payload)
    if contract_failures:
        return {
            "id": "acceptance",
            "status": "fail",
            "message": "Acceptance status report must be a complete Freyja 6 acceptance-status artifact.",
            "report": _redact_path(path),
            "contract_failures": contract_failures,
        }
    if payload.get("complete") is not True:
        return {
            "id": "acceptance",
            "status": "fail",
            "message": "All Freyja 6 acceptance items must be complete before migration.",
            "report": _redact_path(path),
            "remaining_acceptance": payload.get("remaining_acceptance", []),
        }
    if payload.get("secrets_detected") is True:
        return _failed("acceptance", "Acceptance evidence contains secret markers.")
    return {"id": "acceptance", "status": "pass", "message": "Acceptance status is complete and redacted.", "report": _redact_path(path)}


def _acceptance_status_contract_failures(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    load_failure = payload.get("_load_failure")
    if isinstance(load_failure, str) and load_failure:
        failures.append(load_failure)
    if payload.get("schema_version") != "1.0":
        failures.append("schema_version must be 1.0.")
    if payload.get("report_type") != "freyja6-acceptance-status":
        failures.append("report_type must be freyja6-acceptance-status.")
    if payload.get("status") != "complete":
        failures.append("status must be complete.")
    if payload.get("complete") is not True:
        failures.append("complete must be true.")
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp:
        failures.append("timestamp must be a non-empty ISO timestamp.")
    else:
        parsed_timestamp = _parse_iso_timestamp(timestamp)
        if parsed_timestamp is None:
            failures.append("timestamp must be an ISO timestamp with timezone.")
        elif parsed_timestamp > datetime.now(timezone.utc):
            failures.append("timestamp must not be in the future.")
    remaining_acceptance = payload.get("remaining_acceptance")
    if not isinstance(remaining_acceptance, list):
        failures.append("remaining_acceptance must be a list.")
    elif remaining_acceptance:
        failures.append("remaining_acceptance must be empty.")
    if payload.get("secrets_detected") is not False:
        failures.append("secrets_detected must be false.")
    evidence = payload.get("evidence")
    if not isinstance(evidence, str) or not evidence:
        failures.append("evidence must be a non-empty string.")
    elif Path(evidence).name != "freyja6-live-evidence.json":
        failures.append("evidence must reference freyja6-live-evidence.json.")
    evidence_contract = payload.get("evidence_contract")
    if not isinstance(evidence_contract, dict):
        failures.append("evidence_contract must be an object.")
    elif evidence_contract.get("status") != "pass":
        failures.append("evidence_contract status must be pass.")
    acceptance = payload.get("acceptance")
    if not isinstance(acceptance, list):
        failures.append("acceptance must be a list.")
    else:
        failures.extend(_acceptance_item_failures(acceptance))
    return failures


def _acceptance_item_failures(acceptance: list[Any]) -> list[str]:
    failures: list[str] = []
    required = set(REQUIRED_ACCEPTANCE_IDS)
    seen: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    malformed_count = 0
    unexpected_ids: set[str] = set()
    for item in acceptance:
        if not isinstance(item, dict) or not item.get("id"):
            malformed_count += 1
            continue
        item_id = str(item.get("id"))
        if item_id in seen:
            duplicate_ids.add(item_id)
        else:
            seen[item_id] = item
        if item_id not in required:
            unexpected_ids.add(item_id)
    if malformed_count:
        failures.append("acceptance entries must be objects with ids.")
    for item_id in sorted(unexpected_ids):
        failures.append(f"acceptance contains unexpected id {item_id}.")
    for item_id in sorted(duplicate_ids):
        failures.append(f"acceptance contains duplicate id {item_id}.")
    for item_id in REQUIRED_ACCEPTANCE_IDS:
        item = seen.get(item_id)
        if item is None:
            failures.append(f"acceptance must include {item_id}.")
        elif item.get("status") != "complete":
            failures.append(f"acceptance {item_id} status must be complete.")
        else:
            failures.extend(_complete_acceptance_detail_failures(item_id, item))
    return failures


def _complete_acceptance_detail_failures(item_id: str, item: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for field in ("missing_evidence", "missing_metadata", "semantic_failures"):
        value = item.get(field)
        if not isinstance(value, list):
            failures.append(f"acceptance {item_id} {field} must be a list.")
        elif value:
            failures.append(f"acceptance {item_id} {field} must be empty.")
    required_evidence = item.get("required_evidence")
    present_evidence = item.get("present_evidence")
    required_metadata = item.get("required_metadata")
    expected_evidence = REQUIRED_ACCEPTANCE_EVIDENCE_FIELDS[item_id]
    if not isinstance(required_evidence, list) or not required_evidence:
        failures.append(f"acceptance {item_id} required_evidence must be a non-empty list.")
    elif list(map(str, required_evidence)) != expected_evidence:
        failures.append(f"acceptance {item_id} required_evidence must match the Freyja 6 acceptance contract.")
    if not isinstance(present_evidence, list):
        failures.append(f"acceptance {item_id} present_evidence must be a list.")
    elif set(map(str, present_evidence)) != set(expected_evidence):
        failures.append(f"acceptance {item_id} present_evidence must match required_evidence.")
    if not isinstance(required_metadata, list):
        failures.append(f"acceptance {item_id} required_metadata must be a list.")
    elif list(map(str, required_metadata)) != REQUIRED_ACCEPTANCE_METADATA:
        failures.append(f"acceptance {item_id} required_metadata must match the Freyja 6 acceptance contract.")
    failures.extend(_complete_acceptance_metadata_failures(item_id, item))
    return failures


def _complete_acceptance_metadata_failures(item_id: str, item: dict[str, Any]) -> list[str]:
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        return [f"acceptance {item_id} metadata must be an object."]
    failures: list[str] = []
    metadata_keys = set(metadata)
    expected_keys = set(REQUIRED_ACCEPTANCE_METADATA)
    if metadata_keys != expected_keys:
        failures.append(f"acceptance {item_id} metadata must contain captured_at and source.")
    captured_at = metadata.get("captured_at")
    if not isinstance(captured_at, str) or not captured_at:
        failures.append(f"acceptance {item_id} metadata captured_at must be a non-empty ISO timestamp.")
    else:
        parsed = _parse_iso_timestamp(captured_at)
        if parsed is None:
            failures.append(f"acceptance {item_id} metadata captured_at must be an ISO timestamp with timezone.")
        elif parsed > datetime.now(timezone.utc):
            failures.append(f"acceptance {item_id} metadata captured_at must not be in the future.")
    expected_source = EXPECTED_ACCEPTANCE_SOURCES[item_id]
    if metadata.get("source") != expected_source:
        failures.append(f"acceptance {item_id} metadata source must be {expected_source}.")
    return failures


def _check_repeated_live_bundles(paths: list[Path], *, min_successful_runs: int, expected_evidence: str = "") -> dict[str, Any]:
    complete_reports: list[str] = []
    successful_run_ids: list[str] = []
    successful_instants: list[str] = []
    successful_dates: list[str] = []
    rejected: list[dict[str, Any]] = []
    for path in paths:
        payload = _load_json(path)
        load_failure = payload.get("_load_failure") if isinstance(payload, dict) else None
        if isinstance(load_failure, str) and load_failure:
            rejected.append({"report": _redact_path(path), "reason": load_failure})
            continue
        if not payload:
            rejected.append({"report": _redact_path(path), "reason": "missing_or_unreadable"})
            continue
        if payload.get("report_type") != "freyja6-live-validation-bundle":
            rejected.append({"report": _redact_path(path), "reason": "not_live_validation_bundle"})
            continue
        if payload.get("schema_version") != "1.0":
            rejected.append({"report": _redact_path(path), "reason": "invalid_schema_version"})
            continue
        if payload.get("live") is not True:
            rejected.append({"report": _redact_path(path), "reason": "not_live"})
            continue
        if payload.get("complete") is not True:
            rejected.append({"report": _redact_path(path), "reason": "incomplete"})
            continue
        if payload.get("status") != "complete":
            rejected.append({"report": _redact_path(path), "reason": "status_not_complete"})
            continue
        failed_required = payload.get("failed_required")
        skipped_required = payload.get("skipped_required")
        if not isinstance(failed_required, list) or not isinstance(skipped_required, list):
            rejected.append({"report": _redact_path(path), "reason": "invalid_required_summary"})
            continue
        if failed_required or skipped_required:
            rejected.append({"report": _redact_path(path), "reason": "failed_or_skipped_required"})
            continue
        nested_failure = _bundle_nested_required_failure(payload, bundle_path=path)
        if nested_failure:
            rejected.append({"report": _redact_path(path), "reason": nested_failure})
            continue
        provenance_failure = _bundle_provenance_failure(payload)
        if provenance_failure:
            rejected.append({"report": _redact_path(path), "reason": provenance_failure})
            continue
        evidence_reference = str(payload.get("evidence") or "")
        if expected_evidence and not evidence_reference:
            rejected.append({"report": _redact_path(path), "reason": "missing_evidence_reference"})
            continue
        if expected_evidence and _normalize_report_reference(evidence_reference) != _normalize_report_reference(expected_evidence):
            rejected.append({"report": _redact_path(path), "reason": "evidence_reference_mismatch"})
            continue
        run_id = str(payload.get("run_id") or "")
        if not run_id:
            rejected.append({"report": _redact_path(path), "reason": "missing_run_id"})
            continue
        if not _valid_run_id(run_id):
            rejected.append({"report": _redact_path(path), "reason": "invalid_run_id"})
            continue
        if run_id in successful_run_ids:
            rejected.append({"report": _redact_path(path), "reason": "duplicate_run_id"})
            continue
        timestamp = str(payload.get("timestamp") or "")
        if not timestamp:
            rejected.append({"report": _redact_path(path), "reason": "missing_timestamp"})
            continue
        parsed_timestamp = _parse_iso_timestamp(timestamp)
        if parsed_timestamp is None:
            rejected.append({"report": _redact_path(path), "reason": "invalid_timestamp"})
            continue
        if parsed_timestamp > datetime.now(timezone.utc):
            rejected.append({"report": _redact_path(path), "reason": "future_timestamp"})
            continue
        timestamp_instant = parsed_timestamp.astimezone(timezone.utc).isoformat()
        if timestamp_instant in successful_instants:
            rejected.append({"report": _redact_path(path), "reason": "duplicate_timestamp"})
            continue
        side_report_failure = _bundle_side_report_failure(path, payload, bundle_timestamp=parsed_timestamp, expected_evidence=expected_evidence)
        if side_report_failure:
            rejected.append({"report": _redact_path(path), "reason": side_report_failure})
            continue
        successful_run_ids.append(run_id)
        successful_instants.append(timestamp_instant)
        successful_dates.append(parsed_timestamp.astimezone(timezone.utc).date().isoformat())
        complete_reports.append(_redact_path(path))
    distinct_dates = sorted(set(successful_dates))
    if rejected or len(complete_reports) < min_successful_runs or len(distinct_dates) < min_successful_runs:
        return {
            "id": "repeated_live_bundles",
            "status": "fail",
            "message": "Migration requires repeated complete live validation bundle runs on distinct dates with no rejected reports.",
            "required": min_successful_runs,
            "complete_count": len(complete_reports),
            "complete_reports": complete_reports,
            "rejected_reports": rejected[:10],
            "unique_successful_timestamps": len(set(successful_instants)),
            "unique_successful_run_ids": len(set(successful_run_ids)),
            "distinct_successful_dates": distinct_dates,
        }
    return {
        "id": "repeated_live_bundles",
        "status": "pass",
        "message": "Repeated complete live validation bundle runs are present on distinct dates.",
        "required": min_successful_runs,
        "complete_count": len(complete_reports),
        "complete_reports": complete_reports,
        "unique_successful_timestamps": len(set(successful_instants)),
        "unique_successful_run_ids": len(set(successful_run_ids)),
        "distinct_successful_dates": distinct_dates,
    }


def _bundle_nested_required_failure(payload: dict[str, Any], *, bundle_path: Path) -> str:
    results = payload.get("results")
    if results is None:
        return "missing_results"
    if not isinstance(results, list):
        return "invalid_results"
    result_counts: dict[str, int] = {}
    result_by_id: dict[str, dict[str, Any]] = {}
    malformed_ids = 0
    unexpected_steps: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            return "invalid_results"
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            malformed_ids += 1
            continue
        if not isinstance(item.get("required"), bool) or not isinstance(item.get("status"), str):
            return "malformed_live_step"
        if item_id not in REQUIRED_LIVE_BUNDLE_STEPS:
            unexpected_steps.add(item_id)
        result_counts[item_id] = result_counts.get(item_id, 0) + 1
        if item_id and item_id not in result_by_id:
            result_by_id[item_id] = item
        if item.get("required") is True and item.get("status") in {"fail", "skip"}:
            return "nested_required_not_complete"
        if item.get("required") is True and item.get("status") != "pass":
            return "nested_required_status_unknown"
        if item.get("required") is True and item.get("status") == "pass" and item.get("exit_code") != 0:
            return "required_live_step_pass_without_zero_exit"
        if item.get("required") is True and item.get("status") == "pass" and _live_step_has_failure_markers(item):
            return "required_live_step_pass_with_failure_markers"
        if item.get("required") is True and _live_step_command_failure(item, item_id):
            return _live_step_command_failure(item, item_id)
    if malformed_ids:
        return "malformed_live_step"
    if unexpected_steps:
        return "unexpected_live_step"
    duplicate_required_steps = [step for step in REQUIRED_LIVE_BUNDLE_STEPS if result_counts.get(step, 0) > 1]
    if duplicate_required_steps:
        return "duplicate_required_live_steps"
    reportless_steps = [
        step
        for step in REQUIRED_LIVE_BUNDLE_REPORT_STEPS
        if _live_step_report_failure(result_by_id.get(step, {}), step, bundle_path=bundle_path)
    ]
    if reportless_steps:
        return "required_live_step_missing_report"
    mismatched_report_steps = [
        step
        for step in REQUIRED_LIVE_BUNDLE_REPORT_STEPS
        if _live_step_report_bundle_mismatch(result_by_id.get(step, {}), bundle_path=bundle_path)
    ]
    if mismatched_report_steps:
        return "required_live_step_report_bundle_mismatch"
    missing_steps = [step for step in REQUIRED_LIVE_BUNDLE_STEPS if step not in result_by_id]
    if missing_steps:
        return "missing_required_live_steps"
    non_required_steps = [step for step in REQUIRED_LIVE_BUNDLE_STEPS if result_by_id[step].get("required") is not True]
    if non_required_steps:
        return "required_live_step_not_marked_required"
    incomplete_steps = [step for step in REQUIRED_LIVE_BUNDLE_STEPS if result_by_id[step].get("status") != "pass"]
    if incomplete_steps:
        return "required_live_step_not_passed"
    return ""


def _live_step_command_failure(item: dict[str, Any], step_id: str) -> str:
    command = item.get("command")
    if not isinstance(command, list) or not command or any(not isinstance(part, str) or not part for part in command):
        return "required_live_step_missing_command"
    if command[0] not in ALLOWED_LIVE_BUNDLE_PYTHON_LAUNCHERS:
        return "required_live_step_command_launcher_mismatch"
    expected_script = REQUIRED_LIVE_BUNDLE_COMMAND_SCRIPTS.get(step_id)
    if expected_script and expected_script not in command:
        return "required_live_step_command_mismatch"
    return ""


def _live_step_has_failure_markers(item: dict[str, Any]) -> bool:
    if item.get("payload_missing") is True or item.get("payload_failure") is True:
        return True
    if item.get("report_type_failure") or item.get("contract_failure"):
        return True
    failures = item.get("failures")
    return isinstance(failures, list) and bool(failures)


def _live_step_report_failure(item: dict[str, Any], step_id: str, *, bundle_path: Path) -> bool:
    report = item.get("report")
    if not isinstance(report, str) or not report:
        return True
    report_path = Path(report)
    if report_path.is_absolute() or ".." in report_path.parts:
        return True
    if report_path.parent not in {Path("."), Path("certification/reports")}:
        return True
    expected_suffix = LIVE_BUNDLE_REPORT_SUFFIXES.get(step_id)
    return bool(expected_suffix) and not report_path.name.endswith(f"-{expected_suffix}.json")


def _live_step_report_bundle_mismatch(item: dict[str, Any], *, bundle_path: Path) -> bool:
    report = item.get("report")
    if not isinstance(report, str) or not report:
        return False
    return not Path(report).name.startswith(f"{bundle_path.stem}-")


def _bundle_side_report_failure(
    bundle_path: Path,
    payload: dict[str, Any],
    *,
    bundle_timestamp: datetime,
    expected_evidence: str = "",
) -> str:
    results = payload.get("results")
    if not isinstance(results, list):
        return ""
    for item in results:
        if not isinstance(item, dict):
            continue
        step_id = item.get("id")
        if step_id not in REQUIRED_LIVE_BUNDLE_REPORT_STEPS:
            continue
        report = item.get("report")
        if not isinstance(report, str) or not report:
            return "missing_step_report_artifact"
        report_path = _resolve_side_report(bundle_path, report)
        if report_path.is_symlink():
            return "step_report_symlink"
        if report_path.exists() and not report_path.is_file():
            return "step_report_not_regular"
        report_payload = _load_json(report_path)
        if not report_payload:
            return "missing_step_report_artifact"
        expected_report_type = f"freyja6-{str(step_id).replace('_', '-')}"
        if report_payload.get("report_type") != expected_report_type:
            return "step_report_type_mismatch"
        if report_payload.get("schema_version") != "1.0":
            return "step_report_invalid_schema_version"
        if expected_evidence and "evidence" in report_payload and _normalize_report_reference(str(report_payload.get("evidence") or "")) != _normalize_report_reference(expected_evidence):
            return "step_report_evidence_mismatch"
        if _side_report_indicates_failure(report_payload):
            return "step_report_indicates_failure"
        contract_failure = _side_report_contract_failure(step_id, report_payload)
        if contract_failure:
            return contract_failure
        timestamp_failure = _side_report_timestamp_failure(report_payload, bundle_timestamp, item)
        if timestamp_failure:
            return timestamp_failure
    return ""


def _side_report_contract_failure(step_id: str, payload: dict[str, Any]) -> str:
    if step_id == "acceptance_status" and _acceptance_status_contract_failures(payload):
        return "acceptance_status_side_report_contract_failure"
    return ""


def _side_report_timestamp_failure(payload: dict[str, Any], bundle_timestamp: datetime, step_result: dict[str, Any]) -> str:
    timestamp = payload.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp:
        return "step_report_missing_timestamp"
    parsed_timestamp = _parse_iso_timestamp(timestamp)
    if parsed_timestamp is None:
        return "step_report_invalid_timestamp"
    report_instant = parsed_timestamp.astimezone(timezone.utc)
    bundle_instant = bundle_timestamp.astimezone(timezone.utc)
    if report_instant > bundle_instant:
        return "step_report_future_timestamp"
    if report_instant.date() != bundle_instant.date():
        return "step_report_stale_timestamp"
    step_started_at = _parse_step_result_timestamp(step_result.get("started_at"))
    step_finished_at = _parse_step_result_timestamp(step_result.get("finished_at"))
    if step_started_at is None or step_finished_at is None:
        return "step_result_missing_timestamps"
    if step_finished_at < step_started_at:
        return "step_result_invalid_timestamp_order"
    if report_instant < step_started_at.astimezone(timezone.utc) or report_instant > step_finished_at.astimezone(timezone.utc):
        return "step_report_outside_step_window"
    return ""


def _parse_step_result_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    return _parse_iso_timestamp(value)


def _side_report_indicates_failure(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").lower()
    if status in {"fail", "failed", "error", "incomplete", "not_ready", "blocked"}:
        return True
    for field in ("ok", "complete", "ready"):
        if payload.get(field) is False:
            return True
    for field in ("failures", "blockers", "contract_failures", "semantic_failures", "missing", "rejected_reports"):
        value = payload.get(field)
        if isinstance(value, list) and value:
            return True
    return False


def _resolve_side_report(bundle_path: Path, report: str) -> Path:
    report_path = Path(report)
    if report_path.is_absolute():
        return report_path
    if report_path.parent == Path("certification/reports"):
        return _resolve(report_path)
    return _resolve(bundle_path).parent / report_path.name


def _bundle_provenance_failure(payload: dict[str, Any]) -> str:
    env_file = payload.get("env_file")
    if not isinstance(env_file, str) or not env_file:
        return "missing_env_file"
    if Path(env_file).name == ".env.example":
        return "example_env_file"
    if Path(env_file).name != ".env":
        return "invalid_env_file"
    env_path = _resolve(Path(env_file))
    if env_path.is_symlink():
        return "env_file_symlink"
    if env_path.exists() and not env_path.is_file():
        return "env_file_not_regular"
    log_root = payload.get("log_root")
    if not isinstance(log_root, str) or not log_root:
        return "missing_log_root"
    if log_root not in {"logs", "freyja6/logs"}:
        return "invalid_log_root"
    return ""


def _acceptance_evidence_reference(path: Path) -> str:
    payload = _load_json(path)
    if not payload:
        return ""
    return str(payload.get("evidence") or "")


def _normalize_report_reference(value: str) -> str:
    if not value:
        return ""
    path = Path(value)
    resolved = path if path.is_absolute() else REPO_ROOT / path
    try:
        return str(resolved.resolve())
    except OSError:
        return str(resolved)


def _next_actions(blockers: list[dict[str, Any]], ready: bool) -> list[str]:
    if ready:
        return ["Start migration with Freyja only, one capability or channel at a time, keeping rollback systems online."]
    if blockers:
        return [str(blockers[0]["message"])]
    return ["Continue live validation."]


def _load_json(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    if resolved.is_symlink():
        return {"_load_failure": "input_report_symlink"}
    if resolved.exists() and not resolved.is_file():
        return {"_load_failure": "input_report_not_regular"}
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _glob_bundle_reports(pattern: str) -> list[Path]:
    if Path(pattern).is_absolute():
        return [Path(item) for item in sorted(glob.glob(pattern))]
    return sorted(_resolve(Path(".")).glob(pattern))


def _parse_iso_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _valid_run_id(value: str) -> bool:
    prefix = "freyja6-live-"
    if not value.startswith(prefix):
        return False
    try:
        uuid.UUID(value.removeprefix(prefix))
    except ValueError:
        return False
    return True


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _same_resolved_path(left: Path, right: Path) -> bool:
    try:
        return _resolve(left).resolve() == _resolve(right).resolve()
    except OSError:
        return _resolve(left) == _resolve(right)


def _path_matches_glob(path: Path, pattern: str) -> bool:
    resolved_path = _resolve(path)
    resolved_pattern = pattern if Path(pattern).is_absolute() else str(REPO_ROOT / pattern)
    return fnmatch.fnmatch(str(resolved_path), resolved_pattern)


def _redact_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return path.name


def _failed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "fail", "message": message}


def _output_path_failure(output: Path) -> str | None:
    if output.is_symlink():
        return f"output path must not be a symlink: {output.name}"
    if output.exists() and not output.is_file():
        return f"output path must be a regular file: {output.name}"
    return None


def _error_report(error: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-migration-readiness",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ready": False,
        "status": "not_ready",
        "error": error,
        **extra,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_failure = _output_path_failure(args.output)
    if output_failure:
        report = _error_report(output_failure)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2
    bundle_reports = args.bundle_report or _glob_bundle_reports(args.bundle_glob)
    input_reports = [args.acceptance_status, args.preservation_report, *bundle_reports]
    conflicting_inputs = [_redact_path(path) for path in input_reports if _same_resolved_path(args.output, path)]
    if not args.bundle_report and _path_matches_glob(args.output, args.bundle_glob):
        conflicting_inputs.append(_redact_path(args.output))
    conflicting_inputs = list(dict.fromkeys(conflicting_inputs))
    if conflicting_inputs:
        report = _error_report(
            "output path must not overwrite input evidence reports",
            conflicting_inputs=conflicting_inputs,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2
    report = build_report(
        acceptance_status=args.acceptance_status,
        preservation_report=args.preservation_report,
        bundle_reports=bundle_reports,
        bundle_glob=args.bundle_glob,
        min_successful_runs=args.min_successful_runs,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
