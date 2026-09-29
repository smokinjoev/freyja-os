#!/usr/bin/env python3
"""Interactively provision the five family Discord agents without printing secrets."""
from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import stat
import tempfile
from pathlib import Path

AGENTS = (
    ("FREYJA", "freyja", "Freyja"),
    ("CLOYD", "cloyd-gibbler", "Cloyd"),
    ("BENEDICT", "benedict", "Benedict"),
    ("AGENT_44", "agent-47", "Agent 44"),
    ("SMITH", "smith", "Agent Smith"),
)


def write_private(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(contents)
        os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(temporary, path)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_core_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family-env", type=Path, default=Path.home() / ".config/freyja-os/family-discord.env")
    parser.add_argument("--core-env", type=Path, default=Path.home() / ".config/freyja-os/core-mcp.env")
    args = parser.parse_args()

    family_lines = [
        "# Generated locally. Contains Discord and Core bearer credentials.",
        "# Mode 600; never commit or paste its contents into chat.",
    ]
    mapping: dict[str, str]
    core_values = load_core_env(args.core_env)
    raw_mapping = core_values.get("FREYJA_MCP_AGENT_TOKENS_JSON", "{}")
    try:
        mapping = json.loads(raw_mapping)
    except json.JSONDecodeError as error:
        raise SystemExit("Existing Core token mapping is invalid; no files changed.") from error
    if not isinstance(mapping, dict):
        raise SystemExit("Existing Core token mapping is invalid; no files changed.")

    for prefix, policy_id, display_name in AGENTS:
        print(f"{display_name}:")
        bot_token = getpass.getpass("  Discord bot token: ").strip()
        channel_id = input("  Dedicated Discord channel ID: ").strip()
        if not bot_token:
            raise SystemExit("Empty bot token; no files changed.")
        if not channel_id.isdecimal():
            raise SystemExit("Channel ID must contain only digits; no files changed.")
        core_token = secrets.token_urlsafe(32)
        family_lines.extend(
            (
                f"FREYJA6_{prefix}_DISCORD_BOT_TOKEN={bot_token}",
                f"FREYJA6_{prefix}_DISCORD_CHANNEL_ID={channel_id}",
                f"FREYJA6_{prefix}_CORE_MCP_TOKEN={core_token}",
                "",
            )
        )
        mapping[core_token] = policy_id

    updated_core = [
        line for line in args.core_env.read_text(encoding="utf-8").splitlines()
        if not line.startswith("FREYJA_MCP_AGENT_TOKENS_JSON=")
    ] if args.core_env.exists() else []
    updated_core.append("FREYJA_MCP_AGENT_TOKENS_JSON=" + json.dumps(mapping, separators=(",", ":"), sort_keys=True))
    write_private(args.family_env, "\n".join(family_lines) + "\n")
    write_private(args.core_env, "\n".join(updated_core) + "\n")
    print("Credentials saved with mode 600. No token values were printed.")
    print("Next: restart com.freyja-os.core-mcp, then start the family Compose overlay.")


if __name__ == "__main__":
    main()
