from __future__ import annotations

from typing import Any

from freyja.config import settings
from freyja.homeassistant import HomeAssistantClient, HomeAssistantService, PairingProtocol
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


_service: HomeAssistantService | None = None


def get_homeassistant_service() -> HomeAssistantService:
    global _service
    if _service is None:
        allowed = [item.strip() for item in settings.home_assistant_entity_allowlist.split(",") if item.strip()]
        _service = HomeAssistantService(
            HomeAssistantClient(
                settings.home_assistant_base_url,
                settings.home_assistant_token,
                timeout_seconds=settings.home_assistant_timeout_seconds,
            ),
            allowed_entities=allowed,
        )
    return _service


def set_homeassistant_service(service: HomeAssistantService | None) -> None:
    global _service
    _service = service


async def _status(_request: ToolExecutionRequest) -> dict:
    return await get_homeassistant_service().status()


async def _list_entities(request: ToolExecutionRequest) -> dict:
    domain = str(request.arguments.get("domain", "")).strip().lower()
    access = str(request.arguments.get("access", "")).strip().lower()
    entities = await get_homeassistant_service().inventory()
    if domain:
        entities = [item for item in entities if item.entity_id.startswith(f"{domain}.")]
    if access:
        entities = [item for item in entities if item.access.value == access]
    return {"entities": [item.model_dump(mode="json") for item in entities], "count": len(entities)}


async def _home_summary(_request: ToolExecutionRequest) -> dict:
    summary = await get_homeassistant_service().summary()
    return summary.model_dump(mode="json")


async def _pairing_plan(request: ToolExecutionRequest) -> dict:
    protocol = PairingProtocol(request.arguments["protocol"])
    duration = int(request.arguments.get("duration_seconds", 60))
    return get_homeassistant_service().pairing_plan(protocol, duration_seconds=duration).model_dump(mode="json")


async def _begin_pairing(request: ToolExecutionRequest) -> dict:
    protocol = PairingProtocol(request.arguments["protocol"])
    if protocol is not PairingProtocol.ZIGBEE:
        raise PermissionError("automated pairing is currently supported only for Zigbee through ZHA")
    duration = int(request.arguments.get("duration_seconds", 60))
    confirmed = bool(request.arguments.get("confirmed", False))
    session = await get_homeassistant_service().begin_zigbee_pairing(
        duration_seconds=duration,
        confirmed=confirmed,
    )
    return session.model_dump(mode="json")


def register_homeassistant_tools(registry: ToolRegistry) -> None:
    for definition, implementation in _tool_specs():
        if registry.get_tool(definition.name) is None:
            registry.register(definition, implementation)


def _tool_specs() -> list[tuple[ToolDefinition, Any]]:
    return [
        (
            _definition(
                "homeassistant_status",
                "Report whether the private Home Assistant API is configured and reachable.",
                {},
            ),
            _status,
        ),
        (
            _definition(
                "homeassistant_list_entities",
                "List sanitized Home Assistant entity states and their Freyja access classification.",
                {
                    "domain": {"type": "string"},
                    "access": {
                        "type": "string",
                        "enum": ["quarantined", "read_only", "controlled", "high_risk"],
                    },
                },
            ),
            _list_entities,
        ),
        (
            _definition(
                "homeassistant_home_summary",
                "Summarize the family home inventory from Home Assistant by domain, state, and access class.",
                {},
            ),
            _home_summary,
        ),
        (
            _definition(
                "homeassistant_pairing_plan",
                "Describe the safe physical and approval steps for adding a device; does not open pairing.",
                {
                    "protocol": {
                        "type": "string",
                        "enum": ["zigbee", "zwave", "matter", "bluetooth", "vendor"],
                    },
                    "duration_seconds": {"type": "integer"},
                },
                required=["protocol"],
            ),
            _pairing_plan,
        ),
        (
            _definition(
                "homeassistant_begin_pairing",
                "Open a bounded Zigbee ZHA pairing window after explicit user confirmation.",
                {
                    "protocol": {
                        "type": "string",
                        "enum": ["zigbee"],
                    },
                    "duration_seconds": {"type": "integer"},
                    "confirmed": {"type": "boolean"},
                },
                required=["protocol", "confirmed"],
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                enabled=False,
            ),
            _begin_pairing,
        ),
    ]


def _definition(
    name: str,
    description: str,
    properties: dict[str, Any],
    *,
    required: list[str] | None = None,
    risk_level: ToolRiskLevel = ToolRiskLevel.READ_ONLY,
    enabled: bool = True,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=description,
        version="1.0.0",
        input_schema={"type": "object", "required": required or [], "properties": properties},
        output_schema={"type": "object", "properties": {}},
        risk_level=risk_level,
        enabled=enabled,
        timeout_seconds=15,
        tags=["home-assistant", "devices", "local"],
    )
