#!/usr/bin/env python3
"""Manage a local Freyja 5 Gateway/WebGUI-compatible test service."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_PID_FILE = Path("/tmp/freyja5-gateway-8500.pid")
DEFAULT_LOG_FILE = Path("/tmp/freyja5-gateway-8500.log")
DEFAULT_TOKEN = "test-connector-token"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the local Freyja 5 Gateway test service.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8500)
    parser.add_argument("--pid-file", type=Path, default=DEFAULT_PID_FILE)
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG_FILE)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="Start the local service if it is not already healthy.")
    start.add_argument("--token", default=os.environ.get("FREYJA_CONNECTOR_TOKEN", DEFAULT_TOKEN))
    start.add_argument("--timeout", type=float, default=10.0)

    subparsers.add_parser("status", help="Print health and process status.")

    stop = subparsers.add_parser("stop", help="Stop the pid-file-owned service process.")
    stop.add_argument("--force", action="store_true", help="Also stop a matching listener on the requested port.")

    smoke = subparsers.add_parser("smoke", help="Run the Freyja 5 smoke script against the local service.")
    smoke.add_argument("--token", default=os.environ.get("FREYJA_CONNECTOR_TOKEN", DEFAULT_TOKEN))
    smoke.add_argument("--output", type=Path, default=Path("certification/reports/freyja5-smoke-local.json"))
    smoke.add_argument("--skip-media", action="store_true")
    return parser


def base_url(host: str, port: int) -> str:
    health_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{health_host}:{port}"


def command_start(args: argparse.Namespace) -> int:
    health = health_status(args.host, args.port)
    if health["healthy"]:
        _write_json({"status": "already-running", **health})
        return 0

    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    args.pid_file.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "FREYJA_CONNECTOR_TOKEN": args.token,
            "FREYJA5_OPENAI_LIVE_INFERENCE_ENABLED": "false",
            "CLOUD_ENABLED": "false",
        }
    )
    log = args.log_file.open("ab", buffering=0)
    process = subprocess.Popen(
        [
            str(VENV_PYTHON if VENV_PYTHON.exists() else sys.executable),
            "-m",
            "uvicorn",
            "freyja.main:app",
            "--host",
            args.host,
            "--port",
            str(args.port),
            "--log-level",
            "info",
        ],
        cwd=REPO_ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )
    args.pid_file.write_text(str(process.pid), encoding="utf-8")

    deadline = time.monotonic() + args.timeout
    last_health: dict[str, Any] = {"healthy": False}
    while time.monotonic() < deadline:
        last_health = health_status(args.host, args.port)
        if last_health["healthy"]:
            _write_json({"status": "started", "pid": process.pid, **last_health})
            return 0
        if process.poll() is not None:
            break
        time.sleep(0.25)

    _write_json(
        {
            "status": "failed",
            "pid": process.pid,
            "log_file": str(args.log_file),
            "health": last_health,
            "returncode": process.poll(),
        }
    )
    return 1


def command_status(args: argparse.Namespace) -> int:
    pid = read_pid(args.pid_file)
    listener = listener_pid(args.port)
    listener_owned_by_pid_file = bool(pid and listener == pid)
    report = {
        "status": "healthy" if health_status(args.host, args.port)["healthy"] else "not-healthy",
        "pid_file": str(args.pid_file),
        "pid": pid,
        "pid_running": bool(pid and process_running(pid)),
        "listener_pid": listener,
        "listener_owned_by_pid_file": listener_owned_by_pid_file,
        "health": health_status(args.host, args.port),
        "log_file": str(args.log_file),
    }
    _write_json(report)
    return 0 if report["status"] == "healthy" else 1


def command_stop(args: argparse.Namespace) -> int:
    pid = read_pid(args.pid_file)
    stopped = False
    if pid and process_running(pid):
        os.kill(pid, signal.SIGTERM)
        stopped = wait_for_exit(pid, timeout=5.0)
    if args.pid_file.exists():
        args.pid_file.unlink()

    if args.force and health_status(args.host, args.port)["healthy"]:
        listener = listener_pid(args.port)
        if listener and process_running(listener):
            os.kill(listener, signal.SIGTERM)
            stopped = wait_for_exit(listener, timeout=5.0) or stopped

    health = health_status(args.host, args.port)
    _write_json({"status": "stopped" if not health["healthy"] else "still-running", "stopped": stopped, "health": health})
    return 0 if not health["healthy"] else 1


def command_smoke(args: argparse.Namespace) -> int:
    cmd = [
        str(REPO_ROOT / "scripts" / "freyja5-smoke.py"),
        "--base-url",
        base_url(args.host, args.port),
        "--token",
        args.token,
        "--output",
        str(args.output),
    ]
    if args.skip_media:
        cmd.append("--skip-media")
    return subprocess.run(cmd, cwd=REPO_ROOT, check=False).returncode


def health_status(host: str, port: int) -> dict[str, Any]:
    url = f"{base_url(host, port)}/health"
    try:
        with urllib.request.urlopen(url, timeout=2.0) as response:
            body = response.read(2048).decode("utf-8", errors="replace")
            return {"healthy": response.status == 200, "url": url, "status_code": response.status, "body": body}
    except (OSError, urllib.error.URLError) as exc:
        return {"healthy": False, "url": url, "error": type(exc).__name__}


def read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def process_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def wait_for_exit(pid: int, *, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_running(pid):
            return True
        time.sleep(0.1)
    return False


def listener_pid(port: int) -> int | None:
    completed = subprocess.run(
        ["lsof", "-ti", f"TCP:{port}", "-sTCP:LISTEN"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    for line in completed.stdout.splitlines():
        try:
            return int(line.strip())
        except ValueError:
            continue
    return None


def _write_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "start":
        return command_start(args)
    if args.command == "status":
        return command_status(args)
    if args.command == "stop":
        return command_stop(args)
    if args.command == "smoke":
        return command_smoke(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
