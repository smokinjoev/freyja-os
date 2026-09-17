#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MSTY_DB = Path.home() / "Library/Application Support/Msty Go/msty-go.db"
DEFAULT_CORE_URL = "http://127.0.0.1:8510"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that Msty Go Freyja is configured to route tools through Freyja Core.")
    parser.add_argument("--msty-db", type=Path, default=DEFAULT_MSTY_DB)
    parser.add_argument("--core-url", default=DEFAULT_CORE_URL)
    parser.add_argument("--since", default="", help="Optional ISO timestamp; report Msty tool events after this time.")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "msty_db": str(args.msty_db),
        "core_url": args.core_url.rstrip("/"),
        "core": check_core(args.core_url.rstrip("/")),
        "msty": inspect_msty_db(args.msty_db, since=args.since, core_url=args.core_url.rstrip("/")),
    }
    report["ok"] = bool(report["core"].get("ok") and report["msty"].get("configured"))
    has_live_core_message = bool(report["msty"].get("recent_core_tool_messages"))
    report["remaining_live_validation"] = (
        []
        if has_live_core_message
        else ["Ask the live Msty Go Freyja agent to call Freyja Core via its shell tool, then rerun with --since set before that chat."]
    )
    body = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(body + "\n", encoding="utf-8")
    print(body)
    return 0 if report["ok"] else 1


def check_core(base_url: str) -> dict[str, Any]:
    try:
        health = request_json(f"{base_url}/health")
        tools = request_json(f"{base_url}/tools")
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    tool_names = tools.get("tools") if isinstance(tools, dict) else []
    required = {
        "calendar.resolve_date",
        "calendar.create_event",
        "calendar.delete_event",
        "opencode.status",
        "opencode.send",
        "opencode.read",
    }
    missing = sorted(required - set(tool_names or []))
    return {
        "ok": bool(health.get("ok") and not missing),
        "health": health,
        "tool_count": len(tool_names or []),
        "missing_required_tools": missing,
    }


def inspect_msty_db(path: Path, *, since: str = "", core_url: str = DEFAULT_CORE_URL) -> dict[str, Any]:
    if not path.exists():
        return {"configured": False, "error": f"Msty Go database missing: {path}"}
    uri = f"file:{path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        bot = conn.execute(
            """
            SELECT id, name, model, shell_access_enabled, web_access_enabled,
                   search_lens_enabled, custom_instructions
            FROM bots
            WHERE id = 'freyja'
            """
        ).fetchone()
        if bot is None:
            return {"configured": False, "error": "Msty Go bot row 'freyja' not found"}
        instructions = str(bot["custom_instructions"] or "")
        events = recent_tool_events(conn, since=since)
        core_messages = recent_core_tool_messages(conn, since=since, core_url=core_url)
    finally:
        try:
            conn.close()
        except Exception:
            pass

    has_core_block = "Freyja Core tool gateway:" in instructions
    has_tools_call = "POST /tools/call" in instructions
    shell_enabled = int(bot["shell_access_enabled"] or 0) == 1
    return {
        "configured": bool(has_core_block and has_tools_call and shell_enabled),
        "bot": {
            "id": bot["id"],
            "name": bot["name"],
            "model": bot["model"],
            "shell_access_enabled": shell_enabled,
            "web_access_enabled": int(bot["web_access_enabled"] or 0) == 1,
            "search_lens_enabled": int(bot["search_lens_enabled"] or 0) == 1,
            "core_routing_block_present": has_core_block,
            "tools_call_instruction_present": has_tools_call,
        },
        "recent_core_tool_events": events,
        "recent_core_tool_messages": core_messages,
    }


def recent_tool_events(conn: sqlite3.Connection, *, since: str = "") -> list[dict[str, Any]]:
    clauses = ["tool_name = 'shell'"]
    params: list[Any] = []
    if since:
        clauses.append("created_at >= ?")
        params.append(since)
    rows = conn.execute(
        f"""
        SELECT id, tool_name, status, model, conversation_id, session_id, message_id, created_at
        FROM tool_call_usage_events
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at DESC
        LIMIT 10
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def recent_core_tool_messages(conn: sqlite3.Connection, *, since: str = "", core_url: str = DEFAULT_CORE_URL) -> list[dict[str, Any]]:
    host = core_url.replace("http://", "").replace("https://", "").rstrip("/")
    clauses = [
        "tool_calls LIKE '%/tools/call%'",
        "(tool_calls LIKE ? OR tool_calls LIKE '%127.0.0.1:8510%' OR tool_calls LIKE '%100.115.228.56:8510%')",
        "tool_calls LIKE '%\"status\":\"completed\"%'",
        "tool_calls LIKE '%\"isError\":false%'",
    ]
    params: list[Any] = [f"%{host}%"]
    if since:
        clauses.append("created_at >= ?")
        params.append(since)
    rows = conn.execute(
        f"""
        SELECT id, conversation_id, role, content, tool_calls, metadata, sequence, created_at
        FROM messages
        WHERE {' AND '.join(clauses)}
        ORDER BY created_at DESC
        LIMIT 10
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def request_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


if __name__ == "__main__":
    sys.exit(main())
