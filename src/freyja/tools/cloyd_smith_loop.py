from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from freyja.cloyd_smith_loop import (
    AgentRunHeartbeat,
    CloydSmithJobCreate,
    CloydSmithJobStatus,
    CloydSmithJobStore,
    CloydSmithJobUpdate,
    enrich_loop_status_with_runtime,
    expected_smith_alias,
    heartbeat_summary,
    job_status_summary,
    loop_status_payload,
    read_supervisor_heartbeat,
)
from freyja.home_memory import HomeMemoryWriteRequest, _write_record
from freyja.memory.models import MemoryPrincipal
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.opencode_runtime import _opencode_status, opencode_health
from freyja.tools.registry import ToolRegistry


def _job_summary(job, *, store: CloydSmithJobStore, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    heartbeat = store.get_heartbeat(job.job_id)
    return {
        "job_id": job.job_id,
        "objective": job.objective,
        "smith_alias": job.smith_alias,
        "status": job.status.value,
        "acceptance_criteria": job.acceptance_criteria,
        "current_prompt": job.current_prompt,
        "next_action": job.next_action,
        "last_evidence": job.last_evidence,
        "metadata": job.metadata,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "heartbeat": heartbeat_summary(heartbeat) if heartbeat else None,
        "summary": job_status_summary(job, heartbeat=heartbeat),
        "events": events or [],
    }


def _loop_summary(store: CloydSmithJobStore, *, include_runtime: bool = False) -> dict[str, Any]:
    payload = loop_status_payload(store)
    if include_runtime:
        payload = enrich_loop_status_with_runtime(payload, opencode_health(alias="freyja-code", timeout_seconds=5))
    return {
        "canonical_monitor_url": "http://100.115.228.56:8000/agent-runs",
        "canonical_status_endpoint": "http://100.115.228.56:8000/agent-runs/api/status",
        **payload,
    }


def _opencode_status_is_busy(status: dict[str, Any]) -> bool:
    state = status.get("state")
    if state == "busy":
        return True
    if isinstance(state, dict) and state.get("type") == "busy":
        return True
    action = status.get("recent_action")
    return isinstance(action, dict) and action.get("status") == "running"


async def _cloyd_smith_submit(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    objective = str(args.get("objective") or "").strip()
    prompt = str(args.get("prompt") or args.get("current_prompt") or objective).strip()
    if not objective:
        return {"ok": False, "error": "objective is required"}
    if not prompt:
        return {"ok": False, "error": "prompt is required"}
    criteria = args.get("acceptance_criteria") or []
    if isinstance(criteria, str):
        criteria = [item.strip() for item in criteria.splitlines() if item.strip()]
    job = CloydSmithJobStore().create(
        CloydSmithJobCreate(
            objective=objective,
            smith_alias=str(args.get("smith_alias") or args.get("alias") or "freyja-code").strip(),
            acceptance_criteria=[str(item) for item in criteria],
            current_prompt=prompt,
            created_by=str(args.get("created_by") or request.actor or "joe"),
            metadata={"conversation_id": request.conversation_id, **(args.get("metadata") or {})},
        )
    )
    CloydSmithJobStore().add_event(job.job_id, "submitted", {"actor": request.actor})
    return {
        "ok": True,
        "receipt": {
            "job_id": job.job_id,
            "status": job.status.value,
            "smith_alias": job.smith_alias,
            "summary": job.objective,
            "status_prompt": f"Ask Cloyd: status {job.job_id}",
        },
    }


async def _cloyd_smith_status(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    store = CloydSmithJobStore()
    job_id = str(args.get("job_id") or "").strip()
    try:
        if job_id:
            job = store.get(job_id)
            return {"ok": True, "loop": _loop_summary(store, include_runtime=True), "job": _job_summary(job, store=store, events=store.events(job.job_id))}
        loop = _loop_summary(store, include_runtime=True)
        return {"ok": True, "loop": loop, "jobs": loop["runs"]}
    except KeyError:
        return {"ok": False, "error": f"Unknown Cloyd Smith job: {job_id}"}


async def _cloyd_smith_record(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    job_id = str(args.get("job_id") or "").strip()
    event_type = str(args.get("event_type") or "evidence").strip()
    payload = args.get("payload") or {}
    if not job_id:
        return {"ok": False, "error": "job_id is required"}
    if not isinstance(payload, dict):
        return {"ok": False, "error": "payload must be an object"}
    store = CloydSmithJobStore()
    try:
        store.add_event(job_id, event_type, payload)
        job = store.update(
            job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus(str(args["status"])) if args.get("status") else None,
                next_action=str(args["next_action"]) if args.get("next_action") is not None else None,
                last_evidence=payload,
                error=str(args["error"]) if args.get("error") is not None else None,
            ),
        )
        continuity_record = _record_cloyd_continuity_summary(request, job, event_type=event_type, payload=payload)
    except KeyError:
        return {"ok": False, "error": f"Unknown Cloyd Smith job: {job_id}"}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    result = {"ok": True, "job": _job_summary(job, store=store)}
    if continuity_record is not None:
        result["continuity"] = continuity_record.model_dump(mode="json")
    return result


def _record_cloyd_continuity_summary(
    request: ToolExecutionRequest,
    job,
    *,
    event_type: str,
    payload: dict[str, Any],
):
    args = request.arguments or {}
    content = str(args.get("continuity_summary") or args.get("decision") or "").strip()
    if not content:
        return None
    operation = "record-decision" if args.get("decision") else "remember"
    scope = str(args.get("continuity_scope") or "project:freyja-os").strip()
    owner = str(args.get("continuity_owner") or "freyja-os").strip()
    provenance = str(args.get("continuity_provenance") or "cloyd-smith-loop").strip()
    principal = MemoryPrincipal(
        client_type="cloyd-smith-loop",
        client_subject="agent:cloyd",
        account_owner="joe",
    )
    return _write_record(
        principal,
        HomeMemoryWriteRequest(
            scope=scope,
            owner=owner,
            content=content,
            provenance=provenance,
            sensitivity=str(args.get("continuity_sensitivity") or "private"),
            record_id=str(args.get("continuity_record_id") or f"cloyd-smith-{job.job_id}-{event_type}"),
            metadata={
                "continuity_surface": "opencode",
                "continuity_active_user": request.actor or "joe",
                "continuity_active_agent": "cloyd",
                "cloyd_smith_job_id": job.job_id,
                "cloyd_smith_event_type": event_type,
                "cloyd_smith_status": job.status.value,
                "cloyd_smith_payload_keys": sorted(payload),
            },
        ),
        operation=operation,
    )


async def _cloyd_smith_follow_up(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    job_id = str(args.get("job_id") or "").strip()
    prompt = str(args.get("prompt") or args.get("current_prompt") or "").strip()
    if not job_id:
        return {"ok": False, "error": "job_id is required"}
    if not prompt:
        return {"ok": False, "error": "prompt is required"}
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
        if job.status not in {CloydSmithJobStatus.NEEDS_REVIEW, CloydSmithJobStatus.BLOCKED, CloydSmithJobStatus.STALE}:
            return {"ok": False, "error": f"Job {job_id} is {job.status.value}; only needs_review, blocked, or stale jobs can receive a bounded follow-up."}
        metadata = dict(job.metadata or {})
        follow_up = dict(metadata.get("follow_up") or {})
        attempts = int(follow_up.get("attempts") or 0)
        if attempts >= 1:
            store.add_event(job_id, "operator_follow_up_limit_reached", {"actor": request.actor, "attempts": attempts})
            return {"ok": False, "error": f"Job {job_id} already has a bounded follow-up; mark blocked or create a new job instead of looping."}
        attempts += 1
        follow_up.update(
            {
                "attempts": attempts,
                "last_follow_up_at": datetime.now(UTC).isoformat(),
                "previous_status": job.status.value,
            }
        )
        metadata["follow_up"] = follow_up
        store.add_event(job_id, "operator_follow_up", {"actor": request.actor, "attempt": attempts, "previous_status": job.status.value})
        updated = store.update(
            job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus.QUEUED,
                current_prompt=prompt,
                next_action="send_to_smith",
                last_evidence={"operator_action": "follow_up", "attempt": attempts},
                metadata=metadata,
                error="",
            ),
        )
        store.record_heartbeat(
            AgentRunHeartbeat(
                job_id=job_id,
                agent="smith",
                alias=job.smith_alias,
                state="queued",
                phase="operator_follow_up_queued",
                last_action="operator_follow_up",
                last_message=f"Queued bounded follow-up attempt {attempts}.",
                working_directory="",
                started_at=datetime.now(UTC),
                stop_reason=None,
            )
        )
    except KeyError:
        return {"ok": False, "error": f"Unknown Cloyd Smith job: {job_id}"}
    return {"ok": True, "loop": _loop_summary(store), "job": _job_summary(updated, store=store)}


async def _cloyd_smith_retry(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    job_id = str(args.get("job_id") or "").strip()
    if not job_id:
        return {"ok": False, "error": "job_id is required"}
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
        if job.status not in {CloydSmithJobStatus.BLOCKED, CloydSmithJobStatus.STALE, CloydSmithJobStatus.STOPPED}:
            return {"ok": False, "error": f"Job {job_id} is {job.status.value}; only blocked, stale, or stopped jobs can be retried."}
        expected_alias = expected_smith_alias(job)
        if expected_alias and expected_alias != job.smith_alias:
            store.add_event(job_id, "operator_retry_alias_mismatch", {"actor": request.actor, "current_alias": job.smith_alias, "expected_alias": expected_alias})
            return {"ok": False, "error": f"Job {job_id} targets {expected_alias} but is assigned to {job.smith_alias}; reroute or create a new job with smith_alias={expected_alias} before retrying."}
        metadata = dict(job.metadata or {})
        retry = dict(metadata.get("retry") or {})
        attempts = int(retry.get("attempts") or 0)
        if attempts >= 3:
            store.add_event(job_id, "operator_retry_limit_reached", {"actor": request.actor, "attempts": attempts, "previous_status": job.status.value})
            return {"ok": False, "error": f"Job {job_id} already has {attempts} retry attempts; inspect the error/output before requeueing."}
        runtime = opencode_health(alias=job.smith_alias, timeout_seconds=5)
        if not runtime.get("ok"):
            store.add_event(job_id, "operator_retry_preflight_failed", {"actor": request.actor, "runtime": runtime})
            return {"ok": False, "error": f"OpenCode runtime is not healthy: {runtime.get('error') or runtime}", "runtime": runtime}
        status = await _opencode_status(
            ToolExecutionRequest(
                tool_name="opencode_status",
                arguments={"alias": job.smith_alias},
                actor=request.actor or "cloyd-smith-loop",
            )
        )
        if not status.get("ok") or _opencode_status_is_busy(status):
            store.add_event(job_id, "operator_retry_runtime_busy", {"actor": request.actor, "runtime": runtime, "status": status})
            updated = store.update(
                job_id,
                CloydSmithJobUpdate(
                    next_action="inspect_or_stop_opencode_session_before_retry",
                    last_evidence={"operator_action": "retry_preflight_busy", "runtime": runtime, "status": status},
                ),
            )
            return {
                "ok": False,
                "error": "OpenCode runtime is not ready for retry; inspect or stop the current session before requeueing.",
                "runtime": runtime,
                "status": status,
                "job": _job_summary(updated, store=store),
            }
        attempts += 1
        retry.update(
            {
                "attempts": attempts,
                "last_retry_at": datetime.now(UTC).isoformat(),
                "last_error": job.error or "",
                "previous_status": job.status.value,
            }
        )
        metadata["retry"] = retry
        store.add_event(job_id, "operator_retry", {"actor": request.actor, "previous_status": job.status.value, "attempt": attempts, "runtime": runtime})
        updated = store.update(
            job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus.QUEUED,
                next_action="send_to_smith",
                last_evidence={"operator_action": "retry", "attempt": attempts, "runtime": runtime},
                metadata=metadata,
                error="",
            ),
        )
        store.record_heartbeat(
            AgentRunHeartbeat(
                job_id=job_id,
                agent="smith",
                alias=job.smith_alias,
                state="queued",
                phase="operator_requeued",
                last_action="operator_retry",
                last_message=f"Queued for supervisor retry attempt {attempts}.",
                working_directory="",
                started_at=datetime.now(UTC),
                stop_reason=None,
            )
        )
    except KeyError:
        return {"ok": False, "error": f"Unknown Cloyd Smith job: {job_id}"}
    return {"ok": True, "action": "retry", "loop": _loop_summary(store), "job": _job_summary(updated, store=store)}


async def _cloyd_smith_mark_done(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    job_id = str(args.get("job_id") or "").strip()
    if not job_id:
        return {"ok": False, "error": "job_id is required"}
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
        if job.status != CloydSmithJobStatus.NEEDS_REVIEW:
            return {"ok": False, "error": f"Job {job_id} is {job.status.value}; only needs_review jobs can be marked done."}
        store.add_event(job_id, "operator_mark_done", {"actor": request.actor})
        updated = store.update(
            job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus.DONE,
                next_action="operator_reviewed_done",
                last_evidence={"operator_action": "marked_done"},
            ),
        )
        store.record_heartbeat(
            AgentRunHeartbeat(
                job_id=job_id,
                agent="smith",
                alias=job.smith_alias,
                state="done",
                phase="operator_reviewed",
                last_action="operator_mark_done",
                last_message="Marked done from Cloyd-Smith tool.",
                working_directory="",
                stop_reason="operator_reviewed_done",
            )
        )
    except KeyError:
        return {"ok": False, "error": f"Unknown Cloyd Smith job: {job_id}"}
    return {"ok": True, "action": "done", "loop": _loop_summary(store), "job": _job_summary(updated, store=store)}


async def _cloyd_smith_mark_blocked(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    job_id = str(args.get("job_id") or "").strip()
    supplied_reason = str(args.get("reason") or "").strip()
    if not job_id:
        return {"ok": False, "error": "job_id is required"}
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
        if job.status not in {CloydSmithJobStatus.NEEDS_REVIEW, CloydSmithJobStatus.QUEUED, CloydSmithJobStatus.RUNNING, CloydSmithJobStatus.STALE}:
            return {"ok": False, "error": f"Job {job_id} is {job.status.value}; only active or needs-review jobs can be marked blocked."}
        heartbeat = store.get_heartbeat(job_id)
        reason = supplied_reason or "operator marked blocked from Cloyd-Smith tool"
        if not supplied_reason and heartbeat and "INFERENCE_QUEUE_TIMEOUT" in heartbeat.last_message:
            reason = "review evidence is timeout-only; requested objective is not proven"
        elif not supplied_reason and job.error:
            reason = job.error
        store.add_event(job_id, "operator_mark_blocked", {"actor": request.actor, "previous_status": job.status.value, "reason": reason})
        updated = store.update(
            job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus.BLOCKED,
                next_action="blocked_pending_new_prompt_or_runtime_fix",
                last_evidence={"operator_action": "marked_blocked", "reason": reason},
                error=reason,
            ),
        )
        store.record_heartbeat(
            AgentRunHeartbeat(
                job_id=job_id,
                agent="smith",
                alias=job.smith_alias,
                state="blocked",
                phase="operator_review_blocked",
                last_action="operator_mark_blocked",
                last_message=reason,
                last_error=reason,
                working_directory=heartbeat.working_directory if heartbeat else "",
                stop_reason="operator_review_blocked",
            )
        )
    except KeyError:
        return {"ok": False, "error": f"Unknown Cloyd Smith job: {job_id}"}
    return {"ok": True, "action": "block", "loop": _loop_summary(store), "job": _job_summary(updated, store=store)}


async def _cloyd_smith_stop(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    job_id = str(args.get("job_id") or "").strip()
    if not job_id:
        return {"ok": False, "error": "job_id is required"}
    store = CloydSmithJobStore()
    try:
        store.add_event(job_id, "stopped", {"actor": request.actor})
        job = store.update(
            job_id,
            CloydSmithJobUpdate(status=CloydSmithJobStatus.STOPPED, next_action="stopped_by_user"),
        )
    except KeyError:
        return {"ok": False, "error": f"Unknown Cloyd Smith job: {job_id}"}
    return {"ok": True, "job": _job_summary(job, store=store)}


async def _cloyd_smith_replace(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    job_id = str(args.get("job_id") or "").strip()
    prompt = str(args.get("prompt") or args.get("current_prompt") or "").strip()
    objective = str(args.get("objective") or "").strip()
    smith_alias = str(args.get("smith_alias") or args.get("alias") or "").strip()
    criteria = args.get("acceptance_criteria") or []
    if isinstance(criteria, str):
        criteria = [item.strip() for item in criteria.splitlines() if item.strip()]
    if not job_id:
        return {"ok": False, "error": "job_id is required"}
    if not prompt:
        return {"ok": False, "error": "prompt is required"}
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
        if job.status != CloydSmithJobStatus.BLOCKED:
            return {"ok": False, "error": f"Job {job_id} is {job.status.value}; only blocked jobs can be replaced."}
        replacement = store.create(
            CloydSmithJobCreate(
                objective=objective or f"Replacement for blocked job {job_id}: {job.objective}",
                smith_alias=smith_alias or job.smith_alias or "freyja-code",
                acceptance_criteria=[str(item).strip() for item in criteria if str(item).strip()],
                current_prompt=prompt,
                created_by=request.actor or "cloyd-smith-tool",
                metadata={
                    "source": "cloyd_smith_replace",
                    "replaces": job_id,
                    "replaced_objective": job.objective,
                    "replacement_reason": job.error or "blocked job needed sharper replacement",
                    "parent_metadata": job.metadata,
                },
            )
        )
        store.add_event(job_id, "operator_create_replacement", {"actor": request.actor, "replacement_job_id": replacement.job_id, "replacement_alias": replacement.smith_alias})
        store.add_event(replacement.job_id, "submitted_as_replacement", {"actor": request.actor, "replaces": job_id})
        metadata = dict(job.metadata or {})
        metadata["superseded_by"] = replacement.job_id
        metadata["superseded_reason"] = "replaced by sharper Cloyd-Smith job"
        updated = store.update(
            job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus.STOPPED,
                next_action=f"superseded_by:{replacement.job_id}",
                last_evidence={"operator_action": "create_replacement", "replacement_job_id": replacement.job_id},
                metadata=metadata,
                error="",
            ),
        )
        store.record_heartbeat(
            AgentRunHeartbeat(
                job_id=job_id,
                agent="smith",
                alias=job.smith_alias,
                state="stopped",
                phase="superseded",
                last_action="operator_create_replacement",
                last_message=f"Superseded by replacement job {replacement.job_id}.",
                working_directory="",
                stop_reason="superseded",
            )
        )
        store.record_heartbeat(
            AgentRunHeartbeat(
                job_id=replacement.job_id,
                agent="smith",
                alias=replacement.smith_alias,
                state="queued",
                phase="replacement_queued",
                last_action="operator_create_replacement",
                last_message=f"Queued replacement for {job_id}.",
                working_directory="",
            )
        )
    except KeyError:
        return {"ok": False, "error": f"Unknown Cloyd Smith job: {job_id}"}
    return {
        "ok": True,
        "action": "replace",
        "loop": _loop_summary(store),
        "replaced_job": _job_summary(updated, store=store),
        "replacement_job": _job_summary(replacement, store=store),
    }


def register_cloyd_smith_loop_tools(registry: ToolRegistry) -> None:
    for definition, implementation in (
        (
            ToolDefinition(
                name="cloyd_smith_submit",
                description="Create a durable Freyja 5.2 Cloyd-Smith job and return a receipt for later status checks.",
                input_schema={
                    "type": "object",
                    "required": ["objective"],
                    "properties": {
                        "objective": {"type": "string"},
                        "prompt": {"type": "string"},
                        "smith_alias": {"type": "string"},
                        "acceptance_criteria": {"type": "array"},
                        "metadata": {"type": "object"},
                    },
                },
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                host_service="cloyd-smith-loop",
                required_permission="coding.execute",
                tags=["cloyd", "smith", "pratt-5.2", "jobs"],
            ),
            _cloyd_smith_submit,
        ),
        (
            ToolDefinition(
                name="cloyd_smith_status",
                description="Return status for one durable Cloyd-Smith job, or active jobs if no id is supplied.",
                input_schema={"type": "object", "properties": {"job_id": {"type": "string"}}},
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.READ_ONLY,
                host_service="cloyd-smith-loop",
                tags=["cloyd", "smith", "pratt-5.2", "status"],
            ),
            _cloyd_smith_status,
        ),
        (
            ToolDefinition(
                name="cloyd_smith_record",
                description="Record supervisor evidence or state transitions for a durable Cloyd-Smith job.",
                input_schema={
                    "type": "object",
                    "required": ["job_id", "payload"],
                    "properties": {
                        "job_id": {"type": "string"},
                        "event_type": {"type": "string"},
                        "payload": {"type": "object"},
                        "status": {"type": "string"},
                        "next_action": {"type": "string"},
                        "error": {"type": "string"},
                        "continuity_summary": {"type": "string"},
                        "decision": {"type": "string"},
                        "continuity_scope": {"type": "string"},
                        "continuity_owner": {"type": "string"},
                        "continuity_record_id": {"type": "string"},
                    },
                },
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                host_service="cloyd-smith-loop",
                required_permission="coding.execute",
                tags=["cloyd", "smith", "pratt-5.2", "evidence"],
            ),
            _cloyd_smith_record,
        ),
        (
            ToolDefinition(
                name="cloyd_smith_stop",
                description="Mark a durable Cloyd-Smith job stopped so the supervisor will not continue it.",
                input_schema={"type": "object", "required": ["job_id"], "properties": {"job_id": {"type": "string"}}},
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                host_service="cloyd-smith-loop",
                required_permission="coding.execute",
                tags=["cloyd", "smith", "pratt-5.2", "stop"],
            ),
            _cloyd_smith_stop,
        ),
        (
            ToolDefinition(
                name="cloyd_smith_retry",
                description="Run a bounded OpenCode health preflight and requeue one blocked, stale, or stopped Cloyd-Smith job.",
                input_schema={"type": "object", "required": ["job_id"], "properties": {"job_id": {"type": "string"}}},
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                host_service="cloyd-smith-loop",
                required_permission="coding.execute",
                tags=["cloyd", "smith", "pratt-5.2", "retry"],
            ),
            _cloyd_smith_retry,
        ),
        (
            ToolDefinition(
                name="cloyd_smith_mark_done",
                description="Mark a needs-review Cloyd-Smith job done after evidence proves the objective.",
                input_schema={"type": "object", "required": ["job_id"], "properties": {"job_id": {"type": "string"}}},
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                host_service="cloyd-smith-loop",
                required_permission="coding.execute",
                tags=["cloyd", "smith", "pratt-5.2", "review"],
            ),
            _cloyd_smith_mark_done,
        ),
        (
            ToolDefinition(
                name="cloyd_smith_mark_blocked",
                description="Mark an active or needs-review Cloyd-Smith job blocked with a concrete reason.",
                input_schema={
                    "type": "object",
                    "required": ["job_id"],
                    "properties": {
                        "job_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                },
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                host_service="cloyd-smith-loop",
                required_permission="coding.execute",
                tags=["cloyd", "smith", "pratt-5.2", "review"],
            ),
            _cloyd_smith_mark_blocked,
        ),
        (
            ToolDefinition(
                name="cloyd_smith_follow_up",
                description="Queue exactly one bounded follow-up prompt for a needs-review, blocked, or stale Cloyd-Smith job.",
                input_schema={
                    "type": "object",
                    "required": ["job_id", "prompt"],
                    "properties": {
                        "job_id": {"type": "string"},
                        "prompt": {"type": "string"},
                    },
                },
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                host_service="cloyd-smith-loop",
                required_permission="coding.execute",
                tags=["cloyd", "smith", "pratt-5.2", "follow-up"],
            ),
            _cloyd_smith_follow_up,
        ),
        (
            ToolDefinition(
                name="cloyd_smith_replace",
                description="Create a narrower replacement job for a blocked Cloyd-Smith job and supersede the old job.",
                input_schema={
                    "type": "object",
                    "required": ["job_id", "prompt"],
                    "properties": {
                        "job_id": {"type": "string"},
                        "prompt": {"type": "string"},
                        "objective": {"type": "string"},
                        "smith_alias": {"type": "string"},
                        "acceptance_criteria": {"type": "array"},
                    },
                },
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                host_service="cloyd-smith-loop",
                required_permission="coding.execute",
                tags=["cloyd", "smith", "pratt-5.2", "replace"],
            ),
            _cloyd_smith_replace,
        ),
    ):
        if registry.get_tool(definition.name) is None:
            registry.register(definition, implementation)
