import asyncio
import logging
import os
import platform
import subprocess
from typing import Any

from freyja.config import settings
from freyja.iris_router import IrisRouterClient

logger = logging.getLogger(__name__)

_task: asyncio.Task[None] | None = None


def iris_warm_monitor_enabled() -> bool:
    return settings.iris_router_enabled and settings.iris_router_warm_enabled


def available_memory_mb() -> int | None:
    system = platform.system().lower()
    if system == "darwin":
        return _darwin_available_memory_mb()
    if system == "linux":
        return _linux_available_memory_mb()
    return None


def _darwin_available_memory_mb() -> int | None:
    try:
        page_size = int(subprocess.check_output(["sysctl", "-n", "hw.pagesize"], text=True).strip())
        output = subprocess.check_output(["vm_stat"], text=True)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    pages = 0
    for line in output.splitlines():
        key, _, raw_value = line.partition(":")
        if key.strip() not in {"Pages free", "Pages inactive", "Pages speculative", "Pages purgeable"}:
            continue
        try:
            pages += int(raw_value.strip().rstrip("."))
        except ValueError:
            continue
    return int((pages * page_size) / (1024 * 1024))


def _linux_available_memory_mb() -> int | None:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    parts = line.split()
                    return int(int(parts[1]) / 1024)
    except (OSError, ValueError, IndexError):
        return None
    return None


async def warm_iris_once(client: IrisRouterClient | None = None) -> dict[str, Any]:
    available_mb = available_memory_mb()
    minimum_mb = int(settings.iris_router_min_available_memory_mb)
    if available_mb is not None and available_mb < minimum_mb:
        event = {
            "event": "iris_router_warm_skipped_low_memory",
            "warmed": False,
            "resident": False,
            "available_memory_mb": available_mb,
            "minimum_memory_mb": minimum_mb,
            "base_url": settings.iris_ollama_base_url,
            "model": settings.iris_router_model,
        }
        logger.warning(event)
        return event

    client = client or IrisRouterClient()
    warmed = await client.warm()
    resident = await client.model_resident() if warmed else False
    event = {
        "event": "iris_router_warm",
        "warmed": warmed,
        "resident": resident,
        "available_memory_mb": available_mb,
        "minimum_memory_mb": minimum_mb,
        "base_url": settings.iris_ollama_base_url,
        "model": settings.iris_router_model,
        "keep_alive": settings.iris_router_keep_alive,
    }
    if warmed and resident:
        logger.info(event)
    else:
        logger.warning(event)
    return event


async def _iris_warm_loop() -> None:
    interval = max(60, int(settings.iris_router_warm_interval_seconds))
    while True:
        try:
            await warm_iris_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Iris warmup task crashed")
        await asyncio.sleep(interval)


def start_iris_warm_monitor() -> asyncio.Task[None] | None:
    global _task
    if not iris_warm_monitor_enabled():
        return None
    if _task is not None and not _task.done():
        return _task
    _task = asyncio.create_task(_iris_warm_loop())
    return _task


async def stop_iris_warm_monitor() -> None:
    global _task
    if _task is None:
        return
    task = _task
    _task = None
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
