#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMPORT = REPO_ROOT / "certification" / "reports" / "open-webui-home-resources-export.json"
DEFAULT_DB = Path("/app/backend/data/webui.db")
REQUIRED_COLUMNS = {
    "knowledge": {"id", "user_id", "name", "description", "meta", "created_at", "updated_at", "data"},
    "tool": {"id", "user_id", "name", "content", "specs", "meta", "valves", "updated_at", "created_at"},
    "memory": {"id", "user_id", "content", "updated_at", "created_at", "type", "path", "meta"},
    "user": {"id", "name", "email", "username"},
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safely upsert Freyja Open WebUI Knowledge/tool/native-memory resource rows.")
    parser.add_argument("--import-json", type=Path, default=DEFAULT_IMPORT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--owner-user-id", help="Existing Open WebUI user ID that should own shared Knowledge/tool rows.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run.")
    parser.add_argument("--backup-dir", type=Path)
    return parser


def load_import(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("export_type") != "open-webui-home-resources":
        raise ValueError("unexpected resource export_type")
    if payload.get("secrets_included") is not False or payload.get("private_content_included") is not False:
        raise ValueError("refusing resource payload that may contain secrets or private content")
    if payload.get("ok") is False or payload.get("validation_errors"):
        raise ValueError("refusing invalid resource payload")
    return payload


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'pragma table_info("{table}")').fetchall()}


def inspect_schema(conn: sqlite3.Connection) -> None:
    for table, required in REQUIRED_COLUMNS.items():
        columns = _columns(conn, table)
        missing = sorted(required - columns)
        if missing:
            raise ValueError(f"{table} table missing expected columns: {missing}")


def resolve_owner(conn: sqlite3.Connection, owner_user_id: str | None) -> str | None:
    if owner_user_id:
        row = conn.execute("select id from user where id=?", (owner_user_id,)).fetchone()
        return str(row[0]) if row else None
    rows = conn.execute("select id from user order by created_at asc, id asc").fetchall()
    if len(rows) == 1:
        return str(rows[0][0])
    return None


def build_rows(payload: dict[str, Any], owner_user_id: str, now: int | None = None) -> dict[str, list[dict[str, Any]]]:
    timestamp = int(now or time.time())
    knowledge_rows = [
        {
            "id": str(item["id"]),
            "user_id": owner_user_id,
            "name": str(item["name"]),
            "description": str(item.get("description") or ""),
            "meta": json.dumps(item.get("meta") or {}, sort_keys=True),
            "data": json.dumps(item.get("data") or {}, sort_keys=True),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        for item in payload.get("knowledge") or []
    ]
    tool_rows = [
        {
            "id": str(item["id"]),
            "user_id": owner_user_id,
            "name": str(item["name"]),
            "content": "# Freyja managed tool boundary. Configure the live OpenAPI/MCP adapter in Open WebUI before enabling.",
            "specs": json.dumps({"operations": item.get("operations") or [], "boundary": item.get("boundary")}, sort_keys=True),
            "meta": json.dumps(item.get("meta") or {}, sort_keys=True),
            "valves": json.dumps({"enabled": False, "managed_by": "freyja-home-agent"}, sort_keys=True),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        for item in payload.get("tools") or []
    ]
    memory_policy = payload.get("native_memory") or {}
    memory_rows = [
        {
            "id": f"freyja_native_memory_policy:{name}",
            "user_id": owner_user_id,
            "content": f"Freyja native memory scope for {name}: {scope}.",
            "type": "context",
            "path": None,
            "meta": json.dumps(
                {
                    "freyja": {
                        "source": "open-webui-home-resources",
                        "policy": memory_policy.get("policy") or {},
                        "scope": scope,
                        "user_key": name,
                    }
                },
                sort_keys=True,
            ),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        for name, scope in sorted((memory_policy.get("private_preferences") or {}).items())
    ]
    return {"knowledge": knowledge_rows, "tool": tool_rows, "memory": memory_rows}


def _backup_database(db_path: Path, backup_dir: Path | None) -> Path:
    target_dir = backup_dir or db_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    backup = target_dir / f"{db_path.name}.backup-before-home-resources-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup


def count_existing(conn: sqlite3.Connection, table: str, ids: list[str]) -> set[str]:
    if not ids:
        return set()
    return {
        str(row[0])
        for row in conn.execute(
            f'select id from "{table}" where id in ({",".join("?" for _ in ids)})',
            ids,
        ).fetchall()
    }


def upsert(conn: sqlite3.Connection, rows: dict[str, list[dict[str, Any]]]) -> None:
    conn.executemany(
        """
        INSERT INTO knowledge (id, user_id, name, description, meta, created_at, updated_at, data)
        VALUES (:id, :user_id, :name, :description, :meta, :created_at, :updated_at, :data)
        ON CONFLICT(id) DO UPDATE SET
            user_id=excluded.user_id,
            name=excluded.name,
            description=excluded.description,
            meta=excluded.meta,
            updated_at=excluded.updated_at,
            data=excluded.data
        """,
        rows["knowledge"],
    )
    conn.executemany(
        """
        INSERT INTO tool (id, user_id, name, content, specs, meta, valves, updated_at, created_at)
        VALUES (:id, :user_id, :name, :content, :specs, :meta, :valves, :updated_at, :created_at)
        ON CONFLICT(id) DO UPDATE SET
            user_id=excluded.user_id,
            name=excluded.name,
            content=excluded.content,
            specs=excluded.specs,
            meta=excluded.meta,
            valves=excluded.valves,
            updated_at=excluded.updated_at
        """,
        rows["tool"],
    )
    conn.executemany(
        """
        INSERT INTO memory (id, user_id, content, updated_at, created_at, type, path, meta)
        VALUES (:id, :user_id, :content, :updated_at, :created_at, :type, :path, :meta)
        ON CONFLICT(id) DO UPDATE SET
            user_id=excluded.user_id,
            content=excluded.content,
            updated_at=excluded.updated_at,
            type=excluded.type,
            path=excluded.path,
            meta=excluded.meta
        """,
        rows["memory"],
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = load_import(args.import_json)
    conn = sqlite3.connect(args.db)
    try:
        inspect_schema(conn)
        owner_user_id = resolve_owner(conn, args.owner_user_id)
        report: dict[str, Any] = {
            "report_type": "open-webui-home-resources-offline-import",
            "mode": "apply" if args.apply else "dry-run",
            "db": str(args.db),
            "import_json": str(args.import_json),
            "secrets_included": False,
            "private_content_included": False,
            "owner_user_id_resolved": owner_user_id is not None,
            "touched_tables": ["knowledge", "tool", "memory"],
        }
        if owner_user_id is None:
            report.update(
                {
                    "ready": False,
                    "applied": False,
                    "reason": "missing or ambiguous Open WebUI owner user",
                    "knowledge_count": len(payload.get("knowledge") or []),
                    "tool_count": len(payload.get("tools") or []),
                    "memory_policy_count": len((payload.get("native_memory") or {}).get("private_preferences") or {}),
                }
            )
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0

        rows = build_rows(payload, owner_user_id)
        report["ready"] = True
        for table, table_rows in rows.items():
            ids = [row["id"] for row in table_rows]
            existing = count_existing(conn, table, ids)
            report[f"{table}_insert_count"] = len([row_id for row_id in ids if row_id not in existing])
            report[f"{table}_update_count"] = len([row_id for row_id in ids if row_id in existing])
            report[f"{table}_ids"] = ids
        if args.apply:
            backup = _backup_database(args.db, args.backup_dir)
            upsert(conn, rows)
            conn.commit()
            report["backup"] = str(backup)
            report["applied"] = True
        else:
            report["applied"] = False
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
