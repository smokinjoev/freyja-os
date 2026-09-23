#!/usr/bin/env python3
"""Validate Freyja 6 schedules and write redacted scheduler smoke logs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_SCHEDULES = Path("config/freyja6/schedules.yaml")
DEFAULT_LOG_ROOT = Path(os.environ.get("FREYJA6_LOG_ROOT", "/srv/freyja6/logs"))
DEFAULT_OUTPUT = Path("certification/reports/freyja6-schedule-smoke.json")
EXPECTED_SCHEDULE_IDS = ["freyja-test-health-heartbeat", "freyja-test-daily-tool-smoke"]
FORBIDDEN_MUTATING_TERMS = (
    "calendar.create_event",
    "calendar.delete",
    "calendar.write",
    "create calendar",
    "modify files",
    "write files",
    "control home assistant",
    "home_assistant.control",
    "start migration",
    "migrate",
)
REQUIRED_DAILY_GUARDS = (
    "read-only",
    "Do not create calendar",
    "modify files",
    "control Home Assistant",
    "start migration",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Freyja 6 schedule config and log writability.")
    parser.add_argument("--schedules", type=Path, default=DEFAULT_SCHEDULES)
    parser.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--write-logs", action="store_true", help="Append one redacted JSONL smoke entry per enabled schedule.")
    return parser


def run_smoke(*, schedules_path: Path, log_root: Path, write_logs: bool = False) -> dict[str, Any]:
    payload = _load_yaml(_resolve(schedules_path))
    schedules = payload.get("schedules") if isinstance(payload.get("schedules"), list) else []
    checks = [
        _check_agent_scope(payload),
        _check_schedule_ids(schedules),
        _check_schedule_cron(schedules),
        _check_schedule_guardrails(schedules),
        _check_log_targets(schedules),
    ]
    pre_write_failures = [check for check in checks if check["status"] == "fail"]
    log_preflight_failures = _log_preflight_failures(schedules, log_root=log_root) if write_logs and not pre_write_failures else []
    writes = _write_schedule_logs(schedules, log_root=log_root) if write_logs and not pre_write_failures and not log_preflight_failures else []
    if write_logs:
        checks.append(_check_log_writes(writes, log_root=log_root, pre_write_failures=pre_write_failures, log_preflight_failures=log_preflight_failures))
    else:
        checks.append({"id": "log_writes", "status": "skip", "message": "Run with --write-logs to append scheduler smoke entries."})
    failures = [check for check in checks if check["status"] == "fail"]
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-schedule-smoke",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": not failures,
        "schedules_path": str(schedules_path),
        "log_root_redacted": _redact_log_root(log_root),
        "checks": checks,
        "writes": writes,
        "failures": failures,
    }


def _check_agent_scope(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("agent_id") != "freyja-test":
        return _failed("agent_scope", "Schedules must be scoped to freyja-test.")
    if payload.get("phase") != "validation":
        return _failed("agent_scope", "Schedules must remain in validation phase.")
    return _passed("agent_scope", "Schedules are scoped to freyja-test validation.")


def _check_schedule_ids(schedules: list[Any]) -> dict[str, Any]:
    ids = [item.get("id") for item in schedules if isinstance(item, dict)]
    if ids != EXPECTED_SCHEDULE_IDS:
        return {"id": "schedule_ids", "status": "fail", "message": "Unexpected Freyja 6 schedule IDs.", "ids": ids}
    return _passed("schedule_ids", "Only the two freyja-test validation schedules are enabled.")


def _check_schedule_cron(schedules: list[Any]) -> dict[str, Any]:
    invalid = []
    for item in schedules:
        if not isinstance(item, dict):
            invalid.append({"id": "", "reason": "schedule item is not an object"})
            continue
        cron = str(item.get("cron") or "")
        if item.get("kind") != "cron" or len(cron.split()) != 5:
            invalid.append({"id": item.get("id", ""), "cron": cron})
    if invalid:
        return {"id": "cron_shape", "status": "fail", "message": "One or more schedules do not use 5-field cron.", "invalid": invalid}
    return _passed("cron_shape", "Enabled schedules use 5-field cron expressions.")


def _check_schedule_guardrails(schedules: list[Any]) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    for item in schedules:
        if not isinstance(item, dict):
            continue
        schedule_id = str(item.get("id") or "")
        text = f"{item.get('purpose', '')} {item.get('prompt', '')}"
        lowered = text.lower()
        for term in FORBIDDEN_MUTATING_TERMS:
            if term.lower() in lowered and not _is_negated_guard(lowered, term):
                failures.append({"id": schedule_id, "reason": "mutating_instruction", "term": term})
        if schedule_id == "freyja-test-daily-tool-smoke":
            prompt = str(item.get("prompt") or "")
            for term in REQUIRED_DAILY_GUARDS:
                if term not in prompt:
                    failures.append({"id": schedule_id, "reason": "missing_read_only_guard", "term": term})
    if failures:
        return {
            "id": "schedule_guardrails",
            "status": "fail",
            "message": "Schedules must remain read-only validation jobs.",
            "failures": failures,
        }
    return _passed("schedule_guardrails", "Schedule prompts are constrained to non-mutating validation.")


def _is_negated_guard(lowered_text: str, term: str) -> bool:
    lowered_term = term.lower()
    index = lowered_text.find(lowered_term)
    if index == -1:
        return False
    guard_index = lowered_text.rfind("do not ", 0, index + len(lowered_term))
    if guard_index == -1:
        return False
    clause = lowered_text[guard_index:index]
    return "." not in clause and ";" not in clause


def _check_log_targets(schedules: list[Any]) -> dict[str, Any]:
    missing = []
    for item in schedules:
        if not isinstance(item, dict):
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        if not str(evidence.get("log") or "").startswith("/var/log/freyja6/"):
            missing.append(str(item.get("id") or ""))
    if missing:
        return {"id": "log_targets", "status": "fail", "message": "Schedules must write under /var/log/freyja6.", "missing": missing}
    return _passed("log_targets", "Schedule evidence logs target /var/log/freyja6.")


def _write_schedule_logs(schedules: list[Any], *, log_root: Path) -> list[dict[str, Any]]:
    results = []
    log_root.mkdir(parents=True, exist_ok=True)
    for item in schedules:
        if not isinstance(item, dict) or item.get("enabled") is not True:
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        log_name = Path(str(evidence.get("log") or "")).name
        if not log_name:
            results.append({"ok": False, "schedule_id": item.get("id", ""), "error": "missing log target"})
            continue
        path = log_root / log_name
        trace_id = f"freyja6-schedule-{uuid.uuid4().hex[:12]}"
        entry = _schedule_log_entry(log_name=log_name, schedule_id=str(item.get("id") or ""), trace_id=trace_id)
        try:
            if path.is_symlink():
                raise OSError(f"Log file must not be a symlink: {path.name}.")
            if path.exists() and not path.is_file():
                raise OSError(f"Log file must be a regular file: {path.name}.")
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
            results.append({"ok": True, "schedule_id": item.get("id"), "log": _redact_log_path(path), "trace_id": entry["trace_id"]})
        except OSError as exc:
            results.append({"ok": False, "schedule_id": item.get("id"), "log": _redact_log_path(path), "error": str(exc)})
    return results


def _log_preflight_failures(schedules: list[Any], *, log_root: Path) -> list[dict[str, str]]:
    failures = []
    for item in schedules:
        if not isinstance(item, dict) or item.get("enabled") is not True:
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        log_name = Path(str(evidence.get("log") or "")).name
        if not log_name:
            continue
        path = log_root / log_name
        if path.is_symlink():
            failures.append({"schedule_id": str(item.get("id") or ""), "log": _redact_log_path(path), "error": f"Log file must not be a symlink: {path.name}."})
        elif path.exists() and not path.is_file():
            failures.append({"schedule_id": str(item.get("id") or ""), "log": _redact_log_path(path), "error": f"Log file must be a regular file: {path.name}."})
    return failures


def _schedule_log_entry(*, log_name: str, schedule_id: str, trace_id: str) -> dict[str, Any]:
    base = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "schedule_id": schedule_id,
        "trace_id": trace_id,
        "status": "ok",
        "source": "freyja6-schedule-smoke",
    }
    if log_name == "freyja-test-acceptance.jsonl":
        return {
            **base,
            "event": "acceptance",
            "acceptance_id": "scheduled_validation",
        }
    return {
        **base,
        "event": "tool_call",
        "tool": "status.check",
        "status_code": 200,
    }


def _check_log_writes(
    writes: list[dict[str, Any]],
    *,
    log_root: Path | None = None,
    pre_write_failures: list[dict[str, Any]] | None = None,
    log_preflight_failures: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    if pre_write_failures:
        return {
            "id": "log_writes",
            "status": "fail",
            "message": "Schedule smoke log writes were not attempted because schedule validation failed.",
            "blocked_by": [item["id"] for item in pre_write_failures],
        }
    if log_preflight_failures:
        return {
            "id": "log_writes",
            "status": "fail",
            "message": "One or more schedule smoke log targets are unsafe.",
            "failed": log_preflight_failures,
        }
    if not writes:
        return _failed("log_writes", "No schedule log writes were attempted.")
    failed = [item for item in writes if not item.get("ok")]
    if failed:
        return {"id": "log_writes", "status": "fail", "message": "One or more schedule smoke log writes failed.", "failed": failed}
    expected = {
        "freyja-test-health-heartbeat": "freyja6/logs/freyja-test-acceptance.jsonl",
        "freyja-test-daily-tool-smoke": "freyja6/logs/freyja-test-tools.jsonl",
    }
    actual = {
        str(item.get("schedule_id") or ""): str(item.get("log") or "")
        for item in writes
        if isinstance(item, dict)
    }
    if actual != expected:
        return {
            "id": "log_writes",
            "status": "fail",
            "message": "Schedule smoke must write exactly the expected redacted logs.",
            "expected": expected,
            "actual": actual,
        }
    if log_root is not None:
        content_failures = _log_write_content_failures(writes, log_root=log_root)
        if content_failures:
            return {
                "id": "log_writes",
                "status": "fail",
                "message": "Schedule smoke wrote malformed log entries.",
                "failures": content_failures,
            }
    return _passed("log_writes", "Schedule smoke entries were written to redacted logs.")


def _log_write_content_failures(writes: list[dict[str, Any]], *, log_root: Path) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    for item in writes:
        schedule_id = str(item.get("schedule_id") or "")
        log = str(item.get("log") or "")
        trace_id = str(item.get("trace_id") or "")
        path = log_root / Path(log).name
        entry = _last_jsonl_entry(path)
        if not entry:
            failures.append({"schedule_id": schedule_id, "reason": "missing_or_unreadable_entry"})
            continue
        if str(entry.get("trace_id") or "") != trace_id:
            failures.append({"schedule_id": schedule_id, "reason": "trace_id_mismatch"})
        if entry.get("source") != "freyja6-schedule-smoke" or entry.get("status") != "ok":
            failures.append({"schedule_id": schedule_id, "reason": "invalid_source_or_status"})
        if schedule_id == "freyja-test-health-heartbeat":
            if entry.get("event") != "acceptance" or entry.get("acceptance_id") != "scheduled_validation":
                failures.append({"schedule_id": schedule_id, "reason": "invalid_acceptance_entry"})
        elif schedule_id == "freyja-test-daily-tool-smoke":
            if entry.get("event") != "tool_call" or entry.get("tool") != "status.check":
                failures.append({"schedule_id": schedule_id, "reason": "invalid_tool_entry"})
        else:
            failures.append({"schedule_id": schedule_id, "reason": "unexpected_schedule_id"})
    return failures


def _last_jsonl_entry(path: Path) -> dict[str, Any]:
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return {}
    if not lines:
        return {}
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _redact_log_root(path: Path) -> str:
    if str(path).startswith("/srv/freyja6/logs"):
        return "freyja6/logs"
    return path.name


def _redact_log_path(path: Path) -> str:
    return f"freyja6/logs/{path.name}"


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


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
        "report_type": "freyja6-schedule-smoke",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "status": "fail",
        "error": error,
        "writes": [],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_failure = _output_path_failure(args.output)
    report = (
        _error_report(output_failure)
        if output_failure
        else run_smoke(schedules_path=args.schedules, log_root=args.log_root, write_logs=args.write_logs)
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
