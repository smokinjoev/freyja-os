from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from freyja.proactive import ProactivePlanner, render_candidates


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check-freyja-proactive-readiness.py"


def _script_module():
    spec = importlib.util.spec_from_file_location("check_freyja_proactive_readiness", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_proactive_planner_builds_all_disabled_candidates() -> None:
    planner = ProactivePlanner()
    candidates = planner.candidates()

    assert len(candidates) == 27
    assert {candidate.job_id for candidate in candidates} == {
        "scheduled_briefing",
        "reminder_followup",
        "calendar_conflict_warning",
        "system_health_notification",
    }
    assert all(candidate.status == "disabled" for candidate in candidates)
    assert all(candidate.requires_approval for candidate in candidates)
    assert all(candidate.dry_run_required for candidate in candidates)


def test_proactive_readiness_blocks_everything_by_default() -> None:
    report = ProactivePlanner().readiness(
        chat_stable=False,
        recipients_verified=set(),
        destinations_verified=set(),
        approved_schedule_ids=set(),
    )

    assert report["ok"] is True
    assert report["all_disabled_by_default"] is True
    assert report["candidate_count"] == 27
    assert report["ready_schedule_ids"] == []
    assert all("job_disabled" in item["reasons"] for item in report["blocked"])
    assert any("recipient_not_verified" in item["reasons"] for item in report["blocked"])


def test_proactive_readiness_still_requires_dry_run_even_with_verified_inputs() -> None:
    planner = ProactivePlanner()
    schedule_ids = {planner.schedule_id(candidate) for candidate in planner.candidates()}
    report = planner.readiness(
        chat_stable=True,
        recipients_verified={"joe", "beth", "liam", "jenna"},
        destinations_verified={"open-webui", "telegram", "signal"},
        approved_schedule_ids=schedule_ids,
    )

    assert report["ready_schedule_ids"] == []
    assert all({"job_disabled", "dry_run_required"} <= set(item["reasons"]) for item in report["blocked"])


def test_proactive_audit_event_does_not_log_message_body() -> None:
    planner = ProactivePlanner()
    event = planner.audit_event(planner.candidates()[0])

    assert event["message_body_logged"] is False
    assert event["delivery_result"] == "not_sent"
    assert "recipient" in event
    assert "destination" in event


def test_proactive_dry_run_dispatches_never_send() -> None:
    report = ProactivePlanner().dry_run_report()

    assert report["report_type"] == "freyja-proactive-dry-run"
    assert isinstance(report["generated_at_unix"], int)
    assert report["timestamp_unix"] == report["generated_at_unix"]
    assert report["secrets_included"] is False
    assert report["private_content_included"] is False
    assert report["dispatch_count"] == 27
    assert report["would_send_count"] == 0
    assert report["all_sends_suppressed"] is True
    assert all(item["delivery_result"] == "dry_run_only" for item in report["dispatches"])


def test_render_candidates_is_reviewable_json() -> None:
    text = render_candidates(ProactivePlanner().candidates())

    assert "scheduled_briefing" in text
    assert "required_tools" in text


def test_proactive_readiness_script_writes_report(tmp_path: Path, capsys) -> None:
    output = tmp_path / "proactive.json"

    assert _script_module().main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "freyja-proactive-readiness"
    assert isinstance(written["generated_at_unix"], int)
    assert written["git_head"]
    assert written["ready_schedule_ids"] == []


def test_proactive_dry_run_script_writes_suppressed_report(tmp_path: Path, capsys) -> None:
    script = REPO_ROOT / "scripts" / "dry-run-freyja-proactive.py"
    spec = importlib.util.spec_from_file_location("dry_run_freyja_proactive", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "dry-run.json"

    assert module.main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert isinstance(written["generated_at_unix"], int)
    assert written["timestamp_unix"] == written["generated_at_unix"]
    assert written["git_head"]
    assert written["all_sends_suppressed"] is True
