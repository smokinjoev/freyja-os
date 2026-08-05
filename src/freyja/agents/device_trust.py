"""Cryptographic device allowlisting linked to canonical people."""

from __future__ import annotations

import hmac
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .hierarchy import PersonName


class DeviceCredentialKind(StrEnum):
    SSH_KEY = "ssh_key"
    TAILSCALE_NODE = "tailscale_node"
    APPLE_KEYCHAIN_CERTIFICATE = "apple_keychain_certificate"


class TrustedDevice(BaseModel):
    """A device relationship; hostnames and network addresses are descriptive only."""

    model_config = ConfigDict(frozen=True)

    device_id: str = Field(min_length=1, max_length=160)
    owner: PersonName
    credential_kind: DeviceCredentialKind
    credential_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    display_name: str = Field(min_length=1, max_length=160)
    enabled: bool = True


class DeviceRegistry:
    """Resolve devices by stable IDs and verify cryptographic credentials."""

    def __init__(self, devices: list[TrustedDevice] | None = None) -> None:
        self._devices: dict[str, TrustedDevice] = {}
        fingerprints: set[tuple[DeviceCredentialKind, str]] = set()
        for device in devices or []:
            if device.device_id in self._devices:
                raise ValueError(f"duplicate device_id: {device.device_id}")
            fingerprint = (device.credential_kind, device.credential_sha256)
            if fingerprint in fingerprints:
                raise ValueError("duplicate device credential")
            self._devices[device.device_id] = device
            fingerprints.add(fingerprint)

    def authorize(self, *, device_id: str, owner: PersonName, credential_sha256: str) -> bool:
        device = self._devices.get(device_id)
        if device is None or not device.enabled or device.owner is not owner:
            return False
        return hmac.compare_digest(device.credential_sha256, credential_sha256)

    def devices_for(self, owner: PersonName) -> tuple[TrustedDevice, ...]:
        return tuple(device for device in self._devices.values() if device.owner is owner and device.enabled)
