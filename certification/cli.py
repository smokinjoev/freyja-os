from __future__ import annotations

import argparse
import sys
from pathlib import Path

from certification import __version__
from certification.benchmark import (
    DEFAULT_BENCHMARK_DIR,
    BenchmarkTarget,
    build_benchmark_report,
    compare_benchmark_models,
    compare_reports,
    find_benchmark_report_by_commit,
    find_benchmark_report_with_models,
    load_report,
    render_compare_markdown,
    write_benchmark_report,
    write_compare_report,
)
from certification.reporter import DEFAULT_REPORT_DIR, write_reports
from certification.runner import OpenRouterCertificationProvider, OllamaCertificationProvider, list_suite_names, load_suite, run_suite_sync


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
        choices=("ollama", "openrouter"),
        action="append",
        default=None,
        help="Model provider to use. Repeat with --model in benchmark mode. Defaults to ollama.",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=None,
        help="Provider model override. Repeat with --provider in benchmark mode.",
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
        action="append",
        default=None,
        help="Suite or difficulty to run in benchmark mode. Repeat for multiple suites. Defaults to smoke.",
    )
    parser.add_argument(
        "--reports",
        nargs=2,
        type=Path,
        metavar=("LEFT", "RIGHT"),
        help="Two JSON report files to compare in compare mode.",
    )
    parser.add_argument(
        "--commits",
        nargs=2,
        metavar=("LEFT", "RIGHT"),
        help="Two git SHAs or prefixes to compare from benchmark history.",
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
        provider_name = _single_provider(args)
        provider = _provider(provider_name, _single_model(args))
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
    targets = _benchmark_targets(args)
    suite_names = args.benchmark_suite or ["smoke"]
    output_dir = DEFAULT_BENCHMARK_DIR if args.output_dir == DEFAULT_REPORT_DIR else args.output_dir
    reports_by_target = []
    try:
        suites = [load_suite(name) for name in suite_names]
        for target in targets:
            target_reports = []
            for suite in suites:
                provider = _provider(target.provider, target.model)
                report = run_suite_sync(suite=suite, provider=provider, router_mode=args.router_mode)
                target_reports.append(write_reports(report, output_dir=output_dir))
            reports_by_target.append((target, target_reports))
        benchmark_report = build_benchmark_report(reports_by_target, router_mode=args.router_mode)
        benchmark_report = write_benchmark_report(benchmark_report, output_dir=output_dir)
    except Exception as exc:
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        return 1

    markdown_path = benchmark_report.report_paths["markdown"]
    print(Path(markdown_path).read_text(encoding="utf-8"), end="")
    print(f"Benchmark Markdown report: {markdown_path}")
    print(f"Benchmark JSON report: {benchmark_report.report_paths['json']}")
    return 0


def _compare(args: argparse.Namespace) -> int:
    try:
        output_dir = DEFAULT_BENCHMARK_DIR if args.output_dir == DEFAULT_REPORT_DIR else args.output_dir
        if args.reports:
            comparison = compare_reports(load_report(args.reports[0]), load_report(args.reports[1]))
        elif args.commits:
            comparison = compare_reports(
                find_benchmark_report_by_commit(args.commits[0], output_dir),
                find_benchmark_report_by_commit(args.commits[1], output_dir),
            )
        elif args.models:
            models = [model.strip() for model in args.models.split(",") if model.strip()]
            if len(models) != 2:
                raise ValueError("Model comparison requires --models LEFT,RIGHT")
            source = find_benchmark_report_with_models(models[0], models[1], output_dir)
            comparison = compare_benchmark_models(source, models[0], models[1])
        else:
            print("Compare requires --reports LEFT RIGHT, --commits LEFT RIGHT, or --models LEFT,RIGHT.", file=sys.stderr)
            return 1
        paths = write_compare_report(comparison, output_dir=output_dir)
    except Exception as exc:
        print(f"Compare failed: {exc}", file=sys.stderr)
        return 1
    markdown = render_compare_markdown(comparison)
    print(markdown, end="")
    print(f"Compare Markdown report: {paths['markdown']}")
    print(f"Compare JSON report: {paths['json']}")
    return 0


def _provider(provider_name: str, model: str | None):
    if provider_name == "ollama":
        return OllamaCertificationProvider(model=model)
    if provider_name == "openrouter":
        return OpenRouterCertificationProvider(model=model)
    raise ValueError(f"Unsupported provider '{provider_name}'")


def _single_provider(args: argparse.Namespace) -> str:
    return (args.provider or ["ollama"])[-1]


def _single_model(args: argparse.Namespace) -> str | None:
    return (args.model or [None])[-1]


def _benchmark_targets(args: argparse.Namespace) -> list[BenchmarkTarget]:
    providers = args.provider or ["ollama"]
    if args.models:
        models = [model.strip() for model in args.models.split(",") if model.strip()]
        if len(providers) == 1:
            return [BenchmarkTarget(providers[0], model) for model in models]
        if len(providers) != len(models):
            raise ValueError("--models must have one model per repeated --provider or a single provider")
        return [BenchmarkTarget(provider, model) for provider, model in zip(providers, models, strict=True)]

    models = args.model or []
    if not models:
        return [BenchmarkTarget(provider, None) for provider in providers]
    if len(providers) == len(models):
        return [BenchmarkTarget(provider, model) for provider, model in zip(providers, models, strict=True)]
    if len(providers) == 1:
        return [BenchmarkTarget(providers[0], model) for model in models]
    raise ValueError("Benchmark requires matching repeated --provider and --model pairs")


if __name__ == "__main__":
    raise SystemExit(main())
