from __future__ import annotations

import argparse
import sys
from pathlib import Path

from certification import __version__
from certification.benchmark import benchmark_row, compare_reports, load_report, render_benchmark_markdown, render_compare_markdown
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
        help="Certification suite, category/name, difficulty, 'all', 'benchmark', or 'compare'. Defaults to smoke gauntlet.",
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
    parser.add_argument(
        "--models",
        default=None,
        help="Comma-separated model list for benchmark mode.",
    )
    parser.add_argument(
        "--benchmark-suite",
        default="smoke",
        help="Suite or difficulty to run in benchmark mode. Defaults to smoke.",
    )
    parser.add_argument(
        "--reports",
        nargs=2,
        type=Path,
        metavar=("LEFT", "RIGHT"),
        help="Two JSON report files to compare in compare mode.",
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

    if args.suite == "benchmark":
        return _benchmark(args)

    if args.suite == "compare":
        return _compare(args)

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
    for category, score in sorted(report.category_scores.items()):
        print(f"{category.title()}: {score * 100:.1f}%")
    print(f"Overall score: {report.metadata.overall_score:.3f}")
    print(f"Markdown report: {report.report_paths['markdown']}")
    print(f"JSON report: {report.report_paths['json']}")
    return 0


def _benchmark(args: argparse.Namespace) -> int:
    models = [model.strip() for model in (args.models or args.model or "").split(",") if model.strip()]
    if not models:
        models = [None]
    rows = []
    output_dir = args.output_dir
    try:
        suite = load_suite(args.benchmark_suite)
        for model in models:
            provider = OllamaCertificationProvider(model=model)
            report = run_suite_sync(suite=suite, provider=provider, router_mode=args.router_mode)
            report = write_reports(report, output_dir=output_dir)
            rows.append(benchmark_row(report))
    except Exception as exc:
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        return 1

    markdown = render_benchmark_markdown(rows)
    path = output_dir / "benchmark.md"
    path.write_text(markdown, encoding="utf-8")
    print(markdown, end="")
    print(f"Benchmark report: {path}")
    return 0


def _compare(args: argparse.Namespace) -> int:
    if not args.reports:
        print("Compare requires --reports LEFT RIGHT.", file=sys.stderr)
        return 1
    try:
        comparison = compare_reports(load_report(args.reports[0]), load_report(args.reports[1]))
    except Exception as exc:
        print(f"Compare failed: {exc}", file=sys.stderr)
        return 1
    markdown = render_compare_markdown(comparison)
    print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
