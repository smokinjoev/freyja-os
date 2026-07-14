from freyja.memory.store import get_active_store
from freyja.ollama_client import OllamaClient
from freyja.openrouter_client import OpenRouterClient
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolImplementation, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


async def _system_health_implementation(request: ToolExecutionRequest) -> dict:
    return {
        "director": {"status": "ok"},
        "ollama": {
            "healthy": await _ollama_healthy(),
            "base_url": getattr(_ollama_client(), "base_url", None),
        },
        "openrouter": {"healthy": await _openrouter_healthy()},
        "memory": {"enabled": _memory_enabled()},
    }


async def _list_models_implementation(request: ToolExecutionRequest) -> dict:
    tags = await _ollama_tags()
    if isinstance(tags, dict) and "error" in tags:
        return {"models": [], "ollama_error": tags["error"]}
    return {"models": tags.get("models", [])}


async def _recall_conversation_implementation(request: ToolExecutionRequest) -> dict:
    args = request.arguments or {}
    conversation_id = args.get("conversation_id")
    if not conversation_id:
        return {"error": "Missing required argument: conversation_id"}
    limit = args.get("limit", 50)
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return {"error": "limit must be an integer"}
    response = get_active_store().get_messages(conversation_id, limit=limit)
    return {
        "conversation_id": response.conversation_id,
        "messages": [message.model_dump(mode="json") for message in response.messages],
        "count": len(response.messages),
    }


def register_builtin_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="system_health",
            description="Read-only health check for Director, Ollama, OpenRouter, and memory store.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=10,
            tags=["system", "health"],
        ),
        _system_health_implementation,
    )
    registry.register(
        ToolDefinition(
            name="list_models",
            description="List available local models from the Ollama server.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={
                "type": "object",
                "properties": {
                    "models": {"type": "array"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=10,
            tags=["ollama", "models"],
        ),
        _list_models_implementation,
    )
    registry.register(
        ToolDefinition(
            name="recall_conversation",
            description="Recall recent messages from a conversation via the memory store.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["conversation_id"],
                "properties": {
                    "conversation_id": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "conversation_id": {"type": "string"},
                    "messages": {"type": "array"},
                    "count": {"type": "integer"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=10,
            tags=["memory", "recall"],
        ),
        _recall_conversation_implementation,
    )


_ollama_singleton: OllamaClient | None = None
_openrouter_singleton: OpenRouterClient | None = None


def _ollama_client() -> OllamaClient:
    global _ollama_singleton
    if _ollama_singleton is None:
        _ollama_singleton = OllamaClient()
    return _ollama_singleton


def _openrouter_client() -> OpenRouterClient:
    global _openrouter_singleton
    if _openrouter_singleton is None:
        _openrouter_singleton = OpenRouterClient()
    return _openrouter_singleton


async def _ollama_healthy() -> bool:
    try:
        return await _ollama_client().healthy()
    except Exception:
        return False


async def _ollama_tags() -> dict:
    try:
        return await _ollama_client().tags()
    except Exception as exc:
        return {"error": str(exc)}


async def _openrouter_healthy() -> bool:
    try:
        return await _openrouter_client().healthy()
    except Exception:
        return False


def _memory_enabled() -> bool:
    from freyja.memory.store import is_memory_enabled

    return is_memory_enabled()
