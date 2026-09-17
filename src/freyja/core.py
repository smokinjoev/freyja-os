from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from freyja.config import settings
from freyja.calendar.service import parse_datetime
from freyja.macagent import MacAgentClient
from freyja.memory.models import MemoryPrincipal, PutSharedMemoryRequest
from freyja.memory.store import get_store
from freyja.tools.calendar import get_calendar_service
from freyja.tools.models import ToolExecutionRequest
from freyja.tools.opencode_runtime import (
    _opencode_output,
    _opencode_send,
    _opencode_start,
    _opencode_status,
    _opencode_stop,
)

logger = logging.getLogger(__name__)

DEFAULT_NEXUS_BASE_URL = "http://100.94.80.21:3939"
DEFAULT_CORE_MODEL = "@preset/freyja-fast-local"
DEFAULT_CORE_PORT = 8510
DEFAULT_TIMEZONE = "America/New_York"
CORE_TOOL_NAMES = (
    "status.check",
    "calendar.resolve_date",
    "calendar.create_event",
    "calendar.delete_event",
    "opencode.start",
    "opencode.stop",
    "opencode.status",
    "opencode.send",
    "opencode.read",
    "memory.search",
    "memory.write",
)


HOUSE: dict[str, dict[str, Any]] = {
    "iris": {
        "role": "Freyja Core host, Apple/body integrations, hot local diagnostics",
        "network_identities": {"tailscale": "100.115.228.56", "hostname": "iris", "ssh_user": "freyja"},
        "major_services": ["Freyja fallback service", "Ollama local helper", "Codex workspace"],
        "relationships": ["Calls Vulcan Nexus for inference", "Can inspect Atlas and Vulcan over Tailscale/SSH when available"],
    },
    "vulcan": {
        "role": "Primary local inference appliance",
        "network_identities": {"tailscale": "100.94.80.21", "hostname": "vulcan-1", "ssh_user": "joe"},
        "major_services": ["Msty Nexus on 3939", "Ollama on 11434", "OpenAI-compatible Ollama proxy on 8088/8090"],
        "relationships": ["Inference target for Freyja Core", "Serves Msty Go and Open WebUI through Nexus-compatible APIs"],
    },
    "atlas": {
        "role": "Always-on gateway/infrastructure host",
        "network_identities": {"tailscale": "100.119.235.114", "hostname": "atlas", "ssh_user": "joe"},
        "major_services": ["Open WebUI", "model proxy", "home-agent gateway"],
        "relationships": ["Open WebUI can route to Freyja Core", "Needs reachability to Vulcan Nexus"],
    },
    "hera": {
        "role": "Avatar, voice, presence, perception, and semantic publishing host",
        "network_identities": {"hostname": "hera"},
        "major_services": ["FLM/GPT-OSS adapter", "voice/presence services"],
        "relationships": ["Consumes Freyja semantic events", "Can use Core for reasoning when connected"],
    },
    "cloyd": {
        "role": "Joe's coding-focused family agent",
        "network_identities": {"agent_id": "cloyd-gibbler", "model": "agent/cloyd-gibbler"},
        "major_services": ["OpenCode/Qwen-style coding sessions", "repo investigation"],
        "relationships": ["Controlled through agent_control", "Uses Vulcan Nexus coder preset"],
    },
}

READ_ONLY_PREFIXES = (
    "cat",
    "curl",
    "date",
    "df",
    "dig",
    "du",
    "find",
    "free",
    "git diff",
    "git log",
    "git show",
    "git status",
    "head",
    "hostname",
    "ip ",
    "lsof",
    "ls",
    "netstat",
    "ping",
    "pgrep",
    "ps",
    "pwd",
    "rg",
    "sed",
    "ss",
    "systemctl --user status",
    "systemctl status",
    "tail",
    "tailscale",
    "test ",
    "top",
    "traceroute",
    "uname",
    "uptime",
    "wc",
    "whoami",
)

DANGEROUS_PATTERN = re.compile(
    r"(^|\s)(sudo|su|rm|mv|cp|chmod|chown|kill|pkill|reboot|shutdown|launchctl|systemctl\s+(restart|stop|disable|enable)|docker\s+(rm|stop|restart)|"
    r"podman\s+(rm|stop|restart)|dd|mkfs|diskutil)\b|[;&|`$()]|>\s*[^&]",
    re.IGNORECASE,
)


class ChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = None


class ChatRequest(BaseModel):
    model: str = Field(default="freyja-core")
    messages: list[ChatMessage]
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None


class CoreToolRequest(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


def create_app() -> FastAPI:
    app = FastAPI(title="Freyja Core", version="0.1.0")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "service": "freyja-core", "nexus_base_url": _nexus_base_url()}

    @app.get("/tools")
    async def list_core_tools() -> dict[str, Any]:
        return {"ok": True, "tools": list(CORE_TOOL_NAMES)}

    @app.post("/tools/call")
    async def call_core_tool(request: CoreToolRequest) -> dict[str, Any]:
        result = await call_tool(request.tool, request.arguments)
        if not result.get("ok", False):
            return result
        return result

    @app.get("/v1/models")
    async def models() -> dict[str, Any]:
        return {
            "object": "list",
            "data": [{"id": "freyja-core", "object": "model", "created": 0, "owned_by": "freyja-os"}],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(request: ChatRequest) -> dict[str, Any]:
        if request.stream:
            raise HTTPException(status_code=400, detail="Freyja Core v0.1 does not support streaming yet.")
        prompt = _last_user_message(request.messages)
        if not prompt:
            raise HTTPException(status_code=400, detail="At least one user message is required.")
        started = time.monotonic()
        trace = await run_core_loop(prompt)
        duration_ms = int((time.monotonic() - started) * 1000)
        content = trace["answer"]
        return {
            "id": f"chatcmpl-freyja-core-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": request.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "freyja": {"duration_ms": duration_ms, **trace},
        }

    return app


app = create_app()


async def call_tool(tool: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = arguments or {}
    try:
        if tool == "status.check":
            return await status_check()
        if tool == "calendar.resolve_date":
            return resolve_date_tool(arguments)
        if tool == "calendar.create_event":
            return await create_calendar_event_tool(arguments)
        if tool == "calendar.delete_event":
            return await delete_calendar_event_tool(arguments)
        if tool.startswith("opencode."):
            return await opencode_tool(tool, arguments)
        if tool == "memory.search":
            return memory_search_tool(arguments)
        if tool == "memory.write":
            return memory_write_tool(arguments)
        return {"ok": False, "error": f"Unknown Freyja Core tool: {tool}", "configured_tools": list(CORE_TOOL_NAMES)}
    except Exception as exc:
        logger.exception("Freyja Core tool failed: %s", tool)
        return {"ok": False, "tool": tool, "error": str(exc)}


async def status_check() -> dict[str, Any]:
    hostname = subprocess.run(["hostname"], text=True, capture_output=True, timeout=3).stdout.strip()
    checks = {
        "nexus": await _http_reachable(_nexus_base_url(), "/health"),
        "opencode": await _http_reachable(settings.opencode_base_url, "/session/status", auth="opencode"),
    }
    if settings.apple_calendar_enabled and settings.apple_calendar_backend.strip().lower() == "macagent":
        checks["macagent"] = (await MacAgentClient(timeout_seconds=settings.apple_calendar_timeout_seconds).health()).model_dump(mode="json")
    calendar_provider = settings.calendar_default_provider
    memory_path = str(Path(settings.memory_database_path).expanduser())
    return {
        "ok": True,
        "service": "freyja-core",
        "hostname": hostname,
        "time": _now_iso(),
        "timezone": DEFAULT_TIMEZONE,
        "configured_tools": list(CORE_TOOL_NAMES),
        "downstream": checks,
        "configuration": {
            "nexus_base_url": _nexus_base_url(),
            "opencode_base_url": settings.opencode_base_url,
            "calendar_provider": calendar_provider,
            "apple_calendar_enabled": settings.apple_calendar_enabled,
            "memory_database_path": memory_path,
        },
    }


def resolve_date_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    phrase = str(arguments.get("phrase") or "").strip()
    if not phrase:
        return {"ok": False, "error": "calendar.resolve_date requires phrase."}
    base = _base_date(arguments)
    resolved = _resolve_date_phrase(phrase, base)
    if resolved is None:
        return {"ok": False, "error": f"Unsupported date phrase: {phrase}"}
    return {"ok": True, "phrase": phrase, "base_date": base.isoformat(), **resolved}


async def create_calendar_event_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    missing = [name for name in ("title", "start", "end", "calendar_id") if not str(arguments.get(name) or "").strip()]
    if missing:
        return {"ok": False, "error": "calendar.create_event missing required field(s): " + ", ".join(missing)}
    start = parse_datetime(str(arguments["start"]))
    end = parse_datetime(str(arguments["end"]))
    if end <= start:
        return {"ok": False, "error": "calendar.create_event requires end after start."}
    event = await get_calendar_service().create_event(
        title=str(arguments["title"]).strip(),
        start=start,
        end=end,
        member_ids=arguments.get("member_ids"),
        calendar_id=str(arguments["calendar_id"]).strip(),
        provider_name=arguments.get("provider"),
        location=arguments.get("location"),
        description=arguments.get("description"),
    )
    return {"ok": True, "event": event.to_dict()}


async def delete_calendar_event_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    event_id = str(arguments.get("event_id") or "").strip()
    approval = str(arguments.get("approval") or "").strip()
    if not event_id:
        return {"ok": False, "error": "calendar.delete_event requires event_id."}
    if approval != "DELETE_FREYJA_CORE_SMOKE_EVENT":
        return {
            "ok": False,
            "error": "calendar.delete_event requires approval='DELETE_FREYJA_CORE_SMOKE_EVENT'.",
            "approval_required": True,
        }
    deleted = await get_calendar_service().delete_event(event_id=event_id, provider_name=arguments.get("provider"))
    return {"ok": True, "deleted": deleted, "event_id": event_id}


async def opencode_tool(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    action = tool.split(".", 1)[1]
    action_map = {"read": "output"}
    return await agent_control({"action": action_map.get(action, action), **arguments})


def memory_search_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    query = str(arguments.get("query") or "").strip().lower()
    limit = int(arguments.get("limit") or 10)
    memories = get_store().list_shared_memories(_memory_principal(arguments), limit=min(max(limit, 1), 50)).memories
    if query:
        memories = [memory for memory in memories if query in memory.content.lower() or query in memory.memory_id.lower()]
    return {"ok": True, "count": len(memories), "memories": [memory.model_dump(mode="json") for memory in memories[:limit]]}


def memory_write_tool(arguments: dict[str, Any]) -> dict[str, Any]:
    content = str(arguments.get("content") or "").strip()
    if not content:
        return {"ok": False, "error": "memory.write requires content."}
    memory_id = str(arguments.get("memory_id") or f"core-{uuid.uuid4()}").strip()
    request = PutSharedMemoryRequest(
        memory_id=memory_id,
        kind=arguments.get("kind") or "fact",
        content=content,
        source="freyja-core",
        confidence=float(arguments.get("confidence") or 1.0),
        sensitivity=arguments.get("sensitivity") or "private",
        metadata={"tool": "memory.write"},
    )
    memory = get_store().put_shared_memory(_memory_principal(arguments), request)
    return {"ok": True, "memory": memory.model_dump(mode="json")}


async def run_core_loop(prompt: str, *, max_iterations: int | None = None) -> dict[str, Any]:
    limit = max(1, min(max_iterations or int(os.environ.get("FREYJA_CORE_MAX_ITERATIONS", "4")), 8))
    observations: list[dict[str, Any]] = []
    for iteration in range(limit):
        call = choose_tool(prompt, observations)
        if call is None:
            break
        started = time.monotonic()
        result = await execute_tool(call)
        observations.append(
            {
                "iteration": iteration + 1,
                "tool": call.name,
                "arguments": call.arguments,
                "duration_ms": int((time.monotonic() - started) * 1000),
                "result": result,
            }
        )
        if result.get("terminal"):
            break
    answer = await synthesize_answer(prompt, observations)
    return {"iterations": len(observations), "observations": observations, "answer": answer}


def choose_tool(prompt: str, observations: list[dict[str, Any]]) -> ToolCall | None:
    text = prompt.lower()
    used = {item["tool"] for item in observations}
    if "start" in text and ("coding agent" in text or "opencode" in text or "qwen" in text):
        if "agent_control" not in used:
            return ToolCall("agent_control", {"action": "start", "alias": "freyja-core-coder", "directory": settings.repository_root})
        if len(observations) == 1:
            return ToolCall(
                "agent_control",
                {
                    "action": "send",
                    "alias": "freyja-core-coder",
                    "prompt": "Investigate this repository and report the current architecture, tests, and likely next repair target. Use read-only inspection first.",
                    "directory": settings.repository_root,
                },
            )
        return None
    if any(name in text for name in HOUSE) and "house_query" not in used:
        entity = next(name for name in HOUSE if name in text)
        return ToolCall("house_query", {"query": entity})
    if "atlas" in text and "vulcan" in text and not _used_terminal(observations, "ping"):
        return ToolCall("terminal", {"host": "atlas", "command": "ping -c 2 100.94.80.21"})
    if "network" in text:
        if not _used_terminal(observations, "tailscale"):
            return ToolCall("terminal", {"host": "iris", "command": "tailscale status"})
        if not _used_terminal(observations, "ping -c 2 100.94.80.21"):
            return ToolCall("terminal", {"host": "iris", "command": "ping -c 2 100.94.80.21"})
        return None
    if "vulcan" in text and not _used_terminal(observations, "curl"):
        return ToolCall("terminal", {"host": "iris", "command": "curl -fsS --max-time 5 http://100.94.80.21:3939/health"})
    if ("slow" in text or "freyja" in text) and not _used_terminal(observations, "top"):
        return ToolCall("terminal", {"host": "iris", "command": "top -l 1 -n 15 -stats pid,cpu,mem,command"})
    if ("slow" in text or "freyja" in text) and not _used_terminal(observations, "pgrep"):
        return ToolCall("terminal", {"host": "iris", "command": "pgrep -fl freyja"})
    return None


async def execute_tool(call: ToolCall) -> dict[str, Any]:
    if call.name == "house_query":
        return house_query(str(call.arguments.get("query", "")))
    if call.name == "terminal":
        return await terminal(str(call.arguments.get("host") or "iris"), str(call.arguments.get("command") or ""))
    if call.name == "agent_control":
        return await agent_control(call.arguments)
    return {"ok": False, "error": f"Unknown tool: {call.name}"}


def house_query(query: str) -> dict[str, Any]:
    normalized = query.lower()
    matches = {name: data for name, data in HOUSE.items() if name in normalized or normalized in name}
    if not matches:
        matches = HOUSE
    return {"ok": True, "matches": matches}


async def terminal(host: str, command: str) -> dict[str, Any]:
    command = command.strip()
    if not command:
        return {"ok": False, "error": "No command supplied."}
    if not _is_read_only_command(command):
        return {"ok": False, "approval_required": True, "error": "Command is not allowed without explicit approval."}
    argv = _terminal_argv(host, command)
    timeout = float(os.environ.get("FREYJA_CORE_TERMINAL_TIMEOUT_SECONDS", "12"))
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=settings.repository_root,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        return {"ok": False, "host": host, "command": command, "timeout": timeout, "error": "Command timed out."}
    except OSError as exc:
        return {"ok": False, "host": host, "command": command, "error": str(exc)}
    return {
        "ok": proc.returncode == 0,
        "host": host,
        "command": command,
        "returncode": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace")[-6000:],
        "stderr": stderr.decode("utf-8", errors="replace")[-3000:],
    }


async def agent_control(arguments: dict[str, Any]) -> dict[str, Any]:
    action = str(arguments.get("action") or "status").strip().lower()
    alias = str(arguments.get("alias") or "freyja-core-coder").strip()
    req = ToolExecutionRequest(tool_name=f"agent_control:{action}", arguments={**arguments, "alias": alias}, actor="freyja-core")
    old_timeout = os.environ.get("OPENCODE_REQUEST_TIMEOUT_SECONDS")
    os.environ["OPENCODE_REQUEST_TIMEOUT_SECONDS"] = os.environ.get("FREYJA_CORE_AGENT_TIMEOUT_SECONDS", "90")
    try:
        if action == "start":
            result = await _opencode_start(req)
        elif action in {"send", "input"}:
            result = await _opencode_send(req)
            if not result.get("ok") and "timed out" in str(result.get("error", "")).lower():
                status = await _opencode_status(
                    ToolExecutionRequest(
                        tool_name="agent_control:status",
                        arguments={"alias": alias},
                        actor="freyja-core",
                    )
                )
                result = {
                    "ok": True,
                    "accepted": True,
                    "state": "working",
                    "alias": alias,
                    "send_timed_out": True,
                    "detail": "Prompt was sent, but the coding agent did not finish before the Core timeout.",
                    "status": status,
                }
        elif action in {"check", "status"}:
            result = await _opencode_status(req)
        elif action == "output":
            result = await _opencode_output(req)
        elif action == "stop":
            result = await _opencode_stop(req)
        else:
            result = {"ok": False, "error": f"Unsupported agent_control action: {action}"}
    finally:
        if old_timeout is None:
            os.environ.pop("OPENCODE_REQUEST_TIMEOUT_SECONDS", None)
        else:
            os.environ["OPENCODE_REQUEST_TIMEOUT_SECONDS"] = old_timeout
    return result


async def synthesize_answer(prompt: str, observations: list[dict[str, Any]]) -> str:
    context = _compact_observations(observations)
    system = (
        "You are Freyja Core v0.1. Answer Joe directly. Use the observations as live evidence. "
        "Be concrete about what was checked, what failed, and the next safe action. "
        "Do not claim commands succeeded unless the observations show that. "
        "Do not mention tools, sessions, or commands that are not present in the observations."
    )
    try:
        answer = await nexus_chat(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Question: {prompt}\n\nObservations:\n{context}"},
            ]
        )
        if _answer_relevant(prompt, answer):
            return answer
        retry_answer = await nexus_chat(
            [
                {"role": "system", "content": system},
                {
                    "role": "user",
                    "content": (
                        "The previous draft was unrelated. Answer only this question using only these observations.\n\n"
                        f"Question: {prompt}\n\nObservations:\n{context}"
                    ),
                },
            ]
        )
        if _answer_relevant(prompt, retry_answer):
            return retry_answer
        return _fallback_answer(prompt, observations, "Nexus returned an unrelated answer twice.")
    except Exception as exc:  # pragma: no cover - defensive live fallback
        logger.warning("Nexus synthesis failed: %s", exc)
        return _fallback_answer(prompt, observations, str(exc))


async def nexus_chat(messages: list[dict[str, str]]) -> str:
    base_url = _nexus_base_url().rstrip("/")
    model = os.environ.get("FREYJA_CORE_NEXUS_MODEL", DEFAULT_CORE_MODEL)
    headers = {"content-type": "application/json"}
    token = _nexus_api_key()
    if token:
        headers["authorization"] = f"Bearer {token}"
    payload = {"model": model, "messages": messages, "stream": False, "temperature": 0.2}
    async with httpx.AsyncClient(timeout=float(os.environ.get("FREYJA_CORE_NEXUS_TIMEOUT_SECONDS", "90"))) as client:
        response = await client.post(f"{base_url}/v1/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    message = data.get("choices", [{}])[0].get("message", {})
    content = str(message.get("content") or message.get("reasoning") or "").strip()
    if not content:
        raise RuntimeError("Nexus returned empty content")
    return content


def _fallback_answer(prompt: str, observations: list[dict[str, Any]], error: str) -> str:
    lines = [f"I gathered {len(observations)} observation(s), but Nexus synthesis failed: {error}."]
    for item in observations:
        result = item.get("result", {})
        lines.append(f"- {item['tool']} {item.get('arguments', {})}: ok={result.get('ok')} {result.get('error', '')}".rstrip())
    return "\n".join(lines)


async def _http_reachable(base_url: str, path: str, *, auth: str | None = None) -> dict[str, Any]:
    timeout = float(os.environ.get("FREYJA_CORE_STATUS_TIMEOUT_SECONDS", "8"))
    if not base_url:
        return {"ok": False, "error": "base URL is not configured"}
    headers: dict[str, str] = {}
    if auth == "opencode":
        try:
            import base64

            credentials = f"{settings.opencode_username}:{Path(settings.opencode_password_file).expanduser().read_text(encoding='utf-8').strip()}"
            headers["authorization"] = "Basic " + base64.b64encode(credentials.encode("utf-8")).decode("ascii")
        except OSError as exc:
            return {"ok": False, "base_url": base_url, "error": f"OpenCode password file unavailable: {exc}"}
    try:
        async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
            response = await client.get(f"{base_url.rstrip('/')}{path}")
        return {"ok": response.status_code < 500, "base_url": base_url, "status_code": response.status_code, "timeout_seconds": timeout}
    except Exception as exc:
        return {"ok": False, "base_url": base_url, "timeout_seconds": timeout, "error": str(exc)}


def _base_date(arguments: dict[str, Any]) -> date:
    value = str(arguments.get("base_date") or "").strip()
    if value:
        return date.fromisoformat(value)
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).date()


def _resolve_date_phrase(phrase: str, base: date) -> dict[str, Any] | None:
    normalized = re.sub(r"\s+", " ", phrase.strip().lower())
    if normalized == "today":
        return _single_date(base, "today")
    if normalized == "tomorrow":
        return _single_date(base + timedelta(days=1), "tomorrow")
    if normalized in {"this weekend", "weekend"}:
        saturday = base + timedelta(days=(5 - base.weekday()) % 7)
        sunday = saturday + timedelta(days=1)
        return {"kind": "date_range", "label": "this weekend", "start_date": saturday.isoformat(), "end_date": sunday.isoformat(), "dates": [saturday.isoformat(), sunday.isoformat()]}
    if normalized == "next weekend":
        saturday = base + timedelta(days=((5 - base.weekday()) % 7) + 7)
        sunday = saturday + timedelta(days=1)
        return {"kind": "date_range", "label": "next weekend", "start_date": saturday.isoformat(), "end_date": sunday.isoformat(), "dates": [saturday.isoformat(), sunday.isoformat()]}
    match = re.fullmatch(r"(this|next)? ?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", normalized)
    if match:
        modifier = match.group(1) or "this"
        weekday = _weekday_number(match.group(2))
        days_ahead = (weekday - base.weekday()) % 7
        if modifier == "next":
            days_ahead = days_ahead + 7 if days_ahead == 0 else days_ahead
        return _single_date(base + timedelta(days=days_ahead), f"{modifier} {match.group(2)}")
    return None


def _single_date(value: date, label: str) -> dict[str, Any]:
    return {"kind": "date", "label": label, "date": value.isoformat(), "dates": [value.isoformat()]}


def _weekday_number(name: str) -> int:
    return ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"].index(name)


def _memory_principal(arguments: dict[str, Any]) -> MemoryPrincipal:
    return MemoryPrincipal(
        client_type=str(arguments.get("client_type") or "core"),
        client_subject=str(arguments.get("client_subject") or "agent:freyja"),
        account_owner=str(arguments.get("account_owner") or "person:joe"),
        conversation_id=str(arguments.get("conversation_id") or "freyja-core"),
    )


def _now_iso() -> str:
    return datetime.now(ZoneInfo(DEFAULT_TIMEZONE)).isoformat()


def _compact_observations(observations: list[dict[str, Any]]) -> str:
    compact = []
    for item in observations:
        result = item.get("result", {})
        compact.append(
            {
                "tool": item.get("tool"),
                "arguments": item.get("arguments"),
                "ok": result.get("ok"),
                "error": result.get("error"),
                "stdout": str(result.get("stdout") or "")[-2000:],
                "stderr": str(result.get("stderr") or "")[-800:],
                "matches": result.get("matches"),
                "state": result.get("state"),
                "session": result.get("session"),
                "working_directory": result.get("working_directory"),
            }
        )
    return json.dumps(compact, indent=2, sort_keys=True)


def _answer_relevant(prompt: str, answer: str) -> bool:
    lowered_prompt = prompt.lower()
    lowered_answer = answer.lower()
    if "slow" in lowered_prompt:
        return any(term in lowered_answer for term in ("cpu", "memory", "load", "process", "top", "pgrep"))
    if "coding agent" in lowered_prompt:
        return any(term in lowered_answer for term in ("agent", "opencode", "session", "repo", "repository"))
    if "atlas" in lowered_prompt and "vulcan" in lowered_prompt:
        return "atlas" in lowered_answer and "vulcan" in lowered_answer
    if "vulcan" in lowered_prompt:
        return "vulcan" in lowered_answer
    if "network" in lowered_prompt:
        return any(term in lowered_answer for term in ("network", "tailscale", "packet", "ping", "reach"))
    return True


def _last_user_message(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role != "user":
            continue
        if isinstance(message.content, str):
            return message.content.strip()
        if isinstance(message.content, list):
            return "\n".join(str(part.get("text", "")) for part in message.content if part.get("type") == "text").strip()
    return ""


def _used_terminal(observations: list[dict[str, Any]], command_fragment: str) -> bool:
    return any(
        item.get("tool") == "terminal" and command_fragment in str(item.get("arguments", {}).get("command", ""))
        for item in observations
    )


def _is_read_only_command(command: str) -> bool:
    lowered = command.strip().lower()
    if DANGEROUS_PATTERN.search(lowered):
        return False
    return any(lowered == prefix.strip() or lowered.startswith(prefix) for prefix in READ_ONLY_PREFIXES)


def _terminal_argv(host: str, command: str) -> list[str]:
    normalized_host = host.strip().lower()
    if normalized_host in {"", "iris", "localhost", "127.0.0.1"}:
        return shlex.split(command)
    identities = HOUSE.get(normalized_host, {}).get("network_identities", {})
    target = identities.get("tailscale") or normalized_host
    ssh_user = identities.get("ssh_user")
    if ssh_user and "@" not in str(target):
        target = f"{ssh_user}@{target}"
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", str(target), command]


def _nexus_base_url() -> str:
    return (os.environ.get("NEXUS_BASE_URL") or settings.nexus_base_url or DEFAULT_NEXUS_BASE_URL).rstrip("/")


def _nexus_api_key() -> str:
    token = os.environ.get("NEXUS_API_KEY") or settings.nexus_api_key
    if token:
        return token
    token_file = os.environ.get("NEXUS_API_KEY_FILE", "").strip()
    if not token_file:
        return ""
    path = Path(token_file).expanduser()
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        logger.warning("NEXUS_API_KEY_FILE is configured but could not be read: %s", path)
        return ""


def main() -> None:
    import uvicorn

    host = os.environ.get("FREYJA_CORE_HOST", "127.0.0.1")
    port = int(os.environ.get("FREYJA_CORE_PORT", str(DEFAULT_CORE_PORT)))
    uvicorn.run("freyja.core:app", host=host, port=port)


if __name__ == "__main__":  # pragma: no cover
    main()
