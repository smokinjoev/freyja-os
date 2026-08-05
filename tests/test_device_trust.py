from __future__ import annotations

import pytest

from freyja.agents import DeviceCredentialKind, DeviceRegistry, PersonName, TrustedDevice


JOE_FINGERPRINT = "a" * 64
BETH_FINGERPRINT = "b" * 64


def device(device_id: str, owner: PersonName, fingerprint: str, *, enabled: bool = True) -> TrustedDevice:
    return TrustedDevice(
        device_id=device_id,
        owner=owner,
        credential_kind=DeviceCredentialKind.TAILSCALE_NODE,
        credential_sha256=fingerprint,
        display_name=device_id,
        enabled=enabled,
    )


def test_device_requires_matching_owner_and_cryptographic_identity() -> None:
    registry = DeviceRegistry([device("joe-mbp", PersonName.JOE, JOE_FINGERPRINT)])

    assert registry.authorize(device_id="joe-mbp", owner=PersonName.JOE, credential_sha256=JOE_FINGERPRINT)
    assert not registry.authorize(device_id="joe-mbp", owner=PersonName.BETH, credential_sha256=JOE_FINGERPRINT)
    assert not registry.authorize(device_id="joe-mbp", owner=PersonName.JOE, credential_sha256=BETH_FINGERPRINT)
    assert not registry.authorize(device_id="unknown", owner=PersonName.JOE, credential_sha256=JOE_FINGERPRINT)


def test_disabled_devices_are_not_authorized_or_listed() -> None:
    registry = DeviceRegistry([device("retired-mac", PersonName.JOE, JOE_FINGERPRINT, enabled=False)])

    assert not registry.authorize(
        device_id="retired-mac", owner=PersonName.JOE, credential_sha256=JOE_FINGERPRINT
    )
    assert registry.devices_for(PersonName.JOE) == ()


def test_duplicate_device_ids_and_credentials_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate device_id"):
        DeviceRegistry(
            [
                device("shared-id", PersonName.JOE, JOE_FINGERPRINT),
                device("shared-id", PersonName.BETH, BETH_FINGERPRINT),
            ]
        )
    with pytest.raises(ValueError, match="duplicate device credential"):
        DeviceRegistry(
            [
                device("joe-mbp", PersonName.JOE, JOE_FINGERPRINT),
                device("iris", PersonName.JOE, JOE_FINGERPRINT),
            ]
        )


def test_fingerprint_must_be_a_sha256_hex_digest() -> None:
    with pytest.raises(ValueError):
        device("bad", PersonName.JOE, "hostname-or-ip")
