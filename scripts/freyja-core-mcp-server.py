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


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Starlette, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.url.path in {"/", "/healthz"}:
            return await call_next(request)
        if request.headers.get("authorization") != f"Bearer {self._token}":
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


async def _core(tool: str, arguments: dict[str, Any] | None = None) -> str:
    return _json(await call_tool(tool, arguments or {}))


mcp = MCPServer(
    "freyja-core",
    title="Freyja Core",
    description="MCP-compatible wrapper for Iris-owned Freyja Core tools.",
    instructions=(
        "This server is a protocol wrapper only. Freyja Core owns tool logic, policy, memory, "
        "Apple Calendar access, and OpenCode session control. Call the exposed tools rather than "
        "duplicating behavior in the client."
    ),
)


@mcp.tool(name="status.check", description="Report Freyja Core health, host, configured tools, and downstream reachability.")
async def status_check() -> str:
    return await _core("status.check")


@mcp.tool(name="calendar.resolve_date", description="Resolve a date phrase deterministically using Freyja Core.")
async def calendar_resolve_date(phrase: str, base_date: str = "") -> str:
    arguments: dict[str, Any] = {"phrase": phrase}
    if base_date:
        arguments["base_date"] = base_date
    return await _core("calendar.resolve_date", arguments)


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


def app() -> Starlette:
    starlette = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=False, host=DEFAULT_HOST)

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "ok": True,
                "service": "freyja-core-mcp",
                "transport": "streamable_http",
                "path": "/mcp",
                "core_tools": list(CORE_TOOL_NAMES),
            }
        )

    starlette.routes.append(Route("/healthz", healthz, methods=["GET"]))

    token = os.environ.get("FREYJA_CORE_MCP_TOKEN", "")
    if token:
        starlette.add_middleware(BearerAuthMiddleware, token=token)
    return starlette


if __name__ == "__main__":
    host = os.environ.get("FREYJA_CORE_MCP_HOST", DEFAULT_HOST)
    port = int(os.environ.get("FREYJA_CORE_MCP_PORT", str(DEFAULT_PORT)))
    uvicorn.run(app(), host=host, port=port, log_level=os.environ.get("LOG_LEVEL", "info").lower())
