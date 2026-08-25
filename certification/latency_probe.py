from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from certification.benchmark import (
    BenchmarkEntry,
    BenchmarkMetrics,
    BenchmarkReport,
    BenchmarkTarget,
    rank_benchmark_entries,
    router_consumable_data,
    write_benchmark_report,
)
from certification.rev2_readiness import DEFAULT_REQUIRED_PROVIDER_PROFILES
from certification.rev2_readiness import REQUIRED_REV2_CAPABILITIES


def build_latency_probe_report(
    director_url: str,
    *,
    timeout: float = 5.0,
    output_dir: Path = Path("certification/benchmarks"),
    required_provider_profiles: tuple[str, ...] = DEFAULT_REQUIRED_PROVIDER_PROFILES,
) -> BenchmarkReport:
    base_url = director_url.rstrip("/")
    entries = tuple(_probe_targets(base_url, timeout=timeout, required_provider_profiles=required_provider_profiles))
    rankings = rank_benchmark_entries(entries)
    report = BenchmarkReport(
        timestamp=_timestamp(),
        git_sha=_git_output("rev-parse", "HEAD"),
        branch=_git_output("branch", "--show-current") or "unknown",
        working_tree="dirty" if _git_output("status", "--porcelain") else "clean",
        router_mode="rev2-latency-probe",
        suite_names=("rev2-latency-probe",),
        entries=entries,
        rankings=rankings,
        router_data=router_consumable_data(entries, rankings),
    )
    return write_benchmark_report(report, output_dir=output_dir)


def _probe_targets(
    base_url: str,
    *,
    timeout: float,
    required_provider_profiles: tuple[str, ...],
) -> list[BenchmarkEntry]:
    entries: list[BenchmarkEntry] = []
    with httpx.Client(timeout=timeout, headers=_auth_headers()) as client:
        entries.append(_probe_http_target(client, BenchmarkTarget("director", "health"), f"{base_url}/health"))
        entries.append(_probe_http_target(client, BenchmarkTarget("iris_router", "health"), f"{base_url}/iris-router/health"))
        entries.append(_probe_http_target(client, BenchmarkTarget("macagent", "health"), f"{base_url}/macagent/health"))
        provider_entries = _probe_provider_profiles(
            client,
            base_url,
            required_provider_profiles=required_provider_profiles,
        )
        entries.extend(provider_entries)
    return entries


def _probe_http_target(client: httpx.Client, target: BenchmarkTarget, url: str) -> BenchmarkEntry:
    started = time.perf_counter()
    failures = 0
    try:
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()
        if not _http_target_ready(target, payload):
            failures = 1
    except Exception:
        failures = 1
    latency_ms = max(0.0, (time.perf_counter() - started) * 1000)
    return _entry(target, latency_ms=latency_ms, failures=failures)


def _http_target_ready(target: BenchmarkTarget, payload: Any) -> bool:
    if target.provider == "director" and target.model == "health":
        return isinstance(payload, dict) and payload.get("status") == "healthy"
    if target.provider == "iris_router" and target.model == "health":
        return (
            isinstance(payload, dict)
            and payload.get("enabled") is True
            and (payload.get("available") is True or payload.get("reachable") is True)
        )
    if target.provider == "macagent" and target.model == "health":
        capabilities = payload.get("capabilities") if isinstance(payload, dict) else None
        capability_set = set(capabilities if isinstance(capabilities, list) else [])
        return (
            isinstance(payload, dict)
            and payload.get("enabled") is True
            and payload.get("reachable") is True
            and payload.get("authenticated") is True
            and set(REQUIRED_REV2_CAPABILITIES).issubset(capability_set)
            and payload.get("authorization_granted_by_macagent") is False
        )
    return True


def _probe_provider_profiles(
    client: httpx.Client,
    base_url: str,
    *,
    required_provider_profiles: tuple[str, ...],
) -> list[BenchmarkEntry]:
    started = time.perf_counter()
    try:
        response = client.get(f"{base_url}/providers/health")
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return [_entry(BenchmarkTarget("providers", "health"), latency_ms=(time.perf_counter() - started) * 1000, failures=1)]

    latency_ms = max(0.0, (time.perf_counter() - started) * 1000)
    profiles = payload.get("providers") if isinstance(payload, dict) else []
    entries: list[BenchmarkEntry] = []
    for profile in profiles if isinstance(profiles, list) else []:
        if not isinstance(profile, dict):
            continue
        provider_id = str(profile.get("provider_id") or profile.get("profile_id") or "unknown")
        ready = profile.get("ready") is True
        if provider_id not in set(required_provider_profiles) and not ready:
            continue
        entries.append(_entry(BenchmarkTarget("provider", provider_id), latency_ms=latency_ms, failures=0 if ready else 1))
    return entries or [_entry(BenchmarkTarget("providers", "health"), latency_ms=latency_ms, failures=1)]


def _entry(target: BenchmarkTarget, *, latency_ms: float, failures: int) -> BenchmarkEntry:
    return BenchmarkEntry(
        target=target,
        suite_names=("rev2-latency-probe",),
        metrics=BenchmarkMetrics(
            overall_score=1.0 if failures == 0 else 0.0,
            category_scores={"latency": 1.0 if failures == 0 else 0.0},
            execution_time=latency_ms / 1000,
            average_latency_ms=latency_ms,
            token_usage=0,
            failures=failures,
        ),
    )


def _git_output(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def _auth_headers() -> dict[str, str]:
    token = os.getenv("FREYJA_CONNECTOR_TOKEN", "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


def _timestamp() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")
