#!/usr/bin/env python3
"""Read-only production preflight checks for Freyja messaging connectors."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

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

from connectors.imessage.config import IMessageSettings  # noqa: E402
from connectors.signal.config import SignalSettings  # noqa: E402


def _http_health(url: str, *, timeout: float = 5.0) -> dict[str, object]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {
                "ok": 200 <= response.status < 300,
                "status_code": response.status,
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status_code": exc.code}
    except Exception as exc:  # noqa: BLE001 - operator output should stay compact
        return {"ok": False, "error": type(exc).__name__}


def _imessage_status(*, check_director: bool, env_file: str | None = None) -> dict[str, object]:
    settings = IMessageSettings(_env_file=env_file) if env_file else IMessageSettings()
    imsg_path = Path(settings.resolved_imsg_path)
    database_path = Path(settings.imessage_database_path)
    status: dict[str, object] = {
        "enabled": settings.imessage_enabled,
        "host_role": "iris-macos-launchagent",
        "director_url": settings.freyja_director_url,
        "connector_token_configured": bool(settings.freyja_connector_token),
        "imsg_path": str(imsg_path),
        "imsg_exists": imsg_path.exists(),
        "database_path": str(database_path),
        "database_exists": database_path.exists(),
        "allowed_sender_count": len(settings.allowed_sender_set),
        "watch_enabled": settings.imessage_watch_enabled,
        "poll_interval_seconds": settings.imessage_poll_interval_seconds,
        "family_observer_enabled": settings.imessage_family_observer_enabled,
        "family_chat_count": len(settings.family_chat_identifier_set),
        "provisional_reply_enabled": settings.imessage_provisional_reply_enabled,
    }
    status["ready_for_live_smoke"] = all(
        [
            status["enabled"],
            status["imsg_exists"],
            status["database_exists"],
            status["allowed_sender_count"],
            bool(settings.freyja_director_url.strip()),
        ]
    )
    if check_director:
        status["director_health"] = _http_health(
            f"{settings.freyja_director_url.rstrip('/')}/health",
            timeout=min(settings.imessage_request_timeout_seconds, 5.0),
        )
    return status


def _signal_status(
    *,
    check_director: bool,
    check_rest: bool,
    env_file: str | None = None,
) -> dict[str, object]:
    settings = SignalSettings(_env_file=env_file) if env_file else SignalSettings()
    status: dict[str, object] = {
        "enabled": settings.signal_enabled,
        "host_role": "atlas-compose",
        "director_url": settings.freyja_director_url,
        "connector_token_configured": bool(settings.freyja_connector_token),
        "rest_api_url": settings.signal_rest_api_url,
        "account_number_configured": settings.transport_configured,
        "allowed_sender_count": len(settings.allowed_sender_set),
        "poll_interval_seconds": settings.signal_poll_interval_seconds,
        "max_message_chars": settings.signal_max_message_chars,
    }
    status["ready_for_live_smoke"] = all(
        [
            status["enabled"],
            status["account_number_configured"],
            status["allowed_sender_count"],
            bool(settings.freyja_director_url.strip()),
            bool(settings.signal_rest_api_url.strip()),
        ]
    )
    if check_director:
        status["director_health"] = _http_health(
            f"{settings.freyja_director_url.rstrip('/')}/health",
            timeout=min(settings.signal_request_timeout_seconds, 5.0),
        )
    if check_rest:
        status["signal_rest_health"] = _http_health(
            f"{settings.signal_rest_api_url.rstrip('/')}/v1/about",
            timeout=min(settings.signal_transport_timeout_seconds, 5.0),
        )
    return status


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check Freyja iMessage and Signal production readiness without printing secrets."
    )
    parser.add_argument(
        "--connector",
        choices=("all", "imessage", "signal"),
        default="all",
        help="Connector to check.",
    )
    parser.add_argument(
        "--env-file",
        help="Optional connector environment file to read, such as the Iris runtime .env or Atlas Compose .env.",
    )
    parser.add_argument(
        "--check-director",
        action="store_true",
        help="Call the configured Director /health endpoint.",
    )
    parser.add_argument(
        "--check-signal-rest",
        action="store_true",
        help="Call the configured signal-cli-rest-api /v1/about endpoint.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report: dict[str, object] = {}

    if args.connector in {"all", "imessage"}:
        report["imessage"] = _imessage_status(
            check_director=args.check_director,
            env_file=args.env_file,
        )
    if args.connector in {"all", "signal"}:
        report["signal"] = _signal_status(
            check_director=args.check_director,
            check_rest=args.check_signal_rest,
            env_file=args.env_file,
        )

    print(json.dumps(report, indent=2, sort_keys=True))
    connector_reports = [value for value in report.values() if isinstance(value, dict)]
    return 0 if all(value.get("ready_for_live_smoke") for value in connector_reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
