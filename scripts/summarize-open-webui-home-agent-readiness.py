#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
REPORTS = REPO_ROOT / "certification" / "reports"
DEFAULT_OUTPUT_JSON = REPORTS / "open-webui-home-agent-readiness-summary.json"
DEFAULT_OUTPUT_MD = REPORTS / "open-webui-home-agent-readiness-summary.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize Freyja Open WebUI home-agent activation readiness.")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    return parser


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("secrets_included") is not False:
        raise ValueError(f"report is not marked secret-free: {path}")
    return data


def _gate(
    gate_id: str,
    label: str,
    ready: bool,
    evidence: str,
    next_action: str | None = None,
    next_actions: list[str] | None = None,
    command: str | None = None,
    evidence_generated_at_unix: int | None = None,
    evidence_git_head: str | None = None,
) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "label": label,
        "ready": bool(ready),
        "evidence": evidence,
        "next_action": next_action,
        "next_actions": next_actions or [],
        "command": command,
        "evidence_generated_at_unix": evidence_generated_at_unix,
        "evidence_git_head": evidence_git_head,
    }


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _channel_next_action(channel_report: dict[str, Any], *, fallback: str) -> str:
    missing = channel_report.get("missing_configuration") or []
    if missing:
        return "Configure: " + ", ".join(str(item) for item in missing) + "."
    return fallback


def _channel_next_actions(channel: str, channel_report: dict[str, Any]) -> list[str]:
    if (
        channel_report.get("ready") is True
        or channel_report.get("ready_for_live_round_trip") is True
        or channel_report.get("status") == "complete"
    ):
        return []
    configured = channel_report.get("next_actions")
    if isinstance(configured, list) and configured:
        return [_canonical_action(str(action)) for action in configured]
    missing = channel_report.get("missing_configuration") or []
    if not missing:
        return []
    if channel == "telegram":
        action_map = {
            "TELEGRAM_BOT_TOKEN": "Create or choose the Telegram bot and set TELEGRAM_BOT_TOKEN outside source control.",
            "TELEGRAM_ALLOWED_USER_IDS": "Set TELEGRAM_ALLOWED_USER_IDS with reviewed family sender IDs; keep an empty allowlist as deny-all.",
            "TELEGRAM_IDENTITY_MAP": "Map every allowed Telegram sender to an approved Freyja identity in TELEGRAM_IDENTITY_MAP.",
            "TELEGRAM_IDENTITY_MAP:missing_allowlist_entries": "Map every allowed Telegram sender to an approved Freyja identity in TELEGRAM_IDENTITY_MAP.",
            "OPEN_WEBUI_API_KEY": "Set OPEN_WEBUI_API_KEY or OPEN_WEBUI_API_KEY_FILE outside source control.",
        }
        final_action = "Run scripts/run-freyja-channels-telegram-pilot.py --dry-run before enabling the long-polling pilot."
    else:
        action_map = {
            "SIGNAL_REST_API_URL": "Set SIGNAL_REST_API_URL for the existing signal-cli-rest-api endpoint.",
            "SIGNAL_ACCOUNT_NUMBER": "Set SIGNAL_ACCOUNT_NUMBER for the registered dedicated Signal account.",
            "SIGNAL_ALLOWED_SENDERS": "Set SIGNAL_ALLOWED_SENDERS with reviewed E.164 family senders; keep an empty allowlist as deny-all.",
            "SIGNAL_IDENTITY_MAP": "Map every allowed Signal sender to an approved Freyja identity in SIGNAL_IDENTITY_MAP.",
            "SIGNAL_IDENTITY_MAP:missing_allowlist_entries": "Map every allowed Signal sender to an approved Freyja identity in SIGNAL_IDENTITY_MAP.",
            "OPEN_WEBUI_API_KEY": "Set OPEN_WEBUI_API_KEY or OPEN_WEBUI_API_KEY_FILE outside source control.",
        }
        final_action = "Run scripts/run-freyja-channels-signal-pilot.py --dry-run after signal-cli-rest-api registration is healthy."
    actions = []
    for key, action in action_map.items():
        if key in missing and action not in actions:
            actions.append(action)
    actions.append(final_action)
    return actions


def _chat_smoke_next_actions(chat_smoke: dict[str, Any]) -> list[str]:
    configured = chat_smoke.get("next_actions")
    if isinstance(configured, list) and configured:
        return [str(action) for action in configured]
    if chat_smoke.get("status") == "complete":
        return []
    if "OPEN_WEBUI_API_KEY" in (chat_smoke.get("missing_configuration") or []) or chat_smoke.get("reason") == "OPEN_WEBUI_API_KEY not supplied":
        return [
            "Use the existing Atlas Open WebUI admin account and generate an admin or service-account API key.",
            "Set OPEN_WEBUI_API_KEY outside source control.",
            "Rerun scripts/smoke-open-webui-home-agent-chats.py and require status=complete for all five agents.",
        ]
    return ["Resolve the reported chat-smoke readiness issue and rerun the authenticated five-agent chat smoke."]


def _pilot_live_round_trip_ok(report: dict[str, Any], handled_key: str = "handled") -> bool:
    if report.get("mode") != "run":
        return False
    totals = report.get("totals") if isinstance(report.get("totals"), dict) else {}
    return int(totals.get(handled_key) or 0) > 0 and int(totals.get("failed") or 0) == 0


def _pilot_next_actions(channel: str, pilot: dict[str, Any], readiness: dict[str, Any]) -> list[str]:
    if _pilot_live_round_trip_ok(pilot):
        return []
    if isinstance(pilot.get("next_actions"), list) and pilot.get("next_actions") and pilot.get("mode") == "run":
        return _dedupe(
            [_canonical_action(str(action)) for action in pilot["next_actions"]]
            + _channel_next_actions(channel, readiness)
        )
    if pilot.get("ready") is True:
        return [f"Run the {channel} live round-trip pilot and archive a report with handled > 0."]
    return _channel_next_actions(channel, readiness)


def _canonical_action(value: str) -> str:
    if value in {
        "Set OPEN_WEBUI_API_KEY from an authenticated Open WebUI admin or service account.",
        "Set OPEN_WEBUI_API_KEY outside source control.",
    }:
        return "Set OPEN_WEBUI_API_KEY or OPEN_WEBUI_API_KEY_FILE outside source control."
    return value


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        action = _canonical_action(value)
        if action in seen:
            continue
        seen.add(action)
        deduped.append(action)
    return deduped


def _required_next_actions(gates: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    for gate in gates:
        if gate.get("ready") is True:
            continue
        if gate.get("gate_id") == "telegram_pilot":
            actions.extend(
                str(action)
                for action in gate.get("next_actions") or []
                if "Telegram getUpdates poller" in str(action)
            )
        if gate.get("next_action"):
            actions.append(str(gate["next_action"]))
        actions.extend(str(action) for action in gate.get("next_actions") or [])
    return _dedupe(actions)


def build_summary() -> dict[str, Any]:
    activation = _load(REPORTS / "open-webui-home-agent-post-auth-activation.json")
    db_verification = _load(REPORTS / "open-webui-home-agent-db-verification.json")
    chat_smoke = _load(REPORTS / "open-webui-home-agent-chat-smoke.json")
    telegram = _load(REPORTS / "freyja-channels-telegram-pilot.json")
    signal = _load(REPORTS / "freyja-channels-signal-pilot.json")
    deliverable = _load(REPORTS / "open-webui-home-agent-deliverable.json")
    completion = _load(REPORTS / "open-webui-home-agent-completion-audit.json")
    inventory = _load(REPORTS / "open-webui-home-agent-platform-inventory.json")
    open_webui_next_action = inventory.get("open_webui_next_action_hint") or deliverable.get("exact_next_action")
    public_config = inventory.get("open_webui_public_config") if isinstance(inventory.get("open_webui_public_config"), dict) else {}
    atlas_onboarding_complete = public_config.get("reachable") is True and public_config.get("onboarding") is False
    activation_next_actions = activation.get("next_actions") if isinstance(activation.get("next_actions"), list) else []
    db_activation_ready = db_verification.get("ok") is True and chat_smoke.get("status") == "complete"
    if db_activation_ready:
        activation_next_actions = []
        open_webui_next_action = None
    elif atlas_onboarding_complete:
        activation_next_actions = [
            "Generate an Atlas Open WebUI admin or service-account API key.",
            "Set OPEN_WEBUI_API_KEY outside source control.",
            "Rerun scripts/activate-open-webui-home-agent-post-auth.py against the authenticated Atlas Open WebUI context.",
        ]
    channels = _load(REPORTS / "freyja-channels-readiness.json")
    telegram_readiness = channels.get("telegram") if isinstance(channels.get("telegram"), dict) else {}
    signal_readiness = channels.get("signal") if isinstance(channels.get("signal"), dict) else {}

    telegram_checks = telegram.get("checks") or {}
    signal_checks = signal.get("checks") or {}
    telegram_live_ok = _pilot_live_round_trip_ok(telegram)
    signal_live_ok = _pilot_live_round_trip_ok(signal)
    gates = [
        _gate(
            "post_auth_activation",
            "Open WebUI resource/access activation",
            activation.get("ready") is True or db_activation_ready,
            "certification/reports/open-webui-home-agent-db-verification.json",
            None if activation.get("ready") or db_activation_ready else open_webui_next_action,
            activation_next_actions,
            "scripts/activate-open-webui-home-agent-post-auth.py --resources-json certification/reports/open-webui-home-resources-export.json",
            db_verification.get("generated_at_unix") if db_activation_ready else activation.get("generated_at_unix") or activation.get("timestamp_unix"),
            db_verification.get("git_head") if db_activation_ready else activation.get("git_head"),
        ),
        _gate(
            "authenticated_chat_smoke",
            "Five-agent authenticated Open WebUI chat smoke",
            chat_smoke.get("status") == "complete",
            "certification/reports/open-webui-home-agent-chat-smoke.json",
            None if chat_smoke.get("status") == "complete" else "Set OPEN_WEBUI_API_KEY and run the five-agent chat smoke.",
            _chat_smoke_next_actions(chat_smoke),
            "OPEN_WEBUI_API_KEY=<redacted> scripts/smoke-open-webui-home-agent-chats.py --output certification/reports/open-webui-home-agent-chat-smoke.json",
            chat_smoke.get("generated_at_unix") or chat_smoke.get("timestamp_unix"),
            chat_smoke.get("git_head"),
        ),
        _gate(
            "telegram_pilot",
            "Telegram Joe pilot round trip",
            telegram_live_ok,
            "certification/reports/freyja-channels-telegram-pilot.json",
            None
            if telegram_live_ok
            else (
                str(telegram["next_actions"][0])
                if telegram.get("mode") == "run" and isinstance(telegram.get("next_actions"), list) and telegram["next_actions"]
                else
                "Run the Telegram live round-trip pilot and require handled > 0."
                if telegram.get("ready") is True
                else _channel_next_action(
                    telegram_readiness,
                    fallback="Run the Telegram live round-trip pilot and require handled > 0.",
                )
            ),
            _pilot_next_actions("telegram", telegram, telegram_readiness),
            "scripts/run-freyja-channels-telegram-pilot.py --dry-run --output certification/reports/freyja-channels-telegram-pilot.json",
            telegram.get("generated_at_unix") or telegram.get("timestamp_unix"),
            telegram.get("git_head"),
        ),
        _gate(
            "signal_pilot",
            "Signal round trip",
            signal_live_ok,
            "certification/reports/freyja-channels-signal-pilot.json",
            None
            if signal_live_ok
            else (
                "Run the Signal live round-trip pilot and require handled > 0."
                if signal.get("mode") == "run"
                else
                "Run the Signal live round-trip pilot and require handled > 0."
                if signal.get("ready") is True
                else _channel_next_action(
                    signal_readiness,
                    fallback="Run the Signal live round-trip pilot and require handled > 0.",
                )
            ),
            _pilot_next_actions("signal", signal, signal_readiness),
            "scripts/run-freyja-channels-signal-pilot.py --dry-run --output certification/reports/freyja-channels-signal-pilot.json",
            signal.get("generated_at_unix") or signal.get("timestamp_unix"),
            signal.get("git_head"),
        ),
    ]
    all_ready = all(gate["ready"] for gate in gates)
    required_next_actions = _required_next_actions(gates)
    if chat_smoke.get("status") == "complete":
        required_next_actions = [
            action for action in required_next_actions if "OPEN_WEBUI_API_KEY" not in action
        ]
    exact_next_action = None if all_ready else (open_webui_next_action or (required_next_actions[0] if required_next_actions else None))
    return {
        "report_type": "open-webui-home-agent-readiness-summary",
        "secrets_included": False,
        "private_content_included": False,
        "generated_at_unix": int(time.time()),
        "status": "ready_for_live_activation" if all_ready else "pending_external_auth_or_credentials",
        "all_ready": all_ready,
        "git_head": _git_head() or deliverable.get("git_head"),
        "completion_status_counts": completion.get("status_counts") or {},
        "gates": gates,
        "telegram_checks": telegram_checks,
        "signal_checks": signal_checks,
        "exact_next_action": exact_next_action,
        "required_next_actions": required_next_actions,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Open WebUI Home-Agent Readiness Summary",
        "",
        f"Status: `{summary['status']}`",
        "",
        "## Gates",
        "",
    ]
    for gate in summary["gates"]:
        state = "ready" if gate["ready"] else "pending"
        lines.append(f"- `{gate['gate_id']}`: {state} - {gate['label']}")
        if gate.get("next_action"):
            lines.append(f"  Next: {gate['next_action']}")
        for action in gate.get("next_actions") or []:
            lines.append(f"  Action: {action}")
        if gate.get("command"):
            lines.append(f"  Command: `{gate['command']}`")
    lines += ["", "## Exact Next Action", "", str(summary.get("exact_next_action") or ""), ""]
    lines += ["", "## Required Next Actions", ""]
    for action in summary.get("required_next_actions") or []:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = build_summary()
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.output_md.write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["all_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
