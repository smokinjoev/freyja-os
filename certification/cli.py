from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _ensure_checkout_src_on_path() -> None:
    src_path = Path(__file__).resolve().parents[1] / "src"
    if src_path.exists() and str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


_ensure_checkout_src_on_path()

from certification import __version__
from certification.approval_exercise import run_approval_exercise, write_approval_exercise_report
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
from certification.latency_probe import build_latency_probe_report
from certification.reporter import DEFAULT_REPORT_DIR, write_reports
from certification.memory_audit import audit_memory_provenance, write_memory_audit_report
from certification.rev2_readiness import (
    DEFAULT_REQUIRED_MODEL_PROFILES,
    DEFAULT_REQUIRED_PROVIDER_PROFILES,
    run_readiness_probe,
    write_readiness_report,
)
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
        help="Certification suite, category/name, difficulty, 'all', 'benchmark', 'compare', 'rev2-readiness', 'rev2-memory-audit', 'rev2-approval-exercise', or 'rev2-latency-probe'. Defaults to smoke gauntlet.",
    )
    parser.add_argument(
        "--provider",
        choices=("ollama", "local_reasoning", "openrouter"),
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
    parser.add_argument(
        "--director-url",
        default="http://localhost:8000",
        help="Director base URL for rev2-readiness. Defaults to http://localhost:8000.",
    )
    parser.add_argument(
        "--certification-report",
        type=Path,
        default=None,
        help="Rev 2 certification JSON report to include in rev2-readiness evidence.",
    )
    parser.add_argument(
        "--benchmark-report",
        type=Path,
        default=None,
        help="Benchmark JSON report to include in rev2-readiness latency evidence.",
    )
    parser.add_argument(
        "--connector-report",
        type=Path,
        action="append",
        default=None,
        help="Messaging production-check JSON report to include in rev2-readiness evidence. Repeat for multiple reports.",
    )
    parser.add_argument(
        "--memory-report",
        type=Path,
        default=None,
        help="Memory provenance audit JSON report to include in rev2-readiness evidence.",
    )
    parser.add_argument(
        "--approval-report",
        type=Path,
        default=None,
        help="Consequential-action approval exercise JSON report to include in rev2-readiness evidence.",
    )
    parser.add_argument(
        "--vulcan-report",
        type=Path,
        default=None,
        help="Vulcan operator readiness JSON report to include in rev2-readiness evidence.",
    )
    parser.add_argument(
        "--smoke-report",
        type=Path,
        default=None,
        help="iMessage live-smoke JSON report to include in rev2-readiness evidence.",
    )
    parser.add_argument(
        "--signal-smoke-report",
        type=Path,
        default=None,
        help="Signal live-smoke JSON report to include in rev2-readiness evidence.",
    )
    parser.add_argument(
        "--require-smoke-report",
        action="store_true",
        help="Require a non-dry-run iMessage live-smoke report for final rev2-readiness.",
    )
    parser.add_argument(
        "--require-signal-smoke-report",
        action="store_true",
        help="Require a non-dry-run Signal live-smoke report for final rev2-readiness.",
    )
    parser.add_argument(
        "--require-vulcan-report",
        action="store_true",
        help="Require a passing Vulcan operator readiness report for final rev2-readiness.",
    )
    parser.add_argument(
        "--memory-db",
        type=Path,
        default=None,
        help="Memory SQLite database path for rev2-memory-audit.",
    )
    parser.add_argument(
        "--approval-person-id",
        default="joe",
        help="Household person ID used for rev2-approval-exercise. Defaults to joe.",
    )
    parser.add_argument(
        "--latency-winner-target",
        default=None,
        help="Expected fastest benchmark target ID for rev2-readiness, such as ollama:qwen2.5:7b.",
    )
    parser.add_argument(
        "--required-provider-profile",
        action="append",
        default=None,
        help=(
            "Provider profile ID required by rev2-readiness. Repeat for multiple profiles. "
            "Defaults to the Rev 2 always-on profiles."
        ),
    )
    parser.add_argument(
        "--required-model-profile",
        action="append",
        default=None,
        help=(
            "Logical model profile required by rev2-readiness, such as fast, reason, code, or vision. "
            "Repeat for multiple profiles."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="HTTP timeout in seconds for rev2-readiness probes.",
    )
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

    if args.suite == "rev2-readiness":
        return _rev2_readiness(args)

    if args.suite == "rev2-memory-audit":
        return _rev2_memory_audit(args)

    if args.suite == "rev2-approval-exercise":
        return _rev2_approval_exercise(args)

    if args.suite == "rev2-latency-probe":
        return _rev2_latency_probe(args)

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
    print(f"Passing score: {report.passing_score:.3f}")
    print(f"Passed: {report.passed}")
    print(f"Mean generation speed: {_format_speed(report.speed_metrics.get('mean_generation_tokens_per_second'))}")
    print(f"Speed samples: {report.speed_metrics.get('measured_cases', 0)}")
    print(f"Markdown report: {report.report_paths['markdown']}")
    print(f"JSON report: {report.report_paths['json']}")
    return 0 if report.passed else 1


def _rev2_readiness(args: argparse.Namespace) -> int:
    try:
        report = run_readiness_probe(
            args.director_url,
            certification_report=args.certification_report,
            benchmark_report=args.benchmark_report,
            connector_reports=tuple(args.connector_report or ()),
            memory_report=args.memory_report,
            approval_report=args.approval_report,
            vulcan_report=args.vulcan_report,
            smoke_report=args.smoke_report,
            signal_smoke_report=args.signal_smoke_report,
            latency_winner_target=args.latency_winner_target,
            require_certification_report=True,
            require_benchmark_report=True,
            require_connector_report=True,
            require_memory_report=True,
            require_approval_report=True,
            require_vulcan_report=args.require_vulcan_report,
            require_smoke_report=args.require_smoke_report,
            require_signal_smoke_report=args.require_signal_smoke_report,
            require_latency_winner_target=True,
            required_provider_profiles=tuple(args.required_provider_profile or DEFAULT_REQUIRED_PROVIDER_PROFILES),
            required_model_profiles=tuple(args.required_model_profile or DEFAULT_REQUIRED_MODEL_PROFILES),
            timeout=args.timeout,
        )
        report = write_readiness_report(report, output_dir=args.output_dir)
    except Exception as exc:
        print(f"Rev 2 readiness failed: {exc}", file=sys.stderr)
        return 1

    print(f"Director URL: {report.director_url}")
    print(f"Overall readiness: {'passed' if report.passed else 'failed'}")
    for check in report.checks:
        print(f"{check.name}: {'passed' if check.passed else 'failed'} - {check.status}")
    print(f"Markdown report: {report.report_paths['markdown']}")
    print(f"JSON report: {report.report_paths['json']}")
    return 0 if report.passed else 1


def _rev2_memory_audit(args: argparse.Namespace) -> int:
    database_path = args.memory_db
    if database_path is None:
        print("Rev 2 memory audit requires --memory-db PATH.", file=sys.stderr)
        return 1
    try:
        report = audit_memory_provenance(database_path)
        report = write_memory_audit_report(report, output_dir=args.output_dir)
    except Exception as exc:
        print(f"Rev 2 memory audit failed: {exc}", file=sys.stderr)
        return 1

    print(f"Memory database: {report.database_path}")
    print(f"Shared memory rows: {report.shared_memory_count}")
    print(f"Overall memory provenance: {'passed' if report.passed else 'failed'}")
    print(f"Markdown report: {report.report_paths['markdown']}")
    print(f"JSON report: {report.report_paths['json']}")
    return 0 if report.passed else 1


def _rev2_approval_exercise(args: argparse.Namespace) -> int:
    try:
        report = run_approval_exercise(actor_person_id=args.approval_person_id)
        report = write_approval_exercise_report(report, output_dir=args.output_dir)
    except Exception as exc:
        print(f"Rev 2 approval exercise failed: {exc}", file=sys.stderr)
        return 1

    print(f"Actor person ID: {report.actor_person_id}")
    print(f"Approval exercise: {'passed' if report.passed else 'failed'}")
    print(f"Exercises: {len(report.exercises)}")
    print(f"Markdown report: {report.report_paths['markdown']}")
    print(f"JSON report: {report.report_paths['json']}")
    return 0 if report.passed else 1


def _rev2_latency_probe(args: argparse.Namespace) -> int:
    try:
        report = build_latency_probe_report(
            args.director_url,
            timeout=args.timeout,
            output_dir=args.output_dir,
            required_provider_profiles=tuple(args.required_provider_profile or DEFAULT_REQUIRED_PROVIDER_PROFILES),
        )
    except Exception as exc:
        print(f"Rev 2 latency probe failed: {exc}", file=sys.stderr)
        return 1

    winner = report.rankings.get("latency", [None])[0]
    failed = {
        entry.target.target_id: entry.metrics.failures
        for entry in report.entries
        if entry.metrics.failures
    }
    print(f"Director URL: {args.director_url}")
    print(f"Latency winner: {winner}")
    print(f"Targets: {len(report.entries)}")
    print(f"Failed targets: {failed or 'none'}")
    print(f"Benchmark Markdown report: {report.report_paths['markdown']}")
    print(f"Benchmark JSON report: {report.report_paths['json']}")
    return 0 if not failed and len(report.entries) >= 2 else 1


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
    if provider_name in {"ollama", "local_reasoning"}:
        from certification.runner import provider_for_name

        return provider_for_name(provider_name, model=model)
    if provider_name == "openrouter":
        return OpenRouterCertificationProvider(model=model)
    raise ValueError(f"Unsupported provider '{provider_name}'")


def _single_provider(args: argparse.Namespace) -> str:
    return (args.provider or ["ollama"])[-1]


def _single_model(args: argparse.Namespace) -> str | None:
    return (args.model or [None])[-1]


def _format_speed(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.3f} tokens/s"
    except (TypeError, ValueError):
        return "n/a"


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
