#!/usr/bin/env python3
"""Assemble and run the strict Freyja Rev 2 readiness gate."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the final Freyja Rev 2 readiness gate with the required artifact bundle."
    )
    parser.add_argument("--director-url", required=True)
    parser.add_argument("--certification-report", required=True, type=Path)
    parser.add_argument("--benchmark-report", type=Path)
    parser.add_argument("--connector-report", required=True, type=Path, action="append")
    parser.add_argument("--approval-report", required=True, type=Path)
    parser.add_argument("--smoke-report", type=Path)
    parser.add_argument("--signal-smoke-report", type=Path)
    parser.add_argument(
        "--imessage-live-smoke",
        action="store_true",
        help="Run the iMessage live-smoke operator step before readiness. Dry-run unless --yes is present.",
    )
    parser.add_argument(
        "--imessage-smoke-output",
        type=Path,
        help=(
            "JSON report path for --imessage-live-smoke. Defaults to "
            "imessage-live-smoke-dry-run.json without --yes and imessage-live-smoke-sent.json with --yes."
        ),
    )
    parser.add_argument(
        "--imessage-smoke-recipient",
        help="Allowlisted iMessage smoke recipient. Defaults to the first configured recipient.",
    )
    parser.add_argument(
        "--imessage-smoke-text",
        default="Freyja 2.0 live smoke test.",
        help="Message text for --imessage-live-smoke.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually send the iMessage live smoke when --imessage-live-smoke is present.",
    )
    parser.add_argument(
        "--signal-live-smoke",
        action="store_true",
        help="Run the Signal live-smoke operator step before readiness. Dry-run unless --signal-yes is present.",
    )
    parser.add_argument(
        "--signal-smoke-output",
        type=Path,
        help=(
            "JSON report path for --signal-live-smoke. Defaults to "
            "signal-live-smoke-dry-run.json without --signal-yes and signal-live-smoke-sent.json with --signal-yes."
        ),
    )
    parser.add_argument(
        "--signal-smoke-recipient",
        help="Allowlisted Signal smoke recipient. Defaults to the first configured recipient.",
    )
    parser.add_argument(
        "--signal-smoke-text",
        default="Freyja 2.0 Signal live smoke test.",
        help="Message text for --signal-live-smoke.",
    )
    parser.add_argument(
        "--signal-yes",
        action="store_true",
        help="Actually send the Signal live smoke when --signal-live-smoke is present.",
    )
    parser.add_argument(
        "--require-smoke-report",
        action="store_true",
        help="Require --smoke-report and fail final readiness when no sent iMessage smoke report is supplied.",
    )
    parser.add_argument(
        "--require-signal-smoke-report",
        action="store_true",
        help="Require --signal-smoke-report and fail final readiness when no sent Signal smoke report is supplied.",
    )
    parser.add_argument("--latency-winner-target", required=True)
    parser.add_argument("--required-provider-profile", action="append", default=None)
    parser.add_argument("--required-model-profile", action="append", default=None)
    parser.add_argument("--memory-report", type=Path)
    parser.add_argument("--memory-db", type=Path)
    parser.add_argument("--vulcan-report", type=Path)
    parser.add_argument(
        "--require-vulcan-report",
        action="store_true",
        help="Require a passing Vulcan operator readiness report for final readiness.",
    )
    parser.add_argument(
        "--benchmark-probe",
        action="store_true",
        help="Generate a Rev 2 latency benchmark report from the live Director before readiness.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("certification/reports"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="HTTP timeout in seconds for live Rev 2 probes.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the commands that would run without executing them.",
    )
    return parser


def build_smoke_command(args: argparse.Namespace) -> list[str] | None:
    if not args.imessage_live_smoke:
        return None
    smoke_output = _imessage_smoke_output(args)
    command = [
        args.python,
        "scripts/imessage-operator.py",
        "live-smoke",
        "--text",
        args.imessage_smoke_text,
        "--output",
        str(smoke_output),
    ]
    if args.imessage_smoke_recipient:
        command.extend(["--recipient", args.imessage_smoke_recipient])
    command.append("--yes" if args.yes else "--dry-run")
    return command


def build_signal_smoke_command(args: argparse.Namespace) -> list[str] | None:
    if not args.signal_live_smoke:
        return None
    smoke_output = _signal_smoke_output(args)
    command = [
        args.python,
        "scripts/signal-operator.py",
        "live-smoke",
        "--text",
        args.signal_smoke_text,
        "--output",
        str(smoke_output),
    ]
    if args.signal_smoke_recipient:
        command.extend(["--recipient", args.signal_smoke_recipient])
    command.append("--yes" if args.signal_yes else "--dry-run")
    return command


def build_commands(args: argparse.Namespace) -> list[list[str]]:
    memory_report = args.memory_report
    benchmark_report = args.benchmark_report
    commands: list[list[str]] = []
    if benchmark_report is None:
        if not args.benchmark_probe:
            raise ValueError("Provide --benchmark-report or --benchmark-probe.")
        benchmark_output_dir = Path("certification/benchmarks")
        commands.append(
            [
                args.python,
                "-m",
                "certification.cli",
                "rev2-latency-probe",
                "--director-url",
                args.director_url,
                "--output-dir",
                str(benchmark_output_dir),
                "--timeout",
                str(args.timeout),
            ]
        )
        benchmark_report = benchmark_output_dir / "<latest-rev2-latency-probe-benchmark>.json"
    if memory_report is None:
        if args.memory_db is None:
            raise ValueError("Provide --memory-report or --memory-db.")
        commands.append(
            [
                args.python,
                "-m",
                "certification.cli",
                "rev2-memory-audit",
                "--memory-db",
                str(args.memory_db),
                "--output-dir",
                str(args.output_dir),
            ]
        )
        memory_report = args.output_dir / "<latest-rev2-memory-provenance>.json"

    readiness = [
        args.python,
        "-m",
        "certification.cli",
        "rev2-readiness",
        "--director-url",
        args.director_url,
        "--certification-report",
        str(args.certification_report),
        "--benchmark-report",
        str(benchmark_report),
        "--memory-report",
        str(memory_report),
        "--approval-report",
        str(args.approval_report),
        "--latency-winner-target",
        args.latency_winner_target,
        "--output-dir",
        str(args.output_dir),
        "--timeout",
        str(args.timeout),
    ]
    smoke_report = args.smoke_report
    if args.imessage_live_smoke and args.yes:
        smoke_report = _imessage_smoke_output(args)
    if smoke_report is not None:
        readiness.extend(["--smoke-report", str(smoke_report)])
    signal_smoke_report = args.signal_smoke_report
    if args.signal_live_smoke and args.signal_yes:
        signal_smoke_report = _signal_smoke_output(args)
    if signal_smoke_report is not None:
        readiness.extend(["--signal-smoke-report", str(signal_smoke_report)])
    if args.require_smoke_report:
        readiness.append("--require-smoke-report")
    if args.require_signal_smoke_report:
        readiness.append("--require-signal-smoke-report")
    if args.vulcan_report is not None:
        readiness.extend(["--vulcan-report", str(args.vulcan_report)])
    if args.require_vulcan_report:
        readiness.append("--require-vulcan-report")
    for connector_report in args.connector_report:
        readiness.extend(["--connector-report", str(connector_report)])
    for profile_id in args.required_provider_profile or ():
        readiness.extend(["--required-provider-profile", profile_id])
    for profile_id in args.required_model_profile or ():
        readiness.extend(["--required-model-profile", profile_id])
    commands.append(readiness)
    return commands


def _imessage_smoke_output(args: argparse.Namespace) -> Path:
    if args.imessage_smoke_output is not None:
        return args.imessage_smoke_output
    filename = "imessage-live-smoke-sent.json" if args.yes else "imessage-live-smoke-dry-run.json"
    return Path("certification/reports") / filename


def _signal_smoke_output(args: argparse.Namespace) -> Path:
    if args.signal_smoke_output is not None:
        return args.signal_smoke_output
    filename = "signal-live-smoke-sent.json" if args.signal_yes else "signal-live-smoke-dry-run.json"
    return Path("certification/reports") / filename


def _extract_json_report(output: str, *, prefix: str = "JSON report:") -> str:
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    raise ValueError("Could not find JSON report path in command output.")


def _print_command(command: list[str]) -> None:
    print(shlex.join(command), flush=True)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        smoke_command = build_smoke_command(args)
        signal_smoke_command = build_signal_smoke_command(args)
        commands = build_commands(args)
    except Exception as exc:
        print(f"Rev 2 readiness bundle failed: {exc}", file=sys.stderr)
        return 1

    if smoke_command is not None:
        _print_command(smoke_command)
        if not args.print_only:
            completed = subprocess.run(smoke_command)
            if completed.returncode != 0:
                return completed.returncode
            if not args.yes:
                print(
                    "iMessage live smoke dry-run complete; rerun with --yes to send and run final readiness.",
                    file=sys.stderr,
                )
                return 2
    if signal_smoke_command is not None:
        _print_command(signal_smoke_command)
        if not args.print_only:
            completed = subprocess.run(signal_smoke_command)
            if completed.returncode != 0:
                return completed.returncode
            if not args.signal_yes:
                print(
                    "Signal live smoke dry-run complete; rerun with --signal-yes to send and run final readiness.",
                    file=sys.stderr,
                )
                return 2

    if not args.print_only and args.benchmark_report is None and args.benchmark_probe:
        benchmark_command = next(command for command in commands if "rev2-latency-probe" in command)
        _print_command(benchmark_command)
        completed = subprocess.run(benchmark_command, text=True, capture_output=True)
        print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        try:
            benchmark_report = _extract_json_report(completed.stdout, prefix="Benchmark JSON report:")
        except Exception as exc:
            print(f"Rev 2 readiness bundle failed: {exc}", file=sys.stderr)
            return completed.returncode or 1
        readiness = next(command for command in commands if "rev2-readiness" in command)
        benchmark_index = readiness.index("--benchmark-report") + 1
        readiness[benchmark_index] = benchmark_report

    if not args.print_only and args.memory_report is None:
        memory_command = next(command for command in commands if "rev2-memory-audit" in command)
        _print_command(memory_command)
        completed = subprocess.run(memory_command, text=True, capture_output=True)
        print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
        if completed.returncode != 0:
            return completed.returncode
        try:
            memory_report = _extract_json_report(completed.stdout)
        except Exception as exc:
            print(f"Rev 2 readiness bundle failed: {exc}", file=sys.stderr)
            return 1
        readiness = next(command for command in commands if "rev2-readiness" in command)
        memory_index = readiness.index("--memory-report") + 1
        readiness[memory_index] = memory_report

    for command in commands:
        if not args.print_only and "rev2-latency-probe" in command:
            continue
        if not args.print_only and "rev2-memory-audit" in command:
            continue
        _print_command(command)
        if args.print_only:
            continue
        completed = subprocess.run(command)
        if completed.returncode != 0:
            return completed.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
