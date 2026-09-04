#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freyja.channel_transports import SignalCliRestConfig, TelegramPilotConfig
from freyja.channels import DEFAULT_POLICY, DEFAULT_STATE_DIR, FreyjaChannels, OpenWebUIChatClient


DEFAULT_OUTPUT = Path("certification/reports/freyja-channels-readiness.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check Freyja channels readiness without exposing secrets.")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _env_count(name: str) -> int:
    raw = os.environ.get(name, "")
    return len([item for item in raw.replace(";", ",").split(",") if item.strip()])


def build_report(policy: Path = DEFAULT_POLICY) -> dict[str, Any]:
    service = FreyjaChannels(policy_path=policy)
    channels = service.policy.get("channels") or {}
    telegram = channels.get("telegram") or {}
    signal = channels.get("signal") or {}
    whatsapp = channels.get("whatsapp") or {}
    telegram_allowed = _env_count(str(telegram.get("sender_allowlist_env") or "TELEGRAM_ALLOWED_USER_IDS"))
    signal_allowed = _env_count(str(signal.get("sender_allowlist_env") or "SIGNAL_ALLOWED_SENDERS"))
    telegram_transport = TelegramPilotConfig.from_env()
    signal_transport = SignalCliRestConfig.from_env()
    open_webui_client = OpenWebUIChatClient()
    return {
        "report_type": "freyja-channels-readiness",
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
            "empty_allowlist": telegram.get("empty_allowlist"),
            "ready_for_live_round_trip": telegram_allowed > 0 and telegram_transport.configured,
        },
        "signal": {
            "status": signal.get("status"),
            "transport": signal.get("transport"),
            "transport_adapter": "SignalCliRestTransport",
            "transport_configured": signal_transport.configured,
            "allowlist_configured": signal_allowed > 0,
            "allowlist_count": signal_allowed,
            "empty_allowlist": signal.get("empty_allowlist"),
            "ready_for_live_round_trip": signal_allowed > 0 and signal_transport.configured,
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
