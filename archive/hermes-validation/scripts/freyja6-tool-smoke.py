#!/usr/bin/env python3
"""Run non-mutating Freyja 6 tool smokes and record redacted evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_EVIDENCE = Path("certification/reports/freyja6-live-evidence.json")
DEFAULT_LOG_ROOT = Path(os.environ.get("FREYJA6_LOG_ROOT", "/srv/freyja6/logs"))
SAFE_COMMANDS = {"pwd", "date", "whoami", "ls", "rg"}
APPROVED_FILE_ROOTS = tuple(
    dict.fromkeys(
        [
            Path(os.environ.get("FREYJA6_APPROVED_FILES_ROOT", "/srv/freyja6/approved-files")),
            Path("/srv/freyja6/approved-files"),
            Path("/workspace/approved"),
        ]
    )
)
CODING_WORKFLOW_RESULT_SUMMARY = "opencode status queried through Freyja Core"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Freyja 6 non-mutating tool smoke checks.")
    parser.add_argument("--core-url", default=os.environ.get("FREYJA6_CORE_URL", "http://127.0.0.1:8510"))
    parser.add_argument("--core-mcp-health-url", default=os.environ.get("FREYJA6_CORE_MCP_HEALTH_URL", "http://127.0.0.1:8766/healthz"))
    parser.add_argument("--terminal-mcp-health-url", default=os.environ.get("FREYJA6_TERMINAL_MCP_HEALTH_URL", "http://127.0.0.1:8765/healthz"))
    parser.add_argument("--approved-file", default=os.environ.get("FREYJA6_APPROVED_SMOKE_FILE", ""))
    parser.add_argument("--safe-command", default="pwd", choices=sorted(SAFE_COMMANDS))
    parser.add_argument("--calendar-start", default=os.environ.get("FREYJA6_CALENDAR_SMOKE_START", "2026-09-19T00:00:00+00:00"))
    parser.add_argument("--calendar-end", default=os.environ.get("FREYJA6_CALENDAR_SMOKE_END", "2026-09-20T00:00:00+00:00"))
    parser.add_argument("--home-domain", default=os.environ.get("FREYJA6_HOME_SMOKE_DOMAIN", "sensor"))
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser


def run_smoke(
    *,
    core_url: str,
    core_mcp_health_url: str,
    terminal_mcp_health_url: str,
    approved_file: str,
    safe_command: str,
    calendar_start: str,
    calendar_end: str,
    home_domain: str,
    timeout: float,
) -> dict[str, Any]:
    trace_prefix = f"freyja6-tools-{uuid.uuid4().hex[:12]}"
    checks: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_prefix": trace_prefix,
        "core_url_redacted": _redact_url(core_url),
        "core_mcp_health": _http_health(core_mcp_health_url, timeout=timeout),
        "terminal_mcp_health": _http_health(terminal_mcp_health_url, timeout=timeout),
        "approved_file": _read_approved_file(approved_file, trace_id=f"{trace_prefix}-file"),
        "safe_terminal": _run_safe_command(safe_command, trace_id=f"{trace_prefix}-terminal"),
    }
    with httpx.Client(base_url=core_url.rstrip("/"), timeout=timeout) as client:
        checks["mcp_discovery"] = _core_tool_call(client, "status.check", {}, trace_id=f"{trace_prefix}-mcp")
        checks["calendar_read"] = _core_tool_call(
            client,
            "calendar.list_events",
            {"start": calendar_start, "end": calendar_end},
            trace_id=f"{trace_prefix}-calendar",
        )
        checks["home_assistant_query"] = _core_tool_call(
            client,
            "home_assistant.list_states",
            {"domain": home_domain},
            trace_id=f"{trace_prefix}-home",
        )
        checks["coding_workflow"] = _core_tool_call(
            client,
            "opencode.status",
            {"alias": "freyja-core-coder"},
            trace_id=f"{trace_prefix}-coding",
        )
    return checks


def update_evidence(path: Path, smoke: dict[str, Any]) -> dict[str, Any]:
    payload = _load_evidence(path)
    acceptance = _acceptance_map(payload)
    captured_at = smoke.get("timestamp") or datetime.now(timezone.utc).isoformat()

    approved = smoke.get("approved_file", {})
    if _approved_file_result_ok(approved):
        acceptance["approved_file_read"] = {
            "status": "complete",
            "captured_at": captured_at,
            "source": "freyja6-tool-smoke",
            "evidence": {
                "approved_path": approved["path_redacted"],
                "tool_trace_id": approved["trace_id"],
                "bytes_read": approved["bytes"],
            },
        }

    terminal = smoke.get("safe_terminal", {})
    if _safe_terminal_result_ok(terminal):
        acceptance["safe_terminal"] = {
            "status": "complete",
            "captured_at": captured_at,
            "source": "freyja6-tool-smoke",
            "evidence": {
                "command": terminal["command"],
                "tool_trace_id": terminal["trace_id"],
                "exit_code": terminal["exit_code"],
                "working_dir": terminal["working_dir"],
            },
        }

    core_mcp = smoke.get("core_mcp_health", {})
    discovery = smoke.get("mcp_discovery", {})
    if core_mcp.get("ok") and _tool_result_ok(discovery, "status.check"):
        acceptance["mcp_tool"] = {
            "status": "complete",
            "captured_at": captured_at,
            "source": "freyja6-tool-smoke",
            "evidence": {
                "server": "freyja-core-gateway",
                "tool": "status.check",
                "tool_trace_id": discovery["trace_id"],
                "status_code": discovery["status_code"],
            },
        }

    calendar = smoke.get("calendar_read", {})
    if _tool_result_ok(calendar, "calendar.list_events"):
        acceptance["calendar_read"] = {
            "status": "complete",
            "captured_at": captured_at,
            "source": "freyja6-tool-smoke",
            "evidence": {
                "calendar_name_redacted": "configured-calendar",
                "tool_trace_id": calendar["trace_id"],
                "status_code": calendar["status_code"],
            },
        }

    home = smoke.get("home_assistant_query", {})
    if _tool_result_ok(home, "home_assistant.list_states") and _home_assistant_result_ok(home):
        acceptance["home_assistant_query"] = {
            "status": "complete",
            "captured_at": captured_at,
            "source": "freyja6-tool-smoke",
            "evidence": {
                "entity_id_redacted": "domain:" + str(home.get("domain")),
                "tool_trace_id": home["trace_id"],
                "states_count": home["states_count"],
            },
        }

    coding = smoke.get("coding_workflow", {})
    if _coding_workflow_result_ok(coding):
        acceptance["coding_workflow"] = {
            "status": "complete",
            "captured_at": captured_at,
            "source": "freyja6-tool-smoke",
            "evidence": {
                "executor": "opencode",
                "handoff_trace_id": coding["trace_id"],
                "result_summary": coding["result_summary"],
                "status_keys": coding["status_keys"],
            },
        }

    payload["last_tool_smoke"] = smoke
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def append_logs(log_root: Path, smoke: dict[str, Any]) -> list[dict[str, Any]]:
    log_root.mkdir(parents=True, exist_ok=True)
    tool_log = log_root / "freyja-test-tools.jsonl"
    acceptance_log = log_root / "freyja-test-acceptance.jsonl"
    writes: list[dict[str, Any]] = []
    captured_at = smoke.get("timestamp") or datetime.now(timezone.utc).isoformat()
    tool_items = [
        ("approved_file_read", "filesystem.read", smoke.get("approved_file", {})),
        ("safe_terminal", "terminal.safe_command", smoke.get("safe_terminal", {})),
        ("mcp_tool", "status.check", smoke.get("mcp_discovery", {})),
        ("calendar_read", "calendar.list_events", smoke.get("calendar_read", {})),
        ("home_assistant_query", "home_assistant.list_states", smoke.get("home_assistant_query", {})),
        ("coding_workflow", "opencode.status", smoke.get("coding_workflow", {})),
    ]
    acceptance_written = False
    for acceptance_id, tool_name, item in tool_items:
        if not isinstance(item, dict) or not item.get("trace_id"):
            continue
        accepted = _tool_acceptance_log_ok(acceptance_id, item, smoke)
        status = "ok" if accepted else "failed"
        entry = {
            "timestamp": captured_at,
            "event": "tool_call",
            "trace_id": item["trace_id"],
            "tool": tool_name,
            "status": status,
            "source": "freyja6-tool-smoke",
        }
        if isinstance(item.get("status_code"), int):
            entry["status_code"] = item["status_code"]
        if not accepted:
            entry["error_summary"] = _tool_failure_summary(acceptance_id, item, smoke)
        _append_jsonl(
            tool_log,
            entry,
        )
        writes.append({"log": _redact_log_path(tool_log), "trace_id": item["trace_id"]})
        if accepted:
            _append_jsonl(
                acceptance_log,
                {
                    "timestamp": captured_at,
                    "event": "acceptance",
                    "trace_id": item["trace_id"],
                    "acceptance_id": acceptance_id,
                    "status": "ok",
                    "source": "freyja6-tool-smoke",
                },
            )
            acceptance_written = True
    if acceptance_written:
        writes.append({"log": _redact_log_path(acceptance_log), "trace_id": smoke.get("trace_prefix", "")})
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


def _tool_result_ok(item: Any, expected_tool: str) -> bool:
    return (
        isinstance(item, dict)
        and item.get("ok") is True
        and item.get("tool") == expected_tool
        and _trace_id_is_validation_trace(str(item.get("trace_id") or ""))
    )


def _tool_acceptance_log_ok(acceptance_id: str, item: dict[str, Any], smoke: dict[str, Any]) -> bool:
    if acceptance_id == "approved_file_read":
        return _approved_file_result_ok(item)
    if acceptance_id == "safe_terminal":
        return _safe_terminal_result_ok(item)
    if acceptance_id == "mcp_tool":
        return bool(smoke.get("core_mcp_health", {}).get("ok")) and _tool_result_ok(item, "status.check")
    if acceptance_id == "calendar_read":
        return _tool_result_ok(item, "calendar.list_events")
    if acceptance_id == "home_assistant_query":
        return _tool_result_ok(item, "home_assistant.list_states") and _home_assistant_result_ok(item)
    if acceptance_id == "coding_workflow":
        return _coding_workflow_result_ok(item)
    return False


def _tool_failure_summary(acceptance_id: str, item: dict[str, Any], smoke: dict[str, Any]) -> str:
    if item.get("ok") is not True:
        error = str(item.get("error") or "").strip()
        return error[:160] if error else "tool result was not marked ok"
    trace_id = str(item.get("trace_id") or "")
    if not _trace_id_is_validation_trace(trace_id):
        return "trace id is not a Freyja validation trace"
    if acceptance_id == "approved_file_read":
        if not str(item.get("path_redacted") or "").startswith("approved-files/"):
            return "approved file path was outside approved-files"
    elif acceptance_id == "safe_terminal":
        if str(item.get("command") or "") not in SAFE_COMMANDS:
            return "command is not in safe allowlist"
        if item.get("exit_code") != 0:
            return "safe command exited nonzero"
    elif acceptance_id == "mcp_tool":
        if not bool(smoke.get("core_mcp_health", {}).get("ok")):
            return "core MCP health check was not ok"
        if item.get("tool") != "status.check":
            return "MCP smoke used unexpected tool"
    elif acceptance_id == "calendar_read":
        if item.get("tool") != "calendar.list_events":
            return "calendar read smoke used unexpected tool"
    elif acceptance_id == "home_assistant_query":
        if item.get("tool") != "home_assistant.list_states":
            return "Home Assistant smoke used unexpected tool"
        if not _home_assistant_result_ok(item):
            return "Home Assistant result was not domain-scoped with states"
    elif acceptance_id == "coding_workflow":
        if item.get("tool") != "opencode.status":
            return "coding workflow smoke used unexpected tool"
        if item.get("alias") != "freyja-core-coder":
            return "coding workflow must target freyja-core-coder"
        if item.get("status_payload_present") is not True or not isinstance(item.get("status_keys"), list) or not item["status_keys"]:
            return "coding workflow status payload was missing"
    return "tool result failed acceptance validation"


def _home_assistant_result_ok(item: dict[str, Any]) -> bool:
    domain = str(item.get("domain") or "")
    result_keys = item.get("result_keys")
    return (
        bool(domain)
        and domain.replace("_", "").isalnum()
        and isinstance(result_keys, list)
        and ("states" in result_keys or "entities" in result_keys)
        and isinstance(item.get("states_count"), int)
        and item["states_count"] > 0
    )


def _coding_workflow_result_ok(item: dict[str, Any]) -> bool:
    return (
        _tool_result_ok(item, "opencode.status")
        and item.get("alias") == "freyja-core-coder"
        and item.get("result_summary") == CODING_WORKFLOW_RESULT_SUMMARY
        and item.get("status_payload_present") is True
        and isinstance(item.get("status_keys"), list)
        and bool(item["status_keys"])
    )


def _approved_file_result_ok(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    path_redacted = str(item.get("path_redacted") or "")
    return (
        item.get("ok") is True
        and path_redacted.startswith("approved-files/")
        and _trace_id_is_validation_trace(str(item.get("trace_id") or ""))
    )


def _safe_terminal_result_ok(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    command = str(item.get("command") or "")
    return (
        item.get("ok") is True
        and command in SAFE_COMMANDS
        and item.get("exit_code") == 0
        and item.get("working_dir") == "freyja-os"
        and _trace_id_is_validation_trace(str(item.get("trace_id") or ""))
    )


def _tool_smoke_ok(smoke: dict[str, Any]) -> bool:
    approved = smoke.get("approved_file", {})
    terminal = smoke.get("safe_terminal", {})
    core_mcp = smoke.get("core_mcp_health", {})
    discovery = smoke.get("mcp_discovery", {})
    calendar = smoke.get("calendar_read", {})
    home = smoke.get("home_assistant_query", {})
    coding = smoke.get("coding_workflow", {})
    return (
        _approved_file_result_ok(approved)
        and _safe_terminal_result_ok(terminal)
        and isinstance(core_mcp, dict)
        and core_mcp.get("ok") is True
        and _tool_result_ok(discovery, "status.check")
        and _tool_result_ok(calendar, "calendar.list_events")
        and isinstance(home, dict)
        and _tool_result_ok(home, "home_assistant.list_states")
        and _home_assistant_result_ok(home)
        and isinstance(coding, dict)
        and _coding_workflow_result_ok(coding)
    )


def _trace_id_is_validation_trace(trace_id: str) -> bool:
    trace = trace_id.strip()
    return "..." not in trace and (trace.startswith("trace-") or trace.startswith("freyja6-"))


def _redact_log_path(path: Path) -> str:
    return f"freyja6/logs/{path.name}"


def _core_tool_call(client: httpx.Client, tool: str, arguments: dict[str, Any], *, trace_id: str) -> dict[str, Any]:
    try:
        response = client.post("/tools/call", headers={"X-Freyja-Trace-Id": trace_id}, json={"tool": tool, "arguments": arguments})
        body = _safe_json(response)
        ok = response.status_code < 400 and isinstance(body, dict) and body.get("ok") is True
        result = {
            "ok": ok,
            "tool": tool,
            "trace_id": trace_id,
            "status_code": response.status_code,
        }
        if tool == "home_assistant.list_states":
            result["domain"] = arguments.get("domain", "sensor")
        if tool == "opencode.status":
            result["alias"] = arguments.get("alias", "")
            result["result_summary"] = CODING_WORKFLOW_RESULT_SUMMARY
        if isinstance(body, dict):
            result["result_keys"] = sorted(str(key) for key in body.keys())
            if tool == "home_assistant.list_states":
                states = body.get("states")
                if not isinstance(states, list):
                    states = body.get("entities")
                if isinstance(states, list):
                    result["states_count"] = len(states)
            if tool == "opencode.status":
                status = body.get("status")
                result["status_payload_present"] = isinstance(status, dict)
                if isinstance(status, dict):
                    result["status_keys"] = sorted(str(key) for key in status.keys())
                else:
                    status_keys = [key for key in ("alias", "state") if key in body]
                    result["status_payload_present"] = bool(status_keys)
                    result["status_keys"] = sorted(status_keys)
        return result
    except httpx.HTTPError as exc:
        return {"ok": False, "tool": tool, "trace_id": trace_id, "error": str(exc)}


def _http_health(url: str, *, timeout: float) -> dict[str, Any]:
    try:
        response = httpx.get(url, timeout=timeout)
        body = _safe_json(response)
        return {
            "ok": response.status_code < 400 and isinstance(body, dict) and body.get("ok") is True,
            "url_redacted": _redact_url(url),
            "status_code": response.status_code,
            "service": body.get("service") if isinstance(body, dict) else None,
        }
    except httpx.HTTPError as exc:
        return {"ok": False, "url_redacted": _redact_url(url), "error": str(exc)}


def _read_approved_file(path_text: str, *, trace_id: str) -> dict[str, Any]:
    if not path_text:
        return {"ok": False, "trace_id": trace_id, "error": "No approved file supplied."}
    path = Path(path_text).expanduser()
    if not _approved_file_path_allowed(path):
        return {"ok": False, "trace_id": trace_id, "path_redacted": _redact_path(path), "error": "Approved file must be under a Freyja 6 approved read-only root."}
    try:
        data = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "trace_id": trace_id, "path_redacted": _redact_path(path), "error": str(exc)}
    return {
        "ok": True,
        "trace_id": trace_id,
        "path_redacted": _redact_path(path),
        "bytes": len(data.encode("utf-8")),
    }


def _approved_file_path_allowed(path: Path) -> bool:
    if not path.is_absolute():
        return False
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path.absolute()
    for root in APPROVED_FILE_ROOTS:
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return True
    return False


def _run_safe_command(command: str, *, trace_id: str) -> dict[str, Any]:
    if command not in SAFE_COMMANDS:
        return {"ok": False, "trace_id": trace_id, "command": command, "error": "Command is not in safe allowlist."}
    result = subprocess.run([command], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10, check=False)
    return {
        "ok": result.returncode == 0,
        "trace_id": trace_id,
        "command": command,
        "exit_code": result.returncode,
        "working_dir": _redact_working_dir(REPO_ROOT),
    }


def _redact_working_dir(path: Path) -> str:
    return path.name


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


def _redact_path(path: Path) -> str:
    text = str(path)
    for marker in (str(Path(os.environ.get("FREYJA6_APPROVED_FILES_ROOT", "/srv/freyja6/approved-files"))), "/srv/freyja6/approved-files", "/workspace/approved"):
        if text.startswith(marker):
            return text.replace(marker, "approved-files", 1)
    return path.name


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
        core_mcp_health_url=args.core_mcp_health_url,
        terminal_mcp_health_url=args.terminal_mcp_health_url,
        approved_file=args.approved_file,
        safe_command=args.safe_command,
        calendar_start=args.calendar_start,
        calendar_end=args.calendar_end,
        home_domain=args.home_domain,
        timeout=args.timeout,
    )
    try:
        update_evidence(args.evidence, smoke)
    except ValueError as exc:
        print(json.dumps({"ok": False, "evidence": str(args.evidence), "error": str(exc), "smoke": smoke}, indent=2, sort_keys=True))
        return 2
    log_writes = append_logs(args.log_root, smoke)
    ok = _tool_smoke_ok(smoke)
    print(json.dumps({"ok": ok, "evidence": str(args.evidence), "log_writes": log_writes, "smoke": smoke}, indent=2, sort_keys=True))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
