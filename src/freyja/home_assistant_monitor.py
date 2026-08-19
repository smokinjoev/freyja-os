import asyncio
import logging
from typing import Any

from freyja.config import settings
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.registry import ToolRegistry, get_registry

logger = logging.getLogger(__name__)

_task: asyncio.Task[None] | None = None


def home_assistant_inventory_monitor_enabled() -> bool:
    return (
        settings.home_assistant_inventory_poll_enabled
        and bool(settings.home_assistant_base_url)
        and bool(settings.home_assistant_access_token)
    )


async def poll_home_assistant_inventory_once(registry: ToolRegistry | None = None) -> dict[str, Any]:
    registry = registry or get_registry()
    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="home_assistant_inventory_changes",
            arguments={"include_all": True, "update_snapshot": True},
            actor="home_assistant_inventory_monitor",
            metadata={
                "director_authorized": True,
                "person": {"person_id": "family"},
            },
        )
    )
    if not result.success:
        logger.warning(
            {
                "event": "home_assistant_inventory_poll_failed",
                "error_code": result.error_code,
                "public_error_message": result.public_error_message,
            }
        )
        return {
            "success": False,
            "error_code": result.error_code,
            "public_error_message": result.public_error_message,
        }

    output = result.output
    added = output.get("added") if isinstance(output.get("added"), list) else []
    removed = output.get("removed") if isinstance(output.get("removed"), list) else []
    changed = output.get("changed") if isinstance(output.get("changed"), list) else []
    if added or removed or changed:
        logger.info(
            {
                "event": "home_assistant_inventory_changed",
                "location": output.get("location"),
                "current_count": output.get("current_count"),
                "previous_count": output.get("previous_count"),
                "added": [item.get("entity_id") for item in added if isinstance(item, dict)],
                "removed": [item.get("entity_id") for item in removed if isinstance(item, dict)],
                "changed": [
                    item.get("after", {}).get("entity_id")
                    for item in changed
                    if isinstance(item, dict) and isinstance(item.get("after"), dict)
                ],
            }
        )
    return {"success": True, **output}


async def _inventory_monitor_loop() -> None:
    interval = max(60, int(settings.home_assistant_inventory_poll_interval_seconds))
    while True:
        try:
            await poll_home_assistant_inventory_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Home Assistant inventory poll crashed")
        await asyncio.sleep(interval)


def start_home_assistant_inventory_monitor() -> asyncio.Task[None] | None:
    global _task
    if not home_assistant_inventory_monitor_enabled():
        return None
    if _task is not None and not _task.done():
        return _task
    _task = asyncio.create_task(_inventory_monitor_loop())
    return _task


async def stop_home_assistant_inventory_monitor() -> None:
    global _task
    if _task is None:
        return
    task = _task
    _task = None
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
