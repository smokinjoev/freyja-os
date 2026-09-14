from __future__ import annotations

from typing import Any

from freyja.cloyd_smith_loop import (
    CloydSmithJobCreate,
    CloydSmithJobStatus,
    CloydSmithJobStore,
    CloydSmithJobUpdate,
)
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


def _job_summary(job, *, events: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "objective": job.objective,
        "smith_alias": job.smith_alias,
        "status": job.status.value,
        "acceptance_criteria": job.acceptance_criteria,
        "current_prompt": job.current_prompt,
        "next_action": job.next_action,
        "last_evidence": job.last_evidence,
        "error": job.error,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "events": events or [],
    }


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
            return {"ok": True, "job": _job_summary(job, events=store.events(job.job_id))}
        return {"ok": True, "jobs": [_job_summary(job) for job in store.list_active()]}
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
    except KeyError:
        return {"ok": False, "error": f"Unknown Cloyd Smith job: {job_id}"}
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "job": _job_summary(job)}


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
    return {"ok": True, "job": _job_summary(job)}


def register_cloyd_smith_loop_tools(registry: ToolRegistry) -> None:
    for definition, implementation in (
        (
            ToolDefinition(
                name="cloyd_smith_submit",
                description="Create a durable Pratt 5.2 Cloyd-Smith job and return a receipt for later status checks.",
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
    ):
        if registry.get_tool(definition.name) is None:
            registry.register(definition, implementation)
