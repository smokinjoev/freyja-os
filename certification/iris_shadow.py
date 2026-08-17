from __future__ import annotations

import argparse
import asyncio
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from certification.runner import DIFFICULTIES, load_gauntlet
from freyja.config import settings
from freyja.iris_router import IrisRouterClient
from freyja.ollama_client import OllamaClient
from freyja.openrouter_client import OpenRouterClient
from freyja.router import RouteRequest, router

DEFAULT_REPORT_DIR = Path(__file__).resolve().parent / "reports"


@dataclass(frozen=True)
class IrisComparison:
    case: str
    category: str
    difficulty: str
    director_provider: str
    director_model: str
    director_target: str | None
    final_provider: str
    final_model: str
    final_target: str | None
    response_ok: bool
    iris_ok: bool
    iris_tier: int | None
    iris_target: str | None
    iris_task: str | None
    iris_confidence: float | None
    iris_latency_ms: int | None
    iris_error: str | None
    agrees_with_director: bool
    agrees_with_final: bool


def provider_target(provider: str | None) -> str | None:
    if provider == "ollama":
        return "iris"
    if provider == "local_reasoning":
        return "local_heavy"
    if provider == "openrouter":
        return "cloud"
    if provider == "deterministic":
        return "deterministic"
    return None


async def compare_case(case: Any, iris: IrisRouterClient) -> IrisComparison:
    request_data: dict[str, Any] = {"prompt": case.prompt, "provider": "auto"}
    request_data.update(case.route_request)
    request_data["prompt"] = case.prompt
    request = RouteRequest(**request_data)

    director_decision, iris_result = await asyncio.gather(
        router.decide(request),
        iris.recommend(
            request.prompt,
            task_type=request.task_type,
            privacy=request.privacy,
            tools_required=request.tools_required,
            context_size=request.context_size,
        ),
    )

    execution = await router.execute(request)
    final_provider = execution.decision.provider
    final_model = execution.decision.model

    recommendation = iris_result.recommendation
    iris_target = recommendation.preferred_target if recommendation else None
    director_target = provider_target(director_decision.provider)
    final_target = provider_target(final_provider)

    return IrisComparison(
        case=case.name,
        category=case.category,
        difficulty=case.difficulty,
        director_provider=director_decision.provider,
        director_model=director_decision.model,
        director_target=director_target,
        final_provider=final_provider,
        final_model=final_model,
        final_target=final_target,
        response_ok=bool(execution.response),
        iris_ok=iris_result.ok,
        iris_tier=recommendation.tier if recommendation else None,
        iris_target=iris_target,
        iris_task=recommendation.task if recommendation else None,
        iris_confidence=recommendation.confidence if recommendation else None,
        iris_latency_ms=iris_result.latency_ms,
        iris_error=iris_result.error,
        agrees_with_director=bool(iris_target and director_target and iris_target == director_target),
        agrees_with_final=bool(iris_target and final_target and iris_target == final_target),
    )


def summarize(results: list[IrisComparison]) -> dict[str, Any]:
    total = len(results)
    iris_ok = sum(1 for item in results if item.iris_ok)
    director_agree = sum(1 for item in results if item.agrees_with_director)
    final_agree = sum(1 for item in results if item.agrees_with_final)
    response_ok = sum(1 for item in results if item.response_ok)
    latencies = [item.iris_latency_ms for item in results if item.iris_latency_ms is not None]
    confidences = [item.iris_confidence for item in results if item.iris_confidence is not None]
    under_routing = [
        item.case
        for item in results
        if item.iris_target in {"deterministic", "iris"}
        and (
            item.director_target in {"local_heavy", "cloud", "isolated_worker"}
            or item.final_target in {"local_heavy", "cloud", "isolated_worker"}
        )
    ]

    return {
        "cases": total,
        "iris_valid_recommendations": iris_ok,
        "iris_valid_rate": iris_ok / total if total else 0.0,
        "agreement_with_director": director_agree,
        "agreement_with_director_rate": director_agree / total if total else 0.0,
        "agreement_with_final_provider": final_agree,
        "agreement_with_final_provider_rate": final_agree / total if total else 0.0,
        "successful_responses": response_ok,
        "successful_response_rate": response_ok / total if total else 0.0,
        "iris_latency_ms_mean": statistics.fmean(latencies) if latencies else None,
        "iris_latency_ms_p95": _percentile(latencies, 0.95),
        "iris_confidence_mean": statistics.fmean(confidences) if confidences else None,
        "iris_confidence_distribution": _confidence_distribution(confidences),
        "under_routing_cases": under_routing,
        "under_routing_count": len(under_routing),
    }


def _percentile(values: list[int], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return float(ordered[index])


def _confidence_distribution(values: list[float]) -> dict[str, int]:
    return {
        "0.00-0.49": sum(1 for value in values if value < 0.5),
        "0.50-0.74": sum(1 for value in values if 0.5 <= value < 0.75),
        "0.75-0.89": sum(1 for value in values if 0.75 <= value < 0.9),
        "0.90-1.00": sum(1 for value in values if value >= 0.9),
    }


def render_markdown(difficulty: str, summary: dict[str, Any], results: list[IrisComparison]) -> str:
    distribution = summary["iris_confidence_distribution"]
    lines = [
        f"# Iris Shadow Routing Report — {difficulty}",
        "",
        f"- Cases: {summary['cases']}",
        f"- Valid Iris recommendations: {summary['iris_valid_rate']:.1%}",
        f"- Agreement with Director: {summary['agreement_with_director_rate']:.1%}",
        f"- Agreement with final provider: {summary['agreement_with_final_provider_rate']:.1%}",
        f"- Successful responses: {summary['successful_response_rate']:.1%}",
        f"- Iris mean latency: {_fmt_ms(summary['iris_latency_ms_mean'])}",
        f"- Iris p95 latency: {_fmt_ms(summary['iris_latency_ms_p95'])}",
        f"- Confidence distribution: 0.00-0.49={distribution['0.00-0.49']}, "
        f"0.50-0.74={distribution['0.50-0.74']}, "
        f"0.75-0.89={distribution['0.75-0.89']}, "
        f"0.90-1.00={distribution['0.90-1.00']}",
        f"- Under-routing cases: {summary['under_routing_count']}",
        "",
        "## Disagreements",
        "",
        "| Case | Director | Iris | Final | Confidence | Iris ms |",
        "|---|---|---|---|---:|---:|",
    ]
    disagreements = [item for item in results if not item.agrees_with_director or not item.agrees_with_final]
    if not disagreements:
        lines.append("| _none_ | | | | | |")
    else:
        for item in disagreements:
            confidence = f"{item.iris_confidence:.2f}" if item.iris_confidence is not None else "-"
            latency = str(item.iris_latency_ms) if item.iris_latency_ms is not None else "-"
            lines.append(
                f"| {item.case} | {item.director_target or item.director_provider} | "
                f"{item.iris_target or 'ERROR'} | {item.final_target or item.final_provider} | "
                f"{confidence} | {latency} |"
            )
    under_routing_cases = set(summary["under_routing_cases"])
    under_routing = [item for item in results if item.case in under_routing_cases]
    lines.extend(["", "## Under-Routing", "", "| Case | Director | Iris | Final | Confidence |", "|---|---|---|---|---:|"])
    if not under_routing:
        lines.append("| _none_ | | | | |")
    else:
        for item in under_routing:
            confidence = f"{item.iris_confidence:.2f}" if item.iris_confidence is not None else "-"
            lines.append(
                f"| {item.case} | {item.director_target or item.director_provider} | "
                f"{item.iris_target or 'ERROR'} | {item.final_target or item.final_provider} | {confidence} |"
            )
    lines.append("")
    return "\n".join(lines)


def _fmt_ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f} ms"


async def run(difficulty: str, report_dir: Path) -> tuple[Path, Path, dict[str, Any]]:
    if not settings.iris_router_enabled:
        raise RuntimeError("IRIS_ROUTER_ENABLED must be true for the shadow gauntlet")

    router.register_clients(OllamaClient(), OpenRouterClient())
    iris = IrisRouterClient()
    if not await iris.healthy():
        raise RuntimeError(
            f"Iris router model {settings.iris_router_model!r} is not reachable at {settings.iris_ollama_base_url}"
        )
    if not await iris.warm():
        raise RuntimeError("Iris router model could not be warmed")

    suite = load_gauntlet(difficulty=difficulty)
    results: list[IrisComparison] = []
    for case in suite.cases:
        results.append(await compare_case(case, iris))

    summary = summarize(results)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"iris-shadow-{difficulty}-{timestamp}.json"
    markdown_path = report_dir / f"iris-shadow-{difficulty}-{timestamp}.md"

    payload = {
        "schema_version": "1.0",
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "difficulty": difficulty,
        "iris": {
            "base_url": settings.iris_ollama_base_url,
            "model": settings.iris_router_model,
            "keep_alive": settings.iris_router_keep_alive,
        },
        "summary": summary,
        "cases": [asdict(item) for item in results],
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(difficulty, summary, results), encoding="utf-8")
    return json_path, markdown_path, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Iris 7B shadow routing against Freyja Director decisions")
    parser.add_argument("--difficulty", choices=DIFFICULTIES, default="smoke")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args()

    json_path, markdown_path, summary = asyncio.run(run(args.difficulty, args.report_dir))
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
