#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_DB = Path("/app/backend/data/webui.db")
DEFAULT_SOURCE = Path(__file__).with_name("open_webui_performance_filter.py")
FUNCTION_ID = "freyja_local_performance_footer"
FUNCTION_NAME = "Freyja Local Performance Footer"


def _admin_user_id(con: sqlite3.Connection) -> str | None:
    row = con.execute("select id from user where role = 'admin' order by created_at limit 1").fetchone()
    if row:
        return str(row[0])
    row = con.execute("select id from user order by created_at limit 1").fetchone()
    return str(row[0]) if row else None


def upsert_filter(db: Path, source: Path, backup: bool = True) -> dict[str, object]:
    if not db.exists():
        raise FileNotFoundError(f"Open WebUI database not found: {db}")
    if not source.exists():
        raise FileNotFoundError(f"filter source not found: {source}")

    content = source.read_text(encoding="utf-8")
    now = int(time.time())
    backup_path = None
    if backup:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = db.with_name(f"{db.name}.backup-before-performance-filter-{stamp}")
        shutil.copy2(db, backup_path)

    con = sqlite3.connect(db)
    try:
        user_id = _admin_user_id(con)
        if not user_id:
            raise RuntimeError("no Open WebUI user found to own the filter")

        meta = json.dumps(
            {
                "description": "Appends local generation performance metrics after streamed model responses.",
                "manifest": {
                    "title": FUNCTION_NAME,
                    "version": "1.0.0",
                    "author": "Freyja OS",
                },
            },
            separators=(",", ":"),
        )
        valves = json.dumps({"priority": 1000, "show_estimated_tokens": True}, separators=(",", ":"))
        existing = con.execute("select created_at from function where id = ?", (FUNCTION_ID,)).fetchone()
        created_at = int(existing[0]) if existing else now

        con.execute(
            """
            insert into function (
                id, user_id, name, type, content, meta, valves, is_active,
                is_global, updated_at, created_at
            )
            values (?, ?, ?, 'filter', ?, ?, ?, 1, 1, ?, ?)
            on conflict(id) do update set
                user_id = excluded.user_id,
                name = excluded.name,
                type = excluded.type,
                content = excluded.content,
                meta = excluded.meta,
                valves = excluded.valves,
                is_active = 1,
                is_global = 1,
                updated_at = excluded.updated_at
            """,
            (FUNCTION_ID, user_id, FUNCTION_NAME, content, meta, valves, now, created_at),
        )
        con.commit()
    finally:
        con.close()

    return {
        "ok": True,
        "id": FUNCTION_ID,
        "name": FUNCTION_NAME,
        "db": str(db),
        "source": str(source),
        "backup": str(backup_path) if backup_path else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Install or update the Freyja Open WebUI performance footer filter.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    print(json.dumps(upsert_filter(args.db, args.source, backup=not args.no_backup), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
