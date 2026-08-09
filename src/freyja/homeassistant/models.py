from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PairingProtocol(StrEnum):
    ZIGBEE = "zigbee"
    ZWAVE = "zwave"
    MATTER = "matter"
    BLUETOOTH = "bluetooth"
    VENDOR = "vendor"


class EntityAccess(StrEnum):
    QUARANTINED = "quarantined"
    READ_ONLY = "read_only"
    CONTROLLED = "controlled"
    HIGH_RISK = "high_risk"


class HomeAssistantEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_id: str = Field(pattern=r"^[a-z0-9_]+\.[a-z0-9_]+$")
    state: str
    friendly_name: str | None = None
    device_class: str | None = None
    unit_of_measurement: str | None = None
    access: EntityAccess = EntityAccess.QUARANTINED

    @classmethod
    def from_api(cls, payload: dict[str, Any], *, access: EntityAccess) -> "HomeAssistantEntity":
        attributes = payload.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        return cls(
            entity_id=payload.get("entity_id", ""),
            state=str(payload.get("state", "unknown")),
            friendly_name=_optional_string(attributes.get("friendly_name")),
            device_class=_optional_string(attributes.get("device_class")),
            unit_of_measurement=_optional_string(attributes.get("unit_of_measurement")),
            access=access,
        )


class PairingPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    protocol: PairingProtocol
    supported: bool
    duration_seconds: int = Field(ge=1, le=120)
    requires_confirmation: bool = True
    requires_mobile_app: bool = False
    physical_step: str
    next_step: str


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
