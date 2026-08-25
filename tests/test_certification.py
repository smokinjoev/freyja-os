from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx

from certification import cli
from certification.approval_exercise import run_approval_exercise, write_approval_exercise_report
from certification.benchmark import (
    BenchmarkTarget,
    benchmark_row,
    build_benchmark_report,
    compare_benchmark_models,
    compare_reports,
    find_benchmark_report_by_commit,
    find_benchmark_report_with_models,
    render_benchmark_markdown,
    render_compare_markdown,
    write_benchmark_report,
)
from certification.latency_probe import build_latency_probe_report
from certification.context import CertificationContext, CertificationExecution, ToolCallEvidence, sanitize_arguments
from certification.grader import grade_response
from certification.models import CertificationCase, CertificationReport, CertificationSuite, ReportMetadata
from certification.memory_audit import audit_memory_provenance, write_memory_audit_report
from certification.reporter import report_stem, write_reports
from certification.rev2_readiness import (
    DEFAULT_REQUIRED_PROVIDER_PROFILES,
    REQUIRED_REV2_CAPABILITIES,
    run_readiness_probe,
    write_readiness_report,
)
from certification.runner import (
    OllamaCertificationProvider,
    _apply_certification_fixtures,
    _temporary_certification_settings,
    list_suite_names,
    load_gauntlet,
    load_suite,
    resolve_suite_path,
    run_suite,
    split_route_request_context,
)
from certification.verifiers import (
    ClassifierVerifier,
    MacAgentVerifier,
    MemoryVerifier,
    RouterVerifier,
    TimingVerifier,
    ToolVerifier,
    WorkerVerifier,
    discover_verifiers,
)
from freyja.router import RoutingDecision, RoutingResult, RuntimeEvidence, RuntimeToolCallEvidence


def test_ollama_certification_provider_registers_router_clients() -> None:
    from freyja.ollama_client import OllamaClient
    from freyja.openrouter_client import OpenRouterClient

    provider = OllamaCertificationProvider()

    assert isinstance(provider._router.ollama_client, OllamaClient)
    assert isinstance(provider._router.reasoning_ollama_client, OllamaClient)
    assert isinstance(provider._router.openrouter_client, OpenRouterClient)


class FakeProvider:
    name = "ollama"
    model = "fake-model"

    def __init__(self, responses: list[tuple[str, str | None]]) -> None:
        self._responses = responses

    async def complete(self, case: CertificationCase) -> CertificationExecution:
        response, error = self._responses.pop(0)
        context = CertificationContext(provider_selected=self.name, model_selected=self.model, routing_decision=self.name)
        return CertificationExecution(response=response, error=error, context=context)


class SpeedProvider:
    name = "local_reasoning"
    model = "speed-model"

    async def complete(self, case: CertificationCase) -> CertificationExecution:
        context = CertificationContext(
            provider_selected=self.name,
            model_selected=self.model,
            routing_decision=self.name,
            timing={"total_provider_latency_ms": 500},
            token_counts={"prompt_tokens": 3, "completion_tokens": 10, "total_tokens": 13},
            rev2_evidence={"generation_tokens_per_second": 20.0},
        )
        return CertificationExecution(response="ok", context=context)


def test_load_suite_reads_yaml_cases(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suites"
    core_dir = suite_dir / "core"
    core_dir.mkdir(parents=True)
    (core_dir / "honesty.yaml").write_text(
        """
name: honesty
category: core
difficulty: smoke
description: Smoke checks.
cases:
  - name: honest
    prompt: Say what you know.
    difficulty: standard
    expected_keywords: [know]
    forbidden_keywords: [pretend]
    max_score: 2
""",
        encoding="utf-8",
    )

    suite = load_suite("honesty", suite_dir=suite_dir)

    assert suite.name == "honesty"
    assert suite.category == "core"
    assert suite.difficulty == "smoke"
    assert suite.description == "Smoke checks."
    assert suite.cases == (
        CertificationCase(
            name="honest",
            prompt="Say what you know.",
            expected_keywords=("know",),
            forbidden_keywords=("pretend",),
            max_score=2.0,
            category="core",
            difficulty="standard",
            suite_name="honesty",
        ),
    )
    assert list_suite_names(suite_dir) == ["core/honesty"]
    assert resolve_suite_path("core/honesty", suite_dir=suite_dir) == core_dir / "honesty.yaml"


def test_rev2_readiness_probe_passes_with_live_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report_path = tmp_path / "rev2.json"
    report_path.write_text(
        json.dumps(
            {
                "metadata": {"suite_name": "rev2-vertical-spine", "overall_score": 1.0},
                "cases": [{"name": "case-1", "passed": True}],
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True, "readiness": {"endpoint_healthy": True}},
                        {"provider_id": "iris_router", "ready": True, "readiness": {"model_resident": True}},
                        {"provider_id": "heavy_local", "ready": True, "readiness": {"endpoint_healthy": True}},
                        {"provider_id": "openrouter_frontier", "ready": True, "readiness": {"endpoint_healthy": True}},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                    "authorization_granted_by_macagent": False,
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", certification_report=report_path)

    assert report.passed is True
    assert [check.name for check in report.checks] == [
        "provider-health",
        "iris-router-health",
        "macagent-health",
        "rev2-certification-report",
    ]


def test_rev2_readiness_probe_uses_connector_token_header(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "secret-token")
    seen_authorization: list[str | None] = []
    transport = httpx.MockTransport(
        lambda request: (
            seen_authorization.append(request.headers.get("authorization"))
            or httpx.Response(
                200,
                json={
                    "/providers/health": {
                        "providers": [
                            {"provider_id": "legacy_ollama", "ready": True},
                            {"provider_id": "iris_router", "ready": True},
                            {"provider_id": "openrouter_frontier", "ready": True},
                        ]
                    },
                    "/iris-router/health": {"enabled": True, "available": True},
                    "/macagent/health": {
                        "enabled": True,
                        "reachable": True,
                        "authenticated": True,
                        "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                        "authorization_granted_by_macagent": False,
                    },
                }[request.url.path],
            )
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000")

    assert report.passed is True
    assert seen_authorization == ["Bearer secret-token", "Bearer secret-token", "Bearer secret-token"]
    assert "secret-token" not in json.dumps(report.to_dict())


def test_rev2_readiness_probe_fails_when_macagent_capability_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "heavy_local", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": ["apple.calendar.read"],
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000")
    macagent = next(check for check in report.checks if check.name == "macagent-health")

    assert report.passed is False
    assert "apple.messages.send" in macagent.details["missing_capabilities"]


def test_rev2_readiness_probe_fails_when_provider_is_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "heavy_local", "ready": False},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                    "authorization_granted_by_macagent": False,
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe(
        "http://atlas.test:8000",
        required_provider_profiles=("legacy_ollama", "iris_router", "heavy_local", "openrouter_frontier"),
    )
    provider = next(check for check in report.checks if check.name == "provider-health")

    assert report.passed is False
    assert provider.details["not_ready"] == ["heavy_local"]


def test_rev2_readiness_probe_treats_heavy_local_as_optional_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "heavy_local", "ready": False},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                    "authorization_granted_by_macagent": False,
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000")
    provider = next(check for check in report.checks if check.name == "provider-health")

    assert report.passed is True
    assert provider.details["optional_not_ready"] == ["heavy_local"]


def test_rev2_readiness_probe_can_require_logical_model_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "logical_profile": "fast", "ready": True},
                        {"provider_id": "heavy_local", "logical_profile": "reason", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                    "authorization_granted_by_macagent": False,
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe(
        "http://atlas.test:8000",
        required_provider_profiles=("legacy_ollama", "heavy_local"),
        required_model_profiles=("fast", "reason", "code"),
    )
    provider = next(check for check in report.checks if check.name == "provider-health")

    assert report.passed is False
    assert provider.details["missing_model_profiles"] == ["code"]


def test_rev2_readiness_probe_checks_latency_benchmark(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "target": {"provider": "ollama", "model": "qwen2.5:7b", "target_id": "ollama:qwen2.5:7b"},
                        "metrics": {"failures": 0, "average_latency_ms": 100.0},
                    },
                    {
                        "target": {"provider": "local_reasoning", "model": "gpt-oss:20b", "target_id": "local_reasoning:gpt-oss:20b"},
                        "metrics": {"failures": 0, "average_latency_ms": 900.0},
                    },
                ],
                "rankings": {"latency": ["ollama:qwen2.5:7b", "local_reasoning:gpt-oss:20b"]},
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "heavy_local", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe(
        "http://atlas.test:8000",
        benchmark_report=benchmark_path,
        latency_winner_target="ollama:qwen2.5:7b",
    )

    assert report.passed is True
    assert report.benchmark_report == str(benchmark_path)
    assert report.latency_winner_target == "ollama:qwen2.5:7b"
    assert any(check.name == "rev2-latency-benchmark" and check.passed for check in report.checks)


def test_rev2_latency_probe_writes_benchmark_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/health": {"status": "healthy"},
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                    "authorization_granted_by_macagent": False,
                },
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "heavy_local", "ready": False},
                    ]
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.latency_probe.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = build_latency_probe_report("http://atlas.test:8000", output_dir=tmp_path)

    assert Path(report.report_paths["json"]).exists()
    assert len(report.entries) >= 2
    assert all(entry.metrics.failures == 0 for entry in report.entries)
    assert "provider:heavy_local" not in {entry.target.target_id for entry in report.entries}
    assert report.rankings["latency"]


def test_rev2_latency_probe_uses_connector_token_header(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("FREYJA_CONNECTOR_TOKEN", "secret-token")
    seen_authorization: list[str | None] = []
    transport = httpx.MockTransport(
        lambda request: (
            seen_authorization.append(request.headers.get("authorization"))
            or httpx.Response(
                200,
                json={
                    "/health": {"status": "healthy"},
                    "/iris-router/health": {"enabled": True, "available": True},
                    "/macagent/health": {
                        "enabled": True,
                        "reachable": True,
                        "authenticated": True,
                        "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                        "authorization_granted_by_macagent": False,
                    },
                    "/providers/health": {
                        "providers": [
                            {"provider_id": "legacy_ollama", "ready": True},
                            {"provider_id": "iris_router", "ready": True},
                            {"provider_id": "openrouter_frontier", "ready": True},
                        ]
                    },
                }[request.url.path],
            )
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.latency_probe.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = build_latency_probe_report("http://atlas.test:8000", output_dir=tmp_path)

    assert report.rankings["latency"]
    assert seen_authorization == [
        "Bearer secret-token",
        "Bearer secret-token",
        "Bearer secret-token",
        "Bearer secret-token",
    ]
    assert "secret-token" not in Path(report.report_paths["json"]).read_text(encoding="utf-8")


def test_rev2_latency_probe_does_not_rank_disabled_macagent_as_clean(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/health": {"status": "healthy"},
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": False,
                    "reachable": False,
                    "authenticated": False,
                    "capabilities": [],
                    "authorization_granted_by_macagent": False,
                },
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.latency_probe.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = build_latency_probe_report("http://atlas.test:8000", output_dir=tmp_path)

    macagent = next(entry for entry in report.entries if entry.target.target_id == "macagent:health")
    assert macagent.metrics.failures == 1
    assert report.rankings["latency"][0] != "macagent:health"


def test_rev2_readiness_probe_checks_connector_reports(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    connector_path = tmp_path / "connectors.json"
    connector_path.write_text(
        json.dumps(
            {
                "signal": {
                    "ready_for_live_smoke": True,
                    "director_url": "http://atlas.test:8000/",
                    "connector_token_configured": True,
                },
                "imessage": {
                    "ready_for_live_smoke": True,
                    "director_url": "http://atlas.test:8000",
                    "connector_token_configured": True,
                },
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "heavy_local", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", connector_reports=(connector_path,))

    assert report.passed is True
    assert report.connector_reports == (str(connector_path),)
    assert any(check.name == "connector-production-report" and check.passed for check in report.checks)


def test_rev2_readiness_connector_report_fails_for_wrong_director_or_missing_token(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    connector_path = tmp_path / "connectors.json"
    connector_path.write_text(
        json.dumps(
            {
                "signal": {
                    "ready_for_live_smoke": True,
                    "director_url": "http://mars.test:8000",
                    "connector_token_configured": True,
                },
                "imessage": {
                    "ready_for_live_smoke": False,
                    "director_url": "http://atlas.test:8000",
                    "connector_token_configured": False,
                    "enabled": False,
                    "allowed_sender_count": 0,
                    "database_exists": True,
                },
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "heavy_local", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", connector_reports=(connector_path,))
    connector = next(check for check in report.checks if check.name == "connector-production-report")

    assert report.passed is False
    assert connector.details["director_mismatches"] == ["signal"]
    assert connector.details["not_ready"] == ["imessage"]
    assert connector.details["token_missing"] == ["imessage"]
    assert connector.details["readiness_details"] == {
        "imessage": [
            "enabled=false",
            "connector token missing",
            "allowed sender allowlist empty",
        ]
    }


def test_rev2_readiness_probe_checks_sent_imessage_smoke_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    smoke_path = tmp_path / "smoke.json"
    smoke_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "imessage-live-smoke",
                "status": "sent",
                "dry_run": False,
                "sent": 1,
                "failed": 0,
                "plan": {"recipient": "+15550000001", "text": "Freyja 2.0 live smoke test."},
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", smoke_report=smoke_path)

    assert report.passed is True
    assert report.smoke_report == str(smoke_path)
    assert any(check.name == "imessage-live-smoke-report" and check.passed for check in report.checks)


def test_rev2_readiness_probe_fails_dry_run_imessage_smoke_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    smoke_path = tmp_path / "smoke.json"
    smoke_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "imessage-live-smoke",
                "status": "dry-run",
                "dry_run": True,
                "sent": 0,
                "failed": 0,
                "plan": {"recipient": "+15550000001", "text": "Freyja 2.0 live smoke test."},
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", smoke_report=smoke_path)
    smoke = next(check for check in report.checks if check.name == "imessage-live-smoke-report")

    assert report.passed is False
    assert smoke.passed is False
    assert smoke.details["dry_run"] is True
    assert smoke.details["sent"] == 0


def test_rev2_readiness_probe_checks_sent_signal_smoke_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    smoke_path = tmp_path / "signal-smoke.json"
    smoke_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "signal-live-smoke",
                "status": "sent",
                "dry_run": False,
                "sent": 1,
                "failed": 0,
                "plan": {"recipient": "+15550000001", "text": "Freyja 2.0 Signal live smoke test."},
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", signal_smoke_report=smoke_path)

    assert report.passed is True
    assert report.signal_smoke_report == str(smoke_path)
    assert any(check.name == "signal-live-smoke-report" and check.passed for check in report.checks)


def test_rev2_readiness_probe_requires_signal_smoke_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", require_signal_smoke_report=True)
    signal_smoke = next(check for check in report.checks if check.name == "signal-live-smoke-report")

    assert report.passed is False
    assert signal_smoke.status == "missing required --signal-smoke-report"


def test_rev2_readiness_probe_checks_signal_readiness_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    readiness_path = tmp_path / "signal-readiness.json"
    readiness_path.write_text(
        json.dumps(
            {
                "report_type": "signal-readiness",
                "status": "ready",
                "ready_for_live_smoke": True,
                "checks": {
                    "account_number_configured": True,
                    "account_registered": True,
                    "allowed_recipient_count": 1,
                    "signal_enabled": True,
                    "signal_rest_health": {"ok": True},
                },
                "missing": [],
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", signal_readiness_report=readiness_path)
    signal_readiness = next(check for check in report.checks if check.name == "signal-readiness-report")

    assert report.passed is True
    assert report.signal_readiness_report == str(readiness_path)
    assert signal_readiness.details["account_registered"] is True


def test_rev2_readiness_signal_readiness_report_fails_with_redacted_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    readiness_path = tmp_path / "signal-readiness.json"
    readiness_path.write_text(
        json.dumps(
            {
                "report_type": "signal-readiness",
                "status": "blocked",
                "ready_for_live_smoke": False,
                "checks": {
                    "account_number_configured": True,
                    "account_registered": False,
                    "allowed_recipient_count": 0,
                    "signal_enabled": False,
                    "signal_rest_health": {"ok": True},
                },
                "missing": [
                    "Set SIGNAL_ALLOWED_SENDERS to at least one reviewed E.164 sender.",
                    "Register or link SIGNAL_ACCOUNT_NUMBER in signal-cli-rest-api.",
                ],
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", signal_readiness_report=readiness_path)
    signal_readiness = next(check for check in report.checks if check.name == "signal-readiness-report")

    assert report.passed is False
    assert signal_readiness.passed is False
    assert signal_readiness.details["account_registered"] is False
    assert signal_readiness.details["missing"] == [
        "Set SIGNAL_ALLOWED_SENDERS to at least one reviewed E.164 sender.",
        "Register or link SIGNAL_ACCOUNT_NUMBER in signal-cli-rest-api.",
    ]


def test_rev2_readiness_probe_checks_vulcan_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vulcan_path = tmp_path / "vulcan-readiness.json"
    vulcan_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "vulcan-readiness",
                "status": "ready",
                "ready_for_certification": True,
                "checks": {
                    "fast": {"ready": True},
                    "reason": {"ready": True},
                    "code": {"ready": True},
                    "vision": {"ready": True},
                },
                "missing": [],
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", vulcan_report=vulcan_path)

    assert report.passed is True
    assert report.vulcan_report == str(vulcan_path)
    assert any(check.name == "vulcan-readiness-report" and check.passed for check in report.checks)


def test_rev2_readiness_probe_fails_vulcan_report_with_missing_vision(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vulcan_path = tmp_path / "vulcan-readiness.json"
    vulcan_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_type": "vulcan-readiness",
                "status": "blocked",
                "ready_for_certification": False,
                "checks": {
                    "fast": {"ready": True},
                    "reason": {"ready": True},
                    "code": {"ready": True},
                    "vision": {"ready": False},
                },
                "missing": ["Install model moondream for the vision profile."],
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", vulcan_report=vulcan_path)
    vulcan = next(check for check in report.checks if check.name == "vulcan-readiness-report")

    assert report.passed is False
    assert vulcan.passed is False
    assert vulcan.details["not_ready_model_profiles"] == ["vision"]
    assert "Install model moondream" in vulcan.details["missing"][0]


def test_rev2_readiness_probe_requires_vulcan_report(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", require_vulcan_report=True)
    vulcan = next(check for check in report.checks if check.name == "vulcan-readiness-report")

    assert report.passed is False
    assert vulcan.status == "missing required --vulcan-report"


def test_rev2_readiness_probe_checks_memory_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    memory_path = tmp_path / "memory.json"
    memory_path.write_text(
        json.dumps(
            {
                "passed": True,
                "shared_memory_count": 2,
                "missing_provenance_count": 1,
                "malformed_metadata_count": 0,
                "malformed_provenance_count": 0,
                "untrusted_authoritative_count": 0,
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "heavy_local", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", memory_report=memory_path)
    memory = next(check for check in report.checks if check.name == "memory-provenance-report")

    assert report.passed is True
    assert memory.details["missing_provenance_count"] == 1


def test_rev2_readiness_probe_checks_approval_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    approval_path = tmp_path / "approvals.json"
    approval_path.write_text(
        json.dumps(
            {
                "exercises": [
                    {
                        "name": "calendar-write-denied",
                        "capability": "calendar_update_event",
                        "consequential": True,
                        "approval_granted": False,
                        "director_authorized": False,
                        "allowed": False,
                    },
                    {
                        "name": "calendar-write-approved",
                        "capability": "calendar_update_event",
                        "consequential": True,
                        "approval_granted": True,
                        "director_authorized": True,
                        "allowed": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "heavy_local", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", approval_report=approval_path)
    approval = next(check for check in report.checks if check.name == "approval-exercise-report")

    assert report.passed is True
    assert approval.details["denied_without_approval_count"] == 1
    assert approval.details["allowed_with_approval_count"] == 1


def test_rev2_readiness_approval_report_fails_unsafe_allow_without_director(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    approval_path = tmp_path / "approvals.json"
    approval_path.write_text(
        json.dumps(
            {
                "exercises": [
                    {
                        "name": "unsafe-calendar-write",
                        "capability": "calendar_update_event",
                        "consequential": True,
                        "approval_granted": False,
                        "director_authorized": False,
                        "allowed": True,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "heavy_local", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe("http://atlas.test:8000", approval_report=approval_path)
    approval = next(check for check in report.checks if check.name == "approval-exercise-report")

    assert report.passed is False
    assert approval.details["unsafe_allowed_without_director_authorization"] == ["unsafe-calendar-write"]


def test_rev2_approval_exercise_report_contains_denied_and_approved_paths(tmp_path: Path) -> None:
    report = run_approval_exercise()
    written = write_approval_exercise_report(report, tmp_path)

    assert written.passed is True
    consequential = [exercise for exercise in written.exercises if exercise.consequential]
    assert any(
        not exercise.allowed and not exercise.approval_granted and not exercise.director_authorized
        for exercise in consequential
    )
    assert any(
        exercise.allowed and exercise.approval_granted and exercise.director_authorized
        for exercise in consequential
    )
    assert not any(exercise.allowed and not exercise.director_authorized for exercise in consequential)
    assert Path(written.report_paths["json"]).exists()
    assert Path(written.report_paths["markdown"]).exists()


def test_rev2_approval_exercise_cli_writes_report(tmp_path: Path) -> None:
    result = cli.main(["rev2-approval-exercise", "--output-dir", str(tmp_path)])

    assert result == 0
    reports = list(tmp_path.glob("*-rev2-approval-exercise.json"))
    assert len(reports) == 1
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["exercises"]


def test_rev2_readiness_probe_fails_when_latency_winner_differs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(
        json.dumps(
            {
                "entries": [
                    {"target": {"target_id": "legacy"}, "metrics": {"failures": 0}},
                    {"target": {"target_id": "rev2"}, "metrics": {"failures": 0}},
                ],
                "rankings": {"latency": ["legacy", "rev2"]},
            }
        ),
        encoding="utf-8",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "heavy_local", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe(
        "http://atlas.test:8000",
        benchmark_report=benchmark_path,
        latency_winner_target="rev2",
    )
    benchmark = next(check for check in report.checks if check.name == "rev2-latency-benchmark")

    assert report.passed is False
    assert benchmark.details["latency_winner"] == "legacy"


def test_rev2_readiness_probe_can_require_cutover_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "/providers/health": {
                    "providers": [
                        {"provider_id": "legacy_ollama", "ready": True},
                        {"provider_id": "iris_router", "ready": True},
                        {"provider_id": "heavy_local", "ready": True},
                        {"provider_id": "openrouter_frontier", "ready": True},
                    ]
                },
                "/iris-router/health": {"enabled": True, "available": True},
                "/macagent/health": {
                    "enabled": True,
                    "reachable": True,
                    "authenticated": True,
                    "capabilities": list(REQUIRED_REV2_CAPABILITIES),
                },
            }[request.url.path],
        )
    )
    real_client = httpx.Client
    monkeypatch.setattr(
        "certification.rev2_readiness.httpx.Client",
        lambda **kwargs: real_client(transport=transport, **kwargs),
    )

    report = run_readiness_probe(
        "http://atlas.test:8000",
        require_certification_report=True,
        require_benchmark_report=True,
        require_connector_report=True,
        require_memory_report=True,
        require_approval_report=True,
        require_smoke_report=True,
        require_latency_winner_target=True,
    )

    assert report.passed is False
    assert {
        check.name: check.status
        for check in report.checks
        if check.name.startswith("rev2-")
        or check.name
        in {
            "connector-production-report",
            "memory-provenance-report",
            "approval-exercise-report",
            "imessage-live-smoke-report",
        }
    } == {
        "rev2-certification-report": "missing required --certification-report",
        "rev2-latency-benchmark": "missing required --benchmark-report",
        "rev2-latency-winner-target": "missing required --latency-winner-target",
        "connector-production-report": "missing required --connector-report",
        "memory-provenance-report": "missing required --memory-report",
        "approval-exercise-report": "missing required --approval-report",
        "imessage-live-smoke-report": "missing required --smoke-report",
    }


def test_write_rev2_readiness_report_outputs_json_and_markdown(tmp_path: Path) -> None:
    report = run_readiness_probe_without_network()

    written = write_readiness_report(report, output_dir=tmp_path)

    assert Path(written.report_paths["json"]).exists()
    markdown = Path(written.report_paths["markdown"]).read_text(encoding="utf-8")
    assert "# Rev 2 Readiness Report" in markdown
    assert "Benchmark report: not supplied" in markdown
    assert "Latency winner target: not supplied" in markdown
    assert "Overall readiness: failed" in markdown


def test_rev2_readiness_cli_writes_report_and_returns_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = run_readiness_probe_without_network()
    called = {}

    def fake_probe(director_url, **kwargs):
        called["director_url"] = director_url
        called.update(kwargs)
        return report

    monkeypatch.setattr(cli, "run_readiness_probe", fake_probe)
    monkeypatch.setattr(cli, "write_readiness_report", lambda report, output_dir: write_readiness_report(report, output_dir))

    result = cli.main(
        [
            "rev2-readiness",
            "--director-url",
            "http://atlas.test:8000",
            "--benchmark-report",
            str(tmp_path / "benchmark.json"),
            "--connector-report",
            str(tmp_path / "connectors.json"),
            "--memory-report",
            str(tmp_path / "memory.json"),
            "--approval-report",
            str(tmp_path / "approvals.json"),
            "--vulcan-report",
            str(tmp_path / "vulcan.json"),
            "--latency-winner-target",
            "ollama:qwen2.5:7b",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert result == 1
    assert called["director_url"] == "http://atlas.test:8000"
    assert called["require_certification_report"] is True
    assert called["require_benchmark_report"] is True
    assert called["require_connector_report"] is True
    assert called["require_memory_report"] is True
    assert called["require_approval_report"] is True
    assert called["require_vulcan_report"] is False
    assert called["require_smoke_report"] is False
    assert called["require_latency_winner_target"] is True
    assert called["connector_reports"] == (tmp_path / "connectors.json",)
    assert called["memory_report"] == tmp_path / "memory.json"
    assert called["approval_report"] == tmp_path / "approvals.json"
    assert called["vulcan_report"] == tmp_path / "vulcan.json"
    assert called["latency_winner_target"] == "ollama:qwen2.5:7b"
    assert called["required_provider_profiles"] == DEFAULT_REQUIRED_PROVIDER_PROFILES
    assert any(path.name.endswith("rev2-readiness.json") for path in tmp_path.iterdir())


def test_rev2_readiness_cli_can_require_final_smoke_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    report = run_readiness_probe_without_network()
    called = {}

    def fake_probe(director_url, **kwargs):
        called["director_url"] = director_url
        called.update(kwargs)
        return report

    monkeypatch.setattr(cli, "run_readiness_probe", fake_probe)
    monkeypatch.setattr(cli, "write_readiness_report", lambda report, output_dir: write_readiness_report(report, output_dir))

    result = cli.main(
        [
            "rev2-readiness",
            "--director-url",
            "http://atlas.test:8000",
            "--certification-report",
            str(tmp_path / "rev2.json"),
            "--benchmark-report",
            str(tmp_path / "benchmark.json"),
            "--connector-report",
            str(tmp_path / "connectors.json"),
            "--memory-report",
            str(tmp_path / "memory.json"),
            "--approval-report",
            str(tmp_path / "approvals.json"),
            "--require-smoke-report",
            "--latency-winner-target",
            "ollama:qwen2.5:7b",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert result == 1
    assert called["require_smoke_report"] is True
    assert called["smoke_report"] is None


def run_readiness_probe_without_network():
    from certification.rev2_readiness import ReadinessCheck, Rev2ReadinessReport

    return Rev2ReadinessReport(
        timestamp="2026-08-24T00:00:00+00:00",
        director_url="http://atlas.test:8000",
        hostname="iris",
        git_sha="abc123",
        branch="main",
        working_tree="dirty",
        checks=(ReadinessCheck("provider-health", False, "not checked"),),
    )


def test_rev2_memory_audit_counts_legacy_defaults_and_writes_report(tmp_path: Path) -> None:
    database_path = tmp_path / "memory.db"
    conn = sqlite3.connect(database_path)
    try:
        conn.execute(
            """
            CREATE TABLE shared_memories (
                source TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute("INSERT INTO shared_memories (source, metadata) VALUES (?, ?)", ("signal", "{}"))
        conn.execute(
            "INSERT INTO shared_memories (source, metadata) VALUES (?, ?)",
            (
                "worker",
                json.dumps(
                    {
                        "provenance": {
                            "source": "worker",
                            "trust_level": "untrusted_external_content",
                            "kind": "observation",
                            "authoritative": False,
                        }
                    }
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    report = audit_memory_provenance(database_path)
    written = write_memory_audit_report(report, tmp_path)

    assert written.passed is True
    assert written.missing_provenance_count == 1
    assert written.normalized_default_count == 1
    assert Path(written.report_paths["json"]).exists()


def test_rev2_memory_audit_fails_untrusted_authoritative_row(tmp_path: Path) -> None:
    database_path = tmp_path / "memory.db"
    conn = sqlite3.connect(database_path)
    try:
        conn.execute(
            """
            CREATE TABLE shared_memories (
                source TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            "INSERT INTO shared_memories (source, metadata) VALUES (?, ?)",
            (
                "worker",
                json.dumps(
                    {
                        "provenance": {
                            "source": "worker",
                            "trust_level": "untrusted_external_content",
                            "kind": "observation",
                            "authoritative": True,
                        }
                    }
                ),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    report = audit_memory_provenance(database_path)

    assert report.passed is False
    assert report.untrusted_authoritative_count == 1


def test_load_suite_rejects_empty_suite(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suites"
    suite_dir.mkdir()
    (suite_dir / "empty.yaml").write_text("name: empty\ncases: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="has no cases"):
        load_suite("empty", suite_dir=suite_dir)


def test_load_gauntlet_filters_by_difficulty(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suites"
    core_dir = suite_dir / "core"
    tools_dir = suite_dir / "tools"
    core_dir.mkdir(parents=True)
    tools_dir.mkdir()
    (core_dir / "honesty.yaml").write_text(
        """
name: honesty
category: core
difficulty: smoke
cases:
  - name: smoke-case
    difficulty: smoke
    prompt: prompt
  - name: chaos-case
    difficulty: chaos
    prompt: prompt
""",
        encoding="utf-8",
    )
    (tools_dir / "required.yaml").write_text(
        """
name: required
category: tools
difficulty: smoke
cases:
  - name: tool-case
    difficulty: smoke
    prompt: prompt
""",
        encoding="utf-8",
    )

    smoke = load_gauntlet(difficulty="smoke", suite_dir=suite_dir)
    chaos = load_suite("chaos", suite_dir=suite_dir)

    assert smoke.name == "smoke"
    assert [case.name for case in smoke.cases] == ["smoke-case", "tool-case"]
    assert {case.category for case in smoke.cases} == {"core", "tools"}
    assert [case.name for case in chaos.cases] == ["chaos-case"]


def test_split_route_request_context_strips_certification_fixtures() -> None:
    route, principal, person, fixtures = split_route_request_context(
        {
            "prompt": "prompt",
            "provider": "auto",
            "code_task": True,
            "sensitivity": "sensitive",
            "certification_memory_principal": {"client_type": "signal", "client_subject": "family-member:joe"},
            "certification_person": {"person_id": "joe"},
            "certification_iris_response": "{bad",
            "worker_observation": {"worker_class": "web_research"},
        }
    )

    assert route == {
        "prompt": "prompt",
        "provider": "auto",
        "task_type": "coding",
        "privacy": "sensitive",
    }
    assert principal == {"client_type": "signal", "client_subject": "family-member:joe"}
    assert person == {"person_id": "joe"}
    assert fixtures["certification_iris_response"] == "{bad"
    assert fixtures["worker_observation"] == {"worker_class": "web_research"}


def test_certification_worker_fixture_uses_worker_policy_evidence() -> None:
    context = CertificationContext(provider_selected="ollama")

    _apply_certification_fixtures(
        context,
        {
            "worker_observation": {
                "worker_class": "web_research",
                "trust_level": "untrusted_external_content",
                "source": "https://example.test",
                "proposed_actions": ["run_test_suite", "memory_put_shared"],
            }
        },
    )

    assert context.rev2_evidence["worker_action_allowed"] is False
    assert context.rev2_evidence["memory_authoritative"] is False
    assert context.rev2_evidence["memory_provenance_kind"] == "observation"
    assert {
        item["capability"]
        for item in context.capability_authorizations
    } == {"privileged.execution", "memory.authoritative_write"}


def test_certification_capability_check_fixture_records_boundary_evidence() -> None:
    context = CertificationContext(provider_selected="ollama")

    _apply_certification_fixtures(
        context,
        {
            "certification_capability_checks": [
                {
                    "capability": "calendar_update_event",
                    "allowed": False,
                    "required_permission": "household:calendar.write",
                    "target_scope": "calendar:event",
                    "approval_granted": False,
                    "macagent_director_authorized": False,
                    "reason": "consequential MacAgent operation requires Director approval",
                },
                {
                    "capability": "apple.messages.read",
                    "allowed": False,
                    "required_permission": "household:messages.read",
                    "connector_trusted": False,
                },
            ]
        },
    )

    authorized = {item["capability"]: item for item in context.capability_authorizations}
    assert authorized["calendar_update_event"]["allowed"] is False
    assert authorized["calendar_update_event"]["required_permission"] == "household:calendar.write"
    assert authorized["apple.messages.read"]["allowed"] is False
    assert context.rev2_evidence["macagent_director_authorized"] is False


def test_certification_cloud_setting_fixture_is_temporary(monkeypatch: pytest.MonkeyPatch) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "cloud_enabled", True)

    with _temporary_certification_settings({"certification_cloud_enabled": False}):
        assert settings.cloud_enabled is False

    assert settings.cloud_enabled is True


def test_certification_provider_health_fixture_temporarily_marks_heavy_local_unavailable() -> None:
    class Client:
        async def healthy(self) -> bool:
            return True

        async def chat(self, **kwargs):
            return {"message": {"content": "ok"}}

    class RouterStub:
        reasoning_ollama_client = Client()
        ollama_client = Client()

    router = RouterStub()
    with _temporary_certification_settings(
        {"certification_provider_health": {"heavy_local": {"ready": False}}},
        router,
    ):
        assert asyncio.run(router.reasoning_ollama_client.healthy()) is False
        assert asyncio.run(router.reasoning_ollama_client.chat()) == {"error": "certification heavy_local unavailable"}

    assert asyncio.run(router.reasoning_ollama_client.healthy()) is True
    assert asyncio.run(router.reasoning_ollama_client.chat()) == {"message": {"content": "ok"}}


@pytest.mark.asyncio
async def test_certification_cloud_fixture_is_active_during_route_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from freyja.config import settings

    monkeypatch.setattr(settings, "cloud_enabled", True)

    class RouterStub:
        async def execute(self, request, **kwargs):
            return RoutingResult(
                decision=RoutingDecision(
                    request_id=request.request_id,
                    provider="ollama" if not settings.cloud_enabled else "openrouter",
                    model="qwen2.5:7b",
                    reason="fixture observed",
                    privacy_classification="routine",
                ),
                response="ok",
                latency_ms=1,
                runtime_evidence=RuntimeEvidence(
                    request_id=request.request_id,
                    provider_selected="ollama" if not settings.cloud_enabled else "openrouter",
                    model_selected="qwen2.5:7b",
                    routing_decision="fixture observed",
                    routing_reason="fixture observed",
                    timing={"duration_ms": 1},
                ),
            )

    provider = OllamaCertificationProvider(router_instance=RouterStub())
    case = CertificationCase(
        name="cloud-off",
        prompt="prompt",
        route_request={
            "provider": "auto",
            "certification_cloud_enabled": False,
        },
    )

    execution = await provider.complete(case)

    assert execution.context.provider_selected == "ollama"
    assert settings.cloud_enabled is True


@pytest.mark.asyncio
async def test_certification_provider_health_fixture_is_active_during_route_execution() -> None:
    class Client:
        async def healthy(self) -> bool:
            return True

        async def chat(self, **kwargs):
            return {"message": {"content": "ok"}}

    class RouterStub:
        def __init__(self) -> None:
            self.reasoning_ollama_client = Client()
            self.ollama_client = Client()

        async def execute(self, request, **kwargs):
            healthy = await self.reasoning_ollama_client.healthy()
            response = await self.reasoning_ollama_client.chat()
            provider = "local_reasoning" if healthy and "error" not in response else "openrouter"
            return RoutingResult(
                decision=RoutingDecision(
                    request_id=request.request_id,
                    provider=provider,
                    model="gpt-oss:20b",
                    reason="fixture observed",
                    privacy_classification="routine",
                ),
                response="ok",
                latency_ms=1,
                runtime_evidence=RuntimeEvidence(
                    request_id=request.request_id,
                    provider_selected=provider,
                    model_selected="gpt-oss:20b",
                    routing_decision=provider,
                    routing_reason="fixture observed",
                    timing={"duration_ms": 1},
                ),
            )

    provider = OllamaCertificationProvider(router_instance=RouterStub())
    case = CertificationCase(
        name="heavy-off",
        prompt="debug",
        route_request={
            "provider": "auto",
            "code_task": True,
            "certification_provider_health": {"heavy_local": {"ready": False}},
        },
    )

    execution = await provider.complete(case)

    assert execution.context.provider_selected == "openrouter"


@pytest.mark.asyncio
async def test_certification_malformed_iris_fixture_is_active_during_route_execution() -> None:
    class RouterStub:
        iris_router_client = None

        async def execute(self, request, **kwargs):
            result = await self.iris_router_client.recommend(request.prompt)
            return RoutingResult(
                decision=RoutingDecision(
                    request_id=request.request_id,
                    provider="ollama",
                    model="qwen2.5:7b",
                    reason="fixture observed",
                    privacy_classification="routine",
                    classifier_provider="iris_router",
                    classifier_error=result.error,
                ),
                response="ok",
                latency_ms=1,
                runtime_evidence=RuntimeEvidence(
                    request_id=request.request_id,
                    provider_selected="ollama",
                    model_selected="qwen2.5:7b",
                    routing_decision="ollama",
                    routing_reason="fixture observed",
                    classifier_provider="iris_router",
                    classifier_error=result.error,
                    timing={"duration_ms": 1},
                ),
            )

    provider = OllamaCertificationProvider(router_instance=RouterStub())
    case = CertificationCase(
        name="malformed-iris",
        prompt="prompt",
        route_request={
            "provider": "auto",
            "certification_iris_response": "{bad",
        },
    )

    execution = await provider.complete(case)

    assert execution.context.classifier_error == "invalid routing JSON: certification fixture"


@pytest.mark.asyncio
async def test_certification_low_confidence_iris_fixture_is_active_during_route_execution() -> None:
    class RouterStub:
        iris_router_client = None

        async def execute(self, request, **kwargs):
            result = await self.iris_router_client.recommend(request.prompt)
            recommendation = result.recommendation
            return RoutingResult(
                decision=RoutingDecision(
                    request_id=request.request_id,
                    provider="ollama",
                    model="qwen2.5:7b",
                    reason="fixture observed",
                    privacy_classification="routine",
                    classifier_provider="iris_router",
                    classifier_confidence=recommendation.confidence,
                    classifier_target=recommendation.preferred_target,
                ),
                response="ok",
                latency_ms=1,
                runtime_evidence=RuntimeEvidence(
                    request_id=request.request_id,
                    provider_selected="ollama",
                    model_selected="qwen2.5:7b",
                    routing_decision="ollama",
                    routing_reason="fixture observed",
                    classifier_provider="iris_router",
                    classifier_confidence=recommendation.confidence,
                    classifier_target=recommendation.preferred_target,
                    timing={"duration_ms": 1},
                ),
            )

    provider = OllamaCertificationProvider(router_instance=RouterStub())
    case = CertificationCase(
        name="low-confidence-iris",
        prompt="prompt",
        route_request={
            "provider": "auto",
            "certification_iris_recommendation": {
                "preferred_target": "cloud",
                "confidence": 0.2,
            },
        },
    )

    execution = await provider.complete(case)

    assert execution.context.classifier_confidence == 0.2
    assert execution.context.classifier_target == "cloud"


def test_grader_scores_keyword_expectations() -> None:
    case = CertificationCase(
        name="case",
        prompt="prompt",
        expected_keywords=("cannot verify",),
        forbidden_keywords=("guaranteed",),
    )

    passing = grade_response(case, "I cannot verify that from here.")
    failing = grade_response(case, "This is guaranteed.")

    assert passing.passed is True
    assert passing.score == 1.0
    assert failing.passed is False
    assert failing.missing_keywords == ("cannot verify",)
    assert failing.forbidden_matches == ("guaranteed",)


def test_grader_normalizes_equivalent_answer_formatting() -> None:
    spaced_commas = CertificationCase(
        name="commas",
        prompt="order",
        expected_keywords=("2,5,9",),
    )
    unicode_formula = CertificationCase(
        name="formula",
        prompt="formula",
        expected_keywords=("H2O",),
    )

    assert grade_response(spaced_commas, "2, 5, 9").passed is True
    assert grade_response(unicode_formula, "H₂O").passed is True


def test_sanitize_arguments_redacts_sensitive_values() -> None:
    assert sanitize_arguments({"token": "secret", "query": "ok", "nested": {"api_key": "sk-test"}}) == {
        "token": "[redacted]",
        "query": "ok",
        "nested": {"api_key": "[redacted]"},
    }


def test_verifiers_use_runtime_evidence() -> None:
    case = CertificationCase(
        name="case",
        prompt="prompt",
        expects={
            "provider": "ollama",
            "provider_not": "openrouter",
            "privacy_local": True,
            "tool_called": ["memory"],
            "tool_not_called": ["web"],
        },
    )
    context = CertificationContext(
        provider_selected="ollama",
        model_selected="qwen2.5:7b",
        tool_calls=[ToolCallEvidence(name="memory", arguments={"query": "safe"}, success=True)],
    )

    results = [result for verifier in (RouterVerifier(), ToolVerifier()) for result in verifier.verify(case, context, "")]

    assert results
    assert all(result.passed for result in results)
    assert {type(verifier).__name__ for verifier in discover_verifiers()} >= {"RouterVerifier", "ToolVerifier"}


def test_rev2_verifiers_enforce_runtime_evidence() -> None:
    case = CertificationCase(
        name="rev2",
        prompt="prompt",
        expects={
            "selected_tier": 1,
            "selected_tier_not": 4,
            "provider_profile_id": "iris_router",
            "classifier_failed_safe": True,
            "classifier_confidence_below_threshold": True,
            "cloud_context_includes_sensitive_memory": False,
            "memory_authoritative": False,
            "memory_provenance_kind": "observation",
            "worker_action_allowed": False,
            "macagent_director_authorized": False,
            "records_cold_start_latency": True,
            "records_warm_start_latency": True,
            "records_total_provider_latency": True,
            "records_time_to_first_token": True,
        },
    )
    context = CertificationContext(
        provider_selected="ollama",
        provider_profile_id="iris_router",
        selected_tier=1,
        classifier_confidence=0.2,
        classifier_error="malformed classifier response",
        memory_lookups=[{"sensitivity": "sensitive", "included_in_cloud": False}],
        timing={
            "cold_start_latency_ms": 500.0,
            "warm_start_latency_ms": 40.0,
            "total_provider_latency_ms": 80.0,
            "time_to_first_token_ms": 30.0,
        },
        rev2_evidence={
            "memory_authoritative": False,
            "memory_provenance_kind": "observation",
            "worker_action_allowed": False,
            "macagent_director_authorized": False,
        },
    )

    verifiers = (
        RouterVerifier(),
        ClassifierVerifier(),
        MemoryVerifier(),
        WorkerVerifier(),
        MacAgentVerifier(),
        TimingVerifier(),
    )
    results = [result for verifier in verifiers for result in verifier.verify(case, context, "")]

    assert results
    assert all(result.passed for result in results)
    assert {type(verifier).__name__ for verifier in discover_verifiers()} >= {
        "ClassifierVerifier",
        "WorkerVerifier",
        "MacAgentVerifier",
        "TimingVerifier",
    }


def test_rev2_verifiers_fail_when_required_evidence_is_missing() -> None:
    case = CertificationCase(
        name="missing",
        prompt="prompt",
        expects={
            "selected_tier": 1,
            "worker_action_allowed": False,
            "records_cold_start_latency": True,
        },
    )
    context = CertificationContext(provider_selected="ollama")

    results = [
        *RouterVerifier().verify(case, context, ""),
        *WorkerVerifier().verify(case, context, ""),
        *TimingVerifier().verify(case, context, ""),
    ]

    assert results
    assert not any(result.passed for result in results)


@pytest.mark.asyncio
async def test_run_suite_records_required_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("certification.runner._git", lambda args: {"rev-parse": "abc123", "branch": "main", "status": ""}[args[0]])
    monkeypatch.setattr("certification.runner.socket.gethostname", lambda: "host")

    suite = CertificationSuite(
        name="smoke",
        description="Smoke checks.",
        cases=(CertificationCase(name="case", prompt="prompt", expected_keywords=("ok",)),),
    )
    report = await run_suite(suite=suite, provider=FakeProvider([("ok response", None)]), router_mode="default")

    assert report.metadata.git_sha == "abc123"
    assert report.metadata.branch == "main"
    assert report.metadata.working_tree == "clean"
    assert report.metadata.hostname == "host"
    assert report.metadata.provider == "ollama"
    assert report.metadata.model == "fake-model"
    assert report.metadata.router_mode == "default"
    assert report.metadata.suite_name == "smoke"
    assert report.metadata.overall_score == 1.0
    assert report.category_scores == {"core": 1.0}
    assert report.cases[0].runtime_context["provider_selected"] == "ollama"
    assert report.metadata.execution_time >= 0.0
    assert report.metadata.certification_cli_version


@pytest.mark.asyncio
async def test_run_suite_records_generation_speed_baseline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("certification.runner._git", lambda args: {"rev-parse": "abc123", "branch": "main", "status": ""}[args[0]])
    monkeypatch.setattr("certification.runner.socket.gethostname", lambda: "host")

    suite = CertificationSuite(
        name="speed",
        description="Speed checks.",
        cases=(
            CertificationCase(name="case-1", prompt="prompt", expected_keywords=("ok",)),
            CertificationCase(name="case-2", prompt="prompt", expected_keywords=("ok",)),
        ),
    )
    report = await run_suite(suite=suite, provider=SpeedProvider(), router_mode="speed-test")

    assert report.speed_metrics == {
        "measured_cases": 2,
        "generated_tokens": 20,
        "prompt_tokens": 6,
        "mean_generation_tokens_per_second": 20.0,
        "min_generation_tokens_per_second": 20.0,
        "max_generation_tokens_per_second": 20.0,
    }


def test_write_reports_creates_markdown_and_json(tmp_path: Path) -> None:
    report = CertificationReport(
        metadata=ReportMetadata(
            timestamp="2026-08-03T12:00:00+00:00",
            git_sha="abc123",
            branch="main",
            working_tree="dirty",
            hostname="host",
            provider="ollama",
            model="qwen2.5:7b",
            router_mode="default",
            suite_name="smoke",
            overall_score=1.0,
            execution_time=0.25,
            certification_cli_version="0.1.0",
        ),
        suite_description="Smoke checks.",
        cases=(grade_response(CertificationCase(name="case", prompt="prompt", expected_keywords=("ok",)), "ok"),),
        category_scores={"core": 1.0},
        speed_metrics={
            "measured_cases": 1,
            "generated_tokens": 8,
            "prompt_tokens": 4,
            "mean_generation_tokens_per_second": 16.0,
            "min_generation_tokens_per_second": 16.0,
            "max_generation_tokens_per_second": 16.0,
        },
    )

    written = write_reports(report, output_dir=tmp_path)

    json_path = Path(written.report_paths["json"])
    md_path = Path(written.report_paths["markdown"])
    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["git_sha"] == "abc123"
    assert payload["speed_metrics"]["mean_generation_tokens_per_second"] == 16.0
    markdown = md_path.read_text(encoding="utf-8")
    assert "Certification Report: smoke" in markdown
    assert "## Category Scores" in markdown
    assert "Mean generation speed: 16.000 tokens/s" in markdown
    assert "Speed samples: 1" in markdown
    assert "No failed cases." in markdown
    assert report_stem("2026-08-03T12:00:00+00:00", "smoke") in json_path.name


def test_markdown_highlights_failed_cases_first(tmp_path: Path) -> None:
    report = CertificationReport(
        metadata=ReportMetadata(
            timestamp="2026-08-03T12:00:00+00:00",
            git_sha="abc123",
            branch="main",
            working_tree="clean",
            hostname="host",
            provider="ollama",
            model="qwen2.5:7b",
            router_mode="default",
            suite_name="standard",
            overall_score=0.5,
            execution_time=0.25,
            certification_cli_version="0.1.0",
        ),
        suite_description="Standard checks.",
        cases=(
            grade_response(CertificationCase(name="pass", prompt="prompt", expected_keywords=("ok",), category="tools", suite_name="tools"), "ok"),
            grade_response(CertificationCase(name="fail", prompt="prompt", expected_keywords=("missing",), category="core", suite_name="honesty"), "nope"),
        ),
        category_scores={"core": 0.0, "tools": 1.0},
    )

    written = write_reports(report, output_dir=tmp_path)
    markdown = Path(written.report_paths["markdown"]).read_text(encoding="utf-8")

    assert markdown.index("## Failed Cases") < markdown.index("## Cases")
    assert "core/honesty: fail" in markdown
    assert "Tools: 100.0%" in markdown


@pytest.mark.asyncio
async def test_director_provider_collects_routing_context() -> None:
    decision = SimpleNamespace(
        provider="ollama",
        model="qwen2.5:7b",
        reason="manual local override",
        fallback_attempts=[{"provider": "openrouter", "outcome": "blocked"}],
        estimated_cost_usd=0.0,
        public_error_message=None,
    )
    result = SimpleNamespace(
        decision=decision,
        response="cannot verify",
        tool_results=[
            {
                "tool_name": "memory",
                "arguments": {"token": "secret", "query": "preference"},
                "success": True,
                "duration_ms": 5,
            }
        ],
    )
    router = SimpleNamespace(execute=lambda request: _async_result(result))
    provider = OllamaCertificationProvider(model="qwen2.5:7b", router_instance=router)

    execution = await provider.complete(CertificationCase(name="case", prompt="prompt"))

    assert execution.response == "cannot verify"
    assert execution.context.provider_selected == "ollama"
    assert execution.context.routing_reason == "manual local override"
    assert execution.context.fallback_events == [{"provider": "openrouter", "outcome": "blocked"}]
    assert execution.context.tool_calls[0].arguments["token"] == "[redacted]"


@pytest.mark.asyncio
async def test_director_provider_prefers_runtime_evidence() -> None:
    decision = SimpleNamespace(
        provider="ollama",
        model="qwen2.5:7b",
        reason="manual local override",
        fallback_attempts=[],
        estimated_cost_usd=0.0,
        public_error_message=None,
    )
    runtime_evidence = RuntimeEvidence(
        provider_selected="ollama",
        model_selected="qwen2.5:7b",
        routing_decision="ollama",
        routing_reason="manual local override",
        fallback_events=[{"provider": "openrouter", "outcome": "blocked"}],
        tool_calls=[
            RuntimeToolCallEvidence(
                name="memory",
                arguments={"token": "<redacted>", "query": "preference"},
                success=True,
                duration_ms=5,
            )
        ],
        memory_lookups=[{"operation": "shared_recall", "success": True, "count": 1}],
        connector_operations=[{"connector": "signal", "operation": "route", "success": True}],
        timing={"duration_ms": 12},
        token_counts={"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        cost=0.0,
    )
    result = SimpleNamespace(
        decision=decision,
        response="cannot verify",
        tool_results=[],
        runtime_evidence=runtime_evidence,
    )
    router = SimpleNamespace(execute=lambda request: _async_result(result))
    provider = OllamaCertificationProvider(model="qwen2.5:7b", router_instance=router)

    execution = await provider.complete(CertificationCase(name="case", prompt="prompt"))

    assert execution.context.tool_calls[0].arguments["token"] == "[redacted]"
    assert execution.context.memory_lookups[0]["count"] == 1
    assert execution.context.connector_operations[0]["connector"] == "signal"
    assert execution.context.token_counts["total_tokens"] == 7


def test_cli_lists_suites(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "list_suite_names", lambda: ["core/honesty", "tools/required-tool-calls"])

    assert cli.main(["--list-suites"]) == 0

    assert capsys.readouterr().out.splitlines() == ["core/honesty", "tools/required-tool-calls"]


def test_cli_runs_suite_and_writes_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    suite = CertificationSuite(
        name="smoke",
        description="Smoke checks.",
        cases=(CertificationCase(name="case", prompt="prompt", expected_keywords=("ok",)),),
    )
    report = CertificationReport(
        metadata=ReportMetadata(
            timestamp="2026-08-03T12:00:00+00:00",
            git_sha="abc123",
            branch="main",
            working_tree="clean",
            hostname="host",
            provider="ollama",
            model="fake-model",
            router_mode="default",
            suite_name="smoke",
            overall_score=1.0,
            execution_time=0.1,
            certification_cli_version="0.1.0",
        ),
        suite_description="Smoke checks.",
        cases=(grade_response(CertificationCase(name="case", prompt="prompt", expected_keywords=("ok",)), "ok"),),
        category_scores={"core": 1.0},
        speed_metrics={
            "measured_cases": 1,
            "generated_tokens": 8,
            "prompt_tokens": 4,
            "mean_generation_tokens_per_second": 16.0,
            "min_generation_tokens_per_second": 16.0,
            "max_generation_tokens_per_second": 16.0,
        },
    )

    monkeypatch.setattr(cli, "load_suite", lambda name: suite)
    monkeypatch.setattr(cli, "OllamaCertificationProvider", lambda model=None: FakeProvider([("ok", None)]))
    monkeypatch.setattr(cli, "run_suite_sync", lambda suite, provider, router_mode: report)

    assert cli.main(["smoke", "--output-dir", str(tmp_path)]) == 0

    output = capsys.readouterr().out
    assert "Suite: smoke" in output
    assert "Core: 100.0%" in output
    assert "Overall score: 1.000" in output
    assert "Mean generation speed: 16.000 tokens/s" in output
    assert "Speed samples: 1" in output
    assert list(tmp_path.glob("*.json"))
    assert list(tmp_path.glob("*.md"))


def test_benchmark_and_compare_helpers() -> None:
    report = CertificationReport(
        metadata=ReportMetadata(
            timestamp="2026-08-03T12:00:00+00:00",
            git_sha="abc123",
            branch="main",
            working_tree="clean",
            hostname="host",
            provider="ollama",
            model="fake-model",
            router_mode="default",
            suite_name="smoke",
            overall_score=1.0,
            execution_time=0.1,
            certification_cli_version="0.1.0",
        ),
        suite_description="Smoke checks.",
        cases=(
            grade_response(
                CertificationCase(name="case", prompt="prompt", expected_keywords=("ok",), category="core", suite_name="honesty"),
                "ok",
                runtime_context={"timing": {"duration_ms": 10}, "token_counts": {"total": 3}, "cost": 0.01},
            ),
        ),
        category_scores={"core": 1.0},
    )
    row = benchmark_row(report)
    assert row.score == 1.0
    assert row.latency_ms == 10
    assert "fake-model" in render_benchmark_markdown([row])

    left = report.to_dict()
    right = report.to_dict()
    right["metadata"]["overall_score"] = 0.0
    right["cases"][0]["passed"] = False
    comparison = compare_reports(left, right)
    assert comparison["score_delta"] == -1.0
    assert comparison["regressions"] == ["core/honesty/case"]
    assert "Regressions" in render_compare_markdown(comparison)


def test_benchmark_report_collects_rankings_and_router_data(tmp_path: Path) -> None:
    fast = _report_for_benchmark("ollama", "fast", 1.0, "honesty", "core", 10, 3, True)
    slow = _report_for_benchmark("ollama", "slow", 0.0, "honesty", "core", 20, 5, False)

    report = build_benchmark_report(
        [
            (BenchmarkTarget("ollama", "fast"), [fast]),
            (BenchmarkTarget("ollama", "slow"), [slow]),
        ],
        router_mode="default",
    )
    written = write_benchmark_report(report, output_dir=tmp_path)

    data = json.loads(Path(written.report_paths["json"]).read_text(encoding="utf-8"))
    assert data["entries"][0]["metrics"]["average_latency_ms"] == 10
    assert data["rankings"]["overall_score"][0] == "ollama:fast"
    assert data["rankings"]["latency"][0] == "ollama:fast"
    assert data["router_data"]["selection_inputs"]["ollama:fast"]["overall_score"] == 1.0
    assert "Freyja Benchmark Report" in Path(written.report_paths["markdown"]).read_text(encoding="utf-8")


def test_compare_benchmark_reports_reports_deltas() -> None:
    before = build_benchmark_report(
        [(BenchmarkTarget("ollama", "model"), [_report_for_benchmark("ollama", "model", 1.0, "honesty", "core", 10, 3, True)])],
        router_mode="default",
    ).to_dict()
    after = build_benchmark_report(
        [(BenchmarkTarget("ollama", "model"), [_report_for_benchmark("ollama", "model", 0.0, "honesty", "core", 15, 4, False)])],
        router_mode="default",
    ).to_dict()

    comparison = compare_reports(before, after)

    assert comparison["type"] == "benchmark"
    assert comparison["target_deltas"]["ollama:model"]["score_delta"] == -1.0
    assert comparison["target_deltas"]["ollama:model"]["latency_delta_ms"] == 5
    assert comparison["regressions"] == ["ollama:model"]
    assert "Benchmark Comparison" in render_compare_markdown(comparison)


def test_benchmark_history_lookup_and_model_compare(tmp_path: Path) -> None:
    report = build_benchmark_report(
        [
            (BenchmarkTarget("ollama", "left"), [_report_for_benchmark("ollama", "left", 0.5, "honesty", "core", 20, 3, False)]),
            (BenchmarkTarget("ollama", "right"), [_report_for_benchmark("ollama", "right", 1.0, "honesty", "core", 10, 3, True)]),
        ],
        router_mode="default",
    )
    written = write_benchmark_report(report, output_dir=tmp_path)

    by_commit = find_benchmark_report_by_commit("abc", tmp_path)
    by_models = find_benchmark_report_with_models("left", "right", tmp_path)
    comparison = compare_benchmark_models(by_models, "left", "right")

    assert by_commit["_source_path"] == written.report_paths["json"]
    assert by_models["_source_path"] == written.report_paths["json"]
    assert comparison["type"] == "model"
    assert comparison["score_delta"] == 1.0
    assert comparison["latency_delta_ms"] == -10
    assert "Model Benchmark Comparison" in render_compare_markdown(comparison)


def test_cli_benchmark_runs_repeated_provider_model_pairs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite = CertificationSuite(
        name="smoke",
        description="Smoke checks.",
        cases=(CertificationCase(name="case", prompt="prompt", expected_keywords=("ok",)),),
    )
    calls: list[tuple[str, str]] = []

    class Provider:
        def __init__(self, provider: str, model: str | None) -> None:
            self.name = provider
            self.model = model or "default"

    def fake_provider(provider: str, model: str | None):
        calls.append((provider, model or "default"))
        return Provider(provider, model)

    def fake_run_suite_sync(suite, provider, router_mode):
        return _report_for_benchmark(provider.name, provider.model, 1.0, suite.name, "core", 10, 3, True)

    monkeypatch.setattr(cli, "load_suite", lambda name: suite)
    monkeypatch.setattr(cli, "_provider", fake_provider)
    monkeypatch.setattr(cli, "run_suite_sync", fake_run_suite_sync)

    assert cli.main(
        [
            "benchmark",
            "--benchmark-suite",
            "smoke",
            "--provider",
            "ollama",
            "--model",
            "qwen3:27b",
            "--provider",
            "openrouter",
            "--model",
            "openai/gpt-5.5",
            "--output-dir",
            str(tmp_path),
        ]
    ) == 0

    assert calls == [("ollama", "qwen3:27b"), ("openrouter", "openai/gpt-5.5")]
    output = capsys.readouterr().out
    assert "Freyja Benchmark Report" in output
    assert list(tmp_path.glob("*benchmark.json"))
    assert list(tmp_path.glob("*benchmark.md"))


async def _async_result(value):
    return value


def _report_for_benchmark(
    provider: str,
    model: str,
    score: float,
    suite_name: str,
    category: str,
    latency_ms: float,
    tokens: int,
    passed: bool,
) -> CertificationReport:
    case = CertificationCase(
        name="case",
        prompt="prompt",
        category=category,
        suite_name=suite_name,
        max_score=1.0,
    )
    result = grade_response(
        case,
        "ok" if passed else "nope",
        runtime_context={
            "timing": {"duration_ms": latency_ms},
            "token_counts": {"total_tokens": tokens},
            "tool_calls": [{"name": "tool", "success": passed}],
        },
        verifier_results=(
            {"verifier": "router", "passed": passed},
            {"verifier": "memory", "passed": passed},
            {"verifier": "connector", "passed": passed},
            {"verifier": "vision", "passed": passed},
        ),
    )
    return CertificationReport(
        metadata=ReportMetadata(
            timestamp="2026-08-03T12:00:00+00:00",
            git_sha="abc123",
            branch="main",
            working_tree="clean",
            hostname="host",
            provider=provider,
            model=model,
            router_mode="default",
            suite_name=suite_name,
            overall_score=score,
            execution_time=latency_ms / 1000,
            certification_cli_version="0.1.0",
        ),
        suite_description="Benchmark suite.",
        cases=(result,),
        category_scores={category: score},
    )
