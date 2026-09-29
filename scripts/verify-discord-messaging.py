#!/usr/bin/env python3
"""Deterministically verify the current Discord messaging invariants."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from connectors.discord.config import APPROVED_AGENT_IDS, DiscordSettings, parse_user_agent_bindings  # noqa: E402
from connectors.discord.gateway import DiscordGateway  # noqa: E402


EXPECTED_AGENTS = {
    "freyja": "Freyja",
    "cloyd-gibbler": "Cloyd Gibbler",
    "benedict": "Benedict",
    "agent-47": "Agent 44",
    "smith": "Agent Smith",
}


def main() -> int:
    failures: list[str] = []
    if APPROVED_AGENT_IDS != set(EXPECTED_AGENTS):
        failures.append("Approved Discord agent ids must match the configured five-agent roster.")

    sample = ",".join(f"{10_000_000_000_000_000 + index}={agent_id}" for index, agent_id in enumerate(EXPECTED_AGENTS))
    try:
        bindings = parse_user_agent_bindings(sample)
    except ValueError as exc:
        failures.append(f"Valid Discord user-agent map was rejected: {exc}")
        bindings = ()
    if len(bindings) != len(EXPECTED_AGENTS):
        failures.append("Verifier sample must map each approved Discord user exactly once.")

    rejection_cases = {
        "duplicate user": "100=freyja,100=smith",
        "unknown agent": "101=jennacide",
        "non numeric user": "joe=cloyd-gibbler",
        "missing equals": "102",
    }
    for label, raw in rejection_cases.items():
        try:
            parse_user_agent_bindings(raw)
        except ValueError:
            pass
        else:
            failures.append(f"Discord user-agent map must reject {label}.")

    try:
        shared_default = parse_user_agent_bindings("100=freyja,101=freyja")
    except ValueError as exc:
        failures.append(f"Multiple Discord users must be allowed to default to Freyja: {exc}")
        shared_default = ()
    if len(shared_default) != 2:
        failures.append("Verifier shared-Freyja sample must allow two approved users.")

    disabled = DiscordSettings.from_env()
    if disabled.enabled:
        failures.append("DISCORD_ENABLED must remain false during deterministic validation.")

    settings = DiscordSettings(
        enabled=False,
        bot_token="",
        director_url="http://127.0.0.1:8000",
        connector_token="",
        user_agent_bindings=bindings,
    )
    gateway = DiscordGateway(settings)
    startup_failures = gateway.validate_startup()
    if "Discord transport is disabled." not in startup_failures:
        failures.append("Gateway startup validation must keep disabled Discord from running live.")
    if settings.ready_for_live_transport:
        failures.append("Discord settings without secrets must not be ready for live transport.")

    failures.extend(_tracked_secret_failures(os.environ))

    result = {
        "ok": not failures,
        "discord_enabled": disabled.enabled,
        "approved_agents": EXPECTED_AGENTS,
        "live_transport_ready": disabled.ready_for_live_transport,
        "failures": failures,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if failures else 0


def _tracked_secret_failures(env: os._Environ[str] | dict[str, str]) -> list[str]:
    tracked_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in [
            ROOT / "docs/discord/family-discord-runbook.md",
            ROOT / "connectors/discord/config.py",
            ROOT / "connectors/discord/gateway.py",
        ]
    )
    failures: list[str] = []
    secret_markers = {
        key: value
        for key, value in env.items()
        if value and (key == "FREYJA_CONNECTOR_TOKEN" or ("DISCORD" in key and "TOKEN" in key))
    }
    for key, marker in secret_markers.items():
        if marker in tracked_text:
            failures.append(f"A live {key} value appears in tracked Discord files.")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
