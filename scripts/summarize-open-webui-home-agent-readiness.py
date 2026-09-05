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
        "command": command,
        "evidence_generated_at_unix": evidence_generated_at_unix,
        "evidence_git_head": evidence_git_head,
    }


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def build_summary() -> dict[str, Any]:
    activation = _load(REPORTS / "open-webui-home-agent-post-auth-activation.json")
    chat_smoke = _load(REPORTS / "open-webui-home-agent-chat-smoke.json")
    telegram = _load(REPORTS / "freyja-channels-telegram-pilot.json")
    signal = _load(REPORTS / "freyja-channels-signal-pilot.json")
    deliverable = _load(REPORTS / "open-webui-home-agent-deliverable.json")
    completion = _load(REPORTS / "open-webui-home-agent-completion-audit.json")
    inventory = _load(REPORTS / "open-webui-home-agent-platform-inventory.json")
    open_webui_next_action = inventory.get("open_webui_next_action_hint") or deliverable.get("exact_next_action")

    telegram_checks = telegram.get("checks") or {}
    signal_checks = signal.get("checks") or {}
    gates = [
        _gate(
            "post_auth_activation",
            "Open WebUI resource/access activation",
            activation.get("ready") is True,
            "certification/reports/open-webui-home-agent-post-auth-activation.json",
            None if activation.get("ready") else open_webui_next_action,
            "scripts/activate-open-webui-home-agent-post-auth.py --resources-json certification/reports/open-webui-home-resources-export.json --owner-user-id <open-webui-owner-user-id>",
            activation.get("generated_at_unix") or activation.get("timestamp_unix"),
            activation.get("git_head"),
        ),
        _gate(
            "authenticated_chat_smoke",
            "Five-agent authenticated Open WebUI chat smoke",
            chat_smoke.get("status") == "complete",
            "certification/reports/open-webui-home-agent-chat-smoke.json",
            None if chat_smoke.get("status") == "complete" else "Set OPEN_WEBUI_API_KEY and run the five-agent chat smoke.",
            "OPEN_WEBUI_API_KEY=<redacted> scripts/smoke-open-webui-home-agent-chats.py --output certification/reports/open-webui-home-agent-chat-smoke.json",
            chat_smoke.get("generated_at_unix") or chat_smoke.get("timestamp_unix"),
            chat_smoke.get("git_head"),
        ),
        _gate(
            "telegram_pilot",
            "Telegram Joe pilot round trip",
            telegram.get("ready") is True,
            "certification/reports/freyja-channels-telegram-pilot.json",
            None
            if telegram.get("ready")
            else "Set TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS, TELEGRAM_IDENTITY_MAP, and OPEN_WEBUI_API_KEY.",
            "scripts/run-freyja-channels-telegram-pilot.py --dry-run --output certification/reports/freyja-channels-telegram-pilot.json",
            telegram.get("generated_at_unix") or telegram.get("timestamp_unix"),
            telegram.get("git_head"),
        ),
        _gate(
            "signal_pilot",
            "Signal round trip",
            signal.get("ready") is True,
            "certification/reports/freyja-channels-signal-pilot.json",
            None
            if signal.get("ready")
            else "Register signal-cli-rest-api and set SIGNAL_ACCOUNT_NUMBER, SIGNAL_ALLOWED_SENDERS, SIGNAL_IDENTITY_MAP, and OPEN_WEBUI_API_KEY.",
            "scripts/run-freyja-channels-signal-pilot.py --dry-run --output certification/reports/freyja-channels-signal-pilot.json",
            signal.get("generated_at_unix") or signal.get("timestamp_unix"),
            signal.get("git_head"),
        ),
    ]
    return {
        "report_type": "open-webui-home-agent-readiness-summary",
        "secrets_included": False,
        "private_content_included": False,
        "generated_at_unix": int(time.time()),
        "status": "ready_for_live_activation" if all(gate["ready"] for gate in gates) else "pending_external_auth_or_credentials",
        "all_ready": all(gate["ready"] for gate in gates),
        "git_head": _git_head() or deliverable.get("git_head"),
        "completion_status_counts": completion.get("status_counts") or {},
        "gates": gates,
        "telegram_checks": telegram_checks,
        "signal_checks": signal_checks,
        "exact_next_action": open_webui_next_action,
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
        if gate.get("command"):
            lines.append(f"  Command: `{gate['command']}`")
    lines += ["", "## Exact Next Action", "", str(summary.get("exact_next_action") or ""), ""]
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
