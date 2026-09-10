#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import uvicorn
from mcp.server.mcpserver import MCPServer
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE = Path(os.environ.get("FREYJA_TERMINAL_BRIDGE", REPO_ROOT / "scripts" / "openwebui-terminal-bridge.py"))
DEFAULT_WORKDIR = os.environ.get("FREYJA_TERMINAL_DEFAULT_WORKDIR", str(REPO_ROOT))
DEFAULT_SESSION = os.environ.get("FREYJA_TERMINAL_DEFAULT_SESSION", "freyja-terminal-agent")
MAX_TEXT_CHARS = int(os.environ.get("FREYJA_TERMINAL_MAX_TEXT_CHARS", "20000"))
MAX_READ_LINES = int(os.environ.get("FREYJA_TERMINAL_MAX_READ_LINES", "2000"))
MAX_READ_CHARS = int(os.environ.get("FREYJA_TERMINAL_MAX_READ_CHARS", "50000"))


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Starlette, token: str) -> None:
        super().__init__(app)
        self._token = token

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        if request.url.path in {"/healthz", "/"}:
            return await call_next(request)
        expected = f"Bearer {self._token}"
        if request.headers.get("authorization") != expected:
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


def _bridge(args: list[str], *, stdin: str | None = None, timeout: int = 30) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(BRIDGE), *args],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    raw = (result.stdout or result.stderr).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"ok": False, "status": "invalid_bridge_json", "raw": raw[-4000:]}
    if result.returncode != 0:
        payload.setdefault("ok", False)
        payload.setdefault("status", "bridge_failed")
        payload["returncode"] = result.returncode
    return payload


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


mcp = MCPServer(
    "freyja-terminal",
    title="Freyja Terminal",
    description="Controlled tmux-backed terminal tools for Freyja coding-agent evaluation.",
    instructions=(
        "Use these tools to run a persistent Qwen coding-agent terminal in the designated workspace. "
        "Inspect files before editing, run tests after changes, read failures, fix them, rerun, and report commands."
    ),
)


@mcp.tool(description="Start a named Qwen or shell-test terminal session in an allowed working directory.")
def terminal_start(
    session: str = DEFAULT_SESSION,
    workdir: str = DEFAULT_WORKDIR,
    agent: str = "qwen",
) -> str:
    if agent not in {"qwen", "shell-test"}:
        return _json({"ok": False, "status": "unsupported_agent", "allowed": ["qwen", "shell-test"]})
    return _json(_bridge(["start", session, "--agent", agent, "--workdir", workdir], timeout=45))


@mcp.tool(description="Report whether a named terminal session is running.")
def terminal_status(session: str = DEFAULT_SESSION) -> str:
    return _json(_bridge(["status", session], timeout=15))


@mcp.tool(description="Send literal text to a named terminal session, optionally followed by Enter.")
def terminal_send(text: str, session: str = DEFAULT_SESSION, enter: bool = False) -> str:
    if len(text) > MAX_TEXT_CHARS:
        return _json({"ok": False, "status": "text_too_large", "max_chars": MAX_TEXT_CHARS})
    args = ["send", session, "--stdin"]
    if enter:
        args.append("--enter")
    return _json(_bridge(args, stdin=text, timeout=20))


@mcp.tool(description="Send Ctrl-C to a named terminal session.")
def terminal_ctrl_c(session: str = DEFAULT_SESSION) -> str:
    return _json(_bridge(["send", session, "--ctrl-c"], timeout=15))


@mcp.tool(description="Read recent output from a named terminal session.")
def terminal_read(session: str = DEFAULT_SESSION, lines: int = 200) -> str:
    bounded_lines = max(1, min(int(lines), MAX_READ_LINES))
    return _json(
        _bridge(
            ["read", session, "--lines", str(bounded_lines), "--max-chars", str(MAX_READ_CHARS)],
            timeout=20,
        )
    )


@mcp.tool(description="Interrupt and remove a named terminal session.")
def terminal_stop(session: str = DEFAULT_SESSION) -> str:
    return _json(_bridge(["stop", session], timeout=20))


def app() -> Starlette:
    starlette = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=False, host="127.0.0.1")

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True, "service": "freyja-terminal-mcp", "bridge": str(BRIDGE)})

    starlette.routes.append(Route("/healthz", healthz, methods=["GET"]))

    token = os.environ.get("FREYJA_TERMINAL_MCP_TOKEN", "")
    if token:
        starlette.add_middleware(BearerAuthMiddleware, token=token)
    return starlette


if __name__ == "__main__":
    host = os.environ.get("FREYJA_TERMINAL_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("FREYJA_TERMINAL_MCP_PORT", "8765"))
    uvicorn.run(app(), host=host, port=port, log_level=os.environ.get("LOG_LEVEL", "info").lower())
