import logging
import datetime as _datetime
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from freyja.config import settings
from freyja.main import app
from freyja.memory.models import AppendMessageRequest, CreateConversationRequest
from freyja.memory.store import MemoryStore, set_store
from freyja.tools.builtin import register_builtin_tools
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import DisabledToolRegistry, ToolRegistry, get_registry, set_registry


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> ToolRegistry:
    monkeypatch.setattr(settings, "tools_enabled", True)
    r = ToolRegistry(default_timeout_seconds=5, audit_enabled=False)
    set_registry(r)
    yield r
    set_registry(None)


@pytest.fixture
def disabled_registry(monkeypatch: pytest.MonkeyPatch) -> DisabledToolRegistry:
    monkeypatch.setattr(settings, "tools_enabled", False)
    d = DisabledToolRegistry()
    set_registry(d)
    yield d
    set_registry(None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_register_and_list_tools(registry: ToolRegistry) -> None:
    definition = ToolDefinition(
        name="echo",
        description="Echoes arguments",
        input_schema={"type": "object", "properties": {"value": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"value": {"type": "string"}}},
    )

    async def echo(request: ToolExecutionRequest) -> dict:
        return {"value": request.arguments.get("value")}

    registry.register(definition, echo)
    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "echo"


def test_register_duplicate_rejected(registry: ToolRegistry) -> None:
    definition = ToolDefinition(name="unique", description="One only")

    async def noop(request: ToolExecutionRequest) -> dict:
        return {}

    registry.register(definition, noop)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition, noop)


def test_unregister(registry: ToolRegistry) -> None:
    definition = ToolDefinition(name="tmp", description="Temporary")

    async def noop(request: ToolExecutionRequest) -> dict:
        return {}

    registry.register(definition, noop)
    assert registry.unregister("tmp") is True
    assert registry.unregister("tmp") is False
    assert registry.get_tool("tmp") is None


def test_discovery(registry: ToolRegistry) -> None:
    assert registry.list_tools() == []
    register_builtin_tools(registry)
    names = {t.name for t in registry.list_tools()}
    assert names == {
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
    }


def test_disable_tool_rejects_execution(registry: ToolRegistry) -> None:
    definition = ToolDefinition(name="gate", description="Gated")

    async def noop(request: ToolExecutionRequest) -> dict:
        return {}

    registry.register(definition, noop)
    registry.set_enabled("gate", False)
    result = asyncio_run(registry.execute(ToolExecutionRequest(tool_name="gate")))
    assert result.success is False
    assert result.error_code == "tool_disabled"
    assert result.public_error_message == "Tool is currently disabled."


def test_unknown_tool_rejected(registry: ToolRegistry) -> None:
    result = asyncio_run(registry.execute(ToolExecutionRequest(tool_name="missing")))
    assert result.success is False
    assert result.error_code == "tool_not_found"
    assert result.public_error_message == "Tool not found."


def test_input_validation(registry: ToolRegistry) -> None:
    definition = ToolDefinition(
        name="greet",
        description="Greets a user",
        input_schema={
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        },
    )

    async def greet(request: ToolExecutionRequest) -> dict:
        return {"message": f"Hello, {request.arguments['name']}"}

    registry.register(definition, greet)
    result = asyncio_run(registry.execute(ToolExecutionRequest(tool_name="greet")))
    assert result.success is False
    assert result.error_code == "validation_error"
    assert "Missing required argument" in result.public_error_message

    result = asyncio_run(
        registry.execute(ToolExecutionRequest(tool_name="greet", arguments={"name": 123}))
    )
    assert result.success is False
    assert "type string" in result.public_error_message


def test_enum_normalization_safe_alias(registry: ToolRegistry) -> None:
    definition = ToolDefinition(
        name="weather_units",
        description="Normalizes weather units",
        input_schema={
            "type": "object",
            "required": ["unit"],
            "properties": {"unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}},
        },
    )

    async def weather_units(request: ToolExecutionRequest) -> dict:
        return {"unit": request.arguments["unit"]}

    registry.register(definition, weather_units)
    result = asyncio_run(
        registry.execute(ToolExecutionRequest(tool_name="weather_units", arguments={"unit": "F"}))
    )
    assert result.success is True
    assert result.output == {"unit": "fahrenheit"}


def test_invalid_enum_rejected(registry: ToolRegistry) -> None:
    definition = ToolDefinition(
        name="weather_units_invalid",
        description="Rejects bad units",
        input_schema={
            "type": "object",
            "required": ["unit"],
            "properties": {"unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}},
        },
    )

    async def noop(request: ToolExecutionRequest) -> dict:
        return {}

    registry.register(definition, noop)
    result = asyncio_run(
        registry.execute(ToolExecutionRequest(tool_name="weather_units_invalid", arguments={"unit": "kelvin"}))
    )
    assert result.success is False
    assert result.error_code == "validation_error"
    assert "must be one of" in result.public_error_message


def test_ambiguous_enum_alias_rejected(registry: ToolRegistry) -> None:
    definition = ToolDefinition(
        name="ambiguous_units",
        description="Rejects ambiguous aliases",
        input_schema={
            "type": "object",
            "required": ["unit"],
            "properties": {"unit": {"type": "string", "enum": ["fahrenheit", "forecast"]}},
        },
    )

    async def noop(request: ToolExecutionRequest) -> dict:
        return {}

    registry.register(definition, noop)
    result = asyncio_run(
        registry.execute(ToolExecutionRequest(tool_name="ambiguous_units", arguments={"unit": "F"}))
    )
    assert result.success is False
    assert result.error_code == "validation_error"
    assert "ambiguous" in result.public_error_message


def test_successful_execution(registry: ToolRegistry) -> None:
    definition = ToolDefinition(
        name="add",
        description="Adds two numbers",
        input_schema={
            "type": "object",
            "required": ["a", "b"],
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        },
    )

    async def add(request: ToolExecutionRequest) -> dict:
        return {"sum": request.arguments["a"] + request.arguments["b"]}

    registry.register(definition, add)
    result = asyncio_run(
        registry.execute(ToolExecutionRequest(tool_name="add", arguments={"a": 2, "b": 3}))
    )
    assert result.success is True
    assert result.output == {"sum": 5}
    assert result.request_id


def test_timeout_handling(registry: ToolRegistry) -> None:
    definition = ToolDefinition(
        name="slow",
        description="Sleeps",
        timeout_seconds=0,
    )

    async def slow(request: ToolExecutionRequest) -> dict:
        import asyncio

        await asyncio.sleep(5)
        return {}

    registry.register(definition, slow)
    result = asyncio_run(registry.execute(ToolExecutionRequest(tool_name="slow")))
    assert result.success is False
    assert result.error_code == "tool_timeout"
    assert result.public_error_message == "Tool execution timed out."


def test_exception_isolation(registry: ToolRegistry) -> None:
    definition = ToolDefinition(name="boom", description="Raises")

    async def boom(request: ToolExecutionRequest) -> dict:
        raise RuntimeError("secret internals")

    registry.register(definition, boom)
    result = asyncio_run(registry.execute(ToolExecutionRequest(tool_name="boom")))
    assert result.success is False
    assert result.error_code == "tool_error"
    assert "secret internals" not in result.public_error_message
    assert result.public_error_message == "Tool execution failed."


def test_request_id_propagation(registry: ToolRegistry) -> None:
    definition = ToolDefinition(name="id_echo", description="Echoes request id")

    async def id_echo(request: ToolExecutionRequest) -> dict:
        return {"id": request.request_id}

    registry.register(definition, id_echo)
    request = ToolExecutionRequest(tool_name="id_echo", request_id="req-abc-123")
    result = asyncio_run(registry.execute(request))
    assert result.request_id == "req-abc-123"


def test_audit_redaction(registry: ToolRegistry, caplog: pytest.LogCaptureFixture) -> None:
    registry._audit_enabled = True

    definition = ToolDefinition(name="leak", description="Leaks secrets")

    async def leak(request: ToolExecutionRequest) -> dict:
        return {"secret": request.arguments.get("secret")}

    registry.register(definition, leak)
    with caplog.at_level(logging.INFO, logger="freyja.tools.registry"):
        result = asyncio_run(
            registry.execute(
                ToolExecutionRequest(
                    tool_name="leak",
                    arguments={"secret": "sk-12345", "normal": "hello"},
                )
            )
        )
    assert result.success is True
    assert result.output["secret"] == "sk-12345"
    records = [r for r in caplog.records if r.message.startswith("{")]
    assert records
    log_text = records[0].message
    assert "sk-12345" not in log_text
    assert "<redacted>" in log_text
    assert "hello" in log_text


def test_disabled_registry_rejects_all(disabled_registry: DisabledToolRegistry) -> None:
    result = asyncio_run(disabled_registry.execute(ToolExecutionRequest(tool_name="anything")))
    assert result.success is False
    assert result.error_code == "tool_disabled"
    assert result.public_error_message == "Tool execution is globally disabled."


def test_builtin_system_health(registry: ToolRegistry) -> None:
    register_builtin_tools(registry)
    with patch("freyja.tools.builtin._ollama_healthy", return_value=True), patch(
        "freyja.tools.builtin._openrouter_healthy", return_value=True
    ):
        result = asyncio_run(registry.execute(ToolExecutionRequest(tool_name="system_health")))
    assert result.success is True
    assert "director" in result.output
    assert "ollama" in result.output
    assert "openrouter" in result.output
    assert "memory" in result.output


def test_builtin_list_models(registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    register_builtin_tools(registry)
    with patch(
        "freyja.tools.builtin._ollama_tags",
        return_value={"models": [{"name": "qwen2.5:1.5b"}]},
    ):
        result = asyncio_run(registry.execute(ToolExecutionRequest(tool_name="list_models")))
    assert result.success is True
    assert result.output["models"] == [{"name": "qwen2.5:1.5b"}]


def test_builtin_recall_conversation(registry: ToolRegistry, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from freyja.memory.store import is_memory_enabled

    monkeypatch.setattr(settings, "memory_enabled", True)
    monkeypatch.setattr(settings, "memory_database_path", str(tmp_path / "tools_recall.db"))
    store = MemoryStore(database_path=str(tmp_path / "tools_recall.db"))
    store.initialize()
    set_store(store)
    store.create_conversation(CreateConversationRequest(conversation_id="conv-1"))
    store.append_message(
        AppendMessageRequest(
            conversation_id="conv-1", role="user", content="hello", provider="ollama"
        )
    )
    monkeypatch.setattr(settings, "tools_default_timeout_seconds", 5)
    register_builtin_tools(registry)
    try:
        result = asyncio_run(
            registry.execute(
                ToolExecutionRequest(
                    tool_name="recall_conversation",
                    arguments={"conversation_id": "conv-1", "limit": 10},
                )
            )
        )
    finally:
        set_store(None)
    assert result.success is True
    assert result.output["conversation_id"] == "conv-1"
    assert result.output["count"] == 1


def test_api_list_tools(client: TestClient, registry: ToolRegistry) -> None:
    register_builtin_tools(registry)
    response = client.get("/tools")
    assert response.status_code == 200
    tools = response.json()["tools"]
    assert len(tools) == 37


def test_api_get_tool(client: TestClient, registry: ToolRegistry) -> None:
    register_builtin_tools(registry)
    response = client.get("/tools/system_health")
    assert response.status_code == 200
    assert response.json()["name"] == "system_health"

    response = client.get("/tools/nonexistent")
    assert response.status_code == 404


def test_api_execute_tool(client: TestClient, registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    register_builtin_tools(registry)
    with patch("freyja.tools.builtin._ollama_healthy", return_value=True), patch(
        "freyja.tools.builtin._openrouter_healthy", return_value=True
    ):
        response = client.post("/tools/system_health/execute")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["tool_name"] == "system_health"


def test_api_execute_unknown_tool(client: TestClient, registry: ToolRegistry) -> None:
    response = client.post("/tools/unknown/execute")
    assert response.status_code == 400
    assert response.json()["detail"] == "Tool not found."


def test_api_execute_disabled_tool(client: TestClient, registry: ToolRegistry) -> None:
    register_builtin_tools(registry)
    registry.set_enabled("system_health", False)
    response = client.post("/tools/system_health/execute")
    assert response.status_code == 400
    assert response.json()["detail"] == "Tool is currently disabled."


def test_builtin_get_weather_safe_fallback(registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "weather_tool_enabled", False)
    register_builtin_tools(registry)
    result = asyncio_run(
        registry.execute(
            ToolExecutionRequest(
                tool_name="get_weather",
                arguments={"location": "Aiken, SC", "request_type": "current"},
            )
        )
    )
    assert result.success is True
    assert result.output["live_data_available"] is False
    assert "not configured" in result.output["summary"].lower()


def test_builtin_get_weather_bad_request_type(registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "weather_tool_enabled", True)
    register_builtin_tools(registry)
    result = asyncio_run(
        registry.execute(
            ToolExecutionRequest(
                tool_name="get_weather",
                arguments={"location": "Aiken, SC", "request_type": "next-month"},
            )
        )
    )
    assert result.success is False
    assert result.error_code == "validation_error"
    assert "request_type" in result.public_error_message


def test_builtin_get_weather_accepts_forecast_date_alias(registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "weather_tool_enabled", True)
    register_builtin_tools(registry)

    captured: dict[str, Any] = {}

    async def fake_get_weather(*, location, request_type, target_date=None, target_label=""):
        captured.update(
            {
                "location": location,
                "request_type": request_type.value,
                "target_date": target_date.isoformat() if target_date else None,
                "target_label": target_label,
            }
        )
        return {"live_data_available": True, "success": True}

    with patch("freyja.tools.builtin.get_weather", side_effect=fake_get_weather):
        result = asyncio_run(
            registry.execute(
                ToolExecutionRequest(
                    tool_name="get_weather",
                    arguments={
                        "location": "Atlanta, GA",
                        "request_type": "forecast",
                        "forecast_date": "2026-09-05",
                        "target_label": "Dragon Con",
                    },
                )
            )
        )

    assert result.success is True
    assert captured == {
        "location": "Atlanta, GA",
        "request_type": "forecast",
        "target_date": "2026-09-05",
        "target_label": "Dragon Con",
    }


def test_builtin_get_weather_provider_500(registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    """A provider error during geocoding returns a safe, sanitized response."""
    monkeypatch.setattr(settings, "weather_tool_enabled", True)
    register_builtin_tools(registry)
    import httpx

    def _bad_request(*args, **kwargs):
        url = str(args[0]) if args else kwargs.get("url", "")
        request = httpx.Request("GET", url)
        raise httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=request,
            response=httpx.Response(500, text="Internal Server Error", request=request),
        )

    with patch("httpx.AsyncClient.get", side_effect=_bad_request):
        result = asyncio_run(
            registry.execute(
                ToolExecutionRequest(
                    tool_name="get_weather",
                    arguments={"location": "Aiken, SC", "request_type": "current"},
                )
            )
        )
    assert result.success is True
    assert result.output["live_data_available"] is False
    assert "location not found" in result.output["summary"].lower()


def _openmeteo_geo_response() -> dict[str, Any]:
    return {
        "results": [
            {
                "id": 456123,
                "name": "Aiken",
                "latitude": 33.559,
                "longitude": -81.722,
                "admin1": "South Carolina",
                "country": "United States",
            }
        ]
    }


def _openmeteo_forecast_response(target_iso: str) -> dict[str, Any]:
    return {
        "latitude": 33.56,
        "longitude": -81.72,
        "daily": {
            "time": [target_iso],
            "weather_code": [0],
            "temperature_2m_max": [75.0],
            "temperature_2m_min": [58.0],
            "relative_humidity_2m_mean": [60],
        },
    }


def _openmeteo_current_response() -> dict[str, Any]:
    return {
        "latitude": 33.56,
        "longitude": -81.72,
        "current": {
            "time": f"{_datetime.date.today().isoformat()}T14:00",
            "temperature_2m": 72.5,
            "relative_humidity_2m": 55,
            "apparent_temperature": 74.0,
            "weather_code": 1,
            "wind_speed_10m": 5.2,
        },
    }


def test_builtin_get_weather_forecast_hits_forecast_endpoint(registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "weather_tool_enabled", True)
    register_builtin_tools(registry)

    captured_urls: list[str] = []
    import httpx

    def _capture(*args, **kwargs):
        url = str(args[0]) if args else kwargs.get("url", "")
        captured_urls.append(url)
        request = httpx.Request("GET", url)
        if "geocoding-api" in url:
            return httpx.Response(200, json=_openmeteo_geo_response(), request=request)
        target = kwargs.get("params", {}).get("forecast_days")
        assert target is not None
        return httpx.Response(200, json=_openmeteo_forecast_response(target_date.isoformat()), request=request)

    today = _datetime.date.today()
    target_date = today + _datetime.timedelta(days=1)
    monkeypatch.setattr("freyja.tools.weather._today", lambda: today)

    with patch("httpx.AsyncClient.get", side_effect=_capture):
        result = asyncio_run(
            registry.execute(
                ToolExecutionRequest(
                    tool_name="get_weather",
                    arguments={
                        "location": "Aiken, SC",
                        "request_type": "forecast",
                        "target_date": target_date.isoformat(),
                        "target_label": "tomorrow",
                    },
                )
            )
        )
    assert result.success is True
    assert result.output["live_data_available"] is True
    assert "forecast" in str(captured_urls)
    assert any("api.open-meteo.com/v1/forecast" in url for url in captured_urls)
    assert result.output["request_type"] == "forecast"
    assert result.output["target_label"] == "tomorrow"
    assert result.output["high_f"] == 75.0


def test_builtin_get_weather_current_hits_current_endpoint(registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "weather_tool_enabled", True)
    register_builtin_tools(registry)

    captured_urls: list[str] = []
    import httpx

    def _capture(*args, **kwargs):
        url = str(args[0]) if args else kwargs.get("url", "")
        captured_urls.append(url)
        request = httpx.Request("GET", url)
        if "geocoding-api" in url:
            return httpx.Response(200, json=_openmeteo_geo_response(), request=request)
        return httpx.Response(200, json=_openmeteo_current_response(), request=request)

    with patch("httpx.AsyncClient.get", side_effect=_capture):
        result = asyncio_run(
            registry.execute(
                ToolExecutionRequest(
                    tool_name="get_weather",
                    arguments={"location": "Aiken, SC", "request_type": "current"},
                )
            )
        )
    assert result.success is True
    assert result.output["live_data_available"] is True
    assert result.output["request_type"] == "current"
    assert any("api.open-meteo.com/v1/forecast" in url for url in captured_urls)
    assert result.output["temperature_f"] == 72.5


def test_builtin_get_weather_unknown_place(registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "weather_tool_enabled", True)
    register_builtin_tools(registry)
    import httpx

    def _empty_geo(*args, **kwargs):
        url = str(args[0]) if args else kwargs.get("url", "")
        request = httpx.Request("GET", url)
        return httpx.Response(200, json={"results": None}, request=request)

    with patch("httpx.AsyncClient.get", side_effect=_empty_geo):
        result = asyncio_run(
            registry.execute(
                ToolExecutionRequest(
                    tool_name="get_weather",
                    arguments={"location": "Xylophoneburg", "request_type": "current"},
                )
            )
        )
    assert result.success is True
    assert result.output["live_data_available"] is False
    assert "location not found" in result.output["summary"].lower()


def test_builtin_get_weather_unsupported_future_date(registry: ToolRegistry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "weather_tool_enabled", True)
    register_builtin_tools(registry)

    def _capture(*args, **kwargs):
        import httpx
        url = str(args[0]) if args else kwargs.get("url", "")
        request = httpx.Request("GET", url)
        if "geocoding-api" in url:
            return httpx.Response(200, json=_openmeteo_geo_response(), request=request)
        return httpx.Response(200, json=_openmeteo_forecast_response(target_date.isoformat()), request=request)

    today = _datetime.date.today()
    target = today + _datetime.timedelta(days=8)
    target_date = today + _datetime.timedelta(days=1)
    monkeypatch.setattr("freyja.tools.weather._today", lambda: today)

    with patch("httpx.AsyncClient.get", side_effect=_capture):
        result = asyncio_run(
            registry.execute(
                ToolExecutionRequest(
                    tool_name="get_weather",
                    arguments={
                        "location": "Aiken, SC",
                        "request_type": "forecast",
                        "target_date": target.isoformat(),
                        "target_label": "christmas",
                    },
                )
            )
        )
    assert result.success is True
    assert result.output["live_data_available"] is False
    assert "outside supported range" in result.output["summary"].lower()


def test_api_execute_validation_error(client: TestClient, registry: ToolRegistry) -> None:
    register_builtin_tools(registry)
    response = client.post(
        "/tools/recall_conversation/execute",
        json={"arguments": {"limit": "not-an-int"}},
    )
    assert response.status_code == 400
    assert "Missing required argument" in response.json()["detail"]


def test_home_assistant_read_requires_canonical_principal(registry: ToolRegistry) -> None:
    register_builtin_tools(registry)
    result = asyncio_run(
        registry.execute(
            ToolExecutionRequest(
                tool_name="home_assistant_read_state",
                arguments={"entity_id": "light.downstairs"},
            )
        )
    )
    assert result.success is False
    assert result.error_code == "authorization_denied"


def test_home_assistant_read_allows_director_authorized_joe(registry: ToolRegistry) -> None:
    register_builtin_tools(registry)
    result = asyncio_run(
        registry.execute(
            ToolExecutionRequest(
                tool_name="home_assistant_read_state",
                arguments={"entity_id": "light.downstairs"},
                metadata={
                    "director_authorized": True,
                    "memory_principal": {
                        "client_type": "imessage",
                        "client_subject": "family-member:abc",
                    },
                    "person": {"person_id": "joe"},
                },
            )
        )
    )
    assert result.success is True
    assert result.output["state"] == "on"


@pytest.mark.parametrize(
    ("person_id", "permission"),
    [
        ("liam", "household:home.read"),
        ("jenna", "household:home.read"),
        ("liam", "household:calendar.read"),
        ("jenna", "household:calendar.read"),
        ("liam", "personal:memory.read"),
        ("jenna", "personal:memory.read"),
    ],
)
def test_household_authorization_uses_configured_family_agents(
    registry: ToolRegistry,
    person_id: str,
    permission: str,
) -> None:
    definition = ToolDefinition(name="authorized", description="Authorized", required_permission=permission)
    request = ToolExecutionRequest(
        tool_name="authorized",
        metadata={
            "director_authorized": True,
            "memory_principal": {
                "client_type": "imessage",
                "client_subject": f"agent:{person_id}",
            },
            "person": {"person_id": person_id},
        },
    )

    decision = registry.authorize(definition, request)

    assert decision.allowed is True


@pytest.mark.parametrize(
    ("person_id", "permission"),
    [
        ("liam", "household:home.control"),
        ("jenna", "household:home.control"),
        ("liam", "household:calendar.write"),
        ("jenna", "household:calendar.write"),
    ],
)
def test_household_write_authorization_accepts_configured_family_agents_with_approval(
    registry: ToolRegistry,
    person_id: str,
    permission: str,
) -> None:
    definition = ToolDefinition(name="authorized", description="Authorized", required_permission=permission)
    request = ToolExecutionRequest(
        tool_name="authorized",
        metadata={
            "director_authorized": True,
            "approval_granted": True,
            "memory_principal": {
                "client_type": "imessage",
                "client_subject": f"agent:{person_id}",
            },
            "person": {"person_id": person_id},
        },
    )

    decision = registry.authorize(definition, request)

    assert decision.allowed is True


def test_home_assistant_list_states_exposes_fixture_sensors_for_household_principal(
    registry: ToolRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "home_assistant_state_fixture",
        '{"sensor.kitchen_temperature":"72","light.downstairs":"on"}',
    )
    register_builtin_tools(registry)
    result = asyncio_run(
        registry.execute(
            ToolExecutionRequest(
                tool_name="home_assistant_list_states",
                arguments={"domain": "sensor"},
                metadata={
                    "director_authorized": True,
                    "memory_principal": {
                        "client_type": "imessage",
                        "client_subject": "family-member:abc",
                    },
                    "person": {"person_id": "joe"},
                },
            )
        )
    )
    assert result.success is True
    assert result.output["location"] == "Atlanta"
    assert result.output["count"] == 1
    assert result.output["entities"][0]["entity_id"] == "sensor.kitchen_temperature"


def test_home_assistant_inventory_changes_detects_added_and_removed_entities(
    registry: ToolRegistry,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(settings, "home_assistant_inventory_snapshot_path", str(tmp_path / "ha-inventory.json"))
    monkeypatch.setattr(
        settings,
        "home_assistant_state_fixture",
        '{"sensor.kitchen_temperature":"72","light.downstairs":"on"}',
    )
    register_builtin_tools(registry)
    metadata = {
        "director_authorized": True,
        "memory_principal": {
            "client_type": "imessage",
            "client_subject": "family-member:abc",
        },
        "person": {"person_id": "joe"},
    }
    baseline = asyncio_run(
        registry.execute(
            ToolExecutionRequest(
                tool_name="home_assistant_inventory_changes",
                arguments={"include_all": True},
                metadata=metadata,
            )
        )
    )
    assert baseline.success is True
    assert baseline.output["baseline_available"] is False
    assert baseline.output["current_count"] == 2

    monkeypatch.setattr(
        settings,
        "home_assistant_state_fixture",
        '{"sensor.kitchen_temperature":"72","sensor.front_door_battery":"88"}',
    )
    changed = asyncio_run(
        registry.execute(
            ToolExecutionRequest(
                tool_name="home_assistant_inventory_changes",
                arguments={"include_all": True},
                metadata=metadata,
            )
        )
    )
    assert changed.success is True
    assert changed.output["baseline_available"] is True
    assert [item["entity_id"] for item in changed.output["added"]] == ["sensor.front_door_battery"]
    assert [item["entity_id"] for item in changed.output["removed"]] == ["light.downstairs"]


def test_memory_recall_shared_requires_principal(registry: ToolRegistry) -> None:
    register_builtin_tools(registry)
    result = asyncio_run(
        registry.execute(
            ToolExecutionRequest(
                tool_name="memory_recall_shared",
                arguments={"limit": 5},
            )
        )
    )
    assert result.success is False
    assert result.error_code == "authorization_denied"


def test_home_assistant_control_requires_explicit_approval(registry: ToolRegistry) -> None:
    register_builtin_tools(registry)
    result = asyncio_run(
        registry.execute(
            ToolExecutionRequest(
                tool_name="home_assistant_control_state",
                arguments={"entity_id": "light.downstairs", "state": "off"},
                metadata={
                    "director_authorized": True,
                    "memory_principal": {
                        "client_type": "imessage",
                        "client_subject": "family-member:abc",
                    },
                    "person": {"person_id": "joe"},
                },
            )
        )
    )
    assert result.success is False
    assert result.error_code == "authorization_denied"


def test_apple_messages_send_requires_explicit_approval(registry: ToolRegistry) -> None:
    register_builtin_tools(registry)
    result = asyncio_run(
        registry.execute(
            ToolExecutionRequest(
                tool_name="apple_messages_send",
                arguments={"chat_id": 123, "text": "hello"},
                metadata={
                    "director_authorized": True,
                    "memory_principal": {
                        "client_type": "imessage",
                        "client_subject": "agent:cloyd-gibbler",
                    },
                    "person": {"person_id": "joe"},
                },
            )
        )
    )
    assert result.success is False
    assert result.error_code == "authorization_denied"


def test_apple_shortcuts_run_requires_explicit_approval(registry: ToolRegistry) -> None:
    register_builtin_tools(registry)
    result = asyncio_run(
        registry.execute(
            ToolExecutionRequest(
                tool_name="apple_shortcuts_run",
                arguments={"name": "Example"},
                metadata={
                    "director_authorized": True,
                    "memory_principal": {
                        "client_type": "imessage",
                        "client_subject": "agent:cloyd-gibbler",
                    },
                    "person": {"person_id": "joe"},
                },
            )
        )
    )
    assert result.success is False
    assert result.error_code == "authorization_denied"


def test_home_assistant_control_rejects_non_light_domains_with_approval(registry: ToolRegistry) -> None:
    register_builtin_tools(registry)
    result = asyncio_run(
        registry.execute(
            ToolExecutionRequest(
                tool_name="home_assistant_control_state",
                arguments={"entity_id": "switch.garage", "state": "off"},
                metadata={
                    "director_authorized": True,
                    "approval_granted": True,
                    "memory_principal": {
                        "client_type": "imessage",
                        "client_subject": "family-member:abc",
                    },
                    "person": {"person_id": "joe"},
                },
            )
        )
    )
    assert result.success is True
    assert result.output["changed"] is False
    assert "control is not enabled" in result.output["error"]


# Helper to run async tool implementations in synchronous tests.
import asyncio as _asyncio


def asyncio_run(coro):
    return _asyncio.run(coro)
