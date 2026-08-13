import asyncio
import contextlib
import logging
from typing import Any

from fastapi import FastAPI

from freyja.config import settings


logger = logging.getLogger(__name__)


async def warm_local_models_once(client: Any, *, service_name: str) -> list[dict[str, Any]]:
    if not settings.ollama_warmup_enabled:
        return []

    results: list[dict[str, Any]] = []
    for model in settings.ollama_warmup_model_names:
        result = await client.warm(model=model)
        result["service"] = service_name
        results.append(result)
        if "error" in result:
            logger.warning("Ollama warmup failed: %s", result)
        else:
            logger.info("Ollama warmup completed: %s", result)
    return results


async def warm_local_models_loop(client: Any, *, service_name: str) -> None:
    interval = max(60.0, float(settings.ollama_warmup_interval_seconds))
    while True:
        await warm_local_models_once(client, service_name=service_name)
        await asyncio.sleep(interval)


def start_ollama_warmup(app: FastAPI, client: Any, *, service_name: str) -> None:
    if not settings.ollama_warmup_enabled:
        return
    app.state.ollama_warmup_task = asyncio.create_task(
        warm_local_models_loop(client, service_name=service_name)
    )


async def stop_ollama_warmup(app: FastAPI) -> None:
    task = getattr(app.state, "ollama_warmup_task", None)
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
