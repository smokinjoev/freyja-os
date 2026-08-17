import json
from typing import Any

from freyja.config import settings
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


def _configured_state_fixture() -> dict[str, str]:
    try:
        data = json.loads(settings.home_assistant_state_fixture)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


async def _read_state(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    area = str(args.get("area") or "").strip().lower()
    domain = str(args.get("domain") or "light").strip().lower()
    entity_id = str(args.get("entity_id") or "").strip().lower()
    if not entity_id:
        if area and domain:
            entity_id = f"{domain}.{area}"
        else:
            return {
                "live_data_available": False,
                "error": "entity_id or area/domain is required",
            }

    states = _configured_state_fixture()
    state = states.get(entity_id)
    if state is None:
        return {
            "live_data_available": False,
            "entity_id": entity_id,
            "state": "unknown",
            "source": "fixture",
        }
    return {
        "live_data_available": False,
        "entity_id": entity_id,
        "area": area or None,
        "domain": domain,
        "state": state,
        "is_on": state.lower() == "on",
        "source": "fixture",
    }


def register_home_assistant_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="home_assistant_read_state",
            description="Read Home Assistant entity state through the Atlas-controlled household capability boundary.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "entity_id": {"type": "string"},
                    "area": {"type": "string"},
                    "domain": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "live_data_available": {"type": "boolean"},
                    "entity_id": {"type": "string"},
                    "area": {"type": "string"},
                    "domain": {"type": "string"},
                    "state": {"type": "string"},
                    "is_on": {"type": "boolean"},
                    "source": {"type": "string"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            host_service="atlas.home_assistant",
            required_permission="household:home.read",
            confirmation_policy="none",
            audit_policy="request_result",
            health="fixture",
            enabled=True,
            timeout_seconds=5,
            tags=["home", "home-assistant", "read-only", "capability"],
        ),
        _read_state,
    )
