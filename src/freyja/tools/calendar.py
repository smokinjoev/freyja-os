from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from freyja.calendar import AppleCalendarProvider, CalendarService, InMemoryCalendarProvider
from freyja.calendar.service import parse_date, parse_datetime
from freyja.config import settings
from freyja.memory.models import MemoryPrincipal
from freyja.memory.store import get_active_store
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


_service: CalendarService | None = None


def get_calendar_service() -> CalendarService:
    global _service
    if _service is None:
        _service = build_calendar_service()
    return _service


def set_calendar_service(service: CalendarService | None) -> None:
    global _service
    _service = service


def build_calendar_service() -> CalendarService:
    providers = {"memory": InMemoryCalendarProvider()}
    default_provider = settings.calendar_default_provider.strip() or "memory"
    if settings.apple_calendar_enabled and default_provider == "apple":
        providers["apple"] = AppleCalendarProvider(
            default_calendar_name=settings.apple_calendar_default_calendar_name,
            calendar_aliases=_parse_aliases(settings.apple_calendar_calendar_aliases),
            timeout_seconds=settings.apple_calendar_timeout_seconds,
        )
    if default_provider not in providers:
        default_provider = "memory"
    return CalendarService(providers=providers, default_provider_name=default_provider)


async def _today(request: ToolExecutionRequest) -> dict:
    today = _now(request).date()
    return await get_calendar_service().schedule_for_day(today, member_ids=_member_ids(request))


async def _tomorrow(request: ToolExecutionRequest) -> dict:
    tomorrow = (_now(request) + timedelta(days=1)).date()
    return await get_calendar_service().schedule_for_day(tomorrow, member_ids=_member_ids(request))


async def _free_busy(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    return await get_calendar_service().free_busy(
        start=parse_datetime(args["start"]),
        end=parse_datetime(args["end"]),
        member_ids=_member_ids(request),
    )


async def _list_events(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    events = await get_calendar_service().list_events(
        start=parse_datetime(args["start"]),
        end=parse_datetime(args["end"]),
        member_ids=_member_ids(request),
        calendar_ids=args.get("calendar_ids"),
    )
    return {"events": [event.to_dict() for event in events], "count": len(events)}


async def _search_events(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    events = await get_calendar_service().search_events(
        query=args["query"],
        start=parse_datetime(args["start"]),
        end=parse_datetime(args["end"]),
        member_ids=_member_ids(request),
    )
    return {"events": [event.to_dict() for event in events], "count": len(events)}


async def _create_event(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    event = await get_calendar_service().create_event(
        title=args["title"],
        start=parse_datetime(args["start"]),
        end=parse_datetime(args["end"]),
        member_ids=_member_ids(request),
        calendar_id=args.get("calendar_id"),
        provider_name=args.get("provider"),
        location=args.get("location"),
        description=args.get("description"),
    )
    return {"event": event.to_dict()}


async def _modify_event(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    event = await get_calendar_service().modify_event(
        event_id=args["event_id"],
        updates=args.get("updates", {}),
        provider_name=args.get("provider"),
    )
    return {"event": event.to_dict() if event else None, "modified": event is not None}


async def _delete_event(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    deleted = await get_calendar_service().delete_event(
        event_id=args["event_id"],
        provider_name=args.get("provider"),
    )
    return {"deleted": deleted}


async def _find_time(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    options = await get_calendar_service().find_time(
        start=parse_datetime(args["start"]),
        end=parse_datetime(args["end"]),
        duration_minutes=int(args["duration_minutes"]),
        member_ids=_member_ids(request),
        memory_preferences=_memory_preferences(request),
        limit=int(args.get("limit", 5)),
        after_work=bool(args.get("after_work", False)),
        least_disruptive=bool(args.get("least_disruptive", True)),
    )
    return {"options": [option.to_dict() for option in options], "count": len(options)}


async def _move_if_conflict(request: ToolExecutionRequest) -> dict:
    args = request.arguments
    return await get_calendar_service().move_event_if_conflict(
        event_id=args["event_id"],
        search_start=parse_datetime(args["search_start"]),
        search_end=parse_datetime(args["search_end"]),
        duration_minutes=int(args["duration_minutes"]),
        member_ids=_member_ids(request),
        memory_preferences=_memory_preferences(request),
        provider_name=args.get("provider"),
    )


def register_calendar_tools(registry: ToolRegistry) -> None:
    for definition, implementation in _tool_specs():
        if registry.get_tool(definition.name) is None:
            registry.register(definition, implementation)


def _tool_specs() -> list[tuple[ToolDefinition, Any]]:
    return [
        (_definition("calendar_today_schedule", "Return today's family schedule.", {}, ToolRiskLevel.READ_ONLY), _today),
        (_definition("calendar_tomorrow_schedule", "Return tomorrow's family schedule.", {}, ToolRiskLevel.READ_ONLY), _tomorrow),
        (
            _definition(
                "calendar_free_busy",
                "Return busy events for members in a time window.",
                {"required": ["start", "end"], "properties": _window_properties()},
                ToolRiskLevel.READ_ONLY,
            ),
            _free_busy,
        ),
        (
            _definition(
                "calendar_list_events",
                "List calendar events in a time window.",
                {"required": ["start", "end"], "properties": _window_properties() | {"calendar_ids": {"type": "array"}}},
                ToolRiskLevel.READ_ONLY,
            ),
            _list_events,
        ),
        (
            _definition(
                "calendar_search_events",
                "Search calendar events by title, description, or location.",
                {"required": ["query", "start", "end"], "properties": _window_properties() | {"query": {"type": "string"}}},
                ToolRiskLevel.READ_ONLY,
            ),
            _search_events,
        ),
        (
            _definition(
                "calendar_create_event",
                "Create a calendar event after scheduling has selected the intended slot.",
                {
                    "required": ["title", "start", "end"],
                    "properties": _event_properties() | {"title": {"type": "string"}},
                },
                ToolRiskLevel.CONTROLLED_WRITE,
            ),
            _create_event,
        ),
        (
            _definition(
                "calendar_modify_event",
                "Modify an existing calendar event by ID.",
                {"required": ["event_id", "updates"], "properties": {"event_id": {"type": "string"}, "updates": {"type": "object"}, "provider": {"type": "string"}}},
                ToolRiskLevel.CONTROLLED_WRITE,
            ),
            _modify_event,
        ),
        (
            _definition(
                "calendar_delete_event",
                "Delete an existing calendar event by ID.",
                {"required": ["event_id"], "properties": {"event_id": {"type": "string"}, "provider": {"type": "string"}}},
                ToolRiskLevel.CONTROLLED_WRITE,
            ),
            _delete_event,
        ),
        (
            _definition(
                "calendar_find_time",
                "Find and rank conflict-free scheduling options using family availability and preferences.",
                {
                    "required": ["start", "end", "duration_minutes"],
                    "properties": _window_properties()
                    | {
                        "duration_minutes": {"type": "integer"},
                        "member_ids": {"type": "array"},
                        "memory_preferences": {"type": "array"},
                        "limit": {"type": "integer"},
                        "after_work": {"type": "boolean"},
                        "least_disruptive": {"type": "boolean"},
                    },
                },
                ToolRiskLevel.READ_ONLY,
            ),
            _find_time,
        ),
        (
            _definition(
                "calendar_move_event_if_conflict",
                "Move an event to the best ranked option when a schedule conflict requires it.",
                {
                    "required": ["event_id", "search_start", "search_end", "duration_minutes"],
                    "properties": {
                        "event_id": {"type": "string"},
                        "search_start": {"type": "string"},
                        "search_end": {"type": "string"},
                        "duration_minutes": {"type": "integer"},
                        "member_ids": {"type": "array"},
                        "provider": {"type": "string"},
                    },
                },
                ToolRiskLevel.CONTROLLED_WRITE,
            ),
            _move_if_conflict,
        ),
    ]


def _definition(name: str, description: str, schema: dict[str, Any], risk: ToolRiskLevel) -> ToolDefinition:
    properties = {
        "member_ids": {"type": "array"},
        **schema.get("properties", {}),
    }
    return ToolDefinition(
        name=name,
        description=description,
        version="1.0.0",
        input_schema={"type": "object", "required": schema.get("required", []), "properties": properties},
        output_schema={"type": "object", "properties": {}},
        risk_level=risk,
        host_service="atlas.calendar",
        required_permission="household:calendar.write" if risk != ToolRiskLevel.READ_ONLY else "household:calendar.read",
        confirmation_policy="operator_approval_required" if risk != ToolRiskLevel.READ_ONLY else "none",
        audit_policy="request_result",
        health="available",
        enabled=True,
        timeout_seconds=10,
        tags=["calendar", "family", "personal-intelligence"],
    )


def _window_properties() -> dict[str, Any]:
    return {"start": {"type": "string"}, "end": {"type": "string"}, "member_ids": {"type": "array"}}


def _event_properties() -> dict[str, Any]:
    return _window_properties() | {
        "calendar_id": {"type": "string"},
        "provider": {"type": "string"},
        "location": {"type": "string"},
        "description": {"type": "string"},
    }


def _member_ids(request: ToolExecutionRequest) -> list[str] | None:
    value = request.arguments.get("member_ids")
    if isinstance(value, list):
        return [str(item) for item in value]
    person_data = request.metadata.get("person")
    if isinstance(person_data, dict) and person_data.get("person_id"):
        return [str(person_data["person_id"])]
    return None


def _memory_preferences(request: ToolExecutionRequest) -> list[str]:
    explicit = request.arguments.get("memory_preferences")
    if isinstance(explicit, list):
        return [str(item) for item in explicit]
    principal_data = request.metadata.get("memory_principal")
    if not isinstance(principal_data, dict):
        return []
    try:
        principal = MemoryPrincipal(**principal_data)
        memories = get_active_store().list_shared_memories(principal, limit=20).memories
    except Exception:
        return []
    return [
        memory.content
        for memory in memories
        if memory.kind == "preference" and "calendar" in (memory.metadata or {}).get("domain", "calendar")
    ]


def _now(request: ToolExecutionRequest) -> datetime:
    value = request.arguments.get("now")
    if isinstance(value, str):
        return parse_datetime(value)
    return datetime.now(UTC)


def _parse_aliases(value: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for item in value.split(","):
        if not item.strip() or "=" not in item:
            continue
        key, alias_value = item.split("=", 1)
        key = key.strip()
        alias_value = alias_value.strip()
        if key and alias_value:
            aliases[key] = alias_value
    return aliases
