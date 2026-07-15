import os
import subprocess
from pathlib import Path

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


async def _repository_status_implementation(request: ToolExecutionRequest) -> dict:
    repo_root = Path(__file__).resolve().parents[3]
    try:
        status_proc = subprocess.run(
            ["git", "status", "--short", "--branch"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        diff_proc = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "repository_root": str(repo_root),
            "branch_status": status_proc.stdout.strip(),
            "diff_summary": diff_proc.stdout.strip(),
            "git_available": status_proc.returncode == 0,
        }
    except Exception as exc:
        return {"repository_root": str(repo_root), "error": str(exc)}


async def _repository_diff_summary_implementation(request: ToolExecutionRequest) -> dict:
    repo_root = Path(__file__).resolve().parents[3]
    try:
        proc = subprocess.run(
            ["git", "diff", "--stat"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "repository_root": str(repo_root),
            "diff_summary": proc.stdout.strip(),
            "git_available": proc.returncode == 0,
        }
    except Exception as exc:
        return {"repository_root": str(repo_root), "error": str(exc)}


async def _run_test_suite_implementation(request: ToolExecutionRequest) -> dict:
    repo_root = Path(__file__).resolve().parents[3]
    venv_bin = os.path.join(repo_root, ".venv", "bin")
    pytest_path = os.path.join(venv_bin, "pytest")
    try:
        proc = subprocess.run(
            [pytest_path, "-q", "--tb=short", "--ignore=tests/test_agent_smith.py"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=110,
        )
        return {
            "returncode": proc.returncode,
            "passed": proc.returncode == 0,
            "stdout_tail": "\n".join(proc.stdout.strip().splitlines()[-20:]),
            "stderr_tail": "\n".join(proc.stderr.strip().splitlines()[-20:]),
        }
    except Exception as exc:
        return {"error": str(exc)}


async def _compile_project_implementation(request: ToolExecutionRequest) -> dict:
    repo_root = Path(__file__).resolve().parents[3]
    try:
        proc = subprocess.run(
            ["python", "-m", "compileall", str(repo_root / "src")],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "returncode": proc.returncode,
            "passed": proc.returncode == 0,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
    except Exception as exc:
        return {"error": str(exc)}


def register_smith_read_only_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="repository_status",
            description="Read-only git status and branch summary for the repository.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=30,
            tags=["smith", "git", "status"],
        ),
        _repository_status_implementation,
    )
    registry.register(
        ToolDefinition(
            name="repository_diff_summary",
            description="Read-only summary of uncommitted repository changes.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=30,
            tags=["smith", "git", "diff"],
        ),
        _repository_diff_summary_implementation,
    )
    registry.register(
        ToolDefinition(
            name="run_test_suite",
            description="Run the project pytest suite and return results.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=120,
            tags=["smith", "tests"],
        ),
        _run_test_suite_implementation,
    )
    registry.register(
        ToolDefinition(
            name="compile_project",
            description="Compile all project Python sources to verify syntax.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=60,
            tags=["smith", "compile"],
        ),
        _compile_project_implementation,
    )
