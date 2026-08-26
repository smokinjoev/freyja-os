from __future__ import annotations

import hmac
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from freyja.agent_gateway import AgentGateway, GatewayAuthenticationError, GatewayPermissionError, GatewayRequest
from freyja.agent_runtime_v3 import AgentRuntimeV3
from freyja.config import settings
from freyja.contracts import CanonicalRequest, CanonicalResponse, CanonicalSender
from freyja.foundation_models import GatewaySender, SecurityDomainId, SemanticEvent
from freyja.freyja3_machines import Freyja3MachineAccessError, Freyja3MachineHeartbeat, Freyja3MachineStatusStore
from freyja.freyja3_memory import Freyja3MemoryAccessError, Freyja3MemoryQuery, Freyja3MemoryStore, Freyja3MemoryWrite
from freyja.freyja3_scheduler import Freyja3ScheduleAccessError, Freyja3ScheduleCreate, Freyja3ScheduleQuery, Freyja3SchedulerStore
from freyja.inference_registry_v3 import InferenceRegistryV3
from freyja.ollama_client import OllamaClient
from freyja.semantic_events import SemanticEventPermissionError, SemanticEventQuery, SemanticEventStore
from freyja.tools.builtin import register_builtin_tools, register_smith_read_only_tools, register_smith_write_pilot_tools
from freyja.tools.registry import get_registry


app = FastAPI(
    title="Freyja 3 Agent Gateway",
    version="0.3.0",
    description="Deterministic Freyja 3 gateway, agent runtime, inference lookup, and semantic events.",
)

agent_gateway = AgentGateway()
semantic_event_store = SemanticEventStore()
memory_store = Freyja3MemoryStore()
scheduler_store = Freyja3SchedulerStore()
machine_status_store = Freyja3MachineStatusStore()
register_builtin_tools(get_registry())
register_smith_write_pilot_tools(get_registry())
register_smith_read_only_tools(get_registry())
agent_runtime = AgentRuntimeV3(
    tool_registry=get_registry(),
    memory_store=memory_store,
    run_inference=settings.freyja3_inference_enabled,
)
inference_registry = InferenceRegistryV3()


@app.middleware("http")
async def require_connector_auth(request: Request, call_next):
    expected = settings.freyja_connector_token
    if not expected or request.url.path in {"/", "/health"}:
        return await call_next(request)
    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() == "bearer" and bool(supplied) and hmac.compare_digest(supplied, expected):
        return await call_next(request)
    return JSONResponse(
        status_code=401,
        content={"detail": "Connector authentication required."},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "freyja3-agent-gateway", "status": "online", "version": "0.3.0"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/freyja3/inference/health")
async def freyja3_inference_health() -> dict[str, Any]:
    checks = []
    for endpoint in inference_registry.all_endpoints(domain_id=SecurityDomainId.HOUSEHOLD):
        reachable, models = await _inference_endpoint_health(endpoint.provider, endpoint.base_url, endpoint.model)
        checks.append(
            {
                "endpoint_id": endpoint.endpoint_id,
                "provider": endpoint.provider,
                "machine_id": endpoint.machine_id,
                "base_url": endpoint.base_url,
                "model": endpoint.model,
                "reachable": reachable,
                "model_available": endpoint.model in models or any(name.startswith(f"{endpoint.model}:") for name in models),
            }
        )
    return {"ok": any(check["reachable"] and check["model_available"] for check in checks), "endpoints": checks}


async def _inference_endpoint_health(provider: str, base_url: str, model: str) -> tuple[bool, list[str]]:
    if not base_url:
        return False, []
    if provider == "ollama":
        client = OllamaClient(base_url=base_url, model=model)
        reachable = await client.healthy()
        return reachable, await client.list_local_models() if reachable else []
    if provider in {"lmstudio", "openai-compatible"}:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url.rstrip('/')}/v1/models")
                response.raise_for_status()
                data = response.json()
        except Exception:
            return False, []
        models = data.get("data") if isinstance(data, dict) else []
        names = [str(item.get("id")) for item in models if isinstance(item, dict) and item.get("id")]
        return True, names
    return False, []


@app.post("/freyja3/memory")
async def put_freyja3_memory(write: Freyja3MemoryWrite, raw_request: Request) -> dict[str, Any]:
    domain_id = _domain_from_header(raw_request.headers.get("x-freyja-security-domain"))
    try:
        record = memory_store.put(write, writer_domain_id=domain_id)
    except Freyja3MemoryAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return {"ok": True, "memory": record.model_dump(mode="json")}


@app.get("/freyja3/memory")
async def list_freyja3_memory(
    raw_request: Request,
    owner_domain_id: SecurityDomainId | None = None,
    scope: str | None = None,
    source_agent_id: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    domain_id = _domain_from_header(raw_request.headers.get("x-freyja-security-domain"))
    try:
        query = Freyja3MemoryQuery(
            owner_domain_id=owner_domain_id,
            scope=scope,
            source_agent_id=source_agent_id,
            limit=limit,
        )
        records = memory_store.list(query, reader_domain_id=domain_id)
    except (Freyja3MemoryAccessError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return {"ok": True, "memories": [record.model_dump(mode="json") for record in records], "count": len(records)}


@app.post("/freyja3/machines/heartbeat")
async def record_freyja3_machine_heartbeat(heartbeat: Freyja3MachineHeartbeat, raw_request: Request) -> dict[str, Any]:
    domain_id = _domain_from_header(raw_request.headers.get("x-freyja-security-domain"), SecurityDomainId.SYSTEM)
    try:
        status = machine_status_store.heartbeat(heartbeat, writer_domain_id=domain_id)
    except Freyja3MachineAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return {"ok": True, "machine": status.model_dump(mode="json")}


@app.get("/freyja3/machines")
async def list_freyja3_machines(raw_request: Request) -> dict[str, Any]:
    domain_id = _domain_from_header(raw_request.headers.get("x-freyja-security-domain"), SecurityDomainId.HOUSEHOLD)
    try:
        statuses = machine_status_store.list(reader_domain_id=domain_id)
    except Freyja3MachineAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return {"ok": True, "machines": [status.model_dump(mode="json") for status in statuses], "count": len(statuses)}


@app.post("/freyja3/schedules")
async def create_freyja3_schedule(schedule: Freyja3ScheduleCreate, raw_request: Request) -> dict[str, Any]:
    domain_id = _domain_from_header(raw_request.headers.get("x-freyja-security-domain"))
    try:
        envelope = scheduler_store.create(schedule, writer_domain_id=domain_id)
    except Freyja3ScheduleAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return {"ok": True, "schedule": envelope.model_dump(mode="json")}


@app.get("/freyja3/schedules")
async def list_freyja3_schedules(
    raw_request: Request,
    due_before: str | None = None,
    include_dispatched: bool = False,
    limit: int = 50,
) -> dict[str, Any]:
    domain_id = _domain_from_header(raw_request.headers.get("x-freyja-security-domain"))
    try:
        query = Freyja3ScheduleQuery(due_before=due_before, include_dispatched=include_dispatched, limit=limit)
        schedules = scheduler_store.list(query, reader_domain_id=domain_id)
    except (Freyja3ScheduleAccessError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return {"ok": True, "schedules": [schedule.model_dump(mode="json") for schedule in schedules], "count": len(schedules)}


@app.post("/freyja3/schedules/dispatch-due")
async def dispatch_due_freyja3_schedules(raw_request: Request, due_before: str | None = None, limit: int = 10) -> dict[str, Any]:
    domain_id = _domain_from_header(raw_request.headers.get("x-freyja-security-domain"), SecurityDomainId.SYSTEM)
    if domain_id != SecurityDomainId.SYSTEM:
        raise HTTPException(status_code=403, detail="only system dispatchers may dispatch scheduled agent triggers")
    try:
        due = scheduler_store.list(
            Freyja3ScheduleQuery(due_before=due_before, include_dispatched=False, limit=limit),
            reader_domain_id=SecurityDomainId.SYSTEM,
        )
    except (Freyja3ScheduleAccessError, ValueError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None

    dispatched = []
    for schedule in due:
        request = CanonicalRequest(
            message_id=f"schedule:{schedule.schedule_id}",
            channel=schedule.channel,
            conversation_id=schedule.conversation_id,
            sender=CanonicalSender(channel_id=f"schedule:{schedule.schedule_id}", display_name="Freyja 3 Scheduler"),
            resolved_user_id=schedule.resolved_user_id,
            resolved_agent_id=schedule.target_agent_id,
            text=schedule.text,
            channel_metadata={"schedule_id": schedule.schedule_id, **schedule.metadata},
        )
        response = await _execute_canonical_request(request, raw_request)
        marked = scheduler_store.mark_dispatched(schedule.schedule_id, dispatcher_domain_id=SecurityDomainId.SYSTEM)
        dispatched.append({"schedule": marked.model_dump(mode="json"), "response": response.model_dump(mode="json")})
    return {"ok": True, "dispatched": dispatched, "count": len(dispatched)}


@app.post("/canonical/route")
async def canonical_route(request: CanonicalRequest, raw_request: Request) -> dict[str, Any]:
    response = await _execute_canonical_request(request, raw_request)
    return response.model_dump(mode="json")


@app.post("/events/semantic")
async def publish_semantic_event(event: SemanticEvent, raw_request: Request) -> dict[str, Any]:
    domain_id = _domain_from_header(raw_request.headers.get("x-freyja-security-domain"), SecurityDomainId.SYSTEM)
    try:
        stored = semantic_event_store.publish(event, publisher_domain_id=domain_id)
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
        events = semantic_event_store.list_events(
            SemanticEventQuery(event_type=event_type, room=room, limit=limit),
            reader_domain_id=domain_id,
        )
    except SemanticEventPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return {"ok": True, "events": [event.model_dump(mode="json") for event in events], "count": len(events)}


async def _execute_canonical_request(request: CanonicalRequest, raw_request: Request) -> CanonicalResponse:
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
    target_agent = request.resolved_agent_id or _default_agent_for_user(request.resolved_user_id)
    try:
        gateway_result = agent_gateway.handle(
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
    result = await agent_runtime.arun(gateway_result.handoff)
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


def _domain_from_header(value: str | None, default: SecurityDomainId = SecurityDomainId.HOUSEHOLD) -> SecurityDomainId:
    if not value:
        return default
    try:
        return SecurityDomainId(value)
    except ValueError:
        raise HTTPException(status_code=403, detail="Unknown security domain.") from None


def _security_domain_for_canonical_request(request: CanonicalRequest) -> SecurityDomainId:
    person = (request.resolved_user_id or "").strip().lower()
    return {
        "joe": SecurityDomainId.PERSON_JOE,
        "beth": SecurityDomainId.PERSON_BETH,
        "liam": SecurityDomainId.PERSON_LIAM,
        "jenna": SecurityDomainId.PERSON_JENNA,
    }.get(person, SecurityDomainId.HOUSEHOLD)


def _default_agent_for_user(resolved_user_id: str | None) -> str:
    person = (resolved_user_id or "").strip().lower()
    return {
        "joe": "cloyd-gibbler",
        "beth": "benedict",
        "liam": "agent-44",
        "jenna": "jenna",
    }.get(person, "freyja")
