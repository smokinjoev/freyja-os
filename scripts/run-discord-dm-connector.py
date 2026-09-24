#!/usr/bin/env python3
"""Run the Freyja Discord DM-only connector."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

_PROJECT_DIR = Path(__file__).resolve().parents[1]
_SRC_DIR = str(_PROJECT_DIR / "src")
_ROOT_DIR = str(_PROJECT_DIR)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(1, _ROOT_DIR)

from connectors.discord.config import DiscordSettings  # noqa: E402
from connectors.discord.gateway import DiscordGateway, DiscordInboundMessage  # noqa: E402


logger = logging.getLogger("discord_dm_connector")

API_BASE = "https://discord.com/api/v10"
DISCORD_GATEWAY_VERSION = 10
INTENT_DIRECT_MESSAGES = 1 << 12
INTENT_MESSAGE_CONTENT = 1 << 15


def _configure_logging() -> None:
    log_dir = _PROJECT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    handler = logging.FileHandler(log_dir / "discord-dm-connector.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(stderr_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)


async def main() -> int:
    _configure_logging()
    _load_dotenv(_PROJECT_DIR / ".env")
    settings = DiscordSettings.from_env()
    gateway = DiscordGateway(settings)
    failures = gateway.validate_startup()
    if failures:
        logger.warning("Discord connector not started: %s", "; ".join(failures))
        return 1

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, shutdown_event.set)

    async with httpx.AsyncClient(timeout=30) as client:
        runner = DiscordDmRunner(settings=settings, gateway=gateway, client=client)
        await runner.run(shutdown_event)
    return 0


class DiscordDmRunner:
    def __init__(self, *, settings: DiscordSettings, gateway: DiscordGateway, client: httpx.AsyncClient) -> None:
        self._settings = settings
        self._gateway = gateway
        self._client = client
        self._sequence: int | None = None

    async def run(self, shutdown_event: asyncio.Event) -> None:
        backoff = 1.0
        while not shutdown_event.is_set():
            try:
                await self._run_once(shutdown_event)
                if not shutdown_event.is_set():
                    logger.warning("Discord Gateway session ended; reconnecting.")
            except Exception:
                logger.exception("Discord Gateway session failed; reconnecting.")
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 60.0)

    async def _run_once(self, shutdown_event: asyncio.Event) -> None:
        import websockets

        gateway_url = await self._gateway_url()
        url = f"{gateway_url}?v={DISCORD_GATEWAY_VERSION}&encoding=json"
        async with websockets.connect(url, max_size=2**20) as websocket:
            hello = json.loads(await websocket.recv())
            heartbeat_interval = float(hello["d"]["heartbeat_interval"]) / 1000.0
            heartbeat_task = asyncio.create_task(self._heartbeat(websocket, heartbeat_interval, shutdown_event))
            try:
                await websocket.send(json.dumps(_identify_payload(self._settings.bot_token)))
                logger.info("Discord DM connector identify sent.")
                async for raw_event in websocket:
                    if shutdown_event.is_set():
                        break
                    await self._handle_gateway_event(json.loads(raw_event))
            finally:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)

    async def _gateway_url(self) -> str:
        response = await self._client.get(
            f"{API_BASE}/gateway/bot",
            headers=_bot_headers(self._settings.bot_token),
        )
        response.raise_for_status()
        return str(response.json()["url"])

    async def _heartbeat(self, websocket: Any, interval: float, shutdown_event: asyncio.Event) -> None:
        while not shutdown_event.is_set():
            await asyncio.sleep(interval)
            await websocket.send(json.dumps({"op": 1, "d": self._sequence}))

    async def _handle_gateway_event(self, event: dict[str, Any]) -> None:
        if isinstance(event.get("s"), int):
            self._sequence = event["s"]
        if event.get("op") == 0 and event.get("t") == "READY":
            user = (event.get("d") or {}).get("user") if isinstance(event.get("d"), dict) else {}
            logger.info("Discord DM connector ready as bot_id=%s username=%s", user.get("id"), user.get("username"))
            return
        if event.get("op") != 0 or event.get("t") != "MESSAGE_CREATE":
            return
        payload = event.get("d") if isinstance(event.get("d"), dict) else {}
        message = _message_from_gateway_payload(payload)
        logger.info(
            "Discord message event received channel_type=%s author_id=%s has_text=%s attachments=%s embeds=%s",
            message.channel_type,
            message.author_id,
            bool(message.content.strip()),
            len(message.attachments),
            len(message.embeds),
        )
        if self._gateway.would_route(message):
            await self._send_seen_feedback(message)
        unsupported_reply = self._gateway.unsupported_message_reply(message)
        if unsupported_reply is not None:
            await self._send_message(
                channel_id=message.channel_id,
                content=unsupported_reply.text,
                message_reference_id=unsupported_reply.message_reference_id,
            )
            logger.info("Discord unsupported message notice sent message_id=%s", message.message_id)
            return
        reply = await self._gateway.handle_message(message)
        if reply is None:
            logger.info("Discord message ignored by gateway author_id=%s channel_type=%s", message.author_id, message.channel_type)
            return
        await self._send_message(
            channel_id=message.channel_id,
            content=reply.text,
            message_reference_id=reply.message_reference_id,
        )
        logger.info("Discord reply sent agent_id=%s trace_id=%s", reply.agent_id, reply.trace_id)

    async def _send_message(self, *, channel_id: str, content: str, message_reference_id: str) -> None:
        response = await self._client.post(
            f"{API_BASE}/channels/{channel_id}/messages",
            headers=_bot_headers(self._settings.bot_token),
            json={
                "content": content,
                "message_reference": {"message_id": message_reference_id},
            },
        )
        response.raise_for_status()

    async def _send_seen_feedback(self, message: DiscordInboundMessage) -> None:
        if not self._settings.seen_reactions_enabled:
            return
        for reaction in self._settings.seen_reactions:
            try:
                response = await self._client.put(
                    f"{API_BASE}/channels/{message.channel_id}/messages/{message.message_id}/reactions/{quote(reaction, safe='')}/@me",
                    headers=_bot_headers(self._settings.bot_token),
                    timeout=5,
                )
                response.raise_for_status()
            except Exception as exc:  # noqa: BLE001 - feedback should never block the actual reply
                logger.warning(
                    "Discord seen reaction failed message_id=%s reaction=%r error=%s",
                    message.message_id,
                    reaction,
                    exc,
                )


def _identify_payload(token: str) -> dict[str, Any]:
    return {
        "op": 2,
        "d": {
            "token": token,
            "intents": INTENT_DIRECT_MESSAGES | INTENT_MESSAGE_CONTENT,
            "properties": {
                "os": sys.platform,
                "browser": "freyja-discord-dm-connector",
                "device": "freyja-discord-dm-connector",
            },
        },
    }


def _message_from_gateway_payload(payload: dict[str, Any]) -> DiscordInboundMessage:
    author = payload.get("author") if isinstance(payload.get("author"), dict) else {}
    channel_type = "dm" if payload.get("guild_id") is None else "guild_text"
    return DiscordInboundMessage(
        message_id=str(payload.get("id") or ""),
        author_id=str(author.get("id") or ""),
        channel_id=str(payload.get("channel_id") or ""),
        channel_type=channel_type,
        content=str(payload.get("content") or ""),
        author_is_bot=bool(author.get("bot")),
        attachments=tuple(payload.get("attachments") or ()),
        embeds=tuple(payload.get("embeds") or ()),
    )


def _bot_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bot {token}",
        "User-Agent": "FreyjaDiscordDmConnector/0.1",
        "Content-Type": "application/json",
    }


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
