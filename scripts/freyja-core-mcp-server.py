#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from typing import Any

import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from freyja.core import CORE_TOOL_NAMES, call_tool
from freyja.mcp_gateway import (
    discover_tools,
    dispatch_tool,
    profile,
    reset_current_agent,
    set_current_agent,
)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766


class MCPHostAliasMiddleware(BaseHTTPMiddleware):
    """Accept Docker Desktop's host alias without widening the MCP listener."""

    def __init__(self, app: Starlette, allowed_aliases: set[str]) -> None:
        super().__init__(app)
        self._allowed_aliases = {alias.lower() for alias in allowed_aliases}

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        host = request.headers.get("host", "").split(":", 1)[0].lower()
        if host in self._allowed_aliases:
            request.scope["headers"] = [
                (key, b"127.0.0.1:8766") if key.lower() == b"host" else (key, value)
                for key, value in request.scope.get("headers", [])
            ]
        return await call_next(request)


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Starlette, token: str, agent_tokens: dict[str, str] | None = None) -> None:
        super().__init__(app)
        self._token = token
        self._agent_tokens = agent_tokens or {}

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.url.path in {"/", "/healthz"}:
            return await call_next(request)
        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        supplied = authorization.removeprefix("Bearer ")
        if supplied == self._token:
            agent_id = "freyja"
        else:
            agent_id = self._agent_tokens.get(supplied, "")
        if not agent_id:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        context_token = set_current_agent(agent_id)
        try:
            return await call_next(request)
        finally:
            reset_current_agent(context_token)


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


async def _core(tool: str, arguments: dict[str, Any] | None = None) -> str:
    return _json(await dispatch_tool(tool, arguments or {}, call_tool))


mcp = MCPServer(
    "freyja-mcp-gateway",
    title="Freyja MCP Gateway",
    description="Policy-aware discovery and dispatch for Iris-owned tools.",
    instructions=(
        "This server is a protocol wrapper only. Freyja Core owns tool logic, policy, memory, "
        "Apple Calendar access, and OpenCode session control. Call the exposed tools rather than "
        "duplicating behavior in the client."
    ),
)

gateway_mcp = MCPServer(
    "freyja-mcp-gateway",
    title="Freyja MCP Gateway",
    description="Small discovery surface for a policy-controlled tool catalog.",
    instructions=(
        "Use tools.search to find a relevant capability, then tools.call to invoke it. "
        "Use tools.profile only when you need to inspect the current policy surface."
    ),
)


@gateway_mcp.tool(name="tools.search", description="Find tools available to the authenticated agent without loading the full catalog.")
async def tools_search(query: str = "", category: str = "", limit: int = 20) -> str:
    return _json(discover_tools(query=query, category=category, limit=limit))


@gateway_mcp.tool(name="tools.profile", description="Show the authenticated agent identity and its allowed tool names.")
async def tools_profile() -> str:
    return _json(profile())


@gateway_mcp.tool(name="tools.call", description="Call one discovered tool after enforcing the authenticated agent policy.")
async def tools_call(tool: str, arguments_json: str = "{}") -> str:
    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as exc:
        return _json({"ok": False, "error": f"arguments_json must be valid JSON: {exc.msg}"})
    if not isinstance(arguments, dict):
        return _json({"ok": False, "error": "arguments_json must encode a JSON object."})
    return _json(await dispatch_tool(tool, arguments, call_tool))


@mcp.tool(name="status.check", description="Report Freyja Core health, host, configured tools, and downstream reachability.")
async def status_check() -> str:
    return await _core("status.check")


@mcp.tool(name="calendar.resolve_date", description="Resolve a date phrase deterministically using Freyja Core.")
async def calendar_resolve_date(phrase: str, base_date: str = "") -> str:
    arguments: dict[str, Any] = {"phrase": phrase}
    if base_date:
        arguments["base_date"] = base_date
    return await _core("calendar.resolve_date", arguments)


@mcp.tool(name="calendar.list_events", description="List calendar events through Freyja Core.")
async def calendar_list_events(
    start: str = "",
    end: str = "",
    calendar_ids_json: str = "[]",
    member_ids_json: str = "[]",
    provider: str = "apple",
) -> str:
    try:
        calendar_ids = json.loads(calendar_ids_json or "[]")
        member_ids = json.loads(member_ids_json or "[]")
    except json.JSONDecodeError as exc:
        return _json({"ok": False, "error": f"calendar_ids_json/member_ids_json must be valid JSON: {exc.msg}"})
    return await _core(
        "calendar.list_events",
        {
            "start": start,
            "end": end,
            "calendar_ids": calendar_ids if isinstance(calendar_ids, list) else [],
            "member_ids": member_ids if isinstance(member_ids, list) else [],
            "provider": provider,
        },
    )


@mcp.tool(name="calendar.create_event", description="Create an Apple Calendar event through Freyja Core.")
async def calendar_create_event(
    title: str = "",
    calendar_id: str = "",
    start: str = "",
    end: str = "",
    description: str = "",
    location: str = "",
    provider: str = "apple",
) -> str:
    return await _core(
        "calendar.create_event",
        {
            "title": title,
            "calendar_id": calendar_id,
            "start": start,
            "end": end,
            "description": description,
            "location": location,
            "provider": provider,
        },
    )


@mcp.tool(name="calendar.delete_event", description="Delete a Freyja Core smoke event only with explicit approval.")
async def calendar_delete_event(
    event_id: str = "",
    approval: str = "",
    provider: str = "apple",
) -> str:
    return await _core(
        "calendar.delete_event",
        {
            "event_id": event_id,
            "approval": approval,
            "provider": provider,
        },
    )


@mcp.tool(name="opencode.start", description="Start the single Freyja Core OpenCode session.")
async def opencode_start(alias: str = "freyja-core-coder", directory: str = "") -> str:
    arguments: dict[str, Any] = {"alias": alias}
    if directory:
        arguments["directory"] = directory
    return await _core("opencode.start", arguments)


@mcp.tool(name="opencode.stop", description="Stop the single Freyja Core OpenCode session.")
async def opencode_stop(alias: str = "freyja-core-coder") -> str:
    return await _core("opencode.stop", {"alias": alias})


@mcp.tool(name="opencode.status", description="Report the Freyja Core OpenCode session state.")
async def opencode_status(alias: str = "freyja-core-coder") -> str:
    return await _core("opencode.status", {"alias": alias})


@mcp.tool(name="opencode.send", description="Send a prompt to the Freyja Core OpenCode session.")
async def opencode_send(alias: str = "freyja-core-coder", prompt: str = "", timeout_seconds: int = 120) -> str:
    return await _core(
        "opencode.send",
        {
            "alias": alias,
            "prompt": prompt,
            "timeout_seconds": timeout_seconds,
        },
    )


@mcp.tool(name="opencode.read", description="Read recent output from the Freyja Core OpenCode session.")
async def opencode_read(alias: str = "freyja-core-coder", limit: int = 20) -> str:
    return await _core("opencode.read", {"alias": alias, "limit": limit})


@mcp.tool(name="memory.search", description="Search Freyja Core local memory.")
async def memory_search(query: str = "", limit: int = 10) -> str:
    return await _core("memory.search", {"query": query, "limit": limit})


@mcp.tool(name="memory.write", description="Write a minimal local Freyja Core memory record.")
async def memory_write(memory_id: str = "", content: str = "", kind: str = "note") -> str:
    return await _core(
        "memory.write",
        {
            "memory_id": memory_id,
            "content": content,
            "kind": kind,
        },
    )


@mcp.tool(name="home_assistant.read_state", description="Read one Home Assistant entity through Freyja Core.")
async def home_assistant_read_state(entity_id: str = "", area: str = "", domain: str = "light") -> str:
    return await _core(
        "home_assistant.read_state",
        {
            "entity_id": entity_id,
            "area": area,
            "domain": domain,
        },
    )


@mcp.tool(name="home_assistant.list_states", description="List Home Assistant states through Freyja Core.")
async def home_assistant_list_states(domain: str = "", include_all: bool = False) -> str:
    arguments: dict[str, Any] = {"include_all": include_all}
    if domain:
        arguments["domain"] = domain
    return await _core("home_assistant.list_states", arguments)


def app() -> Starlette:
    configured_host = os.environ.get("FREYJA_CORE_MCP_HOST", DEFAULT_HOST)
    starlette = gateway_mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=False, host=configured_host)
    aliases = {
        value.strip()
        for value in os.environ.get("FREYJA_CORE_MCP_HOST_ALIASES", "host.docker.internal").split(",")
        if value.strip()
    }
    if aliases:
        starlette.add_middleware(MCPHostAliasMiddleware, allowed_aliases=aliases)

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "service": "freyja-core-mcp",
                "gateway": "freyja-mcp-gateway",
                "transport": "streamable_http",
                "path": "/mcp",
                "core_tools": list(CORE_TOOL_NAMES),
                "agent_id_supported": ["freyja", "freyja-test"],
                "discovery_tools": ["tools.search", "tools.profile", "tools.call"],
            }
        )

    starlette.routes.append(Route("/healthz", healthz, methods=["GET"]))

    token = os.environ.get("FREYJA_CORE_MCP_TOKEN", "")
    raw_agent_tokens = os.environ.get("FREYJA_MCP_AGENT_TOKENS_JSON", "{}")
    try:
        parsed_agent_tokens = json.loads(raw_agent_tokens)
    except json.JSONDecodeError:
        parsed_agent_tokens = {}
    agent_tokens = {
        str(agent_token): str(agent_id)
        for agent_token, agent_id in parsed_agent_tokens.items()
        if isinstance(agent_token, str) and isinstance(agent_id, str)
    } if isinstance(parsed_agent_tokens, dict) else {}
    if token or agent_tokens:
        starlette.add_middleware(BearerAuthMiddleware, token=token, agent_tokens=agent_tokens)
    return starlette


if __name__ == "__main__":
    host = os.environ.get("FREYJA_CORE_MCP_HOST", DEFAULT_HOST)
    port = int(os.environ.get("FREYJA_CORE_MCP_PORT", str(DEFAULT_PORT)))
    uvicorn.run(app(), host=host, port=port, log_level=os.environ.get("LOG_LEVEL", "info").lower())
