#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SESSION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
STATE_DIR = Path(
    os.environ.get(
        "OPENWEBUI_TERMINAL_BRIDGE_STATE_DIR",
        str(Path.home() / ".local/state/freyja/openwebui-terminal-bridge"),
    )
)
DEFAULT_MODEL = os.environ.get("FREYJA_GATEWAY_REMOTE_VULCAN_MODEL", "@preset/freyja-coder")
DEFAULT_BASE_URL = os.environ.get("FREYJA_GATEWAY_REMOTE_VULCAN_MODEL_BASE_URL", "http://100.94.80.21:3939/v1")
DEFAULT_TOKEN_FILE = Path(
    os.environ.get(
        "FREYJA_GATEWAY_REMOTE_NEXUS_TOKEN_FILE",
        str(Path.home() / ".local/state/freyja/gateway-remote/msty-nexus-token"),
    )
)
DEFAULT_QWEN_BIN = os.environ.get("FREYJA_GATEWAY_REMOTE_QWEN_BIN", "/opt/homebrew/bin/qwen")
TMUX_BIN = os.environ.get("OPENWEBUI_TERMINAL_BRIDGE_TMUX_BIN", "/opt/homebrew/bin/tmux")
DEFAULT_PATH = "/opt/homebrew/bin:/Users/freyja/.local/npm/bin:/Users/freyja/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def _run(argv: list[str], timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def _validate_session(name: str) -> str:
    if not SESSION_RE.fullmatch(name):
        raise SystemExit("session must contain only letters, numbers, dot, underscore, or dash, max 64 chars")
    return name


def _session_path(name: str) -> Path:
    return STATE_DIR / f"{name}.json"


def _tmux(*args: str, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    return _run([TMUX_BIN, *args], timeout=timeout)


def _session_exists(name: str) -> bool:
    return _tmux("has-session", "-t", name).returncode == 0


def _read_meta(name: str) -> dict[str, Any]:
    path = _session_path(name)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"metadata_error": "invalid_json"}
    return data if isinstance(data, dict) else {"metadata_error": "invalid_shape"}


def _write_meta(name: str, meta: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _session_path(name).write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _qwen_command() -> list[str]:
    token = DEFAULT_TOKEN_FILE.read_text(encoding="utf-8").strip() if DEFAULT_TOKEN_FILE.exists() else ""
    qwen_home = Path(
        os.environ.get(
            "FREYJA_GATEWAY_REMOTE_QWEN_HOME",
            str(Path.home() / ".local/state/freyja/gateway-remote/qwen-openwebui"),
        )
    )
    qwen_home.mkdir(parents=True, exist_ok=True)
    settings_path = qwen_home / "settings.json"
    settings = {
        "$version": 4,
        "general": {"enableAutoUpdate": False},
        "model": {"name": DEFAULT_MODEL, "baseUrl": DEFAULT_BASE_URL},
        "modelProviders": {
            "openai": [
                {
                    "id": DEFAULT_MODEL,
                    "name": "Vulcan Nexus",
                    "baseUrl": DEFAULT_BASE_URL,
                    "envKey": "OPENAI_API_KEY",
                    "generationConfig": {"contextWindowSize": 128000},
                    "models": [DEFAULT_MODEL],
                }
            ]
        },
        "security": {"auth": {"baseUrl": DEFAULT_BASE_URL, "selectedType": "openai"}},
        "ui": {"autoModeAcknowledged": True},
    }
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    exports = {
        "PATH": f"{DEFAULT_PATH}:{os.environ.get('PATH', '')}",
        "TERM": os.environ.get("TERM", "xterm-256color"),
        "QWEN_HOME": str(qwen_home),
        "OPENAI_BASE_URL": DEFAULT_BASE_URL,
        "OPENAI_API_KEY": token,
    }
    prefix = " ".join(f"{key}={shlex.quote(value)}" for key, value in exports.items())
    command = (
        "unset OPENROUTER_API_KEY ANTHROPIC_API_KEY GEMINI_API_KEY GOOGLE_API_KEY DASHSCOPE_API_KEY; "
        f"{prefix} {shlex.quote(DEFAULT_QWEN_BIN)} --model {shlex.quote(DEFAULT_MODEL)}; "
        "status=$?; printf '\\n[openwebui-terminal-bridge] qwen exited with status %s\\n' \"$status\"; exec /bin/zsh -f"
    )
    return ["/bin/zsh", "-lc", command]


def _agent_command(agent: str) -> list[str]:
    if agent == "qwen":
        return _qwen_command()
    if agent == "shell-test":
        return ["/bin/zsh", "-lc", "printf 'bridge shell-test ready\\n'; exec /bin/zsh -f"]
    raise SystemExit("unsupported agent; use qwen")


def start(args: argparse.Namespace) -> dict[str, Any]:
    name = _validate_session(args.session)
    workdir = Path(args.workdir).expanduser().resolve()
    if not workdir.is_dir():
        raise SystemExit(f"working directory does not exist: {workdir}")
    if _session_exists(name):
        meta = _read_meta(name)
        return {"ok": True, "status": "already_running", "session": name, **meta}
    command = _agent_command(args.agent)
    result = _tmux("new-session", "-d", "-s", name, "-c", str(workdir), *command)
    if result.returncode != 0:
        return {"ok": False, "status": "start_failed", "session": name, "stderr": result.stderr.strip()}
    meta = {
        "agent": args.agent,
        "workdir": str(workdir),
        "created_at_unix": int(time.time()),
        "model": DEFAULT_MODEL if args.agent == "qwen" else None,
        "base_url": DEFAULT_BASE_URL if args.agent == "qwen" else None,
    }
    _write_meta(name, meta)
    return {"ok": True, "status": "started", "session": name, **meta}


def status(args: argparse.Namespace) -> dict[str, Any]:
    name = _validate_session(args.session)
    running = _session_exists(name)
    meta = _read_meta(name)
    panes = _tmux("list-panes", "-t", name, "-F", "#{pane_current_command} #{pane_pid}", timeout=5) if running else None
    return {
        "ok": True,
        "status": "running" if running else "stopped",
        "session": name,
        "running": running,
        **meta,
        "pane": (panes.stdout.strip() if panes and panes.returncode == 0 else None),
    }


def send(args: argparse.Namespace) -> dict[str, Any]:
    name = _validate_session(args.session)
    if not _session_exists(name):
        return {"ok": False, "status": "not_running", "session": name}
    text = sys.stdin.read() if args.stdin else args.text
    if args.ctrl_c:
        result = _tmux("send-keys", "-t", name, "C-c")
    else:
        result = _tmux("send-keys", "-t", name, "-l", text)
        if result.returncode == 0 and args.enter:
            result = _tmux("send-keys", "-t", name, "Enter")
    return {"ok": result.returncode == 0, "status": "sent" if result.returncode == 0 else "send_failed", "session": name, "stderr": result.stderr.strip()}


def read(args: argparse.Namespace) -> dict[str, Any]:
    name = _validate_session(args.session)
    if not _session_exists(name):
        return {"ok": False, "status": "not_running", "session": name}
    lines = max(1, min(args.lines, 2000))
    result = _tmux("capture-pane", "-t", name, "-p", "-S", f"-{lines}")
    output = result.stdout
    max_chars = max(1000, min(args.max_chars, 50000))
    if len(output) > max_chars:
        output = output[-max_chars:]
    return {"ok": result.returncode == 0, "status": "read", "session": name, "output": output, "truncated_to_chars": max_chars if len(result.stdout) > len(output) else None}


def stop(args: argparse.Namespace) -> dict[str, Any]:
    name = _validate_session(args.session)
    if not _session_exists(name):
        _session_path(name).unlink(missing_ok=True)
        return {"ok": True, "status": "already_stopped", "session": name}
    _tmux("send-keys", "-t", name, "C-c", timeout=5)
    time.sleep(max(0.1, min(args.grace_seconds, 5.0)))
    if _session_exists(name):
        _tmux("kill-session", "-t", name, timeout=5)
    _session_path(name).unlink(missing_ok=True)
    return {"ok": not _session_exists(name), "status": "stopped", "session": name}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Constrained tmux bridge for OpenWebUI coding-agent terminals.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("start")
    p.add_argument("session")
    p.add_argument("--agent", default="qwen", choices=["qwen", "shell-test"])
    p.add_argument("--workdir", default=str(Path.home()))
    p.set_defaults(func=start)
    for command, func in (("status", status), ("read", read), ("stop", stop)):
        p = sub.add_parser(command)
        p.add_argument("session")
        if command == "read":
            p.add_argument("--lines", type=int, default=200)
            p.add_argument("--max-chars", type=int, default=20000)
        if command == "stop":
            p.add_argument("--grace-seconds", type=float, default=1.0)
        p.set_defaults(func=func)
    p = sub.add_parser("send")
    p.add_argument("session")
    p.add_argument("text", nargs="?", default="")
    p.add_argument("--stdin", action="store_true")
    p.add_argument("--enter", action="store_true")
    p.add_argument("--ctrl-c", action="store_true")
    p.set_defaults(func=send)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(json.dumps(args.func(args), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
