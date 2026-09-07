#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent / "app"
FREYJA_OPENAI_BASE_URL = os.environ.get("FREYJA_OPENAI_BASE_URL", "http://host.docker.internal:8500/v1").rstrip("/")
FREYJA_API_KEY = os.environ.get("FREYJA_API_KEY", "")
PORT = int(os.environ.get("BETH_PORTAL_PORT", "8091"))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0].startswith("/v1/"):
            self._proxy()
            return
        self._serve_static()

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0].startswith("/v1/"):
            self._proxy()
            return
        self._send(404, {"content-type": "application/json"}, b'{"error":"not found"}')

    def _serve_static(self) -> None:
        path = self.path.split("?", 1)[0]
        relative = "index.html" if path in {"", "/"} else path.removeprefix("/")
        target = (APP_DIR / relative).resolve()
        if not str(target).startswith(str(APP_DIR.resolve())) or not target.is_file():
            target = APP_DIR / "index.html"
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
        }.get(target.suffix, "application/octet-stream")
        self._send(200, {"content-type": content_type, "cache-control": "no-store"}, target.read_bytes())

    def _proxy(self) -> None:
        length = int(self.headers.get("content-length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        path = self.path.removeprefix("/v1")
        headers = {"content-type": self.headers.get("content-type", "application/json")}
        if FREYJA_API_KEY:
            headers["authorization"] = f"Bearer {FREYJA_API_KEY}"
        request = urllib.request.Request(
            f"{FREYJA_OPENAI_BASE_URL}{path}",
            data=body or None,
            headers=headers,
            method=self.command,
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                self._send(response.status, dict(response.headers), response.read())
        except urllib.error.HTTPError as exc:
            self._send(exc.code, dict(exc.headers), exc.read())
        except OSError:
            self._send(
                502,
                {"content-type": "application/json"},
                json.dumps({"error": "Freyja endpoint is unavailable."}).encode("utf-8"),
            )

    def _send(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        self.send_header("content-length", str(len(body)))
        for key, value in headers.items():
            if key.lower() not in {"content-length", "connection", "transfer-encoding"}:
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
