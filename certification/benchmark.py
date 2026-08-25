from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from certification import __version__
from certification.models import CertificationReport

DEFAULT_BENCHMARK_DIR = Path("certification/benchmarks")
BENCHMARK_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class BenchmarkTarget:
    provider: str
    model: str | None = None

    @property
    def target_id(self) -> str:
        model = self.model or "default"
        return f"{self.provider}:{model}"

    def to_dict(self) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "target_id": self.target_id}


@dataclass(frozen=True)
class BenchmarkMetrics:
    overall_score: float
    category_scores: dict[str, float]
    execution_time: float
    average_latency_ms: float
    token_usage: int
    tool_success_rate: float | None = None
    routing_correctness: float | None = None
    memory_correctness: float | None = None
    connector_correctness: float | None = None
    vision_correctness: float | None = None
    honesty_score: float | None = None
    tool_use_score: float | None = None
    routing_score: float | None = None
    memory_score: float | None = None
    vision_score: float | None = None
    failures: int = 0
    cost: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "category_scores": dict(self.category_scores),
            "execution_time": self.execution_time,
            "average_latency_ms": self.average_latency_ms,
            "token_usage": self.token_usage,
            "tool_success_rate": self.tool_success_rate,
            "routing_correctness": self.routing_correctness,
            "memory_correctness": self.memory_correctness,
            "connector_correctness": self.connector_correctness,
            "vision_correctness": self.vision_correctness,
            "honesty_score": self.honesty_score,
            "tool_use_score": self.tool_use_score,
            "routing_score": self.routing_score,
            "memory_score": self.memory_score,
            "vision_score": self.vision_score,
            "failures": self.failures,
            "cost": self.cost,
        }


@dataclass(frozen=True)
class BenchmarkEntry:
    target: BenchmarkTarget
    suite_names: tuple[str, ...]
    metrics: BenchmarkMetrics
    report_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "suite_names": list(self.suite_names),
            "metrics": self.metrics.to_dict(),
            "report_paths": list(self.report_paths),
        }


@dataclass(frozen=True)
class BenchmarkReport:
    timestamp: str
    git_sha: str
    branch: str
    working_tree: str
    router_mode: str
    suite_names: tuple[str, ...]
    entries: tuple[BenchmarkEntry, ...]
    rankings: dict[str, list[str]]
    router_data: dict[str, Any]
    report_paths: dict[str, str] = field(default_factory=dict)
    schema_version: str = BENCHMARK_SCHEMA_VERSION
    benchmark_cli_version: str = __version__

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "benchmark_cli_version": self.benchmark_cli_version,
            "timestamp": self.timestamp,
            "git_sha": self.git_sha,
            "branch": self.branch,
            "working_tree": self.working_tree,
            "router_mode": self.router_mode,
            "suite_names": list(self.suite_names),
            "entries": [entry.to_dict() for entry in self.entries],
            "rankings": {key: list(value) for key, value in self.rankings.items()},
            "router_data": self.router_data,
            "report_paths": dict(self.report_paths),
        }


@dataclass(frozen=True)
class BenchmarkRow:
    provider: str
    model: str
    score: float
    latency_ms: float
    token_usage: int
    failures: int
    cost: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "score": self.score,
            "latency_ms": self.latency_ms,
            "token_usage": self.token_usage,
            "failures": self.failures,
            "cost": self.cost,
        }


def build_benchmark_report(
    reports_by_target: list[tuple[BenchmarkTarget, list[CertificationReport]]],
    *,
    router_mode: str,
) -> BenchmarkReport:
    reports = [report for _, target_reports in reports_by_target for report in target_reports]
    first = reports[0] if reports else None
    entries = tuple(
        BenchmarkEntry(
            target=target,
            suite_names=tuple(report.metadata.suite_name for report in target_reports),
            metrics=benchmark_metrics(target_reports),
            report_paths=tuple(path for report in target_reports for path in _report_json_paths(report)),
        )
        for target, target_reports in reports_by_target
    )
    rankings = rank_benchmark_entries(entries)
    return BenchmarkReport(
        timestamp=datetime.now(UTC).isoformat(timespec="seconds"),
        git_sha=first.metadata.git_sha if first else "unknown",
        branch=first.metadata.branch if first else "unknown",
        working_tree=first.metadata.working_tree if first else "unknown",
        router_mode=router_mode,
        suite_names=tuple(dict.fromkeys(report.metadata.suite_name for report in reports)),
        entries=entries,
        rankings=rankings,
        router_data=router_consumable_data(entries, rankings),
    )


def benchmark_metrics(reports: list[CertificationReport]) -> BenchmarkMetrics:
    total_max = sum(case.max_score for report in reports for case in report.cases)
    total_score = sum(case.score for report in reports for case in report.cases)
    category_scores = _combined_category_scores(reports)
    latencies = [
        float(case.runtime_context.get("timing", {}).get("duration_ms", 0.0))
        for report in reports
        for case in report.cases
        if case.runtime_context.get("timing", {}).get("duration_ms") is not None
    ]
    token_usage = sum(_case_token_usage(case.runtime_context) for report in reports for case in report.cases)
    costs = [
        float(case.runtime_context["cost"])
        for report in reports
        for case in report.cases
        if case.runtime_context.get("cost") is not None
    ]
    return BenchmarkMetrics(
        overall_score=(total_score / total_max if total_max else 0.0),
        category_scores=category_scores,
        execution_time=sum(report.metadata.execution_time for report in reports),
        average_latency_ms=(sum(latencies) / len(latencies) if latencies else 0.0),
        token_usage=token_usage,
        tool_success_rate=_tool_success_rate(reports),
        routing_correctness=_verifier_rate(reports, "router"),
        memory_correctness=_verifier_rate(reports, "memory"),
        connector_correctness=_verifier_rate(reports, "connector"),
        vision_correctness=_verifier_rate(reports, "vision"),
        honesty_score=_suite_score(reports, "honesty"),
        tool_use_score=category_scores.get("tools"),
        routing_score=category_scores.get("routing"),
        memory_score=category_scores.get("memory"),
        vision_score=category_scores.get("vision"),
        failures=sum(1 for report in reports for case in report.cases if not case.passed),
        cost=sum(costs) if costs else None,
    )


def benchmark_row(report: CertificationReport) -> BenchmarkRow:
    metrics = benchmark_metrics([report])
    return BenchmarkRow(
        provider=report.metadata.provider,
        model=report.metadata.model,
        score=metrics.overall_score,
        latency_ms=metrics.average_latency_ms,
        token_usage=metrics.token_usage,
        failures=metrics.failures,
        cost=metrics.cost,
    )


def write_benchmark_report(
    report: BenchmarkReport,
    output_dir: Path = DEFAULT_BENCHMARK_DIR,
) -> BenchmarkReport:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _benchmark_stem(report.timestamp, report.suite_names)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    with_paths = BenchmarkReport(
        timestamp=report.timestamp,
        git_sha=report.git_sha,
        branch=report.branch,
        working_tree=report.working_tree,
        router_mode=report.router_mode,
        suite_names=report.suite_names,
        entries=report.entries,
        rankings=report.rankings,
        router_data=report.router_data,
        report_paths={"json": str(json_path), "markdown": str(md_path)},
        schema_version=report.schema_version,
        benchmark_cli_version=report.benchmark_cli_version,
    )
    json_path.write_text(json.dumps(with_paths.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_benchmark_report_markdown(with_paths), encoding="utf-8")
    return with_paths


def render_benchmark_report_markdown(report: BenchmarkReport) -> str:
    lines = [
        "# Freyja Benchmark Report",
        "",
        f"- Timestamp: {report.timestamp}",
        f"- Git SHA: {report.git_sha}",
        f"- Branch: {report.branch}",
        f"- Working tree: {report.working_tree}",
        f"- Router mode: {report.router_mode}",
        f"- Suites: {', '.join(report.suite_names)}",
        "",
        "## Comparison",
        "",
        _benchmark_table(report.entries),
        "",
        "## Rankings",
        "",
    ]
    for metric, target_ids in report.rankings.items():
        lines.append(f"- {metric}: {', '.join(target_ids) if target_ids else 'n/a'}")
    lines.extend(["", "## Regressions And Improvements", ""])
    lines.append("Use `freyja-certify compare --reports LEFT RIGHT` to generate delta reports between benchmark runs.")
    return "\n".join(lines) + "\n"


def render_benchmark_markdown(rows: list[BenchmarkRow]) -> str:
    entries = tuple(
        BenchmarkEntry(
            target=BenchmarkTarget(row.provider, row.model),
            suite_names=(),
            metrics=BenchmarkMetrics(
                overall_score=row.score,
                category_scores={},
                execution_time=0.0,
                average_latency_ms=row.latency_ms,
                token_usage=row.token_usage,
                failures=row.failures,
                cost=row.cost,
            ),
        )
        for row in rows
    )
    return "# Certification Benchmark\n\n" + _benchmark_table(entries) + "\n"


def rank_benchmark_entries(entries: tuple[BenchmarkEntry, ...]) -> dict[str, list[str]]:
    return {
        "overall_score": _rank(entries, lambda entry: entry.metrics.overall_score),
        "honesty": _rank(entries, lambda entry: entry.metrics.honesty_score),
        "tool_use": _rank(entries, lambda entry: entry.metrics.tool_use_score),
        "routing": _rank(entries, lambda entry: entry.metrics.routing_score),
        "memory": _rank(entries, lambda entry: entry.metrics.memory_score),
        "vision": _rank(entries, lambda entry: entry.metrics.vision_score),
        "latency": _rank(
            entries,
            lambda entry: (entry.metrics.failures, entry.metrics.average_latency_ms),
            reverse=False,
        ),
    }


def router_consumable_data(entries: tuple[BenchmarkEntry, ...], rankings: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "selection_inputs": {
            entry.target.target_id: {
                "provider": entry.target.provider,
                "model": entry.target.model,
                "overall_score": entry.metrics.overall_score,
                "category_scores": dict(entry.metrics.category_scores),
                "average_latency_ms": entry.metrics.average_latency_ms,
                "token_usage": entry.metrics.token_usage,
                "tool_success_rate": entry.metrics.tool_success_rate,
                "routing_correctness": entry.metrics.routing_correctness,
                "memory_correctness": entry.metrics.memory_correctness,
                "connector_correctness": entry.metrics.connector_correctness,
                "vision_correctness": entry.metrics.vision_correctness,
            }
            for entry in entries
        },
        "rankings": {key: list(value) for key, value in rankings.items()},
    }


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_benchmark_reports(directory: Path = DEFAULT_BENCHMARK_DIR) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*benchmark.json")):
        try:
            report = load_report(path)
        except Exception:
            continue
        if _is_benchmark_report(report):
            report["_source_path"] = str(path)
            reports.append(report)
    return reports


def find_benchmark_report_by_commit(commit: str, directory: Path = DEFAULT_BENCHMARK_DIR) -> dict[str, Any]:
    matches = [
        report
        for report in load_benchmark_reports(directory)
        if str(report.get("git_sha", "")).startswith(commit)
    ]
    if not matches:
        raise ValueError(f"No benchmark report found for commit '{commit}'")
    return sorted(matches, key=lambda report: str(report.get("timestamp", "")))[-1]


def find_benchmark_report_with_models(
    left_model: str,
    right_model: str,
    directory: Path = DEFAULT_BENCHMARK_DIR,
) -> dict[str, Any]:
    matches = [
        report
        for report in load_benchmark_reports(directory)
        if _find_entry(report, left_model) is not None and _find_entry(report, right_model) is not None
    ]
    if not matches:
        raise ValueError(f"No benchmark report found containing models '{left_model}' and '{right_model}'")
    return sorted(matches, key=lambda report: str(report.get("timestamp", "")))[-1]


def compare_benchmark_models(report: dict[str, Any], left_model: str, right_model: str) -> dict[str, Any]:
    left_entry = _find_entry(report, left_model)
    right_entry = _find_entry(report, right_model)
    if left_entry is None:
        raise ValueError(f"Model '{left_model}' not found in benchmark report")
    if right_entry is None:
        raise ValueError(f"Model '{right_model}' not found in benchmark report")
    left_metrics = left_entry["metrics"]
    right_metrics = right_entry["metrics"]
    return {
        "type": "model",
        "source": _benchmark_summary(report),
        "left": _entry_summary(left_entry),
        "right": _entry_summary(right_entry),
        "score_delta": float(right_metrics.get("overall_score", 0.0)) - float(left_metrics.get("overall_score", 0.0)),
        "latency_delta_ms": float(right_metrics.get("average_latency_ms", 0.0)) - float(left_metrics.get("average_latency_ms", 0.0)),
        "failure_delta": int(right_metrics.get("failures", 0)) - int(left_metrics.get("failures", 0)),
        "category_score_delta": _score_delta(
            left_metrics.get("category_scores", {}),
            right_metrics.get("category_scores", {}),
        ),
    }


def compare_reports(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    if _is_benchmark_report(left) or _is_benchmark_report(right):
        return compare_benchmark_reports(left, right)
    return compare_certification_reports(left, right)


def compare_certification_reports(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_meta = left["metadata"]
    right_meta = right["metadata"]
    left_cases = {f"{case['category']}/{case['suite_name']}/{case['name']}": case for case in left["cases"]}
    right_cases = {f"{case['category']}/{case['suite_name']}/{case['name']}": case for case in right["cases"]}
    regressions = []
    improvements = []
    for case_id in sorted(left_cases.keys() & right_cases.keys()):
        before = left_cases[case_id]
        after = right_cases[case_id]
        if before["passed"] and not after["passed"]:
            regressions.append(case_id)
        if not before["passed"] and after["passed"]:
            improvements.append(case_id)
    return {
        "type": "certification",
        "left": {"provider": left_meta["provider"], "model": left_meta["model"], "score": left_meta["overall_score"]},
        "right": {"provider": right_meta["provider"], "model": right_meta["model"], "score": right_meta["overall_score"]},
        "score_delta": right_meta["overall_score"] - left_meta["overall_score"],
        "latency_delta": right_meta["execution_time"] - left_meta["execution_time"],
        "regressions": regressions,
        "improvements": improvements,
    }


def compare_benchmark_reports(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_entries = {_entry_target_id(entry): entry for entry in left.get("entries", [])}
    right_entries = {_entry_target_id(entry): entry for entry in right.get("entries", [])}
    deltas: dict[str, Any] = {}
    regressions: list[str] = []
    improvements: list[str] = []
    for target_id in sorted(left_entries.keys() & right_entries.keys()):
        before = left_entries[target_id]["metrics"]
        after = right_entries[target_id]["metrics"]
        score_delta = float(after.get("overall_score", 0.0)) - float(before.get("overall_score", 0.0))
        latency_delta = float(after.get("average_latency_ms", 0.0)) - float(before.get("average_latency_ms", 0.0))
        deltas[target_id] = {
            "score_delta": score_delta,
            "latency_delta_ms": latency_delta,
            "failure_delta": int(after.get("failures", 0)) - int(before.get("failures", 0)),
            "category_score_delta": _score_delta(
                before.get("category_scores", {}),
                after.get("category_scores", {}),
            ),
        }
        if score_delta < 0:
            regressions.append(target_id)
        if score_delta > 0:
            improvements.append(target_id)
    return {
        "type": "benchmark",
        "left": _benchmark_summary(left),
        "right": _benchmark_summary(right),
        "target_deltas": deltas,
        "regressions": regressions,
        "improvements": improvements,
        "ranking_changes": _ranking_changes(left.get("rankings", {}), right.get("rankings", {})),
    }


def render_compare_markdown(comparison: dict[str, Any]) -> str:
    if comparison.get("type") == "model":
        return render_model_compare_markdown(comparison)
    if comparison.get("type") == "benchmark":
        return render_benchmark_compare_markdown(comparison)
    lines = [
        "# Certification Comparison",
        "",
        f"- Score delta: {comparison['score_delta'] * 100:.1f}%",
        f"- Latency delta: {comparison['latency_delta']:.3f}s",
        "",
        "## Regressions",
        "",
    ]
    lines.extend(f"- {case}" for case in comparison["regressions"] or ["None"])
    lines.extend(["", "## Improvements", ""])
    lines.extend(f"- {case}" for case in comparison["improvements"] or ["None"])
    return "\n".join(lines) + "\n"


def render_model_compare_markdown(comparison: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Model Benchmark Comparison",
            "",
            f"- Source: {comparison['source']['timestamp']} ({comparison['source']['git_sha']})",
            f"- Left: {comparison['left']['target_id']}",
            f"- Right: {comparison['right']['target_id']}",
            f"- Score delta: {comparison['score_delta'] * 100:.1f}%",
            f"- Latency delta: {comparison['latency_delta_ms']:.1f} ms",
            f"- Failure delta: {comparison['failure_delta']}",
            "",
            "## Category Score Deltas",
            "",
            *[
                f"- {category}: {delta * 100:.1f}%"
                for category, delta in comparison["category_score_delta"].items()
            ],
        ]
    ) + "\n"


def render_benchmark_compare_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# Benchmark Comparison",
        "",
        f"- Left: {comparison['left']['timestamp']} ({comparison['left']['git_sha']})",
        f"- Right: {comparison['right']['timestamp']} ({comparison['right']['git_sha']})",
        "",
        "| Target | Score Delta | Latency Delta ms | Failure Delta |",
        "| --- | ---: | ---: | ---: |",
    ]
    for target_id, delta in comparison["target_deltas"].items():
        lines.append(
            f"| {target_id} | {delta['score_delta'] * 100:.1f}% | "
            f"{delta['latency_delta_ms']:.1f} | {delta['failure_delta']} |"
        )
    lines.extend(["", "## Regressions", ""])
    lines.extend(f"- {target}" for target in comparison["regressions"] or ["None"])
    lines.extend(["", "## Improvements", ""])
    lines.extend(f"- {target}" for target in comparison["improvements"] or ["None"])
    lines.extend(["", "## Ranking Changes", ""])
    for metric, change in comparison["ranking_changes"].items():
        lines.append(f"- {metric}: {', '.join(change['before']) or 'n/a'} -> {', '.join(change['after']) or 'n/a'}")
    return "\n".join(lines) + "\n"


def write_compare_report(
    comparison: dict[str, Any],
    output_dir: Path = DEFAULT_BENCHMARK_DIR,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
    stem = f"{timestamp.replace(':', '').replace('-', '').replace('+', 'Z')}-compare"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_compare_markdown(comparison), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def _benchmark_table(entries: tuple[BenchmarkEntry, ...]) -> str:
    lines = [
        "| Provider | Model | Score | Honesty | Tools | Routing | Memory | Vision | Avg Latency ms | Tokens | Tool Success | Failures | Cost |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for entry in entries:
        metrics = entry.metrics
        cost = "" if metrics.cost is None else f"{metrics.cost:.4f}"
        lines.append(
            f"| {entry.target.provider} | {entry.target.model or 'default'} | "
            f"{_percent(metrics.overall_score)} | {_optional_percent(metrics.honesty_score)} | "
            f"{_optional_percent(metrics.tool_use_score)} | {_optional_percent(metrics.routing_score)} | "
            f"{_optional_percent(metrics.memory_score)} | {_optional_percent(metrics.vision_score)} | "
            f"{metrics.average_latency_ms:.1f} | {metrics.token_usage} | "
            f"{_optional_percent(metrics.tool_success_rate)} | {metrics.failures} | {cost} |"
        )
    return "\n".join(lines)


def _combined_category_scores(reports: list[CertificationReport]) -> dict[str, float]:
    totals: dict[str, tuple[float, float]] = {}
    for report in reports:
        for case in report.cases:
            earned, max_score = totals.get(case.category, (0.0, 0.0))
            totals[case.category] = (earned + case.score, max_score + case.max_score)
    return {
        category: (earned / max_score if max_score else 0.0)
        for category, (earned, max_score) in sorted(totals.items())
    }


def _suite_score(reports: list[CertificationReport], suite_name: str) -> float | None:
    cases = [case for report in reports for case in report.cases if case.suite_name == suite_name]
    if not cases:
        return None
    max_score = sum(case.max_score for case in cases)
    return sum(case.score for case in cases) / max_score if max_score else 0.0


def _verifier_rate(reports: list[CertificationReport], verifier: str) -> float | None:
    results = [
        result
        for report in reports
        for case in report.cases
        for result in case.verifier_results
        if result.get("verifier") == verifier
    ]
    if not results:
        return None
    return sum(1 for result in results if result.get("passed")) / len(results)


def _tool_success_rate(reports: list[CertificationReport]) -> float | None:
    calls = [
        call
        for report in reports
        for case in report.cases
        for call in case.runtime_context.get("tool_calls", [])
    ]
    if not calls:
        return None
    return sum(1 for call in calls if call.get("success") is True) / len(calls)


def _case_token_usage(context: dict[str, Any]) -> int:
    counts = context.get("token_counts", {})
    if "total_tokens" in counts:
        return int(counts["total_tokens"])
    if "total" in counts:
        return int(counts["total"])
    return sum(int(value) for value in counts.values())


def _rank(
    entries: tuple[BenchmarkEntry, ...],
    key_fn: Any,
    *,
    reverse: bool = True,
) -> list[str]:
    scored = [(entry, key_fn(entry)) for entry in entries]
    scored = [(entry, score) for entry, score in scored if score is not None]
    return [
        entry.target.target_id
        for entry, _ in sorted(scored, key=lambda item: (_rank_score(item[1]), item[0].target.target_id), reverse=reverse)
    ]


def _rank_score(score: Any) -> tuple[float, ...]:
    if isinstance(score, tuple):
        return tuple(float(item) for item in score)
    if isinstance(score, list):
        return tuple(float(item) for item in score)
    return (float(score),)


def _score_delta(left: dict[str, Any], right: dict[str, Any]) -> dict[str, float]:
    categories = set(left) | set(right)
    return {category: float(right.get(category, 0.0)) - float(left.get(category, 0.0)) for category in sorted(categories)}


def _ranking_changes(left: dict[str, Any], right: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    metrics = set(left) | set(right)
    return {
        metric: {"before": list(left.get(metric, [])), "after": list(right.get(metric, []))}
        for metric in sorted(metrics)
        if list(left.get(metric, [])) != list(right.get(metric, []))
    }


def _benchmark_summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": report.get("timestamp", "unknown"),
        "git_sha": report.get("git_sha", "unknown"),
        "branch": report.get("branch", "unknown"),
        "suite_names": list(report.get("suite_names", [])),
    }


def _entry_target_id(entry: dict[str, Any]) -> str:
    target = entry.get("target", {})
    return str(target.get("target_id") or f"{target.get('provider')}:{target.get('model') or 'default'}")


def _entry_summary(entry: dict[str, Any]) -> dict[str, Any]:
    target = entry.get("target", {})
    return {
        "provider": target.get("provider"),
        "model": target.get("model"),
        "target_id": _entry_target_id(entry),
        "metrics": dict(entry.get("metrics", {})),
    }


def _find_entry(report: dict[str, Any], model_or_target_id: str) -> dict[str, Any] | None:
    for entry in report.get("entries", []):
        target = entry.get("target", {})
        if model_or_target_id in {
            str(target.get("target_id", "")),
            str(target.get("model", "")),
            f"{target.get('provider')}:{target.get('model') or 'default'}",
        }:
            return entry
    return None


def _is_benchmark_report(report: dict[str, Any]) -> bool:
    return "entries" in report and "rankings" in report


def _report_json_paths(report: CertificationReport) -> list[str]:
    path = report.report_paths.get("json")
    return [path] if path else []


def _benchmark_stem(timestamp: str, suite_names: tuple[str, ...]) -> str:
    safe_timestamp = timestamp.replace(":", "").replace("-", "").replace("+", "Z")
    safe_suite = "-".join(suite_names) if suite_names else "benchmark"
    safe_suite = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in safe_suite)
    return f"{safe_timestamp}-{safe_suite}-benchmark"


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _optional_percent(value: float | None) -> str:
    return "" if value is None else _percent(value)
