#!/usr/bin/env python3
"""Small operator CLI for Vulcan model profile readiness."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and Path(sys.executable) != _VENV_PYTHON:
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON), *sys.argv])

_SRC_DIR = str(_PROJECT_ROOT / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

from freyja.config import Settings  # noqa: E402
from freyja.inference import InferenceProviderProfile, provider_registry_from_settings  # noqa: E402

REQUIRED_PROFILES = ("fast", "reason", "code", "vision")


def _operator_report(report_type: str, result: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    report = {
        "schema_version": "1.0",
        "report_type": report_type,
        "timestamp": datetime.now(UTC).isoformat(),
        "dry_run": dry_run,
    }
    report.update(result)
    return report


def _render_report(report: dict[str, Any], output: Path | None = None) -> None:
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")


def _settings(env_file: str | None) -> Settings:
    return Settings(_env_file=env_file) if env_file else Settings()


def _providers_by_profile(settings: Settings) -> dict[str, InferenceProviderProfile]:
    registry = provider_registry_from_settings(settings)
    providers: dict[str, InferenceProviderProfile] = {}
    for profile in REQUIRED_PROFILES:
        matches = registry.by_logical_profile(profile)
        if matches:
            providers[profile] = matches[0]
    return providers


async def _ollama_tags(provider: InferenceProviderProfile) -> set[str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{provider.base_url.rstrip('/')}/api/tags")
        response.raise_for_status()
        payload = response.json()
    models = payload.get("models") if isinstance(payload, dict) else []
    if not isinstance(models, list):
        return set()
    names: set[str] = set()
    for item in models:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.add(item["name"])
    return names


async def _pull_ollama_model(provider: InferenceProviderProfile) -> int:
    async with httpx.AsyncClient(timeout=None) as client:
        response = await client.post(
            f"{provider.base_url.rstrip('/')}/api/pull",
            json={"model": provider.model, "stream": False},
        )
        response.raise_for_status()
    return response.status_code


def _ollama_model_available(configured_model: str, available_models: set[str]) -> bool:
    if configured_model in available_models:
        return True
    if ":" not in configured_model and f"{configured_model}:latest" in available_models:
        return True
    return False


async def _readiness(settings: Settings) -> dict[str, Any]:
    providers = _providers_by_profile(settings)
    checks: dict[str, Any] = {}
    missing: list[str] = []

    for profile in REQUIRED_PROFILES:
        provider = providers.get(profile)
        if provider is None:
            checks[profile] = {"configured": False, "ready": False}
            missing.append(f"Configure a Vulcan provider for the {profile} profile.")
            continue

        check: dict[str, Any] = {
            "configured": True,
            "provider_id": provider.provider_id,
            "kind": provider.kind,
            "base_url": provider.base_url,
            "model": provider.model,
            "ready": False,
        }
        if provider.kind != "ollama":
            check["ready"] = bool(provider.enabled)
            checks[profile] = check
            if not check["ready"]:
                missing.append(f"Enable provider {provider.provider_id} for the {profile} profile.")
            continue

        try:
            available = await _ollama_tags(provider)
        except Exception as exc:  # noqa: BLE001 - operator report should preserve failure class
            check["host_reachable"] = False
            check["error"] = type(exc).__name__
            missing.append(f"Reach Ollama at {provider.base_url} for the {profile} profile.")
        else:
            check["host_reachable"] = True
            check["model_available"] = _ollama_model_available(provider.model, available)
            check["available_model_count"] = len(available)
            check["ready"] = bool(check["model_available"])
            if not check["model_available"]:
                missing.append(f"Install model {provider.model} for the {profile} profile.")
        checks[profile] = check

    ready = all(check.get("ready") is True for check in checks.values()) and len(checks) == len(REQUIRED_PROFILES)
    return _operator_report(
        "vulcan-readiness",
        {
            "status": "ready" if ready else "blocked",
            "ready_for_certification": ready,
            "checks": checks,
            "missing": missing,
        },
        dry_run=False,
    )


async def _pull_profile(settings: Settings, *, profile: str, dry_run: bool) -> dict[str, Any]:
    providers = _providers_by_profile(settings)
    provider = providers.get(profile)
    if provider is None:
        return _operator_report(
            "vulcan-pull-profile",
            {"status": "failed", "profile": profile, "error": "profile is not configured"},
            dry_run=dry_run,
        )
    plan = {
        "profile": profile,
        "provider_id": provider.provider_id,
        "kind": provider.kind,
        "base_url": provider.base_url,
        "model": provider.model,
    }
    if provider.kind != "ollama":
        return _operator_report(
            "vulcan-pull-profile",
            {"status": "failed", "plan": plan, "error": "only Ollama profiles can be pulled"},
            dry_run=dry_run,
        )
    if dry_run:
        return _operator_report("vulcan-pull-profile", {"status": "dry-run", "plan": plan}, dry_run=True)

    try:
        status_code = await _pull_ollama_model(provider)
    except Exception as exc:  # noqa: BLE001 - operator report should preserve failure class
        return _operator_report(
            "vulcan-pull-profile",
            {"status": "failed", "plan": plan, "error": type(exc).__name__},
            dry_run=False,
        )
    return _operator_report(
        "vulcan-pull-profile",
        {"status": "pulled", "plan": plan, "http_status": status_code},
        dry_run=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Operate Vulcan model profiles")
    parser.add_argument(
        "--env-file",
        help="Optional Freyja environment file, such as deploy/compose/director/.env.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    readiness_parser = subparsers.add_parser("readiness", help="Check required Vulcan profile models.")
    readiness_parser.add_argument("--output", type=Path, help="Optional path to write the JSON report.")

    pull_parser = subparsers.add_parser("pull-profile", help="Pull the model configured for one Vulcan profile.")
    pull_parser.add_argument("profile", choices=REQUIRED_PROFILES)
    pull_parser.add_argument("--yes", action="store_true", help="Actually pull the model. Defaults to dry-run.")
    pull_parser.add_argument("--output", type=Path, help="Optional path to write the JSON report.")

    args = parser.parse_args(argv)
    settings = _settings(args.env_file)

    if args.command == "readiness":
        report = asyncio.run(_readiness(settings))
        _render_report(report, args.output)
        return 0 if report.get("status") == "ready" else 1
    if args.command == "pull-profile":
        report = asyncio.run(_pull_profile(settings, profile=args.profile, dry_run=not args.yes))
        _render_report(report, args.output)
        return 0 if report.get("status") in {"dry-run", "pulled"} else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
