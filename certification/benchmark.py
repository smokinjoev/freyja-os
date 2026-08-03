from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from certification.models import CertificationReport


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


def benchmark_row(report: CertificationReport) -> BenchmarkRow:
    latency = 0.0
    tokens = 0
    cost = 0.0
    saw_cost = False
    for case in report.cases:
        context = case.runtime_context
        latency += float(context.get("timing", {}).get("duration_ms", 0.0))
        tokens += sum(int(value) for value in context.get("token_counts", {}).values())
        if context.get("cost") is not None:
            saw_cost = True
            cost += float(context["cost"])
    return BenchmarkRow(
        provider=report.metadata.provider,
        model=report.metadata.model,
        score=report.metadata.overall_score,
        latency_ms=latency,
        token_usage=tokens,
        failures=sum(1 for case in report.cases if not case.passed),
        cost=cost if saw_cost else None,
    )


def render_benchmark_markdown(rows: list[BenchmarkRow]) -> str:
    lines = [
        "# Certification Benchmark",
        "",
        "| Provider | Model | Score | Latency ms | Tokens | Failures | Cost |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        cost = "" if row.cost is None else f"{row.cost:.4f}"
        lines.append(
            f"| {row.provider} | {row.model} | {row.score * 100:.1f}% | "
            f"{row.latency_ms:.1f} | {row.token_usage} | {row.failures} | {cost} |"
        )
    return "\n".join(lines) + "\n"


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def compare_reports(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
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
        "left": {"provider": left_meta["provider"], "model": left_meta["model"], "score": left_meta["overall_score"]},
        "right": {"provider": right_meta["provider"], "model": right_meta["model"], "score": right_meta["overall_score"]},
        "score_delta": right_meta["overall_score"] - left_meta["overall_score"],
        "latency_delta": right_meta["execution_time"] - left_meta["execution_time"],
        "regressions": regressions,
        "improvements": improvements,
    }


def render_compare_markdown(comparison: dict[str, Any]) -> str:
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
