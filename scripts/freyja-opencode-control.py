#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_URL = "http://127.0.0.1:4097"
DEFAULT_USERNAME = "freyja"
DEFAULT_PASSWORD_FILE = Path.home() / ".local" / "state" / "freyja" / "opencode" / "server-password"
STATE_FILE = Path.home() / ".local" / "state" / "freyja" / "opencode" / "controller-sessions.json"
MODEL = {"providerID": "vulcan-nexus", "modelID": "@preset/freyja-coder"}


def _password(password_file: str | None = None) -> str:
    configured = os.environ.get("OPENCODE_SERVER_PASSWORD")
    if configured:
        return configured
    return Path(password_file or DEFAULT_PASSWORD_FILE).expanduser().read_text(encoding="utf-8").strip()


def _request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    query: dict[str, str] | None = None,
    base_url: str | None = None,
    username: str | None = None,
    password_file: str | None = None,
) -> Any:
    base_url = (base_url or os.environ.get("FREYJA_OPENCODE_URL", DEFAULT_URL)).rstrip("/")
    if query:
        path = f"{path}?{urllib.parse.urlencode(query)}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(f"{base_url}{path}", data=data, method=method)
    username = username or os.environ.get("OPENCODE_SERVER_USERNAME") or DEFAULT_USERNAME
    request.add_header("authorization", "Basic " + base64.b64encode(f"{username}:{_password(password_file)}".encode()).decode())
    if body is not None:
        request.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"OpenCode API error {exc.code}: {detail}") from exc
    if not payload:
        return None
    return json.loads(payload)


def _load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def _save_state(state: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    STATE_FILE.chmod(0o600)


def _session(alias: str) -> dict[str, str]:
    state = _load_state()
    if alias.startswith("ses_"):
        return {"session": alias}
    if alias not in state:
        raise SystemExit(f"Unknown coder alias: {alias}")
    entry = state[alias]
    if isinstance(entry, str):
        return {"session": entry}
    if isinstance(entry, dict) and isinstance(entry.get("session"), str):
        result = {
            "session": entry["session"],
            "base_url": str(entry.get("base_url") or os.environ.get("FREYJA_OPENCODE_URL") or DEFAULT_URL),
            "username": str(entry.get("username") or os.environ.get("OPENCODE_SERVER_USERNAME") or DEFAULT_USERNAME),
        }
        if entry.get("password_file"):
            result["password_file"] = str(entry["password_file"])
        return result
    raise SystemExit(f"Invalid coder alias entry: {alias}")


def _recent_action(parts: list[dict[str, Any]]) -> dict[str, Any] | None:
    for part in reversed(parts):
        if part.get("type") == "tool":
            state = part.get("state") or {}
            return {
                "tool": part.get("tool"),
                "status": state.get("status"),
                "title": state.get("title"),
                "input": state.get("input"),
                "error": state.get("error"),
            }
    return None


def start(args: argparse.Namespace) -> None:
    query = {"directory": args.directory} if args.directory else None
    session = _request("POST", "/session", {"title": args.alias}, query=query)
    state = _load_state()
    state[args.alias] = {
        "base_url": os.environ.get("FREYJA_OPENCODE_URL", DEFAULT_URL),
        "session": session["id"],
        "username": os.environ.get("OPENCODE_SERVER_USERNAME", DEFAULT_USERNAME),
    }
    _save_state(state)
    print(json.dumps({"alias": args.alias, "session": session["id"], "working_directory": session.get("directory")}, indent=2))


def send(args: argparse.Namespace) -> None:
    session_config = _session(args.alias)
    session_id = session_config["session"]
    body = {
        "model": MODEL,
        "agent": "build",
        "parts": [{"type": "text", "text": args.prompt}],
    }
    result = _request("POST", f"/session/{session_id}/message", body, **_request_config(session_config))
    print(json.dumps(_summarize_message(session_id, result), indent=2))


def shell(args: argparse.Namespace) -> None:
    session_config = _session(args.alias)
    session_id = session_config["session"]
    result = _request(
        "POST",
        f"/session/{session_id}/shell",
        {"agent": "build", "model": MODEL, "command": args.command},
        **_request_config(session_config),
    )
    print(json.dumps(_summarize_message(session_id, result), indent=2))


def status(args: argparse.Namespace) -> None:
    session_config = _session(args.alias)
    session_id = session_config["session"]
    request_config = _request_config(session_config)
    statuses = _request("GET", "/session/status", **request_config)
    session = _request("GET", f"/session/{session_id}", **request_config)
    messages = _request("GET", f"/session/{session_id}/message", query={"limit": "1"}, **request_config)
    parts = messages[0].get("parts", []) if messages else []
    print(json.dumps({
        "alias": args.alias,
        "session": session_id,
        "working_directory": session.get("directory"),
        "state": statuses.get(session_id, "idle"),
        "recent_action": _recent_action(parts),
    }, indent=2))


def output(args: argparse.Namespace) -> None:
    session_config = _session(args.alias)
    session_id = session_config["session"]
    messages = _request("GET", f"/session/{session_id}/message", query={"limit": str(args.limit)}, **_request_config(session_config))
    print(json.dumps({"session": session_id, "messages": messages}, indent=2))


def stop(args: argparse.Namespace) -> None:
    session_config = _session(args.alias)
    session_id = session_config["session"]
    print(json.dumps({"session": session_id, "aborted": _request("POST", f"/session/{session_id}/abort", **_request_config(session_config))}, indent=2))


def resume(args: argparse.Namespace) -> None:
    session_config = _session(args.alias)
    print(json.dumps({"alias": args.alias, "session": session_config["session"], "base_url": session_config.get("base_url")}, indent=2))


def _request_config(session_config: dict[str, str]) -> dict[str, str]:
    return {key: session_config[key] for key in ("base_url", "username", "password_file") if key in session_config}


def _summarize_message(session_id: str, result: dict[str, Any]) -> dict[str, Any]:
    parts = result.get("parts", [])
    text = "\n".join(part.get("text", "") for part in parts if part.get("type") == "text").strip()
    action = _recent_action(parts)
    tool_output = ""
    if action and action["status"] == "completed":
        for part in reversed(parts):
            if part.get("type") == "tool":
                tool_output = ((part.get("state") or {}).get("output") or "").strip()
                break
    return {
        "session": session_id,
        "state": "completed" if (result.get("info") or {}).get("time", {}).get("completed") else "working",
        "message": (result.get("info") or {}).get("id"),
        "recent_action": action,
        "result": text or tool_output,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal Freyja controller for a local OpenCode server.")
    subparsers = parser.add_subparsers(required=True)
    start_parser = subparsers.add_parser("start")
    start_parser.add_argument("alias")
    start_parser.add_argument("--directory")
    start_parser.set_defaults(func=start)
    send_parser = subparsers.add_parser("send")
    send_parser.add_argument("alias")
    send_parser.add_argument("prompt")
    send_parser.set_defaults(func=send)
    shell_parser = subparsers.add_parser("shell")
    shell_parser.add_argument("alias")
    shell_parser.add_argument("command")
    shell_parser.set_defaults(func=shell)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("alias")
    status_parser.set_defaults(func=status)
    output_parser = subparsers.add_parser("output")
    output_parser.add_argument("alias")
    output_parser.add_argument("--limit", type=int, default=5)
    output_parser.set_defaults(func=output)
    stop_parser = subparsers.add_parser("stop")
    stop_parser.add_argument("alias")
    stop_parser.set_defaults(func=stop)
    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("alias")
    resume_parser.set_defaults(func=resume)
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
