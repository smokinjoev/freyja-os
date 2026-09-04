#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if VENV_PYTHON.exists() and Path(sys.executable).resolve() != VENV_PYTHON.resolve():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

sys.path.insert(0, str(REPO_ROOT / "src"))

from freyja.open_webui_tools import (
    ToolInvocationRequest,
    authorize_tool_invocation,
    invoke_policy_boundary,
    load_agent_tool_policies,
    load_operation_policies,
)


DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-tools-gateway-readiness.json"
REQUIRED_OPERATIONS = {
    "search",
    "remember",
    "update",
    "forget",
    "record-decision",
    "recent-events",
    "calendar.read",
    "calendar.create",
    "reminders.read",
    "reminders.create",
    "imessage.send.approved",
    "shortcuts.run",
    "home.status",
    "home.device_action",
    "files.household.read",
    "files.beth.read",
    "pdf.analyze",
    "image.analyze",
    "infrastructure.health",
    "weather.read",
}


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit the Open WebUI tool gateway policy without invoking live side effects.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _allowed(operation: str, agent_id: str, *, confirmed: bool = False) -> bool:
    try:
        authorize_tool_invocation(ToolInvocationRequest(operation=operation, agent_id=agent_id, confirmed=confirmed))
    except Exception:
        return False
    return True


def build_report() -> dict[str, Any]:
    operations = load_operation_policies()
    agent_policies = load_agent_tool_policies()
    missing = sorted(REQUIRED_OPERATIONS - set(operations))
    extra = sorted(set(operations) - REQUIRED_OPERATIONS)
    confirmation_required = sorted(operation for operation, policy in operations.items() if policy.confirmation_required)
    child_allowed = sorted(operation for operation, policy in operations.items() if policy.children_allowed)
    weather_policy = authorize_tool_invocation(ToolInvocationRequest(operation="weather.read", agent_id="jenna"))
    calendar_policy = authorize_tool_invocation(ToolInvocationRequest(operation="calendar.create", agent_id="freyja", confirmed=True))
    dry_run_status = invoke_policy_boundary(weather_policy, ToolInvocationRequest(operation="weather.read", agent_id="jenna")).status
    confirmed_status = invoke_policy_boundary(
        calendar_policy,
        ToolInvocationRequest(operation="calendar.create", agent_id="freyja", confirmed=True),
    ).status
    generated_at = int(time.time())
    report = {
        "report_type": "open-webui-tools-gateway-readiness",
        "generated_at_unix": generated_at,
        "timestamp_unix": generated_at,
        "git_head": _git_head(),
        "secrets_included": False,
        "private_content_included": False,
        "operation_count": len(operations),
        "missing_operations": missing,
        "extra_operations": extra,
        "agent_count": len(agent_policies),
        "destructive_default_all_deny": all(policy.destructive_default == "deny" for policy in operations.values()),
        "confirmation_required": confirmation_required,
        "child_allowed_operations": child_allowed,
        "execution_statuses": {
            "read_only": dry_run_status,
            "confirmed_write": confirmed_status,
        },
        "checks": {
            "unknown_operation_denied": not _allowed("shell.run", "cloyd"),
            "calendar_create_requires_confirmation": not _allowed("calendar.create", "freyja") and _allowed("calendar.create", "freyja", confirmed=True),
            "children_cannot_use_admin_tools": not _allowed("infrastructure.health", "jenna"),
            "children_can_use_weather": _allowed("weather.read", "jenna"),
            "benedict_cannot_read_household_files": not _allowed("files.household.read", "benedict"),
            "benedict_can_read_beth_files": _allowed("files.beth.read", "benedict"),
            "cloyd_cannot_read_beth_files": not _allowed("files.beth.read", "cloyd"),
            "iris_write_requires_confirmation": not _allowed("shortcuts.run", "freyja") and _allowed("shortcuts.run", "freyja", confirmed=True),
            "read_only_operations_are_dry_run_only": dry_run_status == "dry_run_available",
            "confirmed_writes_do_not_execute_without_adapter": confirmed_status == "confirmed_not_configured",
        },
        "live_side_effects_invoked": False,
    }
    report["ok"] = (
        not missing
        and report["destructive_default_all_deny"]
        and all(report["checks"].values())
        and report["live_side_effects_invoked"] is False
    )
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report()
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
