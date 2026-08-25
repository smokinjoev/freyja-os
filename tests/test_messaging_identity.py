from __future__ import annotations

from connectors.messaging import AuthorizedSender, household_agent_for_sender, parse_allowed_senders
from freyja.agents.household import household_agents


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


def test_signal_and_imessage_resolve_same_household_agents() -> None:
    signal = parse_allowed_senders("joe=+15551234567,beth=+15557654321,family=+15550000000", "signal")
    imessage = parse_allowed_senders("joe=joe@example.com,beth=beth@example.com,family=family@example.com", "imessage")

    assert household_agent_for_sender(signal["+15551234567"]).agent_id == "cloyd-gibbler"
    assert household_agent_for_sender(imessage["joe@example.com"]).agent_id == "cloyd-gibbler"
    assert household_agent_for_sender(signal["+15557654321"]).agent_id == "benedict"
    assert household_agent_for_sender(imessage["beth@example.com"]).agent_id == "benedict"
    assert household_agent_for_sender(signal["+15550000000"]).agent_id == "freyja"
    assert household_agent_for_sender(imessage["family@example.com"]).agent_id == "freyja"


def test_raw_allowlisted_senders_default_to_family_agent_context() -> None:
    signal = parse_allowed_senders("+15551234567", "signal")
    imessage = parse_allowed_senders("+15551234567", "imessage")

    assert household_agent_for_sender(signal["+15551234567"]).agent_id == "freyja"
    assert household_agent_for_sender(imessage["+15551234567"]).agent_id == "freyja"


def test_benedict_runtime_prompt_forbids_fabricated_context_like_cloyd() -> None:
    cloyd = household_agents.resolve("joe")
    benedict = household_agents.resolve("beth")

    for phrase in (
        "Do not claim you checked calendars",
        "unless Director supplied that data",
        "say you cannot verify it from here",
    ):
        assert phrase in cloyd.prompt_role
        assert phrase in benedict.prompt_role
