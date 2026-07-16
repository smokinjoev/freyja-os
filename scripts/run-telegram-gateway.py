#!/usr/bin/env python3
"""Run the Telegram gateway polling loop."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

# Add src to path when run as a LaunchAgent script.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))
sys.path.insert(0, str(PROJECT_DIR / "connectors"))

from connectors.telegram.gateway import TelegramGateway  # noqa: E402

logger = logging.getLogger("telegram_gateway_runner")

_MIN_BACKOFF = 1.0
_MAX_BACKOFF = 60.0
_BACKOFF_FACTOR = 2.0


def _setup_logging() -> None:
    log_dir = PROJECT_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / "telegram-gateway.log"
    handler = logging.FileHandler(log_path)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # Also log errors to stderr so launchd captures them.
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root.addHandler(stderr_handler)


async def main() -> int:
    _setup_logging()
    gateway = TelegramGateway()

    if not gateway.enabled:
        logger.warning("Telegram gateway is disabled; exiting.")
        return 0

    shutdown_event = asyncio.Event()

    def _handle_signal(signum: int, _frame: object) -> None:
        logger.info("Received signal %s; shutting down gracefully.", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    backoff = _MIN_BACKOFF
    try:
        while not shutdown_event.is_set():
            try:
                replies = await gateway.poll_updates()
                for reply in replies:
                    await gateway.send_reply(reply)
                backoff = _MIN_BACKOFF
            except Exception:
                logger.exception("Telegram polling iteration failed")
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=min(backoff, _MAX_BACKOFF),
                )
                backoff = min(backoff * _BACKOFF_FACTOR, _MAX_BACKOFF)

            try:
                poll_interval = gateway._settings.telegram_poll_interval_seconds
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=max(0.0, poll_interval),
                )
            except asyncio.TimeoutError:
                pass
    finally:
        await gateway.close()
        logger.info("Telegram gateway stopped.")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:
        logging.exception("Fatal error in Telegram gateway runner: %s", exc)
        sys.exit(1)
