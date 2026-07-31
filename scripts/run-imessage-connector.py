#!/usr/bin/env python3
"""Run the native macOS iMessage connector loop."""

from __future__ import annotations

import asyncio
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


async def _poll_recent_messages(
    shutdown_event: asyncio.Event,
    gateway: IMessageGateway,
    transport: IMessageTransport,
    settings: IMessageSettings,
) -> None:
    while not shutdown_event.is_set():
        try:
            for message in await transport.recent_messages():
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
        poll_task = asyncio.create_task(
            _poll_recent_messages(
                shutdown_event,
                gateway,
                transport,
                connector_settings,
            )
        )
        async for message in transport.watch():
            if shutdown_event.is_set():
                break

            await _handle_message(gateway, transport, message)

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
