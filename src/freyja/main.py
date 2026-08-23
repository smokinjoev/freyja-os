import hashlib
import hmac
import ipaddress
import time
from contextlib import asynccontextmanager
from typing import Any

import httpx

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from freyja.agents import AgentHierarchy, PersonName
from freyja.agents.approval_provider import PersistentApprovalProvider
from freyja.agents.models import ApprovalStoreError, WritePilotResultWithApprovals
from freyja.agents.runtime import SmithRuntime
from freyja.config import settings
from freyja.home_assistant_monitor import (
    start_home_assistant_inventory_monitor,
    stop_home_assistant_inventory_monitor,
)
from freyja.identity import person_context_from_headers
from freyja.iris_monitor import start_iris_warm_monitor, stop_iris_warm_monitor
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
router.register_clients(ollama, openrouter)
router.register_reasoning_client(reasoning_ollama)

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



async def _openai_health(base_url: str) -> bool:
    if not base_url:
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base_url.rstrip('/')}/models")
            return response.status_code == 200
    except Exception:
        return False


async def _local_chat_completion(
    *,
    base_url: str,
    model: str,
    prompt: str,
    image_url: str | None = None,
    output_tokens: int | None = None,
) -> dict[str, Any]:
    if image_url:
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            }
        ]
    else:
        messages = [{"role": "user", "content": prompt}]
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": output_tokens or settings.vulcan_default_output_tokens,
    }
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=240.0) as client:
        response = await client.post(f"{base_url.rstrip('/')}/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    return {
        "status": "ok",
        "model": data.get("model", model),
        "response": message.get("content", ""),
        "usage": data.get("usage", {}),
        "latency_ms": int((time.monotonic() - started) * 1000),
        "finish_reason": choice.get("finish_reason", ""),
    }


@app.get("/endpoints")
async def endpoints() -> dict[str, Any]:
    vulcan_reachable = await _openai_health(settings.vulcan_base_url) if settings.vulcan_enabled else False
    coder_reachable = await _openai_health(settings.vulcan_coder_base_url) if settings.vulcan_coder_enabled else False
    lmstudio_reachable = await _openai_health(settings.lmstudio_base_url) if settings.lmstudio_enabled else False
    vision_reachable = await _openai_health(settings.vision_base_url) if settings.vision_provider == "local" else False
    return {
        "endpoints": [
            {
                "id": "vulcan-general",
                "name": "Vulcan General",
                "node": "Vulcan",
                "role": "general reasoning",
                "provider": "llama.cpp",
                "base_url": settings.vulcan_base_url,
                "model": settings.vulcan_model,
                "enabled": settings.vulcan_enabled,
                "reachable": vulcan_reachable,
                "recommended_for": ["complex chat", "planning", "local reasoning"],
            },
            {
                "id": "vulcan-coder",
                "name": "Vulcan Coder",
                "node": "Vulcan",
                "role": "coding",
                "provider": "llama.cpp",
                "base_url": settings.vulcan_coder_base_url,
                "model": settings.vulcan_coder_model,
                "enabled": settings.vulcan_coder_enabled,
                "reachable": coder_reachable,
                "recommended_for": ["coding", "debugging", "refactoring"],
            },
            {
                "id": "lmstudio",
                "name": "LM Studio",
                "node": "Vulcan",
                "role": "wake-on-query experiments",
                "provider": "lmstudio-proxy",
                "base_url": settings.lmstudio_base_url,
                "wake_url": settings.lmstudio_wake_url,
                "model": settings.lmstudio_model,
                "enabled": settings.lmstudio_enabled,
                "reachable": lmstudio_reachable,
                "recommended_for": ["iPad experiments", "model trials", "manual chat"],
            },
            {
                "id": "vision-docs",
                "name": "Vision Docs",
                "node": "Vulcan",
                "role": "vision/document inference",
                "provider": settings.vision_provider,
                "base_url": settings.vision_base_url,
                "model": settings.vision_model,
                "enabled": settings.vision_provider == "local" and bool(settings.vision_base_url),
                "reachable": vision_reachable,
                "recommended_for": ["OCR", "document understanding", "image-heavy PDFs"],
            },
            {
                "id": "audio",
                "name": "Audio",
                "node": "Vulcan",
                "role": "speech and audio inference",
                "provider": settings.audio_provider,
                "base_url": settings.audio_base_url,
                "model": settings.audio_model,
                "enabled": bool(settings.audio_base_url),
                "reachable": False,
                "recommended_for": ["transcription", "voice notes", "speech understanding"],
            },
        ]
    }


@app.get("/vulcan/health")
async def vulcan_health() -> dict[str, bool | str]:
    return {
        "vulcan_enabled": settings.vulcan_enabled,
        "vulcan_reachable": await _openai_health(settings.vulcan_base_url) if settings.vulcan_enabled else False,
        "base_url": settings.vulcan_base_url,
        "model": settings.vulcan_model,
    }


@app.get("/vulcan-coder/health")
async def vulcan_coder_health() -> dict[str, bool | str]:
    return {
        "vulcan_coder_enabled": settings.vulcan_coder_enabled,
        "vulcan_coder_reachable": await _openai_health(settings.vulcan_coder_base_url) if settings.vulcan_coder_enabled else False,
        "base_url": settings.vulcan_coder_base_url,
        "model": settings.vulcan_coder_model,
    }


@app.get("/vision/health")
async def vision_health() -> dict[str, bool | str]:
    reachable = await _openai_health(settings.vision_base_url) if settings.vision_provider == "local" else False
    return {
        "vision_provider": settings.vision_provider,
        "vision_configured": settings.vision_provider == "local" and bool(settings.vision_base_url),
        "vision_reachable": reachable,
        "base_url": settings.vision_base_url,
        "model": settings.vision_model,
    }


class VisionExtractRequest(BaseModel):
    prompt: str
    image_url: str
    model: str | None = None
    output_tokens: int | None = None


@app.post("/vision/extract")
async def vision_extract(request: VisionExtractRequest) -> dict[str, Any]:
    if settings.vision_provider != "local" or not settings.vision_base_url:
        raise HTTPException(status_code=503, detail="Local vision provider is not configured.")
    try:
        return await _local_chat_completion(
            base_url=settings.vision_base_url,
            model=request.model or settings.vision_model,
            prompt=request.prompt,
            image_url=request.image_url,
            output_tokens=request.output_tokens,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=503, detail=f"Vision provider HTTP {exc.response.status_code}: {exc.response.text[:500]}") from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
