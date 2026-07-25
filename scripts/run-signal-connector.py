#!/usr/bin/env python3
"""Run the Signal connector polling loop."""

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

from connectors.signal.config import SignalSettings  # noqa: E402
from connectors.signal.gateway import SignalGateway  # noqa: E402
from connectors.signal.transport import (  # noqa: E402
    SignalRestTransport,
    SignalTransportError,
)

logger = logging.getLogger("signal_connector_runner")

_INITIAL_BACKOFF_SECONDS = 1.0


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Keep request URLs and payload details out of normal connector logs.
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
    connector_settings = SignalSettings()
    gateway = SignalGateway()
    transport = SignalRestTransport(gateway, connector_settings)

    try:
        if not gateway.enabled:
            logger.warning("Signal gateway is disabled; connector will not start")
            return 0
        if not connector_settings.transport_configured:
            logger.error(
                "Signal transport is not configured; "
                "SIGNAL_ACCOUNT_NUMBER must be set"
            )
            return 1

        shutdown_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def request_shutdown() -> None:
            if not shutdown_event.is_set():
                logger.info("Signal connector shutdown requested")
                shutdown_event.set()

        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, request_shutdown)

        logger.info("Signal connector started")
        backoff_seconds = _INITIAL_BACKOFF_SECONDS

        while not shutdown_event.is_set():
            try:
                replies = await transport.poll_once()
                if replies:
                    logger.info(
                        "Signal polling cycle completed",
                        extra={"reply_count": len(replies)},
                    )
                backoff_seconds = _INITIAL_BACKOFF_SECONDS
                await _wait_or_shutdown(
                    shutdown_event,
                    connector_settings.signal_poll_interval_seconds,
                )
            except SignalTransportError:
                logger.warning(
                    "Signal transport cycle failed; retrying after backoff"
                )
                await _wait_or_shutdown(shutdown_event, backoff_seconds)
                backoff_seconds = min(
                    backoff_seconds * 2,
                    connector_settings.signal_reconnect_max_seconds,
                )

        return 0
    finally:
        await transport.close()
        await gateway.close()
        logger.info("Signal connector stopped")


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130) from None
