#!/usr/bin/env python3
"""Run the Freyja 5 source/smoke/readiness certification gauntlet."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Freyja 5 certification gauntlet.")
    parser.add_argument("--base-url", default=os.environ.get("FREYJA5_BASE_URL", "http://127.0.0.1:8500"))
    parser.add_argument("--token", default=os.environ.get("FREYJA_CONNECTOR_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--output-dir", type=Path, default=Path("certification/reports"))
    parser.add_argument("--agent-export", type=Path)
    parser.add_argument("--smoke-report", type=Path)
    parser.add_argument("--bundle-output", type=Path)
    parser.add_argument("--summary-output", type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--skip-smoke", action="store_true", help="Skip service smoke checks and use --smoke-report.")
    parser.add_argument("--skip-media", action="store_true", help="Pass through to freyja5-smoke.py.")
    parser.add_argument("--print-only", action="store_true", help="Print commands without running them.")
    return parser


def resolved_paths(args: argparse.Namespace) -> dict[str, Path]:
    output_dir = args.output_dir
    return {
        "agent_export": args.agent_export or output_dir / "freyja5-agent-definitions.json",
        "smoke_report": args.smoke_report or output_dir / "freyja5-smoke.json",
        "bundle_output": args.bundle_output or output_dir / "freyja5-readiness-bundle.json",
        "summary_output": args.summary_output or output_dir / "freyja5-gauntlet-summary.json",
    }


def build_export_command(args: argparse.Namespace, paths: dict[str, Path]) -> list[str]:
    return [
        args.python,
        "scripts/freyja5-export-agent-definitions.py",
        "--output",
        str(paths["agent_export"]),
    ]


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


def build_smoke_command(args: argparse.Namespace, paths: dict[str, Path]) -> list[str]:
    command = [
        args.python,
        "scripts/freyja5-smoke.py",
        "--base-url",
        args.base_url,
        "--timeout",
        str(args.timeout),
        "--output",
        str(paths["smoke_report"]),
    ]
    if args.token:
        command.extend(["--token", args.token])
    if args.skip_media:
        command.append("--skip-media")
    return command


def build_bundle_command(args: argparse.Namespace, paths: dict[str, Path], certification_report: Path) -> list[str]:
    return [
        args.python,
        "scripts/freyja5-readiness-bundle.py",
        "--certification-report",
        str(certification_report),
        "--smoke-report",
        str(paths["smoke_report"]),
        "--output",
        str(paths["bundle_output"]),
    ]


def build_preflight_command(args: argparse.Namespace, paths: dict[str, Path]) -> list[str]:
    return [
        args.python,
        "scripts/freyja5-preflight-status.py",
        "--report",
        str(paths["bundle_output"]),
        "--agent-export",
        str(paths["agent_export"]),
        "--json",
    ]


def command_plan(args: argparse.Namespace, certification_report: Path | None = None) -> list[list[str]]:
    paths = resolved_paths(args)
    planned = [build_export_command(args, paths), build_certification_command(args)]
    if not args.skip_smoke:
        planned.append(build_smoke_command(args, paths))
    if certification_report is not None:
        planned.extend(
            [
                build_bundle_command(args, paths, certification_report),
                build_preflight_command(args, paths),
            ]
        )
    return planned


def run_gauntlet(args: argparse.Namespace) -> dict[str, Any]:
    paths = resolved_paths(args)
    steps: list[dict[str, Any]] = []
    certification_report: Path | None = None

    export = _run_step("agent_export", build_export_command(args, paths), expected_codes={0})
    steps.append(export)
    if not export["ok"]:
        return _summary(paths=paths, steps=steps, preflight=None)

    certification = _run_step("certification", build_certification_command(args), expected_codes={0})
    certification_report = _extract_certification_json(certification.get("stdout", ""))
    certification["json_report"] = str(certification_report) if certification_report else None
    steps.append(certification)
    if not certification["ok"] or certification_report is None:
        return _summary(paths=paths, steps=steps, preflight=None)

    if args.skip_smoke:
        smoke = {
            "name": "smoke",
            "command": [],
            "exit_code": 0,
            "ok": paths["smoke_report"].exists(),
            "status": "skipped_existing_report" if paths["smoke_report"].exists() else "missing_existing_report",
        }
    else:
        smoke = _run_step("smoke", build_smoke_command(args, paths), expected_codes={0})
    steps.append(smoke)
    if not smoke["ok"]:
        return _summary(paths=paths, steps=steps, preflight=None)

    bundle = _run_step("readiness_bundle", build_bundle_command(args, paths, certification_report), expected_codes={0, 2})
    steps.append(bundle)
    if not bundle["ok"]:
        return _summary(paths=paths, steps=steps, preflight=None)

    preflight = _run_step("preflight", build_preflight_command(args, paths), expected_codes={0, 2})
    steps.append(preflight)
    payload = _load_json_from_stdout(preflight.get("stdout", "")) if preflight["ok"] else None
    return _summary(paths=paths, steps=steps, preflight=payload)


def _run_step(name: str, command: list[str], *, expected_codes: set[int]) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return {
        "name": name,
        "command": command,
        "exit_code": completed.returncode,
        "ok": completed.returncode in expected_codes,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _extract_certification_json(output: str) -> Path | None:
    for line in output.splitlines():
        if line.startswith("JSON report:"):
            return Path(line.split(":", 1)[1].strip())
    return None


def _load_json_from_stdout(output: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _summary(*, paths: dict[str, Path], steps: list[dict[str, Any]], preflight: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_type": "freyja5-certification-gauntlet",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "passed": bool(preflight and preflight.get("status") == "complete"),
        "source_ready": bool(preflight and preflight.get("source_ready") is True),
        "live_blocked": bool(preflight and preflight.get("live_blocked") is True),
        "preflight_status": preflight.get("status") if preflight else "not-run",
        "paths": {name: str(path) for name, path in paths.items()},
        "steps": [
            {
                "name": step["name"],
                "command": step["command"],
                "exit_code": step["exit_code"],
                "ok": step["ok"],
                **({"status": step["status"]} if "status" in step else {}),
                **({"json_report": step["json_report"]} if "json_report" in step else {}),
            }
            for step in steps
        ],
        "preflight": preflight,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = resolved_paths(args)
    if args.print_only:
        rendered = json.dumps(
            {"commands": command_plan(args), "paths": {name: str(path) for name, path in paths.items()}},
            indent=2,
            sort_keys=True,
        )
        print(rendered)
        return 0
    report = run_gauntlet(args)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    paths["summary_output"].parent.mkdir(parents=True, exist_ok=True)
    paths["summary_output"].write_text(rendered + "\n", encoding="utf-8")
    if report["passed"]:
        return 0
    if report["source_ready"] and report["live_blocked"]:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
