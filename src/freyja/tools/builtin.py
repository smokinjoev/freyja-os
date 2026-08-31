import os
import subprocess
from pathlib import Path

from freyja.memory.store import get_active_store
from freyja.config import settings
from freyja.macagent import MacAgentClient, MacAgentOperationRequest
from freyja.memory.models import MemoryPrincipal
from freyja.ollama_client import OllamaClient
from freyja.openrouter_client import OpenRouterClient
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolImplementation, ToolRiskLevel
from freyja.tools.registry import ToolRegistry
from freyja.tools.calendar import register_calendar_tools
from freyja.tools.home_assistant import register_home_assistant_tools
from freyja.tools.identity import register_identity_tools
from freyja.tools.local_host import register_local_host_tools
from freyja.tools.weather import WeatherRequestType, classify_weather_request, get_weather
from freyja.tools.web_search import web_fetch, web_search


async def _get_weather_implementation(request: ToolExecutionRequest) -> dict:
    import datetime as _datetime

    args = request.arguments or {}
    location = args.get("location", "")
    request_type_arg = args.get("request_type", "current")
    target_date_arg = args.get("target_date") or args.get("forecast_date") or args.get("date")
    target_label = args.get("target_label", "")

    try:
        request_type = WeatherRequestType(request_type_arg)
    except ValueError:
        return {
            "live_data_available": False,
            "request_type": request_type_arg,
            "location": location,
            "target_label": target_label,
            "summary": "Unsupported weather request type.",
            "detail": "request_type must be 'current' or 'forecast'.",
        }

    target_date = None
    if target_date_arg:
        try:
            target_date = _datetime.datetime.strptime(str(target_date_arg), "%Y-%m-%d").date()
        except ValueError:
            return {
                "live_data_available": False,
                "request_type": request_type_arg,
                "location": location,
                "target_label": target_label,
                "summary": "Invalid forecast date.",
                "detail": "target_date must be in YYYY-MM-DD format.",
            }

    return await get_weather(
        location=location,
        request_type=request_type,
        target_date=target_date,
        target_label=target_label,
    )


async def _web_search_implementation(request: ToolExecutionRequest) -> dict:
    args = request.arguments or {}
    return await web_search(
        str(args.get("query") or ""),
        max_results=int(args.get("max_results") or 5),
    )


async def _web_fetch_implementation(request: ToolExecutionRequest) -> dict:
    args = request.arguments or {}
    return await web_fetch(
        str(args.get("url") or ""),
        max_chars=int(args.get("max_chars") or 12000),
    )


async def _event_weather_implementation(request: ToolExecutionRequest) -> dict:
    import datetime as _datetime
    import re

    args = request.arguments or {}
    event = " ".join(str(args.get("event") or args.get("query") or "").split())
    if not event:
        return {"success": False, "summary": "Event name is required."}
    year = str(args.get("year") or _datetime.date.today().year)
    search = await web_search(f"{event} {year} dates location", max_results=5)
    text = " ".join(
        f"{item.get('title', '')} {item.get('snippet', '')}"
        for item in search.get("results", [])
        if isinstance(item, dict)
    )
    location = None
    if re.search(r"\bAtlanta\b", text, flags=re.IGNORECASE):
        location = "Atlanta, Georgia"
    date_match = re.search(
        rf"(?:September|Sep\.?)\s+(\d{{1,2}})(?:\s*[-–]\s*(?:September|Sep\.?)?\s*\d{{1,2}})?\s*,?\s*{re.escape(year)}",
        text,
        flags=re.IGNORECASE,
    )
    target_date = None
    if date_match:
        target_date = _datetime.date(int(year), 9, int(date_match.group(1)))
    if not location:
        return {
            "success": False,
            "event": event,
            "search": search,
            "summary": "Could not resolve event location from search results.",
        }
    if target_date is None:
        return {
            "success": False,
            "event": event,
            "location": location,
            "search": search,
            "summary": "Could not resolve event date from search results.",
        }
    weather = await get_weather(
        location=location,
        request_type=WeatherRequestType.FORECAST,
        target_date=target_date,
        target_label=f"{event} opening day",
    )
    return {
        "success": bool(weather.get("live_data_available")),
        "event": event,
        "year": year,
        "location": location,
        "target_date": target_date.isoformat(),
        "search": search,
        "weather": weather,
    }


async def _macagent_health_implementation(request: ToolExecutionRequest) -> dict:
    health = await MacAgentClient().health()
    return health.model_dump(mode="json")


async def _apple_contacts_list_implementation(request: ToolExecutionRequest) -> dict:
    args = request.arguments or {}
    result = await MacAgentClient().invoke(
        MacAgentOperationRequest(
            capability="apple.contacts.read",
            operation="list_contacts",
            arguments={
                "include_identifiers": bool(args.get("include_identifiers") is True),
                "limit": int(args.get("limit") or 100),
            },
            request_id=request.request_id,
            actor=request.actor or "atlas_director",
            director_authorized=True,
            required_permission="apple.contacts.read",
            principal=request.metadata.get("memory_principal") if isinstance(request.metadata, dict) else None,
            person=request.metadata.get("person") if isinstance(request.metadata, dict) else None,
        )
    )
    return result.output if result.ok else {"error": result.error or "MacAgent contacts read failed."}


async def _apple_messages_recent_implementation(request: ToolExecutionRequest) -> dict:
    args = request.arguments or {}
    result = await MacAgentClient().invoke(
        MacAgentOperationRequest(
            capability="apple.messages.read",
            operation="recent_messages",
            arguments={"limit": int(args.get("limit") or 20)},
            request_id=request.request_id,
            actor=request.actor or "atlas_director",
            director_authorized=True,
            required_permission="apple.messages.read",
            principal=request.metadata.get("memory_principal") if isinstance(request.metadata, dict) else None,
            person=request.metadata.get("person") if isinstance(request.metadata, dict) else None,
        )
    )
    return result.output if result.ok else {"error": result.error or "MacAgent messages read failed."}


async def _apple_messages_send_implementation(request: ToolExecutionRequest) -> dict:
    args = request.arguments or {}
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    result = await MacAgentClient().invoke(
        MacAgentOperationRequest(
            capability="apple.messages.send",
            operation="send_reply",
            arguments={
                "chat_id": int(args.get("chat_id") or 0),
                "text": str(args.get("text") or ""),
            },
            request_id=request.request_id,
            actor=request.actor or "atlas_director",
            director_authorized=True,
            required_permission="apple.messages.send",
            approval_granted=metadata.get("approval_granted") is True,
            principal=metadata.get("memory_principal"),
            person=metadata.get("person"),
        )
    )
    return result.output if result.ok else {"error": result.error or "MacAgent Messages send failed."}


async def _apple_mailbox_counts_implementation(request: ToolExecutionRequest) -> dict:
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    result = await MacAgentClient().invoke(
        MacAgentOperationRequest(
            capability="apple.mail.read",
            operation="mailbox_counts",
            arguments={},
            request_id=request.request_id,
            actor=request.actor or "atlas_director",
            director_authorized=True,
            required_permission="apple.mail.read",
            principal=metadata.get("memory_principal"),
            person=metadata.get("person"),
        )
    )
    return result.output if result.ok else {"error": result.error or "MacAgent Mail read failed."}


async def _apple_music_current_track_implementation(request: ToolExecutionRequest) -> dict:
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    result = await MacAgentClient().invoke(
        MacAgentOperationRequest(
            capability="apple.music.read",
            operation="current_track",
            arguments={},
            request_id=request.request_id,
            actor=request.actor or "atlas_director",
            director_authorized=True,
            required_permission="apple.music.read",
            principal=metadata.get("memory_principal"),
            person=metadata.get("person"),
        )
    )
    return result.output if result.ok else {"error": result.error or "MacAgent Music read failed."}


async def _apple_music_play_query_implementation(request: ToolExecutionRequest) -> dict:
    args = request.arguments or {}
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    result = await MacAgentClient().invoke(
        MacAgentOperationRequest(
            capability="apple.music.write",
            operation="play_query",
            arguments={
                "query": str(args.get("query") or "music"),
                "destination": str(args.get("destination") or ""),
            },
            request_id=request.request_id,
            actor=request.actor or "atlas_director",
            director_authorized=True,
            required_permission="apple.music.write",
            approval_granted=metadata.get("approval_granted") is True,
            principal=metadata.get("memory_principal"),
            person=metadata.get("person"),
        )
    )
    return result.output if result.ok else {"error": result.error or "MacAgent Music write failed."}


async def _apple_browser_front_tab_implementation(request: ToolExecutionRequest) -> dict:
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    result = await MacAgentClient().invoke(
        MacAgentOperationRequest(
            capability="apple.browser.read",
            operation="front_tab",
            arguments={},
            request_id=request.request_id,
            actor=request.actor or "atlas_director",
            director_authorized=True,
            required_permission="apple.browser.read",
            principal=metadata.get("memory_principal"),
            person=metadata.get("person"),
        )
    )
    return result.output if result.ok else {"error": result.error or "MacAgent Browser read failed."}


async def _apple_shortcuts_run_implementation(request: ToolExecutionRequest) -> dict:
    args = request.arguments or {}
    metadata = request.metadata if isinstance(request.metadata, dict) else {}
    operation_args = {"name": str(args.get("name") or "")}
    if args.get("input") is not None:
        operation_args["input"] = str(args.get("input") or "")
    result = await MacAgentClient().invoke(
        MacAgentOperationRequest(
            capability="apple.shortcuts.run",
            operation="run_shortcut",
            arguments=operation_args,
            request_id=request.request_id,
            actor=request.actor or "atlas_director",
            director_authorized=True,
            required_permission="apple.shortcuts.run",
            approval_granted=metadata.get("approval_granted") is True,
            principal=metadata.get("memory_principal"),
            person=metadata.get("person"),
        )
    )
    return result.output if result.ok else {"error": result.error or "MacAgent Shortcuts run failed."}


async def _system_health_implementation(request: ToolExecutionRequest) -> dict:
    return {
        "director": {"status": "ok"},
        "ollama": {
            "healthy": await _ollama_healthy(),
            "base_url": getattr(_ollama_client(), "base_url", None),
        },
        "openrouter": {"healthy": await _openrouter_healthy()},
        "memory": {"enabled": _memory_enabled()},
    }


async def _list_models_implementation(request: ToolExecutionRequest) -> dict:
    tags = await _ollama_tags()
    if isinstance(tags, dict) and "error" in tags:
        return {"models": [], "ollama_error": tags["error"]}
    return {"models": tags.get("models", [])}


async def _recall_conversation_implementation(request: ToolExecutionRequest) -> dict:
    args = request.arguments or {}
    conversation_id = args.get("conversation_id")
    if not conversation_id:
        return {"error": "Missing required argument: conversation_id"}
    limit = args.get("limit", 50)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return {"error": "limit must be an integer"}
    response = get_active_store().get_messages(conversation_id, limit=limit)
    return {
        "conversation_id": response.conversation_id,
        "messages": [message.model_dump(mode="json") for message in response.messages],
        "count": len(response.messages),
    }


async def _memory_recall_shared_implementation(request: ToolExecutionRequest) -> dict:
    principal_data = request.metadata.get("memory_principal")
    if not isinstance(principal_data, dict):
        return {"memories": [], "count": 0, "error": "Missing memory principal."}
    try:
        principal = MemoryPrincipal(**principal_data)
    except Exception:
        return {"memories": [], "count": 0, "error": "Invalid memory principal."}

    args = request.arguments or {}
    limit = max(1, min(int(args.get("limit", 12)), 50))
    kind = args.get("kind")
    kinds = [str(kind)] if kind else None
    query = str(args.get("query") or "").strip().lower()
    domain = str(args.get("domain") or "").strip().lower()
    response = get_active_store().list_shared_memories(principal, kinds=kinds, limit=limit)
    memories = []
    for memory in response.memories:
        metadata = memory.metadata or {}
        memory_domain = str(metadata.get("domain") or "").lower()
        searchable = " ".join(
            str(part).lower()
            for part in (memory.memory_id, memory.kind, memory.content, memory.source, memory_domain)
        )
        if query and query not in searchable:
            continue
        if domain and domain != memory_domain:
            continue
        memories.append(memory.model_dump(mode="json"))
    return {"memories": memories, "count": len(memories)}


_BUILTIN_TOOL_NAMES = (
    "system_health",
    "list_models",
    "recall_conversation",
    "get_weather",
    "event_weather",
    "web_search",
    "web_fetch",
    "macagent_health",
    "apple_contacts_list",
    "apple_messages_recent",
    "apple_messages_send",
    "apple_mailbox_counts",
    "apple_music_current_track",
    "apple_browser_front_tab",
    "apple_shortcuts_run",
    "hostname",
    "current_time",
    "disk_usage",
    "director_health",
    "repository_status",
    "calendar_today_schedule",
    "calendar_tomorrow_schedule",
    "calendar_free_busy",
    "calendar_list_events",
    "calendar_search_events",
    "calendar_create_event",
    "calendar_modify_event",
    "calendar_delete_event",
    "calendar_find_time",
    "calendar_move_event_if_conflict",
    "identity_resolution",
    "identity_relationships",
    "home_assistant_read_state",
    "home_assistant_list_states",
    "home_assistant_inventory_changes",
    "home_assistant_control_state",
    "memory_recall_shared",
)


def _registration_is_complete(registry: ToolRegistry, names: tuple[str, ...]) -> bool:
    return all(registry.get_tool(name) is not None for name in names)


def _assert_registration_consistent(registry: ToolRegistry, names: tuple[str, ...]) -> None:
    present = {name for name in names if registry.get_tool(name) is not None}
    if present and present != set(names):
        missing = set(names) - present
        raise RuntimeError(
            f"Tool registration is inconsistent: present={sorted(present)}, missing={sorted(missing)}"
        )


def register_builtin_tools(registry: ToolRegistry) -> None:
    _assert_registration_consistent(registry, _BUILTIN_TOOL_NAMES)
    if _registration_is_complete(registry, _BUILTIN_TOOL_NAMES):
        return
    register_local_host_tools(registry)
    register_calendar_tools(registry)
    register_identity_tools(registry)
    register_home_assistant_tools(registry)
    registry.register(
        ToolDefinition(
            name="get_weather",
            description=(
                "Return current weather or a forecast for a location. "
                "request_type must be 'current' or 'forecast'; for forecast, "
                "target_date and target_label should be supplied. Falls back safely if live data is not configured."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["location", "request_type"],
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City or location, e.g. 'Aiken, South Carolina'.",
                    },
                    "request_type": {
                        "type": "string",
                        "enum": ["current", "forecast"],
                        "description": "Whether to fetch current conditions or a forecast.",
                    },
                    "target_date": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD) for forecast requests.",
                    },
                    "forecast_date": {
                        "type": "string",
                        "description": "Alias for target_date when the model names the forecast date this way.",
                    },
                    "target_label": {
                        "type": "string",
                        "description": "Human label for the forecast date, e.g. 'tomorrow'.",
                    },
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "live_data_available": {"type": "boolean"},
                    "request_type": {"type": "string"},
                    "location": {"type": "string"},
                    "target_label": {"type": "string"},
                    "summary": {"type": "string"},
                    "detail": {"type": "string"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=20,
            tags=["weather", "live-data"],
        ),
        _get_weather_implementation,
    )
    registry.register(
        ToolDefinition(
            name="web_search",
            description=(
                "Search the public web for current information and return normalized result titles, URLs, and snippets. "
                "Use this for lookup/search/current-fact questions before answering from model memory."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string", "description": "Search query."},
                    "max_results": {"type": "integer", "description": "Maximum results, 1 through 10."},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "query": {"type": "string"},
                    "provider": {"type": "string"},
                    "results": {"type": "array"},
                    "count": {"type": "integer"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=30,
            tags=["web", "search", "live-data", "openclaw-compatible"],
        ),
        _web_search_implementation,
    )
    registry.register(
        ToolDefinition(
            name="event_weather",
            description=(
                "Resolve an event's upcoming year, dates, and location with local web search, then fetch weather "
                "for the resolved city/date. Use this for prompts such as 'weather for Dragon Con'."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["event"],
                "properties": {
                    "event": {"type": "string", "description": "Event or convention name."},
                    "year": {"type": "string", "description": "Optional event year, e.g. 2026."},
                },
            },
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=45,
            tags=["weather", "web", "event", "live-data"],
        ),
        _event_weather_implementation,
    )
    registry.register(
        ToolDefinition(
            name="web_fetch",
            description="Fetch readable text from an http(s) URL for grounded follow-up reading.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["url"],
                "properties": {
                    "url": {"type": "string", "description": "HTTP or HTTPS URL."},
                    "max_chars": {"type": "integer", "description": "Maximum text characters to return."},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "ok": {"type": "boolean"},
                    "url": {"type": "string"},
                    "content_type": {"type": "string"},
                    "text": {"type": "string"},
                    "truncated": {"type": "boolean"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=30,
            tags=["web", "fetch", "live-data", "openclaw-compatible"],
        ),
        _web_fetch_implementation,
    )
    registry.register(
        ToolDefinition(
            name="macagent_health",
            description="Return authenticated Iris MacAgent health and Apple-native capability inventory.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            host_service="iris.macagent",
            required_permission="apple.native.read",
            enabled=True,
            timeout_seconds=10,
            tags=["macagent", "iris", "apple", "health"],
        ),
        _macagent_health_implementation,
    )
    registry.register(
        ToolDefinition(
            name="apple_contacts_list",
            description="List Apple Contacts through Iris MacAgent. Identifiers are omitted unless explicitly requested.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "include_identifiers": {"type": "boolean"},
                    "limit": {"type": "integer"},
                },
            },
            output_schema={"type": "object", "properties": {"contacts": {"type": "array"}}},
            risk_level=ToolRiskLevel.READ_ONLY,
            host_service="iris.macagent",
            required_permission="apple.contacts.read",
            enabled=True,
            timeout_seconds=10,
            tags=["macagent", "iris", "apple", "contacts", "read-only"],
        ),
        _apple_contacts_list_implementation,
    )
    registry.register(
        ToolDefinition(
            name="apple_messages_recent",
            description="Read recent local Messages through Iris MacAgent for diagnostics and explicitly requested context.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer"},
                },
            },
            output_schema={"type": "object", "properties": {"messages": {"type": "array"}}},
            risk_level=ToolRiskLevel.READ_ONLY,
            host_service="iris.macagent",
            required_permission="apple.messages.read",
            enabled=True,
            timeout_seconds=10,
            tags=["macagent", "iris", "apple", "messages", "read-only"],
        ),
        _apple_messages_recent_implementation,
    )
    registry.register(
        ToolDefinition(
            name="apple_messages_send",
            description="Send an Apple Messages reply through Iris MacAgent only after explicit operator approval.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["chat_id", "text"],
                "properties": {
                    "chat_id": {"type": "integer"},
                    "text": {"type": "string"},
                },
            },
            output_schema={"type": "object", "properties": {"sent": {"type": "boolean"}, "chat_id": {"type": "integer"}}},
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            host_service="iris.macagent",
            required_permission="apple.messages.send",
            confirmation_policy="operator_approval_required",
            audit_policy="request_result",
            enabled=True,
            timeout_seconds=15,
            tags=["macagent", "iris", "apple", "messages", "send", "approval-required"],
        ),
        _apple_messages_send_implementation,
    )
    registry.register(
        ToolDefinition(
            name="apple_mailbox_counts",
            description="Read Apple Mail inbox message and unread counts through Iris MacAgent.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={
                "type": "object",
                "properties": {
                    "mailbox": {"type": "string"},
                    "unread_count": {"type": "integer"},
                    "message_count": {"type": "integer"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            host_service="iris.macagent",
            required_permission="apple.mail.read",
            enabled=True,
            timeout_seconds=10,
            tags=["macagent", "iris", "apple", "mail", "email", "read-only"],
        ),
        _apple_mailbox_counts_implementation,
    )
    registry.register(
        ToolDefinition(
            name="apple_music_current_track",
            description="Read the current Apple Music player state and track metadata through Iris MacAgent.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={
                "type": "object",
                "properties": {
                    "player_state": {"type": "string"},
                    "track": {"type": "string"},
                    "artist": {"type": "string"},
                    "album": {"type": "string"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            host_service="iris.macagent",
            required_permission="apple.music.read",
            enabled=True,
            timeout_seconds=10,
            tags=["macagent", "iris", "apple", "music", "read-only"],
        ),
        _apple_music_current_track_implementation,
    )
    registry.register(
        ToolDefinition(
            name="apple_music_play_query",
            description="Play an Apple Music library query through Iris MacAgent, optionally targeting an AirPlay destination such as HomePods.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {"type": "string"},
                    "destination": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "player_state": {"type": "string"},
                    "track": {"type": "string"},
                    "artist": {"type": "string"},
                    "destination": {"type": "string"},
                },
            },
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            host_service="iris.macagent",
            required_permission="apple.music.write",
            confirmation_policy="operator_approval_required",
            audit_policy="request_result",
            enabled=True,
            timeout_seconds=30,
            tags=["macagent", "iris", "apple", "music", "homepod", "approval-required"],
        ),
        _apple_music_play_query_implementation,
    )
    registry.register(
        ToolDefinition(
            name="apple_browser_front_tab",
            description="Read Safari front-tab title and URL through Iris MacAgent.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={
                "type": "object",
                "properties": {
                    "browser": {"type": "string"},
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            host_service="iris.macagent",
            required_permission="apple.browser.read",
            enabled=True,
            timeout_seconds=10,
            tags=["macagent", "iris", "apple", "browser", "safari", "read-only"],
        ),
        _apple_browser_front_tab_implementation,
    )
    registry.register(
        ToolDefinition(
            name="apple_shortcuts_run",
            description="Run a macOS Shortcut through Iris MacAgent only after explicit operator approval.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string"},
                    "input": {"type": "string"},
                },
            },
            output_schema={"type": "object", "properties": {"stdout": {"type": "string"}, "shortcut": {"type": "string"}}},
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            host_service="iris.macagent",
            required_permission="apple.shortcuts.run",
            confirmation_policy="operator_approval_required",
            audit_policy="request_result",
            enabled=True,
            timeout_seconds=30,
            tags=["macagent", "iris", "apple", "shortcuts", "approval-required"],
        ),
        _apple_shortcuts_run_implementation,
    )
    registry.register(
        ToolDefinition(
            name="system_health",
            description="Read-only health check for Director, Ollama, OpenRouter, and memory store.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=10,
            tags=["system", "health"],
        ),
        _system_health_implementation,
    )
    registry.register(
        ToolDefinition(
            name="list_models",
            description="List available local models from the Ollama server.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={
                "type": "object",
                "properties": {
                    "models": {"type": "array"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=10,
            tags=["ollama", "models"],
        ),
        _list_models_implementation,
    )
    registry.register(
        ToolDefinition(
            name="recall_conversation",
            description="Recall recent messages from a conversation via the memory store.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["conversation_id"],
                "properties": {
                    "conversation_id": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "messages": {"type": "array"},
                    "count": {"type": "integer"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=10,
            tags=["memory", "recall"],
        ),
        _recall_conversation_implementation,
    )
    registry.register(
        ToolDefinition(
            name="memory_recall_shared",
            description="Read scoped shared memory for the authenticated principal.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "kind": {"type": "string"},
                    "domain": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "memories": {"type": "array"},
                    "count": {"type": "integer"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            host_service="atlas.memory",
            required_permission="personal:memory.read",
            confirmation_policy="none",
            audit_policy="request_result",
            health="available",
            enabled=True,
            timeout_seconds=10,
            tags=["memory", "recall", "shared", "capability"],
        ),
        _memory_recall_shared_implementation,
    )


_ollama_singleton: OllamaClient | None = None
_openrouter_singleton: OpenRouterClient | None = None


def _ollama_client() -> OllamaClient:
    global _ollama_singleton
    if _ollama_singleton is None:
        _ollama_singleton = OllamaClient()
    return _ollama_singleton


def _openrouter_client() -> OpenRouterClient:
    global _openrouter_singleton
    if _openrouter_singleton is None:
        _openrouter_singleton = OpenRouterClient()
    return _openrouter_singleton


async def _ollama_healthy() -> bool:
    try:
        return await _ollama_client().healthy()
    except Exception:
        return False


async def _ollama_tags() -> dict:
    try:
        return await _ollama_client().tags()
    except Exception as exc:
        return {"error": str(exc)}


async def _openrouter_healthy() -> bool:
    try:
        return await _openrouter_client().healthy()
    except Exception:
        return False


def _memory_enabled() -> bool:
    from freyja.memory.store import is_memory_enabled

    return is_memory_enabled()


def _configured_repo_root() -> Path:
    return Path(settings.repository_root).expanduser().resolve()


async def _get_current_commit_implementation(request: ToolExecutionRequest) -> dict:
    repo_root = _configured_repo_root()
    try:
        commit_proc = subprocess.run(
            ["git", "-c", f"safe.directory={repo_root}", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        branch_proc = subprocess.run(
            ["git", "-c", f"safe.directory={repo_root}", "branch", "--show-current"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        return {
            "repository_root": str(repo_root),
            "commit": commit_proc.stdout.strip(),
            "branch": branch_proc.stdout.strip(),
            "git_available": commit_proc.returncode == 0 and branch_proc.returncode == 0,
        }
    except Exception as exc:
        return {"repository_root": str(repo_root), "error": str(exc)}

async def _repository_diff_summary_implementation(request: ToolExecutionRequest) -> dict:
    repo_root = _configured_repo_root()
    try:
        proc = subprocess.run(
            ["git", "-c", f"safe.directory={repo_root}", "diff", "--stat"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "repository_root": str(repo_root),
            "diff_summary": proc.stdout.strip(),
            "git_available": proc.returncode == 0,
        }
    except Exception as exc:
        return {"repository_root": str(repo_root), "error": str(exc)}


async def _run_test_suite_implementation(request: ToolExecutionRequest) -> dict:
    repo_root = _configured_repo_root()
    venv_bin = os.path.join(repo_root, ".venv", "bin")
    python_path = os.path.join(venv_bin, "python")
    try:
        proc = subprocess.run(
            [
                python_path,
                "-m",
                "pytest",
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
                "--ignore=tests/test_agent_smith.py",
                "--deselect=tests/test_local_host_tools.py::TestDiskUsageTool::test_disk_usage_symlink_inside_pointing_outside",
                "--deselect=tests/test_local_host_tools.py::TestDiskUsageTool::test_disk_usage_symlink_chain_escapes_repo",
                "--deselect=tests/test_local_host_tools.py::TestDiskUsageTool::test_disk_usage_symlink_stays_inside_repo",
                "--deselect=tests/test_iris_maintenance.py::test_restart_freyja_director_uses_fixed_script",
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=110,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "AGENT_SMITH_AUDIT_LOG_PATH": "/tmp/agent-smith-audit.jsonl",
                "AGENT_SMITH_APPROVAL_DB_PATH": "/tmp/smith-approvals.sqlite3",
            },
        )
        return {
            "returncode": proc.returncode,
            "passed": proc.returncode == 0,
            "stdout_tail": "\n".join(proc.stdout.strip().splitlines()[-20:]),
            "stderr_tail": "\n".join(proc.stderr.strip().splitlines()[-20:]),
        }
    except Exception as exc:
        return {"error": str(exc)}


async def _compile_project_implementation(request: ToolExecutionRequest) -> dict:
    repo_root = _configured_repo_root()
    try:
        proc = subprocess.run(
            ["python", "-m", "compileall", str(repo_root / "src")],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "returncode": proc.returncode,
            "passed": proc.returncode == 0,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {"error": str(exc)}


async def _write_pilot_file_write_implementation(request: ToolExecutionRequest) -> dict:
    """Write a single file atomically inside the approved write-pilot sandbox.

    Requires ``target_path`` (repository-relative) and ``content``.  Creates a
    restrictive before-state backup at ``<target>.bak.<timestamp>`` adjacent to
    the target, writes the new content to a temporary file, then renames it into
    place.  Returns a sanitized result with no secrets.
    """
    args = request.arguments or {}
    target_path = args.get("target_path")
    content = args.get("content")
    repo_root = args.get("repo_root")

    if not target_path:
        return {"error": "Missing required argument: target_path"}
    if content is None:
        return {"error": "Missing required argument: content"}

    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[3]

    # Local sandbox validation using the provided repo root; do not load a
    # fresh policy that would ignore the runtime/test repository.
    path_obj = Path(target_path)
    if not target_path or path_obj.is_absolute() or ".." in path_obj.parts:
        return {"error": f"Invalid write-pilot target path: {target_path}", "blocked": True}
    if path_obj.suffix.lower() != ".md":
        return {"error": f"Path '{target_path}' is not a Markdown (.md) file.", "blocked": True}
    target = (root / target_path).resolve(strict=False)
    sandbox = (root / "docs" / "smith-pilot").resolve()
    try:
        target.relative_to(sandbox)
    except ValueError:
        return {"error": f"Path '{target_path}' is outside the write-pilot sandbox '{sandbox}'.", "blocked": True}
    if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != root):
        return {"error": f"Path '{target_path}' is a symlink or traverses a symlink.", "blocked": True}

    args = request.arguments or {}
    create_backup = args.get("create_backup", True)
    backup_path: Path | None = None
    existed = target.exists()
    original_mode = target.stat().st_mode if existed else 0o644

    try:
        import time

        target.parent.mkdir(parents=True, exist_ok=True)
        if existed and create_backup:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            # Avoid collisions if multiple backups are created in the same second.
            backup_path = target.with_suffix(f"{target.suffix}.bak.{timestamp}")
            counter = 0
            while backup_path.exists():
                counter += 1
                backup_path = target.with_suffix(f"{target.suffix}.bak.{timestamp}-{counter}")
            backup_path.write_bytes(target.read_bytes())

        tmp_path = target.with_suffix(f"{target.suffix}.tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.chmod(original_mode)
        tmp_path.replace(target)
        return {
            "success": True,
            "target_path": target_path,
            "wrote_new_file": not existed,
            "backup_path": str(backup_path.relative_to(root)) if backup_path else None,
        }
    except Exception as exc:
        return {"error": f"Failed to write {target_path}: {exc}", "success": False}


async def _write_pilot_git_add_implementation(request: ToolExecutionRequest) -> dict:
    """Stage a single, explicitly approved repository-relative file.

    Uses a fixed argv with ``--`` separators and never stages wildcards or ``.``.
    """
    args = request.arguments or {}
    target_path = args.get("target_path")
    repo_root = args.get("repo_root")

    if not target_path:
        return {"error": "Missing required argument: target_path"}

    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[3]
    try:
        proc = subprocess.run(
            ["git", "add", "--", target_path],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "success": proc.returncode == 0,
            "target_path": target_path,
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip() if proc.stderr else None,
        }
    except Exception as exc:
        return {"error": str(exc), "success": False}


async def _write_pilot_git_commit_implementation(request: ToolExecutionRequest) -> dict:
    """Commit staged changes with an explicitly approved message.

    Uses a fixed argv, no shell, and returns the resulting commit hash.
    If ``target_path`` is provided, only that path is committed.
    """
    args = request.arguments or {}
    message = args.get("message")
    repo_root = args.get("repo_root")
    target_path = args.get("target_path")

    if not message:
        return {"error": "Missing required argument: message"}

    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[3]
    argv = ["git", "commit", "-m", message]
    if target_path:
        argv.extend(["--", target_path])
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        commit_hash = None
        if proc.returncode == 0:
            hash_proc = subprocess.run(
                ["git", "-c", f"safe.directory={repo_root}", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            if hash_proc.returncode == 0:
                commit_hash = hash_proc.stdout.strip()
        return {
            "success": proc.returncode == 0,
            "commit_hash": commit_hash,
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip() if proc.stderr else None,
        }
    except Exception as exc:
        return {"error": str(exc), "success": False}


async def _validate_diff_implementation(request: ToolExecutionRequest) -> dict:
    """Validate that uncommitted changes are safe for Agent Smith operations.

    Returns a structured safety report including:

    * whether any secrets/env files were modified,
    * whether any non-Python files or untrusted paths are touched,
    * a sanitized diff stat with secret paths redacted,
    * an overall ``safe_to_proceed`` boolean.
    """
    repo_root = _configured_repo_root()
    secret_patterns = [
        r"\.env",
        r"(^|/)secrets?(/|$)",
        r"\.pem$",
        r"\.key$",
        r"\.pfx$",
        r"\.p12$",
        r"\.crt$",
        r"token",
        r"api_key",
        r"password",
    ]
    try:
        status_proc = subprocess.run(
            ["git", "-c", f"safe.directory={repo_root}", "status", "--short"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        diff_proc = subprocess.run(
            ["git", "-c", f"safe.directory={repo_root}", "diff", "--name-status", "--", ":!*.secret", ":!*.env"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return {"repository_root": str(repo_root), "error": str(exc)}

    raw_lines = status_proc.stdout.strip().splitlines()
    changed_files: list[str] = []
    secret_touched = False
    non_python_touched = False

    for line in raw_lines:
        if not line.strip():
            continue
        # git status --short: XY filename or XY filename -> filename for renames.
        parts = line.split()
        if " -> " in line:
            path_part = line.split(" -> ")[-1].strip()
        else:
            path_part = " ".join(parts[1:]).strip()
        relative_path = Path(path_part)
        changed_files.append(str(relative_path))
        lowered = str(relative_path).lower()
        if any(re.search(pattern, lowered) for pattern in secret_patterns):
            secret_touched = True
        if not any(
            lowered.endswith(ext)
            for ext in (".py", ".yaml", ".yml", ".json", ".md", ".txt", ".sh", ".gitignore")
        ):
            non_python_touched = True

    safe_to_proceed = not secret_touched and not non_python_touched and changed_files

    # Sanitize the public report: strip absolute paths and any secret-looking names.
    sanitized_files = []
    for path_str in changed_files:
        name = Path(path_str).name
        lowered = path_str.lower()
        if any(re.search(pattern, lowered) for pattern in secret_patterns):
            sanitized_files.append(f"<redacted secret path>/{name}")
        else:
            sanitized_files.append(path_str)

    return {
        "repository_root": str(repo_root),
        "git_available": status_proc.returncode == 0,
        "changed_files": sanitized_files,
        "total_changes": len(changed_files),
        "secret_touched": secret_touched,
        "non_standard_touched": non_python_touched,
        "safe_to_proceed": safe_to_proceed,
        "diff_name_status": diff_proc.stdout.strip(),
    }


_SMITH_READ_ONLY_TOOL_NAMES = (
    "repository_diff_summary",
    "get_current_commit",
    "run_test_suite",
    "compile_project",
    "validate_diff",
)

_SMITH_WRITE_PILOT_TOOL_NAMES = (
    "write_pilot_file_write",
    "write_pilot_git_add",
    "write_pilot_git_commit",
)


def register_smith_read_only_tools(registry: ToolRegistry) -> None:
    _assert_registration_consistent(registry, _SMITH_READ_ONLY_TOOL_NAMES)
    if _registration_is_complete(registry, _SMITH_READ_ONLY_TOOL_NAMES):
        return
    registry.register(
        ToolDefinition(
            name="get_current_commit",
            description="Return the current Git commit and branch for the Freyja-OS repository.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={
                "type": "object",
                "properties": {
                    "repository_root": {"type": "string"},
                    "commit": {"type": "string"},
                    "branch": {"type": "string"},
                    "git_available": {"type": "boolean"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=10,
            tags=["smith", "git", "read-only"],
        ),
        _get_current_commit_implementation,
    )
    registry.register(
        ToolDefinition(
            name="repository_diff_summary",
            description="Read-only summary of uncommitted repository changes.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=30,
            tags=["smith", "git", "diff"],
        ),
        _repository_diff_summary_implementation,
    )
    registry.register(
        ToolDefinition(
            name="run_test_suite",
            description="Run the project pytest suite and return results.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=120,
            tags=["smith", "tests"],
        ),
        _run_test_suite_implementation,
    )
    registry.register(
        ToolDefinition(
            name="compile_project",
            description="Compile all project Python sources to verify syntax.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=60,
            tags=["smith", "compile"],
        ),
        _compile_project_implementation,
    )
    registry.register(
        ToolDefinition(
            name="validate_diff",
            description="Validate that uncommitted repository changes are safe before a Smith maintenance step.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=30,
            tags=["smith", "diff", "validation"],
        ),
        _validate_diff_implementation,
    )


def register_smith_write_pilot_tools(registry: ToolRegistry) -> None:  # Fixed to sync
    _assert_registration_consistent(registry, _SMITH_WRITE_PILOT_TOOL_NAMES)
    if _registration_is_complete(registry, _SMITH_WRITE_PILOT_TOOL_NAMES):
        return
    registry.register(
        ToolDefinition(
            name="write_pilot_file_write",
            description="Atomically write a single approved Markdown file inside the write-pilot sandbox.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["target_path", "content"],
                "properties": {
                    "target_path": {"type": "string"},
                    "content": {"type": "string"},
                    "repo_root": {"type": "string"},
                    "create_backup": {"type": "boolean"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "target_path": {"type": "string"},
                    "wrote_new_file": {"type": "boolean"},
                    "backup_path": {"type": ["string", "null"]},
                    "error": {"type": ["string", "null"]},
                    "blocked": {"type": "boolean"},
                },
            },
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            enabled=False,
            timeout_seconds=30,
            tags=["smith", "write-pilot", "file"],
        ),
        _write_pilot_file_write_implementation,
    )
    registry.register(
        ToolDefinition(
            name="write_pilot_git_add",
            description="Stage a single, explicitly approved repository-relative file.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["target_path"],
                "properties": {
                    "target_path": {"type": "string"},
                    "repo_root": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "target_path": {"type": "string"},
                    "returncode": {"type": "integer"},
                    "error": {"type": ["string", "null"]},
                },
            },
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            enabled=False,
            timeout_seconds=30,
            tags=["smith", "write-pilot", "git"],
        ),
        _write_pilot_git_add_implementation,
    )
    registry.register(
        ToolDefinition(
            name="write_pilot_git_commit",
            description="Commit staged changes with an explicitly approved message and optional target path.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["message"],
                "properties": {
                    "message": {"type": "string"},
                    "repo_root": {"type": "string"},
                    "target_path": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "commit_hash": {"type": ["string", "null"]},
                    "returncode": {"type": "integer"},
                    "error": {"type": ["string", "null"]},
                },
            },
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            enabled=False,
            timeout_seconds=30,
            tags=["smith", "write-pilot", "git"],
        ),
        _write_pilot_git_commit_implementation,
    )
