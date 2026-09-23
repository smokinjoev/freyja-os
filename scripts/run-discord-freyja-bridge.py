#!/usr/bin/env python3
"""Minimal Discord channel bridge for Freyja Core.

This is intentionally narrow:
- one Discord bot token, read from env or the local Msty Go DB
- one Discord channel
- optional allowlisted Discord author ids
- one local Freyja Core OpenAI-compatible endpoint

It is a fallback while Msty Go's built-in Discord connector is not routing
messages into Activity.
"""

from __future__ import annotations

import argparse
import faulthandler
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_DB = Path.home() / "Library/Application Support/Msty Go/msty-go.db"
DEFAULT_CHANNEL_ID = "1550929424667512936"
DEFAULT_MSTY_CHANNEL_ID = "36f74b07"
DEFAULT_CORE_URL = "http://127.0.0.1:8510/v1/chat/completions"
DEFAULT_STATE = Path("data/discord-freyja-bridge/state.json")
DEFAULT_ALLOWED_AUTHORS = "895679349225820212"


def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> Any:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "user-agent": "FreyjaDiscordBridge/0.1 (+https://local.freyja-os)",
            "content-type": "application/json",
            **(headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} returned HTTP {exc.code}: {detail[:500]}") from exc
    return json.loads(body) if body else {}


def _discord_get(token: str, path: str, *, query: dict[str, str] | None = None) -> Any:
    url = "https://discord.com/api/v10" + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    return _request_json("GET", url, headers={"authorization": f"Bot {token}"})


def _discord_post(token: str, path: str, payload: dict[str, Any]) -> Any:
    return _request_json(
        "POST",
        "https://discord.com/api/v10" + path,
        headers={"authorization": f"Bot {token}"},
        payload=payload,
    )


def _read_token(db_path: Path, channel_row_id: str) -> str:
    env_token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if env_token:
        return env_token
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("select token from channels where id = ?", (channel_row_id,)).fetchone()
    if not row or not str(row[0]).strip():
        raise RuntimeError("Discord bot token not found in env or Msty Go DB")
    return str(row[0]).strip()


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _core_reply(core_url: str, text: str, *, timeout: float) -> str:
    payload = {
        "model": "freyja-core",
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are Freyja answering from the local Discord bridge. "
                    "Be concise. Use Freyja Core tools only when the Core loop chooses them."
                ),
            },
            {"role": "user", "content": text},
        ],
    }
    data = _request_json("POST", core_url, payload=payload, timeout=timeout)
    choices = data.get("choices") if isinstance(data, dict) else None
    if not choices:
        raise RuntimeError("Freyja Core returned no choices")
    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("Freyja Core returned an empty response")
    return content


def _trim_reply(text: str) -> str:
    # Discord hard limit is 2000 chars.
    return text if len(text) <= 1900 else text[:1890].rstrip() + "\n...[trimmed]"


def _initial_last_id(token: str, channel_id: str) -> str | None:
    messages = _discord_get(token, f"/channels/{channel_id}/messages", query={"limit": "1"})
    if isinstance(messages, list) and messages:
        return str(messages[0].get("id") or "")
    return None


def run(args: argparse.Namespace) -> int:
    token = _read_token(Path(args.db), args.msty_channel_id)
    allowed = {item.strip() for item in args.allowed_authors.split(",") if item.strip()}
    state_path = Path(args.state)
    state = _load_state(state_path)
    last_id = str(state.get("last_message_id") or "") or None

    if args.skip_existing and not last_id:
        last_id = _initial_last_id(token, args.channel_id)
        if last_id:
            _save_state(state_path, {"last_message_id": last_id, "updated_at_unix": int(time.time())})
            print(f"Initialized after existing message {last_id}", flush=True)

    print(
        f"Discord Freyja bridge running channel={args.channel_id} allowed={sorted(allowed) or ['<any>']}",
        flush=True,
    )
    while True:
        try:
            query = {"limit": "10"}
            if last_id:
                query["after"] = last_id
            messages = _discord_get(token, f"/channels/{args.channel_id}/messages", query=query)
            if not isinstance(messages, list):
                raise RuntimeError(f"Unexpected Discord messages response: {messages!r}")
            for message in sorted(messages, key=lambda item: int(item.get("id", "0"))):
                message_id = str(message.get("id") or "")
                author = message.get("author") or {}
                author_id = str(author.get("id") or "")
                content = str(message.get("content") or "").strip()
                last_id = message_id or last_id
                _save_state(state_path, {"last_message_id": last_id, "updated_at_unix": int(time.time())})
                if not message_id or author.get("bot") or not content:
                    continue
                if allowed and author_id not in allowed:
                    print(f"Skipping non-allowlisted author {author_id}", flush=True)
                    continue
                print(f"Received {message_id} from {author_id}: {content[:120]!r}", flush=True)
                try:
                    reply = _core_reply(args.core_url, content, timeout=args.core_timeout)
                except Exception as exc:
                    reply = f"Freyja bridge error: {exc}"
                _discord_post(
                    token,
                    f"/channels/{args.channel_id}/messages",
                    {"content": _trim_reply(reply), "message_reference": {"message_id": message_id}},
                )
                print(f"Replied to {message_id}", flush=True)
        except Exception as exc:
            print(f"Polling loop error: {exc}", flush=True)
        time.sleep(args.poll_seconds)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--msty-channel-id", default=DEFAULT_MSTY_CHANNEL_ID)
    parser.add_argument("--channel-id", default=DEFAULT_CHANNEL_ID)
    parser.add_argument("--allowed-authors", default=os.environ.get("DISCORD_ALLOWED_AUTHORS", DEFAULT_ALLOWED_AUTHORS))
    parser.add_argument("--core-url", default=os.environ.get("FREYJA_DISCORD_CORE_URL", DEFAULT_CORE_URL))
    parser.add_argument("--core-timeout", type=float, default=25.0)
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    parser.add_argument("--skip-existing", action="store_true", default=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    faulthandler.enable()
    return run(parse_args(argv or sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
