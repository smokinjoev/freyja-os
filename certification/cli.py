from __future__ import annotations

import argparse
import sys
from pathlib import Path

from certification import __version__
from certification.reporter import DEFAULT_REPORT_DIR, write_reports
from certification.runner import OllamaCertificationProvider, list_suite_names, load_suite, run_suite_sync


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="freyja-certify",
        description="Run Freyja OS certification suites and write Markdown and JSON reports.",
    )
    parser.add_argument(
        "suite",
        nargs="?",
        default="smoke",
        help="Certification suite name to run. Defaults to smoke.",
    )
    parser.add_argument(
        "--provider",
        choices=("ollama",),
        default="ollama",
        help="Model provider to use. Defaults to ollama.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Provider model override. Defaults to the configured Ollama chat model.",
    )
    parser.add_argument(
        "--router-mode",
        default="default",
        help="Router mode label recorded in reports. Defaults to default.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory for timestamped Markdown and JSON reports. Defaults to certification/reports/.",
    )
    parser.add_argument(
        "--list-suites",
        action="store_true",
        help="List available certification suites and exit.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_suites:
        for suite_name in list_suite_names():
            print(suite_name)
        return 0

    try:
        suite = load_suite(args.suite)
        provider = OllamaCertificationProvider(model=args.model)
        report = run_suite_sync(suite=suite, provider=provider, router_mode=args.router_mode)
        report = write_reports(report, output_dir=args.output_dir)
    except Exception as exc:
        print(f"Certification failed: {exc}", file=sys.stderr)
        return 1

    print(f"Suite: {report.metadata.suite_name}")
    print(f"Provider: {report.metadata.provider}")
    print(f"Model: {report.metadata.model}")
    print(f"Overall score: {report.metadata.overall_score:.3f}")
    print(f"Markdown report: {report.report_paths['markdown']}")
    print(f"JSON report: {report.report_paths['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
