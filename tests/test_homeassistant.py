from __future__ import annotations

import json

import httpx
import pytest

from freyja.homeassistant import EntityAccess, HomeAssistantClient, HomeAssistantService, PairingProtocol


def client(handler, *, token: str = "synthetic-token") -> HomeAssistantClient:
    return HomeAssistantClient(
        "http://homeassistant.test:8123",
        token,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_health_uses_bearer_auth_without_returning_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/"
        assert request.headers["authorization"] == "Bearer synthetic-token"
        return httpx.Response(200, json={"message": "API running."})

    service = HomeAssistantService(client(handler))
    assert await service.status() == {
        "configured": True,
        "reachable": True,
        "base_url": "http://homeassistant.test:8123",
    }


@pytest.mark.asyncio
async def test_unconfigured_or_failed_health_is_honest() -> None:
    unconfigured = HomeAssistantService(HomeAssistantClient("http://homeassistant.test:8123", ""))
    assert await unconfigured.status() == {
        "configured": False,
        "reachable": False,
        "base_url": "http://homeassistant.test:8123",
    }

    failed = HomeAssistantService(client(lambda _request: httpx.Response(401)))
    assert await failed.status() == {
        "configured": True,
        "reachable": False,
        "base_url": "http://homeassistant.test:8123",
    }


@pytest.mark.asyncio
async def test_inventory_returns_only_safe_entity_fields_and_policy() -> None:
    payload = [
        {
            "entity_id": "sensor.basement_temperature",
            "state": "71.2",
            "attributes": {
                "friendly_name": "Basement Temperature",
                "device_class": "temperature",
                "unit_of_measurement": "°F",
                "private_vendor_blob": "must-not-leak",
            },
        },
        {"entity_id": "switch.lamp", "state": "off", "attributes": {"friendly_name": "Lamp"}},
        {"entity_id": "lock.front_door", "state": "locked", "attributes": {}},
        {"entity_id": "light.unknown", "state": "off", "attributes": {}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/states"
        return httpx.Response(200, json=payload)

    service = HomeAssistantService(client(handler), allowed_entities={"switch.lamp"})
    entities = await service.inventory()
    serialized = json.dumps([entity.model_dump(mode="json") for entity in entities])

    assert [entity.entity_id for entity in entities] == [
        "light.unknown",
        "lock.front_door",
        "sensor.basement_temperature",
        "switch.lamp",
    ]
    assert {entity.entity_id: entity.access for entity in entities} == {
        "light.unknown": EntityAccess.QUARANTINED,
        "lock.front_door": EntityAccess.HIGH_RISK,
        "sensor.basement_temperature": EntityAccess.READ_ONLY,
        "switch.lamp": EntityAccess.CONTROLLED,
    }
    assert "must-not-leak" not in serialized


@pytest.mark.asyncio
async def test_summary_rolls_up_inventory_without_raw_attributes() -> None:
    payload = [
        {"entity_id": "sensor.temperature", "state": "70", "attributes": {"friendly_name": "Temperature"}},
        {"entity_id": "binary_sensor.front_door", "state": "off", "attributes": {}},
        {"entity_id": "switch.lamp", "state": "unavailable", "attributes": {"private_vendor_blob": "secret"}},
        {"entity_id": "lock.front_door", "state": "locked", "attributes": {}},
        {"entity_id": "sensor.homekit_controller_status", "state": "ok", "attributes": {}},
    ]

    service = HomeAssistantService(
        client(lambda request: httpx.Response(200, json=payload)),
        allowed_entities={"switch.lamp"},
    )
    summary = await service.summary()
    serialized = json.dumps(summary.model_dump(mode="json"))

    assert summary.entity_total == 5
    assert summary.domain_counts == {"binary_sensor": 1, "lock": 1, "sensor": 2, "switch": 1}
    assert summary.access_counts == {
        EntityAccess.CONTROLLED: 1,
        EntityAccess.HIGH_RISK: 1,
        EntityAccess.READ_ONLY: 3,
    }
    assert summary.unavailable_count == 1
    assert summary.unknown_count == 0
    assert summary.attention_count == 1
    assert summary.high_risk_count == 1
    assert summary.controlled_count == 1
    assert summary.visible_count == 4
    assert summary.observable_count == 3
    assert summary.policy_controlled_count == 1
    assert summary.blocked_control_count == 1
    assert summary.homekit_like_count == 1
    assert summary.homekit_like_entities == ["sensor.homekit_controller_status"]
    assert "private_vendor_blob" not in serialized


@pytest.mark.parametrize("duration,expected", [(1, 15), (60, 60), (999, 120)])
def test_zigbee_pairing_plan_is_bounded(duration: int, expected: int) -> None:
    plan = HomeAssistantService(HomeAssistantClient("http://ha", "token")).pairing_plan(
        PairingProtocol.ZIGBEE,
        duration_seconds=duration,
    )
    assert plan.supported is True
    assert plan.requires_confirmation is True
    assert plan.duration_seconds == expected


def test_matter_plan_requires_mobile_commissioning() -> None:
    plan = HomeAssistantService(HomeAssistantClient("http://ha", "token")).pairing_plan(PairingProtocol.MATTER)
    assert plan.supported is False
    assert plan.requires_mobile_app is True


@pytest.mark.asyncio
async def test_zigbee_pairing_requires_confirmation_and_calls_only_zha_permit() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=[])

    service = HomeAssistantService(client(handler))
    with pytest.raises(PermissionError, match="confirmation"):
        await service.begin_zigbee_pairing(duration_seconds=60, confirmed=False)
    assert requests == []

    result = await service.begin_zigbee_pairing(duration_seconds=999, confirmed=True)
    assert result == {"protocol": "zigbee", "pairing_open": True, "duration_seconds": 120}
    assert len(requests) == 1
    assert requests[0].url.path == "/api/services/zha/permit"
    assert json.loads(requests[0].content) == {"duration": 120}


@pytest.mark.asyncio
async def test_malformed_states_fail_closed() -> None:
    service = HomeAssistantService(client(lambda _request: httpx.Response(200, json={"not": "a list"})))
    with pytest.raises(ValueError, match="array of objects"):
        await service.inventory()
