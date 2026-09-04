#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("/app/backend/data/webui.db")
EXPECTED = {
    "agent/freyja": {"groups": {"beth", "joe"}, "name": "Freyja"},
    "agent/cloyd-gibbler": {"groups": {"joe"}, "name": "Cloyd"},
    "agent/benedict": {"groups": {"beth"}, "name": "Benedict"},
    "agent/agent-47": {"groups": {"beth", "joe", "liam"}, "name": "Agent 44"},
    "agent/jennacide": {"groups": {"beth", "jenna", "joe"}, "name": "Jenna"},
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja home-agent access metadata in an Open WebUI database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output", type=Path)
    return parser


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return conn.execute("select name from sqlite_master where type='table' and name=?", (table,)).fetchone() is not None


def _count_table(conn: sqlite3.Connection, table: str) -> int | None:
    if not _table_exists(conn, table):
        return None
    quoted = '"' + table.replace('"', '""') + '"'
    return int(conn.execute(f"select count(*) from {quoted}").fetchone()[0])


def _load_meta(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def audit(conn: sqlite3.Connection) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    rows = {
        str(row["id"]): row
        for row in conn.execute(
            "select id, name, base_model_id, meta, is_active from model where id in ({})".format(
                ",".join("?" for _ in EXPECTED)
            ),
            list(EXPECTED),
        ).fetchall()
    }

    checks: list[dict[str, Any]] = []
    missing = sorted(set(EXPECTED) - set(rows))
    for model_id, expected in EXPECTED.items():
        row = rows.get(model_id)
        if row is None:
            checks.append({"name": f"{model_id}:present", "ok": False, "evidence": {"missing": True}})
            continue
        meta = _load_meta(row["meta"])
        access = meta.get("access_control") if isinstance(meta.get("access_control"), dict) else {}
        read = access.get("read") if isinstance(access.get("read"), dict) else {}
        groups = set(read.get("group_ids") or [])
        checks.append(
            {
                "name": f"{model_id}:read_groups",
                "ok": groups == expected["groups"],
                "evidence": {"group_ids": sorted(groups), "expected": sorted(expected["groups"])},
            }
        )
        checks.append(
            {
                "name": f"{model_id}:active",
                "ok": bool(row["is_active"]),
                "evidence": {"is_active": bool(row["is_active"])},
            }
        )

    user_count = _count_table(conn, "user")
    group_count = _count_table(conn, "group")
    pending: list[str] = []
    if not user_count:
        pending.append("open_webui_users_missing")
    if not group_count:
        pending.append("open_webui_groups_missing")
    if user_count and not group_count:
        pending.append("open_webui_group_assignment_missing")

    return {
        "report_type": "open-webui-home-agent-access-audit",
        "secrets_included": False,
        "private_content_included": False,
        "db": str(DEFAULT_DB),
        "model_ids": sorted(rows),
        "missing_model_ids": missing,
        "user_count": user_count,
        "group_count": group_count,
        "checks": checks,
        "pending": pending,
        "ok": not missing and all(check["ok"] for check in checks),
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = sqlite3.connect(args.db)
    try:
        report = audit(conn)
    finally:
        conn.close()
    report["db"] = str(args.db)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
