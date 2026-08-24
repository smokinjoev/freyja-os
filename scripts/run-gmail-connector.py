#!/usr/bin/env python3
"""Run the Gmail connector polling loop."""

from __future__ import annotations

import asyncio
import logging
import os
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

from connectors.gmail.config import GmailSettings  # noqa: E402
from connectors.gmail.gateway import GmailGateway  # noqa: E402
from connectors.gmail.transport import (  # noqa: E402
    GmailImapSmtpTransport,
    GmailTransportError,
)

logger = logging.getLogger("gmail_connector_runner")

_INITIAL_BACKOFF_SECONDS = 1.0


def _configure_logging() -> None:
    log_dir = _PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "gmail-connector.log"
    handler = logging.FileHandler(log_path)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if os.environ.get("XPC_SERVICE_NAME") != "com.freyja-os.gmail-connector":
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(logging.WARNING)
        stderr_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        root.addHandler(stderr_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _wait_or_shutdown(
    shutdown_event: asyncio.Event,
    timeout_seconds: float,
) -> None:
    try:
        await asyncio.wait_for(
            shutdown_event.wait(),
            timeout=max(0.0, timeout_seconds),
        )
    except asyncio.TimeoutError:
        pass


async def main() -> int:
    _configure_logging()
    connector_settings = GmailSettings()
    gateway = GmailGateway()
    transport = GmailImapSmtpTransport(gateway, connector_settings)

    try:
        shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def request_shutdown() -> None:
            if not shutdown_event.is_set():
                logger.info("Gmail connector shutdown requested")
                shutdown_event.set()

        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, request_shutdown)

        if not gateway.enabled:
            logger.warning("Gmail gateway is disabled; connector is idle until enabled")
            await shutdown_event.wait()
            return 0
        if not connector_settings.transport_configured:
            logger.error(
                "Gmail transport is not configured; IMAP and SMTP credentials must be set"
            )
            return 1

        logger.info("Gmail connector started")
        backoff_seconds = _INITIAL_BACKOFF_SECONDS

        while not shutdown_event.is_set():
            try:
                replies = await transport.poll_once()
                if replies:
                    logger.info(
                        "Gmail polling cycle completed",
                        extra={"reply_count": len(replies)},
                    )
                backoff_seconds = _INITIAL_BACKOFF_SECONDS
                await _wait_or_shutdown(
                    shutdown_event,
                    connector_settings.gmail_poll_interval_seconds,
                )
            except GmailTransportError:
                logger.warning("Gmail transport cycle failed; retrying after backoff")
                await _wait_or_shutdown(shutdown_event, backoff_seconds)
                backoff_seconds = min(
                    backoff_seconds * 2,
                    connector_settings.gmail_reconnect_max_seconds,
                )

        return 0
    finally:
        await gateway.close()
        logger.info("Gmail connector stopped")


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
