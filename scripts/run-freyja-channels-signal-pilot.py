#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from freyja.channel_transports import ChannelTransportError, SignalCliRestConfig, SignalCliRestTransport
from freyja.channels import (
    ChannelClientError,
    ChannelPolicyError,
    FileChannelStore,
    FreyjaChannels,
    OpenWebUIChatClient,
)


DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "freyja-channels-signal-pilot.json"
DEFAULT_STATE_DIR = REPO_ROOT / "data" / "freyja-channels"
DEFAULT_POLL_INTERVAL_SECONDS = 5.0


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
    parser = argparse.ArgumentParser(description="Run the deterministic Freyja Signal pilot channel.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--once", action="store_true", help="Run one receive/reply iteration and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Check configuration without calling Signal or Open WebUI.")
    parser.add_argument("--poll-interval", type=float, default=_env_float("FREYJA_CHANNEL_SIGNAL_POLL_INTERVAL", DEFAULT_POLL_INTERVAL_SECONDS))
    parser.add_argument("--max-iterations", type=int, default=0, help="Limit receive iterations. 0 means no limit.")
    return parser


def _csv_set(name: str) -> set[str]:
    raw = os.environ.get(name, "")
    return {item.strip() for item in raw.replace(";", ",").split(",") if item.strip()}


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


def _csv_map(name: str) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in _csv_set(name):
        if ":" not in item:
            continue
        sender, identity = item.split(":", 1)
        if sender.strip() and identity.strip():
            mapping[sender.strip()] = identity.strip()
    return mapping


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


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _missing_configuration(checks: dict[str, bool]) -> list[str]:
    missing: list[str] = []
    if not checks["signal_rest_api_configured"]:
        missing.append("SIGNAL_REST_API_URL")
    if not checks["signal_account_configured"]:
        missing.append("SIGNAL_ACCOUNT_NUMBER")
    if not checks["allowlist_configured"]:
        missing.append("SIGNAL_ALLOWED_SENDERS")
    if not checks["identity_map_configured"]:
        missing.append("SIGNAL_IDENTITY_MAP")
    elif not checks["allowlist_identity_map_complete"]:
        missing.append("SIGNAL_IDENTITY_MAP:missing_allowlist_entries")
    if not checks["open_webui_api_key_configured"]:
        missing.append("OPEN_WEBUI_API_KEY")
    return missing


def _next_actions(missing: list[str], *, ready: bool) -> list[str]:
    if ready:
        return ["Run without --dry-run, preferably with --once first, and verify the generated round-trip report."]
    action_map = {
        "SIGNAL_REST_API_URL": "Set SIGNAL_REST_API_URL for the existing signal-cli-rest-api endpoint.",
        "SIGNAL_ACCOUNT_NUMBER": "Set SIGNAL_ACCOUNT_NUMBER for the registered dedicated Signal account.",
        "SIGNAL_ALLOWED_SENDERS": "Set SIGNAL_ALLOWED_SENDERS with reviewed E.164 family senders; keep an empty allowlist as deny-all.",
        "SIGNAL_IDENTITY_MAP": "Map every allowed Signal sender to an approved Freyja identity in SIGNAL_IDENTITY_MAP.",
        "SIGNAL_IDENTITY_MAP:missing_allowlist_entries": "Map every allowed Signal sender to an approved Freyja identity in SIGNAL_IDENTITY_MAP.",
        "OPEN_WEBUI_API_KEY": "Set OPEN_WEBUI_API_KEY or OPEN_WEBUI_API_KEY_FILE outside source control.",
    }
    actions: list[str] = []
    for key, action in action_map.items():
        if key in missing and action not in actions:
            actions.append(action)
    actions.append("Rerun scripts/run-freyja-channels-signal-pilot.py --dry-run and require ready=true before live receive/send.")
    return actions


def readiness(args: argparse.Namespace) -> dict[str, object]:
    signal_config = SignalCliRestConfig.from_env()
    open_webui = OpenWebUIChatClient()
    allowlist = _signal_allowed_senders()
    identities = _signal_identity_map()
    checks = {
        "signal_account_configured": bool(signal_config.account_number.strip()),
        "signal_rest_api_configured": bool(signal_config.rest_api_url.strip()),
        "open_webui_api_key_configured": open_webui.configured,
        "allowlist_configured": bool(allowlist),
        "identity_map_configured": bool(identities),
        "allowlist_identity_map_complete": bool(allowlist) and allowlist <= set(identities),
    }
    ready = all(checks.values())
    missing = _missing_configuration(checks)
    return {
        "report_type": "freyja-channels-signal-pilot",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "mode": "dry-run" if args.dry_run else "run",
        "secrets_included": False,
        "private_content_included": False,
        "ready": ready,
        "checks": checks,
        "missing_configuration": missing,
        "next_actions": _next_actions(missing, ready=ready),
        "state_dir": _display_path(args.state_dir),
    }


def run_once(*, service: FreyjaChannels, transport: SignalCliRestTransport) -> dict[str, int]:
    messages = transport.receive()
    handled = 0
    denied = 0
    failed = 0
    for message in messages:
        try:
            response = service.handle(message)
            transport.send(recipient=message.sender, text=response)
            handled += 1
        except (ChannelPolicyError, ChannelClientError, ChannelTransportError):
            denied += 1
        except Exception:
            failed += 1
    return {"messages": len(messages), "handled": handled, "denied_or_client_failed": denied, "failed": failed}


def run_loop(args: argparse.Namespace) -> dict[str, object]:
    allowlists = {"signal": _signal_allowed_senders()}
    identities = {"signal": _signal_identity_map()}
    service = FreyjaChannels(allowlists=allowlists, identity_maps=identities, store=FileChannelStore(args.state_dir), client=OpenWebUIChatClient())
    transport = SignalCliRestTransport()
    totals = {"messages": 0, "handled": 0, "denied_or_client_failed": 0, "failed": 0}
    iterations = 0
    while True:
        result = run_once(service=service, transport=transport)
        for key, value in result.items():
            totals[key] += value
        iterations += 1
        if args.once or (args.max_iterations and iterations >= args.max_iterations):
            break
        time.sleep(max(args.poll_interval, 0.1))
    return {
        "report_type": "freyja-channels-signal-pilot",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
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
