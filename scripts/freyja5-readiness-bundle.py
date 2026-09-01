#!/usr/bin/env python3
"""Assemble Freyja 5 architecture certification and side-by-side smoke evidence."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _ensure_checkout_src_on_path() -> None:
    src_path = Path(__file__).resolve().parents[1] / "src"
    if src_path.exists() and str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


_ensure_checkout_src_on_path()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run or validate the Freyja 5 readiness evidence bundle.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8500")
    parser.add_argument("--token", default="")
    parser.add_argument("--certification-report", type=Path)
    parser.add_argument("--smoke-report", type=Path)
    parser.add_argument("--output", type=Path, default=Path("certification/reports/freyja5-readiness-bundle.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("certification/reports"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--run-certification", action="store_true")
    parser.add_argument("--run-smoke", action="store_true")
    parser.add_argument("--skip-media", action="store_true")
    parser.add_argument("--print-only", action="store_true")
    return parser


def build_certification_command(args: argparse.Namespace) -> list[str]:
    return [
        args.python,
        "-m",
        "certification.cli",
        "routing/freyja5_architecture",
        "--provider",
        "freyja5",
        "--output-dir",
        str(args.output_dir),
    ]


def build_smoke_command(args: argparse.Namespace) -> list[str]:
    output = args.smoke_report or args.output_dir / "freyja5-smoke.json"
    command = [
        args.python,
        "scripts/freyja5-smoke.py",
        "--base-url",
        args.base_url,
        "--timeout",
        str(args.timeout),
        "--output",
        str(output),
    ]
    if args.token:
        command.extend(["--token", args.token])
    if args.skip_media:
        command.append("--skip-media")
    return command


def _extract_json_report(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("JSON report:"):
            return line.split(":", 1)[1].strip()
    raise ValueError("Could not find certification JSON report path in command output.")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _certification_check(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"name": "freyja5-certification-report", "ok": False, "status": "not supplied"}
    try:
        payload = _load_json(path)
    except Exception as exc:  # noqa: BLE001 - report should preserve failure class
        return {"name": "freyja5-certification-report", "ok": False, "status": type(exc).__name__, "path": str(path)}
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    suite = metadata.get("suite_name") or metadata.get("suite") or payload.get("suite_name")
    score = metadata.get("overall_score") if metadata.get("overall_score") is not None else payload.get("overall_score")
    if score is None:
        score = payload.get("average_score")
    target_matrix_evidence = _has_freyja5_certification_evidence(payload)
    trace_evidence = _has_freyja5_trace_evidence(payload)
    ok = (
        suite == "freyja5-architecture"
        and payload.get("passed") is True
        and float(score or 0.0) >= 1.0
        and target_matrix_evidence
        and trace_evidence
    )
    return {
        "name": "freyja5-certification-report",
        "ok": ok,
        "status": "passed" if ok else "failed",
        "path": str(path),
        "suite": suite,
        "passed": payload.get("passed"),
        "overall_score": score,
        "target_matrix_evidence": target_matrix_evidence,
        "trace_evidence": trace_evidence,
    }


def _has_freyja5_certification_evidence(payload: dict[str, Any]) -> bool:
    cases = payload.get("cases") if isinstance(payload.get("cases"), list) else []
    for case in cases:
        if not isinstance(case, dict):
            continue
        runtime_context = case.get("runtime_context") if isinstance(case.get("runtime_context"), dict) else {}
        rev2_evidence = (
            runtime_context.get("rev2_evidence") if isinstance(runtime_context.get("rev2_evidence"), dict) else {}
        )
        certification = (
            rev2_evidence.get("freyja5_certification")
            if isinstance(rev2_evidence.get("freyja5_certification"), dict)
            else {}
        )
        targets = certification.get("targets") if isinstance(certification.get("targets"), list) else []
        target_ids = {
            str(target.get("target"))
            for target in targets
            if isinstance(target, dict)
            and target.get("target")
            and target.get("case")
            and target.get("name")
            and target.get("proves")
        }
        if target_ids == {"A", "B", "C", "D", "E", "F", "G"}:
            return True
    return False


def _has_freyja5_trace_evidence(payload: dict[str, Any]) -> bool:
    required_fields = {
        "trace_id",
        "channel",
        "resolved_user",
        "authenticated_subject",
        "actor_principal",
        "memory_scopes",
        "agent",
        "requested_route",
        "actual_endpoint",
        "actual_provider",
        "actual_model",
        "actual_runtime",
        "selected_tools",
        "tool_calls",
        "delegation",
        "machine",
        "latency_ms",
        "failures",
        "fallbacks",
        "inference_status",
        "egress_state",
    }
    cases = payload.get("cases") if isinstance(payload.get("cases"), list) else []
    for case in cases:
        if not isinstance(case, dict):
            continue
        runtime_context = case.get("runtime_context") if isinstance(case.get("runtime_context"), dict) else {}
        rev2_evidence = (
            runtime_context.get("rev2_evidence") if isinstance(runtime_context.get("rev2_evidence"), dict) else {}
        )
        trace = rev2_evidence.get("freyja5_trace_summary")
        if isinstance(trace, dict) and required_fields <= set(trace):
            return True
    return False


def _smoke_check(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"name": "freyja5-smoke-report", "ok": False, "status": "not supplied"}
    try:
        payload = _load_json(path)
    except Exception as exc:  # noqa: BLE001 - report should preserve failure class
        return {"name": "freyja5-smoke-report", "ok": False, "status": type(exc).__name__, "path": str(path)}
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    names = [str(check.get("name")) for check in checks if isinstance(check, dict) and check.get("name")]
    readiness_evidence = _has_freyja5_smoke_readiness_evidence(payload)
    ok = (
        payload.get("report_type") == "freyja5-smoke"
        and payload.get("passed") is True
        and readiness_evidence
    )
    return {
        "name": "freyja5-smoke-report",
        "ok": ok,
        "status": "passed" if ok else "failed",
        "path": str(path),
        "checks": names,
        "token_configured": payload.get("token_configured"),
        "readiness_architecture_evidence": readiness_evidence,
    }


def _has_freyja5_smoke_readiness_evidence(payload: dict[str, Any]) -> bool:
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    readiness = next(
        (check for check in checks if isinstance(check, dict) and check.get("name") == "readiness"),
        {},
    )
    if not isinstance(readiness, dict):
        return False
    return (
        readiness.get("readiness_ok") is True
        and readiness.get("openai_model") == "freyja-5"
        and readiness.get("webgui_default_model") == "agent-smith"
        and readiness.get("webgui_freyja5_opt_in") is True
        and readiness.get("mcp_hosts") == ["atlas", "iris"]
        and readiness.get("mcp_server_ids") == ["iris-apple-mcp", "atlas-household-mcp", "atlas-media-mcp"]
        and readiness.get("certification_targets") == ["A", "B", "C", "D", "E", "F", "G"]
    )


def _blocker_check() -> dict[str, Any]:
    from freyja.freyja5_config import freyja5_live_blocker_evidence

    evidence = freyja5_live_blocker_evidence()
    blockers = evidence.get("joe_required") if isinstance(evidence.get("joe_required"), list) else []
    return {
        "name": "freyja5-live-blockers",
        "ok": not blockers,
        "status": "blocked" if blockers else "passed",
        "source": evidence.get("source"),
        "remaining": [blocker.get("id") for blocker in blockers if isinstance(blocker, dict)],
        "blockers": [
            {
                "id": blocker.get("id"),
                "component": blocker.get("component"),
                "requires": blocker.get("requires") if isinstance(blocker.get("requires"), list) else [],
                "next_actions": blocker.get("next_actions") if isinstance(blocker.get("next_actions"), list) else [],
            }
            for blocker in blockers
            if isinstance(blocker, dict)
        ],
    }


def build_report(*, certification_report: Path | None, smoke_report: Path | None) -> dict[str, Any]:
    checks = [_certification_check(certification_report), _smoke_check(smoke_report), _blocker_check()]
    hard_checks = [check for check in checks if check["name"] != "freyja5-live-blockers"]
    live_blockers = next(check for check in checks if check["name"] == "freyja5-live-blockers")
    return {
        "schema_version": "1.0",
        "report_type": "freyja5-readiness-bundle",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "passed": all(check.get("ok") is True for check in hard_checks) and live_blockers.get("ok") is True,
        "source_ready": all(check.get("ok") is True for check in hard_checks),
        "live_blocked": live_blockers.get("ok") is not True,
        "checks": checks,
    }


def _print_command(command: list[str]) -> None:
    print(shlex.join(command), flush=True)


def _write_report(path: Path, report: dict[str, Any]) -> None:
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    certification_report = args.certification_report
    smoke_report = args.smoke_report

    if args.run_certification:
        command = build_certification_command(args)
        _print_command(command)
        if not args.print_only:
            completed = subprocess.run(command, text=True, capture_output=True)
            print(completed.stdout, end="")
            if completed.stderr:
                print(completed.stderr, end="", file=sys.stderr)
            if completed.returncode != 0:
                return completed.returncode
            certification_report = Path(_extract_json_report(completed.stdout))

    if args.run_smoke:
        command = build_smoke_command(args)
        _print_command(command)
        if not args.print_only:
            completed = subprocess.run(command)
            if completed.returncode != 0:
                return completed.returncode
            smoke_report = args.smoke_report or args.output_dir / "freyja5-smoke.json"

    if args.print_only:
        return 0

    report = build_report(certification_report=certification_report, smoke_report=smoke_report)
    _write_report(args.output, report)
    return 0 if report["passed"] else 2 if report["source_ready"] and report["live_blocked"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
