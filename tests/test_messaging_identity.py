from __future__ import annotations

from connectors.messaging import AuthorizedSender, parse_allowed_senders


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
