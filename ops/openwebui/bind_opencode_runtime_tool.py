from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


JOE_USER_ID = "37fb033a-a2d0-46f2-986d-e22bf8355fa3"
TOOL_IDS = ("opencode_runtime", "cloyd_smith_loop")
MODEL_IDS = ("agent/freyja", "agent/cloyd-gibbler", "agent/freyja-coder")
CODING_MODEL_IDS = {"agent/freyja", "agent/cloyd-gibbler", "agent/freyja-coder"}
DEFAULT_DB = Path("/app/backend/data/webui.db")


def load_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bind OpenCode Runtime to the Open WebUI coding agents.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    return parser


def apply(conn: sqlite3.Connection, *, now: int | None = None) -> dict[str, Any]:
    timestamp = int(now or time.time())
    conn.row_factory = sqlite3.Row
    for tool_id in TOOL_IDS:
        conn.execute("update tool set user_id = ?, updated_at = ? where id = ?", (JOE_USER_ID, timestamp, tool_id))

    rows = []
    for model_id in MODEL_IDS:
        row = conn.execute("select id, meta, params from model where id = ?", (model_id,)).fetchone()
        if row is None:
            continue
        meta = load_json(row["meta"], {})
        params = load_json(row["params"], {})
        tool_ids = list(meta.get("toolIds") or [])
        if model_id in CODING_MODEL_IDS:
            for tool_id in TOOL_IDS:
                if tool_id not in tool_ids:
                    tool_ids.append(tool_id)
        if model_id not in CODING_MODEL_IDS:
            tool_ids = [tool_id for tool_id in tool_ids if tool_id not in TOOL_IDS]
        meta["toolIds"] = tool_ids
        capabilities = meta.setdefault("capabilities", {})
        capabilities["function_calling"] = True
        capabilities["tools"] = True
        system = str(params.get("system") or "")
        note = (
            "The OpenCode Runtime and Cloyd-Smith Loop tools are available. For coding, webpage/app building, "
            "repo changes, tests, development environment checks, ports, or Tailscale/OpenCode service work, use "
            "opencode_start, opencode_send, opencode_shell, opencode_status, opencode_output, opencode_stop, "
            "cloyd_smith_status, cloyd_smith_retry, cloyd_smith_mark_done, cloyd_smith_mark_blocked, "
            "cloyd_smith_follow_up, cloyd_smith_replace, or cloyd_smith_stop. Do not refuse these tasks as outside household scope "
            "when these tools are available."
        )
        if model_id in CODING_MODEL_IDS and note not in system:
            params["system"] = f"{system.strip()}\n\n{note}".strip()
        conn.execute(
            "update model set meta = ?, params = ?, updated_at = ? where id = ?",
            (json.dumps(meta), json.dumps(params), timestamp, model_id),
        )
        rows.append({"model": model_id, "toolIds": tool_ids})

    conn.commit()
    return {"ok": True, "tools": list(TOOL_IDS), "models": rows}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = sqlite3.connect(args.db)
    try:
        report = apply(conn)
    finally:
        conn.close()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
