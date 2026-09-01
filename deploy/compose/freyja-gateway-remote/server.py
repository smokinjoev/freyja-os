#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent / "app"
STATE_DIR = Path(os.environ.get("FREYJA_GATEWAY_REMOTE_STATE_DIR", Path.home() / ".local" / "state" / "freyja" / "gateway-remote"))
TOKEN_FILE = Path(os.environ.get("FREYJA_GATEWAY_REMOTE_TOKENS", STATE_DIR / "tokens.json"))
TRACE_FILE = Path(os.environ.get("FREYJA_GATEWAY_REMOTE_TRACE_LOG", STATE_DIR / "trace.jsonl"))
FREYJA_OPENAI_BASE_URL = os.environ.get("FREYJA_GATEWAY_REMOTE_OPENAI_BASE_URL", "http://127.0.0.1:8503/v1").rstrip("/")
FREYJA_UPSTREAM_TOKEN = os.environ.get("FREYJA_CONNECTOR_TOKEN", "")
PORT = int(os.environ.get("FREYJA_GATEWAY_REMOTE_PORT", "8010"))
HOST = os.environ.get("FREYJA_GATEWAY_REMOTE_HOST", "127.0.0.1")

PEOPLE = {
    "joe": {"display_name": "Joe"},
    "beth": {"display_name": "Beth"},
    "liam": {"display_name": "Liam"},
    "jenna": {"display_name": "Jenna"},
}

AGENTS = {
    "freyja": {"model": "agent/freyja", "label": "Freyja", "kind": "gateway-equivalent"},
    "benedict": {"model": "agent/benedict", "label": "Benedict", "kind": "gateway-equivalent"},
    "benedict-paralegal": {"model": "agent/benedict-paralegal", "label": "Benedict Paralegal", "kind": "gateway-equivalent-local-only"},
    "agent-44": {"model": "agent/agent-47", "label": "Agent 44", "kind": "gateway-equivalent"},
    "jenna": {"model": "agent/jennacide", "label": "Jenna", "kind": "gateway-equivalent"},
    "cloyd": {"model": "agent/cloyd-gibbler", "label": "Cloyd", "kind": "gateway-equivalent"},
}

ALLOWED_AGENTS = {
    "joe": {"freyja", "cloyd"},
    "beth": {"benedict"},
    "liam": {"agent-44"},
    "jenna": {"jenna"},
}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_tokens() -> dict[str, dict[str, str]]:
    if not TOKEN_FILE.exists():
        return {}
    data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _save_tokens(tokens: dict[str, dict[str, str]]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    TOKEN_FILE.chmod(0o600)


def ensure_tokens(*, rotate: set[str] | None = None) -> dict[str, str]:
    tokens = _load_tokens()
    issued: dict[str, str] = {}
    changed = False
    for person in PEOPLE:
        if person in tokens and tokens[person].get("sha256") and person not in (rotate or set()):
            continue
        raw = f"fr5_{person}_{secrets.token_urlsafe(32)}"
        tokens[person] = {"sha256": _sha256(raw), "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        issued[person] = raw
        changed = True
    if changed:
        _save_tokens(tokens)
    return issued


def authenticate(headers: Any) -> tuple[str, str] | None:
    auth = headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token_hash = _sha256(auth.removeprefix("Bearer ").strip())
    for person, record in _load_tokens().items():
        if hmac.compare_digest(token_hash, str(record.get("sha256") or "")):
            return person, PEOPLE.get(person, {}).get("display_name", person.title())
    return None


def append_trace(entry: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request_id": entry.get("request_id"),
        "status": entry.get("status"),
        "person": entry.get("person"),
        "agent": entry.get("agent"),
        "model": entry.get("model"),
        "http_status": entry.get("http_status"),
        "latency_ms": entry.get("latency_ms"),
        "trace_id": entry.get("trace_id"),
        "route": entry.get("route"),
        "endpoint": entry.get("endpoint"),
        "provider": entry.get("provider"),
        "egress_state": entry.get("egress_state"),
        "error": entry.get("error"),
    }
    with TRACE_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(safe, sort_keys=True) + "\n")
    TRACE_FILE.chmod(0o600)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._json(200, {"ok": True, "service": "freyja-gateway-remote", "bind": HOST, "agents": list(AGENTS)})
            return
        if path == "/status":
            self._require_auth()
            user = authenticate(self.headers)
            if not user:
                return
            self._json(
                200,
                {
                    "ok": True,
                    "user": user[0],
                    "agents": {key: AGENTS[key] for key in sorted(ALLOWED_AGENTS.get(user[0], set()))},
                    "msty_go_agents": "not-bridged",
                    "blocked_agents": {
                        "benedict-paralegal": "paralegal enclave requires an explicit enclave identity or policy grant"
                    },
                },
            )
            return
        self._serve_static()

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] == "/api/chat":
            self._chat()
            return
        self._json(404, {"error": "not found"})

    def _require_auth(self) -> bool:
        if authenticate(self.headers):
            return True
        self._json(401, {"error": "authentication required"})
        return False

    def _chat(self) -> None:
        user = authenticate(self.headers)
        if not user:
            self._json(401, {"error": "authentication required"})
            return
        length = int(self.headers.get("content-length", "0") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "invalid json"})
            return
        agent_key = str(payload.get("agent") or "")
        prompt = str(payload.get("message") or "").strip()
        agent = AGENTS.get(agent_key)
        if agent is None:
            self._json(400, {"error": "unknown agent"})
            return
        if agent_key not in ALLOWED_AGENTS.get(user[0], set()):
            append_trace(
                {
                    "request_id": f"remote-gateway-{uuid.uuid4()}",
                    "status": "denied",
                    "person": user[0],
                    "agent": agent_key,
                    "model": agent["model"],
                    "http_status": 403,
                    "error": "remote_agent_not_allowed",
                }
            )
            self._json(403, {"error": "agent is not allowed for this identity"})
            return
        if not prompt:
            self._json(400, {"error": "message is required"})
            return

        request_id = f"remote-gateway-{uuid.uuid4()}"
        body = {
            "model": agent["model"],
            "user": user[0],
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
        }
        start = time.monotonic()
        status = 502
        response_payload: dict[str, Any] = {}
        error: str | None = None
        try:
            request = urllib.request.Request(
                f"{FREYJA_OPENAI_BASE_URL}/chat/completions",
                data=json.dumps(body).encode("utf-8"),
                headers={
                    "content-type": "application/json",
                    "x-freyja-remote-request-id": request_id,
                    **({"authorization": f"Bearer {FREYJA_UPSTREAM_TOKEN}"} if FREYJA_UPSTREAM_TOKEN else {}),
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=180) as response:
                status = response.status
                response_payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            status = exc.code
            error = f"upstream_http_{exc.code}"
            try:
                response_payload = json.loads(exc.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                response_payload = {"error": error}
        except OSError:
            error = "upstream_unavailable"
            response_payload = {"error": "Freyja Gateway is unavailable."}

        latency_ms = int((time.monotonic() - start) * 1000)
        freyja_meta = response_payload.get("freyja") if isinstance(response_payload, dict) else {}
        append_trace(
            {
                "request_id": request_id,
                "status": "ok" if 200 <= status < 300 else "failed",
                "person": user[0],
                "agent": agent_key,
                "model": agent["model"],
                "http_status": status,
                "latency_ms": latency_ms,
                "trace_id": freyja_meta.get("trace_id") if isinstance(freyja_meta, dict) else None,
                "route": freyja_meta.get("route") if isinstance(freyja_meta, dict) else None,
                "endpoint": freyja_meta.get("endpoint") if isinstance(freyja_meta, dict) else None,
                "provider": freyja_meta.get("provider") if isinstance(freyja_meta, dict) else None,
                "egress_state": freyja_meta.get("egress_state") if isinstance(freyja_meta, dict) else None,
                "error": error,
            }
        )
        self._json(status, response_payload)

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
            ".json": "application/manifest+json",
        }.get(target.suffix, "application/octet-stream")
        self._send(200, {"content-type": content_type, "cache-control": "no-store"}, target.read_bytes())

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, {"content-type": "application/json"}, json.dumps(payload).encode("utf-8"))

    def _send(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        self.send_header("content-length", str(len(body)))
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        if args and str(args[0]).startswith("POST /api/chat"):
            return
        super().log_message(format, *args)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rotate-token":
        requested = set(sys.argv[2:] or PEOPLE)
        unknown = requested.difference(PEOPLE)
        if unknown:
            raise SystemExit(f"unknown people: {', '.join(sorted(unknown))}")
        issued_tokens = ensure_tokens(rotate=requested)
        print(json.dumps(issued_tokens, indent=2, sort_keys=True))
        raise SystemExit(0)

    issued_tokens = ensure_tokens()
    if issued_tokens:
        print("Generated initial one-time tokens. Store these securely; only hashes are retained:")
        for person, token in issued_tokens.items():
            print(f"{person}: {token}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
