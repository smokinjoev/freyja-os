from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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
