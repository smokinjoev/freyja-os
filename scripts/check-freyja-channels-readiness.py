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


def _signal_allowed_senders() -> set[str]:
    senders: set[str] = set()
    for item in _csv_set("SIGNAL_ALLOWED_SENDERS"):
        if "=" in item:
            _, sender = item.split("=", 1)
            if sender.strip():
                senders.add(sender.strip())
        else:
            senders.add(item)
    return senders


def _signal_identity_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in _csv_set("SIGNAL_ALLOWED_SENDERS"):
        if "=" not in item:
            continue
        identity, sender = item.split("=", 1)
        if sender.strip() and identity.strip():
            mapping[sender.strip()] = identity.strip()
    mapping.update(_csv_map("SIGNAL_IDENTITY_MAP"))
    return mapping


def _missing_channel_configuration(*, allowlist_env: str, allowlist_count: int, transport_envs: list[str]) -> list[str]:
    missing = []
    if allowlist_count <= 0:
        missing.append(allowlist_env)
    for name in transport_envs:
        if not os.environ.get(name, "").strip():
            missing.append(name)
    return missing


def _remove_open_webui_key_if_configured(missing: list[str], *, configured: bool) -> list[str]:
    if not configured:
        return missing
    return [item for item in missing if item != "OPEN_WEBUI_API_KEY"]


def _channel_next_actions(channel: str, missing: list[str], *, ready: bool) -> list[str]:
    if ready:
        return [f"Run the {channel} live round-trip pilot and archive the generated readiness report."]
    actions: list[str] = []
    if channel == "telegram":
        actions.append("Stop any other Telegram getUpdates poller before running the live pilot.")
        order = [
            ("TELEGRAM_BOT_TOKEN", "Create or choose the Telegram bot and set TELEGRAM_BOT_TOKEN outside source control."),
            ("TELEGRAM_ALLOWED_USER_IDS", "Set TELEGRAM_ALLOWED_USER_IDS with reviewed family sender IDs; keep an empty allowlist as deny-all."),
            ("TELEGRAM_IDENTITY_MAP", "Map every allowed Telegram sender to an approved Freyja identity in TELEGRAM_IDENTITY_MAP."),
            ("OPEN_WEBUI_API_KEY", "Set OPEN_WEBUI_API_KEY or OPEN_WEBUI_API_KEY_FILE outside source control."),
        ]
        final_action = "Run scripts/run-freyja-channels-telegram-pilot.py --dry-run before enabling the long-polling pilot."
    else:
        order = [
            ("SIGNAL_REST_API_URL", "Set SIGNAL_REST_API_URL for the existing signal-cli-rest-api endpoint."),
            ("SIGNAL_ACCOUNT_NUMBER", "Set SIGNAL_ACCOUNT_NUMBER for the registered dedicated Signal account."),
            ("SIGNAL_ALLOWED_SENDERS", "Set SIGNAL_ALLOWED_SENDERS with reviewed E.164 family senders; keep an empty allowlist as deny-all."),
            ("SIGNAL_IDENTITY_MAP", "Map every allowed Signal sender to an approved Freyja identity in SIGNAL_IDENTITY_MAP."),
            ("OPEN_WEBUI_API_KEY", "Set OPEN_WEBUI_API_KEY or OPEN_WEBUI_API_KEY_FILE outside source control."),
        ]
        final_action = "Run scripts/run-freyja-channels-signal-pilot.py --dry-run after the signal live round-trip registration path is healthy."
    missing_set = set(missing)
    for key, action in order:
        if key in missing_set or f"{key}:missing_allowlist_entries" in missing_set:
            actions.append(action)
    actions.append(final_action)
    return actions


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
    signal_allowlist = _signal_allowed_senders()
    signal_allowed = len(signal_allowlist)
    telegram_allowlist = _csv_set(str(telegram.get("sender_allowlist_env") or "TELEGRAM_ALLOWED_USER_IDS"))
    telegram_identities = _csv_map("TELEGRAM_IDENTITY_MAP")
    signal_identities = _signal_identity_map()
    telegram_transport = TelegramPilotConfig.from_env()
    signal_transport = SignalCliRestConfig.from_env()
    open_webui_client = OpenWebUIChatClient()
    telegram_missing = _missing_channel_configuration(
        allowlist_env=str(telegram.get("sender_allowlist_env") or "TELEGRAM_ALLOWED_USER_IDS"),
        allowlist_count=telegram_allowed,
        transport_envs=["TELEGRAM_BOT_TOKEN", "TELEGRAM_IDENTITY_MAP", "OPEN_WEBUI_API_KEY"],
    )
    telegram_missing = _remove_open_webui_key_if_configured(telegram_missing, configured=open_webui_client.configured)
    signal_missing = _missing_channel_configuration(
        allowlist_env=str(signal.get("sender_allowlist_env") or "SIGNAL_ALLOWED_SENDERS"),
        allowlist_count=signal_allowed,
        transport_envs=["SIGNAL_ACCOUNT_NUMBER", "SIGNAL_IDENTITY_MAP", "OPEN_WEBUI_API_KEY"],
    )
    if signal_identities:
        signal_missing = [item for item in signal_missing if item != "SIGNAL_IDENTITY_MAP"]
    signal_missing = _remove_open_webui_key_if_configured(signal_missing, configured=open_webui_client.configured)
    if not os.environ.get("SIGNAL_REST_API_URL", "").strip() and not signal_transport.configured:
        signal_missing.append("SIGNAL_REST_API_URL")
    if telegram_allowlist and not telegram_allowlist <= set(telegram_identities):
        telegram_missing.append("TELEGRAM_IDENTITY_MAP:missing_allowlist_entries")
    if signal_allowlist and not signal_allowlist <= set(signal_identities):
        signal_missing.append("SIGNAL_IDENTITY_MAP:missing_allowlist_entries")
    telegram_ready = (
        telegram_allowed > 0
        and telegram_transport.configured
        and open_webui_client.configured
        and bool(telegram_identities)
        and telegram_allowlist <= set(telegram_identities)
    )
    signal_ready = (
        signal_allowed > 0
        and signal_transport.configured
        and open_webui_client.configured
        and bool(signal_identities)
        and signal_allowlist <= set(signal_identities)
    )
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
            "endpoint": f"{open_webui_client.base_url}/api/chat/completions",
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
            "identity_map_count": len(telegram_identities),
            "allowlist_identity_map_complete": bool(telegram_allowlist) and telegram_allowlist <= set(telegram_identities),
            "empty_allowlist": telegram.get("empty_allowlist"),
            "ready_for_live_round_trip": telegram_ready,
            "missing_configuration": telegram_missing,
            "next_actions": _channel_next_actions("telegram", telegram_missing, ready=telegram_ready),
        },
        "signal": {
            "status": signal.get("status"),
            "transport": signal.get("transport"),
            "transport_adapter": "SignalCliRestTransport",
            "transport_configured": signal_transport.configured,
            "allowlist_configured": signal_allowed > 0,
            "allowlist_count": signal_allowed,
            "identity_map_configured": bool(signal_identities),
            "identity_map_count": len(signal_identities),
            "allowlist_identity_map_complete": bool(signal_allowlist) and signal_allowlist <= set(signal_identities),
            "empty_allowlist": signal.get("empty_allowlist"),
            "ready_for_live_round_trip": signal_ready,
            "missing_configuration": signal_missing,
            "next_actions": _channel_next_actions("signal", signal_missing, ready=signal_ready),
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
