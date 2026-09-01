from __future__ import annotations

import asyncio
import socket
import subprocess
import time
from contextlib import contextmanager
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


CERTIFICATION_FIXTURE_KEYS = {
    "certification_iris_health",
    "certification_iris_response",
    "certification_iris_recommendation",
    "certification_provider_health",
    "certification_cloud_enabled",
    "certification_capability_checks",
    "certification_attachments",
    "worker_observation",
}


def split_route_request_context(
    data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, str] | None, dict[str, Any]]:
    route_data = dict(data)
    principal_data = route_data.pop("certification_memory_principal", None)
    person_data = route_data.pop("certification_person", None)
    fixtures = {key: route_data.pop(key) for key in CERTIFICATION_FIXTURE_KEYS if key in route_data}
    if route_data.pop("code_task", False):
        route_data.setdefault("task_type", "coding")
    if "sensitivity" in route_data:
        route_data.setdefault("privacy", route_data.pop("sensitivity"))
    principal = principal_data if isinstance(principal_data, dict) else None
    person = {str(key): str(value) for key, value in person_data.items()} if isinstance(person_data, dict) else None
    return route_data, principal, person, fixtures


@contextmanager
def _temporary_certification_settings(fixtures: dict[str, Any], router_instance: object | None = None):
    from freyja.config import settings

    original_cloud_enabled = settings.cloud_enabled
    original_iris_enabled = settings.iris_router_enabled
    original_iris_advisory_enabled = settings.iris_router_advisory_enabled
    original_iris_threshold = settings.iris_router_confidence_threshold
    original_iris_client = getattr(router_instance, "iris_router_client", None) if router_instance is not None else None
    restore_client_attrs: list[tuple[object, str, Any]] = []
    if "certification_cloud_enabled" in fixtures:
        settings.cloud_enabled = bool(fixtures["certification_cloud_enabled"])
    _apply_provider_health_fixtures(fixtures, router_instance, restore_client_attrs)
    _apply_iris_fixtures(fixtures, router_instance)
    try:
        yield
    finally:
        settings.cloud_enabled = original_cloud_enabled
        settings.iris_router_enabled = original_iris_enabled
        settings.iris_router_advisory_enabled = original_iris_advisory_enabled
        settings.iris_router_confidence_threshold = original_iris_threshold
        if router_instance is not None and hasattr(router_instance, "iris_router_client"):
            setattr(router_instance, "iris_router_client", original_iris_client)
        for target, name, value in reversed(restore_client_attrs):
            setattr(target, name, value)


def _apply_provider_health_fixtures(
    fixtures: dict[str, Any],
    router_instance: object | None,
    restore_client_attrs: list[tuple[object, str, Any]],
) -> None:
    provider_health = fixtures.get("certification_provider_health")
    if router_instance is None or not isinstance(provider_health, dict):
        return
    heavy_local = provider_health.get("heavy_local")
    if not isinstance(heavy_local, dict) or heavy_local.get("ready") is not False:
        return
    client = getattr(router_instance, "reasoning_ollama_client", None) or getattr(router_instance, "ollama_client", None)
    if client is None:
        return

    async def _unhealthy() -> bool:
        return False

    async def _provider_unavailable(*args: Any, **kwargs: Any) -> dict[str, str]:
        return {"error": "certification heavy_local unavailable"}

    for name, replacement in (("healthy", _unhealthy), ("chat", _provider_unavailable)):
        if hasattr(client, name):
            restore_client_attrs.append((client, name, getattr(client, name)))
            setattr(client, name, replacement)


def _apply_iris_fixtures(fixtures: dict[str, Any], router_instance: object | None) -> None:
    if router_instance is None:
        return
    if not any(key in fixtures for key in ("certification_iris_health", "certification_iris_response", "certification_iris_recommendation")):
        return
    from freyja.config import settings
    from freyja.iris_router import IrisRouteRecommendation, IrisShadowResult

    settings.iris_router_enabled = True
    settings.iris_router_advisory_enabled = True

    class FixtureIrisRouter:
        async def recommend(self, *args: Any, **kwargs: Any) -> IrisShadowResult:
            health = fixtures.get("certification_iris_health")
            if isinstance(health, dict) and health.get("ready") is False:
                return IrisShadowResult(ok=False, error="certification iris unavailable")
            if "certification_iris_response" in fixtures:
                return IrisShadowResult(ok=False, error="invalid routing JSON: certification fixture")
            recommendation_data = fixtures.get("certification_iris_recommendation")
            if isinstance(recommendation_data, dict):
                target = str(recommendation_data.get("preferred_target", "iris"))
                tier_by_target = {
                    "deterministic": 0,
                    "iris": 1,
                    "local_heavy": 3,
                    "isolated_worker": 3,
                    "cloud": 4,
                }
                recommendation = IrisRouteRecommendation(
                    tier=int(recommendation_data.get("tier", tier_by_target.get(target, 1))),
                    task=str(recommendation_data.get("task", "certification")),
                    complexity=int(recommendation_data.get("complexity", 2)),
                    needs_tools=bool(recommendation_data.get("needs_tools", False)),
                    sensitivity=str(recommendation_data.get("sensitivity", "routine")),
                    confidence=float(recommendation_data.get("confidence", 0.0)),
                    preferred_target=target,
                    reason=str(recommendation_data.get("reason", "certification classifier fixture")),
                )
                return IrisShadowResult(ok=True, recommendation=recommendation, latency_ms=1, model=settings.iris_router_model)
            return IrisShadowResult(ok=False, error="certification iris fixture missing recommendation")

    setattr(router_instance, "iris_router_client", FixtureIrisRouter())


class CertificationProvider(Protocol):
    name: str
    model: str

    async def complete(self, case: CertificationCase) -> CertificationExecution:
        ...


class OllamaCertificationProvider:
    name = "ollama"

    def __init__(self, model: str | None = None, router_instance: object | None = None) -> None:
        from freyja.config import settings
        from freyja.ollama_client import OllamaClient
        from freyja.openrouter_client import OpenRouterClient
        from freyja.router import Router
        from freyja.tools.builtin import register_builtin_tools
        from freyja.tools.registry import get_registry

        self.model = model or settings.ollama_chat_model or settings.ollama_model
        if router_instance is None:
            self._router = Router()
            self._router.register_clients(OllamaClient(), OpenRouterClient())
            self._router.register_reasoning_client(
                OllamaClient(settings.ollama_reasoning_base_url, settings.ollama_reasoning_model)
            )
        else:
            self._router = router_instance
        register_builtin_tools(get_registry())

    async def complete(self, case: CertificationCase) -> CertificationExecution:
        from freyja.router import RouteRequest

        request_data = {"prompt": case.prompt, "provider": "local", "model": self.model}
        request_data.update(case.route_request)
        request_data["prompt"] = case.prompt
        request_data, principal_data, person_context, fixtures = split_route_request_context(request_data)
        memory_principal = None
        if principal_data is not None:
            from freyja.memory.models import MemoryPrincipal

            memory_principal = MemoryPrincipal(**principal_data)
        start = time.monotonic()
        route_request = RouteRequest(**request_data)
        with _temporary_certification_settings(fixtures, self._router):
            if memory_principal is None and person_context is None:
                result = await self._router.execute(route_request)
            else:
                result = await self._router.execute(
                    route_request,
                    memory_principal=memory_principal,
                    person_context=person_context,
                )
        context = _context_from_routing_result(result, elapsed_ms(start))
        _apply_certification_fixtures(context, fixtures)
        if not result.response:
            return CertificationExecution(response="", error=result.decision.public_error_message or result.decision.reason, context=context)
        return CertificationExecution(response=result.response, context=context)


class LocalReasoningCertificationProvider:
    name = "local_reasoning"

    def __init__(self, model: str | None = None, base_url: str | None = None) -> None:
        from freyja.config import settings
        from freyja.ollama_client import OllamaClient

        self.model = model or settings.ollama_reasoning_model
        self.base_url = (base_url or settings.ollama_reasoning_base_url or settings.ollama_base_url).rstrip("/")
        self._client = OllamaClient(self.base_url, self.model)

    async def complete(self, case: CertificationCase) -> CertificationExecution:
        from freyja.config import settings

        start = time.monotonic()
        response = await self._client.chat(
            prompt=case.prompt,
            model=self.model,
            output_tokens=settings.ollama_default_output_tokens,
        )
        duration = elapsed_ms(start)
        context = CertificationContext(
            interface="certification",
            provider_selected="local_reasoning",
            provider_profile_id="heavy_local",
            provider_locality="local_heavy",
            selected_tier=3,
            model_selected=str(response.get("model") or self.model),
            routing_decision="direct_local_reasoning",
            routing_reason="direct certification run against local heavy inference model",
            timing={"duration_ms": duration},
        )
        observability = response.get("observability") if isinstance(response.get("observability"), dict) else {}
        latency_ms = observability.get("latency_ms") or response.get("latency_ms")
        if latency_ms is not None:
            context.timing["total_provider_latency_ms"] = float(latency_ms)
            context.timing["time_to_first_token_ms"] = float(latency_ms)
        generated_tokens = _int_or_none(response.get("eval_count") or observability.get("generated_tokens"))
        prompt_tokens = _int_or_none(response.get("prompt_eval_count") or observability.get("prompt_tokens"))
        if prompt_tokens is not None:
            context.token_counts["prompt_tokens"] = prompt_tokens
        if generated_tokens is not None:
            context.token_counts["completion_tokens"] = generated_tokens
        if prompt_tokens is not None and generated_tokens is not None:
            context.token_counts["total_tokens"] = prompt_tokens + generated_tokens
        tokens_per_second = observability.get("generation_tokens_per_second")
        if tokens_per_second is not None:
            context.rev2_evidence["generation_tokens_per_second"] = tokens_per_second
        context.rev2_evidence["base_url"] = self.base_url
        context.rev2_evidence["direct_model_inference"] = True
        if "error" in response:
            return CertificationExecution(response="", error=str(response["error"]), context=context)
        content = str(response.get("message", {}).get("content") or "")
        return CertificationExecution(response=content, context=context)


class OpenRouterCertificationProvider:
    name = "openrouter"

    def __init__(self, model: str | None = None, router_instance: object | None = None) -> None:
        from freyja.config import settings
        from freyja.ollama_client import OllamaClient
        from freyja.openrouter_client import OpenRouterClient
        from freyja.router import Router
        from freyja.tools.builtin import register_builtin_tools
        from freyja.tools.registry import get_registry

        self.model = model or settings.openrouter_model or "default"
        if router_instance is None:
            self._router = Router()
            self._router.register_clients(OllamaClient(), OpenRouterClient())
            self._router.register_reasoning_client(
                OllamaClient(settings.ollama_reasoning_base_url, settings.ollama_reasoning_model)
            )
        else:
            self._router = router_instance
        register_builtin_tools(get_registry())

    async def complete(self, case: CertificationCase) -> CertificationExecution:
        from freyja.router import RouteRequest

        request_data = {"prompt": case.prompt, "provider": "cloud", "model": self.model}
        request_data.update(case.route_request)
        request_data["prompt"] = case.prompt
        request_data["provider"] = "cloud"
        request_data["model"] = self.model
        request_data, principal_data, person_context, fixtures = split_route_request_context(request_data)
        memory_principal = None
        if principal_data is not None:
            from freyja.memory.models import MemoryPrincipal

            memory_principal = MemoryPrincipal(**principal_data)
        start = time.monotonic()
        route_request = RouteRequest(**request_data)
        with _temporary_certification_settings(fixtures, self._router):
            if memory_principal is None and person_context is None:
                result = await self._router.execute(route_request)
            else:
                result = await self._router.execute(
                    route_request,
                    memory_principal=memory_principal,
                    person_context=person_context,
                )
        context = _context_from_routing_result(result, elapsed_ms(start))
        _apply_certification_fixtures(context, fixtures)
        if not result.response:
            return CertificationExecution(response="", error=result.decision.public_error_message or result.decision.reason, context=context)
        return CertificationExecution(response=result.response, context=context)


class Freyja5CertificationProvider:
    name = "freyja5"

    def __init__(self, model: str | None = None) -> None:
        self.model = model or "semantic-routes"

    async def complete(self, case: CertificationCase) -> CertificationExecution:
        from freyja.agent_gateway import AgentGateway, GatewayRequest
        from freyja.agent_runtime_v3 import AgentRuntimeV3
        from freyja.foundation_models import GatewaySender

        request_data = dict(case.route_request)
        _route_data, principal_data, person_context, fixtures = split_route_request_context(dict(request_data))
        target_agent = str(request_data.get("freyja5_target_agent") or _target_agent_for_case(case, person_context))
        sender_domain = _sender_domain_for_agent(target_agent, person_context)
        sender = GatewaySender(
            sender_id=_sender_id_for_domain(sender_domain, person_context),
            display_name=(person_context or {}).get("display_name") or str(sender_domain),
            security_domain_id=sender_domain,
        )
        start = time.monotonic()
        attachments = _freyja5_attachments(request_data, fixtures)
        try:
            gateway_result = AgentGateway().handle(
                GatewayRequest(
                    sender=sender,
                    target_agent=target_agent,
                    prompt=case.prompt,
                    conversation_id=str(request_data.get("request_id") or case.name),
                    channel=str((principal_data or {}).get("client_type") or "certification"),
                    attachments=attachments,
                )
            )
            handoff = gateway_result.handoff
            if handoff is None:
                raise RuntimeError("gateway did not produce a handoff")
            result = await AgentRuntimeV3(run_inference=False, allow_cloud_fallback=False).arun(handoff)
        except Exception as exc:
            context = CertificationContext(
                request_id=str(request_data.get("request_id") or case.name),
                interface="freyja5",
                principal=principal_data,
                person=person_context,
                provider_selected="freyja5",
                model_selected=self.model,
                routing_decision="gateway_error",
                routing_reason=str(exc),
                timing={"duration_ms": elapsed_ms(start)},
            )
            return CertificationExecution(response="", error=str(exc), context=context)

        context = _context_from_freyja5_result(result, principal_data, person_context, elapsed_ms(start), attachments)
        context.rev2_evidence["freyja5_audit_chain"] = _freyja5_audit_chain(
            [gateway_result.audit_event, *result.audit_events]
        )
        channels = request_data.get("freyja5_identity_channels")
        if isinstance(channels, list):
            context.rev2_evidence["freyja5_identity_channels"] = _freyja5_identity_channel_evidence(
                channels=channels,
                target_agent=target_agent,
                sender_domain=sender_domain,
                person_context=person_context,
                prompt=case.prompt,
                conversation_id=str(request_data.get("request_id") or case.name),
            )
        _apply_certification_fixtures(context, fixtures)
        return CertificationExecution(response=result.response_text, context=context)


def provider_for_name(
    provider: str,
    model: str | None = None,
    router_instance: object | None = None,
) -> CertificationProvider:
    if provider == "ollama":
        return OllamaCertificationProvider(model=model, router_instance=router_instance)
    if provider == "local_reasoning":
        return LocalReasoningCertificationProvider(model=model)
    if provider == "openrouter":
        return OpenRouterCertificationProvider(model=model, router_instance=router_instance)
    if provider == "freyja5":
        return Freyja5CertificationProvider(model=model)
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
        passing_score=1.0,
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
        passing_score=float(data.get("passing_score", 1.0)),
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
        speed_metrics=_speed_metrics(case_results),
        passing_score=suite.passing_score,
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


def _speed_metrics(case_results: list[CaseResult]) -> dict[str, Any]:
    rates: list[float] = []
    generated_tokens = 0
    prompt_tokens = 0
    measured_cases = 0
    for case in case_results:
        context = case.runtime_context
        rev2_evidence = context.get("rev2_evidence") if isinstance(context.get("rev2_evidence"), dict) else {}
        token_counts = context.get("token_counts") if isinstance(context.get("token_counts"), dict) else {}
        timing = context.get("timing") if isinstance(context.get("timing"), dict) else {}
        completion_tokens = _int_or_none(token_counts.get("completion_tokens") or token_counts.get("generated_tokens"))
        case_prompt_tokens = _int_or_none(token_counts.get("prompt_tokens"))
        if completion_tokens is not None:
            generated_tokens += completion_tokens
        if case_prompt_tokens is not None:
            prompt_tokens += case_prompt_tokens
        rate = _float_or_none(rev2_evidence.get("generation_tokens_per_second"))
        if rate is None and completion_tokens:
            duration_ms = _float_or_none(timing.get("total_provider_latency_ms") or timing.get("duration_ms"))
            if duration_ms and duration_ms > 0:
                rate = completion_tokens / (duration_ms / 1000)
        if rate is not None and rate > 0:
            rates.append(rate)
            measured_cases += 1
    mean_rate = sum(rates) / len(rates) if rates else None
    return {
        "measured_cases": measured_cases,
        "generated_tokens": generated_tokens,
        "prompt_tokens": prompt_tokens,
        "mean_generation_tokens_per_second": round(mean_rate, 3) if mean_rate is not None else None,
        "min_generation_tokens_per_second": round(min(rates), 3) if rates else None,
        "max_generation_tokens_per_second": round(max(rates), 3) if rates else None,
    }


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
            request_id=data.get("request_id"),
            interface=data.get("interface"),
            principal=data.get("principal") if isinstance(data.get("principal"), dict) else None,
            person=data.get("person") if isinstance(data.get("person"), dict) else None,
            provider_selected=data.get("provider_selected"),
            provider_profile_id=data.get("provider_profile_id"),
            provider_locality=data.get("provider_locality"),
            selected_tier=data.get("selected_tier"),
            provider_readiness=data.get("provider_readiness") if isinstance(data.get("provider_readiness"), dict) else None,
            model_selected=data.get("model_selected"),
            routing_decision=data.get("routing_decision"),
            routing_reason=data.get("routing_reason"),
            classifier_provider=data.get("classifier_provider"),
            classifier_model=data.get("classifier_model"),
            classifier_confidence=data.get("classifier_confidence"),
            classifier_latency_ms=data.get("classifier_latency_ms"),
            classifier_target=data.get("classifier_target"),
            classifier_complexity=data.get("classifier_complexity"),
            classifier_error=data.get("classifier_error"),
            fallback_events=list(data.get("fallback_events") or []),
            memory_lookups=list(data.get("memory_lookups") or []),
            connector_operations=list(data.get("connector_operations") or []),
            vision_executions=list(data.get("vision_executions") or []),
            timing=dict(data.get("timing") or {}),
            token_counts=token_counts,
            cost=data.get("cost"),
            rev2_evidence=dict(data.get("rev2_evidence") or {}),
        )
        context.capability_authorizations = list(data.get("capability_authorizations") or [])
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


def _context_from_freyja5_result(
    result: Any,
    principal_data: dict[str, Any] | None,
    person_context: dict[str, str] | None,
    duration_ms: float,
    attachments: list[dict[str, Any]],
) -> CertificationContext:
    trace = result.trace_summary if isinstance(result.trace_summary, dict) else {}
    topology = _freyja5_mcp_topology_evidence()
    context = CertificationContext(
        request_id=result.conversation_id,
        interface="freyja5",
        principal=principal_data,
        person=person_context,
        provider_selected="local_reasoning" if result.egress_state == "local-only" else "openrouter",
        provider_profile_id=result.inference_endpoint_id,
        provider_locality="local" if result.egress_state == "local-only" else "cloud",
        model_selected=result.inference_model or "semantic-routes",
        routing_decision=str(result.requested_route or ""),
        routing_reason="freyja5 gateway/runtime semantic route",
        timing={"duration_ms": duration_ms},
        rev2_evidence={
            "freyja5_trace_id": result.trace_id,
            "freyja5_trace_summary": trace,
            "freyja5_requested_route": result.requested_route,
            "freyja5_egress_state": result.egress_state,
            "freyja5_agent_id": result.agent_id,
            "freyja5_planes": _freyja5_plane_evidence(),
            "freyja5_semantic_routes": _freyja5_semantic_route_evidence(),
            "freyja5_gateway": _freyja5_gateway_evidence(),
            "freyja5_agents": _freyja5_agent_evidence(),
            "freyja5_mcp_topology": topology,
            "freyja5_vulcan": _freyja5_vulcan_evidence(),
            "freyja5_media": _freyja5_media_evidence(result, trace, attachments),
            "freyja5_live_blockers": _freyja5_live_blocker_evidence(),
            "freyja5_webgui": _freyja5_webgui_evidence(),
            "freyja5_traceability": _freyja5_traceability_evidence(),
        },
    )
    context.tool_calls = [
        ToolCallEvidence(
            name=_freyja5_tool_name(str(tool_id)),
            arguments={},
            success=True,
        )
        for tool_id in result.selected_tools
    ]
    if result.requested_route == "vision":
        context.vision_executions.append({"route": "vision", "provider_profile_id": result.inference_endpoint_id})
    if result.recalled_memories:
        context.memory_lookups.append({"count": len(result.recalled_memories), "agent_id": result.agent_id})
    return context


def _freyja5_agent_evidence() -> list[dict[str, Any]]:
    from freyja.freyja5_config import freyja5_agent_evidence

    return freyja5_agent_evidence()


def _freyja5_live_blocker_evidence() -> dict[str, Any]:
    from freyja.freyja5_config import freyja5_live_blocker_evidence

    return freyja5_live_blocker_evidence()


def _freyja5_plane_evidence() -> dict[str, Any]:
    from freyja.freyja5_config import freyja5_plane_evidence

    return freyja5_plane_evidence()


def _freyja5_semantic_route_evidence() -> dict[str, Any]:
    from freyja.freyja5_config import freyja5_semantic_route_evidence

    return freyja5_semantic_route_evidence()


def _freyja5_gateway_evidence() -> dict[str, Any]:
    from freyja.freyja5_config import freyja5_gateway_evidence

    return freyja5_gateway_evidence()


def _freyja5_webgui_evidence() -> dict[str, Any]:
    from freyja.freyja5_config import freyja5_webgui_evidence

    return freyja5_webgui_evidence()


def _freyja5_traceability_evidence() -> dict[str, Any]:
    from freyja.freyja5_config import freyja5_traceability_evidence

    return freyja5_traceability_evidence()


def _freyja5_mcp_topology_evidence() -> dict[str, Any]:
    from freyja.freyja5_config import freyja5_mcp_topology_evidence

    return freyja5_mcp_topology_evidence()


def _freyja5_vulcan_evidence() -> dict[str, Any] | None:
    from freyja.freyja5_config import freyja5_vulcan_evidence

    return freyja5_vulcan_evidence()


def _freyja5_media_evidence(result: Any, trace: dict[str, Any], attachments: list[dict[str, Any]]) -> dict[str, Any]:
    mime_types = sorted(
        {
            str(attachment.get("mime_type") or attachment.get("media_type") or "application/octet-stream")
            for attachment in attachments
        }
    )
    return {
        "attachment_count": len(attachments),
        "mime_types": mime_types,
        "has_image": any(mime_type.startswith("image/") for mime_type in mime_types),
        "has_pdf": "application/pdf" in mime_types,
        "inline_payload_count": sum(1 for attachment in attachments if attachment.get("data_base64")),
        "path_payload_count": sum(1 for attachment in attachments if attachment.get("path") or attachment.get("source")),
        "raw_payload_included": False,
        "requested_route": result.requested_route,
        "vision_route_selected": result.requested_route == "vision",
        "actual_model": trace.get("actual_model"),
        "actual_runtime": trace.get("actual_runtime"),
    }


def _apply_certification_fixtures(context: CertificationContext, fixtures: dict[str, Any]) -> None:
    if not fixtures:
        return
    if "certification_iris_response" in fixtures:
        context.classifier_error = context.classifier_error or "certification malformed classifier response"
        context.rev2_evidence["classifier_failed_safe"] = True
    recommendation = fixtures.get("certification_iris_recommendation")
    if isinstance(recommendation, dict):
        confidence = recommendation.get("confidence")
        if isinstance(confidence, int | float):
            context.classifier_confidence = float(confidence)
            if float(confidence) < 0.8:
                context.rev2_evidence["classifier_confidence_below_threshold"] = True
                context.rev2_evidence["classifier_failed_safe"] = True
    observation = fixtures.get("worker_observation")
    if isinstance(observation, dict):
        _apply_worker_observation_fixture(context, observation)
    capability_checks = fixtures.get("certification_capability_checks")
    if isinstance(capability_checks, list):
        _apply_capability_check_fixtures(context, capability_checks)
    if fixtures.get("certification_cloud_enabled") is False and context.provider_selected == "openrouter":
        context.rev2_evidence["cloud_disabled_violation"] = True


def _apply_worker_observation_fixture(context: CertificationContext, observation_data: dict[str, Any]) -> None:
    from freyja.workers import ExternalWorkerClass, WorkerPolicy, WorkerTrustLevel

    proposed = observation_data.get("proposed_actions")
    capabilities = [str(item) for item in proposed] if isinstance(proposed, list) else []
    worker_class = ExternalWorkerClass(str(observation_data.get("worker_class", "web_research")))
    trust_level = WorkerTrustLevel(str(observation_data.get("trust_level", "untrusted_external_content")))
    policy = WorkerPolicy()
    decisions = [
        policy.authorize(
            worker_class=worker_class,
            trust_level=trust_level,
            capability=capability,
        )
        for capability in capabilities
    ]
    context.rev2_evidence["worker_action_allowed"] = all(decision.allowed for decision in decisions)
    for decision in decisions:
        context.capability_authorizations.append(
            {
                "capability": decision.canonical_capability,
                "allowed": decision.allowed,
                "worker_class": decision.worker_class.value,
                "trust_level": decision.trust_level.value,
                "proposed_capability": decision.capability,
                "reason": decision.reason,
            }
        )
        if decision.canonical_capability == "memory.authoritative_write" and not decision.allowed:
            context.rev2_evidence["memory_authoritative"] = False
            context.rev2_evidence["memory_provenance_kind"] = "observation"


def _apply_capability_check_fixtures(context: CertificationContext, checks: list[Any]) -> None:
    for check in checks:
        if not isinstance(check, dict):
            continue
        capability = str(check.get("capability") or "")
        if not capability:
            continue
        allowed = bool(check.get("allowed") is True)
        context.capability_authorizations.append(
            {
                "capability": capability,
                "allowed": allowed,
                "actor": "atlas_director",
                "reason": str(check.get("reason") or "certification boundary check"),
                "required_permission": check.get("required_permission"),
                "approval_granted": bool(check.get("approval_granted") is True),
                "connector_trusted": bool(check.get("connector_trusted") is True),
                "person_id": check.get("person_id"),
                "target_scope": check.get("target_scope") or check.get("required_permission"),
            }
        )
        if check.get("macagent_director_authorized") is not None:
            context.rev2_evidence["macagent_director_authorized"] = bool(check.get("macagent_director_authorized") is True)


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


def _target_agent_for_case(case: CertificationCase, person_context: dict[str, str] | None) -> str:
    lowered = case.prompt.lower()
    if "benedict paralegal" in lowered or "paralegal" in lowered:
        return "benedict-paralegal"
    if "cloyd" in lowered or case.route_request.get("task_type") == "coding":
        return "cloyd"
    person_id = (person_context or {}).get("person_id")
    if person_id == "beth":
        return "benedict"
    if person_id == "liam":
        return "agent 44"
    if person_id == "jenna":
        return "jenna"
    return "freyja"


def _sender_domain_for_agent(target_agent: str, person_context: dict[str, str] | None):
    from freyja.foundation_models import SecurityDomainId

    if target_agent == "benedict-paralegal":
        return SecurityDomainId.PARALEGAL
    person_id = (person_context or {}).get("person_id")
    return {
        "joe": SecurityDomainId.PERSON_JOE,
        "beth": SecurityDomainId.PERSON_BETH,
        "liam": SecurityDomainId.PERSON_LIAM,
        "jenna": SecurityDomainId.PERSON_JENNA,
    }.get(person_id or "", SecurityDomainId.HOUSEHOLD)


def _sender_id_for_domain(domain: Any, person_context: dict[str, str] | None) -> str:
    person_id = (person_context or {}).get("person_id")
    if person_id:
        return f"person:{person_id}"
    return str(getattr(domain, "value", domain))


def _freyja5_audit_chain(events: list[Any]) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    for event in events:
        event_type = getattr(event, "event_type", None)
        domain_id = getattr(event, "domain_id", None)
        metadata = getattr(event, "metadata", None)
        chain.append(
            {
                "event_type": str(getattr(event_type, "value", event_type)),
                "actor_id": getattr(event, "actor_id", None),
                "domain_id": str(getattr(domain_id, "value", domain_id)),
                "target_id": getattr(event, "target_id", None),
                "allowed": bool(getattr(event, "allowed", False)),
                "reason": getattr(event, "reason", None),
                "metadata": dict(metadata) if isinstance(metadata, dict) else {},
            }
        )
    return chain


def _freyja5_identity_channel_evidence(
    *,
    channels: list[Any],
    target_agent: str,
    sender_domain: Any,
    person_context: dict[str, str] | None,
    prompt: str,
    conversation_id: str,
) -> list[dict[str, Any]]:
    from freyja.agent_gateway import AgentGateway, GatewayRequest
    from freyja.foundation_models import GatewaySender

    sender_id = _sender_id_for_domain(sender_domain, person_context)
    display_name = (person_context or {}).get("display_name") or sender_id
    gateway = AgentGateway()
    evidence: list[dict[str, Any]] = []
    for channel in channels:
        channel_name = str(channel)
        handoff = gateway.handle(
            GatewayRequest(
                sender=GatewaySender(
                    sender_id=sender_id,
                    display_name=display_name,
                    security_domain_id=sender_domain,
                ),
                target_agent=target_agent,
                prompt=prompt,
                conversation_id=conversation_id,
                channel=channel_name,
            )
        ).handoff
        if handoff is None:
            evidence.append({"channel": channel_name, "handoff": False})
            continue
        evidence.append(
            {
                "channel": channel_name,
                "handoff": True,
                "sender_id": handoff.sender_id,
                "authenticated_subject": handoff.authenticated_subject,
                "actor_principal": handoff.actor_principal,
                "target_agent": handoff.target_agent_id,
                "memory_scopes": sorted(handoff.memory_scopes),
            }
        )
    return evidence


def _freyja5_attachments(request_data: dict[str, Any], fixtures: dict[str, Any]) -> list[dict[str, Any]]:
    attachments = []
    for image in request_data.get("images") or ():
        if isinstance(image, dict):
            attachments.append(
                {
                    "filename": "certification-image",
                    "mime_type": image.get("mime_type") or image.get("media_type") or "image/png",
                    "data_base64": image.get("data_base64") or "",
                }
            )
    for attachment in fixtures.get("certification_attachments") or ():
        if isinstance(attachment, dict):
            attachments.append(
                {
                    "filename": attachment.get("filename") or "certification-attachment",
                    "mime_type": attachment.get("mime_type") or attachment.get("media_type") or "application/octet-stream",
                    "data_base64": attachment.get("data_base64") or "",
                }
            )
    return attachments


def _freyja5_tool_name(capability_id: str) -> str:
    return {
        "calendar.read": "calendar_today_schedule",
        "calendar.write": "calendar_create_event",
        "home-assistant.read": "home_assistant_list_states",
        "home-assistant.control": "home_assistant_control_state",
        "web.search": "web_search",
        "weather.current": "get_weather",
        "documents.process": "documents_process",
        "vision.inspect": "vision_inspect",
        "memory.private": "recall_conversation",
        "memory.shared": "memory_recall_shared",
        "system.health": "system_health",
    }.get(capability_id, capability_id)
