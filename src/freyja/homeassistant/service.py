from __future__ import annotations

from collections.abc import Iterable

from .client import HomeAssistantClient
from .models import EntityAccess, HomeAssistantEntity, PairingPlan, PairingProtocol


_READ_ONLY_DOMAINS = {"binary_sensor", "sensor", "sun", "weather"}
_HIGH_RISK_DOMAINS = {"alarm_control_panel", "camera", "cover", "lock"}


class HomeAssistantService:
    """Policy layer for inventory and protocol-specific pairing workflows."""

    def __init__(self, client: HomeAssistantClient, *, allowed_entities: Iterable[str] = ()) -> None:
        self.client = client
        self._allowed_entities = frozenset(allowed_entities)

    async def status(self) -> dict:
        return {"configured": self.client.configured, "reachable": await self.client.health()}

    async def inventory(self) -> list[HomeAssistantEntity]:
        entities: list[HomeAssistantEntity] = []
        for payload in await self.client.states():
            entity_id = payload.get("entity_id")
            if not isinstance(entity_id, str):
                raise ValueError("Home Assistant entity requires entity_id")
            entities.append(HomeAssistantEntity.from_api(payload, access=self.classify(entity_id)))
        return sorted(entities, key=lambda item: item.entity_id)

    def classify(self, entity_id: str) -> EntityAccess:
        domain, separator, _name = entity_id.partition(".")
        if not separator:
            return EntityAccess.QUARANTINED
        if domain in _HIGH_RISK_DOMAINS:
            return EntityAccess.HIGH_RISK
        if domain in _READ_ONLY_DOMAINS:
            return EntityAccess.READ_ONLY
        if entity_id in self._allowed_entities:
            return EntityAccess.CONTROLLED
        return EntityAccess.QUARANTINED

    def pairing_plan(self, protocol: PairingProtocol, *, duration_seconds: int = 60) -> PairingPlan:
        duration = min(max(duration_seconds, 15), 120)
        plans = {
            PairingProtocol.ZIGBEE: PairingPlan(
                protocol=protocol,
                supported=True,
                duration_seconds=duration,
                physical_step="Put the Zigbee device into its documented pairing mode.",
                next_step="After explicit confirmation, open ZHA joining for the bounded window.",
            ),
            PairingProtocol.ZWAVE: PairingPlan(
                protocol=protocol,
                supported=False,
                duration_seconds=duration,
                physical_step="Put the Z-Wave device into inclusion mode and keep its PIN or QR code ready.",
                next_step="Start inclusion from the Z-Wave control panel; API automation is not enabled yet.",
            ),
            PairingProtocol.MATTER: PairingPlan(
                protocol=protocol,
                supported=False,
                duration_seconds=duration,
                requires_mobile_app=True,
                physical_step="Power the device and keep its Matter QR code or setup code ready.",
                next_step="Commission it with the Home Assistant companion app, then verify the new registry entry.",
            ),
            PairingProtocol.BLUETOOTH: PairingPlan(
                protocol=protocol,
                supported=False,
                duration_seconds=duration,
                physical_step="Power the Bluetooth device near an approved Home Assistant scanner or proxy.",
                next_step="Review passive discovery; no network-wide pairing window is required.",
            ),
            PairingProtocol.VENDOR: PairingPlan(
                protocol=protocol,
                supported=False,
                duration_seconds=duration,
                physical_step="Follow the vendor integration's local onboarding instructions.",
                next_step="Add the vendor integration manually and review its requested access.",
            ),
        }
        return plans[protocol]

    async def begin_zigbee_pairing(self, *, duration_seconds: int, confirmed: bool) -> dict:
        """Open ZHA joining only through an explicit non-tool approval path."""
        plan = self.pairing_plan(PairingProtocol.ZIGBEE, duration_seconds=duration_seconds)
        if not confirmed:
            raise PermissionError("explicit confirmation is required before opening pairing")
        await self.client.call_service("zha", "permit", {"duration": plan.duration_seconds})
        return {"protocol": "zigbee", "pairing_open": True, "duration_seconds": plan.duration_seconds}
