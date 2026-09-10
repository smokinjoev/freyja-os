from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from freyja.config import settings
from freyja.tools.models import ToolDefinition, ToolExecutionRequest, ToolRiskLevel
from freyja.tools.registry import ToolRegistry


MODEL = {"providerID": "vulcan-nexus", "modelID": "@preset/freyja-coder"}


def _password() -> str:
    return Path(settings.opencode_password_file).expanduser().read_text(encoding="utf-8").strip()


def _request(method: str, path: str, body: dict[str, Any] | None = None, *, query: dict[str, str] | None = None) -> Any:
    if query:
        path = f"{path}?{urllib.parse.urlencode(query)}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(f"{settings.opencode_base_url.rstrip('/')}{path}", data=data, method=method)
    credentials = f"{settings.opencode_username}:{_password()}".encode("utf-8")
    request.add_header("authorization", "Basic " + base64.b64encode(credentials).decode("ascii"))
    if body is not None:
        request.add_header("content-type", "application/json")
    try:
        timeout = float(os.environ.get("OPENCODE_REQUEST_TIMEOUT_SECONDS", "300"))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "error": detail}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    if not payload:
        return {"ok": True}
    result = json.loads(payload)
    if isinstance(result, dict):
        result.setdefault("ok", True)
    return result


def _load_aliases() -> dict[str, str]:
    path = Path(settings.opencode_session_registry_path).expanduser()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_aliases(aliases: dict[str, str]) -> None:
    path = Path(settings.opencode_session_registry_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(aliases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def _session_id(alias_or_session: str) -> str:
    if alias_or_session.startswith("ses_"):
        return alias_or_session
    aliases = _load_aliases()
    return aliases.get(alias_or_session, "")


def _recent_action(parts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for part in reversed(parts):
        if part.get("type") != "tool":
            continue
        state = part.get("state") or {}
        return {
            "tool": part.get("tool"),
            "status": state.get("status"),
            "input": state.get("input"),
            "output": state.get("output"),
            "error": state.get("error"),
        }
    return None


def _summarize_message(session_id: str, result: dict[str, Any]) -> dict[str, Any]:
    parts = result.get("parts", []) if isinstance(result, dict) else []
    text = "\n".join(part.get("text", "") for part in parts if part.get("type") == "text").strip()
    action = _recent_action(parts)
    output = text or ((action or {}).get("output") or "")
    info = result.get("info") or {}
    return {
        "session": session_id,
        "state": "completed" if info.get("time", {}).get("completed") else "working",
        "agent": info.get("agent"),
        "working_directory": (info.get("path") or {}).get("cwd"),
        "message": info.get("id"),
        "recent_action": action,
        "result": output,
    }


async def _opencode_start(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    alias = str(args.get("alias") or "coder").strip()
    directory = str(args.get("directory") or "").strip()
    query = {"directory": directory} if directory else None
    result = _request("POST", "/session", {"title": alias}, query=query)
    if not result.get("ok", True):
        return result
    aliases = _load_aliases()
    aliases[alias] = result["id"]
    _save_aliases(aliases)
    return {
        "ok": True,
        "alias": alias,
        "session": result["id"],
        "working_directory": result.get("directory"),
        "state": "idle",
    }


async def _opencode_send(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    alias = str(args.get("alias") or "coder").strip()
    prompt = str(args.get("prompt") or "").strip()
    session_id = _session_id(alias)
    if not session_id:
        directory = str(args.get("directory") or settings.repository_root).strip()
        start_result = _request("POST", "/session", {"title": alias}, query={"directory": directory})
        if not start_result.get("ok", True):
            return start_result
        aliases = _load_aliases()
        aliases[alias] = start_result["id"]
        _save_aliases(aliases)
        session_id = start_result["id"]
    result = _request(
        "POST",
        f"/session/{session_id}/message",
        {"model": MODEL, "agent": "build", "parts": [{"type": "text", "text": prompt}]},
    )
    if not result.get("ok", True):
        return result
    return {"ok": True, **_summarize_message(session_id, result)}


async def _opencode_shell(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    alias = str(args.get("alias") or "coder").strip()
    command = str(args.get("command") or "").strip()
    session_id = _session_id(alias)
    if not session_id:
        return {"ok": False, "error": f"Unknown OpenCode session alias: {alias}"}
    result = _request("POST", f"/session/{session_id}/shell", {"agent": "build", "model": MODEL, "command": command})
    if not result.get("ok", True):
        return result
    return {"ok": True, **_summarize_message(session_id, result)}


async def _opencode_status(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    alias = str(args.get("alias") or "coder").strip()
    session_id = _session_id(alias)
    if not session_id:
        return {"ok": False, "error": f"Unknown OpenCode session alias: {alias}"}
    statuses = _request("GET", "/session/status")
    session = _request("GET", f"/session/{session_id}")
    messages = _request("GET", f"/session/{session_id}/message", query={"limit": "1"})
    parts = messages[0].get("parts", []) if isinstance(messages, list) and messages else []
    return {
        "ok": True,
        "alias": alias,
        "session": session_id,
        "working_directory": session.get("directory"),
        "state": statuses.get(session_id, "idle") if isinstance(statuses, dict) else "unknown",
        "recent_action": _recent_action(parts),
    }


async def _opencode_output(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    alias = str(args.get("alias") or "coder").strip()
    limit = str(max(1, min(int(args.get("limit") or 5), 25)))
    session_id = _session_id(alias)
    if not session_id:
        return {"ok": False, "error": f"Unknown OpenCode session alias: {alias}"}
    return {"ok": True, "session": session_id, "messages": _request("GET", f"/session/{session_id}/message", query={"limit": limit})}


async def _opencode_stop(request: ToolExecutionRequest) -> dict[str, Any]:
    args = request.arguments or {}
    alias = str(args.get("alias") or "coder").strip()
    session_id = _session_id(alias)
    if not session_id:
        return {"ok": False, "error": f"Unknown OpenCode session alias: {alias}"}
    return {"ok": True, "session": session_id, "aborted": _request("POST", f"/session/{session_id}/abort")}


def register_opencode_tools(registry: ToolRegistry) -> None:
    for definition, implementation in (
        (
            ToolDefinition(
                name="opencode_start",
                description="Start or register an OpenCode coding session for a specific repository or worktree.",
                input_schema={"type": "object", "required": ["alias"], "properties": {"alias": {"type": "string"}, "directory": {"type": "string"}}},
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                host_service="opencode",
                required_permission="coding.execute",
                tags=["opencode", "coding", "session"],
            ),
            _opencode_start,
        ),
        (
            ToolDefinition(
                name="opencode_send",
                description="Send a natural-language coding prompt to an OpenCode session, starting it first if needed.",
                input_schema={"type": "object", "required": ["prompt"], "properties": {"alias": {"type": "string"}, "prompt": {"type": "string"}, "directory": {"type": "string"}}},
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                host_service="opencode",
                required_permission="coding.execute",
                tags=["opencode", "coding", "agent"],
            ),
            _opencode_send,
        ),
        (
            ToolDefinition(
                name="opencode_shell",
                description="Run a shell command through an existing OpenCode session and return structured tool output.",
                input_schema={"type": "object", "required": ["alias", "command"], "properties": {"alias": {"type": "string"}, "command": {"type": "string"}}},
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                host_service="opencode",
                required_permission="coding.execute",
                tags=["opencode", "coding", "shell"],
            ),
            _opencode_shell,
        ),
        (
            ToolDefinition(
                name="opencode_status",
                description="Return OpenCode session state, working directory, and most recent tool action.",
                input_schema={"type": "object", "required": ["alias"], "properties": {"alias": {"type": "string"}}},
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.READ_ONLY,
                host_service="opencode",
                tags=["opencode", "coding", "status"],
            ),
            _opencode_status,
        ),
        (
            ToolDefinition(
                name="opencode_output",
                description="Return recent OpenCode messages and tool output for a session.",
                input_schema={"type": "object", "required": ["alias"], "properties": {"alias": {"type": "string"}, "limit": {"type": "integer"}}},
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.READ_ONLY,
                host_service="opencode",
                tags=["opencode", "coding", "output"],
            ),
            _opencode_output,
        ),
        (
            ToolDefinition(
                name="opencode_stop",
                description="Abort current work in an OpenCode session.",
                input_schema={"type": "object", "required": ["alias"], "properties": {"alias": {"type": "string"}}},
                output_schema={"type": "object", "properties": {}},
                risk_level=ToolRiskLevel.CONTROLLED_WRITE,
                host_service="opencode",
                required_permission="coding.execute",
                tags=["opencode", "coding", "stop"],
            ),
            _opencode_stop,
        ),
    ):
        if registry.get_tool(definition.name) is None:
            registry.register(definition, implementation)
