#!/usr/bin/env python3
"""Run the Telegram gateway polling loop."""

from __future__ import annotations

import sys
from pathlib import Path

# Rebuild sys.path BEFORE importing any standard library modules that may
# transitively import signal (e.g. asyncio -> subprocess -> signal).  Put the
# 'connectors' directory at the very end so it cannot shadow stdlib modules.
_PROJECT_DIR = Path(__file__).resolve().parents[1]
_SRC_DIR = str(_PROJECT_DIR / "src")
_CONNECTORS_DIR = str(_PROJECT_DIR / "connectors")
_PROJECT_ROOT = str(_PROJECT_DIR)
_SCRIPT_DIR = str(_PROJECT_DIR / "scripts")

_cleaned: list[str] = []
for _entry in sys.path:
    if _entry in {_SCRIPT_DIR, _PROJECT_ROOT, _SRC_DIR, _CONNECTORS_DIR, ""}:
        continue
    _cleaned.append(_entry)

# src first, then project root (so connectors.telegram resolves), then the
# rest of the path, then connectors last.
sys.path = [_SRC_DIR, _PROJECT_ROOT] + _cleaned + [_CONNECTORS_DIR]

import asyncio
import logging
import signal
import time

from connectors.telegram.config import configured_telegram_settings  # noqa: E402
from connectors.telegram.gateway import TelegramGateway  # noqa: E402

logger = logging.getLogger("telegram_gateway_runner")

_MIN_BACKOFF = 1.0
_MAX_BACKOFF = 60.0
_BACKOFF_FACTOR = 2.0


def _setup_logging() -> None:
    log_dir = _PROJECT_DIR / "logs"
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
    # httpx logs full request URLs at INFO, which would leak the bot token.
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def main() -> int:
    _setup_logging()
    gateways = [TelegramGateway(settings=item) for item in configured_telegram_settings()]
    enabled_gateways = [gateway for gateway in gateways if gateway.enabled]

    if not enabled_gateways:
        logger.warning("Telegram gateway is disabled; exiting.")
        return 0

    shutdown_event = asyncio.Event()

    def _handle_signal(signum: int, _frame: object) -> None:
        logger.info("Received signal %s; shutting down gracefully.", signum)
        shutdown_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    async def poll_gateway(gateway: TelegramGateway) -> None:
        backoff = _MIN_BACKOFF
        while not shutdown_event.is_set():
            try:
                replies = await gateway.poll_updates()
                for reply in replies:
                    await gateway.send_reply(reply)
                backoff = _MIN_BACKOFF
            except Exception:
                logger.exception(
                    "Telegram polling iteration failed agent=%s",
                    gateway._settings.telegram_agent_name,
                )
                try:
                    await asyncio.wait_for(
                        shutdown_event.wait(), timeout=min(backoff, _MAX_BACKOFF)
                    )
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * _BACKOFF_FACTOR, _MAX_BACKOFF)

            try:
                await asyncio.wait_for(
                    shutdown_event.wait(),
                    timeout=max(0.0, gateway._settings.telegram_poll_interval_seconds),
                )
            except asyncio.TimeoutError:
                pass

    tasks = [asyncio.create_task(poll_gateway(gateway)) for gateway in enabled_gateways]
    try:
        await shutdown_event.wait()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for gateway in gateways:
            await gateway.close()
        logger.info("Telegram gateway stopped.")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as exc:
        logging.exception("Fatal error in Telegram gateway runner: %s", exc)
        sys.exit(1)
