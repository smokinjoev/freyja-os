import hashlib
import hmac
import ipaddress
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from freyja.agents.approval_provider import PersistentApprovalProvider
from freyja.agents.models import ApprovalStoreError, WritePilotResultWithApprovals
from freyja.agents.runtime import SmithRuntime
from freyja.config import settings
from freyja.identity import person_context_from_headers
from freyja.local_openai_client import LocalOpenAIClient
from freyja.memory import memory_router
from freyja.memory.principal import principal_from_headers
from freyja.ollama_client import OllamaClient
from freyja.openrouter_client import OpenRouterClient
from freyja.router import RouteRequest, router
from freyja.tools.api import tools_router
from freyja.tools.builtin import register_builtin_tools, register_smith_write_pilot_tools
from freyja.tools.registry import get_registry

app = FastAPI(
    title="Freyja Director",
    version="0.1.0",
    description="Core orchestration service for Freyja-OS.",
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
openrouter = OpenRouterClient()
vulcan = LocalOpenAIClient(settings.vulcan_base_url, settings.vulcan_model)
vulcan_coder = LocalOpenAIClient(settings.vulcan_coder_base_url, settings.vulcan_coder_model)
lmstudio = LocalOpenAIClient(settings.lmstudio_base_url, settings.lmstudio_model or "lmstudio")
vision = LocalOpenAIClient(settings.vision_base_url, settings.vision_model)
router.register_clients(ollama, openrouter, vulcan, vulcan_coder)

app.include_router(memory_router)
app.include_router(tools_router)

register_builtin_tools(get_registry())
register_smith_write_pilot_tools(get_registry())

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


async def _endpoint_inventory() -> list[dict[str, Any]]:
    vulcan_ok = await vulcan.healthy()
    vulcan_coder_ok = await vulcan_coder.healthy()
    lmstudio_ok = await lmstudio.healthy() if settings.lmstudio_enabled else False
    vision_local = bool(settings.vision_base_url)
    vision_ok = await vision.healthy() if vision_local else False
    return [
        {
            "id": "vulcan-general",
            "name": "Vulcan General",
            "node": "Vulcan",
            "role": "general reasoning",
            "provider": "llama.cpp",
            "base_url": settings.vulcan_base_url,
            "model": settings.vulcan_model,
            "enabled": settings.vulcan_enabled,
            "reachable": vulcan_ok,
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
            "reachable": vulcan_coder_ok,
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
            "reachable": lmstudio_ok,
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
            "enabled": vision_local or settings.vision_provider == "cloud",
            "reachable": vision_ok,
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
            "enabled": bool(settings.audio_base_url or settings.audio_model),
            "reachable": False,
            "recommended_for": ["transcription", "voice notes", "speech understanding"],
        },
    ]


@app.get("/endpoints")
async def endpoints() -> dict[str, Any]:
    return {"endpoints": await _endpoint_inventory()}


@app.get("/endpoints.html", response_class=HTMLResponse)
async def endpoints_html() -> str:
    endpoints_data = await _endpoint_inventory()
    rows = "\n".join(
        "<tr>"
        f"<td>{item['name']}</td>"
        f"<td>{item['role']}</td>"
        f"<td>{item['provider']}</td>"
        f"<td><code>{item['base_url']}</code></td>"
        f"<td><code>{item.get('wake_url', '')}</code></td>"
        f"<td><code>{item['model']}</code></td>"
        f"<td>{'yes' if item['enabled'] else 'no'}</td>"
        f"<td>{'ok' if item['reachable'] else 'pending'}</td>"
        "</tr>"
        for item in endpoints_data
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Freyja Endpoints</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; color: #17202a; background: #f7f8fa; }}
    main {{ max-width: 1180px; margin: 0 auto; }}
    h1 {{ font-size: 1.8rem; margin: 0 0 1rem; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid #d8dde5; }}
    th, td {{ text-align: left; padding: .75rem; border-bottom: 1px solid #e5e8ee; vertical-align: top; }}
    th {{ font-size: .78rem; text-transform: uppercase; letter-spacing: .04em; color: #526070; background: #eef1f5; }}
    code {{ font-size: .86rem; overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <main>
    <h1>Freyja Endpoints</h1>
    <table>
      <thead>
        <tr><th>Name</th><th>Role</th><th>Provider</th><th>Base URL</th><th>Wake URL</th><th>Model</th><th>Enabled</th><th>Reachable</th></tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </main>
</body>
</html>"""


@app.get("/ollama/health")
async def ollama_health() -> dict[str, bool | str]:
    healthy = await ollama.healthy()
    return {
        "ollama_reachable": healthy,
        "base_url": settings.ollama_base_url,
    }


@app.get("/local-reasoning/health")
async def local_reasoning_health() -> dict[str, bool | str]:
    if settings.vulcan_enabled:
        healthy = await vulcan.healthy()
        return {
            "local_reasoning_reachable": healthy,
            "provider": "vulcan",
            "base_url": settings.vulcan_base_url,
            "model": settings.vulcan_model,
            "model_available": healthy,
        }

    healthy = await ollama.healthy()
    model_available = False
    if healthy:
        tags = await ollama.tags()
        if "error" not in tags:
            model_available = settings.ollama_reasoning_model in {
                model.get("name", "") for model in tags.get("models", [])
            }
    return {
        "local_reasoning_reachable": healthy and model_available,
        "ollama_reachable": healthy,
        "base_url": settings.ollama_base_url,
        "model": settings.ollama_reasoning_model,
        "model_available": model_available,
    }


@app.get("/vulcan/health")
async def vulcan_health() -> dict[str, bool | str]:
    healthy = await vulcan.healthy()
    return {
        "vulcan_enabled": settings.vulcan_enabled,
        "vulcan_reachable": healthy,
        "base_url": settings.vulcan_base_url,
        "model": settings.vulcan_model,
    }


@app.get("/vulcan-coder/health")
async def vulcan_coder_health() -> dict[str, bool | str]:
    healthy = await vulcan_coder.healthy()
    return {
        "vulcan_coder_enabled": settings.vulcan_coder_enabled,
        "vulcan_coder_reachable": healthy,
        "base_url": settings.vulcan_coder_base_url,
        "model": settings.vulcan_coder_model,
    }


@app.get("/vision/health")
async def vision_health() -> dict[str, bool | str]:
    configured = bool(settings.vision_base_url)
    healthy = await vision.healthy() if configured else False
    return {
        "vision_provider": settings.vision_provider,
        "vision_configured": configured,
        "vision_reachable": healthy,
        "base_url": settings.vision_base_url,
        "model": settings.vision_model,
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


class VisionExtractRequest(BaseModel):
    prompt: str
    image_url: str
    model: str | None = None
    output_tokens: int | None = None


@app.post("/chat")
async def chat(request: ChatRequest) -> dict[str, str]:
    response = await ollama.chat(prompt=request.prompt, model=request.model)

    if "error" in response:
        raise HTTPException(status_code=503, detail=response["error"])

    message = response.get("message", {})
    content = message.get("content", "")

    return {"model": response.get("model", ""), "response": content}


@app.post("/vision/extract")
async def vision_extract(request: VisionExtractRequest) -> dict[str, Any]:
    if not settings.vision_base_url:
        raise HTTPException(status_code=503, detail="No local vision endpoint configured")

    response = await vision.vision_chat(
        prompt=request.prompt,
        image_url=request.image_url,
        model=request.model,
        output_tokens=request.output_tokens,
    )
    if "error" in response:
        raise HTTPException(status_code=503, detail=response["error"])
    return response


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
    return response_payload


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
