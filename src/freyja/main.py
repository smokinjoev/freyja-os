from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from freyja.config import settings
from freyja.ollama_client import OllamaClient
from freyja.openrouter_client import OpenRouterClient

app = FastAPI(
    title="Freyja Director",
    version="0.1.0",
    description="Core orchestration service for Freyja-OS.",
)

ollama = OllamaClient()
openrouter = OpenRouterClient()


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


class RouteRequest(BaseModel):
    prompt: str
    provider: str = "auto"
    model: str | None = None


@app.post("/route")
async def route(request: RouteRequest) -> dict[str, str]:
    if request.provider not in {"local", "cloud", "auto"}:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider '{request.provider}'. Use local, cloud, or auto.",
        )

    if request.provider == "local":
        response = await ollama.chat(prompt=request.prompt, model=request.model)
        if "error" in response:
            raise HTTPException(status_code=503, detail=response["error"])
        return {
            "provider": "ollama",
            "model": response.get("model", ""),
            "response": response.get("message", {}).get("content", ""),
        }

    if request.provider == "cloud":
        response = await openrouter.chat(prompt=request.prompt, model=request.model)
        if "error" in response:
            raise HTTPException(status_code=503, detail=response["error"])
        return {
            "provider": "openrouter",
            "model": response.get("model", ""),
            "response": response.get("response", ""),
        }

    response = await ollama.chat(prompt=request.prompt, model=request.model)
    if "error" not in response:
        return {
            "provider": "ollama",
            "model": response.get("model", ""),
            "response": response.get("message", {}).get("content", ""),
        }

    response = await openrouter.chat(prompt=request.prompt, model=request.model)
    if "error" in response:
        raise HTTPException(status_code=503, detail=response["error"])

    return {
        "provider": "openrouter",
        "model": response.get("model", ""),
        "response": response.get("response", ""),
    }
