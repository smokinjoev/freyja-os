#!/usr/bin/env python3
"""Audit Freyja 6 logs for useful redacted JSONL evidence."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_LOG_ROOT = Path(os.environ.get("FREYJA6_LOG_ROOT", "/srv/freyja6/logs"))
DEFAULT_OUTPUT = Path("certification/reports/freyja6-log-audit.json")
SECRET_MARKERS = ("api_key", "apikey", "authorization", "bearer ", "password", "secret", "token")
EXPECTED_LOGS = {
    "tool": "freyja-test-tools.jsonl",
    "model": "freyja-test-model-calls.jsonl",
    "acceptance": "freyja-test-acceptance.jsonl",
}
REQUIRED_ENTRY_FIELDS = {
    "tool": ("timestamp", "event", "trace_id", "tool", "status", "source"),
    "model": ("timestamp", "event", "trace_id", "model", "status", "source"),
    "acceptance": ("timestamp", "event", "trace_id", "acceptance_id", "status", "source"),
}
EXPECTED_EVENTS = {
    "tool": "tool_call",
    "model": "model_call",
    "acceptance": "acceptance",
}
ALLOWED_STATUSES = {
    "tool": {"ok", "failed"},
    "model": {"ok", "failed"},
    "acceptance": {"ok"},
}
ALLOWED_TOOL_NAMES = {
    "filesystem.read",
    "terminal.safe_command",
    "status.check",
    "calendar.list_events",
    "calendar.create_event",
    "home_assistant.list_states",
    "opencode.status",
}
HTTP_STATUS_TOOL_NAMES = {
    "status.check",
    "calendar.list_events",
    "calendar.create_event",
    "home_assistant.list_states",
    "opencode.status",
}
ALLOWED_MODEL_ALIASES = {"vulcan-fast", "vulcan-general", "vulcan-code"}
ALLOWED_SOURCES_BY_LABEL = {
    "tool": {"freyja6-calendar-write-smoke", "freyja6-log-audit-test", "freyja6-schedule-smoke", "freyja6-tool-smoke"},
    "model": {"freyja6-litellm-smoke", "freyja6-log-audit-test"},
    "acceptance": {
        "freyja6-calendar-write-smoke",
        "freyja6-discord-smoke",
        "freyja6-litellm-smoke",
        "freyja6-log-audit-test",
        "freyja6-restart-evidence",
        "freyja6-schedule-smoke",
        "freyja6-tool-smoke",
    },
}
TOOL_ACCEPTANCE_TO_LOG_NAME = {
    "approved_file_read": "filesystem.read",
    "safe_terminal": "terminal.safe_command",
    "mcp_tool": "status.check",
    "calendar_read": "calendar.list_events",
    "calendar_create_event": "calendar.create_event",
    "home_assistant_query": "home_assistant.list_states",
    "coding_workflow": "opencode.status",
}
ALLOWED_ACCEPTANCE_IDS = {
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
    "scheduled_validation",
}
REQUIRED_LIVE_ACCEPTANCE_IDS = ALLOWED_ACCEPTANCE_IDS - {"scheduled_validation"}
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
    "scheduled_validation": "freyja6-schedule-smoke",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 JSONL logs for redacted useful entries.")
    parser.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-entries", action="store_true", help="Fail if any expected log has zero JSONL entries.")
    return parser


def build_report(*, log_root: Path, require_entries: bool = False) -> dict[str, Any]:
    checks = [_audit_log(log_root / filename, label=label, require_entries=require_entries) for label, filename in EXPECTED_LOGS.items()]
    _apply_cross_log_consistency(checks, log_root)
    failures = [check for check in checks if check["status"] == "fail"]
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-log-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": not failures,
        "status": "pass" if not failures else "fail",
        "log_root_redacted": _redact_log_root(log_root),
        "require_entries": require_entries,
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _apply_cross_log_consistency(checks: list[dict[str, Any]], log_root: Path) -> None:
    acceptance_check = next((check for check in checks if check["id"] == "acceptance_log"), None)
    if not acceptance_check:
        return
    tool_entries = _jsonl_entries(log_root / EXPECTED_LOGS["tool"])
    model_entries = _jsonl_entries(log_root / EXPECTED_LOGS["model"])
    acceptance_entries = _jsonl_entries(log_root / EXPECTED_LOGS["acceptance"])
    failures = [
        *_model_acceptance_trace_failures(model_entries, acceptance_entries),
        *_tool_acceptance_trace_failures(tool_entries, acceptance_entries),
    ]
    if not failures:
        return
    acceptance_check["status"] = "fail"
    acceptance_check["message"] = "acceptance log entries do not match supporting model-call traces."
    acceptance_check.setdefault("semantic_failures", []).extend(failures)
    acceptance_check.setdefault("entry_count", len(_jsonl_entries(log_root / EXPECTED_LOGS["acceptance"])))
    acceptance_check.setdefault("expected_event", EXPECTED_EVENTS["acceptance"])
    acceptance_check.setdefault("allowed_statuses", sorted(ALLOWED_STATUSES["acceptance"]))


def _model_acceptance_trace_failures(model_entries: list[Any], acceptance_entries: list[Any]) -> list[dict[str, Any]]:
    ok_model_entries_by_trace = {
        str(entry.get("trace_id") or ""): entry
        for entry in model_entries
        if isinstance(entry, dict)
        and entry.get("event") == EXPECTED_EVENTS["model"]
        and entry.get("status") == "ok"
        and entry.get("model") in ALLOWED_MODEL_ALIASES
    }
    ok_model_aliases_by_trace = {
        str(entry.get("trace_id") or ""): str(entry.get("model") or "")
        for entry in model_entries
        if isinstance(entry, dict)
        and entry.get("event") == EXPECTED_EVENTS["model"]
        and entry.get("status") == "ok"
        and entry.get("model") in ALLOWED_MODEL_ALIASES
    }
    ok_model_aliases = {alias for alias in ok_model_aliases_by_trace.values() if alias}
    failures: list[dict[str, Any]] = []
    for index, entry in enumerate(acceptance_entries, start=1):
        if not isinstance(entry, dict):
            continue
        acceptance_id = entry.get("acceptance_id")
        if acceptance_id not in {"litellm_to_vulcan", "model_switch"}:
            continue
        trace_id = str(entry.get("trace_id") or "")
        supporting_entry = ok_model_entries_by_trace.get(trace_id)
        if not supporting_entry:
            failures.append({"line": index, "failures": [f"{acceptance_id} trace_id must match an ok model_call log trace."]})
        elif supporting_entry.get("source") != EXPECTED_ACCEPTANCE_SOURCES.get(str(acceptance_id)):
            failures.append(
                {
                    "line": index,
                    "failures": [
                        f"{acceptance_id} supporting model_call source must be {EXPECTED_ACCEPTANCE_SOURCES.get(str(acceptance_id))}."
                    ],
                }
            )
        elif _entry_happened_before(entry, supporting_entry):
            failures.append({"line": index, "failures": [f"{acceptance_id} timestamp must not be before supporting model_call log trace."]})
        if acceptance_id == "model_switch" and len(ok_model_aliases) < 2:
            failures.append({"line": index, "failures": ["model_switch must be supported by at least two distinct ok model_call aliases."]})
    return failures


def _tool_acceptance_trace_failures(tool_entries: list[Any], acceptance_entries: list[Any]) -> list[dict[str, Any]]:
    ok_tool_entries_by_trace = {
        (str(entry.get("trace_id") or ""), str(entry.get("tool") or "")): entry
        for entry in tool_entries
        if isinstance(entry, dict)
        and entry.get("event") == EXPECTED_EVENTS["tool"]
        and entry.get("status") == "ok"
        and entry.get("tool") in ALLOWED_TOOL_NAMES
    }
    failures: list[dict[str, Any]] = []
    for index, entry in enumerate(acceptance_entries, start=1):
        if not isinstance(entry, dict):
            continue
        acceptance_id = str(entry.get("acceptance_id") or "")
        expected_tool = TOOL_ACCEPTANCE_TO_LOG_NAME.get(acceptance_id)
        if not expected_tool:
            continue
        trace_id = str(entry.get("trace_id") or "")
        supporting_entry = ok_tool_entries_by_trace.get((trace_id, expected_tool))
        if not supporting_entry:
            failures.append({"line": index, "failures": [f"{acceptance_id} trace_id must match an ok {expected_tool} tool_call log trace."]})
        elif supporting_entry.get("source") != EXPECTED_ACCEPTANCE_SOURCES.get(acceptance_id):
            failures.append(
                {
                    "line": index,
                    "failures": [
                        f"{acceptance_id} supporting {expected_tool} tool_call source must be {EXPECTED_ACCEPTANCE_SOURCES.get(acceptance_id)}."
                    ],
                }
            )
        elif _entry_happened_before(entry, supporting_entry):
            failures.append({"line": index, "failures": [f"{acceptance_id} timestamp must not be before supporting {expected_tool} tool_call log trace."]})
    return failures


def _entry_happened_before(entry: dict[str, Any], supporting_entry: dict[str, Any]) -> bool:
    entry_timestamp = _parse_timestamp(entry.get("timestamp"))
    supporting_timestamp = _parse_timestamp(supporting_entry.get("timestamp"))
    if not entry_timestamp or not supporting_timestamp:
        return False
    return entry_timestamp < supporting_timestamp


def _jsonl_entries(path: Path) -> list[Any]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[Any] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _audit_log(path: Path, *, label: str, require_entries: bool) -> dict[str, Any]:
    if not path.exists():
        return {
            "id": f"{label}_log",
            "status": "fail",
            "message": f"{label} log is missing.",
            "log": _redact_log_path(path),
        }
    if path.is_symlink() or not path.is_file():
        return {
            "id": f"{label}_log",
            "status": "fail",
            "message": f"{label} log must be a regular file, not a symlink or directory.",
            "log": _redact_log_path(path),
        }
    lines = path.read_text(encoding="utf-8").splitlines()
    entries = []
    invalid_lines = []
    incomplete_entries = []
    semantic_failures = []
    secrets_detected = False
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            invalid_lines.append(index)
            continue
        entries.append(entry)
        if _contains_secret_marker(entry):
            secrets_detected = True
        missing_fields = _missing_required_fields(entry, label)
        if missing_fields:
            incomplete_entries.append({"line": index, "missing": missing_fields})
        else:
            failures = _semantic_failures(entry, label)
            if failures:
                semantic_failures.append({"line": index, "failures": failures})
    if label == "acceptance":
        semantic_failures.extend(_acceptance_trace_reuse_failures(entries))
        if require_entries:
            semantic_failures.extend(_acceptance_coverage_failures(entries))
    if invalid_lines:
        return {
            "id": f"{label}_log",
            "status": "fail",
            "message": f"{label} log contains invalid JSONL entries.",
            "log": _redact_log_path(path),
            "invalid_lines": invalid_lines[:10],
        }
    if secrets_detected:
        return {
            "id": f"{label}_log",
            "status": "fail",
            "message": f"{label} log may contain secret markers.",
            "log": _redact_log_path(path),
            "entry_count": len(entries),
        }
    if require_entries and not entries:
        return {
            "id": f"{label}_log",
            "status": "fail",
            "message": f"{label} log has no entries.",
            "log": _redact_log_path(path),
            "entry_count": 0,
        }
    if entries and incomplete_entries:
        return {
            "id": f"{label}_log",
            "status": "fail",
            "message": f"{label} log entries are missing required usefulness fields.",
            "log": _redact_log_path(path),
            "entry_count": len(entries),
            "incomplete_entries": incomplete_entries[:10],
            "required_fields": list(REQUIRED_ENTRY_FIELDS[label]),
        }
    if entries and semantic_failures:
        return {
            "id": f"{label}_log",
            "status": "fail",
            "message": f"{label} log entries have invalid event or status values.",
            "log": _redact_log_path(path),
            "entry_count": len(entries),
            "semantic_failures": semantic_failures[:10],
            "expected_event": EXPECTED_EVENTS[label],
            "allowed_statuses": sorted(ALLOWED_STATUSES[label]),
        }
    return {
        "id": f"{label}_log",
        "status": "pass",
        "message": f"{label} log is present, parseable, redacted, and structured.",
        "log": _redact_log_path(path),
        "entry_count": len(entries),
    }


def _missing_required_fields(entry: Any, label: str) -> list[str]:
    if not isinstance(entry, dict):
        return list(REQUIRED_ENTRY_FIELDS[label])
    return [field for field in REQUIRED_ENTRY_FIELDS[label] if not _present(entry.get(field))]


def _semantic_failures(entry: dict[str, Any], label: str) -> list[str]:
    failures: list[str] = []
    timestamp_failure = _timestamp_failure(entry.get("timestamp"))
    if timestamp_failure:
        failures.append(timestamp_failure)
    trace_failure = _trace_id_failure(entry.get("trace_id"))
    if trace_failure:
        failures.append(trace_failure)
    source_failure = _source_failure(entry.get("source"), label)
    if source_failure:
        failures.append(source_failure)
    if entry.get("event") != EXPECTED_EVENTS[label]:
        failures.append(f"event must be {EXPECTED_EVENTS[label]}.")
    if entry.get("status") not in ALLOWED_STATUSES[label]:
        failures.append("status must be one of: " + ", ".join(sorted(ALLOWED_STATUSES[label])) + ".")
    if label in {"tool", "model"} and entry.get("status") == "failed" and not _present(entry.get("error_summary")):
        failures.append("failed tool/model log entries must include error_summary.")
    if label == "tool" and entry.get("tool") not in ALLOWED_TOOL_NAMES:
        failures.append("tool must be an approved Freyja 6 tool log name.")
    elif label == "tool" and entry.get("tool") in HTTP_STATUS_TOOL_NAMES and entry.get("status") == "ok":
        status_code = entry.get("status_code")
        if not isinstance(status_code, int):
            failures.append("ok HTTP-backed tool_call status_code must be an integer.")
        elif not 200 <= status_code < 300:
            failures.append("ok HTTP-backed tool_call status_code must be 2xx.")
    elif label == "model":
        if entry.get("model") not in ALLOWED_MODEL_ALIASES:
            failures.append("model must be an approved Freyja 6 Vulcan alias.")
        status_code = entry.get("status_code")
        if not isinstance(status_code, int):
            failures.append("model_call status_code must be an integer.")
        elif entry.get("status") == "ok" and not 200 <= status_code < 300:
            failures.append("ok model_call status_code must be 2xx.")
    elif label == "acceptance":
        acceptance_id = str(entry.get("acceptance_id") or "")
        if acceptance_id not in ALLOWED_ACCEPTANCE_IDS:
            failures.append("acceptance_id must be an approved Freyja 6 acceptance item.")
        else:
            expected_source = EXPECTED_ACCEPTANCE_SOURCES.get(acceptance_id)
            if expected_source and entry.get("source") != expected_source:
                failures.append(f"source must be {expected_source} for {acceptance_id}.")
    return failures


def _acceptance_trace_reuse_failures(entries: list[Any]) -> list[dict[str, Any]]:
    indexed: dict[str, list[tuple[int, str]]] = {}
    trace_by_acceptance_id: dict[str, dict[str, int]] = {}
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue
        acceptance_id = str(entry.get("acceptance_id") or "")
        if acceptance_id not in ALLOWED_ACCEPTANCE_IDS:
            continue
        trace_id = str(entry.get("trace_id") or "")
        indexed.setdefault(acceptance_id, []).append((index, trace_id))
        traces = trace_by_acceptance_id.setdefault(acceptance_id, {})
        if trace_id in traces:
            indexed.setdefault("_duplicate_trace", []).append((index, f"{acceptance_id}:{trace_id}"))
        else:
            traces[trace_id] = index

    failures: list[dict[str, Any]] = []
    for line, duplicate in indexed.get("_duplicate_trace", []):
        acceptance_id, _trace_id = duplicate.split(":", 1)
        failures.append({"line": line, "failures": [f"{acceptance_id} must not reuse the same trace_id across repeated acceptance log entries."]})

    _extend_pair_trace_failures(
        failures,
        indexed,
        first_id="restart_identity_session",
        second_id="remember_fact",
        message="remember_fact trace_id must be distinct from restart_identity_session trace_id.",
    )
    _extend_pair_trace_failures(
        failures,
        indexed,
        first_id="restart_identity_session",
        second_id="atlas_reboot_return",
        message="atlas_reboot_return trace_id must be distinct from restart_identity_session trace_id.",
    )
    _extend_pair_trace_failures(
        failures,
        indexed,
        first_id="discord_reply",
        second_id="atlas_reboot_return",
        message="atlas_reboot_return trace_id must be distinct from discord_reply trace_id.",
    )
    _extend_pair_trace_failures(
        failures,
        indexed,
        first_id="litellm_to_vulcan",
        second_id="model_switch",
        message="model_switch trace_id must be distinct from litellm_to_vulcan trace_id.",
    )
    tool_traces: dict[str, tuple[int, str]] = {}
    for acceptance_id in TOOL_ACCEPTANCE_TO_LOG_NAME:
        for line, trace_id in indexed.get(acceptance_id, []):
            if trace_id in tool_traces:
                other_line, other_id = tool_traces[trace_id]
                failures.append({"line": line, "failures": [f"{acceptance_id} trace_id must be distinct from {other_id} trace_id."]})
                failures.append({"line": other_line, "failures": [f"{other_id} trace_id must be distinct from {acceptance_id} trace_id."]})
            else:
                tool_traces[trace_id] = (line, acceptance_id)
    return failures


def _extend_pair_trace_failures(
    failures: list[dict[str, Any]],
    indexed: dict[str, list[tuple[int, str]]],
    *,
    first_id: str,
    second_id: str,
    message: str,
) -> None:
    first_traces = {trace_id for _line, trace_id in indexed.get(first_id, [])}
    for line, trace_id in indexed.get(second_id, []):
        if trace_id in first_traces:
            failures.append({"line": line, "failures": [message]})


def _acceptance_coverage_failures(entries: list[Any]) -> list[dict[str, Any]]:
    seen = {
        str(entry.get("acceptance_id") or "")
        for entry in entries
        if isinstance(entry, dict) and entry.get("status") == "ok"
    }
    missing = sorted(REQUIRED_LIVE_ACCEPTANCE_IDS - seen)
    if not missing:
        return []
    return [{"line": 0, "failures": ["acceptance log must include all live acceptance ids: " + ", ".join(missing) + "."]}]


def _timestamp_failure(value: Any) -> str:
    if not _present(value):
        return ""
    parsed = _parse_timestamp(value)
    if not parsed:
        return "timestamp must be an ISO timestamp."
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return "timestamp must include a timezone offset."
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc):
        return "timestamp must not be in the future."
    return ""


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _trace_id_failure(value: Any) -> str:
    if not _present(value):
        return ""
    text = str(value).strip()
    if "..." in text:
        return "trace_id must not use placeholder ellipses."
    if not text.startswith("trace-") and not text.startswith("freyja6-"):
        return "trace_id must use a Freyja validation trace prefix."
    return ""


def _source_failure(value: Any, label: str) -> str:
    if not _present(value):
        return ""
    text = str(value).strip()
    allowed_sources = ALLOWED_SOURCES_BY_LABEL[label]
    if text not in allowed_sources:
        return "source must identify an approved Freyja 6 validation helper: " + ", ".join(sorted(allowed_sources)) + "."
    return ""


def _present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _contains_secret_marker(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered_key = str(key).lower()
            if any(marker.strip() in lowered_key for marker in SECRET_MARKERS):
                return True
            if _contains_secret_marker(item):
                return True
        return False
    if isinstance(value, list):
        return any(_contains_secret_marker(item) for item in value)
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in SECRET_MARKERS)
    return False


def _redact_log_root(path: Path) -> str:
    if str(path).startswith("/srv/freyja6/logs"):
        return "freyja6/logs"
    return path.name


def _redact_log_path(path: Path) -> str:
    return f"freyja6/logs/{path.name}"


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Keep collecting redacted Freyja 6 log evidence during live validation."]


def _output_path_failure(output: Path) -> str | None:
    if output.is_symlink():
        return f"output path must not be a symlink: {output.name}"
    if output.exists() and not output.is_file():
        return f"output path must be a regular file: {output.name}"
    return None


def _error_report(error: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-log-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "status": "fail",
        "error": error,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_failure = _output_path_failure(args.output)
    report = _error_report(output_failure) if output_failure else build_report(log_root=args.log_root, require_entries=args.require_entries)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
