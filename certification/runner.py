from __future__ import annotations

import asyncio
import socket
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import yaml

from certification import __version__
from certification.context import CertificationContext, CertificationExecution, ToolCallEvidence, elapsed_ms, sanitize_arguments
from certification.grader import grade_response
from certification.models import CaseResult, CertificationCase, CertificationReport, CertificationSuite, ReportMetadata
from certification.verifiers import Verifier, discover_verifiers

DEFAULT_SUITE_DIR = Path(__file__).resolve().parent / "suites"
DIFFICULTIES = ("smoke", "standard", "stress", "chaos")


class CertificationProvider(Protocol):
    name: str
    model: str

    async def complete(self, case: CertificationCase) -> CertificationExecution:
        ...


class OllamaCertificationProvider:
    name = "ollama"

    def __init__(self, model: str | None = None, router_instance: object | None = None) -> None:
        from freyja.config import settings
        from freyja.router import router

        self.model = model or settings.ollama_chat_model or settings.ollama_model
        self._router = router_instance or router

    async def complete(self, case: CertificationCase) -> CertificationExecution:
        from freyja.router import RouteRequest

        request_data = {"prompt": case.prompt, "provider": "local", "model": self.model}
        request_data.update(case.route_request)
        request_data["prompt"] = case.prompt
        start = time.monotonic()
        result = await self._router.execute(RouteRequest(**request_data))
        context = _context_from_routing_result(result, elapsed_ms(start))
        if not result.response:
            return CertificationExecution(response="", error=result.decision.public_error_message or result.decision.reason, context=context)
        return CertificationExecution(response=result.response, context=context)


class OpenRouterCertificationProvider:
    name = "openrouter"

    def __init__(self, model: str | None = None, router_instance: object | None = None) -> None:
        from freyja.config import settings
        from freyja.router import router

        self.model = model or settings.openrouter_model or "default"
        self._router = router_instance or router

    async def complete(self, case: CertificationCase) -> CertificationExecution:
        from freyja.router import RouteRequest

        request_data = {"prompt": case.prompt, "provider": "cloud", "model": self.model}
        request_data.update(case.route_request)
        request_data["prompt"] = case.prompt
        request_data["provider"] = "cloud"
        request_data["model"] = self.model
        start = time.monotonic()
        result = await self._router.execute(RouteRequest(**request_data))
        context = _context_from_routing_result(result, elapsed_ms(start))
        if not result.response:
            return CertificationExecution(response="", error=result.decision.public_error_message or result.decision.reason, context=context)
        return CertificationExecution(response=result.response, context=context)


def provider_for_name(
    provider: str,
    model: str | None = None,
    router_instance: object | None = None,
) -> CertificationProvider:
    if provider == "ollama":
        return OllamaCertificationProvider(model=model, router_instance=router_instance)
    if provider == "openrouter":
        return OpenRouterCertificationProvider(model=model, router_instance=router_instance)
    raise ValueError(f"Unsupported certification provider '{provider}'")


def load_suite(name: str, suite_dir: Path = DEFAULT_SUITE_DIR) -> CertificationSuite:
    if name in DIFFICULTIES:
        return load_gauntlet(difficulty=name, suite_dir=suite_dir)
    if name == "all":
        return load_gauntlet(difficulty=None, suite_dir=suite_dir)

    suite_path = resolve_suite_path(name, suite_dir=suite_dir)
    if not suite_path.exists():
        available = ", ".join(list_suite_names(suite_dir)) or "none"
        raise ValueError(f"Unknown certification suite '{name}'. Available suites: {available}")

    return _load_suite_file(suite_path, suite_dir=suite_dir)


def load_gauntlet(difficulty: str | None = "smoke", suite_dir: Path = DEFAULT_SUITE_DIR) -> CertificationSuite:
    suites = [_load_suite_file(path, suite_dir=suite_dir) for path in sorted(suite_dir.rglob("*.yaml"))]
    cases = tuple(
        case
        for suite in suites
        for case in suite.cases
        if difficulty is None or case.difficulty == difficulty
    )
    if not cases:
        label = difficulty or "all"
        raise ValueError(f"No certification cases found for difficulty '{label}'")
    label = difficulty or "all"
    return CertificationSuite(
        name=label,
        description=f"Freyja Certification Gauntlet ({label})",
        cases=cases,
        category="gauntlet",
        difficulty=label,
    )


def resolve_suite_path(name: str, suite_dir: Path = DEFAULT_SUITE_DIR) -> Path:
    normalized = name[:-5] if name.endswith(".yaml") else name
    direct = suite_dir / f"{normalized}.yaml"
    if direct.exists():
        return direct

    matches = [path for path in suite_dir.rglob("*.yaml") if path.stem == normalized or str(path.relative_to(suite_dir).with_suffix("")) == normalized]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        choices = ", ".join(str(path.relative_to(suite_dir).with_suffix("")) for path in matches)
        raise ValueError(f"Ambiguous certification suite '{name}'. Use one of: {choices}")
    return direct


def _load_suite_file(suite_path: Path, suite_dir: Path = DEFAULT_SUITE_DIR) -> CertificationSuite:
    data = yaml.safe_load(suite_path.read_text(encoding="utf-8")) or {}
    category = str(data.get("category") or suite_path.parent.name)
    difficulty = str(data.get("difficulty") or "standard")
    suite_name = str(data.get("name") or suite_path.stem)
    cases = tuple(
        CertificationCase(
            name=str(case["name"]),
            prompt=str(case["prompt"]),
            expected_keywords=tuple(case.get("expected_keywords", ())),
            forbidden_keywords=tuple(case.get("forbidden_keywords", ())),
            expects=dict(case.get("expects", {})),
            route_request=dict(case.get("route_request", {})),
            max_score=float(case.get("max_score", 1.0)),
            category=str(case.get("category") or category),
            difficulty=str(case.get("difficulty") or difficulty),
            suite_name=suite_name,
        )
        for case in data.get("cases", ())
    )
    if not cases:
        suite_id = str(suite_path.relative_to(suite_dir).with_suffix(""))
        raise ValueError(f"Certification suite '{suite_id}' has no cases")
    return CertificationSuite(
        name=suite_name,
        description=str(data.get("description") or ""),
        cases=cases,
        category=category,
        difficulty=difficulty,
        path=str(suite_path),
    )


def list_suite_names(suite_dir: Path = DEFAULT_SUITE_DIR) -> list[str]:
    return sorted(str(path.relative_to(suite_dir).with_suffix("")) for path in suite_dir.rglob("*.yaml"))


async def run_suite(
    suite: CertificationSuite,
    provider: CertificationProvider,
    router_mode: str = "default",
    verifiers: list[Verifier] | None = None,
) -> CertificationReport:
    started = time.monotonic()
    active_verifiers = verifiers if verifiers is not None else discover_verifiers()
    case_results = []
    for case in suite.cases:
        execution = await provider.complete(case)
        verification_results = [
            result
            for verifier in active_verifiers
            for result in verifier.verify(case, execution.context, execution.response)
        ]
        case_results.append(
            grade_response(
                case,
                execution.response,
                error=execution.error,
                runtime_context=execution.context.to_dict(),
                verifier_results=tuple(result.to_dict() for result in verification_results),
            )
        )

    execution_time = time.monotonic() - started
    max_score = sum(case.max_score for case in case_results)
    earned = sum(case.score for case in case_results)
    overall_score = earned / max_score if max_score else 0.0
    category_scores = _category_scores(case_results)
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")

    return CertificationReport(
        metadata=ReportMetadata(
            timestamp=timestamp,
            git_sha=_git(["rev-parse", "HEAD"]),
            branch=_git(["branch", "--show-current"]),
            working_tree="dirty" if _git(["status", "--porcelain"]) else "clean",
            hostname=socket.gethostname(),
            provider=_selected_provider(case_results) or provider.name,
            model=_selected_model(case_results) or provider.model,
            router_mode=router_mode,
            suite_name=suite.name,
            overall_score=overall_score,
            execution_time=execution_time,
            certification_cli_version=__version__,
        ),
        suite_description=suite.description,
        cases=tuple(case_results),
        category_scores=category_scores,
    )


def run_suite_sync(
    suite: CertificationSuite,
    provider: CertificationProvider,
    router_mode: str = "default",
    verifiers: list[Verifier] | None = None,
) -> CertificationReport:
    return asyncio.run(run_suite(suite=suite, provider=provider, router_mode=router_mode, verifiers=verifiers))


def _git(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def _category_scores(case_results: list[CaseResult]) -> dict[str, float]:
    scores: dict[str, tuple[float, float]] = {}
    for case in case_results:
        earned, max_score = scores.get(case.category, (0.0, 0.0))
        scores[case.category] = (earned + case.score, max_score + case.max_score)
    return {
        category: (earned / max_score if max_score else 0.0)
        for category, (earned, max_score) in sorted(scores.items())
    }


def _context_from_routing_result(result: Any, duration_ms: float) -> CertificationContext:
    runtime_evidence = getattr(result, "runtime_evidence", None)
    if runtime_evidence is not None:
        data = runtime_evidence.model_dump(mode="json") if hasattr(runtime_evidence, "model_dump") else dict(runtime_evidence)
        token_counts: dict[str, int] = {}
        for key, value in dict(data.get("token_counts") or {}).items():
            try:
                token_counts[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        context = CertificationContext(
            provider_selected=data.get("provider_selected"),
            model_selected=data.get("model_selected"),
            routing_decision=data.get("routing_decision"),
            routing_reason=data.get("routing_reason"),
            fallback_events=list(data.get("fallback_events") or []),
            memory_lookups=list(data.get("memory_lookups") or []),
            connector_operations=list(data.get("connector_operations") or []),
            vision_executions=list(data.get("vision_executions") or []),
            timing=dict(data.get("timing") or {}),
            token_counts=token_counts,
            cost=data.get("cost"),
        )
        context.tool_calls = [
            ToolCallEvidence(
                name=str(entry.get("name", "")),
                arguments=sanitize_arguments(entry.get("arguments", {}) if isinstance(entry.get("arguments"), dict) else {}),
                success=entry.get("success"),
                error=entry.get("error"),
                duration_ms=entry.get("duration_ms"),
            )
            for entry in data.get("tool_calls") or []
        ]
        context.timing.setdefault("duration_ms", duration_ms)
        return context

    decision = result.decision
    context = CertificationContext(
        provider_selected=decision.provider,
        model_selected=decision.model,
        routing_decision=decision.provider,
        routing_reason=decision.reason,
        fallback_events=list(decision.fallback_attempts),
        timing={"duration_ms": duration_ms},
        cost=decision.estimated_cost_usd,
    )
    for entry in result.tool_results:
        context.tool_calls.append(
            ToolCallEvidence(
                name=str(entry.get("tool_name", "")),
                arguments=sanitize_arguments(entry.get("arguments", {}) if isinstance(entry.get("arguments"), dict) else {}),
                success=entry.get("success"),
                error=entry.get("error_code") or entry.get("public_error_message"),
                duration_ms=entry.get("duration_ms"),
            )
        )
    return context


def _selected_provider(case_results: list[CaseResult]) -> str | None:
    for case in case_results:
        provider = case.runtime_context.get("provider_selected")
        if provider:
            return str(provider)
    return None


def _selected_model(case_results: list[CaseResult]) -> str | None:
    for case in case_results:
        model = case.runtime_context.get("model_selected")
        if model:
            return str(model)
    return None
