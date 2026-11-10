from __future__ import annotations

import hashlib
from datetime import date, time

from connectors.gmail.config import settings as gmail_settings
from freyja.scheduled_reminders import ScheduledReminder, ScheduledReminderStore
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


def _store() -> ScheduledReminderStore:
    return ScheduledReminderStore(gmail_settings.gmail_reminder_store_path)


async def _list(request: ToolExecutionRequest) -> dict:
    reminders = _store().list_enabled()
    return {"reminders": reminders, "count": len(reminders)}


async def _create(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    text = " ".join(str(args["text"]).split()).strip()
    reminder_id = str(args.get("reminder_id") or "").strip()
    if not reminder_id:
        reminder_id = "signal-" + hashlib.sha256(text.casefold().encode()).hexdigest()[:12]
    reminder = ScheduledReminder(
        reminder_id=reminder_id,
        text=text,
        start_date=date.fromisoformat(str(args["start_date"])),
        local_time=time.fromisoformat(str(args["local_time"])),
        interval_days=max(1, int(args.get("interval_days", 1))),
        timezone=str(args.get("timezone") or "America/New_York"),
    )
    _store().upsert(reminder)
    return {"created": True, "reminder": _by_id(reminder_id)}


async def _update(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    reminder_id = str(args["reminder_id"])
    store = _store()
    existing = next((item for item in store.list_enabled() if item["reminder_id"] == reminder_id), None)
    if existing is None:
        return {"updated": False, "error": "Active reminder not found."}
    reminder = ScheduledReminder(
        reminder_id=reminder_id,
        text=str(args.get("text") or existing["text"]),
        start_date=date.fromisoformat(str(args.get("start_date") or existing["start_date"])),
        local_time=time.fromisoformat(str(args.get("local_time") or existing["local_time"])),
        interval_days=max(1, int(args.get("interval_days") or existing["interval_days"])),
        timezone=str(args.get("timezone") or existing["timezone"]),
    )
    store.upsert(reminder)
    return {"updated": True, "reminder": _by_id(reminder_id)}


async def _stop(request: ToolExecutionRequest) -> dict:
    reminder_id = str(request.arguments["reminder_id"])
    return {"stopped": _store().disable(reminder_id), "reminder_id": reminder_id}


def _by_id(reminder_id: str) -> dict[str, object] | None:
    return next((item for item in _store().list_enabled() if item["reminder_id"] == reminder_id), None)


def register_scheduled_reminder_tools(registry: ToolRegistry) -> None:
    specs = (
        ("scheduled_reminder_list", "List active recurring Signal reminders. Use this before changing or stopping one.", {}, ToolRiskLevel.READ_ONLY, _list),
        (
            "scheduled_reminder_create",
            "Create a persistent Signal reminder. Resolve natural language into an ISO start_date, 24-hour local_time, and interval_days; every other day means interval_days=2. Confirm only when created is true.",
            {"required": ["text", "start_date", "local_time"], "properties": {
                "text": {"type": "string", "description": "Complete Signal message to send when due."},
                "start_date": {"type": "string", "description": "ISO local date, YYYY-MM-DD."},
                "local_time": {"type": "string", "description": "24-hour local time, HH:MM."},
                "interval_days": {"type": "integer", "minimum": 1},
                "timezone": {"type": "string"},
            }},
            ToolRiskLevel.CONTROLLED_WRITE, _create,
        ),
        (
            "scheduled_reminder_update",
            "Change an active Signal reminder. First list reminders and use the exact reminder_id.",
            {"required": ["reminder_id"], "properties": {
                "reminder_id": {"type": "string"}, "text": {"type": "string"},
                "start_date": {"type": "string"}, "local_time": {"type": "string"},
                "interval_days": {"type": "integer", "minimum": 1}, "timezone": {"type": "string"},
            }},
            ToolRiskLevel.CONTROLLED_WRITE, _update,
        ),
        (
            "scheduled_reminder_stop",
            "Stop an active Signal reminder. First list reminders and use the exact reminder_id. Confirm only when stopped is true.",
            {"required": ["reminder_id"], "properties": {"reminder_id": {"type": "string"}}},
            ToolRiskLevel.CONTROLLED_WRITE, _stop,
        ),
    )
    for name, description, schema, risk, implementation in specs:
        registry.register(ToolDefinition(
            name=name, description=description,
            input_schema={"type": "object", **schema}, output_schema={"type": "object"},
            risk_level=risk, tags=["signal", "reminders", "scheduled"],
        ), implementation)
