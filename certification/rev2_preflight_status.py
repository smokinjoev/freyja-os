from __future__ import annotations

import argparse
import json
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_REPORT_DIR = Path("certification/reports")
IMESSAGE_SMOKE_CHECK = "imessage-live-smoke-report"
SIGNAL_SMOKE_CHECK = "signal-live-smoke-report"
VULCAN_CHECK = "vulcan-readiness-report"
SMOKE_CHECKS = (IMESSAGE_SMOKE_CHECK, SIGNAL_SMOKE_CHECK)


@dataclass(frozen=True)
class PreflightSummary:
    report_path: Path
    passed: bool
    status: str
    failed_checks: tuple[str, ...]
    remaining: tuple[str, ...]
    director_url: str | None
    smoke_report: str | None
    signal_smoke_report: str | None
    vulcan_report: str | None
    latency_winner_target: str | None
    dry_run_command: str | None
    final_command: str | None

    @property
    def exit_code(self) -> int:
        if self.passed:
            return 0
        if self.status == "ready-for-final-smoke":
            return 2
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize Freyja Rev 2 readiness status.")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Specific rev2-readiness JSON report. Defaults to the newest report in certification/reports.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory to search when --report is not supplied.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a machine-readable JSON summary instead of text.",
    )
    return parser


def latest_readiness_report(report_dir: Path) -> Path:
    reports = sorted(report_dir.glob("*-rev2-readiness.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not reports:
        raise FileNotFoundError(f"No Rev 2 readiness reports found in {report_dir}")
    return reports[0]


def summarize_report(path: Path) -> PreflightSummary:
    payload = _load_report(path)
    checks = payload.get("checks", [])
    if not isinstance(checks, list):
        checks = []

    failed = tuple(
        str(check.get("name", "unknown"))
        for check in checks
        if isinstance(check, dict) and check.get("passed") is not True
    )
    passed = bool(payload.get("passed") is True)
    remaining = _remaining_work(checks, failed_checks=failed)
    status = _status(passed=passed, failed_checks=failed, remaining=remaining)
    dry_run_command = _handoff_command(payload, failed_checks=failed, send=False) if status == "ready-for-final-smoke" else None
    final_command = _handoff_command(payload, failed_checks=failed, send=True) if status == "ready-for-final-smoke" else None
    if final_command is not None:
        remaining = (
            f"Review dry-run first: {dry_run_command}",
            f"After approval, run: {final_command}",
        )
    return PreflightSummary(
        report_path=path,
        passed=passed,
        status=status,
        failed_checks=failed,
        remaining=remaining,
        director_url=_optional_str(payload.get("director_url")),
        smoke_report=_optional_str(payload.get("smoke_report")),
        signal_smoke_report=_optional_str(payload.get("signal_smoke_report")),
        vulcan_report=_optional_str(payload.get("vulcan_report")),
        latency_winner_target=_optional_str(payload.get("latency_winner_target")),
        dry_run_command=dry_run_command,
        final_command=final_command,
    )


def render_summary(summary: PreflightSummary) -> str:
    lines = [
        "Freyja Rev 2 preflight",
        f"Report: {summary.report_path}",
        f"Status: {summary.status}",
        f"Director: {summary.director_url or 'not recorded'}",
        f"Latency winner target: {summary.latency_winner_target or 'not recorded'}",
        f"iMessage smoke report: {summary.smoke_report or 'not supplied'}",
        f"Signal smoke report: {summary.signal_smoke_report or 'not supplied'}",
        f"Vulcan readiness report: {summary.vulcan_report or 'not supplied'}",
    ]
    if summary.failed_checks:
        lines.append("Failed checks:")
        lines.extend(f"- {name}" for name in summary.failed_checks)
    if summary.remaining:
        lines.append("Remaining:")
        lines.extend(f"- {item}" for item in summary.remaining)
    return "\n".join(lines)


def render_summary_json(summary: PreflightSummary) -> str:
    return json.dumps(
        {
            "report_path": str(summary.report_path),
            "passed": summary.passed,
            "status": summary.status,
            "exit_code": summary.exit_code,
            "failed_checks": list(summary.failed_checks),
            "remaining": list(summary.remaining),
            "director_url": summary.director_url,
            "smoke_report": summary.smoke_report,
            "signal_smoke_report": summary.signal_smoke_report,
            "vulcan_report": summary.vulcan_report,
            "latency_winner_target": summary.latency_winner_target,
            "dry_run_command": summary.dry_run_command,
            "final_command": summary.final_command,
        },
        indent=2,
        sort_keys=True,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = args.report or latest_readiness_report(args.report_dir)
        summary = summarize_report(report)
    except Exception as exc:
        print(f"Rev 2 preflight status failed: {exc}", file=sys.stderr)
        return 1
    print(render_summary_json(summary) if args.json else render_summary(summary))
    return summary.exit_code


def _load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def _remaining_work(checks: list[Any], *, failed_checks: tuple[str, ...]) -> tuple[str, ...]:
    remaining: list[str] = []
    if IMESSAGE_SMOKE_CHECK in failed_checks:
        smoke_status = _check_status(checks, IMESSAGE_SMOKE_CHECK)
        if "missing required --smoke-report" in smoke_status:
            remaining.append("Run scripts/rev2-readiness-bundle.py --imessage-live-smoke --yes after approval.")
        elif "does not prove a sent message" in smoke_status or "dry" in smoke_status.lower():
            remaining.append("Replace the iMessage dry-run smoke report with a sent live-smoke report.")
        else:
            remaining.append(f"Resolve {IMESSAGE_SMOKE_CHECK}: {smoke_status}")
    if SIGNAL_SMOKE_CHECK in failed_checks:
        smoke_status = _check_status(checks, SIGNAL_SMOKE_CHECK)
        if "missing required --signal-smoke-report" in smoke_status:
            remaining.append("Run scripts/rev2-readiness-bundle.py --signal-live-smoke --signal-yes after approval.")
        elif "does not prove a sent message" in smoke_status or "dry" in smoke_status.lower():
            remaining.append("Replace the Signal dry-run smoke report with a sent live-smoke report.")
        else:
            remaining.append(f"Resolve {SIGNAL_SMOKE_CHECK}: {smoke_status}")
    if VULCAN_CHECK in failed_checks:
        check = _check(checks, VULCAN_CHECK)
        details = check.get("details") if isinstance(check, dict) else {}
        not_ready = details.get("not_ready_model_profiles") if isinstance(details, dict) else None
        if isinstance(not_ready, list) and "vision" in not_ready:
            remaining.append("Install the configured Vulcan vision profile model, rerun scripts/vulcan-operator.py readiness, and attach it with --vulcan-report.")
        elif "missing required --vulcan-report" in _check_status(checks, VULCAN_CHECK):
            remaining.append("Run scripts/vulcan-operator.py readiness --output logs/vulcan-readiness.json and pass --vulcan-report.")
        else:
            remaining.append(f"Resolve {VULCAN_CHECK}: {_check_status(checks, VULCAN_CHECK)}")
    for name in failed_checks:
        if name not in SMOKE_CHECKS and name != VULCAN_CHECK:
            remaining.append(f"Resolve {name}.")
    return tuple(remaining)


def _status(*, passed: bool, failed_checks: tuple[str, ...], remaining: tuple[str, ...]) -> str:
    if passed:
        return "complete"
    if failed_checks and set(failed_checks).issubset(set(SMOKE_CHECKS)) and remaining:
        return "ready-for-final-smoke"
    return "not-ready"


def _check_status(checks: list[Any], name: str) -> str:
    for check in checks:
        if isinstance(check, dict) and check.get("name") == name:
            return str(check.get("status", "failed"))
    return "missing check details"


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _handoff_command(payload: dict[str, Any], *, failed_checks: tuple[str, ...], send: bool) -> str | None:
    director_url = _optional_str(payload.get("director_url"))
    certification_report = _optional_str(payload.get("certification_report"))
    benchmark_report = _optional_str(payload.get("benchmark_report"))
    memory_report = _optional_str(payload.get("memory_report"))
    approval_report = _optional_str(payload.get("approval_report"))
    vulcan_report = _optional_str(payload.get("vulcan_report"))
    latency_winner_target = _optional_str(payload.get("latency_winner_target"))
    smoke_report = _optional_str(payload.get("smoke_report"))
    signal_smoke_report = _optional_str(payload.get("signal_smoke_report"))
    connector_reports = payload.get("connector_reports")
    if not isinstance(connector_reports, list):
        connector_reports = []
    connector_reports = [item for item in connector_reports if isinstance(item, str) and item]
    if not all(
        (
            director_url,
            certification_report,
            benchmark_report,
            memory_report,
            approval_report,
            vulcan_report,
            latency_winner_target,
        )
    ):
        return None
    if not connector_reports:
        return None

    command = [
        "scripts/rev2-readiness-bundle.py",
        "--director-url",
        director_url,
        "--certification-report",
        certification_report,
        "--benchmark-report",
        benchmark_report,
    ]
    for connector_report in connector_reports:
        command.extend(["--connector-report", connector_report])
    command.extend(["--memory-report", memory_report, "--approval-report", approval_report, "--vulcan-report", vulcan_report])
    if IMESSAGE_SMOKE_CHECK in failed_checks:
        command.append("--imessage-live-smoke")
        if send:
            command.append("--yes")
    elif smoke_report:
        command.extend(["--smoke-report", smoke_report])
    if SIGNAL_SMOKE_CHECK in failed_checks:
        command.append("--signal-live-smoke")
        if send:
            command.append("--signal-yes")
    elif signal_smoke_report:
        command.extend(["--signal-smoke-report", signal_smoke_report])
    command.extend([
        "--require-smoke-report",
        "--require-signal-smoke-report",
        "--require-vulcan-report",
        "--latency-winner-target",
        latency_winner_target,
    ])
    return shlex.join(command)


def _check(checks: list[Any], name: str) -> dict[str, Any]:
    for check in checks:
        if isinstance(check, dict) and check.get("name") == name:
            return check
    return {}


if __name__ == "__main__":
    raise SystemExit(main())
