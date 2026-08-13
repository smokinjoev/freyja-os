from __future__ import annotations

from connectors.messaging import AuthorizedSender, parse_allowed_senders
from connectors.imessage.config import IMessageSettings
from connectors.signal.config import SignalSettings
from freyja.identity import Identity, IdentityService, Person


def test_plain_allowed_sender_keeps_platform_scoped_subject() -> None:
    identities = parse_allowed_senders("+15551234567", "signal")
    identity = identities["+15551234567"]

    assert identity.member_id is None
    assert identity.subject.startswith("signal:")
    assert identity.conversation_id.startswith("signal-conv:")


def test_family_alias_uses_shared_family_subject() -> None:
    signal = parse_allowed_senders("Joe Smith=+15551234567", "signal")
    imessage = parse_allowed_senders("joe-smith=joe@example.com", "imessage")

    assert signal["+15551234567"].member_id == "joe-smith"
    assert signal["+15551234567"].subject == imessage["joe@example.com"].subject
    assert signal["+15551234567"].safe_headers()["X-Freyja-Family-Member"] == "joe-smith"
    assert signal["+15551234567"].safe_headers()["X-Freyja-Person-Id"] == "joe-smith"


def test_authorized_sender_headers_do_not_include_raw_address() -> None:
    identity = AuthorizedSender(platform="imessage", address="joe@example.com", member_id="joe")

    headers = identity.safe_headers()

    assert "joe@example.com" not in str(headers)
    assert headers["X-Freyja-Client-Type"] == "imessage"
    assert headers["X-Freyja-Person-Id"] == "joe"


def test_signal_settings_resolve_plain_allowed_sender_to_canonical_person(monkeypatch) -> None:
    service = IdentityService(
        people=[
            Person(
                person_id="joe",
                display_name="Joe",
                identities=(Identity(kind="signal", value="+15551234567"),),
            )
        ]
    )
    monkeypatch.setattr("connectors.signal.config.default_identity_service", lambda: service)

    identity = SignalSettings(signal_allowed_senders="+15551234567").allowed_sender_identities["+15551234567"]

    assert identity.member_id == "joe"
    assert identity.person == service.require_person("joe")
    assert identity.safe_headers()["X-Freyja-Person-Id"] == "joe"


def test_imessage_settings_resolve_plain_allowed_sender_to_canonical_person(monkeypatch) -> None:
    service = IdentityService(
        people=[
            Person(
                person_id="beth",
                display_name="Beth",
                identities=(Identity(kind="email", value="beth@example.com"),),
            )
        ]
    )
    monkeypatch.setattr("connectors.imessage.config.default_identity_service", lambda: service)

    identity = IMessageSettings(imessage_allowed_senders="beth@example.com").allowed_sender_identities["beth@example.com"]

    assert identity.member_id == "beth"
    assert identity.person == service.require_person("beth")
    assert identity.safe_headers()["X-Freyja-Person-Id"] == "beth"
