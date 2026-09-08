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

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from freyja.channel_transports import ChannelTransportError, TelegramLongPollingTransport, TelegramPilotConfig
from freyja.channels import (
    CHANNEL_AGENT_MODEL_IDS,
    DEFAULT_POLICY,
    ChannelClientError,
    ChannelPolicyError,
    FileChannelStore,
    FreyjaChannels,
    OpenWebUIChatClient,
)


DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "freyja-channels-telegram-pilot.json"
DEFAULT_STATE_DIR = REPO_ROOT / "data" / "freyja-channels"
DEFAULT_POLL_INTERVAL_SECONDS = 2.0
DEFAULT_TELEGRAM_BOT_PROFILES = "FREYJA_JOE,CLOYD_JOE,BENEDICT_BETH,AGENT44_LIAM,JENNA"


class TelegramBotProfile:
    def __init__(
        self,
        *,
        name: str,
        token: str,
        allowed_user_ids: set[str],
        identity_map: dict[str, str],
        forced_agent: str,
    ) -> None:
        self.name = name
        self.token = token
        self.allowed_user_ids = allowed_user_ids
        self.identity_map = identity_map
        self.forced_agent = forced_agent

    @property
    def configured(self) -> bool:
        return bool(self.token.strip()) and bool(self.allowed_user_ids) and bool(self.identity_map) and bool(self.forced_agent.strip())


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
    parser.add_argument("--until-handled", action="store_true", help="Exit as soon as at least one update is handled.")
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


def _profile_key(name: str) -> str:
    return "".join(char if char.isalnum() else "_" for char in name.upper()).strip("_")


def _bot_profile_names() -> list[str]:
    raw = os.environ.get("TELEGRAM_BOT_PROFILES", DEFAULT_TELEGRAM_BOT_PROFILES)
    return [_profile_key(item) for item in raw.replace(";", ",").split(",") if _profile_key(item)]


def _bot_profiles() -> list[TelegramBotProfile]:
    profiles: list[TelegramBotProfile] = []
    for name in _bot_profile_names():
        profiles.append(
            TelegramBotProfile(
                name=name,
                token=os.environ.get(f"TELEGRAM_{name}_BOT_TOKEN", ""),
                allowed_user_ids=_csv_set(f"TELEGRAM_{name}_ALLOWED_USER_IDS"),
                identity_map=_csv_map(f"TELEGRAM_{name}_IDENTITY_MAP"),
                forced_agent=os.environ.get(f"TELEGRAM_{name}_AGENT", "").strip(),
            )
        )
    return profiles


def _active_bot_profiles() -> list[TelegramBotProfile]:
    profiles = [profile for profile in _bot_profiles() if _profile_runtime_configured(profile)]
    if profiles:
        return profiles
    return [
        TelegramBotProfile(
            name="DEFAULT",
            token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            allowed_user_ids=_csv_set("TELEGRAM_ALLOWED_USER_IDS"),
            identity_map=_csv_map("TELEGRAM_IDENTITY_MAP"),
            forced_agent=os.environ.get("TELEGRAM_FORCED_AGENT", "").strip(),
        )
    ]


def _profile_runtime_configured(profile: TelegramBotProfile) -> bool:
    forced_agent_ok = profile.name == "DEFAULT" or bool(profile.forced_agent.strip())
    return bool(profile.token.strip()) and bool(profile.allowed_user_ids) and bool(profile.identity_map) and forced_agent_ok


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


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _messaging_agents() -> dict[str, object]:
    service = FreyjaChannels(policy_path=DEFAULT_POLICY)
    catalog = service.policy.get("agent_catalog") or {}
    return {
        "app": "telegram",
        "command_prefixes": (service.policy.get("messaging_agent_command") or {}).get("prefixes") or [],
        "agents": sorted(
            agent
            for agent, item in catalog.items()
            if isinstance(item, dict) and "telegram" in (item.get("messaging_apps") or [])
        ),
        "model_ids": {
            agent: CHANNEL_AGENT_MODEL_IDS[agent]
            for agent, item in catalog.items()
            if agent in CHANNEL_AGENT_MODEL_IDS and isinstance(item, dict) and "telegram" in (item.get("messaging_apps") or [])
        },
    }


def _missing_configuration(checks: dict[str, bool]) -> list[str]:
    missing: list[str] = []
    if not checks["telegram_bot_token_configured"]:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not checks["allowlist_configured"]:
        missing.append("TELEGRAM_ALLOWED_USER_IDS")
    if not checks["identity_map_configured"]:
        missing.append("TELEGRAM_IDENTITY_MAP")
    elif not checks["allowlist_identity_map_complete"]:
        missing.append("TELEGRAM_IDENTITY_MAP:missing_allowlist_entries")
    if not checks["open_webui_api_key_configured"]:
        missing.append("OPEN_WEBUI_API_KEY")
    return missing


def _profile_readiness() -> list[dict[str, object]]:
    results = []
    for profile in _bot_profiles():
        allowlist_complete = bool(profile.allowed_user_ids) and profile.allowed_user_ids <= set(profile.identity_map)
        results.append(
            {
                "name": profile.name,
                "bot_token_configured": bool(profile.token.strip()),
                "allowlist_configured": bool(profile.allowed_user_ids),
                "identity_map_configured": bool(profile.identity_map),
                "allowlist_identity_map_complete": allowlist_complete,
                "forced_agent": profile.forced_agent,
                "configured": profile.configured and allowlist_complete,
                "secrets_included": False,
            }
        )
    return results


def _next_actions(missing: list[str], *, ready: bool) -> list[str]:
    if ready:
        return ["Run without --dry-run, preferably with --once first, and verify the generated round-trip report."]
    action_map = {
        "TELEGRAM_BOT_TOKEN": "Create or choose the Telegram bot and set TELEGRAM_BOT_TOKEN outside source control.",
        "TELEGRAM_ALLOWED_USER_IDS": "Set TELEGRAM_ALLOWED_USER_IDS with reviewed family sender IDs; keep an empty allowlist as deny-all.",
        "TELEGRAM_IDENTITY_MAP": "Map every allowed Telegram sender to an approved Freyja identity in TELEGRAM_IDENTITY_MAP.",
        "TELEGRAM_IDENTITY_MAP:missing_allowlist_entries": "Map every allowed Telegram sender to an approved Freyja identity in TELEGRAM_IDENTITY_MAP.",
        "OPEN_WEBUI_API_KEY": "Set OPEN_WEBUI_API_KEY or OPEN_WEBUI_API_KEY_FILE outside source control.",
    }
    actions: list[str] = []
    for key, action in action_map.items():
        if key in missing and action not in actions:
            actions.append(action)
    actions.append("Rerun scripts/run-freyja-channels-telegram-pilot.py --dry-run and require ready=true before live polling.")
    return actions


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
    profile_readiness = _profile_readiness()
    profile_mode_ready = bool(profile_readiness) and any(item["configured"] for item in profile_readiness) and open_webui.configured
    ready = all(checks.values()) or profile_mode_ready
    missing = _missing_configuration(checks)
    if profile_mode_ready:
        missing = []
    return {
        "report_type": "freyja-channels-telegram-pilot",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "mode": "dry-run" if args.dry_run else "run",
        "secrets_included": False,
        "private_content_included": False,
        "ready": ready,
        "checks": checks,
        "messaging_agents": _messaging_agents(),
        "bot_profiles": profile_readiness,
        "missing_configuration": missing,
        "next_actions": _next_actions(missing, ready=ready),
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
            response = service.handle(transport.enrich_attachments(update.message))
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


def _force_agent(message: ChannelMessage, agent: str) -> ChannelMessage:
    from dataclasses import replace

    return replace(message, requested_agent=agent) if agent else message


def run_once_forced_agent(
    *,
    service: FreyjaChannels,
    transport: TelegramLongPollingTransport,
    offset_file: Path,
    forced_agent: str,
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
            message = _force_agent(transport.enrich_attachments(update.message), forced_agent)
            response = service.handle(message)
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
    profiles = _active_bot_profiles()
    totals = {"updates": 0, "handled": 0, "denied_or_client_failed": 0, "failed": 0}
    iterations = 0
    while True:
        for profile in profiles:
            if not _profile_runtime_configured(profile):
                continue
            offset_file = args.offset_file or args.state_dir / f"telegram-{profile.name.lower()}.offset"
            service = FreyjaChannels(
                allowlists={"telegram": profile.allowed_user_ids},
                identity_maps={"telegram": profile.identity_map},
                store=FileChannelStore(args.state_dir / profile.name.lower()),
                client=OpenWebUIChatClient(),
            )
            transport = TelegramLongPollingTransport(TelegramPilotConfig(bot_token=profile.token))
            result = run_once_forced_agent(
                service=service,
                transport=transport,
                offset_file=offset_file,
                forced_agent=profile.forced_agent,
            )
            for key, value in result.items():
                totals[key] += value
        iterations += 1
        if args.until_handled and totals["handled"] > 0:
            break
        if args.once or (args.max_iterations and iterations >= args.max_iterations):
            break
        time.sleep(max(args.poll_interval, 0.1))
    return {
        "report_type": "freyja-channels-telegram-pilot",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "mode": "run",
        "secrets_included": False,
        "private_content_included": False,
        "ready": totals["handled"] > 0 and totals["failed"] == 0,
        "live_round_trip_complete": totals["handled"] > 0 and totals["failed"] == 0,
        "iterations": iterations,
        "totals": totals,
        "next_actions": []
        if totals["handled"] > 0 and totals["failed"] == 0
        else ["Send a message from an allowed Telegram sender and rerun the live Telegram pilot until handled > 0."],
    }


def _failure_report(args: argparse.Namespace, exc: Exception) -> dict[str, Any]:
    cause = exc.__cause__
    http_status = getattr(cause, "code", None)
    reason = "telegram_poll_conflict" if http_status == 409 else "telegram_live_run_failed"
    return {
        "report_type": "freyja-channels-telegram-pilot",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "mode": "run",
        "secrets_included": False,
        "private_content_included": False,
        "ready": False,
        "failure": {
            "reason": reason,
            "exception_type": type(exc).__name__,
            "http_status": http_status,
        },
        "totals": {"updates": 0, "handled": 0, "denied_or_client_failed": 0, "failed": 1},
        "next_actions": [
            "Stop any other Telegram getUpdates poller or clear the bot webhook, then rerun the live Telegram pilot.",
            "Send a message from an allowed Telegram sender and archive a report with handled > 0.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = readiness(args)
    if report["ready"] and not args.dry_run:
        try:
            report = run_loop(args)
        except ChannelTransportError as exc:
            report = _failure_report(args, exc)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report.get("ready") or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
