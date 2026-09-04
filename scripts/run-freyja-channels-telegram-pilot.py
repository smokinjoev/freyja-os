#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from freyja.channel_transports import ChannelTransportError, TelegramLongPollingTransport, TelegramPilotConfig
from freyja.channels import (
    ChannelClientError,
    ChannelPolicyError,
    FileChannelStore,
    FreyjaChannels,
    OpenWebUIChatClient,
)


DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "freyja-channels-telegram-pilot.json"
DEFAULT_STATE_DIR = REPO_ROOT / "data" / "freyja-channels"
DEFAULT_POLL_INTERVAL_SECONDS = 2.0


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the deterministic Freyja Telegram pilot channel.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--offset-file", type=Path)
    parser.add_argument("--once", action="store_true", help="Run one polling iteration and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Check configuration without calling Telegram or Open WebUI.")
    parser.add_argument("--poll-interval", type=float, default=_env_float("FREYJA_CHANNEL_TELEGRAM_POLL_INTERVAL", DEFAULT_POLL_INTERVAL_SECONDS))
    parser.add_argument("--max-iterations", type=int, default=0, help="Limit polling iterations. 0 means no limit.")
    return parser


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


def _read_offset(path: Path) -> int | None:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    return int(raw) if raw else None


def _write_offset(path: Path, offset: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{offset}\n", encoding="utf-8")


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def readiness(args: argparse.Namespace) -> dict[str, Any]:
    telegram_config = TelegramPilotConfig.from_env()
    open_webui = OpenWebUIChatClient()
    allowlist = _csv_set("TELEGRAM_ALLOWED_USER_IDS")
    identities = _csv_map("TELEGRAM_IDENTITY_MAP")
    checks = {
        "telegram_bot_token_configured": telegram_config.configured,
        "open_webui_api_key_configured": open_webui.configured,
        "allowlist_configured": bool(allowlist),
        "identity_map_configured": bool(identities),
        "allowlist_identity_map_complete": bool(allowlist) and allowlist <= set(identities),
    }
    return {
        "report_type": "freyja-channels-telegram-pilot",
        "mode": "dry-run" if args.dry_run else "run",
        "secrets_included": False,
        "private_content_included": False,
        "ready": all(checks.values()),
        "checks": checks,
        "state_dir": _display_path(args.state_dir),
        "offset_file": _display_path(args.offset_file or args.state_dir / "telegram.offset"),
    }


def run_once(
    *,
    service: FreyjaChannels,
    transport: TelegramLongPollingTransport,
    offset_file: Path,
) -> dict[str, int]:
    offset = _read_offset(offset_file)
    updates = transport.get_update_messages(offset=offset)
    handled = 0
    denied = 0
    failed = 0
    max_update_id = offset - 1 if offset is not None else None
    for update in updates:
        max_update_id = update.update_id if max_update_id is None else max(max_update_id, update.update_id)
        try:
            response = service.handle(update.message)
            if update.message.chat_id:
                transport.send_message(chat_id=update.message.chat_id, text=response)
            handled += 1
        except (ChannelPolicyError, ChannelClientError, ChannelTransportError):
            denied += 1
        except Exception:
            failed += 1
    if max_update_id is not None:
        _write_offset(offset_file, max_update_id + 1)
    return {"updates": len(updates), "handled": handled, "denied_or_client_failed": denied, "failed": failed}


def run_loop(args: argparse.Namespace) -> dict[str, Any]:
    offset_file = args.offset_file or args.state_dir / "telegram.offset"
    allowlists = {"telegram": _csv_set("TELEGRAM_ALLOWED_USER_IDS")}
    identities = {"telegram": _csv_map("TELEGRAM_IDENTITY_MAP")}
    service = FreyjaChannels(allowlists=allowlists, identity_maps=identities, store=FileChannelStore(args.state_dir), client=OpenWebUIChatClient())
    transport = TelegramLongPollingTransport()
    totals = {"updates": 0, "handled": 0, "denied_or_client_failed": 0, "failed": 0}
    iterations = 0
    while True:
        result = run_once(service=service, transport=transport, offset_file=offset_file)
        for key, value in result.items():
            totals[key] += value
        iterations += 1
        if args.once or (args.max_iterations and iterations >= args.max_iterations):
            break
        time.sleep(max(args.poll_interval, 0.1))
    return {
        "report_type": "freyja-channels-telegram-pilot",
        "mode": "run",
        "secrets_included": False,
        "private_content_included": False,
        "ready": True,
        "iterations": iterations,
        "totals": totals,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = readiness(args)
    if report["ready"] and not args.dry_run:
        report = run_loop(args)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.get("ready") or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
