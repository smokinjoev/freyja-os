from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from certification import __version__

DEFAULT_READINESS_DIR = Path("certification/reports")
REQUIRED_REV2_CAPABILITIES = (
    "apple.messages.read",
    "apple.messages.send",
    "apple.calendar.read",
    "apple.calendar.write",
    "apple.contacts.read",
    "apple.shortcuts.run",
)
DEFAULT_REQUIRED_PROVIDER_PROFILES = (
    "legacy_ollama",
    "iris_router",
    "openrouter_frontier",
)
DEFAULT_REQUIRED_MODEL_PROFILES = (
    "fast",
    "reason",
    "code",
    "vision",
)


@dataclass(frozen=True)
class ReadinessCheck:
    name: str
    passed: bool
    status: str
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float | None = None


@dataclass(frozen=True)
class Rev2ReadinessReport:
    timestamp: str
    director_url: str
    hostname: str
    git_sha: str
    branch: str
    working_tree: str
    checks: tuple[ReadinessCheck, ...]
    certification_report: str | None = None
    benchmark_report: str | None = None
    connector_reports: tuple[str, ...] = ()
    memory_report: str | None = None
    approval_report: str | None = None
    vulcan_report: str | None = None
    smoke_report: str | None = None
    signal_smoke_report: str | None = None
    latency_winner_target: str | None = None
    schema_version: str = "1.0"
    readiness_cli_version: str = __version__
    report_paths: dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": self.timestamp,
            "director_url": self.director_url,
            "hostname": self.hostname,
            "git_sha": self.git_sha,
            "branch": self.branch,
            "working_tree": self.working_tree,
            "certification_report": self.certification_report,
            "benchmark_report": self.benchmark_report,
            "connector_reports": list(self.connector_reports),
            "memory_report": self.memory_report,
            "approval_report": self.approval_report,
            "vulcan_report": self.vulcan_report,
            "smoke_report": self.smoke_report,
            "signal_smoke_report": self.signal_smoke_report,
            "latency_winner_target": self.latency_winner_target,
            "readiness_cli_version": self.readiness_cli_version,
            "passed": self.passed,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "status": check.status,
                    "details": check.details,
                    "latency_ms": check.latency_ms,
                }
                for check in self.checks
            ],
            "report_paths": dict(self.report_paths),
        }


def run_readiness_probe(
    director_url: str,
    *,
    certification_report: Path | None = None,
    benchmark_report: Path | None = None,
    connector_reports: tuple[Path, ...] = (),
    memory_report: Path | None = None,
    approval_report: Path | None = None,
    vulcan_report: Path | None = None,
    smoke_report: Path | None = None,
    signal_smoke_report: Path | None = None,
    latency_winner_target: str | None = None,
    require_certification_report: bool = False,
    require_benchmark_report: bool = False,
    require_connector_report: bool = False,
    require_memory_report: bool = False,
    require_approval_report: bool = False,
    require_vulcan_report: bool = False,
    require_smoke_report: bool = False,
    require_signal_smoke_report: bool = False,
    require_latency_winner_target: bool = False,
    required_provider_profiles: tuple[str, ...] = DEFAULT_REQUIRED_PROVIDER_PROFILES,
    required_model_profiles: tuple[str, ...] = (),
    timeout: float = 5.0,
) -> Rev2ReadinessReport:
    if not required_provider_profiles:
        required_provider_profiles = DEFAULT_REQUIRED_PROVIDER_PROFILES
    base_url = director_url.rstrip("/") + "/"
    checks: list[ReadinessCheck] = []

    with httpx.Client(base_url=base_url, timeout=timeout, headers=_auth_headers()) as client:
        checks.append(
            _probe_providers(
                client,
                required_provider_profiles=required_provider_profiles,
                required_model_profiles=required_model_profiles,
            )
        )
        checks.append(_probe_iris(client))
        checks.append(_probe_macagent(client))

    if certification_report is not None:
        checks.append(_check_certification_report(certification_report))
    elif require_certification_report:
        checks.append(_missing_required_artifact("rev2-certification-report", "--certification-report"))
    if benchmark_report is not None:
        checks.append(_check_benchmark_report(benchmark_report, latency_winner_target))
    elif require_benchmark_report:
        checks.append(_missing_required_artifact("rev2-latency-benchmark", "--benchmark-report"))
    if require_latency_winner_target and not latency_winner_target:
        checks.append(_missing_required_artifact("rev2-latency-winner-target", "--latency-winner-target"))
    if connector_reports:
        for path in connector_reports:
            checks.append(_check_connector_report(path, base_url.rstrip("/")))
    elif require_connector_report:
        checks.append(_missing_required_artifact("connector-production-report", "--connector-report"))
    if memory_report is not None:
        checks.append(_check_memory_report(memory_report))
    elif require_memory_report:
        checks.append(_missing_required_artifact("memory-provenance-report", "--memory-report"))
    if approval_report is not None:
        checks.append(_check_approval_report(approval_report))
    elif require_approval_report:
        checks.append(_missing_required_artifact("approval-exercise-report", "--approval-report"))
    if vulcan_report is not None:
        checks.append(_check_vulcan_report(vulcan_report))
    elif require_vulcan_report:
        checks.append(_missing_required_artifact("vulcan-readiness-report", "--vulcan-report"))
    if smoke_report is not None:
        checks.append(_check_messaging_smoke_report(smoke_report, connector="imessage"))
    elif require_smoke_report:
        checks.append(_missing_required_artifact("imessage-live-smoke-report", "--smoke-report"))
    if signal_smoke_report is not None:
        checks.append(_check_messaging_smoke_report(signal_smoke_report, connector="signal"))
    elif require_signal_smoke_report:
        checks.append(_missing_required_artifact("signal-live-smoke-report", "--signal-smoke-report"))

    return Rev2ReadinessReport(
        timestamp=datetime.now(UTC).isoformat(),
        director_url=base_url.rstrip("/"),
        hostname=socket.gethostname(),
        git_sha=_git_output("rev-parse", "HEAD"),
        branch=_git_output("branch", "--show-current") or "unknown",
        working_tree="dirty" if _git_output("status", "--porcelain") else "clean",
        certification_report=str(certification_report) if certification_report is not None else None,
        benchmark_report=str(benchmark_report) if benchmark_report is not None else None,
        connector_reports=tuple(str(path) for path in connector_reports),
        memory_report=str(memory_report) if memory_report is not None else None,
        approval_report=str(approval_report) if approval_report is not None else None,
        vulcan_report=str(vulcan_report) if vulcan_report is not None else None,
        smoke_report=str(smoke_report) if smoke_report is not None else None,
        signal_smoke_report=str(signal_smoke_report) if signal_smoke_report is not None else None,
        latency_winner_target=latency_winner_target,
        checks=tuple(checks),
    )


def write_readiness_report(report: Rev2ReadinessReport, output_dir: Path = DEFAULT_READINESS_DIR) -> Rev2ReadinessReport:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = _report_stem(report.timestamp)
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"

    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_readiness_markdown(report), encoding="utf-8")
    return Rev2ReadinessReport(
        timestamp=report.timestamp,
        director_url=report.director_url,
        hostname=report.hostname,
        git_sha=report.git_sha,
        branch=report.branch,
        working_tree=report.working_tree,
        certification_report=report.certification_report,
        benchmark_report=report.benchmark_report,
        connector_reports=report.connector_reports,
        memory_report=report.memory_report,
        approval_report=report.approval_report,
        vulcan_report=report.vulcan_report,
        smoke_report=report.smoke_report,
        signal_smoke_report=report.signal_smoke_report,
        latency_winner_target=report.latency_winner_target,
        checks=report.checks,
        schema_version=report.schema_version,
        readiness_cli_version=report.readiness_cli_version,
        report_paths={"json": str(json_path), "markdown": str(md_path)},
    )


def render_readiness_markdown(report: Rev2ReadinessReport) -> str:
    lines = [
        "# Rev 2 Readiness Report",
        "",
        "## Summary",
        "",
        f"- Timestamp: {report.timestamp}",
        f"- Director URL: {report.director_url}",
        f"- Hostname: {report.hostname}",
        f"- Git SHA: {report.git_sha}",
        f"- Branch: {report.branch}",
        f"- Working tree: {report.working_tree}",
        f"- Certification report: {report.certification_report or 'not supplied'}",
        f"- Benchmark report: {report.benchmark_report or 'not supplied'}",
        f"- Connector reports: {', '.join(report.connector_reports) if report.connector_reports else 'not supplied'}",
        f"- Memory report: {report.memory_report or 'not supplied'}",
        f"- Approval report: {report.approval_report or 'not supplied'}",
        f"- Vulcan report: {report.vulcan_report or 'not supplied'}",
        f"- Smoke report: {report.smoke_report or 'not supplied'}",
        f"- Signal smoke report: {report.signal_smoke_report or 'not supplied'}",
        f"- Latency winner target: {report.latency_winner_target or 'not supplied'}",
        f"- Overall readiness: {'passed' if report.passed else 'failed'}",
        f"- Readiness CLI version: {report.readiness_cli_version}",
        "",
        "## Checks",
        "",
    ]
    for check in report.checks:
        latency = "" if check.latency_ms is None else f" ({check.latency_ms:.1f} ms)"
        lines.append(f"### {check.name}")
        lines.append("")
        lines.append(f"- Passed: {check.passed}")
        lines.append(f"- Status: {check.status}{latency}")
        if check.details:
            lines.append("- Details:")
            for key, value in sorted(check.details.items()):
                lines.append(f"  - {key}: {json.dumps(value, sort_keys=True)}")
        lines.append("")
    return "\n".join(lines)


def _probe_providers(
    client: httpx.Client,
    *,
    required_provider_profiles: tuple[str, ...] = DEFAULT_REQUIRED_PROVIDER_PROFILES,
    required_model_profiles: tuple[str, ...] = (),
) -> ReadinessCheck:
    started = time.perf_counter()
    try:
        response = client.get("providers/health")
        latency_ms = _elapsed_ms(started)
        if response.status_code != 200:
            return ReadinessCheck("provider-health", False, f"HTTP {response.status_code}", latency_ms=latency_ms)
        payload = response.json()
    except Exception as exc:
        return ReadinessCheck("provider-health", False, str(exc))

    profiles = payload.get("providers") if isinstance(payload, dict) else None
    if not isinstance(profiles, list):
        return ReadinessCheck("provider-health", False, "missing providers list", {"payload": payload}, latency_ms)
    profile_ids = {str(profile.get("provider_id") or profile.get("profile_id")) for profile in profiles if isinstance(profile, dict)}
    model_profiles = {
        str(profile.get("logical_profile"))
        for profile in profiles
        if isinstance(profile, dict) and profile.get("logical_profile")
    }
    expected = set(required_provider_profiles)
    expected_model_profiles = set(required_model_profiles)
    missing = sorted(expected - profile_ids)
    missing_model_profiles = sorted(expected_model_profiles - model_profiles)
    not_ready = sorted(
        str(profile.get("provider_id") or profile.get("profile_id"))
        for profile in profiles
        if isinstance(profile, dict)
        and str(profile.get("provider_id") or profile.get("profile_id")) in expected
        and profile.get("ready") is not True
    )
    optional_not_ready = sorted(
        str(profile.get("provider_id") or profile.get("profile_id"))
        for profile in profiles
        if isinstance(profile, dict)
        and str(profile.get("provider_id") or profile.get("profile_id")) not in expected
        and profile.get("ready") is not True
    )
    ready = {
        str(profile.get("provider_id") or profile.get("profile_id")): profile.get("readiness")
        for profile in profiles
        if isinstance(profile, dict)
    }
    return ReadinessCheck(
        "provider-health",
        not missing and not missing_model_profiles and not not_ready,
        (
            "required provider and model profiles ready"
            if not missing and not missing_model_profiles and not not_ready
            else "required provider or model profiles not ready"
        ),
        {
            "required_profile_ids": sorted(expected),
            "required_model_profiles": sorted(expected_model_profiles),
            "profile_ids": sorted(profile_ids),
            "model_profiles": sorted(model_profiles),
            "missing": missing,
            "missing_model_profiles": missing_model_profiles,
            "not_ready": not_ready,
            "optional_not_ready": optional_not_ready,
            "readiness": ready,
        },
        latency_ms,
    )


def _probe_iris(client: httpx.Client) -> ReadinessCheck:
    started = time.perf_counter()
    try:
        response = client.get("iris-router/health")
        latency_ms = _elapsed_ms(started)
        if response.status_code != 200:
            return ReadinessCheck("iris-router-health", False, f"HTTP {response.status_code}", latency_ms=latency_ms)
        payload = response.json()
    except Exception as exc:
        return ReadinessCheck("iris-router-health", False, str(exc))

    enabled = bool(payload.get("enabled")) if isinstance(payload, dict) else False
    available = bool(payload.get("available")) if isinstance(payload, dict) else False
    return ReadinessCheck(
        "iris-router-health",
        enabled and available,
        "Iris classifier enabled and available" if enabled and available else "Iris classifier not ready",
        {"enabled": enabled, "available": available, "payload": payload},
        latency_ms,
    )


def _probe_macagent(client: httpx.Client) -> ReadinessCheck:
    started = time.perf_counter()
    try:
        response = client.get("macagent/health")
        latency_ms = _elapsed_ms(started)
        if response.status_code != 200:
            return ReadinessCheck("macagent-health", False, f"HTTP {response.status_code}", latency_ms=latency_ms)
        payload = response.json()
    except Exception as exc:
        return ReadinessCheck("macagent-health", False, str(exc))

    enabled = bool(payload.get("enabled")) if isinstance(payload, dict) else False
    reachable = bool(payload.get("reachable")) if isinstance(payload, dict) else False
    authenticated = bool(payload.get("authenticated")) if isinstance(payload, dict) else False
    capabilities = payload.get("capabilities") if isinstance(payload, dict) else None
    capability_set = {str(item) for item in capabilities} if isinstance(capabilities, list) else set()
    missing = sorted(set(REQUIRED_REV2_CAPABILITIES) - capability_set)
    passed = enabled and reachable and authenticated and not missing
    return ReadinessCheck(
        "macagent-health",
        passed,
        "MacAgent reachable with Rev 2 capabilities" if passed else "MacAgent not ready",
        {
            "enabled": enabled,
            "reachable": reachable,
            "authenticated": authenticated,
            "missing_capabilities": missing,
            "payload": payload,
        },
        latency_ms,
    )


def _check_certification_report(path: Path) -> ReadinessCheck:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ReadinessCheck("rev2-certification-report", False, str(exc), {"path": str(path)})

    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    suite_name = metadata.get("suite_name")
    failed = [case.get("name") for case in cases if isinstance(case, dict) and not case.get("passed")]
    passed = suite_name == "rev2-vertical-spine" and bool(cases) and not failed
    return ReadinessCheck(
        "rev2-certification-report",
        passed,
        "Rev 2 certification report passed" if passed else "Rev 2 certification report is not passing",
        {
            "path": str(path),
            "suite_name": suite_name,
            "case_count": len(cases) if isinstance(cases, list) else 0,
            "failed_cases": failed,
            "overall_score": metadata.get("overall_score"),
        },
    )


def _check_benchmark_report(path: Path, latency_winner_target: str | None) -> ReadinessCheck:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ReadinessCheck("rev2-latency-benchmark", False, str(exc), {"path": str(path)})

    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    rankings = payload.get("rankings", {}) if isinstance(payload, dict) else {}
    latency_ranking = rankings.get("latency", []) if isinstance(rankings, dict) else []
    failures = {
        _entry_target_id(entry): entry.get("metrics", {}).get("failures")
        for entry in entries
        if isinstance(entry, dict)
    }
    winner = latency_ranking[0] if latency_ranking else None
    expected_winner_matches = latency_winner_target is None or winner == latency_winner_target
    all_targets_clean = all(value == 0 for value in failures.values()) if failures else False
    passed = len(entries) >= 2 and bool(winner) and expected_winner_matches and all_targets_clean
    return ReadinessCheck(
        "rev2-latency-benchmark",
        passed,
        "Rev 2 latency benchmark supports cutover"
        if passed
        else "Rev 2 latency benchmark does not support cutover",
        {
            "path": str(path),
            "entry_count": len(entries) if isinstance(entries, list) else 0,
            "latency_winner": winner,
            "expected_latency_winner": latency_winner_target,
            "failures_by_target": failures,
        },
    )


def _check_connector_report(path: Path, director_url: str) -> ReadinessCheck:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ReadinessCheck("connector-production-report", False, str(exc), {"path": str(path)})

    connector_statuses = {
        name: status
        for name, status in payload.items()
        if isinstance(name, str) and isinstance(status, dict)
    } if isinstance(payload, dict) else {}
    not_ready = sorted(
        name
        for name, status in connector_statuses.items()
        if status.get("ready_for_live_smoke") is not True
    )
    director_mismatches = sorted(
        name
        for name, status in connector_statuses.items()
        if _normalize_url(str(status.get("director_url", ""))) != _normalize_url(director_url)
    )
    token_missing = sorted(
        name
        for name, status in connector_statuses.items()
        if status.get("connector_token_configured") is not True
    )
    readiness_details = {
        name: _connector_readiness_details(status)
        for name, status in connector_statuses.items()
        if status.get("ready_for_live_smoke") is not True
    }
    passed = bool(connector_statuses) and not not_ready and not director_mismatches and not token_missing
    return ReadinessCheck(
        "connector-production-report",
        passed,
        "Connector production report supports cutover"
        if passed
        else "Connector production report does not support cutover",
        {
            "path": str(path),
            "connectors": sorted(connector_statuses),
            "not_ready": not_ready,
            "director_mismatches": director_mismatches,
            "token_missing": token_missing,
            "readiness_details": readiness_details,
            "expected_director_url": _normalize_url(director_url),
        },
    )


def _connector_readiness_details(status: dict[str, object]) -> list[str]:
    missing: list[str] = []
    if status.get("enabled") is not True:
        missing.append("enabled=false")
    if status.get("connector_token_configured") is not True:
        missing.append("connector token missing")
    if status.get("account_number_configured") is False:
        missing.append("account number missing")
    if status.get("identity_configured") is False:
        missing.append("identity missing")
    if status.get("transport_configured") is False:
        missing.append("transport credentials missing")
    if status.get("allowed_sender_count") in (None, 0):
        missing.append("allowed sender allowlist empty")
    if status.get("database_exists") is False:
        missing.append("message database missing")
    if status.get("imsg_exists") is False:
        missing.append("imsg binary missing")
    if isinstance(status.get("director_health"), dict) and status["director_health"].get("ok") is not True:
        missing.append("Director health unavailable")
    if isinstance(status.get("director_rev2_health"), dict) and status["director_rev2_health"].get("ok") is not True:
        missing.append("Director Rev 2 health unavailable")
    if isinstance(status.get("signal_rest_health"), dict) and status["signal_rest_health"].get("ok") is not True:
        missing.append("Signal REST health unavailable")
    if isinstance(status.get("launchagent"), dict) and status["launchagent"].get("ok") is False:
        missing.append("LaunchAgent not loaded")
    return missing or ["ready_for_live_smoke=false"]


def _check_memory_report(path: Path) -> ReadinessCheck:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ReadinessCheck("memory-provenance-report", False, str(exc), {"path": str(path)})
    passed = bool(payload.get("passed") is True) if isinstance(payload, dict) else False
    return ReadinessCheck(
        "memory-provenance-report",
        passed,
        "Memory provenance report supports cutover" if passed else "Memory provenance report does not support cutover",
        {
            "path": str(path),
            "shared_memory_count": payload.get("shared_memory_count") if isinstance(payload, dict) else None,
            "missing_provenance_count": payload.get("missing_provenance_count") if isinstance(payload, dict) else None,
            "malformed_metadata_count": payload.get("malformed_metadata_count") if isinstance(payload, dict) else None,
            "malformed_provenance_count": payload.get("malformed_provenance_count") if isinstance(payload, dict) else None,
            "untrusted_authoritative_count": payload.get("untrusted_authoritative_count") if isinstance(payload, dict) else None,
        },
    )


def _check_approval_report(path: Path) -> ReadinessCheck:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ReadinessCheck("approval-exercise-report", False, str(exc), {"path": str(path)})

    exercises = payload.get("exercises", []) if isinstance(payload, dict) else []
    if not isinstance(exercises, list):
        exercises = []
    denied_without_approval = [
        item
        for item in exercises
        if isinstance(item, dict)
        and item.get("consequential") is True
        and item.get("approval_granted") is False
        and item.get("allowed") is False
        and item.get("director_authorized") is False
    ]
    allowed_with_approval = [
        item
        for item in exercises
        if isinstance(item, dict)
        and item.get("consequential") is True
        and item.get("approval_granted") is True
        and item.get("allowed") is True
        and item.get("director_authorized") is True
    ]
    unsafe = [
        item.get("name", "unknown")
        for item in exercises
        if isinstance(item, dict)
        and item.get("consequential") is True
        and item.get("allowed") is True
        and item.get("director_authorized") is not True
    ]
    passed = bool(denied_without_approval) and bool(allowed_with_approval) and not unsafe
    return ReadinessCheck(
        "approval-exercise-report",
        passed,
        "Approval exercise report supports cutover" if passed else "Approval exercise report does not support cutover",
        {
            "path": str(path),
            "exercise_count": len(exercises),
            "denied_without_approval_count": len(denied_without_approval),
            "allowed_with_approval_count": len(allowed_with_approval),
            "unsafe_allowed_without_director_authorization": sorted(unsafe),
        },
    )


def _check_vulcan_report(path: Path) -> ReadinessCheck:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ReadinessCheck("vulcan-readiness-report", False, str(exc), {"path": str(path)})

    if not isinstance(payload, dict):
        return ReadinessCheck("vulcan-readiness-report", False, "invalid Vulcan readiness report", {"path": str(path)})
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    missing_profiles = [
        profile
        for profile in DEFAULT_REQUIRED_MODEL_PROFILES
        if not isinstance(checks.get(profile), dict) or checks[profile].get("ready") is not True
    ]
    passed = (
        payload.get("report_type") == "vulcan-readiness"
        and payload.get("status") == "ready"
        and payload.get("ready_for_certification") is True
        and not missing_profiles
    )
    return ReadinessCheck(
        "vulcan-readiness-report",
        passed,
        "Vulcan readiness report supports cutover"
        if passed
        else "Vulcan readiness report does not support cutover",
        {
            "path": str(path),
            "report_type": payload.get("report_type"),
            "status": payload.get("status"),
            "ready_for_certification": payload.get("ready_for_certification"),
            "required_model_profiles": list(DEFAULT_REQUIRED_MODEL_PROFILES),
            "not_ready_model_profiles": missing_profiles,
            "missing": payload.get("missing") if isinstance(payload.get("missing"), list) else [],
        },
    )


def _check_messaging_smoke_report(path: Path, *, connector: str) -> ReadinessCheck:
    check_name = f"{connector}-live-smoke-report"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ReadinessCheck(check_name, False, str(exc), {"path": str(path)})

    if not isinstance(payload, dict):
        return ReadinessCheck(check_name, False, "invalid smoke report", {"path": str(path)})
    plan = payload.get("plan") if isinstance(payload.get("plan"), dict) else {}
    expected_type = f"{connector}-live-smoke"
    passed = (
        payload.get("report_type") == expected_type
        and payload.get("status") == "sent"
        and payload.get("dry_run") is False
        and payload.get("sent") == 1
        and payload.get("failed") == 0
        and bool(plan.get("recipient"))
    )
    display_name = "iMessage" if connector == "imessage" else connector.title()
    return ReadinessCheck(
        check_name,
        passed,
        f"{display_name} live smoke supports cutover" if passed else f"{display_name} live smoke has not sent a message",
        {
            "path": str(path),
            "report_type": payload.get("report_type"),
            "expected_report_type": expected_type,
            "status": payload.get("status"),
            "dry_run": payload.get("dry_run"),
            "sent": payload.get("sent"),
            "failed": payload.get("failed"),
            "recipient_present": bool(plan.get("recipient")),
        },
    )


def _missing_required_artifact(name: str, option: str) -> ReadinessCheck:
    return ReadinessCheck(
        name,
        False,
        f"missing required {option}",
        {"required_option": option},
    )


def _entry_target_id(entry: dict[str, Any]) -> str:
    target = entry.get("target", {})
    if not isinstance(target, dict):
        return "unknown"
    return str(target.get("target_id") or f"{target.get('provider')}:{target.get('model') or 'default'}")


def _normalize_url(url: str) -> str:
    return url.strip().rstrip("/")


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


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


def _report_stem(timestamp: str) -> str:
    safe_timestamp = timestamp.replace(":", "").replace("-", "").replace("+", "Z")
    return f"{safe_timestamp}-rev2-readiness"
