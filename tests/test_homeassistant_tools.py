from __future__ import annotations

import httpx
import pytest

from freyja.homeassistant import HomeAssistantClient, HomeAssistantService
from freyja.tools.homeassistant import register_homeassistant_tools, set_homeassistant_service
from freyja.tools.models import ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


@pytest.fixture
def registry() -> ToolRegistry:
    registry = ToolRegistry(audit_enabled=False)
    register_homeassistant_tools(registry)
    yield registry
    set_homeassistant_service(None)


def set_service(handler) -> None:
    client = HomeAssistantClient(
        "http://homeassistant.test:8123",
        "synthetic-token",
        transport=httpx.MockTransport(handler),
    )
    set_homeassistant_service(HomeAssistantService(client, allowed_entities={"switch.lamp"}))


def test_homeassistant_tools_keep_pairing_write_disabled_by_default(registry: ToolRegistry) -> None:
    definitions = {item.name: item for item in registry.list_tools(include_disabled=True)}
    assert set(definitions) == {
        "homeassistant_begin_pairing",
        "homeassistant_home_summary",
        "homeassistant_status",
        "homeassistant_list_entities",
        "homeassistant_pairing_plan",
    }
    read_only_tools = {name: item for name, item in definitions.items() if name != "homeassistant_begin_pairing"}
    assert all(item.risk_level is ToolRiskLevel.READ_ONLY for item in read_only_tools.values())
    assert definitions["homeassistant_begin_pairing"].risk_level is ToolRiskLevel.CONTROLLED_WRITE
    assert definitions["homeassistant_begin_pairing"].enabled is False
    assert "homeassistant_begin_pairing" not in {item.name for item in registry.list_tools()}


@pytest.mark.asyncio
async def test_status_tool_reports_reachability(registry: ToolRegistry) -> None:
    set_service(lambda request: httpx.Response(200, json={"message": "API running"}))
    result = await registry.execute(ToolExecutionRequest(tool_name="homeassistant_status"))
    assert result.success is True
    assert result.output == {
        "configured": True,
        "reachable": True,
        "base_url": "http://homeassistant.test:8123",
    }


@pytest.mark.asyncio
async def test_entity_tool_filters_sanitized_inventory(registry: ToolRegistry) -> None:
    payload = [
        {"entity_id": "sensor.temperature", "state": "70", "attributes": {"friendly_name": "Temperature"}},
        {"entity_id": "switch.lamp", "state": "off", "attributes": {"friendly_name": "Lamp"}},
    ]
    set_service(lambda request: httpx.Response(200, json=payload))
    result = await registry.execute(
        ToolExecutionRequest(tool_name="homeassistant_list_entities", arguments={"domain": "sensor"})
    )
    assert result.success is True
    assert result.output["count"] == 1
    assert result.output["entities"][0]["entity_id"] == "sensor.temperature"


@pytest.mark.asyncio
async def test_home_summary_tool_rolls_up_inventory(registry: ToolRegistry) -> None:
    payload = [
        {"entity_id": "sensor.temperature", "state": "70", "attributes": {"friendly_name": "Temperature"}},
        {"entity_id": "switch.lamp", "state": "unavailable", "attributes": {"friendly_name": "Lamp"}},
    ]
    set_service(lambda request: httpx.Response(200, json=payload))
    result = await registry.execute(ToolExecutionRequest(tool_name="homeassistant_home_summary"))
    assert result.success is True
    assert result.output["entity_total"] == 2
    assert result.output["domain_counts"] == {"sensor": 1, "switch": 1}
    assert result.output["access_counts"] == {"controlled": 1, "read_only": 1}
    assert result.output["unavailable_count"] == 1
    assert result.output["attention_count"] == 1
    assert result.output["visible_count"] == 2
    assert result.output["policy_controlled_count"] == 1
    assert result.output["blocked_control_count"] == 0


@pytest.mark.asyncio
async def test_pairing_plan_is_advice_only(registry: ToolRegistry) -> None:
    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="homeassistant_pairing_plan",
            arguments={"protocol": "zigbee", "duration_seconds": 60},
        )
    )
    assert result.success is True
    assert result.output["supported"] is True
    assert result.output["requires_confirmation"] is True
    assert result.output["next_step"].startswith("After explicit confirmation")


@pytest.mark.asyncio
async def test_begin_pairing_tool_is_disabled_until_operator_enables_it(registry: ToolRegistry) -> None:
    result = await registry.execute(
        ToolExecutionRequest(
            tool_name="homeassistant_begin_pairing",
            arguments={"protocol": "zigbee", "duration_seconds": 60, "confirmed": True},
        )
    )
    assert result.success is False
    assert result.error_code == "tool_disabled"


@pytest.mark.asyncio
async def test_enabled_begin_pairing_tool_requires_confirmation_and_opens_zha_only(registry: ToolRegistry) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    set_service(handler)
    assert registry.set_enabled("homeassistant_begin_pairing", True)

    denied = await registry.execute(
        ToolExecutionRequest(
            tool_name="homeassistant_begin_pairing",
            arguments={"protocol": "zigbee", "duration_seconds": 60, "confirmed": False},
        )
    )
    assert denied.success is False
    assert denied.error_code == "tool_error"
    assert requests == []

    opened = await registry.execute(
        ToolExecutionRequest(
            tool_name="homeassistant_begin_pairing",
            arguments={"protocol": "zigbee", "duration_seconds": 999, "confirmed": True},
        )
    )
    assert opened.success is True
    assert opened.output == {
        "protocol": "zigbee",
        "pairing_open": True,
        "duration_seconds": 120,
        "service_domain": "zha",
        "service_name": "permit",
        "safe_summary": "Zigbee pairing is open for 120 seconds.",
    }
    assert len(requests) == 1
    assert requests[0].url.path == "/api/services/zha/permit"
