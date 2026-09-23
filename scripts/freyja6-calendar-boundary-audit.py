#!/usr/bin/env python3
"""Audit Freyja 6 calendar read/write validation boundaries."""

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
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

DEFAULT_TOOL_BOUNDARIES = Path("config/freyja6/tool-boundaries.yaml")
DEFAULT_CALENDAR_SMOKE = Path("scripts/freyja6-calendar-write-smoke.py")
DEFAULT_TOOL_SMOKE = Path("scripts/freyja6-tool-smoke.py")
DEFAULT_CORE = Path("src/freyja/core.py")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-calendar-boundary-audit.json")
REQUIRED_APPROVAL = "CREATE_BASEMENT_CLEANUP_TEST_EVENT"
EXPECTED_CALENDAR_TOOLS = ["calendar.list_events", "calendar.resolve_date", "calendar.create_event"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 calendar boundaries.")
    parser.add_argument("--tool-boundaries", type=Path, default=DEFAULT_TOOL_BOUNDARIES)
    parser.add_argument("--calendar-smoke", type=Path, default=DEFAULT_CALENDAR_SMOKE)
    parser.add_argument("--tool-smoke", type=Path, default=DEFAULT_TOOL_SMOKE)
    parser.add_argument("--core", type=Path, default=DEFAULT_CORE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(*, tool_boundaries: Path, calendar_smoke: Path, tool_smoke: Path, core: Path) -> dict[str, Any]:
    source_check = _check_files(tool_boundaries, calendar_smoke, tool_smoke, core)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-calendar-boundary-audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "checks": [source_check],
            "failures": failures,
            "next_actions": _next_actions(failures),
        }
    boundary_doc = _load_yaml(tool_boundaries)
    calendar_smoke_text = _read_text(calendar_smoke)
    tool_smoke_text = _read_text(tool_smoke)
    core_text = _read_text(core)
    gateway = _load_gateway()
    checks = [
        source_check,
        _check_tool_boundaries(boundary_doc),
        _check_gateway_policy(gateway),
        _check_calendar_write_smoke(calendar_smoke_text),
        _check_calendar_read_smoke(tool_smoke_text),
        _check_core_delete_guard(core_text),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-calendar-boundary-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_tool_boundaries(boundary_doc: dict[str, Any]) -> dict[str, Any]:
    calendar = boundary_doc.get("tool_targets", {}).get("calendar", {})
    failures: list[str] = []
    if calendar.get("boundary") != "mcp" or calendar.get("server") != "freyja-core-gateway":
        failures.append("Calendar must route through freyja-core-gateway MCP.")
    if calendar.get("gateway_tool") != "tools.call":
        failures.append("Calendar must use tools.call.")
    if calendar.get("core_tools") != EXPECTED_CALENDAR_TOOLS:
        failures.append("Calendar core_tools must include resolve/read/create only.")
    if "calendar_create_event" not in (calendar.get("acceptance") or []):
        failures.append("Calendar acceptance must include calendar_create_event.")
    if failures:
        return {"id": "calendar_tool_boundaries", "status": "fail", "message": "Calendar tool boundary drifted.", "failures": failures}
    return _passed("calendar_tool_boundaries", "Calendar read and guarded create routes through Freyja Core MCP.")


def _check_gateway_policy(gateway: Any) -> dict[str, Any]:
    visible = {tool.name for tool in gateway.TOOL_CATALOG if gateway.is_allowed("freyja-test", tool.name)}
    failures: list[str] = []
    for tool in EXPECTED_CALENDAR_TOOLS:
        if tool not in visible:
            failures.append(f"freyja-test policy is missing {tool}.")
    if "calendar.delete_event" in visible:
        failures.append("freyja-test policy must not expose calendar.delete_event.")
    catalog = {tool.name: tool for tool in gateway.TOOL_CATALOG}
    if catalog.get("calendar.delete_event", None) is None or catalog["calendar.delete_event"].risk != "destructive":
        failures.append("calendar.delete_event must remain cataloged as destructive.")
    if failures:
        return {"id": "calendar_gateway_policy", "status": "fail", "message": "Freyja Core calendar policy drifted.", "failures": failures}
    return _passed("calendar_gateway_policy", "freyja-test can resolve/read/create calendar events but cannot delete them.")


def _check_calendar_write_smoke(text: str) -> dict[str, Any]:
    required = [
        f'REQUIRED_APPROVAL = "{REQUIRED_APPROVAL}"',
        '"calendar.resolve_date"',
        '"phrase": "this Saturday"',
        '"calendar.create_event"',
        '"title": "Basement cleanup"',
        "Add basement cleanup this Saturday",
        '"source": "freyja6-calendar-write-smoke"',
        '"acceptance_id": "calendar_create_event"',
    ]
    missing = [item for item in required if item not in text]
    if "calendar.delete_event" in text:
        missing.append("calendar write smoke must not call calendar.delete_event")
    if missing:
        return {"id": "calendar_write_smoke", "status": "fail", "message": "Guarded calendar write smoke drifted.", "missing": missing}
    return _passed("calendar_write_smoke", "Calendar write smoke creates only the approved basement-cleanup validation event.")


def _check_calendar_read_smoke(text: str) -> dict[str, Any]:
    required = ['"calendar.list_events"', '"source": "freyja6-tool-smoke"', '"calendar_read"']
    missing = [item for item in required if item not in text]
    if missing:
        return {"id": "calendar_read_smoke", "status": "fail", "message": "Calendar read smoke drifted.", "missing": missing}
    return _passed("calendar_read_smoke", "Tool smoke records read-only calendar evidence through calendar.list_events.")


def _check_core_delete_guard(text: str) -> dict[str, Any]:
    required = ["DELETE_FREYJA_CORE_SMOKE_EVENT", "approval_required", "calendar.delete_event requires event_id"]
    missing = [item for item in required if item not in text]
    if missing:
        return {"id": "calendar_delete_guard", "status": "fail", "message": "Calendar delete guard drifted.", "missing": missing}
    return _passed("calendar_delete_guard", "Calendar delete remains guarded inside Freyja Core and outside freyja-test policy.")


def _load_gateway() -> Any:
    from freyja import mcp_gateway

    return mcp_gateway


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Run the guarded calendar write smoke only with explicit validation approval."]


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required calendar boundary source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required calendar boundary source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Calendar boundary source files are present.")


def _load_yaml(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    try:
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    resolved = _resolve(path)
    try:
        return resolved.read_text(encoding="utf-8")
    except OSError:
        return ""


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
        "report_type": "freyja6-calendar-boundary-audit",
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
        else build_report(tool_boundaries=args.tool_boundaries, calendar_smoke=args.calendar_smoke, tool_smoke=args.tool_smoke, core=args.core)
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
