#!/usr/bin/env python3
"""Small operator CLI for the Signal connector."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VENV_PYTHON = _PROJECT_ROOT / ".venv" / "bin" / "python"
if _VENV_PYTHON.exists() and Path(sys.executable) != _VENV_PYTHON:
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON), *sys.argv])

_SRC_DIR = str(_PROJECT_ROOT / "src")
_ROOT_DIR = str(_PROJECT_ROOT)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(1, _ROOT_DIR)

from connectors.signal.config import SignalSettings  # noqa: E402


def _configured_recipients(settings: SignalSettings) -> list[str]:
    return sorted(settings.allowed_sender_set)


def _safe_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _smoke_report(result: dict[str, object], *, dry_run: bool) -> dict[str, object]:
    report = {
        "schema_version": "1.0",
        "report_type": "signal-live-smoke",
        "timestamp": datetime.now(UTC).isoformat(),
        "dry_run": dry_run,
        "sent": 0,
        "failed": 0,
    }
    report.update(result)
    return report


def _send_payload(settings: SignalSettings, recipient: str, text: str) -> dict[str, object]:
    return {
        "message": text,
        "number": settings.signal_account_number.strip(),
        "recipients": [recipient],
    }


async def _send_to(settings: SignalSettings, recipient: str, text: str) -> None:
    if not settings.transport_configured:
        raise RuntimeError("SIGNAL_ACCOUNT_NUMBER is not configured")
    payload = _send_payload(settings, recipient, text)
    async with httpx.AsyncClient(timeout=settings.signal_transport_timeout_seconds) as client:
        response = await client.post(
            f"{settings.signal_rest_api_url.rstrip('/')}/v2/send",
            json=payload,
        )
        response.raise_for_status()


async def _registered_accounts(settings: SignalSettings) -> list[str]:
    async with httpx.AsyncClient(timeout=min(settings.signal_transport_timeout_seconds, 10.0)) as client:
        response = await client.get(f"{settings.signal_rest_api_url.rstrip('/')}/v1/accounts")
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        return []
    return [value for value in payload if isinstance(value, str)]


async def _rest_about(settings: SignalSettings) -> dict[str, object]:
    async with httpx.AsyncClient(timeout=min(settings.signal_transport_timeout_seconds, 10.0)) as client:
        response = await client.get(f"{settings.signal_rest_api_url.rstrip('/')}/v1/about")
        response.raise_for_status()
        payload = response.json()
    return payload if isinstance(payload, dict) else {}


async def _readiness(settings: SignalSettings, *, check_registered: bool) -> dict[str, object]:
    recipients = _configured_recipients(settings)
    checks: dict[str, object] = {
        "signal_enabled": settings.signal_enabled,
        "connector_token_configured": bool(settings.freyja_connector_token.strip()),
        "director_url_configured": bool(settings.freyja_director_url.strip()),
        "rest_api_url_configured": bool(settings.signal_rest_api_url.strip()),
        "account_number_configured": settings.transport_configured,
        "allowed_recipient_count": len(recipients),
        "recipient_hashes": [_safe_hash(recipient) for recipient in recipients],
    }

    missing: list[str] = []
    if not settings.signal_enabled:
        missing.append("Set SIGNAL_ENABLED=true after the Signal account and allowlist are reviewed.")
    if not settings.freyja_connector_token.strip():
        missing.append("Set FREYJA_CONNECTOR_TOKEN to the Director connector token.")
    if not settings.freyja_director_url.strip():
        missing.append("Set FREYJA_DIRECTOR_URL to the Atlas Director endpoint.")
    if not settings.signal_rest_api_url.strip():
        missing.append("Set SIGNAL_REST_API_URL to the signal-cli REST API endpoint.")
    if not settings.transport_configured:
        missing.append("Set SIGNAL_ACCOUNT_NUMBER to the linked or registered Signal account.")
    if not recipients:
        missing.append("Set SIGNAL_ALLOWED_SENDERS to at least one reviewed E.164 sender.")

    rest_reachable = False
    try:
        about = await _rest_about(settings)
    except Exception as exc:  # noqa: BLE001 - operator output should preserve failure class
        checks["signal_rest_health"] = {"ok": False, "error": type(exc).__name__}
        missing.append("Start signal-cli-rest-api and make SIGNAL_REST_API_URL reachable.")
    else:
        rest_reachable = True
        checks["signal_rest_health"] = {"ok": True, "payload_keys": sorted(str(key) for key in about)}

    if check_registered:
        try:
            accounts = await _registered_accounts(settings)
        except Exception as exc:  # noqa: BLE001 - operator output should preserve failure class
            checks["account_registered"] = False
            checks["registration_error"] = type(exc).__name__
            if rest_reachable:
                missing.append("Confirm the Signal REST API can list registered accounts.")
        else:
            account = settings.signal_account_number.strip()
            checks["registered_account_count"] = len(accounts)
            checks["account_registered"] = bool(account and account in accounts)
            if account and account not in accounts:
                missing.append("Register or link SIGNAL_ACCOUNT_NUMBER in signal-cli-rest-api.")

    ready = not missing
    return {
        "schema_version": "1.0",
        "report_type": "signal-readiness",
        "timestamp": datetime.now(UTC).isoformat(),
        "status": "ready" if ready else "blocked",
        "ready_for_live_smoke": ready,
        "checks": checks,
        "missing": missing,
    }


async def _live_smoke(
    settings: SignalSettings,
    *,
    recipient: str | None,
    text: str,
    dry_run: bool,
    check_registered: bool = False,
) -> dict[str, object]:
    recipients = _configured_recipients(settings)
    if not recipients:
        return _smoke_report({"status": "error", "error": "allowlist is empty"}, dry_run=dry_run)

    target = recipient or recipients[0]
    if target not in recipients:
        return _smoke_report(
            {
                "status": "error",
                "error": "recipient is not in SIGNAL_ALLOWED_SENDERS",
                "recipient_hash": _safe_hash(target),
                "allowed_recipient_count": len(recipients),
            },
            dry_run=dry_run,
        )

    registration: dict[str, object] = {}
    if check_registered:
        try:
            accounts = await _registered_accounts(settings)
        except Exception as exc:  # noqa: BLE001 - operator report should preserve failure class
            registration = {"account_registered": False, "registration_error": type(exc).__name__}
        else:
            account = settings.signal_account_number.strip()
            registration = {
                "account_registered": account in accounts,
                "registered_account_count": len(accounts),
            }

    plan = {
        "recipient_hash": _safe_hash(target),
        "recipient_count": len(recipients),
        "account_number_configured": settings.transport_configured,
        "signal_enabled": settings.signal_enabled,
        "rest_api_url": settings.signal_rest_api_url,
        "text_length": len(text),
        **registration,
    }

    if dry_run:
        return _smoke_report({"status": "dry-run", "plan": plan}, dry_run=True)

    if not settings.signal_enabled:
        return _smoke_report(
            {"status": "failed", "plan": plan, "failed": 1, "error": "SIGNAL_ENABLED is false"},
            dry_run=False,
        )
    if not settings.transport_configured:
        return _smoke_report(
            {"status": "failed", "plan": plan, "failed": 1, "error": "SIGNAL_ACCOUNT_NUMBER is not configured"},
            dry_run=False,
        )

    try:
        await _send_to(settings, target, text)
    except Exception as exc:  # noqa: BLE001 - operator JSON should report the send failure
        return _smoke_report(
            {
                "status": "failed",
                "plan": plan,
                "sent": 0,
                "failed": 1,
                "error": type(exc).__name__,
            },
            dry_run=False,
        )
    return _smoke_report({"status": "sent", "plan": plan, "sent": 1, "failed": 0}, dry_run=False)


def _settings(env_file: str | None) -> SignalSettings:
    return SignalSettings(_env_file=env_file) if env_file else SignalSettings()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operate the Signal connector")
    parser.add_argument(
        "--env-file",
        help="Optional Signal connector environment file, such as deploy/compose/signal/.env.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("allowlist", help="Print configured allowlist metadata")

    readiness = subparsers.add_parser(
        "readiness",
        help="Check Signal configuration and REST/account readiness without sending.",
    )
    readiness.add_argument(
        "--check-registered",
        action="store_true",
        help="Check /v1/accounts on the configured Signal REST API.",
    )
    readiness.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path for readiness evidence.",
    )

    smoke = subparsers.add_parser(
        "live-smoke",
        help="Send one operator-approved Signal smoke test to an allowlisted recipient.",
    )
    smoke.add_argument(
        "--recipient",
        help="Allowlisted recipient to send to. Defaults to the first configured recipient.",
    )
    smoke.add_argument(
        "--text",
        default="Freyja 2.0 Signal live smoke test.",
        help="Smoke-test message text.",
    )
    smoke.add_argument(
        "--yes",
        action="store_true",
        help="Actually send the smoke message. Without this flag, the command is a dry-run.",
    )
    smoke.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the exact smoke report without sending. This is the default.",
    )
    smoke.add_argument(
        "--check-registered",
        action="store_true",
        help="Check /v1/accounts on the configured Signal REST API before reporting the plan.",
    )
    smoke.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path for readiness evidence.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    settings = _settings(args.env_file)

    if args.command == "allowlist":
        recipients = _configured_recipients(settings)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "recipient_count": len(recipients),
                    "recipient_hashes": [_safe_hash(recipient) for recipient in recipients],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.command == "readiness":
        result = asyncio.run(_readiness(settings, check_registered=args.check_registered))
        rendered = json.dumps(result, indent=2, sort_keys=True)
        print(rendered)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        return 0 if result["ready_for_live_smoke"] is True else 1

    if args.command == "live-smoke":
        dry_run = args.dry_run or not args.yes
        result = asyncio.run(
            _live_smoke(
                settings,
                recipient=args.recipient,
                text=args.text,
                dry_run=dry_run,
                check_registered=args.check_registered,
            )
        )
        rendered = json.dumps(result, indent=2, sort_keys=True)
        print(rendered)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        return 0 if result["status"] in {"dry-run", "sent"} else 1

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
