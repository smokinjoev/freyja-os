#!/usr/bin/env python3
"""Temporary local proxy for inspecting Msty Go OpenAI payload shape.

It redacts authorization and logs request metadata only: path, model, stream,
message count, tool count, and response finish reason/tool-call count.
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


TARGET = os.environ.get("MSTY_NEXUS_PROXY_TARGET", "http://100.94.80.21:3939").rstrip("/")
LOG_PATH = Path(os.environ.get("MSTY_NEXUS_PROXY_LOG", "logs/msty-nexus-debug-proxy.jsonl"))


def _safe_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"payload_type": type(payload).__name__}
    messages = payload.get("messages")
    tools = payload.get("tools")
    return {
        "model": payload.get("model"),
        "stream": payload.get("stream"),
        "message_count": len(messages) if isinstance(messages, list) else None,
        "tool_count": len(tools) if isinstance(tools, list) else 0,
        "tool_names": [
            tool.get("function", {}).get("name")
            for tool in tools[:20]
            if isinstance(tool, dict)
        ]
        if isinstance(tools, list)
        else [],
    }


def _response_summary(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {"response_type": type(payload).__name__}
    choices = payload.get("choices")
    first = choices[0] if isinstance(choices, list) and choices else {}
    message = first.get("message") if isinstance(first, dict) else {}
    tool_calls = message.get("tool_calls") if isinstance(message, dict) else None
    return {
        "response_model": payload.get("model"),
        "finish_reason": first.get("finish_reason") if isinstance(first, dict) else None,
        "response_tool_call_count": len(tool_calls) if isinstance(tool_calls, list) else 0,
    }


def _log(entry: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self._proxy()

    def do_POST(self) -> None:
        self._proxy()

    def _proxy(self) -> None:
        started = time.monotonic()
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
        parsed: Any = None
        if body:
            try:
                parsed = json.loads(body)
            except Exception:
                parsed = None
        headers = {k: v for k, v in self.headers.items() if k.lower() != "host"}
        req = urllib.request.Request(
            TARGET + self.path,
            data=body if body else None,
            headers=headers,
            method=self.command,
        )
        status = 502
        response_headers: dict[str, str] = {"Content-Type": "application/json"}
        response_body = b'{"error":"proxy failure"}'
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                status = resp.status
                response_headers = dict(resp.headers.items())
                response_body = resp.read()
        except urllib.error.HTTPError as exc:
            status = exc.code
            response_headers = dict(exc.headers.items())
            response_body = exc.read()
        finally:
            response_parsed: Any = None
            try:
                response_parsed = json.loads(response_body)
            except Exception:
                pass
            _log(
                {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "method": self.command,
                    "path": self.path,
                    "request": _safe_summary(parsed),
                    "response": _response_summary(response_parsed),
                    "status": status,
                    "latency_ms": int((time.monotonic() - started) * 1000),
                }
            )
        self.send_response(status)
        for key, value in response_headers.items():
            if key.lower() in {"content-length", "connection", "transfer-encoding"}:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> int:
    port = int(os.environ.get("MSTY_NEXUS_PROXY_PORT", "3941"))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"listening on http://127.0.0.1:{port}, forwarding to {TARGET}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
