import hashlib
import ipaddress
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from freyja.agents.approval_provider import PersistentApprovalProvider
from freyja.agents.models import ApprovalStoreError, WritePilotResultWithApprovals
from freyja.agents.runtime import SmithRuntime
from freyja.config import settings
from freyja.memory import memory_router
from freyja.ollama_client import OllamaClient
from freyja.openrouter_client import OpenRouterClient
from freyja.router import RouteRequest, router
from freyja.tools.api import tools_router
from freyja.tools.builtin import register_builtin_tools
from freyja.tools.registry import get_registry

app = FastAPI(
    title="Freyja Director",
    version="0.1.0",
    description="Core orchestration service for Freyja-OS.",
)

ollama = OllamaClient()
openrouter = OpenRouterClient()
router.register_clients(ollama, openrouter)

app.include_router(memory_router)
app.include_router(tools_router)

register_builtin_tools(get_registry())


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


@app.post("/route")
async def route(request: RouteRequest) -> dict:
    result = await router.execute(request)
    if result.decision.provider == "error":
        raise HTTPException(status_code=400, detail=result.decision.reason)
    if not result.response:
        raise HTTPException(
            status_code=503,
            detail=result.decision.public_error_message or "No approved provider is currently available.",
        )
    return {
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


class SmithDryRunRequest(BaseModel):
    objective: str
    actor: str = "agent_smith"
    request_id: str | None = None


class SmithReadOnlyRequest(BaseModel):
    objective: str
    actor: str = "agent_smith"
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
        request_id=request.request_id,
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


def _require_loopback(request: Request) -> None:
    if not settings.agent_smith_approval_loopback_only:
        return
    client = request.client
    if client is None or not client.host:
        raise HTTPException(
            status_code=403,
            detail="Approval admin endpoint requires a client address.",
        )
    host = client.host
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise HTTPException(
            status_code=403,
            detail="Approval admin endpoint received an invalid client address.",
        ) from exc
    if not address.is_loopback:
        raise HTTPException(
            status_code=403,
            detail="Approval admin endpoint is only available from loopback.",
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
    elif record.content_hash is not None and record.content_hash != _hash_for_validation(body.proposed_content):
        mismatch = "proposed_content"
    elif record.commit_message_hash is not None and record.commit_message_hash != _hash_for_validation(body.commit_message):
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
    )
    return result.model_dump(mode="json")
