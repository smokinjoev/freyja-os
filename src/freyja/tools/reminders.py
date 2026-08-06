from __future__ import annotations

from typing import Any

from freyja.config import settings
from freyja.reminders import AppleReminderProvider, ReminderService
from freyja.reminders.service import parse_datetime
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


_service: ReminderService | None = None


def get_reminder_service() -> ReminderService:
    global _service
    if _service is None:
        providers = None
        if settings.apple_reminders_bridge_url and settings.apple_reminders_bridge_token:
            providers = {
                "apple": AppleReminderProvider(
                    base_url=settings.apple_reminders_bridge_url,
                    token=settings.apple_reminders_bridge_token,
                    timeout_seconds=settings.apple_reminders_bridge_timeout_seconds,
                )
            }
        _service = ReminderService(providers=providers)
    return _service


def set_reminder_service(service: ReminderService | None) -> None:
    global _service
    _service = service


async def _lists(request: ToolExecutionRequest) -> dict:
    provider = request.arguments.get("provider", "memory")
    lists = await get_reminder_service().lists(provider_name=provider)
    return {"lists": [item.to_dict() for item in lists], "count": len(lists)}


async def _list_reminders(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    reminders = await get_reminder_service().list_reminders(
        list_ids=[str(item) for item in args.get("list_ids", [])],
        include_completed=bool(args.get("include_completed", False)),
        provider_name=args.get("provider", "memory"),
    )
    return {"reminders": [item.to_dict() for item in reminders], "count": len(reminders)}


async def _create_reminder(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    reminder = await get_reminder_service().create_reminder(
        title=args["title"],
        due=parse_datetime(args.get("due")),
        notes=args.get("notes"),
        list_id=args.get("list_id"),
        provider_name=args.get("provider", "memory"),
    )
    return {"reminder": reminder.to_dict()}


async def _complete_reminder(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    reminder = await get_reminder_service().complete_reminder(
        reminder_id=args["reminder_id"],
        provider_name=args.get("provider", "memory"),
    )
    return {"reminder": reminder.to_dict() if reminder else None, "completed": reminder is not None}


async def _delete_reminder(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    deleted = await get_reminder_service().delete_reminder(
        reminder_id=args["reminder_id"],
        provider_name=args.get("provider", "memory"),
    )
    return {"deleted": deleted}


def register_reminder_tools(registry: ToolRegistry) -> None:
    for definition, implementation in _tool_specs():
        if registry.get_tool(definition.name) is None:
            registry.register(definition, implementation)


def _tool_specs() -> list[tuple[ToolDefinition, Any]]:
    return [
        (
            _definition(
                "reminders_lists",
                "List available reminder lists.",
                {"properties": {"provider": {"type": "string"}}},
                ToolRiskLevel.READ_ONLY,
            ),
            _lists,
        ),
        (
            _definition(
                "reminders_list",
                "List reminders, optionally scoped to reminder lists.",
                {
                    "properties": {
                        "list_ids": {"type": "array"},
                        "include_completed": {"type": "boolean"},
                        "provider": {"type": "string"},
                    }
                },
                ToolRiskLevel.READ_ONLY,
            ),
            _list_reminders,
        ),
        (
            _definition(
                "reminders_create",
                "Create a reminder with optional due date, notes, and list.",
                {
                    "required": ["title"],
                    "properties": {
                        "title": {"type": "string"},
                        "due": {"type": "string"},
                        "notes": {"type": "string"},
                        "list_id": {"type": "string"},
                        "provider": {"type": "string"},
                    },
                },
                ToolRiskLevel.CONTROLLED_WRITE,
            ),
            _create_reminder,
        ),
        (
            _definition(
                "reminders_complete",
                "Mark an existing reminder complete.",
                {"required": ["reminder_id"], "properties": {"reminder_id": {"type": "string"}, "provider": {"type": "string"}}},
                ToolRiskLevel.CONTROLLED_WRITE,
            ),
            _complete_reminder,
        ),
        (
            _definition(
                "reminders_delete",
                "Delete an existing reminder.",
                {"required": ["reminder_id"], "properties": {"reminder_id": {"type": "string"}, "provider": {"type": "string"}}},
                ToolRiskLevel.CONTROLLED_WRITE,
            ),
            _delete_reminder,
        ),
    ]


def _definition(name: str, description: str, schema: dict[str, Any], risk: ToolRiskLevel) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        version="1.0.0",
        input_schema={"type": "object", "required": schema.get("required", []), "properties": schema.get("properties", {})},
        output_schema={"type": "object", "properties": {}},
        risk_level=risk,
        enabled=True,
        timeout_seconds=10,
        tags=["reminders", "personal-intelligence"],
    )
