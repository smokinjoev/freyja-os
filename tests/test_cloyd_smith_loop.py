from __future__ import annotations

import asyncio
import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

import freyja.main as freyja_main
from freyja.cloyd_smith_loop import (
    AgentRunHeartbeat,
    CloydSmithJobCreate,
    CloydSmithJobStatus,
    CloydSmithJobStore,
    CloydSmithJobUpdate,
    capture_revision_evidence,
    default_cloyd_smith_supervisor_heartbeat_path,
    enrich_loop_status_with_runtime,
    heartbeat_summary,
    job_status_summary,
    loop_status_payload,
    read_supervisor_heartbeat,
)
from freyja.tools.builtin import register_builtin_tools
from freyja.tools.cloyd_smith_loop import (
    _cloyd_smith_follow_up,
    _cloyd_smith_mark_blocked,
    _cloyd_smith_mark_done,
    _cloyd_smith_replace,
    _cloyd_smith_retry,
    _cloyd_smith_status,
    _cloyd_smith_submit,
)
from freyja.tools.models import ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


REPO_ROOT = Path(__file__).resolve().parents[1]
DAEMON_SCRIPT = REPO_ROOT / "scripts" / "cloyd-smith-loop-daemon.py"


def _daemon_module():
    spec = importlib.util.spec_from_file_location("cloyd_smith_loop_daemon", DAEMON_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cloyd_smith_job_lifecycle_records_status_and_events(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Update Cloyd runtime contract.",
            smith_alias="freyja-code",
            acceptance_criteria=["diff reviewed", "tests pass"],
            current_prompt="Edit docs/operations/cloyd-runtime-contract.md.",
        )
    )

    assert job.job_id.startswith("freyja52-")
    assert job.status == CloydSmithJobStatus.QUEUED
    assert store.list_active()[0].job_id == job.job_id

    store.add_event(job.job_id, "smith_output", {"tests": "pass"})
    updated = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.NEEDS_REVIEW,
            next_action="cloyd_review_evidence",
            last_evidence={"tests": "pass"},
        ),
    )

    assert updated.status == CloydSmithJobStatus.NEEDS_REVIEW
    assert updated.last_evidence == {"tests": "pass"}
    assert store.events(job.job_id)[0]["event_type"] == "smith_output"

    done = store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.DONE))
    assert done.completed_at is not None
    assert store.list_active() == []


def test_cloyd_smith_job_persists_scope_checks_session_submission_and_revision(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    revision = {
        "head": "abc123",
        "working_tree_sha256": "tree",
        "check_commands": ["pytest -q"],
        "check_results": [{"command": "pytest -q", "exit_code": 0}],
    }
    job = store.create(
        CloydSmithJobCreate(
            objective="Patch one file.",
            scope="repo:freyja-os path:src/freyja/cloyd_smith_loop.py",
            current_prompt="Make one bounded patch.",
            acceptance_criteria=["diff reviewed"],
            check_commands=["pytest -q"],
        )
    )

    updated = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.RUNNING,
            phase="sent_to_smith",
            session_id="ses_one",
            submission_id="msg_one",
            revision_evidence=revision,
        ),
    )
    loaded = store.get(job.job_id)
    summary = job_status_summary(loaded)

    assert updated.scope == "repo:freyja-os path:src/freyja/cloyd_smith_loop.py"
    assert loaded.check_commands == ["pytest -q"]
    assert loaded.session_id == "ses_one"
    assert loaded.submission_id == "msg_one"
    assert loaded.phase == "sent_to_smith"
    assert loaded.revision_evidence == revision
    assert summary["session_id"] == "ses_one"
    assert summary["submission_id"] == "msg_one"
    assert summary["check_commands"] == ["pytest -q"]
    assert summary["revision_evidence"]["working_tree_sha256"] == "tree"


def test_capture_revision_evidence_binds_head_dirty_diff_and_untracked_files(tmp_path) -> None:
    subprocess_result = __import__("subprocess").run
    subprocess_result(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess_result(["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True)
    subprocess_result(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    subprocess_result(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess_result(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)
    tracked.write_text("two\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new\n", encoding="utf-8")

    evidence = capture_revision_evidence(
        repository=tmp_path,
        check_commands=["pytest -q"],
        check_results=[{"command": "pytest -q", "exit_code": 0}],
    )

    assert len(evidence["head"]) == 40
    assert "tracked.txt" in evidence["changed_files"]
    assert "new.txt" in evidence["untracked_file_sha256"]
    assert evidence["tracked_diff_sha256"]
    assert evidence["working_tree_sha256"]
    assert evidence["check_commands"] == ["pytest -q"]
    assert evidence["check_results"][0]["exit_code"] == 0


def test_heartbeat_create_update_stale_and_summary(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Observe Smith.",
            current_prompt="Run one status check.",
        )
    )
    started = datetime(2026, 9, 14, 1, 0, tzinfo=UTC)
    heartbeat = store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            session_id="ses_test",
            state="running",
            phase="polling_smith",
            last_action="opencode_status",
            last_message="Smith is still working.",
            working_directory="/tmp/repo",
            updated_at=started,
            stale_after_seconds=10,
        )
    )

    loaded = store.get_heartbeat(job.job_id)
    assert loaded == heartbeat
    assert not store.heartbeat_is_stale(loaded, now=started + timedelta(seconds=10))
    assert store.heartbeat_is_stale(loaded, now=started + timedelta(seconds=11))

    summary = heartbeat_summary(loaded, now=started + timedelta(seconds=12))
    assert summary["state"] == "running"
    assert summary["heartbeat_age_seconds"] == 12
    assert summary["elapsed_seconds"] == 12

    rows = store.status_rows(now=started + timedelta(seconds=12))
    assert rows[0]["job_id"] == job.job_id
    assert rows[0]["is_stale"] is False
    assert rows[0]["retry_attempts"] == 0
    assert rows[0]["follow_up_attempts"] == 0
    assert rows[0]["metadata"] == {}
    assert job_status_summary(job, heartbeat=loaded, now=started + timedelta(seconds=12))["next_action"] == "send_to_smith"


def test_mark_stale_runs_updates_job_and_heartbeat(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Long run.", current_prompt="Work until done."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING))
    observed_at = datetime(2026, 9, 14, 1, 0, tzinfo=UTC)
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="running",
            phase="smith_busy",
            last_action="bash",
            updated_at=observed_at,
            stale_after_seconds=5,
        )
    )

    warnings = store.mark_stale_runs(now=observed_at + timedelta(seconds=6))

    assert [item.job_id for item in warnings] == [job.job_id]
    assert store.get(job.job_id).status == CloydSmithJobStatus.RUNNING
    assert store.get(job.job_id).next_action == "continue observing; warning is not proof of failure"
    assert store.get_heartbeat(job.job_id).phase == "no_activity_warning"
    assert store.get_heartbeat(job.job_id).stop_reason is None
    assert store.events(job.job_id)[0]["event_type"] == "no_activity_warning"


def test_supervisor_heartbeat_reader_reports_missing_and_fresh(tmp_path) -> None:
    database = tmp_path / "jobs.db"
    heartbeat_path = default_cloyd_smith_supervisor_heartbeat_path(database)

    missing = read_supervisor_heartbeat(database)
    assert missing["ok"] is False
    assert missing["status"] == "missing"
    assert missing["path"] == str(heartbeat_path)

    heartbeat_path.write_text(
        '{"ok": true, "status": "loop_ok", "updated_at": "2026-09-14T01:00:00+00:00"}',
        encoding="utf-8",
    )
    fresh = read_supervisor_heartbeat(database, now=datetime(2026, 9, 14, 1, 0, 30, tzinfo=UTC), stale_after_seconds=90)

    assert fresh["ok"] is True
    assert fresh["status"] == "loop_ok"
    assert fresh["age_seconds"] == 30


def test_supervisor_heartbeat_reader_reports_stale(tmp_path) -> None:
    database = tmp_path / "jobs.db"
    heartbeat_path = default_cloyd_smith_supervisor_heartbeat_path(database)
    heartbeat_path.write_text(
        '{"ok": true, "status": "loop_ok", "updated_at": "2026-09-14T01:00:00+00:00"}',
        encoding="utf-8",
    )

    stale = read_supervisor_heartbeat(database, now=datetime(2026, 9, 14, 1, 2, 0, tzinfo=UTC), stale_after_seconds=90)

    assert stale["ok"] is False
    assert stale["status"] == "stale"
    assert stale["age_seconds"] == 120


def test_loop_status_payload_exposes_simple_cycle(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    default_cloyd_smith_supervisor_heartbeat_path(store.database_path).write_text(
        '{"ok": true, "status": "loop_ok", "updated_at": "%s"}' % datetime.now(UTC).isoformat(),
        encoding="utf-8",
    )

    status = loop_status_payload(store)

    assert status["cycle"]["model"] == ["check_for_work", "do_bounded_work", "finish_or_block", "report_result", "repeat"]
    assert status["cycle"]["current_step"] == "check_for_work"
    assert status["cycle"]["independent"] is True


def test_runtime_busy_outside_ledger_is_reported_as_cycle_exception(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    default_cloyd_smith_supervisor_heartbeat_path(store.database_path).write_text(
        '{"ok": true, "status": "loop_ok", "updated_at": "%s"}' % datetime.now(UTC).isoformat(),
        encoding="utf-8",
    )

    status = enrich_loop_status_with_runtime(loop_status_payload(store), {"ok": True, "session_count": 1})

    assert status["cycle"]["current_step"] == "report_result"
    assert status["cycle"]["runtime_exception"] == "opencode_busy_outside_ledger"
    assert status["diagnostics"][0]["title"] == "OpenCode busy outside ledger"


def test_non_running_heartbeat_is_not_reported_stale(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Review output.", current_prompt="Report."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW))
    old = datetime(2026, 9, 14, 1, 0, tzinfo=UTC)
    heartbeat = store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="needs_review",
            phase="output_ready",
            last_action="opencode_output",
            updated_at=old,
            stale_after_seconds=5,
            stop_reason="smith_idle",
        )
    )

    summary = heartbeat_summary(heartbeat, now=old + timedelta(hours=1))

    assert summary["state"] == "needs_review"
    assert summary["is_stale"] is False


def test_job_status_summary_gives_timeout_review_action(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Review output.", current_prompt="Report."))
    job = store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW))
    heartbeat = store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="needs_review",
            phase="output_ready",
            last_action="opencode_output",
            last_message="INFERENCE_QUEUE_TIMEOUT while waiting to start",
            stop_reason="smith_idle",
        )
    )

    summary = job_status_summary(job, heartbeat=heartbeat)

    assert "do not mark done" in summary["next_action"]
    assert "bounded follow-up" in summary["next_action"]


def test_job_status_summary_gives_retry_limit_action(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Retry work.",
            current_prompt="Try once.",
            metadata={"retry": {"attempts": 3}},
        )
    )
    job = store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, error="timed out"))

    summary = job_status_summary(job)

    assert summary["retry_attempts"] == 3
    assert "retry limit reached" in summary["next_action"]


def test_job_status_summary_gives_bounded_retry_action_for_send_timeout(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Retry work.", current_prompt="Try once."))
    job = store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, error="timed out"))

    summary = job_status_summary(job)

    assert "one bounded Retry" in summary["next_action"]


def test_job_status_summary_keeps_specific_busy_runtime_next_action(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Retry work.", current_prompt="Try once."))
    job = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="inspect_or_stop_opencode_session_before_retry",
            error="timed out",
        ),
    )

    summary = job_status_summary(job)

    assert summary["next_action"] == "inspect_or_stop_opencode_session_before_retry"


def test_job_status_summary_explains_smith_busy_timeout(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Retry work.", current_prompt="Try once."))
    job = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="inspect_or_queue_suggested_replacement_after_busy_timeout",
            error="Smith stayed busy for 221s without producing reviewable output.",
        ),
    )

    summary = job_status_summary(job)

    assert "Smith busy timeout stopped the runtime" in summary["next_action"]
    assert "Draft a smaller replacement job" in summary["suggested_prompt"]
    assert "Smith, this is a bounded replacement" in summary["replacement_prompt"]
    assert "previous bounded job hit a Smith busy timeout" in summary["replacement_prompt"]
    assert "Perform only one read-only check" in summary["replacement_prompt"]


def test_job_status_summary_brakes_repeated_busy_timeout_replacements(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Retry work.",
            current_prompt="Try once.",
            metadata={
                "source": "agent-runs-suggested-replacement",
                "parent_metadata": {
                    "source": "agent-runs-suggested-replacement",
                    "parent_metadata": {"source": "agent-runs-replacement"},
                },
            },
        )
    )
    job = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="inspect_or_queue_suggested_replacement_after_busy_timeout",
            error="Smith stayed busy for 182s without producing reviewable output.",
        ),
    )

    summary = job_status_summary(job)

    assert "repeated Smith busy timeouts" in summary["next_action"]
    assert summary["suggested_prompt"] == ""
    assert summary["replacement_prompt"] == ""


def test_job_status_summary_reports_runtime_reset_after_repeated_busy_timeout(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Retry work.",
            current_prompt="Try once.",
            metadata={
                "source": "agent-runs-suggested-replacement",
                "runtime_reset": {"attempts": 1, "started_session": "ses_new"},
                "parent_metadata": {
                    "source": "agent-runs-suggested-replacement",
                    "parent_metadata": {"source": "agent-runs-replacement"},
                },
            },
        )
    )
    job = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="inspect_or_queue_suggested_replacement_after_busy_timeout",
            error="Smith stayed busy for 182s without producing reviewable output.",
        ),
    )

    summary = job_status_summary(job)

    assert summary["runtime_reset_attempts"] == 1
    assert "runtime reset completed" in summary["next_action"]
    assert summary["replacement_prompt"] == ""


def test_job_status_summary_explains_prompt_replacement_blocker(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Broad feature work.", current_prompt="Build the whole thing."))
    job = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="blocked_pending_new_prompt_or_runtime_fix",
            error="review evidence is timeout-only; requested objective is not proven",
        ),
    )

    summary = job_status_summary(job)

    assert "sharper replacement job" in summary["next_action"]
    assert "acceptance criteria" in summary["next_action"]
    assert "Draft a smaller replacement job" in summary["suggested_prompt"]
    assert f"blocked_job_id: {job.job_id}" in summary["suggested_prompt"]
    assert "exact target files or service URL" in summary["suggested_prompt"]
    assert "Smith, this is a bounded replacement" in summary["replacement_prompt"]
    assert "Perform one read-only inventory" in summary["replacement_prompt"]
    assert "do not call bare python" in summary["replacement_prompt"]


def test_job_status_summary_flags_atlas_alias_mismatch(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Inspect Atlas dashboard.",
            smith_alias="freyja-code",
            current_prompt="Inspect /home/joe/cloyd-services/dashboard/index.html.",
        )
    )
    job = store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, error="could not access Atlas path"))

    summary = job_status_summary(job)

    assert summary["expected_alias"] == "atlas-dashboard"
    assert summary["alias_mismatch"] is True
    assert "smith_alias=atlas-dashboard" in summary["next_action"]


def test_job_status_summary_accepts_matching_metadata_alias(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Inspect Atlas dashboard.",
            smith_alias="atlas-dashboard",
            current_prompt="Inspect /home/joe/cloyd-services/dashboard/index.html.",
            metadata={"alias": "atlas-dashboard"},
        )
    )

    summary = job_status_summary(job)

    assert summary["expected_alias"] == "atlas-dashboard"
    assert summary["alias_mismatch"] is False


def test_job_status_summary_ignores_non_worker_metadata_alias(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Build Road Mode webpage.",
            smith_alias="freyja-code",
            current_prompt="Build src/freyja/roadmode.html.",
            metadata={"alias": "road-mode-webpage"},
        )
    )

    summary = job_status_summary(job)

    assert summary["expected_alias"] is None
    assert summary["alias_mismatch"] is False


def test_job_status_summary_gives_follow_up_limit_action(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Review work.",
            current_prompt="Report.",
            metadata={"follow_up": {"attempts": 1}},
        )
    )
    job = store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW))

    summary = job_status_summary(job)

    assert summary["follow_up_attempts"] == 1
    assert "bounded follow-up already used" in summary["next_action"]


def test_daemon_run_once_writes_heartbeat_transitions(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Patch file.", current_prompt="Inspect and patch one file."))
    old = datetime.now(UTC) - timedelta(seconds=600)
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="queued",
            phase="operator_requeued",
            last_action="operator_retry",
            updated_at=old,
            started_at=old,
        )
    )

    async def fake_send(request):
        sending = store.get(job.job_id)
        assert sending.status == CloydSmithJobStatus.RUNNING
        assert sending.next_action == "await_smith_send_result"
        assert request.arguments["timeout_seconds"] == module.DEFAULT_SEND_TIMEOUT_SECONDS
        assert module.DEFAULT_SEND_TIMEOUT_SECONDS < 90
        return {
            "ok": True,
            "session": "ses_daemon",
            "state": "working",
            "working_directory": "/repo",
            "recent_action": {"tool": "bash", "status": "running"},
            "result": "started",
        }

    monkeypatch.setattr(module, "_opencode_send", fake_send)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "running", "action": "sent_to_smith"}]
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.session_id == "ses_daemon"
    assert heartbeat.state == "running"
    assert heartbeat.phase == "sent_to_smith"
    assert heartbeat.working_directory == "/repo"
    assert heartbeat.started_at > old


def test_daemon_harvests_output_after_send_timeout_when_session_idle(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Patch file.", current_prompt="Inspect and patch one file."))

    async def fake_send(request):
        return {"ok": False, "error": "timed out"}

    async def fake_status(request):
        return {"ok": True, "session": "ses_daemon", "state": "idle", "working_directory": "/repo"}

    async def fake_output(request):
        return {"ok": True, "session": "ses_daemon", "result": "I inspected the file and found evidence."}

    monkeypatch.setattr(module, "_opencode_send", fake_send)
    monkeypatch.setattr(module, "_opencode_status", fake_status)
    monkeypatch.setattr(module, "_opencode_output", fake_output)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "needs_review", "action": "harvested_output_after_send_timeout"}]
    assert store.get(job.job_id).status == CloydSmithJobStatus.NEEDS_REVIEW
    assert store.get(job.job_id).error == ""
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.phase == "output_ready_after_send_timeout"
    assert heartbeat.stop_reason == "smith_idle_after_send_timeout"
    assert [event["event_type"] for event in store.events(job.job_id)[:3]] == [
        "smith_output_after_send_timeout",
        "smith_status_after_send_timeout",
        "smith_send",
    ]


def test_daemon_keeps_job_running_after_send_timeout_when_session_busy(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Patch file.", current_prompt="Inspect and patch one file."))

    async def fake_send(request):
        return {"ok": False, "error": "timed out"}

    async def fake_status(request):
        return {
            "ok": True,
            "session": "ses_daemon",
            "state": "busy",
            "working_directory": "/repo",
            "recent_action": {"tool": "bash", "status": "running"},
        }

    monkeypatch.setattr(module, "_opencode_send", fake_send)
    monkeypatch.setattr(module, "_opencode_status", fake_status)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "running", "action": "send_timed_out_but_smith_busy"}]
    assert store.get(job.job_id).status == CloydSmithJobStatus.RUNNING
    assert store.get(job.job_id).error == ""
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.phase == "smith_busy_after_send_timeout"
    assert heartbeat.last_action == "bash"


def test_daemon_blocks_dispatch_when_external_worker_is_busy(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Patch file.", current_prompt="Inspect and patch one file."))

    async def fail_start(request):
        raise AssertionError("queued work must not start while external worker is busy")

    async def fail_send(request):
        raise AssertionError("queued work must not send while external worker is busy")

    async def busy_status(request):
        return {
            "ok": True,
            "session": "ses_external",
            "state": {"type": "busy"},
            "working_directory": "/repo",
            "recent_action": {"tool": "bash", "status": "running"},
        }

    monkeypatch.setattr(module, "opencode_health", lambda *, alias=None, timeout_seconds=5: {"ok": True, "session_count": 1})
    monkeypatch.setattr(module, "_opencode_status", busy_status)
    monkeypatch.setattr(module, "_opencode_start", fail_start)
    monkeypatch.setattr(module, "_opencode_send", fail_send)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "unknown", "action": "dispatch_blocked_external_worker"}]
    assert store.get(job.job_id).status == CloydSmithJobStatus.QUEUED
    assert store.get(job.job_id).next_action == "external OpenCode work is active; wait or stop it before dispatch"
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.state == "unknown"
    assert heartbeat.phase == "external_worker_busy"
    assert heartbeat.session_id == "ses_external"


def test_daemon_reconciles_existing_submission_without_duplicate_send(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Patch file.", current_prompt="Inspect and patch one file."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.QUEUED,
            phase="sent_to_smith",
            session_id="ses_existing",
            submission_id="msg_existing",
        ),
    )

    async def fail_start(request):
        raise AssertionError("existing submissions must not start another session")

    async def fail_send(request):
        raise AssertionError("existing submissions must not be sent twice")

    monkeypatch.setattr(module, "_opencode_start", fail_start)
    monkeypatch.setattr(module, "_opencode_send", fail_send)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "running", "action": "reconciled_existing_submission"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.RUNNING
    assert loaded.session_id == "ses_existing"
    assert loaded.submission_id == "msg_existing"
    assert loaded.phase == "reconciled_existing_submission"
    assert store.get_heartbeat(job.job_id).phase == "reconciled_existing_submission"
    assert store.events(job.job_id)[0]["event_type"] == "submission_reconciled"


def test_daemon_marks_running_job_unknown_when_telemetry_disappears(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Watch task.", current_prompt="Keep working."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING))

    async def failed_status(request):
        return {"ok": False, "error": "event stream disconnected"}

    monkeypatch.setattr(module, "_opencode_status", failed_status)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "unknown", "action": "telemetry_unknown"}]
    assert store.get(job.job_id).status == CloydSmithJobStatus.UNKNOWN
    assert store.get(job.job_id).next_action == "freeze dispatch and reconcile OpenCode telemetry"
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.state == "unknown"
    assert heartbeat.phase == "telemetry_unavailable"


def test_daemon_reconnects_unknown_job_when_status_returns_busy(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Watch task.", current_prompt="Keep working."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(status=CloydSmithJobStatus.UNKNOWN, phase="telemetry_unavailable", session_id="ses_reconnect"),
    )

    async def reconnected_status(request):
        return {
            "ok": True,
            "session": "ses_reconnect",
            "state": {"type": "busy"},
            "working_directory": "/repo",
            "recent_action": {"tool": "bash", "status": "running"},
        }

    monkeypatch.setattr(module, "_opencode_status", reconnected_status)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "running", "action": "telemetry_reconnected"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.RUNNING
    assert loaded.phase == "telemetry_reconnected"
    assert loaded.next_action == "check_smith_output"
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.state == "running"
    assert heartbeat.phase == "telemetry_reconnected"
    assert store.events(job.job_id)[0]["event_type"] == "smith_status_after_unknown"


def test_daemon_reconnects_unknown_idle_job_and_verifies_output(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Finish after reconnect.",
            current_prompt="Do it.",
            check_commands=["true"],
        )
    )
    store.update(
        job.job_id,
        CloydSmithJobUpdate(status=CloydSmithJobStatus.UNKNOWN, phase="telemetry_unavailable", session_id="ses_reconnect"),
    )

    async def idle_status(request):
        return {"ok": True, "session": "ses_reconnect", "state": "idle", "working_directory": str(REPO_ROOT)}

    async def fake_output(request):
        return {"ok": True, "session": "ses_reconnect", "result": "done"}

    monkeypatch.setattr(module, "_opencode_status", idle_status)
    monkeypatch.setattr(module, "_opencode_output", fake_output)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "verified", "action": "verified"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.VERIFIED
    assert loaded.phase == "verified"
    assert loaded.revision_evidence["check_results"][0]["exit_code"] == 0
    assert store.get_heartbeat(job.job_id).stop_reason == "checks_passed"


def test_daemon_marks_permission_wait_as_waiting_for_input(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Needs approval.", current_prompt="Run command."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING, session_id="ses_wait"))

    async def waiting_status(request):
        return {
            "ok": True,
            "session": "ses_wait",
            "state": {"type": "busy"},
            "working_directory": "/repo",
            "recent_action": {"tool": "bash", "status": "waiting_for_permission", "message": "Waiting for permission to run command"},
        }

    monkeypatch.setattr(module, "_opencode_status", waiting_status)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "waiting_for_input", "action": "permission_wait"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.WAITING_FOR_INPUT
    assert loaded.phase == "permission_wait"
    assert loaded.next_action == "worker is waiting for permission or input; answer in the OpenCode session"
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.state == "waiting_for_input"
    assert heartbeat.phase == "permission_wait"


def test_daemon_reconnects_waiting_for_input_when_permission_resolves(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Needs approval.", current_prompt="Run command."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(status=CloydSmithJobStatus.WAITING_FOR_INPUT, phase="permission_wait", session_id="ses_wait"),
    )

    async def busy_status(request):
        return {
            "ok": True,
            "session": "ses_wait",
            "state": {"type": "busy"},
            "working_directory": "/repo",
            "recent_action": {"tool": "bash", "status": "running"},
        }

    monkeypatch.setattr(module, "_opencode_status", busy_status)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "running", "action": "telemetry_reconnected"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.RUNNING
    assert loaded.phase == "telemetry_reconnected"
    assert store.events(job.job_id)[0]["event_type"] == "smith_status_after_waiting_for_input"


def test_loop_status_counts_waiting_for_input_as_attention(tmp_path) -> None:
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Needs input.", current_prompt="Ask."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.WAITING_FOR_INPUT, phase="permission_wait"))

    status = loop_status_payload(store)

    assert status["queue"]["waiting_for_input"] == 1
    assert status["attention_count"] == 1
    assert status["runs"][0]["next_action"] == "operator or model input required before continuing"


def test_daemon_running_idle_captures_output_for_review(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Finish task.", current_prompt="Do it."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING))
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            session_id="ses_daemon",
            state="running",
            phase="smith_busy",
            last_action="bash",
            working_directory="/repo",
        )
    )

    async def fake_status(request):
        return {"ok": True, "session": "ses_daemon", "state": "idle", "working_directory": "/repo"}

    async def fake_output(request):
        return {"ok": True, "session": "ses_daemon", "messages": [{"parts": [{"type": "text", "text": "done"}]}]}

    monkeypatch.setattr(module, "_opencode_status", fake_status)
    monkeypatch.setattr(module, "_opencode_output", fake_output)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "needs_review", "action": "ready_for_review"}]
    assert store.get(job.job_id).status == CloydSmithJobStatus.NEEDS_REVIEW
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.state == "needs_review"
    assert heartbeat.phase == "output_ready"
    assert heartbeat.stop_reason == "smith_idle"


def test_daemon_running_idle_verifies_when_recorded_checks_pass(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Finish task.",
            current_prompt="Do it.",
            check_commands=["true"],
        )
    )
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING))

    async def fake_status(request):
        return {"ok": True, "session": "ses_daemon", "state": "idle", "working_directory": str(REPO_ROOT)}

    async def fake_output(request):
        return {"ok": True, "session": "ses_daemon", "result": "done"}

    monkeypatch.setattr(module, "_opencode_status", fake_status)
    monkeypatch.setattr(module, "_opencode_output", fake_output)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "verified", "action": "verified"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.VERIFIED
    assert loaded.phase == "verified"
    assert loaded.next_action == "report verified evidence"
    assert loaded.revision_evidence["check_commands"] == ["true"]
    assert loaded.revision_evidence["check_results"][0]["exit_code"] == 0
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.state == "verified"
    assert heartbeat.phase == "verified"
    assert heartbeat.stop_reason == "checks_passed"


def test_daemon_running_idle_needs_attention_when_recorded_checks_fail(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Finish task.",
            current_prompt="Do it.",
            check_commands=["false"],
        )
    )
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING))

    async def fake_status(request):
        return {"ok": True, "session": "ses_daemon", "state": "idle", "working_directory": str(REPO_ROOT)}

    async def fake_output(request):
        return {"ok": True, "session": "ses_daemon", "result": "done"}

    monkeypatch.setattr(module, "_opencode_status", fake_status)
    monkeypatch.setattr(module, "_opencode_output", fake_output)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "needs_attention", "action": "checks_failed"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.NEEDS_ATTENTION
    assert loaded.phase == "checks_failed"
    assert loaded.next_action == "repair failing checks in same Smith session or request input"
    assert loaded.revision_evidence["check_commands"] == ["false"]
    assert loaded.revision_evidence["check_results"][0]["exit_code"] == 1
    assert "'false' failed with exit 1" in loaded.error
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.state == "needs_attention"
    assert heartbeat.phase == "checks_failed"
    assert heartbeat.stop_reason == "checks_failed"


def test_daemon_queues_same_session_repair_after_failed_checks(tmp_path) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Repair task.",
            current_prompt="Do it.",
            acceptance_criteria=["Checks pass."],
            check_commands=["false"],
        )
    )
    revision = {
        "head": "abc123",
        "working_tree_sha256": "tree1",
        "tracked_diff_sha256": "diff1",
        "changed_files": ["src/example.py"],
        "check_results": [{"command": "false", "exit_code": 1, "timed_out": False, "stdout": "", "stderr": "failed"}],
    }
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.NEEDS_ATTENTION,
            phase="checks_failed",
            session_id="ses_repair",
            submission_id="old_submission",
            revision_evidence=revision,
            error="'false' failed with exit 1",
        ),
    )

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "queued", "action": "repair_queued", "attempt": 1}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.QUEUED
    assert loaded.phase == "repair_queued"
    assert loaded.session_id == "ses_repair"
    assert loaded.submission_id == ""
    assert loaded.metadata["repair"]["attempts"] == 1
    assert loaded.metadata["repair"]["last_working_tree_sha256"] == "tree1"
    assert "Repair attempt 1" in loaded.current_prompt
    assert "'false' -> 1: failed" in loaded.current_prompt
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.state == "queued"
    assert heartbeat.phase == "repair_queued"
    assert store.events(job.job_id)[0]["event_type"] == "repair_queued"


def test_daemon_repair_reuses_existing_session_without_new_start(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Repair task.",
            current_prompt="Repair attempt 1.",
            check_commands=["true"],
            metadata={"repair": {"attempts": 1, "session_id": "ses_repair"}},
        )
    )
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.QUEUED,
            phase="repair_queued",
            session_id="ses_repair",
            submission_id="",
        ),
    )
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            session_id="ses_repair",
            state="queued",
            phase="repair_queued",
            last_action="repair_preflight",
        )
    )

    async def fail_start(request):
        raise AssertionError("repair must reuse the existing Smith session")

    async def fake_send(request):
        assert "Repair attempt 1" in request.arguments["prompt"]
        return {"ok": True, "session": "ses_repair", "submission_id": "msg_repair", "result": "sent"}

    monkeypatch.setattr(module, "opencode_health", lambda *, alias=None, timeout_seconds=5: {"ok": True, "session_count": 0})
    monkeypatch.setattr(module, "_opencode_start", fail_start)
    monkeypatch.setattr(module, "_opencode_send", fake_send)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "running", "action": "sent_to_smith"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.RUNNING
    assert loaded.session_id == "ses_repair"
    assert loaded.submission_id == "msg_repair"


def test_daemon_repeated_repair_failure_without_progress_stays_attention(tmp_path) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Repair task.", current_prompt="Do it.", check_commands=["false"]))
    check_results = [{"command": "false", "exit_code": 1, "timed_out": False, "stdout": "", "stderr": "failed"}]
    signature = module._failure_signature(check_results)
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.NEEDS_ATTENTION,
            phase="checks_failed",
            session_id="ses_repair",
            revision_evidence={"working_tree_sha256": "tree1", "check_results": check_results},
            metadata={"repair": {"attempts": 1, "last_failure_signature": signature, "last_working_tree_sha256": "tree1"}},
            error="'false' failed with exit 1",
        ),
    )

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "needs_attention", "action": "repeated_failure_without_progress"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.NEEDS_ATTENTION
    assert loaded.metadata["repair"]["attempts"] == 1
    assert loaded.next_action == "repeated identical check failure without working-tree progress; request attention"
    assert store.get_heartbeat(job.job_id).phase == "repeated_failure_without_progress"


def test_daemon_allows_second_repair_after_progress_then_caps(tmp_path) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Repair task.", current_prompt="Do it.", check_commands=["false"]))
    check_results = [{"command": "false", "exit_code": 1, "timed_out": False, "stdout": "", "stderr": "failed"}]
    signature = module._failure_signature(check_results)
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.NEEDS_ATTENTION,
            phase="checks_failed",
            session_id="ses_repair",
            revision_evidence={"working_tree_sha256": "tree2", "check_results": check_results},
            metadata={"repair": {"attempts": 1, "last_failure_signature": signature, "last_working_tree_sha256": "tree1"}},
            error="'false' failed with exit 1",
        ),
    )

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "queued", "action": "repair_queued", "attempt": 2}]
    loaded = store.get(job.job_id)
    assert loaded.metadata["repair"]["attempts"] == 2
    assert loaded.metadata["repair"]["last_working_tree_sha256"] == "tree2"

    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.NEEDS_ATTENTION,
            phase="checks_failed",
            revision_evidence={"working_tree_sha256": "tree3", "check_results": check_results},
            metadata=loaded.metadata,
            error="'false' failed with exit 1",
        ),
    )

    capped = asyncio.run(module._run_once(store))

    assert capped == [{"job_id": job.job_id, "status": "needs_attention", "action": "repair_limit_reached"}]
    assert store.get(job.job_id).metadata["repair"]["attempts"] == 2
    assert store.get(job.job_id).next_action == "repair limit reached; request operator attention"


def test_daemon_leaves_verified_job_when_revision_evidence_is_current(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Already verified.", current_prompt="Done.", check_commands=["true"]))
    evidence = {"head": "head1", "working_tree_sha256": "tree1", "check_commands": ["true"], "check_results": []}
    store.update(
        job.job_id,
        CloydSmithJobUpdate(status=CloydSmithJobStatus.VERIFIED, phase="verified", revision_evidence=evidence),
    )

    monkeypatch.setattr(module, "capture_revision_evidence", lambda **kwargs: dict(evidence))
    monkeypatch.setattr(module, "_run_check_commands", lambda commands: (_ for _ in ()).throw(AssertionError("current verified evidence must not re-run checks")))

    result = asyncio.run(module._run_once(store))

    assert result == []
    assert store.get(job.job_id).status == CloydSmithJobStatus.VERIFIED


def test_daemon_refreshes_verified_evidence_after_working_tree_change_when_checks_pass(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Already verified.", current_prompt="Done.", check_commands=["true"]))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.VERIFIED,
            phase="verified",
            revision_evidence={"head": "head1", "working_tree_sha256": "tree1", "check_commands": ["true"], "check_results": []},
        ),
    )

    def fake_capture_revision_evidence(*, repository=None, check_commands=None, check_results=None):
        return {
            "head": "head2",
            "working_tree_sha256": "tree2",
            "tracked_diff_sha256": "diff2",
            "check_commands": check_commands or [],
            "check_results": check_results or [],
        }

    monkeypatch.setattr(module, "capture_revision_evidence", fake_capture_revision_evidence)
    monkeypatch.setattr(module, "_run_check_commands", lambda commands: [{"command": "true", "exit_code": 0, "timed_out": False, "stdout": "", "stderr": ""}])

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "verified", "action": "verified_rechecked"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.VERIFIED
    assert loaded.revision_evidence["head"] == "head2"
    assert loaded.revision_evidence["working_tree_sha256"] == "tree2"
    assert loaded.revision_evidence["check_results"][0]["exit_code"] == 0
    assert store.get_heartbeat(job.job_id).phase == "verified"
    assert store.events(job.job_id)[0]["event_type"] == "verified_recheck_finished"


def test_daemon_demotes_verified_after_working_tree_change_when_checks_fail(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Already verified.", current_prompt="Done.", check_commands=["false"]))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.VERIFIED,
            phase="verified",
            session_id="ses_verified",
            revision_evidence={"head": "head1", "working_tree_sha256": "tree1", "check_commands": ["false"], "check_results": []},
        ),
    )

    def fake_capture_revision_evidence(*, repository=None, check_commands=None, check_results=None):
        return {
            "head": "head2",
            "working_tree_sha256": "tree2",
            "tracked_diff_sha256": "diff2",
            "check_commands": check_commands or [],
            "check_results": check_results or [],
        }

    monkeypatch.setattr(module, "capture_revision_evidence", fake_capture_revision_evidence)
    monkeypatch.setattr(module, "_run_check_commands", lambda commands: [{"command": "false", "exit_code": 1, "timed_out": False, "stdout": "", "stderr": "failed"}])

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "needs_attention", "action": "stale_verification_checks_failed"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.NEEDS_ATTENTION
    assert loaded.phase == "checks_failed_after_stale_verification"
    assert loaded.next_action == "repair failing checks in same Smith session or request input"
    assert loaded.revision_evidence["check_results"][0]["exit_code"] == 1
    assert store.get_heartbeat(job.job_id).phase == "checks_failed_after_stale_verification"


def test_daemon_demotes_verified_without_checks_to_review_after_working_tree_change(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Already verified.", current_prompt="Done."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.VERIFIED,
            phase="verified",
            revision_evidence={"head": "head1", "working_tree_sha256": "tree1", "check_commands": [], "check_results": []},
        ),
    )
    refreshed = {"head": "head2", "working_tree_sha256": "tree2", "check_commands": [], "check_results": []}
    monkeypatch.setattr(module, "capture_revision_evidence", lambda **kwargs: dict(refreshed))
    monkeypatch.setattr(module, "_run_check_commands", lambda commands: (_ for _ in ()).throw(AssertionError("no-check verified jobs should not run checks")))

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "needs_review", "action": "verified_stale_after_edit"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.NEEDS_REVIEW
    assert loaded.phase == "verified_stale_after_edit"
    assert loaded.revision_evidence["working_tree_sha256"] == "tree2"
    assert store.get_heartbeat(job.job_id).phase == "verified_stale_after_edit"


def test_daemon_stop_after_current_turn_waits_until_idle_then_stops(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Stop after turn.", current_prompt="Keep working.", check_commands=["true"]))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.RUNNING,
            phase="stop_after_current_turn_requested",
            session_id="ses_stop",
            stop_intent="after_current_turn",
        ),
    )

    async def fake_status(request):
        return {"ok": True, "session": "ses_stop", "state": "idle", "working_directory": "/repo"}

    async def fake_output(request):
        return {"ok": True, "session": "ses_stop", "result": "turn finished"}

    monkeypatch.setattr(module, "_opencode_status", fake_status)
    monkeypatch.setattr(module, "_opencode_output", fake_output)
    monkeypatch.setattr(module, "_run_check_commands", lambda commands: (_ for _ in ()).throw(AssertionError("stop-after-turn must not verify")))

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "stopped", "action": "stopped_after_current_turn"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.STOPPED
    assert loaded.phase == "stopped_after_current_turn"
    assert loaded.stop_intent == "after_current_turn"
    assert loaded.last_evidence["result"] == "turn finished"
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.state == "stopped"
    assert heartbeat.phase == "stopped_after_current_turn"
    assert heartbeat.stop_reason == "after_current_turn"


def test_daemon_stop_after_current_turn_keeps_busy_job_running(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Stop after turn.", current_prompt="Keep working."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.RUNNING,
            phase="stop_after_current_turn_requested",
            session_id="ses_stop",
            stop_intent="after_current_turn",
        ),
    )

    async def fake_status(request):
        return {"ok": True, "session": "ses_stop", "state": {"type": "busy"}, "working_directory": "/repo"}

    monkeypatch.setattr(module, "_opencode_status", fake_status)
    monkeypatch.setattr(module, "_summary_text", lambda payload: "busy")

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "running", "action": "still_running"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.RUNNING
    assert loaded.stop_intent == "after_current_turn"
    assert loaded.next_action == "waiting for current turn boundary before stopping"


def test_daemon_reconciles_stopping_job_by_stopping_runtime(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Stop now.", current_prompt="Stop."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.STOPPING,
            phase="operator_immediate_stop_requested",
            session_id="ses_stop",
            stop_intent="immediate",
        ),
    )
    stop_calls = []

    async def fake_stop(request):
        stop_calls.append(request.arguments)
        return {"ok": True, "session": "ses_stop", "aborted": True}

    monkeypatch.setattr(module, "_opencode_stop", fake_stop)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "stopped", "smith_stop": {"ok": True, "session": "ses_stop", "aborted": True}}]
    assert stop_calls == [{"alias": "freyja-code"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.STOPPED
    assert loaded.stop_intent == "immediate"
    assert store.get_heartbeat(job.job_id).phase == "stopped"


def test_daemon_repeated_busy_poll_refreshes_observation_timestamp(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Watch busy task.", current_prompt="Keep working."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING))
    meaningful_at = datetime.now(UTC)
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            session_id="ses_busy",
            state="running",
            phase="smith_busy",
            last_action="opencode_status",
            last_message='{"state": {"type": "busy"}}',
            working_directory="/repo",
            updated_at=meaningful_at,
            stale_after_seconds=300,
        )
    )

    async def fake_status(request):
        return {
            "ok": True,
            "session": "ses_busy",
            "state": {"type": "busy"},
            "working_directory": "/repo",
        }

    monkeypatch.setattr(module, "_summary_text", lambda payload: '{"state": {"type": "busy"}}')
    monkeypatch.setattr(module, "_opencode_status", fake_status)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "running", "action": "still_running"}]
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.updated_at > meaningful_at
    assert store.get(job.job_id).next_action == "check_smith_output"


def test_daemon_warns_without_stopping_after_first_response_budget(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Watch busy task.", current_prompt="Keep working."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING))
    old = datetime.now(UTC) - timedelta(seconds=module.DEFAULT_FIRST_RESPONSE_BUDGET_SECONDS + 20)
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            session_id="ses_busy",
            state="running",
            phase="smith_busy",
            last_action="opencode_status",
            last_message='{"state": {"type": "busy"}}',
            working_directory="/repo",
            started_at=old,
            updated_at=old,
            stale_after_seconds=300,
        )
    )

    async def fake_status(request):
        return {
            "ok": True,
            "session": "ses_busy",
            "state": {"type": "busy"},
            "working_directory": "/repo",
        }

    stop_calls = []

    async def fake_stop(request):
        stop_calls.append(request.arguments)
        return {"ok": True, "session": "ses_busy", "aborted": True}

    monkeypatch.setattr(module, "_summary_text", lambda payload: '{"aborted": true}' if "aborted" in payload else '{"state": {"type": "busy"}}')
    monkeypatch.setattr(module, "_opencode_status", fake_status)
    monkeypatch.setattr(module, "_opencode_stop", fake_stop)

    result = asyncio.run(module._run_once(store))

    assert {"job_id": job.job_id, "status": "running", "action": "no_activity_warning"} in result
    assert {"job_id": job.job_id, "status": "running", "action": "first_response_warning"} in result
    assert stop_calls == []
    updated = store.get(job.job_id)
    assert updated.status == CloydSmithJobStatus.RUNNING
    assert updated.next_action == "continue observing; first-response warning is not a failure"
    assert "warning only" in updated.error
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.state == "running"
    assert heartbeat.phase == "first_response_warning"
    assert heartbeat.stop_reason is None
    assert store.events(job.job_id)[0]["event_type"] == "first_response_warning"


def test_daemon_recovers_stale_job_when_worker_is_still_busy(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Recover stale busy work.", current_prompt="Keep working."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.STALE, next_action="inspect_opencode_output_or_restart", error="No meaningful progress"))
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            session_id="ses_busy",
            state="stale",
            phase="stale",
            last_action="operator_review",
            last_error="No meaningful progress",
        )
    )

    async def fake_status(request):
        return {
            "ok": True,
            "session": "ses_busy",
            "state": {"type": "busy"},
            "working_directory": "/repo",
        }

    monkeypatch.setattr(module, "_summary_text", lambda payload: '{"state": {"type": "busy"}}')
    monkeypatch.setattr(module, "_opencode_status", fake_status)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "running", "action": "recovered_stale_busy"}]
    assert store.get(job.job_id).status == CloydSmithJobStatus.RUNNING
    assert store.get(job.job_id).error == ""
    assert store.get_heartbeat(job.job_id).phase == "smith_busy_after_stale"
    assert store.events(job.job_id)[0]["event_type"] == "smith_status_after_stale"


def test_daemon_harvests_stale_job_output_when_worker_is_idle(tmp_path, monkeypatch) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Harvest stale work.", current_prompt="Finish."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.STALE, next_action="inspect_opencode_output_or_restart", error="No meaningful progress"))

    async def fake_status(request):
        return {"ok": True, "session": "ses_idle", "state": "idle", "working_directory": "/repo"}

    async def fake_output(request):
        return {"ok": True, "session": "ses_idle", "messages": [{"parts": [{"type": "text", "text": "done"}]}]}

    monkeypatch.setattr(module, "_opencode_status", fake_status)
    monkeypatch.setattr(module, "_opencode_output", fake_output)

    result = asyncio.run(module._run_once(store))

    assert result == [{"job_id": job.job_id, "status": "needs_review", "action": "harvested_output_after_stale"}]
    assert store.get(job.job_id).status == CloydSmithJobStatus.NEEDS_REVIEW
    assert store.get(job.job_id).error == ""
    assert store.get_heartbeat(job.job_id).phase == "output_ready_after_stale"
    assert store.events(job.job_id)[0]["event_type"] == "smith_output_after_stale"


def test_daemon_writes_supervisor_heartbeat(tmp_path) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")

    payload = module._write_supervisor_heartbeat(None, store, status="loop_ok", results=[{"job_id": "freyja52-test"}])
    loaded = read_supervisor_heartbeat(store.database_path, now=datetime.fromisoformat(payload["updated_at"]), stale_after_seconds=90)

    assert payload["ok"] is True
    assert payload["result_count"] == 1
    assert loaded["ok"] is True
    assert loaded["status"] == "loop_ok"
    assert loaded["payload"]["result_count"] == 1


def test_daemon_status_payload_includes_supervisor_queue_and_runs(tmp_path) -> None:
    module = _daemon_module()
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Review work.", current_prompt="Report."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.NEEDS_REVIEW,
            session_id="ses_existing",
            submission_id="msg_old",
        ),
    )
    module._write_supervisor_heartbeat(None, store, status="loop_ok", results=[])

    payload = module._status_payload(store)

    assert payload["ok"] is True
    assert payload["supervisor"]["status"] == "loop_ok"
    assert payload["queue"]["needs_review"] == 1
    assert payload["attention_count"] == 1
    assert payload["runs"][0]["job_id"] == job.job_id


def test_daemon_bounded_evidence_redacts_secrets() -> None:
    module = _daemon_module()

    evidence = module._bounded(
        {
            "password": "open-sesame",
            "nested": {"api_key": "sk-test"},
            "text": "Authorization: Basic abc123 and bearer token-value",
        }
    )

    serialized = str(evidence)
    assert "open-sesame" not in serialized
    assert "sk-test" not in serialized
    assert "abc123" not in serialized
    assert "token-value" not in serialized
    assert "[redacted]" in serialized


def test_daemon_exclusive_lock_reports_contention(tmp_path) -> None:
    module = _daemon_module()
    lock_path = tmp_path / "loop.lock"

    with module._exclusive_lock(lock_path) as acquired:
        assert acquired is True
        with module._exclusive_lock(lock_path) as second_acquired:
            assert second_acquired is False


def test_builtin_registry_includes_cloyd_smith_loop_tools() -> None:
    registry = ToolRegistry()

    register_builtin_tools(registry)

    expected = {
        "cloyd_smith_retry": ToolRiskLevel.CONTROLLED_WRITE,
        "cloyd_smith_mark_done": ToolRiskLevel.CONTROLLED_WRITE,
        "cloyd_smith_mark_blocked": ToolRiskLevel.CONTROLLED_WRITE,
        "cloyd_smith_submit": ToolRiskLevel.CONTROLLED_WRITE,
        "cloyd_smith_status": ToolRiskLevel.READ_ONLY,
        "cloyd_smith_record": ToolRiskLevel.CONTROLLED_WRITE,
        "cloyd_smith_stop": ToolRiskLevel.CONTROLLED_WRITE,
        "cloyd_smith_follow_up": ToolRiskLevel.CONTROLLED_WRITE,
        "cloyd_smith_replace": ToolRiskLevel.CONTROLLED_WRITE,
    }
    for name, risk in expected.items():
        definition = registry.get_tool(name)
        assert definition is not None
        assert definition.risk_level == risk
        assert definition.host_service == "cloyd-smith-loop"


def test_cloyd_smith_submit_returns_receipt(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))

    result = asyncio.run(
        _cloyd_smith_submit(
            ToolExecutionRequest(
                tool_name="cloyd_smith_submit",
                arguments={
                    "objective": "Do durable work.",
                    "prompt": "Ask Smith to do one bounded step.",
                    "smith_alias": "freyja-code",
                    "acceptance_criteria": ["evidence recorded"],
                },
                actor="test",
            )
        )
    )

    assert result["ok"] is True
    assert result["receipt"]["job_id"].startswith("freyja52-")
    assert result["receipt"]["status"] == "queued"
    assert result["receipt"]["status_prompt"].startswith("Ask Cloyd: status")

    status = asyncio.run(
        _cloyd_smith_status(
            ToolExecutionRequest(
                tool_name="cloyd_smith_status",
                arguments={"job_id": result["receipt"]["job_id"]},
                actor="test",
            )
        )
    )
    assert status["job"]["objective"] == "Do durable work."
    assert status["loop"]["canonical_status_endpoint"] == "http://100.115.228.56:8000/agent-runs/api/status"
    assert status["loop"]["queue"]["queued"] == 1
    assert status["loop"]["attention_count"] == 0
    assert status["loop"]["runs"][0]["job_id"] == result["receipt"]["job_id"]


def test_cloyd_smith_status_without_job_id_returns_loop_context(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Review work.", current_prompt="Report."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.NEEDS_REVIEW,
            session_id="ses_existing",
            submission_id="msg_old",
        ),
    )

    status = asyncio.run(
        _cloyd_smith_status(
            ToolExecutionRequest(
                tool_name="cloyd_smith_status",
                arguments={},
                actor="test",
            )
        )
    )

    assert status["ok"] is True
    assert status["loop"]["canonical_monitor_url"] == "http://100.115.228.56:8000/agent-runs"
    assert status["loop"]["queue"]["needs_review"] == 1
    assert status["loop"]["attention_count"] == 1
    assert status["jobs"][0]["job_id"] == job.job_id
    assert status["jobs"] == status["loop"]["runs"]


def test_cloyd_smith_follow_up_queues_same_job_once(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Review work.", current_prompt="Report."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.NEEDS_REVIEW,
            session_id="ses_existing",
            submission_id="msg_old",
        ),
    )

    result = asyncio.run(
        _cloyd_smith_follow_up(
            ToolExecutionRequest(
                tool_name="cloyd_smith_follow_up",
                arguments={"job_id": job.job_id, "prompt": "Run one bounded verification pass."},
                actor="test",
            )
        )
    )

    assert result["ok"] is True
    assert result["job"]["status"] == "queued"
    assert result["job"]["current_prompt"] == "Run one bounded verification pass."
    assert store.get(job.job_id).session_id == "ses_existing"
    assert store.get(job.job_id).submission_id == ""
    assert result["job"]["summary"]["follow_up_attempts"] == 1
    assert result["loop"]["queue"]["queued"] == 1
    assert store.get_heartbeat(job.job_id).phase == "operator_follow_up_queued"
    assert store.events(job.job_id)[0]["event_type"] == "operator_follow_up"


def test_cloyd_smith_follow_up_rejects_second_attempt(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Review work.",
            current_prompt="Report.",
            metadata={"follow_up": {"attempts": 1}},
        )
    )
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW))

    result = asyncio.run(
        _cloyd_smith_follow_up(
            ToolExecutionRequest(
                tool_name="cloyd_smith_follow_up",
                arguments={"job_id": job.job_id, "prompt": "Try again."},
                actor="test",
            )
        )
    )

    assert result["ok"] is False
    assert "already has a bounded follow-up" in result["error"]
    assert store.get(job.job_id).status == CloydSmithJobStatus.NEEDS_REVIEW
    assert store.events(job.job_id)[0]["event_type"] == "operator_follow_up_limit_reached"


def test_cloyd_smith_replace_supersedes_blocked_job(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Broad Road Mode work.",
            current_prompt="Build everything.",
            metadata={"feature": "road-mode"},
        )
    )
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="blocked_pending_new_prompt_or_runtime_fix",
            error="review evidence is timeout-only; requested objective is not proven",
        ),
    )

    result = asyncio.run(
        _cloyd_smith_replace(
            ToolExecutionRequest(
                tool_name="cloyd_smith_replace",
                arguments={
                    "job_id": job.job_id,
                    "objective": "Inventory Road Mode current page state.",
                    "prompt": "Inspect src/freyja/roadmode.html and report the smallest missing piece.",
                    "smith_alias": "freyja-code",
                    "acceptance_criteria": ["Report exact files inspected."],
                },
                actor="test",
            )
        )
    )

    replacement_id = result["replacement_job"]["job_id"]
    assert result["ok"] is True
    assert result["action"] == "replace"
    assert result["replaced_job"]["status"] == "stopped"
    assert result["replaced_job"]["next_action"] == f"superseded_by:{replacement_id}"
    assert result["replacement_job"]["status"] == "queued"
    assert result["replacement_job"]["objective"] == "Inventory Road Mode current page state."
    assert result["replacement_job"]["metadata"]["replaces"] == job.job_id
    assert result["loop"]["queue"]["queued"] == 1
    assert result["loop"]["queue"]["stopped"] == 0
    assert result["loop"]["hidden_terminal_count"] == 1
    assert store.get_heartbeat(job.job_id).phase == "superseded"
    assert store.get_heartbeat(replacement_id).phase == "replacement_queued"


def test_cloyd_smith_retry_requeues_blocked_job_after_health_check(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(
        "freyja.tools.cloyd_smith_loop.opencode_health",
        lambda *, alias=None, timeout_seconds=5: {"ok": True, "alias": alias or "", "base_url": "http://opencode.test", "session_count": 1},
    )

    async def idle_status(request):
        return {"ok": True, "alias": request.arguments["alias"], "state": "idle", "recent_action": None}

    monkeypatch.setattr("freyja.tools.cloyd_smith_loop._opencode_status", idle_status)
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Retry work.", current_prompt="Try once."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, error="timed out"))
    old = datetime.now(UTC) - timedelta(seconds=600)
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="blocked",
            phase="smith_busy_timeout",
            last_action="opencode_stop",
            updated_at=old,
            started_at=old,
        )
    )

    result = asyncio.run(
        _cloyd_smith_retry(
            ToolExecutionRequest(
                tool_name="cloyd_smith_retry",
                arguments={"job_id": job.job_id},
                actor="test",
            )
        )
    )

    assert result["ok"] is True
    assert result["job"]["status"] == "queued"
    assert result["job"]["summary"]["retry_attempts"] == 1
    assert result["loop"]["queue"]["queued"] == 1
    assert store.get(job.job_id).metadata["retry"]["last_error"] == "timed out"
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.phase == "operator_requeued"
    assert heartbeat.started_at > old
    assert store.events(job.job_id)[0]["event_type"] == "operator_retry"


def test_cloyd_smith_retry_rejects_unhealthy_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(
        "freyja.tools.cloyd_smith_loop.opencode_health",
        lambda *, alias=None, timeout_seconds=5: {"ok": False, "alias": alias or "", "base_url": "http://opencode.test", "error": "timed out"},
    )
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Retry work.", current_prompt="Try once."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, error="timed out"))

    result = asyncio.run(
        _cloyd_smith_retry(
            ToolExecutionRequest(
                tool_name="cloyd_smith_retry",
                arguments={"job_id": job.job_id},
                actor="test",
            )
        )
    )

    assert result["ok"] is False
    assert "OpenCode runtime is not healthy" in result["error"]
    assert store.get(job.job_id).status == CloydSmithJobStatus.BLOCKED
    assert store.events(job.job_id)[0]["event_type"] == "operator_retry_preflight_failed"


def test_cloyd_smith_retry_rejects_busy_runtime_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(
        "freyja.tools.cloyd_smith_loop.opencode_health",
        lambda *, alias=None, timeout_seconds=5: {"ok": True, "alias": alias or "", "base_url": "http://opencode.test", "session_count": 1},
    )

    async def busy_status(request):
        return {"ok": True, "alias": request.arguments["alias"], "state": "idle", "recent_action": {"tool": "bash", "status": "running"}}

    monkeypatch.setattr("freyja.tools.cloyd_smith_loop._opencode_status", busy_status)
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Retry work.", current_prompt="Try once."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, error="timed out"))

    result = asyncio.run(
        _cloyd_smith_retry(
            ToolExecutionRequest(
                tool_name="cloyd_smith_retry",
                arguments={"job_id": job.job_id},
                actor="test",
            )
        )
    )

    assert result["ok"] is False
    assert "not ready for retry" in result["error"]
    assert store.get(job.job_id).status == CloydSmithJobStatus.BLOCKED
    assert store.get(job.job_id).next_action == "inspect_or_stop_opencode_session_before_retry"
    assert result["job"]["next_action"] == "inspect_or_stop_opencode_session_before_retry"
    assert store.events(job.job_id)[0]["event_type"] == "operator_retry_runtime_busy"


def test_cloyd_smith_retry_rejects_structured_busy_runtime_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))
    monkeypatch.setattr(
        "freyja.tools.cloyd_smith_loop.opencode_health",
        lambda *, alias=None, timeout_seconds=5: {"ok": True, "alias": alias or "", "base_url": "http://opencode.test", "session_count": 1},
    )

    async def busy_status(request):
        return {"ok": True, "alias": request.arguments["alias"], "state": {"type": "busy"}, "recent_action": None}

    monkeypatch.setattr("freyja.tools.cloyd_smith_loop._opencode_status", busy_status)
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Retry work.", current_prompt="Try once."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, error="timed out"))

    result = asyncio.run(
        _cloyd_smith_retry(
            ToolExecutionRequest(
                tool_name="cloyd_smith_retry",
                arguments={"job_id": job.job_id},
                actor="test",
            )
        )
    )

    assert result["ok"] is False
    assert "not ready for retry" in result["error"]
    assert store.get(job.job_id).next_action == "inspect_or_stop_opencode_session_before_retry"
    assert store.events(job.job_id)[0]["event_type"] == "operator_retry_runtime_busy"


def test_cloyd_smith_retry_rejects_alias_mismatch_before_runtime(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))

    def fail_health(**_: object) -> dict[str, object]:
        raise AssertionError("alias mismatch should be rejected before OpenCode health check")

    monkeypatch.setattr("freyja.tools.cloyd_smith_loop.opencode_health", fail_health)
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(
        CloydSmithJobCreate(
            objective="Inspect Atlas dashboard.",
            smith_alias="freyja-code",
            current_prompt="Inspect /home/joe/cloyd-services/dashboard/index.html.",
        )
    )
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, error="wrong host"))

    result = asyncio.run(
        _cloyd_smith_retry(
            ToolExecutionRequest(
                tool_name="cloyd_smith_retry",
                arguments={"job_id": job.job_id},
                actor="test",
            )
        )
    )

    assert result["ok"] is False
    assert "smith_alias=atlas-dashboard" in result["error"]
    assert store.events(job.job_id)[0]["event_type"] == "operator_retry_alias_mismatch"


def test_cloyd_smith_mark_done_completes_review_job(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Review work.", current_prompt="Report."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW))

    result = asyncio.run(
        _cloyd_smith_mark_done(
            ToolExecutionRequest(
                tool_name="cloyd_smith_mark_done",
                arguments={"job_id": job.job_id},
                actor="test",
            )
        )
    )

    assert result["ok"] is True
    assert result["job"]["status"] == "done"
    assert store.get(job.job_id).completed_at is not None
    assert store.get_heartbeat(job.job_id).phase == "operator_reviewed"
    assert store.events(job.job_id)[0]["event_type"] == "operator_mark_done"


def test_cloyd_smith_mark_blocked_uses_timeout_reason(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("freyja.cloyd_smith_loop.settings.cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))
    store = CloydSmithJobStore(tmp_path / "jobs.db")
    job = store.create(CloydSmithJobCreate(objective="Review work.", current_prompt="Report."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW))
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="needs_review",
            phase="output_ready",
            last_action="opencode_output",
            last_message="INFERENCE_QUEUE_TIMEOUT while waiting to start",
            working_directory="/repo",
            stop_reason="smith_idle",
        )
    )

    result = asyncio.run(
        _cloyd_smith_mark_blocked(
            ToolExecutionRequest(
                tool_name="cloyd_smith_mark_blocked",
                arguments={"job_id": job.job_id},
                actor="test",
            )
        )
    )

    assert result["ok"] is True
    assert result["job"]["status"] == "blocked"
    assert result["job"]["error"] == "review evidence is timeout-only; requested objective is not proven"
    assert store.get_heartbeat(job.job_id).working_directory == "/repo"
    assert store.events(job.job_id)[0]["event_type"] == "operator_mark_blocked"


def test_agent_runs_page_and_api_show_canonical_ledger(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Monitor OpenCode without a terminal.",
            current_prompt="Report status.",
        )
    )
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            session_id="ses_web",
            state="running",
            phase="smith_busy",
            last_action="opencode_status",
            last_message="busy",
            working_directory="/repo",
        )
    )
    default_cloyd_smith_supervisor_heartbeat_path(database).write_text(
        '{"ok": true, "status": "loop_ok", "updated_at": "%s"}' % datetime.now(UTC).isoformat(),
        encoding="utf-8",
    )

    client = TestClient(freyja_main.app)
    page = client.get("/agent-runs")
    status = client.get("/agent-runs/api/status")

    assert page.status_code == 200
    assert "Agent Runs" in page.text
    assert "EventSource('/agent-runs/events')" in page.text
    assert "Copy ID" in page.text
    assert "Copy Cloyd Prompt" in page.text
    assert "Current task" in page.text
    assert "Open Session" in page.text
    assert "action === 'start'" in page.text
    assert "Start" in page.text
    assert "Resume/Retry" in page.text
    assert "Check results" in page.text
    assert "Files/diff" in page.text
    assert "Checked rev" in page.text
    assert "Blocker" in page.text
    assert "Copy Replacement Prompt" in page.text
    assert "run.replacement_prompt" in page.text
    assert "run.suggested_prompt" in page.text
    assert "replacementPrompt(run)" in page.text
    assert "Queue Suggested Replacement" in page.text
    assert "action === 'queue-replacement'" in page.text
    assert "Clear" in page.text
    assert "action === 'clear'" in page.text
    assert "Reset Runtime Session" in page.text
    assert "data-runtime-action=\"reset\"" in page.text
    assert "Create Replacement" in page.text
    assert "action === 'replace'" in page.text
    assert "Replacement job prompt" in page.text
    assert "Concrete blocked reason" in page.text
    assert "Perform one read-only inventory" in page.text
    assert "do not call bare python" in page.text
    assert "Follow Up" in page.text
    assert "Supervisor" in page.text
    assert "Cloyd-Smith supervisor" in page.text
    assert "supervisor_ok" in page.text
    assert "supervisor_status" in page.text
    assert "supervisor_age_seconds" in page.text
    assert "do not start a fresh OpenCode session" in page.text
    assert "pasted snapshot is authoritative" in page.text
    assert "treat that tool as stale/wrong" in page.text
    assert "next queue-clearing action" in page.text
    assert "send exactly one bounded follow-up Smith/OpenCode task" in page.text
    assert "/agent-runs/api/status" in page.text
    assert status.status_code == 200
    body = status.json()
    assert body["canonical_ledger"] == str(database)
    assert body["active_count"] == 1
    assert body["attention_count"] == 0
    assert body["terminal_count"] == 0
    assert body["supervisor"]["ok"] is True
    assert body["supervisor"]["status"] == "loop_ok"
    assert body["queue"]["running"] == 1
    assert body["queue"]["needs_review"] == 0
    assert body["queue"]["blocked"] == 0
    assert body["runs"][0]["objective"] == "Monitor OpenCode without a terminal."


def test_agent_runs_api_counts_blocked_jobs_as_attention(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Blocked work.", current_prompt="Try once."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="needs_user_or_operator_review",
            error="timed out",
        ),
    )
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="blocked",
            phase="send_failed",
            last_action="opencode_send",
            last_error="timed out",
            stop_reason="send_failed",
        )
    )

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()

    assert body["active_count"] == 0
    assert body["attention_count"] == 1
    assert body["terminal_count"] == 1
    assert body["queue"]["blocked"] == 1
    assert body["runs"][0]["job_status"] == "blocked"
    assert "OpenCode send failed" in [item["title"] for item in body["diagnostics"]]
    assert "Blocked jobs need review" in [item["title"] for item in body["diagnostics"]]


def test_agent_runs_api_can_start_queued_job(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Queued work.", current_prompt="Do it."))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/start")
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["action"] == "start"
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.QUEUED
    assert loaded.phase == "operator_start_requested"
    assert loaded.next_action == "send_to_smith"
    assert store.get_heartbeat(job.job_id).phase == "operator_start_requested"
    assert store.events(job.job_id)[0]["event_type"] == "operator_start_requested"


def test_agent_runs_api_reports_work_in_progress_instead_of_loop_quiet(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    default_cloyd_smith_supervisor_heartbeat_path(database).write_text(
        '{"ok": true, "status": "loop_ok", "updated_at": "%s"}' % datetime.now(UTC).isoformat(),
        encoding="utf-8",
    )
    store = CloydSmithJobStore(database)
    store.create(CloydSmithJobCreate(objective="Run Atlas cleanup.", current_prompt="Do it."))

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()
    titles = [item["title"] for item in body["diagnostics"]]

    assert body["queue"]["queued"] == 1
    assert "Work in progress" in titles
    assert "Loop quiet" not in titles


def test_agent_runs_api_reports_smith_busy_timeout_diagnostic(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Busy work.", current_prompt="Try once."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="inspect_or_queue_suggested_replacement_after_busy_timeout",
            error="Smith stayed busy for 221s without producing reviewable output.",
        ),
    )
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="blocked",
            phase="smith_busy_timeout",
            last_action="opencode_stop",
            last_error="Smith stayed busy for 221s without producing reviewable output.",
            stop_reason="smith_busy_timeout",
        )
    )

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()
    titles = [item["title"] for item in body["diagnostics"]]

    assert "Smith busy timeout" in titles
    assert "Blocked jobs need review" in titles
    assert "Smith busy timeout stopped the runtime" in body["runs"][0]["next_action"]
    assert "previous bounded job hit a Smith busy timeout" in body["runs"][0]["replacement_prompt"]


def test_agent_runs_api_reports_runtime_inspection_after_repeated_busy_timeouts(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Repeated timeout work.",
            current_prompt="Try once.",
            metadata={
                "source": "agent-runs-suggested-replacement",
                "parent_metadata": {
                    "source": "agent-runs-suggested-replacement",
                    "parent_metadata": {"source": "agent-runs-replacement"},
                },
            },
        )
    )
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="inspect_or_queue_suggested_replacement_after_busy_timeout",
            error="Smith stayed busy for 182s without producing reviewable output.",
        ),
    )
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="blocked",
            phase="smith_busy_timeout",
            last_action="opencode_stop",
            last_error="Smith stayed busy for 182s without producing reviewable output.",
            stop_reason="smith_busy_timeout",
        )
    )

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()
    titles = [item["title"] for item in body["diagnostics"]]

    assert "OpenCode runtime inspection needed" in titles
    assert "repeated Smith busy timeouts" in body["runs"][0]["next_action"]
    assert body["runs"][0]["replacement_prompt"] == ""


def test_agent_runs_api_does_not_call_generic_blocked_queue_quiet(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Blocked work.", current_prompt="Try once."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="blocked_pending_new_prompt_or_runtime_fix",
            error="review evidence is timeout-only; requested objective is not proven",
        ),
    )

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()
    titles = [item["title"] for item in body["diagnostics"]]

    assert body["queue"]["blocked"] == 1
    assert "Blocked jobs need review" in titles
    assert "Loop quiet" not in titles


def test_agent_runs_api_explains_blocked_job_that_needs_sharper_prompt(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Broad Road Mode work.", current_prompt="Build the whole page."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="blocked_pending_new_prompt_or_runtime_fix",
            error="review evidence is timeout-only; requested objective is not proven",
        ),
    )

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()
    titles = [item["title"] for item in body["diagnostics"]]

    assert "sharper replacement job" in body["runs"][0]["next_action"]
    assert "Draft a smaller replacement job" in body["runs"][0]["suggested_prompt"]
    assert "blocked_objective: Broad Road Mode work." in body["runs"][0]["suggested_prompt"]
    assert "Smith, this is a bounded replacement" in body["runs"][0]["replacement_prompt"]
    assert "do not call bare python" in body["runs"][0]["replacement_prompt"]
    assert "Sharper replacement needed" in titles
    assert "Blocked jobs need review" in titles


def test_agent_runs_api_reports_alias_mismatch_diagnostic(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Inspect Atlas dashboard.",
            smith_alias="freyja-code",
            current_prompt="Inspect /home/joe/cloyd-services/dashboard/index.html.",
        )
    )
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, error="wrong host"))

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()

    assert body["runs"][0]["expected_alias"] == "atlas-dashboard"
    assert body["runs"][0]["alias_mismatch"] is True
    assert "smith_alias=atlas-dashboard" in body["runs"][0]["next_action"]
    assert "Wrong Smith alias" in [item["title"] for item in body["diagnostics"]]


def test_agent_runs_api_ignores_stopped_alias_mismatch_diagnostic(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Inspect Atlas dashboard.",
            smith_alias="freyja-code",
            current_prompt="Inspect /home/joe/cloyd-services/dashboard/index.html.",
        )
    )
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.STOPPED, next_action="superseded_by:freyja52-done"))

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()

    assert body["runs"] == []
    assert body["queue"]["stopped"] == 0
    assert body["hidden_terminal_count"] == 1
    assert "Wrong Smith alias" not in [item["title"] for item in body["diagnostics"]]


def test_agent_runs_api_reports_missing_supervisor_heartbeat(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    CloydSmithJobStore(database)

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()
    titles = [item["title"] for item in body["diagnostics"]]

    assert body["supervisor"]["ok"] is False
    assert body["supervisor"]["status"] == "missing"
    assert "Supervisor heartbeat stale" in titles


def test_agent_runs_api_can_retry_blocked_job(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    monkeypatch.setattr(freyja_main, "opencode_health", lambda *, alias=None, timeout_seconds=5: {"ok": True, "alias": alias or "", "base_url": "http://opencode.test", "session_count": 1})

    async def idle_status(request):
        return {"ok": True, "alias": request.arguments["alias"], "state": "idle", "recent_action": None}

    monkeypatch.setattr(freyja_main, "_opencode_status", idle_status)
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Retry work.", current_prompt="Try once."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, next_action="operator_review", error="timed out"))
    old = datetime.now(UTC) - timedelta(seconds=600)
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="blocked",
            phase="smith_busy_timeout",
            last_action="opencode_stop",
            updated_at=old,
            started_at=old,
        )
    )

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["job"]["status"] == "queued"
    assert body["job"]["completed_at"] is None
    assert body["job"]["metadata"]["retry"]["attempts"] == 1
    assert store.get(job.job_id).next_action == "send_to_smith"
    assert store.get(job.job_id).metadata["retry"]["last_error"] == "timed out"
    heartbeat = store.get_heartbeat(job.job_id)
    assert heartbeat.phase == "operator_requeued"
    assert heartbeat.started_at > old
    assert store.events(job.job_id)[0]["event_type"] == "operator_retry"
    assert store.events(job.job_id)[0]["payload"]["attempt"] == 1


def test_agent_runs_api_retry_refuses_fourth_blind_retry(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    monkeypatch.setattr(freyja_main, "opencode_health", lambda *, alias=None, timeout_seconds=5: {"ok": True, "alias": alias or "", "base_url": "http://opencode.test", "session_count": 1})
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Retry work.",
            current_prompt="Try once.",
            metadata={"retry": {"attempts": 3, "last_error": "timed out"}},
        )
    )
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, next_action="operator_review", error="timed out"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/retry")

    assert response.status_code == 409
    assert store.get(job.job_id).status == CloydSmithJobStatus.BLOCKED
    assert store.get(job.job_id).metadata["retry"]["attempts"] == 3
    assert store.events(job.job_id)[0]["event_type"] == "operator_retry_limit_reached"


def test_agent_runs_api_retry_refuses_unhealthy_runtime(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    monkeypatch.setattr(freyja_main, "opencode_health", lambda *, alias=None, timeout_seconds=5: {"ok": False, "alias": alias or "", "base_url": "http://opencode.test", "error": "timed out"})
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Retry work.", current_prompt="Try once."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, next_action="operator_review", error="timed out"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/retry")

    assert response.status_code == 503
    assert store.get(job.job_id).status == CloydSmithJobStatus.BLOCKED
    assert store.events(job.job_id)[0]["event_type"] == "operator_retry_preflight_failed"


def test_agent_runs_api_retry_refuses_busy_runtime_status(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    monkeypatch.setattr(freyja_main, "opencode_health", lambda *, alias=None, timeout_seconds=5: {"ok": True, "alias": alias or "", "base_url": "http://opencode.test", "session_count": 1})

    async def busy_status(request):
        return {"ok": True, "alias": request.arguments["alias"], "state": "idle", "recent_action": {"tool": "bash", "status": "running"}}

    monkeypatch.setattr(freyja_main, "_opencode_status", busy_status)
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Retry work.", current_prompt="Try once."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, next_action="operator_review", error="timed out"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/retry")

    assert response.status_code == 409
    assert "not ready for retry" in response.json()["detail"]
    assert store.get(job.job_id).status == CloydSmithJobStatus.BLOCKED
    assert store.get(job.job_id).next_action == "inspect_or_stop_opencode_session_before_retry"
    assert store.events(job.job_id)[0]["event_type"] == "operator_retry_runtime_busy"


def test_agent_runs_api_retry_refuses_structured_busy_runtime_state(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    monkeypatch.setattr(freyja_main, "opencode_health", lambda *, alias=None, timeout_seconds=5: {"ok": True, "alias": alias or "", "base_url": "http://opencode.test", "session_count": 1})

    async def busy_status(request):
        return {"ok": True, "alias": request.arguments["alias"], "state": {"type": "busy"}, "recent_action": None}

    monkeypatch.setattr(freyja_main, "_opencode_status", busy_status)
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Retry work.", current_prompt="Try once."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, next_action="operator_review", error="timed out"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/retry")

    assert response.status_code == 409
    assert "not ready for retry" in response.json()["detail"]
    assert store.get(job.job_id).status == CloydSmithJobStatus.BLOCKED
    assert store.get(job.job_id).next_action == "inspect_or_stop_opencode_session_before_retry"
    assert store.events(job.job_id)[0]["event_type"] == "operator_retry_runtime_busy"


def test_agent_runs_api_retry_refuses_alias_mismatch_before_runtime(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))

    def fail_health(**_: object) -> dict[str, object]:
        raise AssertionError("alias mismatch should be rejected before OpenCode health check")

    monkeypatch.setattr(freyja_main, "opencode_health", fail_health)
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Inspect Atlas dashboard.",
            smith_alias="freyja-code",
            current_prompt="Inspect /home/joe/cloyd-services/dashboard/index.html.",
        )
    )
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, error="wrong host"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/retry")

    assert response.status_code == 409
    assert "smith_alias=atlas-dashboard" in response.json()["detail"]
    assert store.events(job.job_id)[0]["event_type"] == "operator_retry_alias_mismatch"


def test_agent_runs_runtime_health_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(freyja_main, "opencode_health", lambda *, alias=None, timeout_seconds=5: {"ok": True, "alias": alias or "", "base_url": "http://opencode.test", "session_count": 2})
    async def status(request: ToolExecutionRequest) -> dict:
        return {
            "ok": True,
            "alias": request.arguments["alias"],
            "session": "ses_test",
            "state": {"type": "busy"},
            "working_directory": "/repo",
            "recent_action": {"tool": "bash", "status": "running"},
        }
    monkeypatch.setattr(freyja_main, "_opencode_status", status)

    response = TestClient(freyja_main.app).get("/agent-runs/api/runtime/health")

    assert response.status_code == 200
    body = response.json()
    assert body["session_count"] == 2
    assert body["session"] == "ses_test"
    assert body["state"] == {"type": "busy"}
    assert body["working_directory"] == "/repo"


def test_agent_runs_runtime_stop_endpoint(monkeypatch) -> None:
    async def stop(request: ToolExecutionRequest) -> dict:
        return {"ok": True, "session": "ses_test", "aborted": {"ok": True}}
    monkeypatch.setattr(freyja_main, "_opencode_stop", stop)

    response = TestClient(freyja_main.app).post("/agent-runs/api/runtime/stop")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["action"] == "runtime_stop"
    assert body["session"] == "ses_test"


def test_agent_runs_runtime_reset_endpoint_records_busy_timeout_job_evidence(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Repeated timeout work.",
            current_prompt="Inspect one file.",
            metadata={
                "source": "agent-runs-suggested-replacement",
                "parent_metadata": {
                    "source": "agent-runs-suggested-replacement",
                    "parent_metadata": {"source": "agent-runs-replacement"},
                },
            },
        )
    )
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="inspect_or_queue_suggested_replacement_after_busy_timeout",
            error="Smith stayed busy for 182s without producing reviewable output.",
        ),
    )
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="blocked",
            phase="smith_busy_timeout",
            last_action="opencode_stop",
            last_error="Smith stayed busy for 182s without producing reviewable output.",
            stop_reason="smith_busy_timeout",
        )
    )

    async def stop(request: ToolExecutionRequest) -> dict:
        return {"ok": True, "session": "old_session", "aborted": {"ok": True}}

    async def start(request: ToolExecutionRequest) -> dict:
        return {
            "ok": True,
            "alias": request.arguments["alias"],
            "session": "new_session",
            "working_directory": request.arguments["directory"],
            "state": "idle",
        }

    monkeypatch.setattr(freyja_main, "_opencode_stop", stop)
    monkeypatch.setattr(freyja_main, "_opencode_start", start)

    response = TestClient(freyja_main.app).post("/agent-runs/api/runtime/reset")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["action"] == "runtime_reset"
    assert body["stopped"]["session"] == "old_session"
    assert body["started"]["session"] == "new_session"
    assert body["updated_jobs"] == [job.job_id]
    updated = store.get(job.job_id)
    assert updated.metadata["runtime_reset"]["attempts"] == 1
    assert updated.metadata["runtime_reset"]["started_session"] == "new_session"
    assert "runtime reset completed" in job_status_summary(updated)["next_action"]
    assert store.events(job.job_id)[0]["event_type"] == "operator_runtime_reset"


def test_agent_runs_api_can_mark_review_job_done(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Review work.", current_prompt="Report."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW, next_action="cloyd_review_evidence"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/done")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["job"]["status"] == "done"
    assert store.get(job.job_id).next_action == "operator_reviewed_done"
    assert store.get_heartbeat(job.job_id).phase == "operator_reviewed"


def test_agent_runs_api_can_clear_done_job_from_monitor(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Completed work.", current_prompt="Report."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW, next_action="cloyd_review_evidence"))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.DONE, next_action="operator_reviewed_done"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/clear")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["job"]["status"] == "stopped"
    assert body["job"]["next_action"] == "cleared_from_monitor"
    assert store.get(job.job_id).metadata["cleared_from_monitor"]["previous_status"] == "done"
    assert store.get_heartbeat(job.job_id).phase == "cleared"

    status = TestClient(freyja_main.app).get("/agent-runs/api/status").json()
    assert status["runs"] == []
    assert status["queue"]["done"] == 0
    assert status["queue"]["stopped"] == 0
    assert status["hidden_terminal_count"] == 1


def test_agent_runs_api_rejects_clear_for_unfinished_job(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Review work.", current_prompt="Report."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW, next_action="cloyd_review_evidence"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/clear")

    assert response.status_code == 409


def test_agent_runs_api_can_mark_timeout_review_job_blocked(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Review work.", current_prompt="Report."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW, next_action="cloyd_review_evidence"))
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="needs_review",
            phase="output_ready",
            last_action="opencode_output",
            last_message="INFERENCE_QUEUE_TIMEOUT while waiting to start",
            working_directory="/repo",
            stop_reason="smith_idle",
        )
    )

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/block")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["job"]["status"] == "blocked"
    assert body["job"]["error"] == "review evidence is timeout-only; requested objective is not proven"
    assert store.get(job.job_id).next_action == "blocked_pending_new_prompt_or_runtime_fix"
    assert store.get_heartbeat(job.job_id).phase == "operator_review_blocked"
    assert store.get_heartbeat(job.job_id).working_directory == "/repo"
    assert store.events(job.job_id)[0]["event_type"] == "operator_mark_blocked"


def test_agent_runs_api_can_mark_running_job_blocked_with_reason(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Hung work.", current_prompt="Report."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING, next_action="check_smith_output"))
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="running",
            phase="smith_busy",
            last_action="opencode_status",
            last_message='{"state": {"type": "busy"}}',
            working_directory="/repo",
        )
    )

    response = TestClient(freyja_main.app).post(
        f"/agent-runs/api/jobs/{job.job_id}/block",
        json={"reason": "Smith is hung after python command not found; use .venv/bin/python or python3 in replacement prompt."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["job"]["status"] == "blocked"
    assert "python command not found" in body["job"]["error"]
    assert store.get_heartbeat(job.job_id).last_error == body["job"]["error"]
    assert store.events(job.job_id)[0]["payload"]["reason"] == body["job"]["error"]


def test_agent_runs_api_can_queue_bounded_follow_up(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Review work.", current_prompt="Report."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW, next_action="cloyd_review_evidence"))

    response = TestClient(freyja_main.app).post(
        f"/agent-runs/api/jobs/{job.job_id}/follow-up",
        json={"prompt": "Inspect the timeout and report one concrete blocker or verified diff."},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["job"]["status"] == "queued"
    assert body["job"]["current_prompt"] == "Inspect the timeout and report one concrete blocker or verified diff."
    assert body["job"]["metadata"]["follow_up"]["attempts"] == 1
    assert store.get(job.job_id).next_action == "send_to_smith"
    assert store.get_heartbeat(job.job_id).phase == "operator_follow_up_queued"
    assert store.events(job.job_id)[0]["event_type"] == "operator_follow_up"


def test_agent_runs_api_can_create_replacement_for_blocked_job(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Broad Road Mode work.",
            current_prompt="Build everything.",
            metadata={"feature": "road-mode"},
        )
    )
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="blocked_pending_new_prompt_or_runtime_fix",
            error="review evidence is timeout-only; requested objective is not proven",
        ),
    )

    response = TestClient(freyja_main.app).post(
        f"/agent-runs/api/jobs/{job.job_id}/replace",
        json={
            "objective": "Inventory Road Mode current page state.",
            "prompt": "Inspect src/freyja/roadmode.html and report the smallest missing piece.",
            "smith_alias": "freyja-code",
            "acceptance_criteria": ["Report exact files inspected.", "No edits unless one reversible cleanup is obvious."],
        },
    )

    assert response.status_code == 200
    body = response.json()
    replacement_id = body["replacement_job"]["job_id"]
    assert body["ok"] is True
    assert body["action"] == "replace"
    assert body["replaced_job"]["status"] == "stopped"
    assert body["replaced_job"]["next_action"] == f"superseded_by:{replacement_id}"
    assert body["replacement_job"]["status"] == "queued"
    assert body["replacement_job"]["objective"] == "Inventory Road Mode current page state."
    assert body["replacement_job"]["metadata"]["replaces"] == job.job_id
    assert store.get(job.job_id).metadata["superseded_by"] == replacement_id
    assert store.get(replacement_id).current_prompt == "Inspect src/freyja/roadmode.html and report the smallest missing piece."
    assert store.get_heartbeat(job.job_id).phase == "superseded"
    assert store.get_heartbeat(replacement_id).phase == "replacement_queued"
    assert store.events(job.job_id)[0]["event_type"] == "operator_create_replacement"
    assert store.events(replacement_id)[0]["event_type"] == "submitted_as_replacement"


def test_agent_runs_api_can_queue_suggested_replacement_for_blocked_job(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Broad Road Mode work.",
            current_prompt="Build everything.",
            metadata={"feature": "road-mode"},
        )
    )
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="blocked_pending_new_prompt_or_runtime_fix",
            error="Smith hung after command error `python: command not found`; inspect src/freyja/roadmode.html only.",
        ),
    )
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="blocked",
            phase="operator_review_blocked",
            last_action="operator_mark_blocked",
            last_message="Smith hung after command error `python: command not found`; inspect src/freyja/roadmode.html only.",
            working_directory="/repo",
        )
    )

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/queue-replacement")

    assert response.status_code == 200
    body = response.json()
    replacement_id = body["replacement_job"]["job_id"]
    replacement = store.get(replacement_id)
    assert body["ok"] is True
    assert body["action"] == "queue-replacement"
    assert body["replaced_job"]["status"] == "stopped"
    assert body["replaced_job"]["next_action"] == f"superseded_by:{replacement_id}"
    assert body["replacement_job"]["status"] == "queued"
    assert "Suggested replacement for blocked job" in body["replacement_job"]["objective"]
    assert replacement.metadata["source"] == "agent-runs-suggested-replacement"
    assert replacement.metadata["replaces"] == job.job_id
    assert "Smith, this is a bounded replacement" in replacement.current_prompt
    assert "do not call bare python" in replacement.current_prompt
    assert "working_directory: /repo" in replacement.current_prompt
    assert store.get(job.job_id).metadata["superseded_by"] == replacement_id
    assert store.get_heartbeat(job.job_id).phase == "superseded"
    assert store.get_heartbeat(replacement_id).phase == "suggested_replacement_queued"
    assert store.events(job.job_id)[0]["event_type"] == "operator_queue_suggested_replacement"
    assert store.events(replacement_id)[0]["event_type"] == "submitted_as_suggested_replacement"


def test_agent_runs_api_can_queue_smaller_replacement_after_busy_timeout(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Timed out bounded Road Mode inventory.", current_prompt="Inspect one file."))
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="inspect_or_queue_suggested_replacement_after_busy_timeout",
            error="Smith stayed busy for 221s without producing reviewable output.",
        ),
    )
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="blocked",
            phase="smith_busy_timeout",
            last_action="opencode_stop",
            last_error="Smith stayed busy for 221s without producing reviewable output.",
            working_directory="/repo",
            stop_reason="smith_busy_timeout",
        )
    )

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/queue-replacement")

    assert response.status_code == 200
    body = response.json()
    replacement_id = body["replacement_job"]["job_id"]
    replacement = store.get(replacement_id)
    assert body["action"] == "queue-replacement"
    assert body["replaced_job"]["next_action"] == f"superseded_by:{replacement_id}"
    assert "previous bounded job hit a Smith busy timeout" in replacement.current_prompt
    assert "Perform only one read-only check" in replacement.current_prompt
    assert store.get_heartbeat(replacement_id).phase == "suggested_replacement_queued"


def test_agent_runs_api_rejects_suggested_replacement_after_repeated_busy_timeouts(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Repeated timeout work.",
            current_prompt="Inspect one file.",
            metadata={
                "source": "agent-runs-suggested-replacement",
                "parent_metadata": {
                    "source": "agent-runs-suggested-replacement",
                    "parent_metadata": {"source": "agent-runs-replacement"},
                },
            },
        )
    )
    store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="inspect_or_queue_suggested_replacement_after_busy_timeout",
            error="Smith stayed busy for 182s without producing reviewable output.",
        ),
    )
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="blocked",
            phase="smith_busy_timeout",
            last_action="opencode_stop",
            last_error="Smith stayed busy for 182s without producing reviewable output.",
            working_directory="/repo",
            stop_reason="smith_busy_timeout",
        )
    )

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/queue-replacement")

    assert response.status_code == 409
    assert "does not have a suggested replacement action" in response.json()["detail"]


def test_agent_runs_api_rejects_second_bounded_follow_up(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Review work.",
            current_prompt="Report.",
            metadata={"follow_up": {"attempts": 1}},
        )
    )
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW, next_action="cloyd_review_evidence"))

    response = TestClient(freyja_main.app).post(
        f"/agent-runs/api/jobs/{job.job_id}/follow-up",
        json={"prompt": "Try again."},
    )

    assert response.status_code == 409
    assert store.get(job.job_id).status == CloydSmithJobStatus.NEEDS_REVIEW
    assert store.events(job.job_id)[0]["event_type"] == "operator_follow_up_limit_reached"


def test_agent_runs_api_rejects_unsafe_action_for_state(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Queued work.", current_prompt="Run."))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/done")

    assert response.status_code == 409


def test_agent_runs_api_rejects_block_for_terminal_job(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Done work.", current_prompt="Run."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.DONE))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/block")

    assert response.status_code == 409
    assert store.get(job.job_id).status == CloydSmithJobStatus.DONE


def test_agent_runs_api_explains_timeout_review_evidence(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Review timeout evidence.", current_prompt="Report."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW, next_action="cloyd_review_evidence"))
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job.job_id,
            agent="smith",
            alias="freyja-code",
            state="needs_review",
            phase="output_ready",
            last_action="opencode_output",
            last_message="INFERENCE_QUEUE_TIMEOUT while waiting to start",
            stop_reason="smith_idle",
        )
    )

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()
    titles = [item["title"] for item in body["diagnostics"]]

    assert "Inference queue timeout evidence" in titles
    assert "Human or Cloyd review required" in titles


def test_agent_runs_api_explains_retry_attempts(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Retry-heavy work.",
            current_prompt="Report.",
            metadata={"retry": {"attempts": 2, "last_error": "timed out"}},
        )
    )
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, next_action="operator_review", error="timed out"))

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()
    titles = [item["title"] for item in body["diagnostics"]]

    assert body["runs"][0]["retry_attempts"] == 2
    assert "Retry attempts accumulating" in titles


def test_agent_runs_api_ignores_retry_attempts_for_done_jobs(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Resolved retry-heavy work.",
            current_prompt="Report.",
            metadata={"retry": {"attempts": 2, "last_error": "timed out"}},
        )
    )
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.DONE, next_action="operator_reviewed_done"))

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()
    titles = [item["title"] for item in body["diagnostics"]]

    assert body["runs"][0]["retry_attempts"] == 2
    assert "Retry attempts accumulating" not in titles


def test_agent_runs_api_explains_follow_up_attempts(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    store = CloydSmithJobStore(database)
    job = store.create(
        CloydSmithJobCreate(
            objective="Followed-up work.",
            current_prompt="Report.",
            metadata={"follow_up": {"attempts": 1}},
        )
    )
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW, next_action="cloyd_review_evidence"))

    body = TestClient(freyja_main.app).get("/agent-runs/api/status").json()
    titles = [item["title"] for item in body["diagnostics"]]

    assert body["runs"][0]["follow_up_attempts"] == 1
    assert "Follow-up already used" in titles


def test_agent_runs_requeue_incomplete_jobs(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    stop_calls = []

    async def fake_stop(request):
        stop_calls.append(request.arguments)
        return {"ok": True, "session": "ses_busy", "aborted": True}

    monkeypatch.setattr(freyja_main, "_opencode_stop", fake_stop)
    store = CloydSmithJobStore(database)
    running = store.create(CloydSmithJobCreate(objective="Running work.", current_prompt="Do it."))
    review = store.create(CloydSmithJobCreate(objective="Review work.", current_prompt="Review it."))
    blocked = store.create(CloydSmithJobCreate(objective="Blocked work.", current_prompt="Blocked."))
    done = store.create(CloydSmithJobCreate(objective="Done work.", current_prompt="Done."))
    store.update(running.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING))
    store.update(review.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.NEEDS_REVIEW))
    store.update(blocked.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, error="blocked"))
    store.update(done.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.DONE))

    response = TestClient(freyja_main.app).post("/agent-runs/api/jobs/requeue-incomplete")
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert set(body["updated_jobs"]) == {running.job_id, review.job_id, blocked.job_id}
    assert stop_calls == [{"alias": "freyja-code"}]
    assert store.get(running.job_id).status == CloydSmithJobStatus.QUEUED
    assert store.get(review.job_id).status == CloydSmithJobStatus.QUEUED
    assert store.get(blocked.job_id).status == CloydSmithJobStatus.QUEUED
    assert store.get(done.job_id).status == CloydSmithJobStatus.DONE
    assert store.get_heartbeat(blocked.job_id).phase == "operator_bulk_requeued"


def test_agent_runs_stop_job_aborts_running_runtime_before_stopped(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    stop_calls = []

    async def fake_status(request):
        return {"ok": True, "session": "ses_stop", "state": {"type": "busy"}}

    async def fake_stop(request):
        stop_calls.append(request.arguments)
        return {"ok": True, "session": "ses_stop", "aborted": True}

    monkeypatch.setattr(freyja_main, "_opencode_status", fake_status)
    monkeypatch.setattr(freyja_main, "_opencode_stop", fake_stop)
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Running work.", current_prompt="Do it."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING, session_id="ses_stop"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/stop")
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["action"] == "stop"
    assert body["runtime_stop"]["session"] == "ses_stop"
    assert stop_calls == [{"alias": "freyja-code"}]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.STOPPED
    assert loaded.stop_intent == "immediate"
    assert loaded.phase == "operator_stopped"
    assert store.get_heartbeat(job.job_id).phase == "operator_stopped"
    events = [event["event_type"] for event in store.events(job.job_id, limit=5)]
    assert "operator_stop_runtime" in events
    assert "operator_stop" in events


def test_agent_runs_stop_job_records_active_command_before_abort(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    calls = []

    async def fake_status(request):
        calls.append(("status", request.arguments))
        return {
            "ok": True,
            "session": "ses_stop",
            "state": {"type": "busy"},
            "recent_action": {"tool": "bash", "status": "running", "command": "sleep 60"},
        }

    async def fake_stop(request):
        calls.append(("stop", request.arguments))
        return {"ok": True, "session": "ses_stop", "aborted": True}

    monkeypatch.setattr(freyja_main, "_opencode_status", fake_status)
    monkeypatch.setattr(freyja_main, "_opencode_stop", fake_stop)
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Running shell work.", current_prompt="Do it."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING, session_id="ses_stop"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/stop")
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert calls == [
        ("status", {"alias": "freyja-code"}),
        ("stop", {"alias": "freyja-code"}),
    ]
    loaded = store.get(job.job_id)
    before_stop = loaded.last_evidence["runtime_status_before_stop"]
    assert before_stop["recent_action"]["tool"] == "bash"
    assert before_stop["recent_action"]["status"] == "running"
    assert before_stop["recent_action"]["command"] == "sleep 60"
    stop_events = [event for event in store.events(job.job_id, limit=10) if event["event_type"] == "operator_stop_runtime"]
    assert stop_events
    assert stop_events[0]["payload"]["runtime_status_before_stop"]["recent_action"]["command"] == "sleep 60"


def test_agent_runs_stop_job_attempts_stop_when_status_preflight_fails(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    calls = []

    async def fake_status(request):
        calls.append(("status", request.arguments))
        return {"ok": False, "session": "ses_stop", "error": "status timeout"}

    async def fake_stop(request):
        calls.append(("stop", request.arguments))
        return {"ok": True, "session": "ses_stop", "aborted": True}

    monkeypatch.setattr(freyja_main, "_opencode_status", fake_status)
    monkeypatch.setattr(freyja_main, "_opencode_stop", fake_stop)
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Running work.", current_prompt="Do it."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING, session_id="ses_stop"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/stop")

    assert response.status_code == 200
    assert calls == [
        ("status", {"alias": "freyja-code"}),
        ("stop", {"alias": "freyja-code"}),
    ]
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.STOPPED
    assert loaded.last_evidence["runtime_status_before_stop"]["error"] == "status timeout"


def test_agent_runs_stop_job_keeps_stopping_when_runtime_stop_fails(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))

    async def fake_status(request):
        return {"ok": True, "session": "ses_stop", "state": {"type": "busy"}}

    async def fake_stop(request):
        return {"ok": False, "session": "ses_stop", "error": "permission wait"}

    monkeypatch.setattr(freyja_main, "_opencode_status", fake_status)
    monkeypatch.setattr(freyja_main, "_opencode_stop", fake_stop)
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Running work.", current_prompt="Do it."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING, session_id="ses_stop"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/stop")

    assert response.status_code == 503
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.STOPPING
    assert loaded.phase == "operator_stop_failed"
    assert loaded.next_action == "OpenCode stop failed; reconcile runtime before restart"
    assert store.get_heartbeat(job.job_id).phase == "operator_stop_failed"


def test_agent_runs_stop_after_current_turn_persists_intent_without_runtime_stop(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))

    async def fail_stop(request):
        raise AssertionError("stop-after-current-turn must not abort the runtime")

    monkeypatch.setattr(freyja_main, "_opencode_stop", fail_stop)
    store = CloydSmithJobStore(database)
    job = store.create(CloydSmithJobCreate(objective="Running work.", current_prompt="Do it."))
    store.update(job.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.RUNNING, session_id="ses_stop"))

    response = TestClient(freyja_main.app).post(f"/agent-runs/api/jobs/{job.job_id}/stop-after-current-turn")
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert body["action"] == "stop-after-current-turn"
    loaded = store.get(job.job_id)
    assert loaded.status == CloydSmithJobStatus.RUNNING
    assert loaded.phase == "stop_after_current_turn_requested"
    assert loaded.stop_intent == "after_current_turn"
    assert loaded.next_action == "waiting for current turn boundary before stopping"
    assert store.get_heartbeat(job.job_id).phase == "stop_after_current_turn_requested"
    assert store.events(job.job_id)[0]["event_type"] == "operator_stop_after_current_turn"


def test_agent_runs_stop_all_incomplete_jobs(tmp_path, monkeypatch) -> None:
    database = tmp_path / "jobs.db"
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(database))
    stop_calls = []

    async def fake_stop(request):
        stop_calls.append(request.arguments)
        return {"ok": True, "session": "ses_busy", "aborted": True}

    monkeypatch.setattr(freyja_main, "_opencode_stop", fake_stop)
    store = CloydSmithJobStore(database)
    queued = store.create(CloydSmithJobCreate(objective="Queued work.", current_prompt="Do it."))
    blocked = store.create(CloydSmithJobCreate(objective="Blocked work.", current_prompt="Blocked."))
    done = store.create(CloydSmithJobCreate(objective="Done work.", current_prompt="Done."))
    store.update(blocked.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.BLOCKED, error="blocked"))
    store.update(done.job_id, CloydSmithJobUpdate(status=CloydSmithJobStatus.DONE))

    response = TestClient(freyja_main.app).post("/agent-runs/api/jobs/stop-all")
    body = response.json()

    assert response.status_code == 200
    assert body["ok"] is True
    assert set(body["updated_jobs"]) == {queued.job_id, blocked.job_id}
    assert stop_calls == [{"alias": "freyja-code"}]
    assert store.get(queued.job_id).status == CloydSmithJobStatus.STOPPED
    assert store.get(blocked.job_id).status == CloydSmithJobStatus.STOPPED
    assert store.get(done.job_id).status == CloydSmithJobStatus.DONE
    assert store.get_heartbeat(queued.job_id).phase == "operator_bulk_stopped"


def test_agent_runs_page_is_public_when_connector_auth_is_enabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(freyja_main.settings, "freyja_connector_token", "secret")
    monkeypatch.setattr(freyja_main.settings, "cloyd_smith_loop_database_path", str(tmp_path / "jobs.db"))
    client = TestClient(freyja_main.app)

    page = client.get("/agent-runs")
    api = client.get("/agent-runs/api/status")

    assert page.status_code == 200
    assert api.status_code == 200
