from __future__ import annotations

from pathlib import Path

import yaml


CONFIG = Path(__file__).resolve().parents[1] / "config" / "freyja-channels.yaml"


def _payload() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_freyja_channels_policy_is_deterministic_and_secret_free() -> None:
    payload = _payload()

    assert payload["service"] == "freyja-channels"
    assert payload["host"] == "atlas"
    assert payload["secrets_included"] is False
    assert payload["principle"] == "deterministic_gateway_only"
    assert payload["prohibitions"]["model_routing"] is True
    assert payload["prohibitions"]["independent_agent_intelligence"] is True
    assert "token" not in str(payload).lower()
    assert "api_key" not in str(payload).lower()


def test_channels_fail_closed_and_follow_requested_order() -> None:
    channels = _payload()["channels"]

    assert channels["telegram"]["build_order"] == 1
    assert channels["signal"]["build_order"] == 2
    assert channels["whatsapp"]["build_order"] == 3
    for channel in channels.values():
        assert channel["empty_allowlist"] == "deny_all"
    assert channels["whatsapp"]["status"] == "disabled"
    assert channels["whatsapp"]["webhook_public_access"] == "forbidden_until_approved"


def test_channels_require_identity_threads_attachments_audit_and_rate_limits() -> None:
    payload = _payload()

    assert payload["shared_controls"]["conversation_persistence"] == "required"
    assert payload["shared_controls"]["attachment_forwarding"] == "required"
    assert payload["shared_controls"]["audit_logging"] == "required"
    assert payload["shared_controls"]["rate_limits"] == "required"

    for name in ("telegram", "signal"):
        channel = payload["channels"][name]
        assert channel["identity_mapping"]
        assert channel["thread_persistence"]["raw_sender_in_thread_id"] is False
        assert channel["rate_limit"]["per_sender_per_minute"] > 0
        assert channel["rate_limit"]["burst"] > 0
        assert channel["audit"]["log_message_body"] is False
        assert channel["audit"]["log_raw_sender"] is False
        assert channel["audit"]["log_sender_hash"] is True


def test_children_only_have_their_own_assistant() -> None:
    identities = _payload()["identities"]

    assert identities["liam"]["permitted_agents"] == ["agent-44"]
    assert identities["jenna"]["permitted_agents"] == ["jenna"]
