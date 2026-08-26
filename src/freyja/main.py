import hashlib
import hmac
import ipaddress
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from freyja.agents import AgentHierarchy, PersonName
from freyja.agents.approval_provider import PersistentApprovalProvider
from freyja.agents.models import ApprovalStoreError, WritePilotResultWithApprovals
from freyja.agents.runtime import SmithRuntime
from freyja.agent_gateway import AgentGateway, GatewayAuthenticationError, GatewayPermissionError, GatewayRequest
from freyja.agent_runtime_v3 import AgentRuntimeV3
from freyja.config import settings
from freyja.contracts import CanonicalAttachment, CanonicalRequest, CanonicalResponse
from freyja.foundation_models import GatewaySender, SecurityDomainId
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
from freyja.memory import memory_router
from freyja.memory.principal import principal_from_headers
from freyja.ollama_client import OllamaClient
from freyja.openrouter_client import OpenRouterClient
from freyja.router import RouteRequest, router
from freyja.tools.api import tools_router
from freyja.tools.builtin import register_builtin_tools, register_smith_read_only_tools, register_smith_write_pilot_tools
from freyja.tools.registry import get_registry


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
async def require_connector_auth(request: Request, call_next):
    """Require a bearer token for non-public Director endpoints when configured."""
    expected = settings.freyja_connector_token
    if not expected or request.url.path in {"/", "/health"}:
        return await call_next(request)

    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    authorized = (
        scheme.lower() == "bearer"
        and bool(supplied)
        and hmac.compare_digest(supplied, expected)
    )
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
agent_runtime_v3 = AgentRuntimeV3()

app.include_router(memory_router)
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
    target_agent = request.resolved_agent_id or _default_agent_for_user(request.resolved_user_id)
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
    result = agent_runtime_v3.run(gateway_result.handoff)
    return CanonicalResponse(
        trace_id=request.trace_id,
        request_message_id=request.message_id,
        channel=request.channel,
        conversation_id=result.conversation_id,
        resolved_user_id=request.resolved_user_id,
        resolved_agent_id=result.agent_id,
        text=result.response_text,
        tool_results=[{"tool_name": tool_id, "success": True} for tool_id in result.selected_tools],
        channel_metadata={
            "freyja3": True,
            "gateway_audit": gateway_result.audit_event.model_dump(mode="json"),
            "agent_steps": [step.model_dump(mode="json") for step in result.steps],
            "inference_endpoint_id": result.inference_endpoint_id,
            "inference_model": result.inference_model,
            "inference_machine_id": result.inference_machine_id,
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
        "liam": "agent-44",
        "jenna": "jenna",
    }.get(person, "freyja")


@app.post("/canonical/route")
async def canonical_route(request: CanonicalRequest, raw_request: Request) -> dict[str, Any]:
    response = await _execute_canonical_request(request, raw_request)
    return response.model_dump(mode="json")


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


class SmithDryRunRequest(BaseModel):
    objective: str
    actor: str = "agent_smith"
    request_id: str | None = None


class SmithReadOnlyRequest(BaseModel):
    objective: str
    actor: str = "agent_smith"
    request_id: str | None = None


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
