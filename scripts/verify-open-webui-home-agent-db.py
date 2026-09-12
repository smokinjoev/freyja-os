#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path("/app/backend/data/webui.db")
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-home-agent-db-verification.json"

MODEL_IDS = [
    "agent/freyja",
    "agent/cloyd-gibbler",
    "agent/freyja-coder",
    "agent/benedict",
    "agent/agent-47",
    "agent/jennacide",
]
KNOWLEDGE_IDS = ["freyja_household", "freyja_projects", "benedict_restricted"]
TOOL_IDS = ["freyja_home_memory", "iris_apple", "home_assistant", "weather", "household_analysis", "infrastructure_health"]
MEMORY_IDS = [
    "freyja_native_memory_policy:beth",
    "freyja_native_memory_policy:jenna",
    "freyja_native_memory_policy:joe",
    "freyja_native_memory_policy:liam",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify sanitized Freyja home-agent rows in an Open WebUI database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("select name from sqlite_master where type='table' and name=?", (table,)).fetchone() is not None


def _count(conn: sqlite3.Connection, table: str) -> int | None:
    if not _table_exists(conn, table):
        return None
    quoted = '"' + table.replace('"', '""') + '"'
    return int(conn.execute(f"select count(*) from {quoted}").fetchone()[0])


def _present(conn: sqlite3.Connection, table: str, ids: list[str]) -> dict[str, bool]:
    if not _table_exists(conn, table):
        return {item_id: False for item_id in ids}
    quoted = '"' + table.replace('"', '""') + '"'
    return {item_id: bool(conn.execute(f"select 1 from {quoted} where id=?", (item_id,)).fetchone()) for item_id in ids}


def _json_type(raw: str | None) -> str:
    try:
        return type(json.loads(raw or "null")).__name__
    except Exception:
        return "invalid_json"


def verify(db: Path) -> dict[str, Any]:
    generated_at = int(time.time())
    if not db.exists():
        return {
            "report_type": "open-webui-home-agent-db-verification",
            "generated_at_unix": generated_at,
            "git_head": _git_head(),
            "db": str(db),
            "secrets_included": False,
            "private_content_included": False,
            "ok": False,
            "reason": "Open WebUI database is not available at the requested path",
        }
    conn = sqlite3.connect(db)
    try:
        model_present = _present(conn, "model", MODEL_IDS)
        knowledge_present = _present(conn, "knowledge", KNOWLEDGE_IDS)
        tool_present = _present(conn, "tool", TOOL_IDS)
        memory_present = _present(conn, "memory", MEMORY_IDS)
        tool_spec_types = {
            tool_id: _json_type(row[0]) if row else "missing"
            for tool_id in TOOL_IDS
            for row in [conn.execute("select specs from tool where id=?", (tool_id,)).fetchone()]
        }
        counts = {table: _count(conn, table) for table in ["user", "auth", "api_key", "model", "knowledge", "tool", "memory"]}
        config = {}
        if _table_exists(conn, "config"):
            for key in ["auth.enable_api_keys", "features.api_keys"]:
                row = conn.execute("select value from config where key=?", (key,)).fetchone()
                config[key] = None if row is None else row[0]
    finally:
        conn.close()
    ok = (
        all(model_present.values())
        and all(knowledge_present.values())
        and all(tool_present.values())
        and all(memory_present.values())
        and all(value == "list" for value in tool_spec_types.values())
        and config.get("auth.enable_api_keys") == "true"
    )
    return {
        "report_type": "open-webui-home-agent-db-verification",
        "generated_at_unix": generated_at,
        "git_head": _git_head(),
        "db": str(db),
        "secrets_included": False,
        "private_content_included": False,
        "ok": ok,
        "counts": counts,
        "config": config,
        "models_present": model_present,
        "knowledge_present": knowledge_present,
        "tools_present": tool_present,
        "memory_policies_present": memory_present,
        "tool_spec_types": tool_spec_types,
        "managed_tool_specs_are_lists": all(value == "list" for value in tool_spec_types.values()),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = verify(args.db)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
