#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import contextlib
import fcntl
import json
import os
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from freyja.config import settings
from freyja.cloyd_smith_loop import (
    AgentRunHeartbeat,
    CloydSmithJobStatus,
    CloydSmithJobStore,
    CloydSmithJobUpdate,
    capture_revision_evidence,
    default_cloyd_smith_supervisor_heartbeat_path,
    enrich_loop_status_with_runtime,
    loop_status_payload,
    read_supervisor_heartbeat,
)
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.opencode_runtime import _opencode_output, _opencode_send, _opencode_start, _opencode_status, _opencode_stop, opencode_health


DEFAULT_STALE_AFTER_SECONDS = 300
DEFAULT_SEND_TIMEOUT_SECONDS = 45
DEFAULT_FIRST_RESPONSE_BUDGET_SECONDS = 900
DEFAULT_CHECK_TIMEOUT_SECONDS = int(os.environ.get("CLOYD_SMITH_CHECK_TIMEOUT_SECONDS", "300") or "300")
DEFAULT_MAX_REPAIR_ATTEMPTS = 2
# The dedicated coder is large and can take several minutes to inspect a
# repository and execute its first bounded change.  Progress is surfaced by
# the heartbeat; do not mistake a legitimate long turn for a stuck worker.
DEFAULT_MAX_BUSY_SECONDS = int(os.environ.get("CLOYD_SMITH_WHOLE_TASK_DEADLINE_SECONDS", "0") or "0")
SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization:\s*basic\s+)[A-Za-z0-9+/=._-]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(api[_-]?key['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"),
    re.compile(r"(?i)(password['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"),
    re.compile(r"(?i)(token['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"),
)


async def _run_once(store: CloydSmithJobStore) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    results.extend(_recheck_verified_jobs(store))
    touched_job_ids = {str(result.get("job_id")) for result in results if result.get("job_id")}
    for warning in store.mark_stale_runs():
        results.append({"job_id": warning.job_id, "status": "running", "action": "no_activity_warning"})
    for job in store.list_active(limit=20):
        if job.job_id in touched_job_ids:
            continue
        if job.status == CloydSmithJobStatus.NEEDS_REVIEW:
            continue
        if job.status in {CloydSmithJobStatus.UNKNOWN, CloydSmithJobStatus.WAITING_FOR_INPUT}:
            results.append(await _reconcile_uncertain_job(store, job))
            continue
        if job.status == CloydSmithJobStatus.NEEDS_ATTENTION:
            results.append(_queue_repair_if_allowed(store, job))
            continue
        if job.status == CloydSmithJobStatus.VERIFYING:
            results.append(await _verify_completed_turn(store, job, job.last_evidence or {}, phase="verifying_resumed"))
            continue
        if job.status == CloydSmithJobStatus.STALE:
            results.append(await _recover_stale_job(store, job))
            continue
        if job.status == CloydSmithJobStatus.STOPPING:
            results.append(await _stop_job(store, job.job_id))
            continue
        if job.status == CloydSmithJobStatus.QUEUED:
            if job.session_id and job.submission_id:
                store.add_event(
                    job.job_id,
                    "submission_reconciled",
                    {"session_id": job.session_id, "submission_id": job.submission_id},
                )
                _record_heartbeat(
                    store,
                    job_id=job.job_id,
                    alias=job.smith_alias,
                    session_id=job.session_id,
                    state="running",
                    phase="reconciled_existing_submission",
                    last_action="opencode_status",
                    last_message="Queued job already had an OpenCode submission; resumed observation without duplicate dispatch.",
                    reset_started_at=True,
                )
                updated = store.update(
                    job.job_id,
                    CloydSmithJobUpdate(
                        status=CloydSmithJobStatus.RUNNING,
                        phase="reconciled_existing_submission",
                        next_action="check_smith_output",
                        last_evidence={"session_id": job.session_id, "submission_id": job.submission_id},
                    ),
                )
                results.append({"job_id": job.job_id, "status": updated.status.value, "action": "reconciled_existing_submission"})
                continue
            external_busy = await _external_worker_busy(store, job)
            if external_busy:
                _record_heartbeat(
                    store,
                    job_id=job.job_id,
                    alias=job.smith_alias,
                    session_id=str(external_busy.get("session") or "") or None,
                    state="unknown",
                    phase="external_worker_busy",
                    last_action="opencode_status",
                    last_message=_summary_text(external_busy),
                    last_error="OpenCode has active work outside this queued ledger job; dispatch frozen.",
                    working_directory=str(external_busy.get("working_directory") or ""),
                )
                store.update(
                    job.job_id,
                    CloydSmithJobUpdate(
                        next_action="external OpenCode work is active; wait or stop it before dispatch",
                        last_evidence=_bounded(external_busy),
                    ),
                )
                results.append({"job_id": job.job_id, "status": "unknown", "action": "dispatch_blocked_external_worker"})
                continue
            prompt = _smith_prompt(job)
            existing_heartbeat = store.get_heartbeat(job.job_id)
            if existing_heartbeat and existing_heartbeat.session_id and (job.metadata.get("follow_up") or job.metadata.get("retry") or job.metadata.get("repair")):
                started = {"ok": True, "session": existing_heartbeat.session_id, "reused": True}
            else:
                # A durable job is an isolated coding run. Reuse the job's own
                # session for repair cycles, but start a fresh one for a new task.
                started = await _opencode_start(
                    ToolExecutionRequest(
                        tool_name="opencode_start",
                        arguments={"alias": job.smith_alias, "directory": settings.repository_root},
                        actor="cloyd-smith-loop-5.2",
                    )
                )
            store.add_event(job.job_id, "smith_session_started", _bounded(started))
            if not started.get("ok"):
                updated = store.update(
                    job.job_id,
                    CloydSmithJobUpdate(
                        status=CloydSmithJobStatus.BLOCKED,
                        next_action="fix_runtime_or_retry",
                        last_evidence=_bounded(started),
                        error=str(started.get("error") or "Unable to create a fresh Smith session."),
                    ),
                )
                _record_heartbeat(
                    store,
                    job_id=job.job_id,
                    alias=job.smith_alias,
                    state="blocked",
                    phase="session_start_failed",
                    last_action="opencode_start",
                    last_error=str(started.get("error") or "Unable to create a fresh Smith session."),
                    stop_reason="session_start_failed",
                )
                results.append({"job_id": job.job_id, "status": updated.status.value, "action": "session_start_failed"})
                continue
            store.update(
                job.job_id,
                CloydSmithJobUpdate(
                    status=CloydSmithJobStatus.RUNNING,
                    phase="fresh_session_created",
                    session_id=str(started.get("session") or "") or None,
                    next_action="await_smith_send_result",
                    last_evidence={"phase": "sending_to_smith"},
                ),
            )
            _record_heartbeat(
                store,
                job_id=job.job_id,
                alias=job.smith_alias,
                session_id=str(started.get("session") or "") or None,
                state="running",
                phase="fresh_session_created",
                last_action="opencode_send",
                last_message="Fresh Smith session created; sending bounded prompt.",
                reset_started_at=True,
            )
            output = await _opencode_send(
                ToolExecutionRequest(
                    tool_name="opencode_send",
                    arguments={"alias": job.smith_alias, "prompt": prompt, "timeout_seconds": DEFAULT_SEND_TIMEOUT_SECONDS},
                    actor="cloyd-smith-loop-5.2",
                )
            )
            store.add_event(job.job_id, "smith_send", _bounded(output))
            if _send_timed_out(output):
                status = await _opencode_status(
                    ToolExecutionRequest(
                        tool_name="opencode_status",
                        arguments={"alias": job.smith_alias},
                        actor="cloyd-smith-loop-5.2",
                    )
                )
                store.add_event(job.job_id, "smith_status_after_send_timeout", _bounded(status))
                if status.get("ok") and status.get("state") == "idle":
                    review = await _opencode_output(
                        ToolExecutionRequest(
                            tool_name="opencode_output",
                            arguments={"alias": job.smith_alias, "limit": 3},
                            actor="cloyd-smith-loop-5.2",
                        )
                    )
                    store.add_event(job.job_id, "smith_output_after_send_timeout", _bounded(review))
                    updated = store.update(
                        job.job_id,
                        CloydSmithJobUpdate(
                            status=CloydSmithJobStatus.VERIFYING,
                            phase="output_ready_after_send_timeout",
                            session_id=str(review.get("session") or status.get("session") or "") or None,
                            next_action="run independent check commands",
                            last_evidence=_bounded(review),
                            error="",
                        ),
                    )
                    results.append(
                        await _verify_completed_turn(
                            store,
                            updated,
                            review,
                            working_directory=str(status.get("working_directory") or ""),
                            phase="output_ready_after_send_timeout",
                            stop_reason="smith_idle_after_send_timeout",
                            no_check_action="harvested_output_after_send_timeout",
                        )
                    )
                    continue
                if status.get("ok") and status.get("state") != "idle":
                    _record_heartbeat(
                        store,
                        job_id=job.job_id,
                        alias=job.smith_alias,
                        session_id=str(status.get("session") or "") or None,
                        state="running",
                        phase="smith_busy_after_send_timeout",
                        last_action=_last_action_name(status) or "opencode_status",
                        last_message=_summary_text(status),
                        working_directory=str(status.get("working_directory") or ""),
                    )
                    store.update(
                        job.job_id,
                        CloydSmithJobUpdate(
                            status=CloydSmithJobStatus.RUNNING,
                            phase="smith_busy_after_send_timeout",
                            session_id=str(status.get("session") or "") or None,
                            next_action="check_smith_output",
                            last_evidence=_bounded(status),
                            error="",
                        ),
                    )
                    results.append({"job_id": job.job_id, "status": "running", "action": "send_timed_out_but_smith_busy"})
                    continue
            next_status = CloydSmithJobStatus.RUNNING if output.get("ok") else CloydSmithJobStatus.BLOCKED
            session_id = str(output.get("session") or "") or None
            working_directory = str(output.get("working_directory") or "")
            _record_heartbeat(
                store,
                job_id=job.job_id,
                alias=job.smith_alias,
                session_id=session_id,
                state=next_status.value,
                phase="sent_to_smith" if output.get("ok") else "send_failed",
                last_action="opencode_send",
                last_message=_summary_text(output),
                last_error="" if output.get("ok") else str(output.get("error") or "Smith send failed"),
                working_directory=working_directory,
                stop_reason=None if output.get("ok") else "send_failed",
            )
            updated = store.update(
                job.job_id,
                CloydSmithJobUpdate(
                    status=next_status,
                    phase="sent_to_smith" if output.get("ok") else "send_failed",
                    session_id=session_id,
                    submission_id=str(output.get("submission_id") or output.get("message") or "") or None,
                    next_action="check_smith_output" if output.get("ok") else "needs_user_or_operator_review",
                    last_evidence=_bounded(output),
                    error=None if output.get("ok") else str(output.get("error") or "Smith send failed"),
                ),
            )
            results.append({"job_id": job.job_id, "status": updated.status.value, "action": "sent_to_smith"})
            continue

        if job.status == CloydSmithJobStatus.RUNNING:
            status = await _opencode_status(
                ToolExecutionRequest(
                    tool_name="opencode_status",
                    arguments={"alias": job.smith_alias},
                    actor="cloyd-smith-loop-5.2",
                )
            )
            store.add_event(job.job_id, "smith_status", _bounded(status))
            if not status.get("ok"):
                _record_heartbeat(
                    store,
                    job_id=job.job_id,
                    alias=job.smith_alias,
                    session_id=str(status.get("session") or "") or None,
                    state="unknown",
                    phase="telemetry_unavailable",
                    last_action="opencode_status",
                    last_error=str(status.get("error") or "Smith status failed"),
                    working_directory=str(status.get("working_directory") or ""),
                )
                updated = store.update(
                    job.job_id,
                    CloydSmithJobUpdate(
                        status=CloydSmithJobStatus.UNKNOWN,
                        phase="telemetry_unavailable",
                        session_id=str(status.get("session") or "") or None,
                        next_action="freeze dispatch and reconcile OpenCode telemetry",
                        last_evidence=_bounded(status),
                        error=str(status.get("error") or "Smith status failed"),
                    ),
                )
                results.append({"job_id": job.job_id, "status": updated.status.value, "action": "telemetry_unknown"})
                continue
            if status.get("state") != "idle":
                if _status_indicates_waiting_for_input(status):
                    _record_heartbeat(
                        store,
                        job_id=job.job_id,
                        alias=job.smith_alias,
                        session_id=str(status.get("session") or "") or None,
                        state=CloydSmithJobStatus.WAITING_FOR_INPUT.value,
                        phase="permission_wait",
                        last_action=_last_action_name(status) or "opencode_status",
                        last_message=_summary_text(status),
                        working_directory=str(status.get("working_directory") or ""),
                    )
                    updated = store.update(
                        job.job_id,
                        CloydSmithJobUpdate(
                            status=CloydSmithJobStatus.WAITING_FOR_INPUT,
                            phase="permission_wait",
                            session_id=str(status.get("session") or "") or None,
                            next_action="worker is waiting for permission or input; answer in the OpenCode session",
                            last_evidence=_bounded(status),
                            error="",
                        ),
                    )
                    results.append({"job_id": job.job_id, "status": updated.status.value, "action": "permission_wait"})
                    continue
                long_busy = await _record_long_busy_warning_if_needed(store, job, status)
                if long_busy:
                    results.append(long_busy)
                    continue
                last_action = _last_action_name(status) or "opencode_status"
                last_message = _summary_text(status)
                existing = store.get_heartbeat(job.job_id)
                meaningful = (
                    existing is None
                    or existing.phase != "smith_busy"
                    or existing.last_action != last_action
                    or existing.last_message != last_message
                )
                _record_heartbeat(
                    store,
                    job_id=job.job_id,
                    alias=job.smith_alias,
                    session_id=str(status.get("session") or "") or None,
                    state="running",
                    phase="smith_busy",
                    last_action=last_action,
                    last_message=last_message,
                    working_directory=str(status.get("working_directory") or ""),
                    meaningful=meaningful,
                )
                next_action = "waiting for current turn boundary before stopping" if job.stop_intent == "after_current_turn" else "check_smith_output"
                store.update(job.job_id, CloydSmithJobUpdate(next_action=next_action, last_evidence=_bounded(status)))
                results.append({"job_id": job.job_id, "status": "running", "action": "still_running"})
                continue
            output = await _opencode_output(
                ToolExecutionRequest(
                    tool_name="opencode_output",
                    arguments={"alias": job.smith_alias, "limit": 3},
                    actor="cloyd-smith-loop-5.2",
                )
            )
            store.add_event(job.job_id, "smith_output", _bounded(output))
            if job.stop_intent == "after_current_turn":
                results.append(_stop_after_current_turn(store, job, output, working_directory=str(status.get("working_directory") or "")))
                continue
            updated = store.update(
                job.job_id,
                CloydSmithJobUpdate(
                    status=CloydSmithJobStatus.VERIFYING,
                    phase="output_ready",
                    session_id=str(output.get("session") or status.get("session") or "") or None,
                    next_action="run independent check commands",
                    last_evidence=_bounded(output),
                ),
            )
            results.append(
                await _verify_completed_turn(
                    store,
                    updated,
                    output,
                    working_directory=str(status.get("working_directory") or ""),
                    phase="output_ready",
                    stop_reason="smith_idle",
                )
            )
    return results


def _recheck_verified_jobs(store: CloydSmithJobStore) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for job in store.list_recent_terminal(limit=50):
        if job.status != CloydSmithJobStatus.VERIFIED:
            continue
        previous = job.revision_evidence or {}
        previous_head = str(previous.get("head") or "")
        previous_tree = str(previous.get("working_tree_sha256") or "")
        if not previous_head or not previous_tree:
            continue
        try:
            current = capture_revision_evidence(check_commands=job.check_commands, check_results=[])
        except Exception as exc:
            store.add_event(job.job_id, "verified_recheck_failed", {"error": str(exc)})
            updated = store.update(
                job.job_id,
                CloydSmithJobUpdate(
                    status=CloydSmithJobStatus.NEEDS_ATTENTION,
                    phase="verified_recheck_failed",
                    next_action="verification evidence could not be refreshed; inspect before trusting verified",
                    error=str(exc),
                ),
            )
            _record_heartbeat(
                store,
                job_id=job.job_id,
                alias=job.smith_alias,
                session_id=job.session_id,
                state=updated.status.value,
                phase=updated.phase,
                last_action="verification_recheck",
                last_error=str(exc),
                stop_reason="verification_recheck_failed",
            )
            results.append({"job_id": job.job_id, "status": updated.status.value, "action": "verified_recheck_failed"})
            continue
        current_head = str(current.get("head") or "")
        current_tree = str(current.get("working_tree_sha256") or "")
        if current_head == previous_head and current_tree == previous_tree:
            continue
        store.add_event(
            job.job_id,
            "verified_evidence_stale",
            {
                "previous_head": previous_head,
                "current_head": current_head,
                "previous_working_tree_sha256": previous_tree,
                "current_working_tree_sha256": current_tree,
            },
        )
        if not job.check_commands:
            updated = store.update(
                job.job_id,
                CloydSmithJobUpdate(
                    status=CloydSmithJobStatus.NEEDS_REVIEW,
                    phase="verified_stale_after_edit",
                    next_action="working tree changed after verification; record check commands before marking verified again",
                    revision_evidence=current,
                    error="Verified evidence is stale because HEAD or working-tree content changed.",
                ),
            )
            _record_heartbeat(
                store,
                job_id=job.job_id,
                alias=job.smith_alias,
                session_id=job.session_id,
                state=updated.status.value,
                phase=updated.phase,
                last_action="verification_recheck",
                last_error=updated.error or "",
                stop_reason="verified_stale_after_edit",
            )
            results.append({"job_id": job.job_id, "status": updated.status.value, "action": "verified_stale_after_edit"})
            continue

        check_results = _run_check_commands(job.check_commands)
        all_passed = all(int(result.get("exit_code") or 0) == 0 and not result.get("timed_out") for result in check_results)
        evidence = _capture_revision_evidence(job, {"result": "verification refreshed after working-tree change"}, check_results=check_results)
        status = CloydSmithJobStatus.VERIFIED if all_passed else CloydSmithJobStatus.NEEDS_ATTENTION
        phase = "verified" if all_passed else "checks_failed_after_stale_verification"
        error = "" if all_passed else _check_failure_summary(check_results)
        next_action = "verified evidence refreshed after working-tree change" if all_passed else "repair failing checks in same Smith session or request input"
        updated = store.update(
            job.job_id,
            CloydSmithJobUpdate(
                status=status,
                phase=phase,
                next_action=next_action,
                last_evidence={"previous_revision_evidence": previous, "check_results": check_results},
                revision_evidence=evidence,
                error=error,
            ),
        )
        store.add_event(
            job.job_id,
            "verified_recheck_finished",
            {"status": updated.status.value, "check_results": check_results, "working_tree_sha256": evidence.get("working_tree_sha256")},
        )
        _record_heartbeat(
            store,
            job_id=job.job_id,
            alias=job.smith_alias,
            session_id=job.session_id,
            state=updated.status.value,
            phase=updated.phase,
            last_action="verification_recheck",
            last_message="Verified evidence refreshed." if all_passed else "",
            last_error=error,
            stop_reason="checks_passed" if all_passed else "checks_failed",
        )
        results.append({"job_id": job.job_id, "status": updated.status.value, "action": "verified_rechecked" if all_passed else "stale_verification_checks_failed"})
    return results


def _queue_repair_if_allowed(store: CloydSmithJobStore, job) -> dict[str, Any]:
    metadata = dict(job.metadata or {})
    repair = dict(metadata.get("repair") or {})
    attempts = int(repair.get("attempts") or 0)
    evidence = job.revision_evidence or {}
    failure_signature = _failure_signature(evidence.get("check_results") or [])
    working_tree_sha256 = str(evidence.get("working_tree_sha256") or "")
    previous_signature = repair.get("last_failure_signature")
    previous_tree = repair.get("last_working_tree_sha256")
    session_id = job.session_id or (store.get_heartbeat(job.job_id).session_id if store.get_heartbeat(job.job_id) else None)

    if not session_id:
        store.add_event(job.job_id, "repair_missing_session", {"status": job.status.value, "phase": job.phase})
        updated = store.update(
            job.job_id,
            CloydSmithJobUpdate(
                next_action="repair requires the original Smith session; request input before retrying",
                error=job.error or "No Smith session is available for same-session repair.",
            ),
        )
        _record_heartbeat(
            store,
            job_id=job.job_id,
            alias=job.smith_alias,
            state=CloydSmithJobStatus.NEEDS_ATTENTION.value,
            phase="repair_missing_session",
            last_action="repair_preflight",
            last_error=updated.error or "",
            stop_reason="repair_missing_session",
        )
        return {"job_id": job.job_id, "status": updated.status.value, "action": "repair_missing_session"}

    if attempts >= DEFAULT_MAX_REPAIR_ATTEMPTS:
        store.add_event(job.job_id, "repair_limit_reached", {"attempts": attempts, "failure_signature": failure_signature})
        updated = store.update(
            job.job_id,
            CloydSmithJobUpdate(
                next_action="repair limit reached; request operator attention",
                error=job.error or f"Repair limit reached after {attempts} attempts.",
            ),
        )
        _record_heartbeat(
            store,
            job_id=job.job_id,
            alias=job.smith_alias,
            session_id=session_id,
            state=CloydSmithJobStatus.NEEDS_ATTENTION.value,
            phase="repair_limit_reached",
            last_action="repair_preflight",
            last_error=updated.error or "",
            stop_reason="repair_limit_reached",
        )
        return {"job_id": job.job_id, "status": updated.status.value, "action": "repair_limit_reached"}

    if attempts > 0 and previous_signature == failure_signature and previous_tree == working_tree_sha256:
        store.add_event(
            job.job_id,
            "repair_repeated_failure_without_progress",
            {"attempts": attempts, "failure_signature": failure_signature, "working_tree_sha256": working_tree_sha256},
        )
        updated = store.update(
            job.job_id,
            CloydSmithJobUpdate(
                next_action="repeated identical check failure without working-tree progress; request attention",
                error=job.error or "Repeated identical check failure without working-tree progress.",
            ),
        )
        _record_heartbeat(
            store,
            job_id=job.job_id,
            alias=job.smith_alias,
            session_id=session_id,
            state=CloydSmithJobStatus.NEEDS_ATTENTION.value,
            phase="repeated_failure_without_progress",
            last_action="repair_preflight",
            last_error=updated.error or "",
            stop_reason="repeated_failure_without_progress",
        )
        return {"job_id": job.job_id, "status": updated.status.value, "action": "repeated_failure_without_progress"}

    attempts += 1
    repair.update(
        {
            "attempts": attempts,
            "last_repair_queued_at": datetime.now(UTC).isoformat(),
            "last_failure_signature": failure_signature,
            "last_working_tree_sha256": working_tree_sha256,
            "session_id": session_id,
        }
    )
    metadata["repair"] = repair
    repair_prompt = _repair_prompt(job, attempt=attempts, failure_signature=failure_signature)
    store.add_event(
        job.job_id,
        "repair_queued",
        {"attempt": attempts, "session_id": session_id, "failure_signature": failure_signature, "working_tree_sha256": working_tree_sha256},
    )
    updated = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.QUEUED,
            phase="repair_queued",
            current_prompt=repair_prompt,
            session_id=session_id,
            submission_id="",
            next_action="send repair to Smith in the same session",
            metadata=metadata,
            last_evidence={"repair": repair, "previous_error": job.error, "revision_evidence": evidence},
            error="",
        ),
    )
    _record_heartbeat(
        store,
        job_id=job.job_id,
        alias=job.smith_alias,
        session_id=session_id,
        state=CloydSmithJobStatus.QUEUED.value,
        phase="repair_queued",
        last_action="repair_preflight",
        last_message=f"Queued repair attempt {attempts} in existing Smith session.",
    )
    return {"job_id": job.job_id, "status": updated.status.value, "action": "repair_queued", "attempt": attempts}


def _stop_after_current_turn(store: CloydSmithJobStore, job, output: dict[str, Any], *, working_directory: str = "") -> dict[str, Any]:
    store.add_event(job.job_id, "stop_after_current_turn_completed", {"output": _bounded(output), "session_id": job.session_id})
    updated = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.STOPPED,
            phase="stopped_after_current_turn",
            next_action="stopped_after_current_turn",
            stop_intent="after_current_turn",
            last_evidence=_bounded(output),
            error="",
        ),
    )
    _record_heartbeat(
        store,
        job_id=job.job_id,
        alias=job.smith_alias,
        session_id=job.session_id or str(output.get("session") or "") or None,
        state=CloydSmithJobStatus.STOPPED.value,
        phase="stopped_after_current_turn",
        last_action="opencode_output",
        last_message=_summary_text(output),
        working_directory=working_directory,
        stop_reason="after_current_turn",
    )
    return {"job_id": job.job_id, "status": updated.status.value, "action": "stopped_after_current_turn"}


async def _reconcile_uncertain_job(store: CloydSmithJobStore, job) -> dict[str, Any]:
    status = await _opencode_status(
        ToolExecutionRequest(
            tool_name="opencode_status",
            arguments={"alias": job.smith_alias},
            actor="cloyd-smith-loop-5.2",
        )
    )
    event_type = "smith_status_after_waiting_for_input" if job.status == CloydSmithJobStatus.WAITING_FOR_INPUT else "smith_status_after_unknown"
    store.add_event(job.job_id, event_type, _bounded(status))
    if not status.get("ok"):
        _record_heartbeat(
            store,
            job_id=job.job_id,
            alias=job.smith_alias,
            session_id=str(status.get("session") or job.session_id or "") or None,
            state=CloydSmithJobStatus.UNKNOWN.value,
            phase="telemetry_unavailable",
            last_action="opencode_status",
            last_error=str(status.get("error") or "Smith status failed"),
            working_directory=str(status.get("working_directory") or ""),
        )
        updated = store.update(
            job.job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus.UNKNOWN,
                phase="telemetry_unavailable",
                session_id=str(status.get("session") or job.session_id or "") or None,
                next_action="freeze dispatch and reconcile OpenCode telemetry",
                last_evidence=_bounded(status),
                error=str(status.get("error") or "Smith status failed"),
            ),
        )
        return {"job_id": job.job_id, "status": updated.status.value, "action": "telemetry_unknown"}
    if status.get("state") != "idle":
        if _status_indicates_waiting_for_input(status):
            _record_heartbeat(
                store,
                job_id=job.job_id,
                alias=job.smith_alias,
                session_id=str(status.get("session") or job.session_id or "") or None,
                state=CloydSmithJobStatus.WAITING_FOR_INPUT.value,
                phase="permission_wait",
                last_action=_last_action_name(status) or "opencode_status",
                last_message=_summary_text(status),
                working_directory=str(status.get("working_directory") or ""),
            )
            updated = store.update(
                job.job_id,
                CloydSmithJobUpdate(
                    status=CloydSmithJobStatus.WAITING_FOR_INPUT,
                    phase="permission_wait",
                    session_id=str(status.get("session") or job.session_id or "") or None,
                    next_action="worker is waiting for permission or input; answer in the OpenCode session",
                    last_evidence=_bounded(status),
                    error="",
                ),
            )
            return {"job_id": job.job_id, "status": updated.status.value, "action": "permission_wait"}
        _record_heartbeat(
            store,
            job_id=job.job_id,
            alias=job.smith_alias,
            session_id=str(status.get("session") or job.session_id or "") or None,
            state=CloydSmithJobStatus.RUNNING.value,
            phase="telemetry_reconnected",
            last_action=_last_action_name(status) or "opencode_status",
            last_message=_summary_text(status),
            working_directory=str(status.get("working_directory") or ""),
        )
        updated = store.update(
            job.job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus.RUNNING,
                phase="telemetry_reconnected",
                session_id=str(status.get("session") or job.session_id or "") or None,
                next_action="check_smith_output",
                last_evidence=_bounded(status),
                error="",
            ),
        )
        return {"job_id": job.job_id, "status": updated.status.value, "action": "telemetry_reconnected"}

    output = await _opencode_output(
        ToolExecutionRequest(
            tool_name="opencode_output",
            arguments={"alias": job.smith_alias, "limit": 3},
            actor="cloyd-smith-loop-5.2",
        )
    )
    store.add_event(job.job_id, "smith_output_after_reconnect", _bounded(output))
    updated = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.VERIFYING,
            phase="output_ready_after_reconnect",
            session_id=str(output.get("session") or status.get("session") or job.session_id or "") or None,
            next_action="run independent check commands",
            last_evidence=_bounded(output),
            error="",
        ),
    )
    return await _verify_completed_turn(
        store,
        updated,
        output,
        working_directory=str(status.get("working_directory") or ""),
        phase="output_ready_after_reconnect",
        stop_reason="telemetry_reconnected_idle",
    )


async def _verify_completed_turn(
    store: CloydSmithJobStore,
    job,
    output: dict[str, Any],
    *,
    working_directory: str = "",
    phase: str,
    stop_reason: str = "smith_idle",
    no_check_action: str = "ready_for_review",
) -> dict[str, Any]:
    _record_heartbeat(
        store,
        job_id=job.job_id,
        alias=job.smith_alias,
        session_id=str(output.get("session") or job.session_id or "") or None,
        state=CloydSmithJobStatus.VERIFYING.value,
        phase="verifying",
        last_action="run_check_commands" if job.check_commands else "opencode_output",
        last_message=_summary_text(output),
        working_directory=working_directory,
        stop_reason=stop_reason,
    )
    if not job.check_commands:
        evidence = _capture_revision_evidence(job, output, check_results=[])
        updated = store.update(
            job.job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus.NEEDS_REVIEW,
                phase=phase,
                next_action="cloyd_review_evidence",
                last_evidence=_bounded(output),
                revision_evidence=evidence,
                error="",
            ),
        )
        _record_heartbeat(
            store,
            job_id=job.job_id,
            alias=job.smith_alias,
            session_id=job.session_id,
            state=CloydSmithJobStatus.NEEDS_REVIEW.value,
            phase=phase,
            last_action="opencode_output",
            last_message=_summary_text(output),
            working_directory=working_directory,
            stop_reason=stop_reason,
        )
        return {"job_id": job.job_id, "status": updated.status.value, "action": no_check_action}

    store.add_event(
        job.job_id,
        "verification_started",
        {"phase": phase, "check_commands": job.check_commands, "session_id": job.session_id},
    )
    check_results = _run_check_commands(job.check_commands)
    all_passed = all(int(result.get("exit_code") or 0) == 0 and not result.get("timed_out") for result in check_results)
    evidence = _capture_revision_evidence(job, output, check_results=check_results)
    status = CloydSmithJobStatus.VERIFIED if all_passed else CloydSmithJobStatus.NEEDS_ATTENTION
    next_action = "report verified evidence" if all_passed else "repair failing checks in same Smith session or request input"
    error = "" if all_passed else _check_failure_summary(check_results)
    updated = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=status,
            phase="verified" if all_passed else "checks_failed",
            next_action=next_action,
            last_evidence={"output": _bounded(output), "check_results": check_results},
            revision_evidence=evidence,
            error=error,
        ),
    )
    store.add_event(
        job.job_id,
        "verification_finished",
        {"status": updated.status.value, "check_results": check_results, "working_tree_sha256": evidence.get("working_tree_sha256")},
    )
    _record_heartbeat(
        store,
        job_id=job.job_id,
        alias=job.smith_alias,
        session_id=job.session_id,
        state=updated.status.value,
        phase=updated.phase,
        last_action="run_check_commands",
        last_message="All check commands passed." if all_passed else error,
        working_directory=working_directory,
        stop_reason="checks_passed" if all_passed else "checks_failed",
    )
    return {"job_id": job.job_id, "status": updated.status.value, "action": "verified" if all_passed else "checks_failed"}


async def _external_worker_busy(store: CloydSmithJobStore, job) -> dict[str, Any] | None:
    runtime = opencode_health(alias=job.smith_alias, timeout_seconds=5)
    if not runtime.get("ok") or int(runtime.get("session_count") or 0) <= 0:
        return None
    status = await _opencode_status(
        ToolExecutionRequest(
            tool_name="opencode_status",
            arguments={"alias": job.smith_alias},
            actor="cloyd-smith-loop-5.2",
        )
    )
    if status.get("ok") and status.get("state") == "idle":
        return None
    status["runtime"] = runtime
    return status


async def _record_long_busy_warning_if_needed(
    store: CloydSmithJobStore,
    job,
    status: dict[str, Any],
) -> dict[str, Any] | None:
    heartbeat = store.get_heartbeat(job.job_id)
    if not heartbeat or heartbeat.state != CloydSmithJobStatus.RUNNING.value:
        return None
    elapsed_seconds = int((datetime.now(UTC) - (heartbeat.started_at or heartbeat.updated_at)).total_seconds())
    if elapsed_seconds <= DEFAULT_FIRST_RESPONSE_BUDGET_SECONDS:
        return None
    if heartbeat.phase == "first_response_warning":
        return None
    reason = f"Smith has been busy for {elapsed_seconds}s without reviewable output; warning only, worker remains active."
    store.add_event(job.job_id, "first_response_warning", {"status": _bounded(status), "elapsed_seconds": elapsed_seconds})
    _record_heartbeat(
        store,
        job_id=job.job_id,
        alias=job.smith_alias,
        session_id=str(status.get("session") or "") or None,
        state="running",
        phase="first_response_warning",
        last_action=_last_action_name(status) or "opencode_status",
        last_message=_summary_text(status),
        last_error=reason,
        working_directory=str(status.get("working_directory") or ""),
    )
    updated = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.RUNNING,
            next_action="continue observing; first-response warning is not a failure",
            last_evidence={"status": _bounded(status), "elapsed_seconds": elapsed_seconds},
            error=reason,
        ),
    )
    return {"job_id": job.job_id, "status": updated.status.value, "action": "first_response_warning"}


async def _recover_stale_job(store: CloydSmithJobStore, job) -> dict[str, Any]:
    status = await _opencode_status(
        ToolExecutionRequest(
            tool_name="opencode_status",
            arguments={"alias": job.smith_alias},
            actor="cloyd-smith-loop-5.2",
        )
    )
    store.add_event(job.job_id, "smith_status_after_stale", _bounded(status))
    if status.get("ok") and status.get("state") != "idle":
        _record_heartbeat(
            store,
            job_id=job.job_id,
            alias=job.smith_alias,
            session_id=str(status.get("session") or "") or None,
            state="running",
            phase="smith_busy_after_stale",
            last_action=_last_action_name(status) or "opencode_status",
            last_message=_summary_text(status),
            working_directory=str(status.get("working_directory") or ""),
        )
        updated = store.update(
            job.job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus.RUNNING,
                next_action="check_smith_output",
                last_evidence=_bounded(status),
                error="",
            ),
        )
        return {"job_id": job.job_id, "status": updated.status.value, "action": "recovered_stale_busy"}
    if status.get("ok") and status.get("state") == "idle":
        output = await _opencode_output(
            ToolExecutionRequest(
                tool_name="opencode_output",
                arguments={"alias": job.smith_alias, "limit": 3},
                actor="cloyd-smith-loop-5.2",
            )
        )
        store.add_event(job.job_id, "smith_output_after_stale", _bounded(output))
        _record_heartbeat(
            store,
            job_id=job.job_id,
            alias=job.smith_alias,
            session_id=str(output.get("session") or status.get("session") or "") or None,
            state="needs_review",
            phase="output_ready_after_stale",
            last_action="opencode_output",
            last_message=_summary_text(output),
            working_directory=str(status.get("working_directory") or ""),
            stop_reason="smith_idle_after_stale",
        )
        updated = store.update(
            job.job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus.NEEDS_REVIEW,
                next_action="cloyd_review_evidence",
                last_evidence=_bounded(output),
                error="",
            ),
        )
        return {"job_id": job.job_id, "status": updated.status.value, "action": "harvested_output_after_stale"}
    _record_heartbeat(
        store,
        job_id=job.job_id,
        alias=job.smith_alias,
        session_id=str(status.get("session") or "") or None,
        state="blocked",
        phase="status_failed_after_stale",
        last_action="opencode_status",
        last_error=str(status.get("error") or "Smith status failed after stale"),
        working_directory=str(status.get("working_directory") or ""),
        stop_reason="status_failed_after_stale",
    )
    updated = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="fix_runtime_or_retry",
            last_evidence=_bounded(status),
            error=str(status.get("error") or "Smith status failed after stale"),
        ),
    )
    return {"job_id": job.job_id, "status": updated.status.value, "action": "blocked_after_stale_status_failed"}


async def _stop_job(store: CloydSmithJobStore, job_id: str) -> dict[str, Any]:
    job = store.get(job_id)
    stopped = await _opencode_stop(
        ToolExecutionRequest(
            tool_name="opencode_stop",
            arguments={"alias": job.smith_alias},
            actor="cloyd-smith-loop-5.2",
        )
    )
    store.add_event(job.job_id, "smith_stop", _bounded(stopped))
    _record_heartbeat(
        store,
        job_id=job.job_id,
        alias=job.smith_alias,
        session_id=str(stopped.get("session") or "") or None,
        state="stopped",
        phase="stopped",
        last_action="opencode_stop",
        last_message=_summary_text(stopped),
        stop_reason="stopped_by_supervisor",
    )
    updated = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.STOPPED,
            phase="stopped",
            session_id=str(stopped.get("session") or "") or None,
            stop_intent="immediate",
            next_action="stopped_by_supervisor",
            last_evidence=_bounded(stopped),
        ),
    )
    return {"job_id": job_id, "status": updated.status.value, "smith_stop": stopped}


def _smith_prompt(job) -> str:
    criteria = "\n".join(f"- {item}" for item in job.acceptance_criteria) or "- Report evidence clearly."
    checks = "\n".join(f"- {item}" for item in job.check_commands) or "- No independent check commands were recorded; propose the smallest relevant checks before claiming done."
    scope = job.scope or "repository-scoped Freyja-OS coding work"
    return f"""Freyja 5.2 Smith worker task.

Original Cloyd objective:
{job.objective}

Scope:
{scope}

Current Smith task:
{job.current_prompt}

Acceptance criteria:
{criteria}

Agreed check commands:
{checks}

Rules:
- Do not use subagents or task delegation.
- Use direct commands only.
- Keep work bounded and report commands, diffs, tests, blockers, and evidence.
- Stop after reporting. Cloyd owns the master plan.
"""


def _repair_prompt(job, *, attempt: int, failure_signature: list[dict[str, Any]]) -> str:
    evidence = job.revision_evidence or {}
    check_lines = []
    for result in evidence.get("check_results") or []:
        command = result.get("command") or result.get("tool") or "check"
        exit_code = result.get("exit_code", result.get("status", "unknown"))
        stderr = _truncate_text(str(result.get("stderr") or "").strip(), 1200)
        stdout = _truncate_text(str(result.get("stdout") or "").strip(), 1200)
        detail = stderr or stdout or "no output"
        check_lines.append(f"- {command!r} -> {exit_code}: {detail}")
    checks = "\n".join(check_lines) or "- No check failure details were captured."
    changed_files = "\n".join(f"- {item}" for item in evidence.get("changed_files") or []) or "- No changed files recorded."
    criteria = "\n".join(f"- {item}" for item in job.acceptance_criteria) or "- Satisfy the original bounded task and report evidence."
    return f"""Repair attempt {attempt} for the same bounded Freyja coding task.

Use the existing OpenCode session. Do not restart the task, broaden scope, use subagents, or delegate.

Original objective:
{job.objective}

Acceptance criteria:
{criteria}

Failing independent checks:
{checks}

Current revision evidence:
- head: {evidence.get("head") or "unknown"}
- working_tree_sha256: {evidence.get("working_tree_sha256") or "unknown"}
- tracked_diff_sha256: {evidence.get("tracked_diff_sha256") or "unknown"}
- failure_signature: {json.dumps(failure_signature, sort_keys=True)}

Changed files:
{changed_files}

Repair instructions:
- Fix only what is needed for the failing checks and acceptance criteria.
- Preserve unrelated user changes.
- Run the relevant checks yourself if practical, then stop and report the commands, diffs, blockers, and evidence.
- If the same failure remains and no working-tree progress is possible, say so plainly instead of repeating work.
"""


def _failure_signature(check_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signature: list[dict[str, Any]] = []
    for result in check_results:
        exit_code = result.get("exit_code")
        status = result.get("status")
        timed_out = bool(result.get("timed_out"))
        status_failed = status not in (None, "", "ok", "success", "passed")
        exit_failed = exit_code is not None and int(exit_code or 0) != 0
        if not (timed_out or status_failed or exit_failed):
            continue
        signature.append(
            {
                "command": str(result.get("command") or result.get("tool") or "check"),
                "exit_code": exit_code,
                "timed_out": timed_out,
                "stderr_tail": _truncate_text(str(result.get("stderr") or ""), 1000),
                "stdout_tail": _truncate_text(str(result.get("stdout") or ""), 1000),
            }
        )
    return signature


def _bounded(payload: Any, *, limit: int = 20000) -> dict[str, Any]:
    payload = _redact(payload)
    text = json.dumps(payload, default=str)
    if len(text) <= limit:
        return payload if isinstance(payload, dict) else {"value": payload}
    return {"truncated": True, "text": text[-limit:]}


def _run_check_commands(commands: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cwd = Path(settings.repository_root).expanduser()
    for command in commands:
        started_at = datetime.now(UTC)
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                shell=True,
                check=False,
                capture_output=True,
                text=True,
                timeout=DEFAULT_CHECK_TIMEOUT_SECONDS,
            )
            result = {
                "command": command,
                "exit_code": completed.returncode,
                "timed_out": False,
                "stdout": _truncate_text(_redact(completed.stdout or ""), 8000),
                "stderr": _truncate_text(_redact(completed.stderr or ""), 8000),
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
                "timeout_seconds": DEFAULT_CHECK_TIMEOUT_SECONDS,
            }
        except subprocess.TimeoutExpired as exc:
            result = {
                "command": command,
                "exit_code": 124,
                "timed_out": True,
                "stdout": _truncate_text(_redact(exc.stdout or ""), 8000),
                "stderr": _truncate_text(_redact(exc.stderr or ""), 8000),
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(UTC).isoformat(),
                "timeout_seconds": DEFAULT_CHECK_TIMEOUT_SECONDS,
            }
        results.append(result)
    return results


def _check_failure_summary(check_results: list[dict[str, Any]]) -> str:
    failed = [result for result in check_results if int(result.get("exit_code") or 0) != 0 or result.get("timed_out")]
    if not failed:
        return ""
    first = failed[0]
    command = str(first.get("command") or "check")
    exit_code = first.get("exit_code")
    timed_out = " timed out" if first.get("timed_out") else ""
    stderr = str(first.get("stderr") or "").strip()
    detail = stderr.splitlines()[-1] if stderr else ""
    return _truncate_text(f"{command!r} failed with exit {exit_code}{timed_out}. {detail}".strip(), 1000)


def _truncate_text(value: Any, limit: int) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[-limit:]


def _capture_revision_evidence(job, output: dict[str, Any], *, check_results: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    captured_check_results = list(check_results or [])
    recent_action = output.get("recent_action")
    if isinstance(recent_action, dict):
        captured_check_results.append(recent_action)
    try:
        return capture_revision_evidence(check_commands=job.check_commands, check_results=captured_check_results)
    except Exception as exc:
        return {
            "capture_error": str(exc),
            "check_commands": job.check_commands,
            "check_results": captured_check_results,
            "captured_at": datetime.now(UTC).isoformat(),
        }


def _redact(payload: Any) -> Any:
    if isinstance(payload, dict):
        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in ("password", "token", "secret", "authorization", "api_key", "apikey")):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = _redact(value)
        return redacted
    if isinstance(payload, list):
        return [_redact(item) for item in payload]
    if isinstance(payload, str):
        text = payload
        for pattern in SECRET_PATTERNS:
            text = pattern.sub(r"\1[redacted]", text)
        return text
    return payload


def _send_timed_out(output: dict[str, Any]) -> bool:
    return not output.get("ok") and "timed out" in str(output.get("error") or "").lower()


def _record_heartbeat(
    store: CloydSmithJobStore,
    *,
    job_id: str,
    alias: str,
    state: str,
    phase: str,
    last_action: str,
    last_message: str = "",
    last_error: str = "",
    working_directory: str = "",
    session_id: str | None = None,
    stop_reason: str | None = None,
    meaningful: bool = True,
    reset_started_at: bool = False,
) -> AgentRunHeartbeat:
    existing = store.get_heartbeat(job_id)
    updated_at = datetime.now(UTC)
    heartbeat = AgentRunHeartbeat(
        job_id=job_id,
        agent="smith",
        alias=alias,
        session_id=session_id or (existing.session_id if existing else None),
        state=state,
        phase=phase,
        last_action=last_action,
        last_message=last_message[-1000:],
        last_error=last_error[-1000:],
        working_directory=working_directory or (existing.working_directory if existing else ""),
        started_at=updated_at if reset_started_at else (existing.started_at if existing else None),
        updated_at=updated_at,
        stale_after_seconds=DEFAULT_STALE_AFTER_SECONDS,
        stop_reason=stop_reason,
    )
    return store.record_heartbeat(heartbeat)


def _summary_text(payload: dict[str, Any], *, limit: int = 1000) -> str:
    for key in ("result", "message", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return str(_redact(value.strip()))[-limit:]
    action = payload.get("recent_action")
    if isinstance(action, dict):
        tool = action.get("tool") or "tool"
        status = action.get("status") or "unknown"
        return f"{tool}: {status}"
    return json.dumps(_bounded(payload, limit=limit), default=str, sort_keys=True)[-limit:]


def _last_action_name(payload: dict[str, Any]) -> str | None:
    action = payload.get("recent_action")
    if isinstance(action, dict) and action.get("tool"):
        return str(action["tool"])
    return None


def _status_indicates_waiting_for_input(payload: dict[str, Any]) -> bool:
    text = json.dumps(_bounded(payload, limit=4000), default=str).lower()
    markers = (
        "permission",
        "approval",
        "approve",
        "waiting for input",
        "needs input",
        "awaiting input",
        "confirm",
        "confirmation",
    )
    waiting_marker = any(marker in text for marker in markers)
    if not waiting_marker:
        return False
    busy_text = str(payload.get("state") or "").lower()
    action = payload.get("recent_action")
    action_status = str(action.get("status") or "").lower() if isinstance(action, dict) else ""
    return (
        "idle" not in busy_text
        and any(marker in text for marker in ("waiting", "pending", "permission", "approval", "confirm"))
        and action_status not in {"completed", "done", "success", "failed"}
    )


def _default_lock_path(database_arg: str | None) -> Path:
    if database_arg:
        database_path = Path(database_arg).expanduser()
    else:
        database_path = Path(settings.cloyd_smith_loop_database_path).expanduser()
    if not database_path.is_absolute():
        database_path = Path.cwd() / database_path
    return database_path.with_suffix(database_path.suffix + ".lock")


def _write_supervisor_heartbeat(
    path: str | Path | None,
    store: CloydSmithJobStore,
    *,
    status: str,
    ok: bool = True,
    results: list[dict[str, Any]] | None = None,
    error: str = "",
) -> dict[str, Any]:
    heartbeat_path = Path(path).expanduser() if path else default_cloyd_smith_supervisor_heartbeat_path(store.database_path)
    if not heartbeat_path.is_absolute():
        heartbeat_path = Path.cwd() / heartbeat_path
    payload = {
        "ok": ok,
        "status": status,
        "pid": os.getpid(),
        "database": str(store.database_path),
        "updated_at": datetime.now(UTC).isoformat(),
        "result_count": len(results or []),
        "results": _bounded(results or [], limit=5000),
        "error": error,
    }
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = heartbeat_path.with_suffix(heartbeat_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    tmp_path.replace(heartbeat_path)
    return payload


def _status_payload(store: CloydSmithJobStore) -> dict[str, Any]:
    return enrich_loop_status_with_runtime(loop_status_payload(store), opencode_health(alias="freyja-code", timeout_seconds=5))


@contextlib.contextmanager
def _exclusive_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()))
        handle.flush()
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main() -> int:
    parser = argparse.ArgumentParser(description="Freyja 5.2 durable Cloyd-Smith supervisor loop.")
    parser.add_argument("--database")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--stop-job")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--lock-file")
    parser.add_argument("--heartbeat-file")
    args = parser.parse_args()

    store = CloydSmithJobStore(args.database)
    if args.status:
        print(json.dumps(_status_payload(store), indent=2))
        return 0
    if args.stop_job:
        print(json.dumps(asyncio.run(_stop_job(store, args.stop_job)), indent=2))
        return 0
    if args.once:
        lock_path = Path(args.lock_file).expanduser() if args.lock_file else _default_lock_path(args.database)
        with _exclusive_lock(lock_path) as acquired:
            if not acquired:
                print(json.dumps({"ok": False, "status": "already_running", "lock_file": str(lock_path)}, indent=2))
                return 75
            results = asyncio.run(_run_once(store))
            _write_supervisor_heartbeat(args.heartbeat_file, store, status="once_complete", results=results)
            print(json.dumps(results, indent=2))
            return 0
    lock_path = Path(args.lock_file).expanduser() if args.lock_file else _default_lock_path(args.database)
    with _exclusive_lock(lock_path) as acquired:
        if not acquired:
            print(json.dumps({"ok": False, "status": "already_running", "lock_file": str(lock_path)}, sort_keys=True), flush=True)
            return 75
        while True:
            try:
                results = asyncio.run(_run_once(store))
                _write_supervisor_heartbeat(args.heartbeat_file, store, status="loop_ok", results=results)
                if results:
                    print(json.dumps({"results": results}, sort_keys=True), flush=True)
            except Exception as exc:
                _write_supervisor_heartbeat(args.heartbeat_file, store, status="loop_error", ok=False, error=str(exc))
                print(json.dumps({"error": str(exc)}, sort_keys=True), flush=True)
            time.sleep(max(args.interval, 1.0))


if __name__ == "__main__":
    raise SystemExit(main())
