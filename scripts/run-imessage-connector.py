#!/usr/bin/env python3
"""Run the native macOS iMessage connector loop."""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = str(_PROJECT_ROOT / "src")
_ROOT_DIR = str(_PROJECT_ROOT)
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(1, _ROOT_DIR)

from connectors.imessage.config import IMessageSettings  # noqa: E402
from connectors.imessage.gateway import IMessageGateway  # noqa: E402
from connectors.imessage.transport import (  # noqa: E402
    IMessageTransport,
    IMessageTransportError,
)

logger = logging.getLogger("imessage_connector_runner")


class SeenMessageStore:
    """Persistent bounded store of iMessage GUIDs already handled by the connector."""

    def __init__(self, path: Path, *, limit: int) -> None:
        self._path = path
        self._limit = max(1, limit)
        self._ordered_ids: list[str] = []
        self._id_set: set[str] = set()

    @property
    def message_ids(self) -> set[str]:
        return set(self._id_set)

    def load(self) -> None:
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, json.JSONDecodeError):
            logger.exception("Unable to load iMessage seen-state file")
            return

        raw_ids = payload.get("message_ids") if isinstance(payload, dict) else payload
        if not isinstance(raw_ids, list):
            logger.warning("Ignoring invalid iMessage seen-state file")
            return

        self._ordered_ids = []
        self._id_set = set()
        for raw_id in raw_ids:
            if isinstance(raw_id, str) and raw_id:
                self.add(raw_id, persist=False)

        logger.info("Loaded iMessage seen-state with %s message ids", len(self._id_set))

    def add_many(self, message_ids: set[str] | list[str]) -> None:
        changed = False
        for message_id in message_ids:
            changed = self.add(message_id, persist=False) or changed
        if changed:
            self.persist()

    def add(self, message_id: str, *, persist: bool = True) -> bool:
        if message_id in self._id_set:
            return False

        self._ordered_ids.append(message_id)
        self._id_set.add(message_id)
        self._prune()
        if persist:
            self.persist()
        return True

    def persist(self) -> None:
        payload = {"message_ids": self._ordered_ids}
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
            temporary_path.write_text(
                json.dumps(payload, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary_path.replace(self._path)
        except OSError:
            logger.exception("Unable to persist iMessage seen-state file")

    def _prune(self) -> None:
        if len(self._ordered_ids) <= self._limit:
            return
        self._ordered_ids = self._ordered_ids[-self._limit :]
        self._id_set = set(self._ordered_ids)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _runtime_ready(settings: IMessageSettings, gateway: IMessageGateway) -> bool:
    if not gateway.enabled:
        logger.warning("iMessage gateway is disabled; connector is idle until enabled")
        return False

    if not Path(settings.imessage_database_path).exists():
        logger.error("Messages database does not exist at configured path")
        return False

    if not settings.allowed_sender_set:
        logger.error("iMessage sender allowlist is empty")
        return False

    return True


async def _handle_message(
    gateway: IMessageGateway,
    transport: IMessageTransport,
    message,
) -> None:
    reply = await gateway.handle(message)
    if reply is not None:
        try:
            await transport.send(reply)
        except IMessageTransportError:
            logger.exception("iMessage reply send failed")


async def _seed_seen_messages(
    transport: IMessageTransport,
    seen_store: SeenMessageStore,
) -> None:
    try:
        messages = await transport.recent_messages()
    except IMessageTransportError:
        logger.exception("Unable to seed iMessage polling state")
        return

    message_ids = {message.message_id for message in messages}
    if message_ids:
        logger.info("Seeded iMessage polling state with %s recent messages", len(message_ids))
        seen_store.add_many(message_ids)


async def _poll_recent_messages(
    shutdown_event: asyncio.Event,
    gateway: IMessageGateway,
    transport: IMessageTransport,
    settings: IMessageSettings,
    seen_store: SeenMessageStore,
) -> None:
    while not shutdown_event.is_set():
        try:
            for message in await transport.recent_messages():
                if message.message_id in seen_store.message_ids:
                    continue
                seen_store.add(message.message_id)
                await _handle_message(gateway, transport, message)
        except IMessageTransportError:
            logger.exception("iMessage polling cycle failed")

        try:
            await asyncio.wait_for(
                shutdown_event.wait(),
                timeout=max(1.0, settings.imessage_poll_interval_seconds),
            )
        except asyncio.TimeoutError:
            pass


async def _run_watch_loop(
    shutdown_event: asyncio.Event,
    gateway: IMessageGateway,
    transport: IMessageTransport,
    seen_store: SeenMessageStore,
) -> None:
    try:
        async for message in transport.watch():
            if shutdown_event.is_set():
                break
            if message.message_id in seen_store.message_ids:
                continue
            seen_store.add(message.message_id)
            await _handle_message(gateway, transport, message)
    except IMessageTransportError:
        logger.exception("iMessage watch failed; polling fallback remains active")
        await shutdown_event.wait()
    else:
        if not shutdown_event.is_set():
            logger.warning("iMessage watch ended; polling fallback remains active")
            await shutdown_event.wait()


async def main() -> int:
    _configure_logging()
    connector_settings = IMessageSettings()
    gateway = IMessageGateway()
    transport = IMessageTransport(connector_settings)

    try:
        shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def request_shutdown() -> None:
            if not shutdown_event.is_set():
                logger.info("iMessage connector shutdown requested")
                shutdown_event.set()

        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, request_shutdown)

        if not _runtime_ready(connector_settings, gateway):
            await shutdown_event.wait()
            return 0

        logger.info("iMessage connector started")
        seen_store = SeenMessageStore(
            Path(connector_settings.imessage_seen_state_path),
            limit=connector_settings.imessage_seen_state_limit,
        )
        seen_store.load()
        await _seed_seen_messages(transport, seen_store)
        poll_task = asyncio.create_task(
            _poll_recent_messages(
                shutdown_event,
                gateway,
                transport,
                connector_settings,
                seen_store,
            )
        )
        if connector_settings.imessage_watch_enabled:
            await _run_watch_loop(
                shutdown_event,
                gateway,
                transport,
                seen_store,
            )
        else:
            logger.info("iMessage watch disabled; polling fallback is active")
            await shutdown_event.wait()

        poll_task.cancel()
        await asyncio.gather(poll_task, return_exceptions=True)

        return 0
    except IMessageTransportError:
        logger.exception("iMessage transport failed")
        return 1
    finally:
        await gateway.close()
        logger.info("iMessage connector stopped")


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
