#!/usr/bin/env python3
"""Create the Freyja 6 basement-cleanup calendar acceptance event."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_EVIDENCE = Path("certification/reports/freyja6-live-evidence.json")
DEFAULT_LOG_ROOT = Path(os.environ.get("FREYJA6_LOG_ROOT", "/srv/freyja6/logs"))
REQUIRED_APPROVAL = "CREATE_BASEMENT_CLEANUP_TEST_EVENT"
CALENDAR_TIMEZONE = ZoneInfo("America/New_York")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create the guarded Freyja 6 calendar write smoke event.")
    parser.add_argument("--core-url", default=os.environ.get("FREYJA6_CORE_URL", "http://127.0.0.1:8510"))
    parser.add_argument("--calendar-id", default=os.environ.get("FREYJA6_CALENDAR_WRITE_CALENDAR_ID", ""))
    parser.add_argument("--base-date", default=os.environ.get("FREYJA6_CALENDAR_WRITE_BASE_DATE", ""))
    parser.add_argument("--start-time", default=os.environ.get("FREYJA6_CALENDAR_WRITE_START_TIME", "09:00:00"))
    parser.add_argument("--duration-minutes", type=int, default=60)
    parser.add_argument("--approval", default="")
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser


def run_smoke(
    *,
    core_url: str,
    calendar_id: str,
    base_date: str,
    start_time: str,
    duration_minutes: int,
    approval: str,
    timeout: float,
) -> dict[str, Any]:
    if approval != REQUIRED_APPROVAL:
        return {"ok": False, "error": f"--approval must be {REQUIRED_APPROVAL!r}"}
    if not calendar_id.strip():
        return {"ok": False, "error": "--calendar-id or FREYJA6_CALENDAR_WRITE_CALENDAR_ID is required."}
    validation_error = _validate_calendar_inputs(base_date=base_date, start_time=start_time, duration_minutes=duration_minutes)
    if validation_error:
        return {"ok": False, "error": validation_error}
    trace_prefix = f"freyja6-calendar-{uuid.uuid4().hex[:12]}"
    with httpx.Client(base_url=core_url.rstrip("/"), timeout=timeout) as client:
        resolved = _core_tool_call(
            client,
            "calendar.resolve_date",
            {"phrase": "this Saturday", **({"base_date": base_date} if base_date else {})},
            trace_id=f"{trace_prefix}-resolve",
        )
        if not resolved.get("ok") or not resolved.get("date"):
            return {"ok": False, "resolve": resolved, "error": "Could not resolve this Saturday."}
        event_date = str(resolved["date"])
        if not _is_iso_date(event_date) or not _is_saturday(event_date):
            return {"ok": False, "resolve": resolved, "event_date": event_date, "error": "Resolved date must be an ISO Saturday."}
        start, end = _event_window(event_date, start_time, duration_minutes)
        created = _core_tool_call(
            client,
            "calendar.create_event",
            {
                "title": "Basement cleanup",
                "calendar_id": calendar_id,
                "start": start,
                "end": end,
                "description": "Freyja 6 validation event created from: Add basement cleanup this Saturday",
            },
            trace_id=f"{trace_prefix}-create",
        )
    return {
        "ok": bool(created.get("ok")),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "core_url_redacted": _redact_url(core_url),
        "calendar_id_redacted": _redact_calendar_id(calendar_id),
        "resolve": resolved,
        "create": created,
        "event_title": "Basement cleanup",
        "event_date": event_date,
        "duration_minutes": duration_minutes,
    }


def update_evidence(path: Path, smoke: dict[str, Any]) -> dict[str, Any]:
    payload = _load_evidence(path)
    acceptance = _acceptance_map(payload)
    captured_at = smoke.get("timestamp") or datetime.now(timezone.utc).isoformat()
    if _calendar_create_ok(smoke):
        acceptance["calendar_create_event"] = {
            "status": "complete",
            "captured_at": captured_at,
            "source": "freyja6-calendar-write-smoke",
            "evidence": {
                "event_title": smoke["event_title"],
                "event_date": smoke["event_date"],
                "tool_trace_id": smoke["create"]["trace_id"],
                "created_event_id": _redact_event_id(_created_event_identifier(smoke["create"]["event"])),
            },
        }
    payload["last_calendar_write_smoke"] = smoke
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def append_logs(log_root: Path, smoke: dict[str, Any]) -> list[dict[str, Any]]:
    create = smoke.get("create", {})
    if not isinstance(create, dict) or not create.get("trace_id"):
        return []
    log_root.mkdir(parents=True, exist_ok=True)
    tool_log = log_root / "freyja-test-tools.jsonl"
    acceptance_log = log_root / "freyja-test-acceptance.jsonl"
    timestamp = smoke.get("timestamp") or datetime.now(timezone.utc).isoformat()
    trace_id = str(create.get("trace_id") or "")
    accepted = _calendar_create_ok(smoke)
    tool_entry = {
        "timestamp": timestamp,
        "event": "tool_call",
        "trace_id": trace_id,
        "tool": "calendar.create_event",
        "status": "ok" if accepted else "failed",
        "source": "freyja6-calendar-write-smoke",
    }
    if isinstance(create.get("status_code"), int):
        tool_entry["status_code"] = create["status_code"]
    if not accepted:
        tool_entry["error_summary"] = _calendar_create_failure_summary(smoke)
    _append_jsonl(
        tool_log,
        tool_entry,
    )
    writes = [{"log": _redact_log_path(tool_log), "trace_id": trace_id}]
    if accepted:
        _append_jsonl(
            acceptance_log,
            {
                "timestamp": timestamp,
                "event": "acceptance",
                "trace_id": trace_id,
                "acceptance_id": "calendar_create_event",
                "status": "ok",
                "source": "freyja6-calendar-write-smoke",
            },
        )
        writes.append({"log": _redact_log_path(acceptance_log), "trace_id": trace_id})
    return writes


def preflight_log_writes(log_root: Path) -> None:
    _check_append_path(log_root / "freyja-test-tools.jsonl")
    _check_append_path(log_root / "freyja-test-acceptance.jsonl")


def _append_jsonl(path: Path, entry: dict[str, Any]) -> None:
    _check_append_path(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def _check_append_path(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"Log file must not be a symlink: {path.name}.")
    if path.exists() and not path.is_file():
        raise ValueError(f"Log file must be a regular file: {path.name}.")


def _calendar_create_ok(smoke: dict[str, Any]) -> bool:
    create = smoke.get("create", {})
    event_date = str(smoke.get("event_date") or "")
    return (
        smoke.get("ok") is True
        and smoke.get("event_title") == "Basement cleanup"
        and _is_iso_date(event_date)
        and _is_saturday(event_date)
        and isinstance(create, dict)
        and create.get("ok") is True
        and create.get("tool") == "calendar.create_event"
        and _trace_id_is_validation_trace(str(create.get("trace_id") or ""))
        and _created_event_matches_date(
            create.get("event"),
            event_date,
            str(smoke.get("calendar_id_redacted") or ""),
            _duration_minutes(smoke),
        )
    )


def _calendar_create_failure_summary(smoke: dict[str, Any]) -> str:
    create = smoke.get("create", {})
    if not isinstance(create, dict):
        return "calendar create result was missing"
    if create.get("ok") is not True:
        error = str(create.get("error") or "").strip()
        return error[:160] if error else "calendar create result was not marked ok"
    if create.get("tool") != "calendar.create_event":
        return "calendar write smoke used unexpected tool"
    if not _trace_id_is_validation_trace(str(create.get("trace_id") or "")):
        return "trace id is not a Freyja validation trace"
    if smoke.get("event_title") != "Basement cleanup":
        return "event title did not match Basement cleanup"
    event_date = str(smoke.get("event_date") or "")
    if not _is_iso_date(event_date) or not _is_saturday(event_date):
        return "event date was not an ISO Saturday"
    if not _created_event_matches_date(create.get("event"), event_date, str(smoke.get("calendar_id_redacted") or ""), _duration_minutes(smoke)):
        return "created event did not match the resolved acceptance date"
    if smoke.get("ok") is not True:
        return "calendar write smoke was not marked ok"
    return "calendar create result failed acceptance validation"


def _created_event_matches_date(event: Any, event_date: str, calendar_id_redacted: str = "", duration_minutes: int = 60) -> bool:
    if not isinstance(event, dict):
        return False
    start = str(event.get("start") or event.get("start_time") or "")
    end = str(event.get("end") or event.get("end_time") or "")
    try:
        parsed_start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        parsed_end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed_start.tzinfo is None or parsed_start.utcoffset() is None:
        return False
    if parsed_end.tzinfo is None or parsed_end.utcoffset() is None:
        return False
    if parsed_start.astimezone(CALENDAR_TIMEZONE).date().isoformat() != event_date:
        return False
    if parsed_end <= parsed_start:
        return False
    if parsed_end != parsed_start + timedelta(minutes=duration_minutes):
        return False
    if not _created_event_has_identifier(event):
        return False
    title = str(event.get("title") or event.get("summary") or "")
    if title != "Basement cleanup":
        return False
    event_calendar = event.get("calendar_id") or event.get("calendarId") or event.get("calendar")
    if event_calendar and calendar_id_redacted and _redact_calendar_id(str(event_calendar)) != calendar_id_redacted:
        return False
    return True


def _created_event_has_identifier(event: dict[str, Any]) -> bool:
    return bool(_created_event_identifier(event))


def _created_event_identifier(event: dict[str, Any]) -> str:
    for key in ("event_id", "id", "uid"):
        identifier = str(event.get(key) or "").strip()
        if identifier and "..." not in identifier:
            return identifier
    return ""


def _redact_event_id(identifier: str) -> str:
    value = identifier.strip()
    if not value:
        return ""
    if len(value) <= 8:
        return f"event-id-...{value}"
    return f"event-id-{value[:4]}...{value[-4:]}"


def _duration_minutes(smoke: dict[str, Any]) -> int:
    value = smoke.get("duration_minutes", 60)
    return value if isinstance(value, int) and 1 <= value <= 240 else 60


def _is_iso_date(value: str) -> bool:
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return len(value) == 10


def _is_saturday(value: str) -> bool:
    try:
        return datetime.fromisoformat(value).weekday() == 5
    except ValueError:
        return False


def _validate_calendar_inputs(*, base_date: str, start_time: str, duration_minutes: int) -> str:
    if base_date and not _is_iso_date(base_date):
        return "--base-date must be an ISO date in YYYY-MM-DD form."
    try:
        parsed = datetime.strptime(start_time, "%H:%M:%S")
    except ValueError:
        return "--start-time must use HH:MM:SS."
    if parsed.time().isoformat() != start_time:
        return "--start-time must use zero-padded HH:MM:SS."
    if duration_minutes < 1 or duration_minutes > 240:
        return "--duration-minutes must be between 1 and 240."
    return ""


def _trace_id_is_validation_trace(trace_id: str) -> bool:
    trace = trace_id.strip()
    return "..." not in trace and (trace.startswith("trace-") or trace.startswith("freyja6-"))


def _redact_log_path(path: Path) -> str:
    return f"freyja6/logs/{path.name}"


def _redact_calendar_id(calendar_id: str) -> str:
    value = calendar_id.strip()
    if len(value) <= 4:
        return "calendar-redacted"
    return "calendar-..." + value[-4:]


def _core_tool_call(client: httpx.Client, tool: str, arguments: dict[str, Any], *, trace_id: str) -> dict[str, Any]:
    try:
        response = client.post("/tools/call", headers={"X-Freyja-Trace-Id": trace_id}, json={"tool": tool, "arguments": arguments})
        body = _safe_json(response)
    except httpx.HTTPError as exc:
        return {"ok": False, "tool": tool, "trace_id": trace_id, "error": str(exc)}
    result = {
        "ok": response.status_code < 400 and isinstance(body, dict) and body.get("ok") is True,
        "tool": tool,
        "trace_id": trace_id,
        "status_code": response.status_code,
    }
    if isinstance(body, dict):
        for key in ("date", "event"):
            if key in body:
                result[key] = body[key]
    return result


def _end_time(start: str, duration_minutes: int) -> str:
    parsed = datetime.fromisoformat(start)
    return (parsed + timedelta(minutes=max(1, duration_minutes))).isoformat()


def _event_window(event_date: str, start_time: str, duration_minutes: int) -> tuple[str, str]:
    local_start = datetime.fromisoformat(f"{event_date}T{start_time}").replace(tzinfo=CALENDAR_TIMEZONE)
    local_end = local_start + timedelta(minutes=duration_minutes)
    return local_start.isoformat(), local_end.isoformat()


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except json.JSONDecodeError:
        return {}


def _load_evidence(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ValueError("Live evidence file must not be a symlink.")
    if path.exists() and not path.is_file():
        raise ValueError("Live evidence file must be a regular file.")
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload.setdefault("schema_version", "1.0")
            payload.setdefault("report_type", "freyja6-live-evidence")
            return payload
    return {"schema_version": "1.0", "report_type": "freyja6-live-evidence", "acceptance": {}}


def _acceptance_map(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != "1.0" or payload.get("report_type") != "freyja6-live-evidence":
        raise ValueError("Live evidence file must be a freyja6-live-evidence schema_version 1.0 artifact.")
    acceptance = payload.setdefault("acceptance", {})
    if not isinstance(acceptance, dict):
        raise ValueError("Live evidence acceptance must be an object before smoke helpers can update it.")
    return acceptance


def _redact_url(url: str) -> str:
    return url.replace("100.94.80.21", "vulcan-tailnet").replace("127.0.0.1", "atlas-loopback")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _acceptance_map(_load_evidence(args.evidence))
        preflight_log_writes(args.log_root)
    except ValueError as exc:
        print(json.dumps({"ok": False, "evidence": str(args.evidence), "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    smoke = run_smoke(
        core_url=args.core_url,
        calendar_id=args.calendar_id,
        base_date=args.base_date,
        start_time=args.start_time,
        duration_minutes=args.duration_minutes,
        approval=args.approval,
        timeout=args.timeout,
    )
    try:
        update_evidence(args.evidence, smoke)
    except ValueError as exc:
        print(json.dumps({"ok": False, "evidence": str(args.evidence), "error": str(exc), "smoke": smoke}, indent=2, sort_keys=True))
        return 2
    log_writes = append_logs(args.log_root, smoke)
    ok = _calendar_create_ok(smoke)
    print(json.dumps({"ok": ok, "evidence": str(args.evidence), "log_writes": log_writes, "smoke": smoke}, indent=2, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
