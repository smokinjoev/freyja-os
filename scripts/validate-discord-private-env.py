#!/usr/bin/env python3
"""Validate private Discord connector env readiness without printing secrets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from connectors.discord.config import APPROVED_AGENT_IDS, DiscordSettings, parse_user_agent_bindings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", action="append", type=Path, default=[])
    parser.add_argument("--require-all-agents", action="store_true")
    args = parser.parse_args()

    values: dict[str, str] = {}
    for path in args.env_file:
        values.update(_read_env(path))

    result = validate(values, require_all_agents=args.require_all_agents)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


def validate(env: dict[str, str], *, require_all_agents: bool = False) -> dict[str, object]:
    failures: list[str] = []
    raw_map = env.get("DISCORD_USER_AGENT_MAP", "")
    try:
        bindings = parse_user_agent_bindings(raw_map)
    except ValueError as exc:
        bindings = ()
        failures.append(str(exc))

    mapped_agents = {binding.agent_id for binding in bindings}
    missing_agents = sorted(APPROVED_AGENT_IDS - mapped_agents)
    extra_agents = sorted(mapped_agents - APPROVED_AGENT_IDS)
    if require_all_agents and missing_agents:
        failures.append("DISCORD_USER_AGENT_MAP is missing approved agents.")
    if extra_agents:
        failures.append("DISCORD_USER_AGENT_MAP contains unapproved agents.")

    settings = DiscordSettings(
        enabled=_truthy(env.get("DISCORD_ENABLED", "")),
        bot_token=env.get("DISCORD_BOT_TOKEN", "").strip(),
        director_url=env.get("FREYJA_DIRECTOR_URL", "http://127.0.0.1:8000").strip(),
        connector_token=env.get("FREYJA_CONNECTOR_TOKEN", "").strip(),
        user_agent_bindings=bindings,
    )
    if not settings.bot_token:
        failures.append("DISCORD_BOT_TOKEN is missing.")
    if not settings.connector_token:
        failures.append("FREYJA_CONNECTOR_TOKEN is missing.")

    return {
        "ok": not failures,
        "discord_enabled": settings.enabled,
        "ready_for_live_transport": settings.ready_for_live_transport,
        "binding_count": len(bindings),
        "mapped_agents": sorted(mapped_agents),
        "missing_agents": missing_agents,
        "failures": failures,
    }


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
