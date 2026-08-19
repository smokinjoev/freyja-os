import json
from pathlib import Path
from typing import Any

import httpx

from freyja.config import settings
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


_READ_DOMAINS = {"sensor", "binary_sensor", "light", "switch", "climate", "cover", "lock"}


def _configured_state_fixture() -> dict[str, str]:
    try:
        data = json.loads(settings.home_assistant_state_fixture)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def _home_assistant_configured() -> bool:
    return bool(settings.home_assistant_base_url and settings.home_assistant_access_token)


def _allowed_control_domains() -> set[str]:
    return {
        item.strip().lower()
        for item in settings.home_assistant_allowed_control_domains.split(",")
        if item.strip()
    }


def _entity_domain(entity_id: str) -> str:
    return entity_id.split(".", 1)[0].lower() if "." in entity_id else ""


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.home_assistant_access_token}",
        "Content-Type": "application/json",
    }


def _ha_url(path: str) -> str:
    return f"{settings.home_assistant_base_url.rstrip('/')}/{path.lstrip('/')}"


def _state_summary(item: dict[str, Any]) -> dict[str, Any]:
    attributes = item.get("attributes") if isinstance(item.get("attributes"), dict) else {}
    entity_id = str(item.get("entity_id") or "")
    state = str(item.get("state") or "unknown")
    return {
        "entity_id": entity_id,
        "domain": _entity_domain(entity_id),
        "state": state,
        "is_on": state.lower() == "on",
        "friendly_name": attributes.get("friendly_name"),
        "area": attributes.get("area_id") or attributes.get("area"),
        "device_class": attributes.get("device_class"),
        "unit_of_measurement": attributes.get("unit_of_measurement"),
        "last_changed": item.get("last_changed"),
    }


def _inventory_record(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": str(entity.get("entity_id") or ""),
        "domain": str(entity.get("domain") or ""),
        "friendly_name": entity.get("friendly_name"),
        "device_class": entity.get("device_class"),
        "unit_of_measurement": entity.get("unit_of_measurement"),
    }


def _load_inventory_snapshot() -> dict[str, dict[str, Any]]:
    path = Path(settings.home_assistant_inventory_snapshot_path).expanduser()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    entities = data.get("entities") if isinstance(data, dict) else None
    if not isinstance(entities, dict):
        return {}
    return {
        str(entity_id): record
        for entity_id, record in entities.items()
        if isinstance(entity_id, str) and isinstance(record, dict)
    }


def _write_inventory_snapshot(entities: list[dict[str, Any]]) -> None:
    path = Path(settings.home_assistant_inventory_snapshot_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    records = {
        str(entity["entity_id"]): _inventory_record(entity)
        for entity in entities
        if isinstance(entity.get("entity_id"), str) and entity.get("entity_id")
    }
    payload = {
        "location": settings.home_assistant_location_name,
        "source": "home_assistant" if _home_assistant_configured() else "fixture",
        "entities": records,
    }
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


async def _ha_get(path: str) -> Any:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(_ha_url(path), headers=_headers())
        response.raise_for_status()
        return response.json()


async def _ha_post(path: str, payload: dict[str, Any]) -> Any:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(_ha_url(path), headers=_headers(), json=payload)
        response.raise_for_status()
        return response.json()


async def _current_state_summaries(args: dict[str, Any]) -> tuple[bool, list[dict[str, Any]], str]:
    requested_domain = str(args.get("domain") or "").strip().lower()
    include_all = bool(args.get("include_all"))
    domains = _READ_DOMAINS if not include_all else None
    if requested_domain:
        domains = {requested_domain}

    if _home_assistant_configured():
        items = await _ha_get("/api/states")
        summaries = [_state_summary(item) for item in items if isinstance(item, dict)]
        source = "home_assistant"
        live_data_available = True
    else:
        states = _configured_state_fixture()
        summaries = [
            {
                "entity_id": entity_id,
                "domain": _entity_domain(entity_id),
                "state": state,
                "is_on": state.lower() == "on",
            }
            for entity_id, state in sorted(states.items())
        ]
        source = "fixture"
        live_data_available = False

    if domains is not None:
        summaries = [item for item in summaries if item["domain"] in domains]
    summaries.sort(key=lambda item: item["entity_id"])
    return live_data_available, summaries, source


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

    if _home_assistant_configured():
        try:
            item = await _ha_get(f"/api/states/{entity_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {
                    "live_data_available": True,
                    "entity_id": entity_id,
                    "state": "unknown",
                    "source": "home_assistant",
                    "error": "entity not found",
                }
            raise
        summary = _state_summary(item)
        summary.update(
            {
                "live_data_available": True,
                "area": area or summary.get("area"),
                "source": "home_assistant",
                "location": settings.home_assistant_location_name,
            }
        )
        return summary

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


async def _list_states(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    live_data_available, entities, source = await _current_state_summaries(args)
    return {
        "live_data_available": live_data_available,
        "location": settings.home_assistant_location_name,
        "count": len(entities),
        "entities": entities,
        "source": source,
    }


async def _inventory_changes(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    update_snapshot = bool(args.get("update_snapshot", True))
    live_data_available, entities, source = await _current_state_summaries(args)
    current = {
        str(entity["entity_id"]): _inventory_record(entity)
        for entity in entities
        if isinstance(entity.get("entity_id"), str) and entity.get("entity_id")
    }
    previous = _load_inventory_snapshot()
    added_ids = sorted(set(current) - set(previous))
    removed_ids = sorted(set(previous) - set(current))
    changed_ids = sorted(
        entity_id
        for entity_id in set(current).intersection(previous)
        if current[entity_id] != previous[entity_id]
    )
    if update_snapshot:
        _write_inventory_snapshot(entities)
    return {
        "live_data_available": live_data_available,
        "location": settings.home_assistant_location_name,
        "source": source,
        "snapshot_updated": update_snapshot,
        "baseline_available": bool(previous),
        "current_count": len(current),
        "previous_count": len(previous),
        "added": [current[entity_id] for entity_id in added_ids],
        "removed": [previous[entity_id] for entity_id in removed_ids],
        "changed": [
            {
                "before": previous[entity_id],
                "after": current[entity_id],
            }
            for entity_id in changed_ids
        ],
    }


async def _control_state(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    entity_id = str(args.get("entity_id") or "").strip().lower()
    target_state = str(args.get("state") or "").strip().lower()
    if not entity_id or target_state not in {"on", "off"}:
        return {
            "changed": False,
            "error": "entity_id and state ('on' or 'off') are required",
        }
    domain = _entity_domain(entity_id)
    if domain not in _allowed_control_domains():
        return {
            "changed": False,
            "entity_id": entity_id,
            "state": target_state,
            "error": f"control is not enabled for domain '{domain}'",
        }
    if _home_assistant_configured():
        service = "turn_on" if target_state == "on" else "turn_off"
        await _ha_post(f"/api/services/{domain}/{service}", {"entity_id": entity_id})
        return {
            "changed": True,
            "entity_id": entity_id,
            "state": target_state,
            "source": "home_assistant",
            "location": settings.home_assistant_location_name,
        }
    return {
        "changed": True,
        "entity_id": entity_id,
        "state": target_state,
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
            health="live" if _home_assistant_configured() else "fixture",
            enabled=True,
            timeout_seconds=5,
            tags=["home", "home-assistant", "read-only", "capability"],
        ),
        _read_state,
    )
    registry.register(
        ToolDefinition(
            name="home_assistant_list_states",
            description=(
                "List Home Assistant entities visible to Freyja, including sensors and household state in Atlanta. "
                "Reads are scoped by household authorization and do not mutate devices."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Optional Home Assistant domain filter, e.g. sensor, binary_sensor, or light.",
                    },
                    "include_all": {
                        "type": "boolean",
                        "description": "When true, include every Home Assistant domain instead of the default household domains.",
                    },
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "live_data_available": {"type": "boolean"},
                    "location": {"type": "string"},
                    "count": {"type": "integer"},
                    "entities": {"type": "array"},
                    "source": {"type": "string"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            host_service="atlas.home_assistant",
            required_permission="household:home.read",
            confirmation_policy="none",
            audit_policy="request_result",
            health="live" if _home_assistant_configured() else "fixture",
            enabled=True,
            timeout_seconds=10,
            tags=["home", "home-assistant", "sensors", "read-only", "capability", "atlanta"],
        ),
        _list_states,
    )
    registry.register(
        ToolDefinition(
            name="home_assistant_inventory_changes",
            description=(
                "Compare current Home Assistant entities against Freyja's last Atlanta inventory snapshot "
                "and report added, removed, or renamed entities."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "properties": {
                    "domain": {"type": "string"},
                    "include_all": {"type": "boolean"},
                    "update_snapshot": {
                        "type": "boolean",
                        "description": "Persist the current inventory after comparison. Defaults to true.",
                    },
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "live_data_available": {"type": "boolean"},
                    "location": {"type": "string"},
                    "snapshot_updated": {"type": "boolean"},
                    "baseline_available": {"type": "boolean"},
                    "current_count": {"type": "integer"},
                    "previous_count": {"type": "integer"},
                    "added": {"type": "array"},
                    "removed": {"type": "array"},
                    "changed": {"type": "array"},
                    "source": {"type": "string"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            host_service="atlas.home_assistant",
            required_permission="household:home.read",
            confirmation_policy="none",
            audit_policy="request_result",
            health="live" if _home_assistant_configured() else "fixture",
            enabled=True,
            timeout_seconds=10,
            tags=["home", "home-assistant", "inventory", "device-changes", "read-only", "atlanta"],
        ),
        _inventory_changes,
    )
    registry.register(
        ToolDefinition(
            name="home_assistant_control_state",
            description="Control approved Home Assistant light entities in Atlanta after Director authorization and explicit approval.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["entity_id", "state"],
                "properties": {
                    "entity_id": {"type": "string"},
                    "state": {"type": "string", "enum": ["on", "off"]},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "changed": {"type": "boolean"},
                    "entity_id": {"type": "string"},
                    "state": {"type": "string"},
                    "source": {"type": "string"},
                },
            },
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            host_service="atlas.home_assistant",
            required_permission="household:home.control",
            confirmation_policy="operator_approval_required",
            audit_policy="request_result",
            health="live" if _home_assistant_configured() else "fixture",
            enabled=True,
            timeout_seconds=5,
            tags=["home", "home-assistant", "controlled-write", "capability"],
        ),
        _control_state,
    )
