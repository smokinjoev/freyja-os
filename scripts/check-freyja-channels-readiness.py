#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freyja.channel_transports import SignalCliRestConfig, TelegramPilotConfig
from freyja.channels import DEFAULT_POLICY, DEFAULT_STATE_DIR, FreyjaChannels, OpenWebUIChatClient


DEFAULT_OUTPUT = Path("certification/reports/freyja-channels-readiness.json")
REPO_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Freyja channels readiness without exposing secrets.")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _env_count(name: str) -> int:
    raw = os.environ.get(name, "")
    return len([item for item in raw.replace(";", ",").split(",") if item.strip()])


def _csv_set(name: str) -> set[str]:
    raw = os.environ.get(name, "")
    return {item.strip() for item in raw.replace(";", ",").split(",") if item.strip()}


def _csv_map(name: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in _csv_set(name):
        if ":" not in item:
            continue
        sender, identity = item.split(":", 1)
        if sender.strip() and identity.strip():
            mapping[sender.strip()] = identity.strip()
    return mapping


def _missing_channel_configuration(*, allowlist_env: str, allowlist_count: int, transport_envs: list[str]) -> list[str]:
    missing = []
    if allowlist_count <= 0:
        missing.append(allowlist_env)
    for name in transport_envs:
        if not os.environ.get(name, "").strip():
            missing.append(name)
    return missing


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def build_report(policy: Path = DEFAULT_POLICY) -> dict[str, Any]:
    service = FreyjaChannels(policy_path=policy)
    channels = service.policy.get("channels") or {}
    telegram = channels.get("telegram") or {}
    signal = channels.get("signal") or {}
    whatsapp = channels.get("whatsapp") or {}
    telegram_allowed = _env_count(str(telegram.get("sender_allowlist_env") or "TELEGRAM_ALLOWED_USER_IDS"))
    signal_allowed = _env_count(str(signal.get("sender_allowlist_env") or "SIGNAL_ALLOWED_SENDERS"))
    telegram_allowlist = _csv_set(str(telegram.get("sender_allowlist_env") or "TELEGRAM_ALLOWED_USER_IDS"))
    signal_allowlist = _csv_set(str(signal.get("sender_allowlist_env") or "SIGNAL_ALLOWED_SENDERS"))
    telegram_identities = _csv_map("TELEGRAM_IDENTITY_MAP")
    signal_identities = _csv_map("SIGNAL_IDENTITY_MAP")
    telegram_transport = TelegramPilotConfig.from_env()
    signal_transport = SignalCliRestConfig.from_env()
    open_webui_client = OpenWebUIChatClient()
    telegram_missing = _missing_channel_configuration(
        allowlist_env=str(telegram.get("sender_allowlist_env") or "TELEGRAM_ALLOWED_USER_IDS"),
        allowlist_count=telegram_allowed,
        transport_envs=["TELEGRAM_BOT_TOKEN", "TELEGRAM_IDENTITY_MAP", "OPEN_WEBUI_API_KEY"],
    )
    signal_missing = _missing_channel_configuration(
        allowlist_env=str(signal.get("sender_allowlist_env") or "SIGNAL_ALLOWED_SENDERS"),
        allowlist_count=signal_allowed,
        transport_envs=["SIGNAL_ACCOUNT_NUMBER", "SIGNAL_IDENTITY_MAP", "OPEN_WEBUI_API_KEY"],
    )
    if not os.environ.get("SIGNAL_REST_API_URL", "").strip() and not signal_transport.configured:
        signal_missing.append("SIGNAL_REST_API_URL")
    if telegram_allowlist and not telegram_allowlist <= set(telegram_identities):
        telegram_missing.append("TELEGRAM_IDENTITY_MAP:missing_allowlist_entries")
    if signal_allowlist and not signal_allowlist <= set(signal_identities):
        signal_missing.append("SIGNAL_IDENTITY_MAP:missing_allowlist_entries")
    return {
        "report_type": "freyja-channels-readiness",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "secrets_included": False,
        "private_content_included": False,
        "deterministic_gateway_only": service.policy.get("principle") == "deterministic_gateway_only",
        "model_routing_prohibited": (service.policy.get("prohibitions") or {}).get("model_routing") is True,
        "independent_agent_intelligence_prohibited": (service.policy.get("prohibitions") or {}).get("independent_agent_intelligence") is True,
        "thread_persistence_store": {
            "backend": "file",
            "path": str((DEFAULT_STATE_DIR / "threads.json").relative_to(Path(__file__).resolve().parents[1])),
            "raw_sender_logged": False,
        },
        "audit_store": {
            "backend": "jsonl",
            "path": str((DEFAULT_STATE_DIR / "audit.jsonl").relative_to(Path(__file__).resolve().parents[1])),
            "message_body_logged": False,
            "raw_sender_logged": False,
            "denied_attempts_logged": True,
            "response_failures_logged": True,
        },
        "open_webui_client": {
            "endpoint": f"{open_webui_client.base_url}/openai/v1/chat/completions",
            "api_key_configured": open_webui_client.configured,
            "secrets_included": False,
        },
        "telegram": {
            "status": telegram.get("status"),
            "transport": telegram.get("transport"),
            "transport_adapter": "TelegramLongPollingTransport",
            "transport_configured": telegram_transport.configured,
            "allowlist_configured": telegram_allowed > 0,
            "allowlist_count": telegram_allowed,
            "identity_map_configured": bool(telegram_identities),
            "allowlist_identity_map_complete": bool(telegram_allowlist) and telegram_allowlist <= set(telegram_identities),
            "empty_allowlist": telegram.get("empty_allowlist"),
            "ready_for_live_round_trip": (
                telegram_allowed > 0
                and telegram_transport.configured
                and open_webui_client.configured
                and bool(telegram_identities)
                and telegram_allowlist <= set(telegram_identities)
            ),
            "missing_configuration": telegram_missing,
        },
        "signal": {
            "status": signal.get("status"),
            "transport": signal.get("transport"),
            "transport_adapter": "SignalCliRestTransport",
            "transport_configured": signal_transport.configured,
            "allowlist_configured": signal_allowed > 0,
            "allowlist_count": signal_allowed,
            "identity_map_configured": bool(signal_identities),
            "allowlist_identity_map_complete": bool(signal_allowlist) and signal_allowlist <= set(signal_identities),
            "empty_allowlist": signal.get("empty_allowlist"),
            "ready_for_live_round_trip": (
                signal_allowed > 0
                and signal_transport.configured
                and open_webui_client.configured
                and bool(signal_identities)
                and signal_allowlist <= set(signal_identities)
            ),
            "missing_configuration": signal_missing,
        },
        "whatsapp": {
            "status": whatsapp.get("status"),
            "ready_for_live_round_trip": False,
            "reason": whatsapp.get("reason"),
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(args.policy)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
