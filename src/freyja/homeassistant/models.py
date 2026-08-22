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


class HomeAssistantSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_total: int
    domain_counts: dict[str, int]
    access_counts: dict[EntityAccess, int]
    state_counts: dict[str, int]
    unavailable_count: int
    unknown_count: int
    attention_count: int
    high_risk_count: int
    controlled_count: int
    read_only_count: int
    quarantined_count: int
    visible_count: int
    observable_count: int
    policy_controlled_count: int
    blocked_control_count: int
    domains_present: list[str]
    homekit_like_count: int
    homekit_like_entities: list[str]


class PairingPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    protocol: PairingProtocol
    supported: bool
    duration_seconds: int = Field(ge=1, le=120)
    requires_confirmation: bool = True
    requires_mobile_app: bool = False
    physical_step: str
    next_step: str


class PairingSession(BaseModel):
    model_config = ConfigDict(frozen=True)

    protocol: PairingProtocol
    pairing_open: bool
    duration_seconds: int = Field(ge=1, le=120)
    service_domain: str
    service_name: str
    safe_summary: str


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
