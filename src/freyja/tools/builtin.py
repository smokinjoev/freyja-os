import os
import subprocess
from pathlib import Path

from freyja.memory.store import get_active_store
from freyja.ollama_client import OllamaClient
from freyja.openrouter_client import OpenRouterClient
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolImplementation, ToolRiskLevel
from freyja.tools.registry import ToolRegistry
from freyja.tools.calendar import register_calendar_tools
from freyja.tools.identity import register_identity_tools
from freyja.tools.homeassistant import register_homeassistant_tools
from freyja.tools.local_host import register_local_host_tools
from freyja.tools.reminders import register_reminder_tools
from freyja.tools.weather import WeatherRequestType, classify_weather_request, get_weather


async def _get_weather_implementation(request: ToolExecutionRequest) -> dict:
    import datetime as _datetime

    args = request.arguments or {}
    location = args.get("location", "")
    request_type_arg = args.get("request_type", "current")
    target_date_arg = args.get("target_date")
    target_label = args.get("target_label", "")

    try:
        request_type = WeatherRequestType(request_type_arg)
    except ValueError:
        return {
            "live_data_available": False,
            "request_type": request_type_arg,
            "location": location,
            "target_label": target_label,
            "summary": "Unsupported weather request type.",
            "detail": "request_type must be 'current' or 'forecast'.",
        }

    target_date = None
    if target_date_arg:
        try:
            target_date = _datetime.datetime.strptime(str(target_date_arg), "%Y-%m-%d").date()
        except ValueError:
            return {
                "live_data_available": False,
                "request_type": request_type_arg,
                "location": location,
                "target_label": target_label,
                "summary": "Invalid forecast date.",
                "detail": "target_date must be in YYYY-MM-DD format.",
            }

    return await get_weather(
        location=location,
        request_type=request_type,
        target_date=target_date,
        target_label=target_label,
    )


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


_BUILTIN_TOOL_NAMES = (
    "system_health",
    "list_models",
    "recall_conversation",
    "get_weather",
    "hostname",
    "current_time",
    "disk_usage",
    "director_health",
    "repository_status",
    "calendar_today_schedule",
    "calendar_tomorrow_schedule",
    "calendar_free_busy",
    "calendar_list_events",
    "calendar_search_events",
    "calendar_create_event",
    "calendar_modify_event",
    "calendar_delete_event",
    "calendar_find_time",
    "calendar_move_event_if_conflict",
    "reminders_lists",
    "reminders_list",
    "reminders_create",
    "reminders_complete",
    "reminders_delete",
    "identity_resolution",
    "identity_relationships",
    "homeassistant_status",
    "homeassistant_list_entities",
    "homeassistant_pairing_plan",
)


def _registration_is_complete(registry: ToolRegistry, names: tuple[str, ...]) -> bool:
    return all(registry.get_tool(name) is not None for name in names)


def _assert_registration_consistent(registry: ToolRegistry, names: tuple[str, ...]) -> None:
    present = {name for name in names if registry.get_tool(name) is not None}
    if present and present != set(names):
        missing = set(names) - present
        raise RuntimeError(
            f"Tool registration is inconsistent: present={sorted(present)}, missing={sorted(missing)}"
        )


def register_builtin_tools(registry: ToolRegistry) -> None:
    _assert_registration_consistent(registry, _BUILTIN_TOOL_NAMES)
    if _registration_is_complete(registry, _BUILTIN_TOOL_NAMES):
        return
    register_local_host_tools(registry)
    register_calendar_tools(registry)
    register_reminder_tools(registry)
    register_identity_tools(registry)
    register_homeassistant_tools(registry)
    registry.register(
        ToolDefinition(
            name="get_weather",
            description=(
                "Return current weather or a forecast for a location. "
                "request_type must be 'current' or 'forecast'; for forecast, "
                "target_date and target_label should be supplied. Falls back safely if live data is not configured."
            ),
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["location", "request_type"],
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City or location, e.g. 'Aiken, South Carolina'.",
                    },
                    "request_type": {
                        "type": "string",
                        "enum": ["current", "forecast"],
                        "description": "Whether to fetch current conditions or a forecast.",
                    },
                    "target_date": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD) for forecast requests.",
                    },
                    "target_label": {
                        "type": "string",
                        "description": "Human label for the forecast date, e.g. 'tomorrow'.",
                    },
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "live_data_available": {"type": "boolean"},
                    "request_type": {"type": "string"},
                    "location": {"type": "string"},
                    "target_label": {"type": "string"},
                    "summary": {"type": "string"},
                    "detail": {"type": "string"},
                },
            },
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=20,
            tags=["weather", "live-data"],
        ),
        _get_weather_implementation,
    )
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


async def _write_pilot_file_write_implementation(request: ToolExecutionRequest) -> dict:
    """Write a single file atomically inside the approved write-pilot sandbox.

    Requires ``target_path`` (repository-relative) and ``content``.  Creates a
    restrictive before-state backup at ``<target>.bak.<timestamp>`` adjacent to
    the target, writes the new content to a temporary file, then renames it into
    place.  Returns a sanitized result with no secrets.
    """
    args = request.arguments or {}
    target_path = args.get("target_path")
    content = args.get("content")
    repo_root = args.get("repo_root")

    if not target_path:
        return {"error": "Missing required argument: target_path"}
    if content is None:
        return {"error": "Missing required argument: content"}

    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[3]

    # Local sandbox validation using the provided repo root; do not load a
    # fresh policy that would ignore the runtime/test repository.
    path_obj = Path(target_path)
    if not target_path or path_obj.is_absolute() or ".." in path_obj.parts:
        return {"error": f"Invalid write-pilot target path: {target_path}", "blocked": True}
    if path_obj.suffix.lower() != ".md":
        return {"error": f"Path '{target_path}' is not a Markdown (.md) file.", "blocked": True}
    target = (root / target_path).resolve(strict=False)
    sandbox = (root / "docs" / "smith-pilot").resolve()
    try:
        target.relative_to(sandbox)
    except ValueError:
        return {"error": f"Path '{target_path}' is outside the write-pilot sandbox '{sandbox}'.", "blocked": True}
    if target.is_symlink() or any(p.is_symlink() for p in target.parents if p != root):
        return {"error": f"Path '{target_path}' is a symlink or traverses a symlink.", "blocked": True}

    args = request.arguments or {}
    create_backup = args.get("create_backup", True)
    backup_path: Path | None = None
    existed = target.exists()
    original_mode = target.stat().st_mode if existed else 0o644

    try:
        import time

        target.parent.mkdir(parents=True, exist_ok=True)
        if existed and create_backup:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            # Avoid collisions if multiple backups are created in the same second.
            backup_path = target.with_suffix(f"{target.suffix}.bak.{timestamp}")
            counter = 0
            while backup_path.exists():
                counter += 1
                backup_path = target.with_suffix(f"{target.suffix}.bak.{timestamp}-{counter}")
            backup_path.write_bytes(target.read_bytes())

        tmp_path = target.with_suffix(f"{target.suffix}.tmp")
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.chmod(original_mode)
        tmp_path.replace(target)
        return {
            "success": True,
            "target_path": target_path,
            "wrote_new_file": not existed,
            "backup_path": str(backup_path.relative_to(root)) if backup_path else None,
        }
    except Exception as exc:
        return {"error": f"Failed to write {target_path}: {exc}", "success": False}


async def _write_pilot_git_add_implementation(request: ToolExecutionRequest) -> dict:
    """Stage a single, explicitly approved repository-relative file.

    Uses a fixed argv with ``--`` separators and never stages wildcards or ``.``.
    """
    args = request.arguments or {}
    target_path = args.get("target_path")
    repo_root = args.get("repo_root")

    if not target_path:
        return {"error": "Missing required argument: target_path"}

    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[3]
    try:
        proc = subprocess.run(
            ["git", "add", "--", target_path],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "success": proc.returncode == 0,
            "target_path": target_path,
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip() if proc.stderr else None,
        }
    except Exception as exc:
        return {"error": str(exc), "success": False}


async def _write_pilot_git_commit_implementation(request: ToolExecutionRequest) -> dict:
    """Commit staged changes with an explicitly approved message.

    Uses a fixed argv, no shell, and returns the resulting commit hash.
    If ``target_path`` is provided, only that path is committed.
    """
    args = request.arguments or {}
    message = args.get("message")
    repo_root = args.get("repo_root")
    target_path = args.get("target_path")

    if not message:
        return {"error": "Missing required argument: message"}

    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[3]
    argv = ["git", "commit", "-m", message]
    if target_path:
        argv.extend(["--", target_path])
    try:
        proc = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        commit_hash = None
        if proc.returncode == 0:
            hash_proc = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            if hash_proc.returncode == 0:
                commit_hash = hash_proc.stdout.strip()
        return {
            "success": proc.returncode == 0,
            "commit_hash": commit_hash,
            "returncode": proc.returncode,
            "stderr": proc.stderr.strip() if proc.stderr else None,
        }
    except Exception as exc:
        return {"error": str(exc), "success": False}


async def _validate_diff_implementation(request: ToolExecutionRequest) -> dict:
    """Validate that uncommitted changes are safe for Agent Smith operations.

    Returns a structured safety report including:

    * whether any secrets/env files were modified,
    * whether any non-Python files or untrusted paths are touched,
    * a sanitized diff stat with secret paths redacted,
    * an overall ``safe_to_proceed`` boolean.
    """
    repo_root = Path(__file__).resolve().parents[3]
    secret_patterns = [
        r"\.env",
        r"(^|/)secrets?(/|$)",
        r"\.pem$",
        r"\.key$",
        r"\.pfx$",
        r"\.p12$",
        r"\.crt$",
        r"token",
        r"api_key",
        r"password",
    ]
    try:
        status_proc = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        diff_proc = subprocess.run(
            ["git", "diff", "--name-status", "--", ":!*.secret", ":!*.env"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception as exc:
        return {"repository_root": str(repo_root), "error": str(exc)}

    raw_lines = status_proc.stdout.strip().splitlines()
    changed_files: list[str] = []
    secret_touched = False
    non_python_touched = False

    for line in raw_lines:
        if not line.strip():
            continue
        # git status --short: XY filename or XY filename -> filename for renames.
        parts = line.split()
        if " -> " in line:
            path_part = line.split(" -> ")[-1].strip()
        else:
            path_part = " ".join(parts[1:]).strip()
        relative_path = Path(path_part)
        changed_files.append(str(relative_path))
        lowered = str(relative_path).lower()
        if any(re.search(pattern, lowered) for pattern in secret_patterns):
            secret_touched = True
        if not any(
            lowered.endswith(ext)
            for ext in (".py", ".yaml", ".yml", ".json", ".md", ".txt", ".sh", ".gitignore")
        ):
            non_python_touched = True

    safe_to_proceed = not secret_touched and not non_python_touched and changed_files

    # Sanitize the public report: strip absolute paths and any secret-looking names.
    sanitized_files = []
    for path_str in changed_files:
        name = Path(path_str).name
        lowered = path_str.lower()
        if any(re.search(pattern, lowered) for pattern in secret_patterns):
            sanitized_files.append(f"<redacted secret path>/{name}")
        else:
            sanitized_files.append(path_str)

    return {
        "repository_root": str(repo_root),
        "git_available": status_proc.returncode == 0,
        "changed_files": sanitized_files,
        "total_changes": len(changed_files),
        "secret_touched": secret_touched,
        "non_standard_touched": non_python_touched,
        "safe_to_proceed": safe_to_proceed,
        "diff_name_status": diff_proc.stdout.strip(),
    }


_SMITH_READ_ONLY_TOOL_NAMES = (
    "repository_diff_summary",
    "run_test_suite",
    "compile_project",
    "validate_diff",
)

_SMITH_WRITE_PILOT_TOOL_NAMES = (
    "write_pilot_file_write",
    "write_pilot_git_add",
    "write_pilot_git_commit",
)


def register_smith_read_only_tools(registry: ToolRegistry) -> None:
    _assert_registration_consistent(registry, _SMITH_READ_ONLY_TOOL_NAMES)
    if _registration_is_complete(registry, _SMITH_READ_ONLY_TOOL_NAMES):
        return
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
    registry.register(
        ToolDefinition(
            name="validate_diff",
            description="Validate that uncommitted repository changes are safe before a Smith maintenance step.",
            version="1.0.0",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {}},
            risk_level=ToolRiskLevel.READ_ONLY,
            enabled=True,
            timeout_seconds=30,
            tags=["smith", "diff", "validation"],
        ),
        _validate_diff_implementation,
    )


def register_smith_write_pilot_tools(registry: ToolRegistry) -> None:  # Fixed to sync
    _assert_registration_consistent(registry, _SMITH_WRITE_PILOT_TOOL_NAMES)
    if _registration_is_complete(registry, _SMITH_WRITE_PILOT_TOOL_NAMES):
        return
    registry.register(
        ToolDefinition(
            name="write_pilot_file_write",
            description="Atomically write a single approved Markdown file inside the write-pilot sandbox.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["target_path", "content"],
                "properties": {
                    "target_path": {"type": "string"},
                    "content": {"type": "string"},
                    "repo_root": {"type": "string"},
                    "create_backup": {"type": "boolean"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "target_path": {"type": "string"},
                    "wrote_new_file": {"type": "boolean"},
                    "backup_path": {"type": ["string", "null"]},
                    "error": {"type": ["string", "null"]},
                    "blocked": {"type": "boolean"},
                },
            },
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            enabled=False,
            timeout_seconds=30,
            tags=["smith", "write-pilot", "file"],
        ),
        _write_pilot_file_write_implementation,
    )
    registry.register(
        ToolDefinition(
            name="write_pilot_git_add",
            description="Stage a single, explicitly approved repository-relative file.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["target_path"],
                "properties": {
                    "target_path": {"type": "string"},
                    "repo_root": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "target_path": {"type": "string"},
                    "returncode": {"type": "integer"},
                    "error": {"type": ["string", "null"]},
                },
            },
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            enabled=False,
            timeout_seconds=30,
            tags=["smith", "write-pilot", "git"],
        ),
        _write_pilot_git_add_implementation,
    )
    registry.register(
        ToolDefinition(
            name="write_pilot_git_commit",
            description="Commit staged changes with an explicitly approved message and optional target path.",
            version="1.0.0",
            input_schema={
                "type": "object",
                "required": ["message"],
                "properties": {
                    "message": {"type": "string"},
                    "repo_root": {"type": "string"},
                    "target_path": {"type": "string"},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "commit_hash": {"type": ["string", "null"]},
                    "returncode": {"type": "integer"},
                    "error": {"type": ["string", "null"]},
                },
            },
            risk_level=ToolRiskLevel.CONTROLLED_WRITE,
            enabled=False,
            timeout_seconds=30,
            tags=["smith", "write-pilot", "git"],
        ),
        _write_pilot_git_commit_implementation,
    )
