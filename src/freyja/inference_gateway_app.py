import hmac
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from freyja.config import settings
from freyja.inference_gateway import inference_gateway_router
from freyja.ollama_client import OllamaClient
from freyja.ollama_warmup import start_ollama_warmup, stop_ollama_warmup


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_ollama_warmup(app, ollama, service_name="inference-gateway")
    try:
        yield
    finally:
        await stop_ollama_warmup(app)


app = FastAPI(
    title="Freyja Inference Gateway",
    version="0.1.0",
    description="Semantic tier routing gateway for Freyja inference.",
    lifespan=lifespan,
)


ollama = OllamaClient(model=settings.inference_gateway_local_model)


@app.middleware("http")
async def require_gateway_auth(request: Request, call_next):
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


app.include_router(inference_gateway_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "freyja-inference-gateway",
        "status": "online",
        "version": "0.1.0",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "healthy",
        "gateway_enabled": settings.inference_gateway_enabled,
    }
