#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import pty
import re
import secrets
import select
import fcntl
import shutil
import struct
import subprocess
import sys
import termios
import threading
import time
import tty
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


APP_DIR = Path(__file__).resolve().parent / "app"
REPO_ROOT = Path("/Users/freyja/freyja-os")
STATE_DIR = Path(os.environ.get("FREYJA_GATEWAY_REMOTE_STATE_DIR", Path.home() / ".local" / "state" / "freyja" / "gateway-remote"))
TOKEN_FILE = Path(os.environ.get("FREYJA_GATEWAY_REMOTE_TOKENS", STATE_DIR / "tokens.json"))
TRACE_FILE = Path(os.environ.get("FREYJA_GATEWAY_REMOTE_TRACE_LOG", STATE_DIR / "trace.jsonl"))
PORT = int(os.environ.get("FREYJA_GATEWAY_REMOTE_PORT", "8010"))
HOST = os.environ.get("FREYJA_GATEWAY_REMOTE_HOST", "127.0.0.1")
QWEN_BIN = os.environ.get("FREYJA_GATEWAY_REMOTE_QWEN_BIN") or shutil.which("qwen") or "/opt/homebrew/bin/qwen"
VULCAN_MODEL_BASE_URL = os.environ.get("FREYJA_GATEWAY_REMOTE_VULCAN_MODEL_BASE_URL", "http://100.94.80.21:3939/v1").rstrip("/")
VULCAN_MODEL = os.environ.get("FREYJA_GATEWAY_REMOTE_VULCAN_MODEL", "@preset/freyja-coder")
SMITH_QWEN_HOME = Path(os.environ.get("FREYJA_GATEWAY_REMOTE_QWEN_HOME", STATE_DIR / "qwen-smith"))
NEXUS_TOKEN_FILE = Path(os.environ.get("FREYJA_GATEWAY_REMOTE_NEXUS_TOKEN_FILE", STATE_DIR / "msty-nexus-token"))
ALLOWED_REPOS = tuple(Path(item).expanduser().resolve() for item in os.environ.get("FREYJA_GATEWAY_REMOTE_ALLOWED_REPOS", str(REPO_ROOT)).split(":") if item)
ALLOWED_ROOTS = tuple(Path(item).expanduser().resolve() for item in os.environ.get("FREYJA_GATEWAY_REMOTE_ALLOWED_ROOTS", "/Users/freyja").split(":") if item)

PEOPLE = {
    "joe": {"display_name": "Joe"},
    "beth": {"display_name": "Beth"},
    "liam": {"display_name": "Liam"},
    "jenna": {"display_name": "Jenna"},
}

SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(token|password|secret|api[_-]?key)(\s*[:=]\s*)\S+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]


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


def authenticate_value(raw_token: str) -> tuple[str, str] | None:
    token_hash = _sha256(raw_token.strip())
    for person, record in _load_tokens().items():
        if hmac.compare_digest(token_hash, str(record.get("sha256") or "")):
            return person, PEOPLE.get(person, {}).get("display_name", person.title())
    return None


def authenticate(headers: Any) -> tuple[str, str] | None:
    auth = headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    return authenticate_value(auth.removeprefix("Bearer "))


def sanitize_text(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        def replacement(match: re.Match[str]) -> str:
            if match.lastindex == 1:
                return f"{match.group(1)}[redacted]"
            if match.lastindex == 2:
                return f"{match.group(1)}{match.group(2)}[redacted]"
            return "[redacted]"

        redacted = pattern.sub(replacement, redacted)
    return redacted


def append_trace(entry: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "event": entry.get("event"),
        "person": entry.get("person"),
        "repo": entry.get("repo"),
        "error": entry.get("error"),
    }
    with TRACE_FILE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(safe, sort_keys=True) + "\n")
    TRACE_FILE.chmod(0o600)


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def allowed_repo(repo: str, *, create: bool = False) -> Path:
    if not repo.strip():
        raise ValueError("folder is required")
    requested = Path(repo).expanduser().resolve()
    allowed = any(requested == path for path in ALLOWED_REPOS) or any(requested == root or is_relative_to(requested, root) for root in ALLOWED_ROOTS)
    if not allowed:
        raise ValueError("folder is outside allowed workspace roots")
    if requested.exists() and requested.is_dir():
        return requested
    if create:
        requested.mkdir(parents=True, exist_ok=True)
        return requested
    raise ValueError("folder does not exist; enable create folder first")


def repo_choices() -> list[str]:
    choices = {str(repo) for repo in ALLOWED_REPOS}
    for root in ALLOWED_ROOTS:
        if not root.exists():
            continue
        for child in root.iterdir():
            if child.name.startswith(".") or not child.is_dir():
                continue
            if (child / ".git").exists() or (child / "pyproject.toml").exists() or (child / "package.json").exists():
                choices.add(str(child.resolve()))
    return sorted(choices)


def qwen_available() -> bool:
    return bool(shutil.which(QWEN_BIN) or Path(QWEN_BIN).exists())


def terminal_env() -> dict[str, str]:
    keep = {
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "PATH",
        "SHELL",
        "TERM",
        "TMPDIR",
        "USER",
    }
    ensure_smith_qwen_home()
    env = {key: value for key, value in os.environ.items() if key in keep}
    env["OPENAI_BASE_URL"] = VULCAN_MODEL_BASE_URL
    token = read_nexus_token()
    if token:
        env["OPENAI_API_KEY"] = token
    else:
        env.setdefault("OPENAI_API_KEY", "missing-nexus-token")
    env["QWEN_HOME"] = str(SMITH_QWEN_HOME)
    path_parts = [
        "/opt/homebrew/bin",
        "/Users/freyja/.local/npm/bin",
        "/Users/freyja/.local/bin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]
    if env.get("PATH"):
        path_parts.extend(env["PATH"].split(":"))
    env["PATH"] = ":".join(dict.fromkeys(path_parts))
    env.setdefault("TERM", "xterm-256color")
    return env


def read_nexus_token() -> str | None:
    try:
        token = NEXUS_TOKEN_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return token or None


def ensure_smith_qwen_home() -> None:
    SMITH_QWEN_HOME.mkdir(parents=True, exist_ok=True)
    settings = {
        "$version": 4,
        "model": {
            "name": VULCAN_MODEL,
            "baseUrl": VULCAN_MODEL_BASE_URL,
        },
        "modelProviders": {
            "openai": [
                {
                    "id": VULCAN_MODEL,
                    "name": f"[Vulcan Nexus] {VULCAN_MODEL}",
                    "baseUrl": VULCAN_MODEL_BASE_URL,
                    "envKey": "OPENAI_API_KEY",
                    "generationConfig": {
                        "contextWindowSize": 128000,
                    },
                }
            ]
        },
        "security": {
            "auth": {
                "selectedType": "openai",
                "baseUrl": VULCAN_MODEL_BASE_URL,
            }
        },
        "ui": {
            "autoModeAcknowledged": True,
        },
    }
    settings_path = SMITH_QWEN_HOME / "settings.json"
    settings_path.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    settings_path.chmod(0o600)


def qwen_command() -> list[str]:
    return [QWEN_BIN, "--model", VULCAN_MODEL]


def nexus_config_status() -> dict[str, Any]:
    return {
        "base_url": VULCAN_MODEL_BASE_URL.removesuffix("/v1"),
        "openai_base_url": VULCAN_MODEL_BASE_URL,
        "model": VULCAN_MODEL,
        "token_file": str(NEXUS_TOKEN_FILE),
        "token_present": read_nexus_token() is not None,
    }


def _read_ws_frame(sock: Any) -> str | None:
    header = sock.recv(2)
    if not header:
        return None
    first, second = header
    opcode = first & 0x0F
    if opcode == 8:
        return None
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", sock.recv(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", sock.recv(8))[0]
    mask = sock.recv(4) if masked else b""
    payload = b""
    while len(payload) < length:
        chunk = sock.recv(length - len(payload))
        if not chunk:
            return None
        payload += chunk
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return payload.decode("utf-8", errors="replace")


def _send_ws_text(sock: Any, text: str) -> None:
    payload = text.encode("utf-8", errors="replace")
    header = bytearray([0x81])
    if len(payload) < 126:
        header.append(len(payload))
    elif len(payload) < 65536:
        header.extend([126, *struct.pack("!H", len(payload))])
    else:
        header.extend([127, *struct.pack("!Q", len(payload))])
    sock.sendall(bytes(header) + payload)


def _run_qwen_terminal(sock: Any, repo: Path, person: str) -> None:
    if not qwen_available():
        _send_ws_text(sock, f"Qwen is unavailable at {QWEN_BIN}\r\n")
        return
    append_trace({"event": "terminal_started", "person": person, "repo": str(repo)})
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(repo)
        os.execvpe(qwen_command()[0], qwen_command(), terminal_env())
    try:
        tty.setraw(fd, termios.TCSANOW)
    except termios.error:
        pass
    try:
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 34, 120, 0, 0))
    except OSError:
        pass

    def pty_to_ws() -> None:
        try:
            while True:
                ready, _, _ = select.select([fd], [], [], 0.25)
                if fd not in ready:
                    continue
                data = os.read(fd, 4096)
                if not data:
                    break
                _send_ws_text(sock, data.decode("utf-8", errors="replace"))
        except OSError:
            pass

    thread = threading.Thread(target=pty_to_ws, daemon=True)
    thread.start()
    try:
        while True:
            message = _read_ws_frame(sock)
            if message is None:
                break
            os.write(fd, message.encode("utf-8", errors="replace"))
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        append_trace({"event": "terminal_closed", "person": person, "repo": str(repo)})


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"ok": True, "service": "agent-smith-terminal", "bind": HOST, "qwen_available": qwen_available(), "model_backend": "vulcan", "nexus": nexus_config_status()})
            return
        if parsed.path == "/status":
            user = self._authenticated_user()
            if not user:
                return
            self._json(200, {"ok": True, "user": user[0], "agent": "Agent Smith", "repos": repo_choices(), "allowed_roots": [str(root) for root in ALLOWED_ROOTS], "qwen_available": qwen_available(), "model_backend": "vulcan", "nexus": nexus_config_status()})
            return
        if parsed.path == "/terminal":
            self._terminal(parsed)
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/folder":
            self._create_folder()
            return
        self._json(404, {"error": "not found"})

    def _authenticated_user(self) -> tuple[str, str] | None:
        user = authenticate(self.headers)
        if not user:
            self._json(401, {"error": "authentication required"})
        return user

    def _create_folder(self) -> None:
        user = self._authenticated_user()
        if not user:
            return
        payload = self._read_json()
        if payload is None:
            return
        try:
            repo = allowed_repo(str(payload.get("repo") or ""), create=True)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        self._json(200, {"ok": True, "repo": str(repo)})

    def _terminal(self, parsed: Any) -> None:
        params = parse_qs(parsed.query)
        token = params.get("token", [""])[0]
        user = authenticate_value(token)
        if not user:
            self._json(401, {"error": "authentication required"})
            return
        try:
            repo = allowed_repo(params.get("repo", [""])[0])
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
            return
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self._json(400, {"error": "websocket required"})
            return
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()).decode("ascii")
        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        _run_qwen_terminal(self.connection, repo, user[0])

    def _read_json(self) -> dict[str, Any] | None:
        length = int(self.headers.get("content-length", "0") or "0")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "invalid json"})
            return None
        return payload if isinstance(payload, dict) else {}

    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.removeprefix("/")
        target = (APP_DIR / relative).resolve()
        if not str(target).startswith(str(APP_DIR.resolve())) or not target.is_file():
            target = APP_DIR / "index.html"
        content_type = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/manifest+json"}.get(target.suffix, "application/octet-stream")
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
        if args and str(args[0]).startswith("GET /terminal"):
            return
        super().log_message(format, *args)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "rotate-token":
        requested = set(sys.argv[2:] or PEOPLE)
        unknown = requested.difference(PEOPLE)
        if unknown:
            raise SystemExit(f"unknown people: {', '.join(sorted(unknown))}")
        print(json.dumps(ensure_tokens(rotate=requested), indent=2, sort_keys=True))
        raise SystemExit(0)

    issued_tokens = ensure_tokens()
    if issued_tokens:
        print("Generated initial one-time tokens. Store these securely; only hashes are retained:")
        for person, token in issued_tokens.items():
            print(f"{person}: {token}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
