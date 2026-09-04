from __future__ import annotations

from pathlib import Path

import yaml


CONFIG = Path(__file__).resolve().parents[1] / "config" / "freyja-proactive.yaml"


def _payload() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_proactive_policy_is_disabled_by_default_and_secret_free() -> None:
    payload = _payload()

    assert payload["service"] == "freyja-proactive"
    assert payload["host"] == "atlas"
    assert payload["secrets_included"] is False
    assert payload["default_status"] == "disabled"
    assert "token" not in str(payload).lower()
    assert "api_key" not in str(payload).lower()


def test_proactive_enablement_requires_verified_destinations_and_dry_run() -> None:
    gate = _payload()["enablement_gate"]

    assert gate["chat_stable"] == "required"
    assert gate["recipients_verified"] == "required"
    assert gate["destinations_verified"] == "required"
    assert gate["per_schedule_approval"] == "required"
    assert gate["dry_run_first"] == "required"


def test_all_requested_proactive_jobs_exist_but_are_disabled() -> None:
    jobs = _payload()["allowed_jobs"]

    assert set(jobs) == {
        "scheduled_briefing",
        "reminder_followup",
        "calendar_conflict_warning",
        "system_health_notification",
    }
    for job in jobs.values():
        assert job["status"] == "disabled"
        assert job["sends_without_verification"] is False
        assert job["allowed_recipients"]
        assert job["allowed_destinations"]
        assert job["required_tools"]


def test_proactive_policy_blocks_unsafe_defaults() -> None:
    prohibitions = _payload()["prohibitions"]
    audit = _payload()["audit"]

    assert prohibitions["enable_globally_by_default"] is True
    assert prohibitions["message_children_without_parent_policy"] is True
    assert prohibitions["run_destructive_tools"] is True
    assert prohibitions["infer_unverified_destination"] is True
    assert audit["log_message_body"] is False
