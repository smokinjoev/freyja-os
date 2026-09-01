from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_REPORT_DIR = Path("certification/reports")
LIVE_BLOCKER_CHECK = "freyja5-live-blockers"
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"


@dataclass(frozen=True)
class Freyja5PreflightSummary:
    report_path: Path
    passed: bool
    source_ready: bool
    live_blocked: bool
    status: str
    failed_checks: tuple[str, ...]
    remaining: tuple[str, ...]
    agent_export_path: Path | None = None
    agent_export_ok: bool | None = None
    agent_export_status: str | None = None

    @property
    def exit_code(self) -> int:
        if self.passed:
            return 0
        if self.source_ready and self.live_blocked:
            return 2
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize Freyja 5 readiness bundle status.")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Specific freyja5-readiness-bundle JSON report. Defaults to the newest report in certification/reports.",
    )
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument(
        "--agent-export",
        type=Path,
        help="Optional freyja5-agent-definitions JSON export to validate and include in the summary.",
    )
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON summary.")
    return parser


def latest_readiness_bundle(report_dir: Path) -> Path:
    reports = sorted(report_dir.glob("*freyja5-readiness-bundle*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not reports:
        raise FileNotFoundError(f"No Freyja 5 readiness bundle reports found in {report_dir}")
    return reports[0]


def summarize_report(path: Path, *, agent_export: Path | None = None) -> Freyja5PreflightSummary:
    payload = _load_report(path)
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    failed = tuple(
        str(check.get("name", "unknown"))
        for check in checks
        if isinstance(check, dict) and check.get("ok") is not True
    )
    passed = bool(payload.get("passed") is True)
    source_ready = bool(payload.get("source_ready") is True)
    live_blocked = bool(payload.get("live_blocked") is True)
    remaining = _remaining_work(checks, failed_checks=failed)
    status = _status(passed=passed, source_ready=source_ready, live_blocked=live_blocked)
    agent_export_ok: bool | None = None
    agent_export_status: str | None = None
    if agent_export is not None:
        agent_export_ok, agent_export_status = validate_agent_export(agent_export)
    return Freyja5PreflightSummary(
        report_path=path,
        passed=passed,
        source_ready=source_ready,
        live_blocked=live_blocked,
        status=status,
        failed_checks=failed,
        remaining=remaining,
        agent_export_path=agent_export,
        agent_export_ok=agent_export_ok,
        agent_export_status=agent_export_status,
    )


def render_summary(summary: Freyja5PreflightSummary) -> str:
    lines = [
        "Freyja 5 preflight",
        f"Report: {summary.report_path}",
        f"Status: {summary.status}",
        f"Source ready: {str(summary.source_ready).lower()}",
        f"Live blocked: {str(summary.live_blocked).lower()}",
    ]
    if summary.failed_checks:
        lines.append("Failed checks:")
        lines.extend(f"- {name}" for name in summary.failed_checks)
    if summary.remaining:
        lines.append("Remaining:")
        lines.extend(f"- {item}" for item in summary.remaining)
    if summary.agent_export_path is not None:
        lines.append(f"Agent export: {summary.agent_export_status} ({summary.agent_export_path})")
    return "\n".join(lines)


def render_summary_json(summary: Freyja5PreflightSummary) -> str:
    return json.dumps(
        {
            "report_path": str(summary.report_path),
            "passed": summary.passed,
            "source_ready": summary.source_ready,
            "live_blocked": summary.live_blocked,
            "status": summary.status,
            "exit_code": summary.exit_code,
            "failed_checks": list(summary.failed_checks),
            "remaining": list(summary.remaining),
            "agent_export": (
                {
                    "path": str(summary.agent_export_path),
                    "ok": summary.agent_export_ok,
                    "status": summary.agent_export_status,
                }
                if summary.agent_export_path is not None
                else None
            ),
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = args.report or latest_readiness_bundle(args.report_dir)
        summary = summarize_report(report, agent_export=args.agent_export)
    except Exception as exc:
        print(f"Freyja 5 preflight status failed: {exc}", file=sys.stderr)
        return 1
    print(render_summary_json(summary) if args.json else render_summary(summary))
    return summary.exit_code


def _load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def validate_agent_export(path: Path) -> tuple[bool, str]:
    try:
        payload = _load_report(path)
    except Exception as exc:  # noqa: BLE001 - preflight should preserve failure class
        return False, type(exc).__name__
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))
    try:
        from freyja.freyja5_config import freyja5_agent_evidence
    except Exception as exc:  # noqa: BLE001 - import failures are operator-visible evidence
        return False, f"source import failed: {type(exc).__name__}"

    agents = payload.get("agents") if isinstance(payload.get("agents"), list) else []
    expected_agents = freyja5_agent_evidence()
    secret_markers = ("api_key", "token", "secret")
    if payload.get("export_type") != "freyja5-agent-definitions":
        return False, "wrong export_type"
    if payload.get("source_controlled") is not True:
        return False, "not source_controlled"
    if payload.get("secrets_included") is not False:
        return False, "secrets_included is not false"
    if _string_value_contains(payload, secret_markers):
        return False, "secret marker present"
    if agents != expected_agents:
        return False, "agent evidence drift"
    return True, "valid"


def _string_value_contains(value: Any, markers: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in markers)
    if isinstance(value, list):
        return any(_string_value_contains(item, markers) for item in value)
    if isinstance(value, dict):
        return any(_string_value_contains(item, markers) for item in value.values())
    return False


def _remaining_work(checks: list[Any], *, failed_checks: tuple[str, ...]) -> tuple[str, ...]:
    remaining: list[str] = []
    for check in checks:
        if not isinstance(check, dict) or str(check.get("name")) not in failed_checks:
            continue
        name = str(check.get("name"))
        if name == LIVE_BLOCKER_CHECK:
            blocker_details = check.get("blockers") if isinstance(check.get("blockers"), list) else []
            if blocker_details:
                for blocker in blocker_details:
                    if not isinstance(blocker, dict):
                        continue
                    blocker_id = blocker.get("id")
                    component = blocker.get("component") or "unknown"
                    requires = blocker.get("requires") if isinstance(blocker.get("requires"), list) else []
                    next_actions = blocker.get("next_actions") if isinstance(blocker.get("next_actions"), list) else []
                    requirement_text = ", ".join(str(requirement) for requirement in requires) or "validation evidence"
                    action_text = " ".join(str(action) for action in next_actions)
                    sentence = f"Resolve Joe-required blocker `{blocker_id}` ({component}): {requirement_text}."
                    if action_text:
                        sentence = f"{sentence} Next actions: {action_text}"
                    remaining.append(sentence)
                continue
            blockers = check.get("remaining") if isinstance(check.get("remaining"), list) else []
            for blocker in blockers:
                remaining.append(f"Resolve Joe-required blocker `{blocker}` in FREYJA-5.0-BLOCKERS.md.")
        else:
            remaining.append(f"Resolve {name}: {check.get('status', 'failed')}.")
    return tuple(remaining)


def _status(*, passed: bool, source_ready: bool, live_blocked: bool) -> str:
    if passed:
        return "complete"
    if source_ready and live_blocked:
        return "source-ready-live-blocked"
    return "not-ready"
