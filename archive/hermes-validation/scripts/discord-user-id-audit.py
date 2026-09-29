#!/usr/bin/env python3
"""List candidate Discord author ids from a private env file without printing secrets."""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path("deploy/compose/freyja6/.env"))
    parser.add_argument("--token-key", default="FREYJA6_DISCORD_BOT_TOKEN")
    parser.add_argument("--channel-key", default="FREYJA6_DISCORD_CHANNEL_ID")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    values = _read_env(args.env_file)
    token = values.get(args.token_key, "")
    channel_id = values.get(args.channel_key, "")
    if not token or not channel_id:
        print(json.dumps({"ok": False, "error": "missing token or channel id"}, sort_keys=True))
        return 1

    try:
        bot = _discord_get(token, "/users/@me")
        channel = _discord_get(token, f"/channels/{channel_id}")
        messages = _discord_get(token, f"/channels/{channel_id}/messages?limit={max(1, min(args.limit, 100))}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        print(json.dumps({"ok": False, "http_status": exc.code, "detail": detail}, sort_keys=True))
        return 1

    authors: dict[str, dict[str, Any]] = {}
    for message in messages if isinstance(messages, list) else []:
        author = message.get("author") or {}
        author_id = str(author.get("id") or "")
        if not author_id or author.get("bot"):
            continue
        entry = authors.setdefault(
            author_id,
            {
                "username": author.get("username"),
                "global_name": author.get("global_name"),
                "message_count": 0,
            },
        )
        entry["message_count"] += 1

    print(
        json.dumps(
            {
                "ok": True,
                "bot_id": bot.get("id"),
                "bot_username": bot.get("username"),
                "channel_id": channel_id,
                "channel_type": channel.get("type"),
                "candidate_human_authors": authors,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


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


def _discord_get(token: str, path: str) -> Any:
    request = urllib.request.Request(
        "https://discord.com/api/v10" + path,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "FreyjaDiscordUserIdAudit/0.1",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else {}


if __name__ == "__main__":
    raise SystemExit(main())
