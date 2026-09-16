#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import contextlib
import fcntl
import json
import os
import re
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
    default_cloyd_smith_supervisor_heartbeat_path,
    enrich_loop_status_with_runtime,
    loop_status_payload,
    read_supervisor_heartbeat,
)
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.opencode_runtime import _opencode_output, _opencode_send, _opencode_status, _opencode_stop, opencode_health


DEFAULT_STALE_AFTER_SECONDS = 300
DEFAULT_SEND_TIMEOUT_SECONDS = 45
DEFAULT_MAX_BUSY_SECONDS = 180
SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization:\s*basic\s+)[A-Za-z0-9+/=._-]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(api[_-]?key['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"),
    re.compile(r"(?i)(password['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"),
    re.compile(r"(?i)(token['\"]?\s*[:=]\s*['\"]?)[^'\"\s,}]+"),
)


async def _run_once(store: CloydSmithJobStore) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for stale in store.mark_stale_runs():
        results.append({"job_id": stale.job_id, "status": "stale", "action": "marked_stale"})
    for job in store.list_active(limit=20):
        if job.status == CloydSmithJobStatus.NEEDS_REVIEW:
            continue
        if job.status == CloydSmithJobStatus.STALE:
            results.append(await _recover_stale_job(store, job))
            continue
        if job.status == CloydSmithJobStatus.QUEUED:
            prompt = _smith_prompt(job)
            store.update(
                job.job_id,
                CloydSmithJobUpdate(
                    status=CloydSmithJobStatus.RUNNING,
                    next_action="await_smith_send_result",
                    last_evidence={"phase": "sending_to_smith"},
                ),
            )
            _record_heartbeat(
                store,
                job_id=job.job_id,
                alias=job.smith_alias,
                state="running",
                phase="sending_to_smith",
                last_action="opencode_send",
                last_message="Sending bounded Smith prompt.",
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
                    _record_heartbeat(
                        store,
                        job_id=job.job_id,
                        alias=job.smith_alias,
                        session_id=str(review.get("session") or status.get("session") or "") or None,
                        state="needs_review",
                        phase="output_ready_after_send_timeout",
                        last_action="opencode_output",
                        last_message=_summary_text(review),
                        working_directory=str(status.get("working_directory") or ""),
                        stop_reason="smith_idle_after_send_timeout",
                    )
                    updated = store.update(
                        job.job_id,
                        CloydSmithJobUpdate(
                            status=CloydSmithJobStatus.NEEDS_REVIEW,
                            next_action="cloyd_review_evidence",
                            last_evidence=_bounded(review),
                            error="",
                        ),
                    )
                    results.append({"job_id": job.job_id, "status": updated.status.value, "action": "harvested_output_after_send_timeout"})
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
                    state="blocked",
                    phase="status_failed",
                    last_action="opencode_status",
                    last_error=str(status.get("error") or "Smith status failed"),
                    working_directory=str(status.get("working_directory") or ""),
                    stop_reason="status_failed",
                )
                updated = store.update(
                    job.job_id,
                    CloydSmithJobUpdate(
                        status=CloydSmithJobStatus.BLOCKED,
                        next_action="fix_runtime_or_retry",
                        last_evidence=_bounded(status),
                        error=str(status.get("error") or "Smith status failed"),
                    ),
                )
                results.append({"job_id": job.job_id, "status": updated.status.value, "action": "blocked"})
                continue
            if status.get("state") != "idle":
                long_busy = await _block_long_busy_job_if_needed(store, job, status)
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
                store.update(job.job_id, CloydSmithJobUpdate(next_action="check_smith_output", last_evidence=_bounded(status)))
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
            _record_heartbeat(
                store,
                job_id=job.job_id,
                alias=job.smith_alias,
                session_id=str(output.get("session") or status.get("session") or "") or None,
                state="needs_review",
                phase="output_ready",
                last_action="opencode_output",
                last_message=_summary_text(output),
                working_directory=str(status.get("working_directory") or ""),
                stop_reason="smith_idle",
            )
            updated = store.update(
                job.job_id,
                CloydSmithJobUpdate(
                    status=CloydSmithJobStatus.NEEDS_REVIEW,
                    next_action="cloyd_review_evidence",
                    last_evidence=_bounded(output),
                ),
            )
            results.append({"job_id": job.job_id, "status": updated.status.value, "action": "ready_for_review"})
    return results


async def _block_long_busy_job_if_needed(
    store: CloydSmithJobStore,
    job,
    status: dict[str, Any],
) -> dict[str, Any] | None:
    heartbeat = store.get_heartbeat(job.job_id)
    if not heartbeat or heartbeat.state != CloydSmithJobStatus.RUNNING.value:
        return None
    elapsed_seconds = int((datetime.now(UTC) - (heartbeat.started_at or heartbeat.updated_at)).total_seconds())
    if elapsed_seconds <= DEFAULT_MAX_BUSY_SECONDS:
        return None
    stop = await _opencode_stop(
        ToolExecutionRequest(
            tool_name="opencode_stop",
            arguments={"alias": job.smith_alias},
            actor="cloyd-smith-loop-5.2",
        )
    )
    reason = (
        f"Smith stayed busy for {elapsed_seconds}s without producing reviewable output; "
        f"stopped OpenCode session after max busy window of {DEFAULT_MAX_BUSY_SECONDS}s."
    )
    store.add_event(job.job_id, "smith_busy_timeout_stop", {"status": _bounded(status), "stop": _bounded(stop), "elapsed_seconds": elapsed_seconds})
    _record_heartbeat(
        store,
        job_id=job.job_id,
        alias=job.smith_alias,
        session_id=str(status.get("session") or "") or None,
        state="blocked",
        phase="smith_busy_timeout",
        last_action="opencode_stop",
        last_message=_summary_text(stop),
        last_error=reason,
        working_directory=str(status.get("working_directory") or ""),
        stop_reason="smith_busy_timeout",
    )
    updated = store.update(
        job.job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.BLOCKED,
            next_action="inspect_or_queue_suggested_replacement_after_busy_timeout",
            last_evidence={"status": _bounded(status), "stop": _bounded(stop), "elapsed_seconds": elapsed_seconds},
            error=reason,
        ),
    )
    return {"job_id": job.job_id, "status": updated.status.value, "action": "blocked_busy_timeout"}


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
            next_action="stopped_by_supervisor",
            last_evidence=_bounded(stopped),
        ),
    )
    return {"job_id": job_id, "status": updated.status.value, "smith_stop": stopped}


def _smith_prompt(job) -> str:
    criteria = "\n".join(f"- {item}" for item in job.acceptance_criteria) or "- Report evidence clearly."
    return f"""Freyja 5.2 Smith worker task.

Original Cloyd objective:
{job.objective}

Current Smith task:
{job.current_prompt}

Acceptance criteria:
{criteria}

Rules:
- Do not use subagents or task delegation.
- Use direct commands only.
- Keep work bounded and report commands, diffs, tests, blockers, and evidence.
- Stop after reporting. Cloyd owns the master plan.
"""


def _bounded(payload: Any, *, limit: int = 20000) -> dict[str, Any]:
    payload = _redact(payload)
    text = json.dumps(payload, default=str)
    if len(text) <= limit:
        return payload if isinstance(payload, dict) else {"value": payload}
    return {"truncated": True, "text": text[-limit:]}


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
