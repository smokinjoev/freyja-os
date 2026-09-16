import hashlib
import hmac
import ipaddress
import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from freyja.agents import AgentHierarchy, PersonName
from freyja.agents.approval_provider import PersistentApprovalProvider
from freyja.agents.models import ApprovalStoreError, WritePilotResultWithApprovals
from freyja.agents.runtime import SmithRuntime
from freyja.agent_gateway import AgentGateway, GatewayAuthenticationError, GatewayPermissionError, GatewayRequest
from freyja.agent_runtime_v3 import AgentRuntimeV3, home_assistant_focus_for_text
from freyja.cloyd_smith_loop import (
    AgentRunHeartbeat,
    CloydSmithJobCreate,
    CloydSmithJobStatus,
    CloydSmithJobStore,
    CloydSmithJobUpdate,
    bounded_replacement_prompt,
    expected_smith_alias,
    enrich_loop_status_with_runtime,
    job_status_summary,
    loop_status_payload,
    read_supervisor_heartbeat,
)
from freyja.config import settings
from freyja.continuity import continuity_router
from freyja.contracts import CanonicalAttachment, CanonicalRequest, CanonicalResponse
from freyja.family_agents import FamilyRouteConfig, family_route_config, family_tool_policy, resolve_family_agent_alias
from freyja.foundation_models import GatewaySender, SecurityDomainId, SemanticEvent
from freyja.freyja3_memory import Freyja3MemoryStore
from freyja.freyja5_config import (
    FREYJA5_OPEN_WEBUI_AGENT_MODELS,
    freyja5_agent_evidence,
    freyja5_gateway_evidence,
    freyja5_iris_readiness_evidence,
    freyja5_live_inference_evidence,
    freyja5_live_blocker_evidence,
    freyja5_open_webui_agent_model_evidence,
    freyja5_plane_evidence,
    freyja5_readiness_certification_evidence,
    freyja5_readiness_mcp_evidence,
    freyja5_readiness_ok,
    freyja5_semantic_route_evidence,
    freyja5_traceability_evidence,
    freyja5_vulcan_evidence,
    freyja5_webgui_evidence,
)
from freyja.home_assistant_monitor import (
    start_home_assistant_inventory_monitor,
    stop_home_assistant_inventory_monitor,
)
from freyja.identity import person_context_from_headers
from freyja.inference import InferenceProviderProfile, ProviderReadiness, provider_registry_from_settings
from freyja.iris_router import IrisRouterClient
from freyja.iris_monitor import start_iris_warm_monitor, stop_iris_warm_monitor
from freyja.macagent import MacAgentClient
from freyja.media import AttachmentInput, images_from_attachments
from freyja.home_memory import home_memory_router
from freyja.memory import memory_router
from freyja.memory.principal import principal_from_headers
from freyja.ollama_client import OllamaClient
from freyja.openrouter_client import OpenRouterClient
from freyja.open_webui_tools import open_webui_tools_router
from freyja.router import RouteRequest, router
from freyja.semantic_events import SemanticEventPermissionError, SemanticEventQuery, SemanticEventStore
from freyja.tools.api import tools_router
from freyja.tools.builtin import register_builtin_tools, register_smith_read_only_tools, register_smith_write_pilot_tools
from freyja.tools.cloyd_smith_loop import _opencode_status_is_busy
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.opencode_runtime import _opencode_start, _opencode_status, _opencode_stop, opencode_health
from freyja.tools.registry import get_registry


logger = logging.getLogger(__name__)
FREYJA5_LEGACY_OPENAI_MODEL_ID = "freyja-5"
FREYJA5_OPENAI_MODEL_IDS = {FREYJA5_LEGACY_OPENAI_MODEL_ID, *FREYJA5_OPEN_WEBUI_AGENT_MODELS}
FREYJA5_AGENT_GATEWAY_MODELS = {
    "freyja": "agent/freyja",
    "cloyd": "agent/cloyd-gibbler",
    "smith": "agent/freyja-coder",
    "benedict": "agent/benedict",
    "agent-44": "agent/agent-47",
    "jenna": "agent/jennacide",
}
FREYJA_OPENWEBUI_TIMEZONE = "America/New_York"


class AgentRunFollowUpRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)


class AgentRunBlockRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class AgentRunReplacementRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=6000)
    objective: str | None = Field(default=None, max_length=1000)
    smith_alias: str | None = Field(default=None, max_length=80)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_iris_warm_monitor()
    start_home_assistant_inventory_monitor()
    try:
        yield
    finally:
        await stop_iris_warm_monitor()
        await stop_home_assistant_inventory_monitor()


app = FastAPI(
    title="Freyja Director",
    version="0.1.0",
    description="Core orchestration service for Freyja-OS.",
    lifespan=lifespan,
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "http_request method=%s path=%s status=%s duration_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.exception_handler(RequestValidationError)
async def log_validation_error(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    logger.warning(
        "http_validation_error method=%s path=%s status=422 errors=%s",
        request.method,
        request.url.path,
        errors,
    )
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


@app.middleware("http")
async def require_connector_auth(request: Request, call_next):
    """Require a bearer token for non-public Director endpoints when configured."""
    expected = settings.freyja_connector_token
    public_paths = {"/", "/health", "/agent-runs"}
    if (
        not expected
        or request.url.path in public_paths
        or request.url.path == "/road"
        or request.url.path.startswith("/road/")
        or request.url.path.startswith("/agent-runs/")
    ):
        return await call_next(request)

    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    authorized = (
        scheme.lower() == "bearer"
        and bool(supplied)
        and hmac.compare_digest(supplied, expected)
    )
    api_key = request.headers.get("x-api-key", "")
    if not authorized and api_key:
        authorized = hmac.compare_digest(api_key, expected)
    if not authorized:
        return JSONResponse(
            status_code=401,
            content={"detail": "Connector authentication required."},
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await call_next(request)

ollama = OllamaClient()
reasoning_ollama = OllamaClient(
    base_url=settings.ollama_reasoning_base_url or settings.ollama_base_url,
    model=settings.ollama_reasoning_model,
)
openrouter = OpenRouterClient()
iris_router = IrisRouterClient()
macagent = MacAgentClient()
router.register_clients(ollama, openrouter)
router.register_reasoning_client(reasoning_ollama)
router.register_iris_router_client(iris_router)
agent_gateway_v3 = AgentGateway()
semantic_event_store_v3 = SemanticEventStore()

app.include_router(memory_router)
app.routes.extend(home_memory_router.routes)
app.include_router(continuity_router)
app.include_router(open_webui_tools_router)
app.include_router(tools_router)

register_builtin_tools(get_registry())
register_smith_write_pilot_tools(get_registry())
register_smith_read_only_tools(get_registry())

# Enable the three approved write-pilot tools only when Smith write-pilot
# mode is enabled. They remain disabled by default so that a simple flag
# toggle is required before any write-pilot tool can be invoked.
if settings.agent_smith_enabled and settings.agent_smith_write_pilot_enabled:
    for _tool_name in ("write_pilot_file_write", "write_pilot_git_add", "write_pilot_git_commit"):
        get_registry().set_enabled(_tool_name, True)

freyja3_memory_store = Freyja3MemoryStore() if settings.memory_enabled else None
agent_runtime_v3 = AgentRuntimeV3(
    tool_registry=get_registry(),
    memory_store=freyja3_memory_store,
    run_inference=settings.freyja3_inference_enabled,
)


class FamilyRouteMessage(BaseModel):
    message: str
    agent: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    policy_mode: str | None = None
    channel: str = "family"


def _domain_from_header(value: str | None, default: SecurityDomainId = SecurityDomainId.HOUSEHOLD) -> SecurityDomainId:
    if not value:
        return default
    try:
        return SecurityDomainId(value)
    except ValueError:
        raise HTTPException(status_code=403, detail="Unknown security domain.") from None


@app.post("/events/semantic")
async def publish_semantic_event(event: SemanticEvent, raw_request: Request) -> dict[str, Any]:
    domain_id = _domain_from_header(raw_request.headers.get("x-freyja-security-domain"), SecurityDomainId.SYSTEM)
    try:
        stored = semantic_event_store_v3.publish(event, publisher_domain_id=domain_id)
    except SemanticEventPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return {"ok": True, "event": stored.model_dump(mode="json")}


@app.get("/events/semantic")
async def list_semantic_events(
    raw_request: Request,
    event_type: str | None = None,
    room: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    domain_id = _domain_from_header(raw_request.headers.get("x-freyja-security-domain"), SecurityDomainId.HOUSEHOLD)
    try:
        events = semantic_event_store_v3.list_events(
            SemanticEventQuery(event_type=event_type, room=room, limit=limit),
            reader_domain_id=domain_id,
        )
    except SemanticEventPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return {"ok": True, "events": [event.model_dump(mode="json") for event in events], "count": len(events)}


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "freyja-director",
        "status": "online",
        "version": "0.1.0",
    }


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/agent-runs", response_class=HTMLResponse)
async def agent_runs_page() -> str:
    return _agent_runs_html()


@app.get("/agent-runs/status", response_class=HTMLResponse)
async def agent_runs_human_status() -> str:
    return _agent_runs_human_status_html(_agent_runs_status_payload())


@app.get("/agent-runs/api/status")
async def agent_runs_status() -> dict[str, Any]:
    return _agent_runs_status_payload()


@app.get("/agent-runs/events")
async def agent_runs_events() -> StreamingResponse:
    async def event_stream():
        last_payload = ""
        while True:
            payload = json.dumps(_agent_runs_status_payload(), sort_keys=True, default=str)
            if payload != last_payload:
                yield f"event: status\ndata: {payload}\n\n"
                last_payload = payload
            await asyncio.sleep(5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/agent-runs/api/jobs/{job_id}/retry")
async def agent_runs_retry_job(job_id: str) -> dict[str, Any]:
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown Cloyd-Smith job: {job_id}") from None
    if job.status not in {CloydSmithJobStatus.BLOCKED, CloydSmithJobStatus.STALE, CloydSmithJobStatus.STOPPED}:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is {job.status.value}; only blocked, stale, or stopped jobs can be retried.")
    expected_alias = expected_smith_alias(job)
    if expected_alias and expected_alias != job.smith_alias:
        store.add_event(
            job_id,
            "operator_retry_alias_mismatch",
            {"source": "agent-runs-page", "current_alias": job.smith_alias, "expected_alias": expected_alias},
        )
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} targets {expected_alias} but is assigned to {job.smith_alias}; reroute or create a new job with smith_alias={expected_alias} before retrying.",
        )
    metadata = dict(job.metadata or {})
    retry = dict(metadata.get("retry") or {})
    attempts = int(retry.get("attempts") or 0)
    if attempts >= 3:
        store.add_event(
            job_id,
            "operator_retry_limit_reached",
            {"source": "agent-runs-page", "attempts": attempts, "previous_status": job.status.value},
        )
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} already has {attempts} retry attempts; inspect the error/output before requeueing.",
        )
    runtime = opencode_health(alias=job.smith_alias, timeout_seconds=5)
    if not runtime.get("ok"):
        store.add_event(job_id, "operator_retry_preflight_failed", {"source": "agent-runs-page", "runtime": runtime})
        raise HTTPException(status_code=503, detail=f"OpenCode runtime is not healthy: {runtime.get('error') or runtime}")
    status = await _opencode_status(
        ToolExecutionRequest(
            tool_name="opencode_status",
            arguments={"alias": job.smith_alias},
            actor="agent-runs-page",
        )
    )
    if not status.get("ok") or _opencode_status_is_busy(status):
        store.add_event(job_id, "operator_retry_runtime_busy", {"source": "agent-runs-page", "runtime": runtime, "status": status})
        store.update(
            job_id,
            CloydSmithJobUpdate(
                next_action="inspect_or_stop_opencode_session_before_retry",
                last_evidence={"operator_action": "retry_preflight_busy", "runtime": runtime, "status": status},
            ),
        )
        raise HTTPException(status_code=409, detail="OpenCode runtime is not ready for retry; inspect or stop the current session before requeueing.")
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
    store.add_event(job_id, "operator_retry", {"source": "agent-runs-page", "previous_status": job.status.value, "attempt": attempts, "runtime": runtime})
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
    return {"ok": True, "action": "retry", "job": updated.model_dump(mode="json")}


@app.post("/agent-runs/api/jobs/{job_id}/done")
async def agent_runs_mark_done(job_id: str) -> dict[str, Any]:
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown Cloyd-Smith job: {job_id}") from None
    if job.status != CloydSmithJobStatus.NEEDS_REVIEW:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is {job.status.value}; only needs_review jobs can be marked done from the monitor.")
    store.add_event(job_id, "operator_mark_done", {"source": "agent-runs-page"})
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
            last_message="Marked done from Agent Runs monitor.",
            working_directory="",
            stop_reason="operator_reviewed_done",
        )
    )
    return {"ok": True, "action": "done", "job": updated.model_dump(mode="json")}


@app.post("/agent-runs/api/jobs/{job_id}/clear")
async def agent_runs_clear_done_job(job_id: str) -> dict[str, Any]:
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown Cloyd-Smith job: {job_id}") from None
    if job.status != CloydSmithJobStatus.DONE:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is {job.status.value}; only done jobs can be cleared from the monitor.")
    metadata = dict(job.metadata)
    metadata["cleared_from_monitor"] = {
        "source": "agent-runs-page",
        "cleared_at": datetime.now(UTC).isoformat(),
        "previous_status": job.status.value,
    }
    store.add_event(job_id, "operator_clear_done", {"source": "agent-runs-page", "previous_status": job.status.value})
    updated = store.update(
        job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.STOPPED,
            next_action="cleared_from_monitor",
            last_evidence={"operator_action": "cleared_done"},
            metadata=metadata,
        ),
    )
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job_id,
            agent="smith",
            alias=job.smith_alias,
            state="stopped",
            phase="cleared",
            last_action="operator_clear_done",
            last_message="Cleared done job from Agent Runs monitor.",
            working_directory="",
            stop_reason="cleared_from_monitor",
        )
    )
    return {"ok": True, "action": "clear", "job": updated.model_dump(mode="json")}


@app.post("/agent-runs/api/jobs/{job_id}/block")
async def agent_runs_mark_blocked(job_id: str, request: AgentRunBlockRequest | None = None) -> dict[str, Any]:
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown Cloyd-Smith job: {job_id}") from None
    if job.status not in {CloydSmithJobStatus.NEEDS_REVIEW, CloydSmithJobStatus.QUEUED, CloydSmithJobStatus.RUNNING, CloydSmithJobStatus.STALE}:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is {job.status.value}; only active or needs-review jobs can be marked blocked from the monitor.")
    heartbeat = store.get_heartbeat(job_id)
    supplied_reason = (request.reason if request else None) or ""
    reason = supplied_reason.strip() or "operator marked blocked from Agent Runs monitor"
    if not supplied_reason.strip() and heartbeat and "INFERENCE_QUEUE_TIMEOUT" in heartbeat.last_message:
        reason = "review evidence is timeout-only; requested objective is not proven"
    elif not supplied_reason.strip() and job.error:
        reason = job.error
    store.add_event(job_id, "operator_mark_blocked", {"source": "agent-runs-page", "previous_status": job.status.value, "reason": reason})
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
    return {"ok": True, "action": "block", "job": updated.model_dump(mode="json")}


@app.post("/agent-runs/api/jobs/{job_id}/follow-up")
async def agent_runs_follow_up_job(job_id: str, request: AgentRunFollowUpRequest) -> dict[str, Any]:
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown Cloyd-Smith job: {job_id}") from None
    if job.status not in {CloydSmithJobStatus.NEEDS_REVIEW, CloydSmithJobStatus.BLOCKED, CloydSmithJobStatus.STALE}:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is {job.status.value}; only needs-review, blocked, or stale jobs can receive a follow-up from the monitor.")
    follow_up_prompt = request.prompt.strip()
    if not follow_up_prompt:
        raise HTTPException(status_code=422, detail="Follow-up prompt cannot be blank.")
    metadata = dict(job.metadata or {})
    follow_up = dict(metadata.get("follow_up") or {})
    attempts = int(follow_up.get("attempts") or 0)
    if attempts >= 1:
        store.add_event(job_id, "operator_follow_up_limit_reached", {"source": "agent-runs-page", "attempts": attempts, "previous_status": job.status.value})
        raise HTTPException(status_code=409, detail=f"Job {job_id} already has a bounded follow-up; mark blocked or create a new job instead of looping.")
    attempts += 1
    follow_up.update(
        {
            "attempts": attempts,
            "last_follow_up_at": datetime.now(UTC).isoformat(),
            "previous_status": job.status.value,
        }
    )
    metadata["follow_up"] = follow_up
    store.add_event(job_id, "operator_follow_up", {"source": "agent-runs-page", "previous_status": job.status.value, "attempt": attempts})
    updated = store.update(
        job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.QUEUED,
            current_prompt=follow_up_prompt,
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
    return {"ok": True, "action": "follow-up", "job": updated.model_dump(mode="json")}


@app.post("/agent-runs/api/jobs/{job_id}/replace")
async def agent_runs_create_replacement_job(job_id: str, request: AgentRunReplacementRequest) -> dict[str, Any]:
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown Cloyd-Smith job: {job_id}") from None
    if job.status != CloydSmithJobStatus.BLOCKED:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is {job.status.value}; only blocked jobs can be replaced from the monitor.")
    prompt_text = request.prompt.strip()
    if not prompt_text:
        raise HTTPException(status_code=422, detail="Replacement prompt cannot be blank.")
    objective = (request.objective or f"Replacement for blocked job {job_id}: {job.objective}").strip()
    smith_alias = (request.smith_alias or job.smith_alias or "freyja-code").strip()
    metadata = {
        "source": "agent-runs-replacement",
        "replaces": job_id,
        "replaced_objective": job.objective,
        "replacement_reason": job.error or "blocked job needed sharper replacement",
        "parent_metadata": job.metadata,
    }
    replacement = store.create(
        CloydSmithJobCreate(
            objective=objective,
            smith_alias=smith_alias,
            acceptance_criteria=[item.strip() for item in request.acceptance_criteria if item.strip()],
            current_prompt=prompt_text,
            created_by="agent-runs-page",
            metadata=metadata,
        )
    )
    store.add_event(
        job_id,
        "operator_create_replacement",
        {"source": "agent-runs-page", "replacement_job_id": replacement.job_id, "replacement_alias": smith_alias},
    )
    store.add_event(
        replacement.job_id,
        "submitted_as_replacement",
        {"source": "agent-runs-page", "replaces": job_id},
    )
    old_metadata = dict(job.metadata or {})
    old_metadata["superseded_by"] = replacement.job_id
    old_metadata["superseded_reason"] = "replaced by sharper Agent Runs job"
    updated = store.update(
        job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.STOPPED,
            next_action=f"superseded_by:{replacement.job_id}",
            last_evidence={"operator_action": "create_replacement", "replacement_job_id": replacement.job_id},
            metadata=old_metadata,
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
    return {
        "ok": True,
        "action": "replace",
        "replaced_job": updated.model_dump(mode="json"),
        "replacement_job": replacement.model_dump(mode="json"),
    }


@app.post("/agent-runs/api/jobs/{job_id}/queue-replacement")
async def agent_runs_queue_suggested_replacement_job(job_id: str) -> dict[str, Any]:
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown Cloyd-Smith job: {job_id}") from None
    if job.status != CloydSmithJobStatus.BLOCKED:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is {job.status.value}; only blocked jobs can be replaced from the monitor.")
    heartbeat = store.get_heartbeat(job_id)
    summary = job_status_summary(job, heartbeat=heartbeat)
    if not str(summary.get("replacement_prompt") or "").strip():
        raise HTTPException(status_code=409, detail=f"Job {job_id} does not have a suggested replacement action.")
    prompt_text = str(summary.get("replacement_prompt") or "").strip()
    if not prompt_text:
        prompt_text = bounded_replacement_prompt(job, heartbeat=heartbeat, error=job.error)
    objective = f"Suggested replacement for blocked job {job_id}: {job.objective}"
    metadata = {
        "source": "agent-runs-suggested-replacement",
        "replaces": job_id,
        "replaced_objective": job.objective,
        "replacement_reason": job.error or "blocked job needed sharper replacement",
        "parent_metadata": job.metadata,
    }
    replacement = store.create(
        CloydSmithJobCreate(
            objective=objective,
            smith_alias=job.smith_alias or "freyja-code",
            acceptance_criteria=[
                "Replacement job is narrower than the blocked objective.",
                "Evidence includes inspected files or URL and explicit no-change reason.",
                "Verification steps are reported before review.",
            ],
            current_prompt=prompt_text,
            created_by="agent-runs-page",
            metadata=metadata,
        )
    )
    store.add_event(
        job_id,
        "operator_queue_suggested_replacement",
        {"source": "agent-runs-page", "replacement_job_id": replacement.job_id, "replacement_alias": replacement.smith_alias},
    )
    store.add_event(
        replacement.job_id,
        "submitted_as_suggested_replacement",
        {"source": "agent-runs-page", "replaces": job_id},
    )
    old_metadata = dict(job.metadata or {})
    old_metadata["superseded_by"] = replacement.job_id
    old_metadata["superseded_reason"] = "replaced by suggested Agent Runs job"
    updated = store.update(
        job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.STOPPED,
            next_action=f"superseded_by:{replacement.job_id}",
            last_evidence={"operator_action": "queue_suggested_replacement", "replacement_job_id": replacement.job_id},
            metadata=old_metadata,
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
            last_action="operator_queue_suggested_replacement",
            last_message=f"Superseded by suggested replacement job {replacement.job_id}.",
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
            phase="suggested_replacement_queued",
            last_action="operator_queue_suggested_replacement",
            last_message=f"Queued suggested replacement for {job_id}.",
            working_directory="",
        )
    )
    return {
        "ok": True,
        "action": "queue-replacement",
        "replaced_job": updated.model_dump(mode="json"),
        "replacement_job": replacement.model_dump(mode="json"),
    }


@app.post("/agent-runs/api/jobs/{job_id}/stop")
async def agent_runs_stop_job(job_id: str) -> dict[str, Any]:
    store = CloydSmithJobStore()
    try:
        job = store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown Cloyd-Smith job: {job_id}") from None
    if job.status not in {CloydSmithJobStatus.QUEUED, CloydSmithJobStatus.RUNNING}:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is {job.status.value}; only queued or running jobs can be stopped from the monitor.")
    store.add_event(job_id, "operator_stop", {"source": "agent-runs-page", "previous_status": job.status.value})
    updated = store.update(
        job_id,
        CloydSmithJobUpdate(
            status=CloydSmithJobStatus.STOPPED,
            next_action="operator_stopped",
            last_evidence={"operator_action": "stopped"},
        ),
    )
    store.record_heartbeat(
        AgentRunHeartbeat(
            job_id=job_id,
            agent="smith",
            alias=job.smith_alias,
            state="stopped",
            phase="operator_stopped",
            last_action="operator_stop",
            last_message="Stopped from Agent Runs monitor.",
            working_directory="",
            stop_reason="operator_stopped",
        )
    )
    return {"ok": True, "action": "stop", "job": updated.model_dump(mode="json")}


@app.post("/agent-runs/api/jobs/requeue-incomplete")
async def agent_runs_requeue_incomplete_jobs() -> dict[str, Any]:
    store = CloydSmithJobStore()
    jobs = _incomplete_agent_run_jobs(store)
    stopped_runtime = await _stop_runtime_if_jobs_running(jobs)
    updated_ids: list[str] = []
    now = datetime.now(UTC)
    for job in jobs:
        metadata = dict(job.metadata or {})
        bulk = dict(metadata.get("bulk_requeue") or {})
        attempts = int(bulk.get("attempts") or 0) + 1
        bulk.update({"attempts": attempts, "last_requeue_at": now.isoformat(), "previous_status": job.status.value})
        metadata["bulk_requeue"] = bulk
        store.add_event(job.job_id, "operator_bulk_requeue", {"source": "agent-runs-page", "previous_status": job.status.value, "attempt": attempts})
        store.update(
            job.job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus.QUEUED,
                next_action="send_to_smith",
                last_evidence={"operator_action": "bulk_requeue", "previous_status": job.status.value, "runtime_stop": stopped_runtime},
                metadata=metadata,
                error="",
            ),
        )
        store.record_heartbeat(
            AgentRunHeartbeat(
                job_id=job.job_id,
                agent="smith",
                alias=job.smith_alias,
                state="queued",
                phase="operator_bulk_requeued",
                last_action="operator_bulk_requeue",
                last_message="Requeued incomplete work from Agent Runs monitor.",
                working_directory="",
                started_at=now,
            )
        )
        updated_ids.append(job.job_id)
    return {"ok": True, "action": "requeue-incomplete", "updated_jobs": updated_ids, "runtime_stop": stopped_runtime}


@app.post("/agent-runs/api/jobs/stop-all")
async def agent_runs_stop_all_jobs() -> dict[str, Any]:
    store = CloydSmithJobStore()
    jobs = _incomplete_agent_run_jobs(store)
    stopped_runtime = await _stop_runtime_if_jobs_running(jobs, always=True)
    updated_ids: list[str] = []
    for job in jobs:
        store.add_event(job.job_id, "operator_bulk_stop", {"source": "agent-runs-page", "previous_status": job.status.value})
        store.update(
            job.job_id,
            CloydSmithJobUpdate(
                status=CloydSmithJobStatus.STOPPED,
                next_action="operator_stopped_all_work",
                last_evidence={"operator_action": "bulk_stop", "previous_status": job.status.value, "runtime_stop": stopped_runtime},
                error="",
            ),
        )
        store.record_heartbeat(
            AgentRunHeartbeat(
                job_id=job.job_id,
                agent="smith",
                alias=job.smith_alias,
                state="stopped",
                phase="operator_bulk_stopped",
                last_action="operator_bulk_stop",
                last_message="Stopped by Stop All Work from Agent Runs monitor.",
                working_directory="",
                stop_reason="operator_stopped_all_work",
            )
        )
        updated_ids.append(job.job_id)
    return {"ok": True, "action": "stop-all", "updated_jobs": updated_ids, "runtime_stop": stopped_runtime}


def _incomplete_agent_run_jobs(store: CloydSmithJobStore) -> list[Any]:
    jobs: dict[str, Any] = {}
    incomplete_statuses = {
        CloydSmithJobStatus.QUEUED,
        CloydSmithJobStatus.RUNNING,
        CloydSmithJobStatus.NEEDS_REVIEW,
        CloydSmithJobStatus.BLOCKED,
        CloydSmithJobStatus.STALE,
    }
    for job in [*store.list_active(limit=200), *store.list_recent_terminal(limit=200)]:
        if job.status in incomplete_statuses:
            jobs[job.job_id] = job
    return list(jobs.values())


async def _stop_runtime_if_jobs_running(jobs: list[Any], *, always: bool = False) -> dict[str, Any] | None:
    if not always and not any(job.status == CloydSmithJobStatus.RUNNING for job in jobs):
        return None
    result = await _opencode_stop(
        ToolExecutionRequest(
            tool_name="opencode_stop",
            arguments={"alias": "freyja-code"},
            actor="agent-runs-page",
        )
    )
    return result


@app.get("/agent-runs/api/runtime/health")
async def agent_runs_runtime_health() -> dict[str, Any]:
    health = opencode_health(alias="freyja-code", timeout_seconds=5)
    if not health.get("ok"):
        return health
    status = await _opencode_status(
        ToolExecutionRequest(
            tool_name="opencode_status",
            arguments={"alias": "freyja-code"},
            actor="agent-runs-page",
        )
    )
    if not status.get("ok"):
        health["status_error"] = status.get("error") or str(status)
        return health
    health.update(
        {
            "session": status.get("session"),
            "state": status.get("state"),
            "working_directory": status.get("working_directory"),
            "recent_action": status.get("recent_action"),
        }
    )
    return health


@app.post("/agent-runs/api/runtime/stop")
async def agent_runs_runtime_stop() -> dict[str, Any]:
    result = await _opencode_stop(
        ToolExecutionRequest(
            tool_name="opencode_stop",
            arguments={"alias": "freyja-code"},
            actor="agent-runs-page",
        )
    )
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error") or str(result))
    return {"ok": True, "action": "runtime_stop", **result}


@app.post("/agent-runs/api/runtime/reset")
async def agent_runs_runtime_reset() -> dict[str, Any]:
    store = CloydSmithJobStore()
    stop = await _opencode_stop(
        ToolExecutionRequest(
            tool_name="opencode_stop",
            arguments={"alias": "freyja-code"},
            actor="agent-runs-page",
        )
    )
    start = await _opencode_start(
        ToolExecutionRequest(
            tool_name="opencode_start",
            arguments={"alias": "freyja-code", "directory": settings.repository_root},
            actor="agent-runs-page",
        )
    )
    if not start.get("ok"):
        raise HTTPException(status_code=503, detail=start.get("error") or str(start))
    updated_jobs = _record_runtime_reset_on_busy_timeout_jobs(store, stop=stop, start=start)
    return {"ok": True, "action": "runtime_reset", "stopped": stop, "started": start, "updated_jobs": updated_jobs}


def _record_runtime_reset_on_busy_timeout_jobs(
    store: CloydSmithJobStore,
    *,
    stop: dict[str, Any],
    start: dict[str, Any],
) -> list[str]:
    updated_job_ids: list[str] = []
    for job in store.list_recent_terminal(limit=20):
        if job.status != CloydSmithJobStatus.BLOCKED:
            continue
        heartbeat = store.get_heartbeat(job.job_id)
        if not heartbeat or heartbeat.phase != "smith_busy_timeout":
            continue
        metadata = dict(job.metadata or {})
        runtime_reset = dict(metadata.get("runtime_reset") or {})
        attempts = int(runtime_reset.get("attempts") or 0) + 1
        runtime_reset.update(
            {
                "attempts": attempts,
                "last_reset_at": datetime.now(UTC).isoformat(),
                "stopped_session": stop.get("session"),
                "started_session": (start or {}).get("session"),
                "source": "agent-runs-page",
            }
        )
        metadata["runtime_reset"] = runtime_reset
        store.add_event(job.job_id, "operator_runtime_reset", {"source": "agent-runs-page", "stop": stop, "start": start, "attempt": attempts})
        store.update(
            job.job_id,
            CloydSmithJobUpdate(
                next_action="runtime reset completed; use one bounded Retry only if the prompt is still worth running",
                last_evidence={"operator_action": "runtime_reset", "stop": stop, "start": start, "attempt": attempts},
                metadata=metadata,
            ),
        )
        updated_job_ids.append(job.job_id)
    return updated_job_ids


def _agent_runs_status_payload() -> dict[str, Any]:
    return enrich_loop_status_with_runtime(loop_status_payload(), opencode_health(alias="freyja-code", timeout_seconds=5))


def _agent_runs_human_status_html(payload: dict[str, Any]) -> str:
    supervisor = payload.get("supervisor") or {}
    cycle = payload.get("cycle") or {}
    queue = payload.get("queue") or {}
    runtime = payload.get("runtime") or {}
    diagnostics = payload.get("diagnostics") or []
    runs = payload.get("runs") or []
    supervisor_text = "alive" if supervisor.get("ok") else "needs attention"
    runtime_text = "healthy" if runtime.get("ok") else "unhealthy"
    headline = str(cycle.get("summary") or "No status summary available.")
    rows = [
        ("Supervisor", f"{supervisor_text} ({supervisor.get('status', 'unknown')}, age {supervisor.get('age_seconds', 'unknown')}s)"),
        ("Loop step", str(cycle.get("current_step") or "unknown")),
        ("Independent", "yes" if cycle.get("independent") else "no"),
        ("OpenCode", f"{runtime_text}, {runtime.get('session_count', 0)} active session(s)"),
        ("Queue", f"{queue.get('queued', 0)} queued, {queue.get('running', 0)} running, {queue.get('needs_review', 0)} review, {queue.get('blocked', 0)} blocked, {queue.get('stale', 0)} stale"),
    ]
    diagnostics_html = "\n".join(
        f"<li class=\"{_html_attr(item.get('level') or '')}\"><strong>{_html(item.get('title') or '')}</strong><span>{_html(item.get('detail') or '')}</span></li>"
        for item in diagnostics
    ) or "<li><strong>No diagnostics</strong><span>No issues reported.</span></li>"
    run_items = "\n".join(
        f"<li><strong>{_html(run.get('state') or run.get('job_status') or '')}</strong><span>{_html(run.get('objective') or '')}</span><code>{_html(run.get('job_id') or '')}</code></li>"
        for run in runs[:5]
    ) or "<li><strong>No visible runs</strong><span>The durable ledger has no active or recent visible work.</span></li>"
    rows_html = "\n".join(f"<dt>{_html(label)}</dt><dd>{_html(value)}</dd>" for label, value in rows)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Runs Status</title>
  <style>
    :root {{ color-scheme: dark; --bg: #0f1113; --panel: #171a1d; --text: #edf1f3; --muted: #a9b2b9; --line: #2c3338; --ok: #72d391; --warn: #f3c969; --bad: #ff7c7c; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font: 16px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 880px; margin: 0 auto; padding: 32px 18px; }}
    h1 {{ margin: 0 0 6px; font-size: clamp(28px, 5vw, 42px); }}
    .headline {{ margin: 0 0 18px; color: var(--muted); font-size: 18px; }}
    section {{ border: 1px solid var(--line); border-radius: 8px; background: var(--panel); padding: 16px; margin: 14px 0; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    dl {{ display: grid; grid-template-columns: 140px 1fr; gap: 8px 14px; margin: 0; }}
    dt {{ color: var(--muted); }}
    dd {{ margin: 0; }}
    ul {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }}
    li {{ border-left: 4px solid var(--line); padding-left: 10px; }}
    li.ok {{ border-left-color: var(--ok); }}
    li.review {{ border-left-color: var(--warn); }}
    li.blocked {{ border-left-color: var(--bad); }}
    li strong, li span, li code {{ display: block; }}
    li span {{ color: var(--muted); }}
    code {{ color: var(--muted); overflow-wrap: anywhere; }}
    a {{ color: #9dccff; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    button {{ appearance: none; border: 1px solid var(--line); border-radius: 6px; background: #20262b; color: var(--text); padding: 9px 12px; font: inherit; cursor: pointer; }}
    button:hover {{ border-color: #9dccff; }}
  </style>
</head>
<body>
  <main>
    <h1>Agent Runs Status</h1>
    <p class="headline">{_html(headline)}</p>
    <section><h2>Now</h2><dl>{rows_html}</dl></section>
    <section><h2>Diagnostics</h2><ul>{diagnostics_html}</ul></section>
    <section><h2>Recent Work</h2><ul>{run_items}</ul></section>
    <section><h2>Controls</h2><div class="actions">
      <button type="button" data-bulk-action="requeue-incomplete">Requeue Incomplete Work</button>
      <button type="button" data-bulk-action="stop-all">Stop All Work</button>
    </div></section>
    <p><a href="/agent-runs">Open live monitor</a> · <a href="/agent-runs/api/status">JSON API</a></p>
  </main>
  <script>
    document.addEventListener('click', async event => {{
      const button = event.target.closest('button[data-bulk-action]');
      if (!button) return;
      const action = button.dataset.bulkAction;
      const label = button.textContent;
      const message = action === 'stop-all'
        ? 'Stop all incomplete work and abort the OpenCode runtime?'
        : 'Requeue all incomplete work and restart it through the durable loop?';
      if (!confirm(message)) return;
      button.disabled = true;
      button.textContent = 'Working...';
      try {{
        const response = await fetch(`/agent-runs/api/jobs/${{action}}`, {{ method: 'POST' }});
        const body = await response.json();
        if (!response.ok || !body.ok) throw new Error(body.detail || body.error || 'Bulk action failed');
        location.reload();
      }} catch (error) {{
        button.disabled = false;
        button.textContent = 'Failed';
        alert(error.message || String(error));
        setTimeout(() => {{ button.textContent = label; }}, 1400);
      }}
    }});
  </script>
</body>
</html>"""


def _html(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _html_attr(value: Any) -> str:
    return "".join(char for char in str(value) if char.isalnum() or char in {"-", "_"})


def _agent_run_is_hidden_terminal(run: dict[str, Any]) -> bool:
    if run.get("job_status") != "stopped":
        return False
    if run.get("phase") == "cleared" or run.get("stop_reason") == "cleared_from_monitor":
        return True
    if run.get("phase") == "superseded" or run.get("stop_reason") == "superseded":
        return True
    return str(run.get("next_action") or "").startswith("superseded_by:")


def _agent_runs_diagnostics(runs: list[dict[str, Any]], *, supervisor: dict[str, Any] | None = None) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    if supervisor and not supervisor.get("ok"):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Supervisor heartbeat stale",
                "detail": f"Cloyd-Smith loop heartbeat is {supervisor.get('status')}; restart or inspect the LaunchAgent before trusting idle queue state.",
            }
        )
    alias_mismatches = [
        run
        for run in runs
        if run.get("alias_mismatch") and run.get("job_status") not in {"done", "stopped"}
    ]
    if alias_mismatches:
        expected = ", ".join(
            f"{run.get('job_id')} -> {run.get('expected_alias')}"
            for run in alias_mismatches[:3]
        )
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Wrong Smith alias",
                "detail": f"Jobs are assigned to the wrong worker for their target: {expected}. Reroute or create a new job with the expected alias before retrying.",
            }
        )
    retrying = [
        run
        for run in runs
        if int(run.get("retry_attempts") or 0) >= 2 and run.get("job_status") not in {"done", "stopped"}
    ]
    if retrying:
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Retry attempts accumulating",
                "detail": "One or more jobs have been retried at least twice. Stop blind retries; inspect the OpenCode error/output and tighten the next prompt or runtime before trying again.",
            }
        )
    followed_up = [run for run in runs if int(run.get("follow_up_attempts") or 0) >= 1 and run.get("job_status") in {"needs_review", "blocked", "stale"}]
    if followed_up:
        diagnostics.append(
            {
                "level": "review",
                "title": "Follow-up already used",
                "detail": "One or more jobs already consumed their bounded follow-up. Mark done only with evidence, otherwise mark blocked with a concrete reason.",
            }
        )
    if any(run["job_status"] == "blocked" and run.get("phase") == "send_failed" for run in runs):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "OpenCode send failed",
                "detail": "At least one job could not be handed to Smith. Use Retry after confirming the OpenCode runtime is healthy, or leave it blocked with the error visible.",
            }
        )
    if any(run["job_status"] == "blocked" and run.get("phase") == "smith_busy_timeout" for run in runs):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Smith busy timeout",
                "detail": "A bounded Smith job stayed busy past the max window and the loop stopped the OpenCode runtime. Inspect the visible error before retrying or queueing a smaller replacement.",
            }
        )
    if any("repeated Smith busy timeouts" in str(run.get("next_action") or "") and int(run.get("runtime_reset_attempts") or 0) == 0 for run in runs):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "OpenCode runtime inspection needed",
                "detail": "Repeated smaller replacements are timing out before producing output. Stop queueing replacements and inspect or reset the OpenCode runtime/session.",
            }
        )
    if any(int(run.get("runtime_reset_attempts") or 0) >= 1 and run.get("job_status") == "blocked" for run in runs):
        diagnostics.append(
            {
                "level": "review",
                "title": "Runtime reset completed",
                "detail": "OpenCode was reset after busy timeouts. A single bounded Retry is available if the job is still worth running; otherwise leave it blocked with the visible reason.",
            }
        )
    if any("INFERENCE_QUEUE_TIMEOUT" in str(run.get("last_message") or "") for run in runs):
        diagnostics.append(
            {
                "level": "review",
                "title": "Inference queue timeout evidence",
                "detail": "Review jobs include timeout evidence. Do not mark them done unless the output also proves the requested objective, diff, and verification.",
            }
        )
    if any(run["job_status"] == "blocked" and run.get("next_action") == "draft a sharper replacement job with verifiable acceptance criteria, or leave blocked with this reason visible" for run in runs):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Sharper replacement needed",
                "detail": "A blocked job has insufficient evidence for its broad objective. Do not retry blindly; draft a smaller replacement with explicit files, expected evidence, and verification steps.",
            }
        )
    if any(run["job_status"] == "needs_review" for run in runs):
        diagnostics.append(
            {
                "level": "review",
                "title": "Human or Cloyd review required",
                "detail": "Needs-review jobs are idle and waiting for evidence review. Mark Done only after evidence matches the objective; otherwise send one bounded follow-up or mark blocked.",
            }
        )
    if any(run["job_status"] == "blocked" for run in runs):
        diagnostics.append(
            {
                "level": "blocked",
                "title": "Blocked jobs need review",
                "detail": "At least one job is blocked without an automatic queue-clearing action. Inspect the reason, then create a sharper replacement job or leave it blocked with the reason visible.",
            }
        )
    if not diagnostics and any(run["job_status"] in {"queued", "running"} for run in runs):
        diagnostics.append(
            {
                "level": "review",
                "title": "Work in progress",
                "detail": "A job is queued or running. Wait for output_ready, needs_review, blocked, or stale before taking a queue-clearing action.",
            }
        )
    if not diagnostics:
        diagnostics.append(
            {
                "level": "ok",
                "title": "Loop quiet",
                "detail": "No blocked, stale, or review jobs are visible in the canonical ledger.",
            }
        )
    return diagnostics


def _agent_runs_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent Runs</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #101214;
      --panel: #171a1d;
      --line: #2a3035;
      --text: #f1f4f6;
      --muted: #a9b3bc;
      --ok: #65d391;
      --warn: #f1bd63;
      --bad: #f17878;
      --accent: #7ab7ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    main { width: min(1180px, calc(100% - 32px)); margin: 24px auto 48px; }
    header { display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 18px; }
    h1 { margin: 0; font-size: 28px; font-weight: 700; }
    .sub { color: var(--muted); margin-top: 6px; }
    .pill { border: 1px solid var(--line); border-radius: 999px; padding: 7px 10px; color: var(--muted); white-space: nowrap; }
    .summary {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
      gap: 10px;
      margin: 0 0 14px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      background: var(--panel);
    }
    .metric strong { display: block; font-size: 22px; line-height: 1; }
    .metric span { display: block; color: var(--muted); font-size: 12px; margin-top: 6px; }
    .metric.attention strong, .metric.blocked strong, .metric.stale strong { color: var(--bad); }
    .metric.review strong { color: var(--warn); }
    .metric.running strong { color: var(--accent); }
    .diagnostics {
      display: grid;
      gap: 8px;
      margin: 0 0 14px;
    }
    .diagnostic {
      border: 1px solid var(--line);
      border-left: 4px solid var(--accent);
      border-radius: 8px;
      padding: 10px 12px;
      background: var(--panel);
    }
    .diagnostic.blocked { border-left-color: var(--bad); }
    .diagnostic.review { border-left-color: var(--warn); }
    .diagnostic.ok { border-left-color: var(--ok); }
    .diagnostic strong { display: block; margin-bottom: 4px; }
    .diagnostic span { color: var(--muted); font-size: 13px; line-height: 1.35; }
    .copybar {
      display: grid;
      grid-template-columns: 1fr auto auto auto auto auto;
      gap: 8px;
      align-items: center;
      margin: 12px 0;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #121518;
    }
    .toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0 0 14px;
    }
    .jobid {
      color: #d2d8dd;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    button {
      appearance: none;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #20262b;
      color: var(--text);
      padding: 8px 10px;
      font: inherit;
      font-size: 13px;
      cursor: pointer;
      min-height: 34px;
    }
    button:hover { border-color: var(--accent); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px; }
    .run {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-height: 220px;
    }
    .top { display: flex; justify-content: space-between; gap: 10px; align-items: start; }
    .state { font-weight: 700; text-transform: uppercase; font-size: 12px; letter-spacing: .04em; color: var(--accent); }
    .state.stale, .state.blocked { color: var(--bad); }
    .state.needs_review { color: var(--warn); }
    .state.done { color: var(--ok); }
    .objective { margin: 10px 0 12px; font-size: 16px; line-height: 1.35; }
    dl { display: grid; grid-template-columns: 104px 1fr; gap: 7px 10px; margin: 0; color: var(--muted); font-size: 13px; }
    dt { color: #d2d8dd; }
    dd { margin: 0; overflow-wrap: anywhere; }
    .next { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line); color: var(--text); }
    .feed { margin-top: 22px; border-top: 1px solid var(--line); padding-top: 14px; }
    .feed h2 { font-size: 18px; margin: 0 0 10px; }
    .event { color: var(--muted); border-left: 3px solid var(--line); padding: 7px 0 7px 10px; font-size: 13px; }
    .empty { color: var(--muted); padding: 28px 0; }
    @media (max-width: 620px) {
      .copybar { grid-template-columns: 1fr; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Agent Runs</h1>
        <div class="sub">Live Cloyd, Smith, and OpenCode work loop status.</div>
      </div>
      <div id="connection" class="pill">connecting...</div>
    </header>
    <section id="summary" class="summary"></section>
    <section class="toolbar">
      <button type="button" data-bulk-action="requeue-incomplete">Requeue Incomplete Work</button>
      <button type="button" data-bulk-action="stop-all">Stop All Work</button>
    </section>
    <section id="diagnostics" class="diagnostics"></section>
    <section id="runs" class="grid"></section>
    <section class="feed">
      <h2>Live Feed</h2>
      <div id="feed"></div>
    </section>
  </main>
  <script>
    const runsEl = document.getElementById('runs');
    const summaryEl = document.getElementById('summary');
    const diagnosticsEl = document.getElementById('diagnostics');
    const feedEl = document.getElementById('feed');
    const connectionEl = document.getElementById('connection');
    const seen = new Map();
    let latestPayload = {};

    function seconds(value) {
      if (value === null || value === undefined) return 'unknown';
      if (value < 90) return `${value}s`;
      const mins = Math.floor(value / 60);
      if (mins < 90) return `${mins}m`;
      return `${Math.floor(mins / 60)}h ${mins % 60}m`;
    }

    function render(payload) {
      latestPayload = payload || {};
      const queue = payload.queue || {};
      const supervisor = payload.supervisor || {};
      connectionEl.textContent = `live - ${payload.active_count} active - ${payload.attention_count || 0} need attention`;
      summaryEl.innerHTML = [
        metric('Supervisor', supervisor.ok ? 'OK' : 'Check', supervisor.ok ? 'running' : 'blocked'),
        metric('Active', payload.active_count || 0, 'running'),
        metric('Needs Review', queue.needs_review || 0, 'review'),
        metric('Blocked', queue.blocked || 0, 'blocked'),
        metric('Stale', queue.stale || 0, 'stale'),
        metric('Queued', queue.queued || 0, ''),
        metric('Done', queue.done || 0, '')
      ].join('');
      diagnosticsEl.innerHTML = (payload.diagnostics || []).map(item => `
        <div class="diagnostic ${escapeHtml(item.level || '')}">
          <strong>${escapeHtml(item.title || '')}</strong>
          <span>${escapeHtml(item.detail || '')}</span>
        </div>
      `).join('');
      renderSupervisor(supervisor);
      if (!payload.runs.length) {
        runsEl.innerHTML = '<div class="empty">No active or recent agent runs.</div>';
        return;
      }
      runsEl.innerHTML = payload.runs.map(run => `
        <article class="run">
          <div class="top">
            <div class="state ${run.state}">${run.state}</div>
            <div class="pill">${run.alias}</div>
          </div>
	          <div class="copybar">
	            <div class="jobid">${escapeHtml(run.job_id)}</div>
	            <button type="button" data-copy="${escapeAttr(run.job_id)}">Copy ID</button>
	            <button type="button" data-copy="${escapeAttr(reviewPrompt(run))}">Copy Cloyd Prompt</button>
	            ${replacementPromptButton(run)}
	            ${actionButton(run, 'queue-replacement', 'Queue Suggested Replacement')}
	            ${actionButton(run, 'retry', 'Retry')}
	            ${actionButton(run, 'done', 'Mark Done')}
	            ${actionButton(run, 'clear', 'Clear')}
	            ${actionButton(run, 'follow-up', 'Follow Up')}
	            ${actionButton(run, 'replace', 'Create Replacement')}
            ${actionButton(run, 'block', 'Mark Blocked')}
            ${actionButton(run, 'stop', 'Stop')}
          </div>
          <div class="objective">${escapeHtml(run.objective)}</div>
          <dl>
            <dt>Phase</dt><dd>${escapeHtml(run.phase || '')}</dd>
            <dt>Last action</dt><dd>${escapeHtml(run.last_action || '')}</dd>
            <dt>Message</dt><dd>${escapeHtml(run.last_message || '')}</dd>
            <dt>Error</dt><dd>${escapeHtml(run.last_error || '')}</dd>
            <dt>Age</dt><dd>${seconds(run.elapsed_seconds)}</dd>
            <dt>Retries</dt><dd>${run.retry_attempts || 0}</dd>
            <dt>Follow-ups</dt><dd>${run.follow_up_attempts || 0}</dd>
            <dt>Stale</dt><dd>${run.is_stale ? 'yes' : 'no'}</dd>
            <dt>Workdir</dt><dd>${escapeHtml(run.working_directory || '')}</dd>
          </dl>
          <div class="next"><strong>Next:</strong> ${escapeHtml(run.next_action || '')}</div>
        </article>
      `).join('');

      for (const run of payload.runs) {
        const key = `${run.job_id}:${run.state}:${run.phase}:${run.last_action}:${run.last_message}:${run.next_action}`;
        if (seen.get(run.job_id) === key) continue;
        seen.set(run.job_id, key);
        const item = document.createElement('div');
        item.className = 'event';
        item.textContent = `${new Date().toLocaleTimeString()} - ${run.alias} ${run.state}/${run.phase}: ${run.last_action || 'status'} - ${run.next_action || ''}`;
        feedEl.prepend(item);
        while (feedEl.children.length > 20) feedEl.removeChild(feedEl.lastChild);
      }
      updateRuntimeHealth();
    }

    function metric(label, value, cls) {
      return `<div class="metric ${cls}"><strong>${value}</strong><span>${label}</span></div>`;
    }

    function renderSupervisor(supervisor) {
      if (!supervisor || !Object.keys(supervisor).length) return;
      const payload = supervisor.payload || {};
      const detail = supervisor.ok
        ? `${escapeHtml(supervisor.status || 'ok')} - age ${seconds(supervisor.age_seconds)} - pid ${escapeHtml(payload.pid || 'unknown')} - last results ${escapeHtml(payload.result_count ?? 0)}`
        : `${escapeHtml(supervisor.status || 'unknown')} - ${escapeHtml(supervisor.error || 'heartbeat is not fresh')}`;
      const html = `<div id="supervisor-health" class="diagnostic ${supervisor.ok ? 'ok' : 'blocked'}">
        <strong>Cloyd-Smith supervisor ${supervisor.ok ? 'alive' : 'needs attention'}</strong>
        <span>${detail}</span>
      </div>`;
      const existing = document.getElementById('supervisor-health');
      if (existing) existing.outerHTML = html;
      else diagnosticsEl.insertAdjacentHTML('afterbegin', html);
    }

	    function actionButton(run, action, label) {
      const status = run.job_status || run.state || '';
      const enabled = (
		        (action === 'retry' && ['blocked', 'stale', 'stopped'].includes(status)) ||
		        (action === 'done' && status === 'needs_review') ||
		        (action === 'clear' && status === 'done') ||
		        (action === 'follow-up' && ['needs_review', 'blocked', 'stale'].includes(status) && !run.follow_up_attempts) ||
		        (action === 'queue-replacement' && status === 'blocked' && !!run.replacement_prompt) ||
		        (action === 'replace' && status === 'blocked' && !!run.suggested_prompt) ||
		        (action === 'block' && ['needs_review', 'queued', 'running', 'stale'].includes(status)) ||
		        (action === 'stop' && ['queued', 'running'].includes(status))
	      );
      if (!enabled) return '';
	      return `<button type="button" data-action="${action}" data-job-id="${escapeAttr(run.job_id)}">${label}</button>`;
	    }

	    function replacementPromptButton(run) {
	      if (!run.replacement_prompt && !run.suggested_prompt && !String(run.next_action || '').includes('sharper replacement job')) return '';
	      return `<button type="button" data-copy="${escapeAttr(replacementPrompt(run))}">Copy Replacement Prompt</button>`;
	    }

	    function reviewPrompt(run) {
      const supervisor = latestPayload.supervisor || {};
      const supervisorPayload = supervisor.payload || {};
      return [
        'Cloyd, do not start a fresh OpenCode session.',
        'Review this job from the canonical Agent Runs monitor page snapshot. This pasted snapshot is authoritative for this request.',
        `supervisor_ok: ${supervisor.ok === undefined ? '' : supervisor.ok}`,
        `supervisor_status: ${supervisor.status || ''}`,
        `supervisor_age_seconds: ${supervisor.age_seconds ?? ''}`,
        `supervisor_pid: ${supervisorPayload.pid || ''}`,
        `job_id: ${run.job_id}`,
        `alias: ${run.alias || ''}`,
        `state: ${run.state || ''}`,
        `job_status: ${run.job_status || ''}`,
        `phase: ${run.phase || ''}`,
        `last_action: ${run.last_action || ''}`,
        `next_action: ${run.next_action || ''}`,
        `objective: ${run.objective || ''}`,
        `working_directory: ${run.working_directory || ''}`,
        `last_message_excerpt: ${(run.last_message || '').slice(0, 900)}`,
        'Use http://100.115.228.56:8000/agent-runs/api/status as the source of truth.',
        'If cloyd_smith.status or any other tool says this job does not exist, treat that tool as stale/wrong and say the tool is stale.',
        'Do not switch to a different blocked job unless Joe explicitly asks.',
        'Do the next queue-clearing action now instead of only describing it:',
        '- If evidence is complete and acceptable, mark this job done/reviewed.',
        '- If it cannot proceed, mark this job blocked with the concrete reason.',
        '- If more work is needed, send exactly one bounded follow-up Smith/OpenCode task with verification requirements.',
        'Then tell me what action you took and what remains, if anything.'
	      ].join('\\n');
	    }

	    function replacementPrompt(run) {
	      if (run.replacement_prompt) return run.replacement_prompt;
	      return [
	        'Smith, this is a bounded replacement for a blocked Cloyd-Smith job. Do not retry the old session and do not broaden the task.',
	        `blocked_job_id: ${run.job_id}`,
	        `blocked_objective: ${run.objective || ''}`,
	        `blocked_reason: ${run.last_error || run.last_message || ''}`,
	        `working_directory: ${run.working_directory || ''}`,
	        `metadata: ${JSON.stringify(run.metadata || {})}`,
	        'Task:',
	        '- Perform one read-only inventory of the exact files, service URL, or narrow surface named above.',
	        '- If the blocked reason names files, inspect only those files unless one adjacent route/module file is required to understand them.',
	        '- Use .venv/bin/python or python3 for Python checks; do not call bare python.',
	        '- Do not edit files, start broad implementation work, or create a new unrelated session.',
	        'Acceptance criteria:',
	        '- Report the files or URL inspected.',
	        '- State whether any existing change is present.',
	        '- Name the smallest safe next task, or say no action is needed.',
	        '- Include verification evidence or the exact reason verification was not possible.'
	      ].join('\\n');
	    }

	    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, char => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[char]));
    }

    function escapeAttr(value) {
      return escapeHtml(value).replace(/`/g, '&#96;');
    }

    async function copyText(value) {
      const text = String(value || '');
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        return;
      }
      const area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.left = '-9999px';
      area.style.top = '0';
      document.body.appendChild(area);
      area.focus();
      area.select();
      area.setSelectionRange(0, area.value.length);
      const copied = document.execCommand('copy');
      document.body.removeChild(area);
      if (!copied) throw new Error('copy failed');
    }

    runsEl.addEventListener('click', async event => {
      const button = event.target.closest('button[data-copy]');
      if (!button) return;
      const original = button.textContent;
      try {
        await copyText(button.dataset.copy || '');
        button.textContent = 'Copied';
        setTimeout(() => { button.textContent = original; }, 1200);
      } catch {
        button.textContent = 'Copy failed';
        setTimeout(() => { button.textContent = original; }, 1600);
      }
    });

    runsEl.addEventListener('click', async event => {
      const button = event.target.closest('button[data-action]');
      if (!button) return;
      const action = button.dataset.action;
      const jobId = button.dataset.jobId;
      const label = button.textContent;
      let requestBody = null;
	      if (action === 'follow-up') {
	        const promptText = prompt(`Bounded follow-up for ${jobId}:`);
	        if (!promptText || !promptText.trim()) return;
	        requestBody = JSON.stringify({ prompt: promptText.trim() });
	      }
	      if (action === 'block') {
	        const reason = prompt(`Concrete blocked reason for ${jobId}:`);
	        if (!reason || !reason.trim()) return;
	        requestBody = JSON.stringify({ reason: reason.trim() });
	      }
		      if (action === 'replace') {
		        const sourceRun = (latestPayload.runs || []).find(run => run.job_id === jobId) || {};
		        const promptText = prompt(`Replacement job prompt for ${jobId}:`, sourceRun.replacement_prompt || sourceRun.suggested_prompt || '');
	        if (!promptText || !promptText.trim()) return;
	        const objective = prompt(`Replacement objective for ${jobId}:`, `Replacement for blocked job ${jobId}`);
	        if (!objective || !objective.trim()) return;
	        requestBody = JSON.stringify({
	          prompt: promptText.trim(),
	          objective: objective.trim(),
	          smith_alias: sourceRun.expected_alias || sourceRun.alias || 'freyja-code',
	          acceptance_criteria: [
	            'Replacement job is narrower than the blocked objective.',
	            'Evidence includes diff or explicit no-change reason.',
	            'Verification steps are reported before review.'
	          ]
	        });
	      }
      if (!confirm(`${label} ${jobId}?`)) return;
      button.disabled = true;
      button.textContent = 'Working...';
      try {
        const response = await fetch(`/agent-runs/api/jobs/${encodeURIComponent(jobId)}/${action}`, {
          method: 'POST',
          headers: requestBody ? { 'Content-Type': 'application/json' } : undefined,
          body: requestBody
        });
        const body = await response.json();
        if (!response.ok || !body.ok) throw new Error(body.detail || body.error || 'Action failed');
        button.textContent = 'Done';
        const status = await fetch('/agent-runs/api/status').then(item => item.json());
        render(status);
      } catch (error) {
        button.disabled = false;
        button.textContent = 'Failed';
        alert(error.message || String(error));
        setTimeout(() => { button.textContent = label; }, 1400);
      }
    });

    document.addEventListener('click', async event => {
      const button = event.target.closest('button[data-bulk-action]');
      if (!button) return;
      const action = button.dataset.bulkAction;
      const label = button.textContent;
      const message = action === 'stop-all'
        ? 'Stop all incomplete work and abort the OpenCode runtime?'
        : 'Requeue all incomplete work and restart it through the durable loop?';
      if (!confirm(message)) return;
      button.disabled = true;
      button.textContent = 'Working...';
      try {
        const response = await fetch(`/agent-runs/api/jobs/${action}`, { method: 'POST' });
        const body = await response.json();
        if (!response.ok || !body.ok) throw new Error(body.detail || body.error || 'Bulk action failed');
        button.textContent = 'Done';
        const status = await fetch('/agent-runs/api/status').then(item => item.json());
        render(status);
        setTimeout(() => { button.disabled = false; button.textContent = label; }, 1200);
      } catch (error) {
        button.disabled = false;
        button.textContent = 'Failed';
        alert(error.message || String(error));
        setTimeout(() => { button.textContent = label; }, 1400);
      }
    });

	    async function updateRuntimeHealth() {
	      try {
	        const health = await fetch('/agent-runs/api/runtime/health').then(item => item.json());
	        const existing = document.getElementById('runtime-health');
	        const stateText = runtimeStateText(health.state);
	        const busy = stateText === 'busy';
	        const queue = latestPayload.queue || {};
	        const orphanBusy = busy && !queue.running;
	        const level = !health.ok || orphanBusy ? 'blocked' : (busy ? 'review' : 'ok');
	        const title = !health.ok
	          ? 'OpenCode runtime unhealthy'
	          : orphanBusy
	            ? 'OpenCode runtime busy with no running job'
	            : `OpenCode runtime ${busy ? 'busy' : 'healthy'}`;
	        const detail = health.ok
	          ? `${health.base_url} answered; sessions=${health.session_count}; state=${stateText}; session=${health.session || 'unknown'}; workdir=${health.working_directory || 'unknown'}`
	          : (health.error || 'runtime check failed');
		        const needsReset = (latestPayload.diagnostics || []).some(item => item.title === 'OpenCode runtime inspection needed');
		        const stopButton = busy ? '<button type="button" data-runtime-action="stop">Stop Runtime</button>' : '';
		        const resetButton = needsReset ? '<button type="button" data-runtime-action="reset">Reset Runtime Session</button>' : '';
		        const html = `<div id="runtime-health" class="diagnostic ${level}">
		          <strong>${escapeHtml(title)}</strong>
		          <span>${escapeHtml(detail)}</span>
		          ${stopButton}${resetButton}
		        </div>`;
	        if (existing) existing.outerHTML = html;
	        else diagnosticsEl.insertAdjacentHTML('afterbegin', html);
	      } catch (error) {
        const existing = document.getElementById('runtime-health');
        const html = `<div id="runtime-health" class="diagnostic blocked"><strong>OpenCode runtime check failed</strong><span>${escapeHtml(error.message || String(error))}</span></div>`;
        if (existing) existing.outerHTML = html;
	        else diagnosticsEl.insertAdjacentHTML('afterbegin', html);
	      }
	    }

		    diagnosticsEl.addEventListener('click', async event => {
		      const button = event.target.closest('button[data-runtime-action]');
		      if (!button) return;
		      const action = button.dataset.runtimeAction;
		      const original = button.textContent;
		      const confirmText = action === 'reset'
		        ? 'Reset the tracked freyja-code OpenCode runtime session?'
		        : 'Stop the tracked freyja-code OpenCode runtime session?';
		      if (!confirm(confirmText)) return;
		      button.disabled = true;
		      button.textContent = action === 'reset' ? 'Resetting...' : 'Stopping...';
		      try {
		        const response = await fetch(`/agent-runs/api/runtime/${action}`, { method: 'POST' });
		        const body = await response.json();
		        if (!response.ok || !body.ok) throw new Error(body.detail || body.error || 'Runtime action failed');
		        button.textContent = action === 'reset' ? 'Reset' : 'Stopped';
		        await updateRuntimeHealth();
		      } catch (error) {
		        button.disabled = false;
		        button.textContent = 'Failed';
		        alert(error.message || String(error));
		        setTimeout(() => { button.textContent = original; }, 1400);
		      }
		    });

	    function runtimeStateText(state) {
	      if (!state) return 'unknown';
	      if (typeof state === 'string') return state;
	      if (typeof state.type === 'string') return state.type;
	      return JSON.stringify(state);
	    }

    const events = new EventSource('/agent-runs/events');
    events.addEventListener('status', event => render(JSON.parse(event.data)));
    events.onerror = () => { connectionEl.textContent = 'reconnecting...'; };
  </script>
</body>
</html>"""


@app.get("/freyja5/readiness")
async def freyja5_readiness() -> dict[str, Any]:
    planes = freyja5_plane_evidence()
    return {
        "ok": freyja5_readiness_ok(),
        "version": "freyja-5.0",
        "fallback_preserved": True,
        "openai_model": "freyja-5",
        "webgui": freyja5_webgui_evidence(),
        "planes": {"source": planes["source"]},
        "live_inference": freyja5_live_inference_evidence(
            enabled=settings.freyja5_openai_live_inference_enabled,
            nexus_base_url=settings.nexus_base_url,
            nexus_api_key=settings.nexus_api_key,
        ),
        "atlas": planes["atlas"],
        "blockers": freyja5_live_blocker_evidence(),
        "traceability": freyja5_traceability_evidence(),
        "semantic_routes": freyja5_semantic_route_evidence(),
        "gateway": freyja5_gateway_evidence(),
        "hera": planes["hera"],
        "iris": freyja5_iris_readiness_evidence(
            macagent_enabled=settings.macagent_enabled,
            macagent_base_url=settings.macagent_base_url,
            macagent_token=settings.macagent_token,
        ),
        "agents": freyja5_agent_evidence(),
        "mcp": freyja5_readiness_mcp_evidence(),
        "vulcan": freyja5_vulcan_evidence(),
        "certification": freyja5_readiness_certification_evidence(),
    }


@app.get("/ollama/health")
async def ollama_health() -> dict[str, bool | str]:
    healthy = await ollama.healthy()
    return {
        "ollama_reachable": healthy,
        "base_url": settings.ollama_base_url,
    }


@app.get("/local-reasoning/health")
async def local_reasoning_health() -> dict[str, bool | str]:
    healthy = await reasoning_ollama.healthy()
    model_available = await reasoning_ollama.has_model(settings.ollama_reasoning_model) if healthy else False
    return {
        "local_reasoning_reachable": healthy and model_available,
        "ollama_reachable": healthy,
        "base_url": settings.ollama_reasoning_base_url or settings.ollama_base_url,
        "model": settings.ollama_reasoning_model,
        "model_available": model_available,
    }


async def _readiness_for_profile(profile: InferenceProviderProfile) -> ProviderReadiness:
    if not profile.enabled:
        return ProviderReadiness(detail="provider disabled")
    if profile.provider_id == "openrouter_frontier":
        healthy = await openrouter.healthy()
        return ProviderReadiness(
            host_reachable=healthy,
            endpoint_healthy=healthy,
            model_available=bool(profile.model),
            detail="api key configured" if settings.openrouter_api_key else "api key not configured",
        )
    if profile.provider_id == "iris_router":
        healthy = await iris_router.healthy()
        resident = await iris_router.model_resident() if healthy else False
        return ProviderReadiness(
            host_reachable=healthy,
            endpoint_healthy=healthy,
            model_available=healthy,
            model_resident=resident,
        )
    if profile.kind == "ollama":
        client = OllamaClient(base_url=profile.base_url, model=profile.model)
        healthy = await client.healthy()
        model_available = await client.has_model(profile.model) if healthy and profile.model else healthy
        return ProviderReadiness(
            host_reachable=healthy,
            endpoint_healthy=healthy,
            model_available=model_available,
        )
    return ProviderReadiness(detail="no readiness probe configured")


@app.get("/providers/health")
async def providers_health() -> dict[str, Any]:
    registry = provider_registry_from_settings()
    providers: list[dict[str, Any]] = []
    for profile in registry.enabled():
        readiness = await _readiness_for_profile(profile)
        providers.append(
            {
                "provider_id": profile.provider_id,
                "logical_profile": profile.logical_profile,
                "kind": profile.kind,
                "base_url": profile.base_url,
                "model": profile.model,
                "capabilities": sorted(profile.capabilities),
                "locality": profile.locality.value,
                "tier": profile.tier,
                "priority": profile.priority,
                "enabled": profile.enabled,
                "readiness": readiness.model_dump(mode="json"),
                "ready": readiness.ready,
            }
        )
    return {"providers": providers}


@app.get("/iris-router/health")
async def iris_router_health() -> dict[str, Any]:
    healthy = await iris_router.healthy()
    return {
        "enabled": settings.iris_router_enabled,
        "advisory_enabled": settings.iris_router_advisory_enabled,
        "shadow_enabled": settings.iris_router_shadow_enabled,
        "confidence_threshold": settings.iris_router_confidence_threshold,
        "available": healthy,
        "reachable": healthy,
        "base_url": settings.iris_ollama_base_url,
        "model": settings.iris_router_model,
    }


@app.post("/iris-router/warm")
async def iris_router_warm() -> dict[str, Any]:
    warmed = await iris_router.warm()
    return {
        "warmed": warmed,
        "model": settings.iris_router_model,
        "keep_alive": settings.iris_router_keep_alive,
    }


@app.get("/macagent/health")
async def macagent_health() -> dict[str, Any]:
    health = await macagent.health()
    return {
        **health.model_dump(mode="json"),
        "authority": "atlas_director",
        "authorization_granted_by_macagent": False,
    }


@app.post("/local-reasoning/warm")
async def local_reasoning_warm() -> dict[str, bool | str]:
    warmed = await reasoning_ollama.warm(settings.ollama_reasoning_model)
    return {
        "warmed": warmed,
        "base_url": settings.ollama_reasoning_base_url or settings.ollama_base_url,
        "model": settings.ollama_reasoning_model,
        "keep_alive": "-1",
    }


@app.get("/ollama/models")
async def ollama_models() -> dict[str, list[str]]:
    tags = await ollama.tags()
    if "error" in tags:
        raise HTTPException(status_code=503, detail=tags["error"])

    models = [model.get("name", "") for model in tags.get("models", [])]
    return {"models": models}


class ChatRequest(BaseModel):
    prompt: str
    model: str | None = None


class ShortcutMessageRequest(BaseModel):
    prompt: str
    conversation_id: str = "homepod"
    sender: str = "shortcut"
    tools_required: bool = True
    request_id: str | None = None


@app.post("/chat")
async def chat(request: ChatRequest) -> dict[str, str]:
    response = await ollama.chat(prompt=request.prompt, model=request.model)

    if "error" in response:
        raise HTTPException(status_code=503, detail=response["error"])

    message = response.get("message", {})
    content = message.get("content", "")

    return {"model": response.get("model", ""), "response": content}


@app.get("/openrouter/health")
async def openrouter_health() -> dict[str, bool | str]:
    healthy = await openrouter.healthy()
    return {
        "openrouter_reachable": healthy,
        "base_url": settings.openrouter_base_url,
        "key_configured": bool(settings.openrouter_api_key),
    }


@app.post("/openrouter/chat")
async def openrouter_chat(request: ChatRequest) -> dict[str, str]:
    response = await openrouter.chat(prompt=request.prompt, model=request.model)

    if "error" in response:
        raise HTTPException(status_code=503, detail=response["error"])

    return {
        "model": response.get("model", ""),
        "response": response.get("response", ""),
    }


def _sanitize_tool_results(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a public, minimal view of tool results for API responses.

    Excludes raw stdout, stderr, prompts, secrets, and internal exception
    details. Includes only tool name, success status, high-level category, and
    a small amount of safe metadata.
    """
    sanitized: list[dict[str, Any]] = []
    for entry in tool_results:
        safe: dict[str, Any] = {
            "tool_name": entry.get("tool_name"),
            "success": entry.get("success"),
        }
        output = entry.get("output") or {}
        # Copy only non-sensitive scalar fields from the tool output.
        for key in ("hostname", "iso_timestamp", "status_code", "status"):
            if key in output:
                safe[key] = output[key]
        error_code = entry.get("error_code")
        if error_code:
            safe["error_category"] = error_code
        duration_ms = entry.get("duration_ms")
        if duration_ms is not None:
            safe["duration_ms"] = duration_ms
        sanitized.append(safe)
    return sanitized


def _images_from_canonical_attachments(attachments: list[CanonicalAttachment]) -> list[Any]:
    attachment_inputs: list[AttachmentInput] = []
    for attachment in attachments:
        path = None
        if attachment.source and not attachment.source.startswith(("http://", "https://")):
            path = attachment.source
        attachment_inputs.append(
            AttachmentInput(
                filename=attachment.filename,
                mime_type=attachment.media_type,
                path=path,
                data_base64=attachment.data_base64,
                size_bytes=attachment.size,
            )
        )
    return images_from_attachments(attachment_inputs)


@app.post("/route")
async def route(request: RouteRequest, raw_request: Request) -> dict:
    try:
        memory_principal = principal_from_headers(raw_request.headers)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid memory principal.") from None
    person_context = person_context_from_headers(raw_request.headers)
    result = await router.execute(request, memory_principal=memory_principal, person_context=person_context)
    if result.decision.provider == "error":
        raise HTTPException(status_code=400, detail=result.decision.reason)
    if not result.response:
        raise HTTPException(
            status_code=503,
            detail=result.decision.public_error_message or "No approved provider is currently available.",
        )
    response_payload: dict[str, Any] = {
        "provider": result.decision.provider,
        "model": result.decision.model,
        "response": result.response,
        "reason": result.decision.reason,
        "privacy_classification": result.decision.privacy_classification,
        "estimated_cost_usd": result.decision.estimated_cost_usd,
        "limitation_notice": result.decision.limitation_notice,
        "fallback_attempts": result.decision.fallback_attempts,
        "request_id": result.decision.request_id,
    }
    if request.tools_required and result.tool_results:
        response_payload["tool_results"] = _sanitize_tool_results(result.tool_results)
    if request.include_trace:
        response_payload["trace"] = result.runtime_evidence.model_dump(mode="json")
    return response_payload


async def _execute_canonical_request(request: CanonicalRequest, raw_request: Request) -> CanonicalResponse:
    if settings.freyja3_canonical_enabled:
        return await _execute_freyja3_canonical_request(request, raw_request)

    try:
        memory_principal = principal_from_headers(raw_request.headers)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid memory principal.") from None
    person_context = person_context_from_headers(raw_request.headers)
    route_request = RouteRequest(
        request_id=request.trace_id,
        prompt=request.text,
        provider=str(request.channel_metadata.get("provider") or "auto"),
        model=str(request.channel_metadata.get("model")) if request.channel_metadata.get("model") else None,
        task_type=str(request.channel_metadata.get("task_type")) if request.channel_metadata.get("task_type") else None,
        privacy=str(request.channel_metadata.get("privacy")) if request.channel_metadata.get("privacy") else None,
        tools_required=bool(request.channel_metadata.get("tools_required")),
        conversation_id=request.conversation_id,
        include_trace=True,
        images=_images_from_canonical_attachments(request.attachments),
    )
    result = await router.execute(route_request, memory_principal=memory_principal, person_context=person_context)
    if result.decision.provider == "error":
        raise HTTPException(status_code=400, detail=result.decision.reason)
    if not result.response:
        raise HTTPException(
            status_code=503,
            detail=result.decision.public_error_message or "No approved provider is currently available.",
        )
    response = CanonicalResponse(
        trace_id=request.trace_id,
        request_message_id=request.message_id,
        channel=request.channel,
        conversation_id=request.conversation_id,
        resolved_user_id=request.resolved_user_id,
        resolved_agent_id=request.resolved_agent_id,
        text=result.response,
        tool_results=_sanitize_tool_results(result.tool_results) if route_request.tools_required else [],
        status="ok",
        channel_metadata={
            "provider": result.decision.provider,
            "model": result.decision.model,
            "reason": result.decision.reason,
            "trace": result.runtime_evidence.model_dump(mode="json"),
        },
    )
    return response


async def _execute_freyja3_canonical_request(request: CanonicalRequest, raw_request: Request) -> CanonicalResponse:
    sender = GatewaySender(
        sender_id=(
            raw_request.headers.get("x-freyja-client-subject")
            or request.resolved_user_id
            or request.sender.channel_id
            or "unknown"
        ),
        display_name=raw_request.headers.get("x-freyja-person-display-name") or request.sender.display_name or request.sender.channel_id,
        security_domain_id=_security_domain_for_canonical_request(request),
        authenticated=True,
    )
    target_agent = _home_specific_agent(request.text) or request.resolved_agent_id or _default_agent_for_user(request.resolved_user_id)
    try:
        gateway_result = agent_gateway_v3.handle(
            GatewayRequest(
                sender=sender,
                target_agent=target_agent,
                prompt=request.text,
                conversation_id=request.conversation_id,
                channel=request.channel,
                message_id=request.message_id,
                attachments=[attachment.model_dump(mode="json") for attachment in request.attachments],
                reply_context=request.reply_context,
                permissions=frozenset(request.permissions),
            )
        )
    except GatewayAuthenticationError:
        raise HTTPException(status_code=403, detail="Sender is not authenticated.") from None
    except GatewayPermissionError as exc:
        raise HTTPException(status_code=403, detail=exc.audit_event.reason) from None
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    if gateway_result.handoff is None:
        raise HTTPException(status_code=500, detail="Gateway did not produce an agent handoff.")
    result = await agent_runtime_v3.arun(gateway_result.handoff)
    return CanonicalResponse(
        trace_id=request.trace_id,
        request_message_id=request.message_id,
        channel=request.channel,
        conversation_id=result.conversation_id,
        resolved_user_id=request.resolved_user_id,
        resolved_agent_id=result.agent_id,
        text=result.response_text,
        tool_results=(
            list(result.tool_results)
            if result.tool_results
            else []
            if result.follow_up_questions
            else [{"tool_name": tool_id, "success": True} for tool_id in result.selected_tools]
        ),
        channel_metadata={
            "freyja3": True,
            "gateway_audit": gateway_result.audit_event.model_dump(mode="json"),
            "agent_steps": [step.model_dump(mode="json") for step in result.steps],
            "inference_endpoint_id": result.inference_endpoint_id,
            "inference_model": result.inference_model,
            "inference_machine_id": result.inference_machine_id,
            "inference_status": result.inference_status,
            "follow_up_questions": list(result.follow_up_questions),
            "recalled_memories": list(result.recalled_memories),
            "written_memories": list(result.written_memories),
        },
        degraded=result.degraded,
        status="degraded" if result.degraded else "ok",
    )


def _security_domain_for_canonical_request(request: CanonicalRequest) -> SecurityDomainId:
    person = (request.resolved_user_id or "").strip().lower()
    if person == "joe":
        return SecurityDomainId.PERSON_JOE
    if person == "beth":
        return SecurityDomainId.PERSON_BETH
    if person == "liam":
        return SecurityDomainId.PERSON_LIAM
    if person == "jenna":
        return SecurityDomainId.PERSON_JENNA
    return SecurityDomainId.HOUSEHOLD


def _default_agent_for_user(resolved_user_id: str | None) -> str:
    person = (resolved_user_id or "").strip().lower()
    return {
        "joe": "cloyd-gibbler",
        "beth": "benedict",
        "liam": "agent-47",
        "jenna": "jennacide",
    }.get(person, "freyja")


def _home_specific_agent(text: str) -> str | None:
    lowered = text.lower()
    home_context_terms = (
        "home assistant",
        "my home",
        "at home",
        "in my home",
        "the house",
        "basement",
        "house state",
        "home state",
    )
    if home_assistant_focus_for_text(lowered) and any(term in lowered for term in home_context_terms):
        return "freyja"
    home_terms = (
        "home assistant",
        "my home",
        "at home",
        "in my home",
        "the house",
        "house state",
        "home state",
        "lights",
        "sensors",
        "devices",
        "thermostat",
        "temperature",
        "humidity",
        "power",
        "energy",
        "battery",
        "voltage",
        "electric",
        "electricity",
        "outlet",
        "garage",
        "door",
        "lock",
    )
    if any(term in lowered for term in home_terms):
        return "freyja"
    return None


@app.post("/canonical/route")
async def canonical_route(request: CanonicalRequest, raw_request: Request) -> dict[str, Any]:
    response = await _execute_canonical_request(request, raw_request)
    return response.model_dump(mode="json")


def _family_route_config(member: str) -> FamilyRouteConfig:
    config = family_route_config(member)
    if config is None:
        raise HTTPException(status_code=404, detail="Unknown family member route.")
    return config


def _family_tool_policy(config: FamilyRouteConfig, requested_mode: str | None) -> str:
    try:
        return family_tool_policy(config, requested_mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.post("/family/{member}")
async def family_route(member: str, request: FamilyRouteMessage) -> dict[str, Any]:
    config = _family_route_config(member)
    prompt = request.message.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Family route message is required.")
    conversation_id = request.conversation_id or f"family:{member.strip().lower()}:{uuid.uuid4()}"
    message_id = request.message_id or f"family-msg:{uuid.uuid4()}"
    tool_policy = _family_tool_policy(config, request.policy_mode)
    try:
        target_agent = resolve_family_agent_alias(config, request.agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    sender = GatewaySender(
        sender_id=config.actor_principal,
        display_name=config.display_name,
        security_domain_id=config.security_domain_id,
        authenticated=True,
    )
    try:
        gateway_result = agent_gateway_v3.handle(
            GatewayRequest(
                sender=sender,
                target_agent=target_agent,
                prompt=prompt,
                conversation_id=conversation_id,
                channel=request.channel,
                message_id=message_id,
                attachments=request.attachments,
                actor_principal=config.actor_principal,
                authenticated_subject=config.actor_principal,
                document_scope=config.document_scope,
                tool_policy=tool_policy,
                privacy_policy=config.privacy_policy,
                parent_visibility=config.parent_visibility,
                audit_reason=f"authenticated family route for {config.member}",
                permissions=frozenset({"family:route"}),
            )
        )
    except GatewayAuthenticationError:
        raise HTTPException(status_code=403, detail="Sender is not authenticated.") from None
    except GatewayPermissionError as exc:
        raise HTTPException(status_code=403, detail=exc.audit_event.reason) from None
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    if gateway_result.handoff is None:
        raise HTTPException(status_code=500, detail="Gateway did not produce an agent handoff.")
    result = await agent_runtime_v3.arun(gateway_result.handoff)
    handoff = gateway_result.handoff
    return {
        "trace_id": result.trace_id,
        "conversation_id": result.conversation_id,
        "resolved_user_id": member.strip().lower(),
        "resolved_agent_id": result.agent_id,
        "text": result.response_text,
        "status": "degraded" if result.degraded else "ok",
        "family_route": {
            "actor_principal": handoff.actor_principal,
            "authenticated_subject": handoff.authenticated_subject,
            "target_agent": handoff.target_agent_id,
            "source_channel": handoff.channel,
            "conversation_id": handoff.conversation_id,
            "memory_scopes": sorted(handoff.memory_scopes),
            "memory_scope": config.document_scope.rsplit("/", 1)[0],
            "document_scope": handoff.document_scope,
            "tool_policy": handoff.tool_policy,
            "privacy_policy": handoff.privacy_policy,
            "cloud_policy": handoff.cloud_egress_policy_id,
            "parent_visibility": handoff.parent_visibility,
            "request_id": handoff.handoff_id,
            "message_id": handoff.message_id,
            "attachments": handoff.attachments,
            "audit_reason": handoff.audit_reason,
        },
        "channel_metadata": {
            "gateway_audit": gateway_result.audit_event.model_dump(mode="json"),
            "inference_endpoint_id": result.inference_endpoint_id,
            "inference_status": result.inference_status,
        },
    }


@app.post("/shortcuts/message")
async def shortcut_message(request: ShortcutMessageRequest, raw_request: Request) -> dict[str, Any]:
    """Protected voice/Shortcut ingress through the canonical Director path."""
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Shortcut prompt is required.")

    conversation_id = f"shortcut-conv:{request.conversation_id.strip() or 'homepod'}"
    trace_id = request.request_id or f"shortcut-{uuid.uuid4()}"
    canonical_request = CanonicalRequest(
        trace_id=trace_id,
        message_id=trace_id,
        channel="voice",
        conversation_id=conversation_id,
        sender={
            "channel_id": request.sender.strip() or "shortcut",
            "display_name": "Shortcut",
            "metadata": {"source": "shortcuts"},
        },
        text=prompt,
        channel_metadata={
            "provider": "auto",
            "tools_required": request.tools_required,
            "privacy": "private",
            "task_type": "voice",
            "source": "shortcuts",
        },
        permissions=["director:route"],
    )
    canonical_response = await _execute_canonical_request(canonical_request, raw_request)
    response = _voice_friendly_response(canonical_response.text)
    return {
        "response": response,
        "spoken": response,
        "conversation_id": canonical_response.conversation_id,
        "request_id": canonical_response.trace_id,
        "provider": canonical_response.channel_metadata.get("provider"),
        "model": canonical_response.channel_metadata.get("model"),
    }


def _voice_friendly_response(text: str, *, limit: int = 700) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _openai_chat_objective(messages: list["OpenAIChatMessage"]) -> str:
    parts: list[str] = []
    for message in messages:
        role = message.role.strip().lower()
        if role not in {"system", "user"}:
            continue
        content = _openai_message_content_text(message.content)
        if content:
            parts.append(f"{role}: {content}")
    if not parts:
        return ""
    return "\n".join(parts)[-8000:]


def _openai_temporal_context() -> dict[str, str]:
    now = datetime.now(ZoneInfo(FREYJA_OPENWEBUI_TIMEZONE))
    return {
        "local_date": now.date().isoformat(),
        "local_time": now.strftime("%H:%M:%S"),
        "local_datetime": now.isoformat(),
        "timezone": FREYJA_OPENWEBUI_TIMEZONE,
    }


def _openai_permissions_for_freyja5(objective: str) -> frozenset[str]:
    lowered = objective.lower()
    if "approve" in lowered and ("calendar" in lowered or "adding it" in lowered):
        return frozenset({"approval:calendar.write"})
    return frozenset()


def _openai_message_content_text(content: str | list[dict[str, Any]] | None) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and isinstance(item.get("text"), str):
            chunks.append(item["text"].strip())
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def _openai_chat_attachments(messages: list["OpenAIChatMessage"]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for message in messages:
        if message.role != "user" or not isinstance(message.content, list):
            continue
        for index, item in enumerate(message.content, start=1):
            if not isinstance(item, dict):
                continue
            attachment = _openai_content_part_attachment(item, index=index)
            if attachment is not None:
                attachments.append(attachment)
    return attachments


def _openai_content_part_attachment(item: dict[str, Any], *, index: int) -> dict[str, Any] | None:
    part_type = item.get("type")
    if part_type in {"image_url", "input_image"}:
        image_url = item.get("image_url")
        url = image_url.get("url") if isinstance(image_url, dict) else item.get("image_url") or item.get("url")
        parsed = _parse_data_url(str(url or ""))
        if parsed is None or not parsed[0].startswith("image/"):
            return None
        mime_type, data_base64 = parsed
        return {
            "filename": str(item.get("filename") or f"openai-image-{index}{_extension_for_mime_type(mime_type)}"),
            "mime_type": mime_type,
            "data_base64": data_base64,
        }
    if part_type in {"file", "input_file"}:
        file_data = item.get("file")
        if isinstance(file_data, dict):
            filename = str(file_data.get("filename") or item.get("filename") or f"openai-file-{index}")
            payload = str(file_data.get("file_data") or file_data.get("data") or item.get("file_data") or "")
        else:
            filename = str(item.get("filename") or f"openai-file-{index}")
            payload = str(item.get("file_data") or item.get("data") or "")
        parsed = _parse_data_url(payload)
        if parsed is None:
            return None
        mime_type, data_base64 = parsed
        return {"filename": filename, "mime_type": mime_type, "data_base64": data_base64}
    return None


def _parse_data_url(value: str) -> tuple[str, str] | None:
    header, separator, data = value.partition(",")
    if not separator or not header.startswith("data:") or ";base64" not in header:
        return None
    mime_type = header.removeprefix("data:").split(";", 1)[0] or "application/octet-stream"
    return mime_type, data.strip()


def _extension_for_mime_type(mime_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }.get(mime_type.lower(), "")


def _openai_chat_should_use_smith(objective: str) -> bool:
    lowered = objective.lower()
    smith_keywords = (
        "check",
        "compile",
        "debug",
        "diagnose",
        "diff",
        "health",
        "inspect",
        "pytest",
        "repo",
        "repository",
        "status",
        "validate",
    )
    smith_phrases = ("run test", "run the test", "test suite", "pytest")
    return any(keyword in lowered for keyword in smith_keywords) or any(phrase in lowered for phrase in smith_phrases)


def _openai_sender_for_freyja5(request: "OpenAIChatCompletionRequest") -> GatewaySender:
    user = (request.user or "").strip().lower()
    person_domain = {
        "joe": SecurityDomainId.PERSON_JOE,
        "beth": SecurityDomainId.PERSON_BETH,
        "liam": SecurityDomainId.PERSON_LIAM,
        "jenna": SecurityDomainId.PERSON_JENNA,
        "paralegal": SecurityDomainId.PARALEGAL,
    }.get(user)
    if person_domain is not None:
        return GatewaySender(
            sender_id=f"person:{user}",
            display_name=request.user or user,
            security_domain_id=person_domain,
        )
    return GatewaySender(
        sender_id=f"open-webui:{request.user or 'gui'}",
        display_name=request.user or "Open WebUI",
        security_domain_id=SecurityDomainId.HOUSEHOLD,
    )


def _freyja5_openai_response_text(result) -> str:
    trace = result.trace_summary
    route = trace.get("requested_route") or result.requested_route
    provider = trace.get("actual_provider") or result.inference_provider or "unavailable"
    model = trace.get("actual_model") or "unavailable"
    status = trace.get("inference_status") or ("degraded" if result.degraded else "completed")
    response_text = str(getattr(result, "response_text", "") or "").strip()
    if not response_text:
        response_text = "Freyja 5.0 response is unavailable."
    return "\n".join(
        (
            response_text,
            "",
            f"Trace: {trace.get('trace_id')}",
            f"Agent: {trace.get('agent_logical_display_name') or trace.get('agent_display_name') or result.agent_id}",
            f"Route: {route}",
            f"Runtime: {provider} {model}",
            f"Status: {status}",
            f"Egress: {result.egress_state}",
        )
    )


def _smith_openai_response_text(summary: dict[str, Any]) -> str:
    lines = [
        f"Agent Smith request: {summary.get('request_id')}",
        f"Status: {summary.get('status')}",
        str(summary.get("message") or "").strip(),
    ]
    plan = summary.get("plan") if isinstance(summary.get("plan"), dict) else None
    tasks = plan.get("tasks") if isinstance(plan, dict) and isinstance(plan.get("tasks"), list) else []
    if tasks:
        lines.append("")
        lines.append("Steps:")
        for index, task in enumerate(tasks[:20], start=1):
            description = str(task.get("description") or "task").strip()
            status = str(task.get("status") or "unknown").strip()
            metadata = task.get("metadata") if isinstance(task.get("metadata"), dict) else {}
            tool = metadata.get("tool")
            suffix = f" [{tool}]" if tool else ""
            lines.append(f"{index}. {status}: {description}{suffix}")
    if summary.get("approval_required_count"):
        lines.append("")
        lines.append("Approval required before any write or privileged action.")
    if summary.get("duration_ms") is not None:
        lines.append("")
        lines.append(f"Duration: {summary['duration_ms']} ms")
    return "\n".join(line for line in lines if line is not None).strip()


def _openai_chat_response(
    *,
    request_id: str,
    content: str,
    duration_ms: int,
    smith_mode: str,
    smith_status: str,
    model: str = "agent-smith",
    extra_freyja: dict[str, Any] | None = None,
) -> dict[str, Any]:
    freyja_metadata = {
        "request_id": request_id,
        "status": smith_status,
        "duration_ms": duration_ms,
        "smith_mode": smith_mode,
    }
    if extra_freyja:
        freyja_metadata.update(extra_freyja)
    return {
        "id": f"chatcmpl-{request_id}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "freyja": freyja_metadata,
    }


def _openai_chat_stream(response: dict[str, Any]) -> StreamingResponse:
    created = int(response.get("created") or time.time())
    response_id = str(response.get("id") or f"chatcmpl-{uuid.uuid4()}")
    model = str(response.get("model") or "agent-smith")
    content = str(response["choices"][0]["message"].get("content") or "")

    async def events():
        first_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        }
        content_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
        }
        final_chunk = {
            "id": response_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        }
        for chunk in (first_chunk, content_chunk, final_chunk):
            yield f"data: {json.dumps(jsonable_encoder(chunk), separators=(',', ':'))}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


class SmithDryRunRequest(BaseModel):
    objective: str
    actor: str = "agent_smith"
    request_id: str | None = None


class SmithReadOnlyRequest(BaseModel):
    objective: str
    actor: str = "agent_smith"
    request_id: str | None = None


class OpenAIChatMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: str
    content: str | list[dict[str, Any]] | None = None


class OpenAIChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str
    messages: list[OpenAIChatMessage]
    stream: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    stop: str | list[str] | None = None
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    user: str | None = None


class FamilyIssueReviewRequest(BaseModel):
    objective: str = "diagnose Director health, repository status, routing configuration, and test readiness"
    owners: list[str] | None = None
    actor_prefix: str = "family_issue_review"
    request_id: str | None = None


class SmithWritePilotRequest(BaseModel):
    objective: str
    target_path: str
    proposed_content: str
    commit_message: str
    actor: str = "agent_smith"
    request_id: str | None = None


@app.post("/agents/smith/dry-run")
async def smith_dry_run(request: SmithDryRunRequest) -> dict[str, Any]:
    if not settings.agent_smith_enabled or not settings.agent_smith_dry_run_enabled:
        raise HTTPException(
            status_code=404 if not settings.agent_smith_enabled else 403,
            detail="Agent Smith dry-run mode is not enabled.",
        )
    runtime = SmithRuntime()
    summary = await runtime.run_dry(request.objective, actor=request.actor, request_id=request.request_id)
    return summary.model_dump(mode="json")


@app.post("/agents/smith/read-only")
async def smith_read_only(request: SmithReadOnlyRequest) -> dict[str, Any]:
    if not settings.agent_smith_enabled or not settings.agent_smith_read_only_enabled:
        raise HTTPException(
            status_code=404 if not settings.agent_smith_enabled else 403,
            detail="Agent Smith read-only mode is not enabled.",
        )
    runtime = SmithRuntime()
    summary = await runtime.run_read_only(
        request.objective,
        actor=request.actor,
        request_id=request.request_id,
    )
    return summary.model_dump(mode="json")


@app.get("/v1/models")
async def openai_compatible_models() -> dict[str, Any]:
    agent_models = [
        {
            "id": model["model_id"],
            "object": "model",
            "created": 0,
            "owned_by": "freyja-os",
            "name": model["display_name"],
            "freyja": model,
        }
        for model in freyja5_open_webui_agent_model_evidence()
    ]
    return {
        "object": "list",
        "data": [
            {
                "id": "agent-smith",
                "object": "model",
                "created": 0,
                "owned_by": "freyja-os",
            },
            {
                "id": "freyja-5",
                "object": "model",
                "created": 0,
                "owned_by": "freyja-os",
            },
            *agent_models,
        ],
    }


@app.get("/agents/{agent_gateway}/v1/models")
async def agent_openai_compatible_models(agent_gateway: str) -> dict[str, Any]:
    model_id = FREYJA5_AGENT_GATEWAY_MODELS.get(agent_gateway)
    if model_id is None:
        raise HTTPException(status_code=404, detail="Unknown Freyja 5 agent gateway.")
    models = (await openai_compatible_models())["data"]
    model = next((item for item in models if item.get("id") == model_id), None)
    if model is None:
        raise HTTPException(status_code=404, detail="Unknown Freyja 5 agent model.")
    return {"object": "list", "data": [model]}


@app.post("/v1/chat/completions", response_model=None)
async def openai_compatible_chat_completions(request: OpenAIChatCompletionRequest) -> dict[str, Any] | StreamingResponse:
    if request.model not in {"agent-smith", *FREYJA5_OPENAI_MODEL_IDS}:
        raise HTTPException(status_code=404, detail="Unknown model.")
    if request.model == "agent-smith" and (not settings.agent_smith_enabled or not settings.agent_smith_read_only_enabled):
        raise HTTPException(
            status_code=404 if not settings.agent_smith_enabled else 403,
            detail="Agent Smith read-only mode is not enabled.",
        )

    objective = _openai_chat_objective(request.messages)
    if not objective:
        raise HTTPException(status_code=400, detail="At least one user message is required.")
    if request.model in FREYJA5_OPENAI_MODEL_IDS:
        agent_model = next(
            (
                model
                for model in freyja5_open_webui_agent_model_evidence()
                if model["model_id"] == request.model
            ),
            None,
        )
        if request.model == FREYJA5_LEGACY_OPENAI_MODEL_ID:
            target_agent = "freyja"
        elif agent_model is not None:
            target_agent = str(agent_model["agent_id"])
        else:
            raise HTTPException(status_code=404, detail="Unknown Freyja 5 agent model.")
        request_id = f"freyja5-openai-{uuid.uuid4()}"
        start = time.monotonic()
        attachments = _openai_chat_attachments(request.messages)
        try:
            gateway_result = AgentGateway().handle(
                GatewayRequest(
                    sender=_openai_sender_for_freyja5(request),
                    target_agent=target_agent,
                    prompt=objective,
                    conversation_id=request_id,
                    channel="open-webui",
                    attachments=attachments,
                    permissions=_openai_permissions_for_freyja5(objective),
                    reply_context={
                        "client": "openai-compatible",
                        "model": request.model,
                        "originating_channel": "open-webui",
                        "temporal_context": _openai_temporal_context(),
                    },
                )
            )
        except GatewayPermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if gateway_result.handoff is None:
            raise HTTPException(status_code=403, detail="Freyja 5 Gateway rejected request.")
        result = await AgentRuntimeV3(
            tool_registry=get_registry(),
            memory_store=freyja3_memory_store,
            run_inference=settings.freyja5_openai_live_inference_enabled,
            allow_cloud_fallback=False,
        ).arun(gateway_result.handoff)
        duration_ms = int((time.monotonic() - start) * 1000)
        response_body = _openai_chat_response(
            request_id=request_id,
            content=_freyja5_openai_response_text(result),
            duration_ms=duration_ms,
            smith_mode="freyja5",
            smith_status="degraded" if result.degraded else "completed",
            model=request.model,
            extra_freyja={
                "trace_id": result.trace_id,
                "agent": result.agent_id,
                "agent_model": request.model,
                "route": result.requested_route,
                "endpoint": result.inference_endpoint_id,
                "provider": result.inference_provider,
                "egress_state": result.egress_state,
                "attachment_count": len(attachments),
                "trace": result.trace_summary,
                **({"agent_model_metadata": agent_model} if agent_model else {}),
            },
        )
        if request.stream:
            return _openai_chat_stream(response_body)
        return response_body

    request_id = f"smith-openai-{uuid.uuid4()}"
    start = time.monotonic()
    smith_mode = "chat"
    smith_status = "completed"
    if _openai_chat_should_use_smith(objective):
        runtime = SmithRuntime()
        summary = await runtime.run_read_only(
            objective,
            actor=f"agent_smith:openai-compatible:{request.user or 'gui'}",
            request_id=request_id,
        )
        content = _smith_openai_response_text(summary.model_dump(mode="json"))
        smith_mode = "read_only"
        smith_status = summary.status
    else:
        client = OllamaClient(
            base_url=settings.ollama_base_url,
            model=settings.ollama_chat_model or settings.ollama_model,
        )
        response = await client.chat(
            prompt=objective,
            stream=False,
            tools_required=False,
            output_tokens=request.max_tokens,
        )
        if "error" in response:
            raise HTTPException(status_code=502, detail=f"Ollama chat failed: {response['error']}")
        content = str(response.get("message", {}).get("content") or "").strip()
        if not content:
            raise HTTPException(status_code=502, detail="Ollama chat returned empty content.")
    duration_ms = int((time.monotonic() - start) * 1000)
    response_body = _openai_chat_response(
        request_id=request_id,
        content=content,
        duration_ms=duration_ms,
        smith_mode=smith_mode,
        smith_status=smith_status,
    )
    if request.stream:
        return _openai_chat_stream(response_body)
    return response_body


@app.post("/agents/{agent_gateway}/v1/chat/completions", response_model=None)
async def agent_openai_compatible_chat_completions(
    agent_gateway: str,
    request: OpenAIChatCompletionRequest,
) -> dict[str, Any] | StreamingResponse:
    model_id = FREYJA5_AGENT_GATEWAY_MODELS.get(agent_gateway)
    if model_id is None:
        raise HTTPException(status_code=404, detail="Unknown Freyja 5 agent gateway.")
    scoped_request = request.model_copy(update={"model": model_id})
    return await openai_compatible_chat_completions(scoped_request)


@app.post("/agents/family/issue-review")
async def family_issue_review(request: FamilyIssueReviewRequest) -> dict[str, Any]:
    if not settings.agent_smith_enabled or not settings.agent_smith_read_only_enabled:
        raise HTTPException(
            status_code=404 if not settings.agent_smith_enabled else 403,
            detail="Agent Smith read-only mode is not enabled.",
        )

    hierarchy = AgentHierarchy()
    try:
        owners = tuple(PersonName(owner) for owner in request.owners) if request.owners else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown family issue-review owner.") from exc

    maintenance_requests = hierarchy.family_issue_review_requests(
        objective=request.objective,
        owners=owners,
    )
    reviews: list[dict[str, Any]] = []
    for index, maintenance_request in enumerate(maintenance_requests, start=1):
        runtime = SmithRuntime()
        request_id = (
            f"{request.request_id}:{maintenance_request.owner.value}"
            if request.request_id
            else maintenance_request.request_id
        )
        summary = await runtime.run_read_only(
            maintenance_request.objective,
            actor=f"{request.actor_prefix}:{maintenance_request.requested_by.value}",
            request_id=request_id,
        )
        reviews.append(
            {
                "index": index,
                "owner": maintenance_request.owner.value,
                "agent": maintenance_request.requested_by.value,
                "authority": maintenance_request.authority.value,
                "escalation_target": maintenance_request.escalation_target.value,
                "memory_principal": maintenance_request.memory_principal.model_dump(mode="json"),
                "summary": summary.model_dump(mode="json"),
            }
        )

    return {
        "objective": request.objective,
        "review_count": len(reviews),
        "reviews": reviews,
    }


@app.post("/agents/smith/write-pilot")
async def smith_write_pilot(request: SmithWritePilotRequest) -> dict[str, Any]:
    if not settings.agent_smith_enabled or not settings.agent_smith_write_pilot_enabled:
        raise HTTPException(
            status_code=404 if not settings.agent_smith_enabled else 403,
            detail="Agent Smith write-pilot mode is not enabled.",
        )
    runtime = SmithRuntime()
    provider = PersistentApprovalProvider()
    result = await runtime.run_write_pilot_with_provider(
        objective=request.objective,
        target_path=request.target_path,
        proposed_content=request.proposed_content,
        commit_message=request.commit_message,
        actor=request.actor,
        request_id=request.request_id or runtime._new_request_id(),
        provider=provider,
    )
    return result.model_dump(mode="json")


class SmithApprovalListResponse(BaseModel):
    approvals: list[dict[str, Any]]


class SmithApprovalResolveRequest(BaseModel):
    actor: str = "operator"
    reason: str | None = None


class SmithWritePilotResumeRequest(BaseModel):
    request_id: str
    approval_id: str
    objective: str
    target_path: str
    proposed_content: str
    commit_message: str
    actor: str = "agent_smith"
    rollback_on_unapproved: bool = True


def _require_loopback(request: Request) -> None:
    if not settings.agent_smith_approval_loopback_only:
        return
    _require_loopback_host(
        request.client.host if request.client else None,
        missing_detail="Approval admin endpoint requires a client address.",
        invalid_detail="Approval admin endpoint received an invalid client address.",
        denied_detail="Approval admin endpoint is only available from loopback.",
    )
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        _require_loopback_host(
            forwarded_for.split(",", 1)[0].strip(),
            missing_detail="Approval admin endpoint received an invalid forwarded client address.",
            invalid_detail="Approval admin endpoint received an invalid forwarded client address.",
            denied_detail="Approval admin endpoint is only available from loopback.",
        )
    forwarded = request.headers.get("forwarded")
    if forwarded:
        for part in forwarded.split(";"):
            key, separator, value = part.strip().partition("=")
            if separator and key.lower() == "for":
                _require_loopback_host(
                    value.strip('"[]'),
                    missing_detail="Approval admin endpoint received an invalid forwarded client address.",
                    invalid_detail="Approval admin endpoint received an invalid forwarded client address.",
                    denied_detail="Approval admin endpoint is only available from loopback.",
                )
                break


def _require_loopback_host(
    host: str | None,
    *,
    missing_detail: str,
    invalid_detail: str,
    denied_detail: str,
) -> None:
    if not host:
        raise HTTPException(
            status_code=403,
            detail=missing_detail,
        )
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise HTTPException(
            status_code=403,
            detail=invalid_detail,
        ) from exc
    if not address.is_loopback:
        raise HTTPException(
            status_code=403,
            detail=denied_detail,
        )


@app.get("/agents/smith/approvals")
async def smith_list_approvals(request: Request) -> SmithApprovalListResponse:
    _require_loopback(request)
    if not settings.agent_smith_enabled:
        raise HTTPException(status_code=404, detail="Agent Smith is not enabled.")
    if not settings.agent_smith_write_pilot_enabled:
        raise HTTPException(status_code=403, detail="Agent Smith write-pilot mode is not enabled.")
    provider = PersistentApprovalProvider()
    pending = provider.store.list_pending()
    return SmithApprovalListResponse(approvals=[a.model_dump(mode="json") for a in pending])


@app.get("/agents/smith/approvals/{approval_id}")
async def smith_get_approval(approval_id: str, request: Request) -> dict[str, Any]:
    _require_loopback(request)
    if not settings.agent_smith_enabled:
        raise HTTPException(status_code=404, detail="Agent Smith is not enabled.")
    if not settings.agent_smith_write_pilot_enabled:
        raise HTTPException(status_code=403, detail="Agent Smith write-pilot mode is not enabled.")
    provider = PersistentApprovalProvider()
    record = provider.store.get(approval_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Approval not found.")
    return record.model_dump(mode="json")


@app.post("/agents/smith/approvals/{approval_id}/approve")
async def smith_approve_approval(
    approval_id: str,
    body: SmithApprovalResolveRequest,
    request: Request,
) -> dict[str, Any]:
    _require_loopback(request)
    if not settings.agent_smith_enabled:
        raise HTTPException(status_code=404, detail="Agent Smith is not enabled.")
    if not settings.agent_smith_write_pilot_enabled:
        raise HTTPException(status_code=403, detail="Agent Smith write-pilot mode is not enabled.")
    provider = PersistentApprovalProvider()
    try:
        record = provider.store.approve(approval_id, actor=body.actor)
    except Exception as exc:
        status = getattr(exc, "status_code", 409)
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return record.model_dump(mode="json")


@app.post("/agents/smith/approvals/{approval_id}/deny")
async def smith_deny_approval(
    approval_id: str,
    body: SmithApprovalResolveRequest,
    request: Request,
) -> dict[str, Any]:
    _require_loopback(request)
    if not settings.agent_smith_enabled:
        raise HTTPException(status_code=404, detail="Agent Smith is not enabled.")
    if not settings.agent_smith_write_pilot_enabled:
        raise HTTPException(status_code=403, detail="Agent Smith write-pilot mode is not enabled.")
    provider = PersistentApprovalProvider()
    try:
        record = provider.store.deny(approval_id, actor=body.actor, reason=body.reason)
    except Exception as exc:
        status = getattr(exc, "status_code", 409)
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return record.model_dump(mode="json")


def _hash_for_validation(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_resume_payload(body: SmithWritePilotResumeRequest) -> None:
    """Compare the resume payload against the persisted approval context.

    Rejects mismatches before any runtime or filesystem action.  Does not
    expose persisted hashes, file contents, or absolute paths in errors.
    """
    provider = PersistentApprovalProvider()
    record = provider.store.get(body.approval_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Approval not found.")

    mismatch: str | None = None
    if record.request_id != body.request_id:
        mismatch = "request_id"
    elif record.target_path != body.target_path:
        mismatch = "target_path"
    elif body.proposed_content is not None and record.content_hash is not None and record.content_hash != _hash_for_validation(body.proposed_content):
        mismatch = "proposed_content"
    elif body.commit_message is not None and record.commit_message_hash is not None and record.commit_message_hash != _hash_for_validation(body.commit_message):
        mismatch = "commit_message"

    if mismatch:
        raise HTTPException(
            status_code=409,
            detail=f"Resume payload mismatch: {mismatch} does not match the persisted approval context.",
        )


@app.post("/agents/smith/write-pilot/resume")
async def smith_write_pilot_resume(
    request: Request,
    body: SmithWritePilotResumeRequest,
) -> dict[str, Any]:
    _require_loopback(request)
    if not settings.agent_smith_enabled:
        raise HTTPException(status_code=404, detail="Agent Smith is not enabled.")
    if not settings.agent_smith_write_pilot_enabled:
        raise HTTPException(status_code=403, detail="Agent Smith write-pilot mode is not enabled.")
    _validate_resume_payload(body)
    runtime = SmithRuntime()
    provider = PersistentApprovalProvider()
    result = await runtime.resume_write_pilot(
        request_id=body.request_id,
        approval_id=body.approval_id,
        objective=body.objective,
        target_path=body.target_path,
        proposed_content=body.proposed_content,
        commit_message=body.commit_message,
        actor=body.actor,
        provider=provider,
        rollback_on_unapproved=body.rollback_on_unapproved,
    )
    return result.model_dump(mode="json")
