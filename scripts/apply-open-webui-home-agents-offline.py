#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMPORT = REPO_ROOT / "certification" / "reports" / "open-webui-home-agents-import.json"
DEFAULT_DB = Path("/app/backend/data/webui.db")
MODEL_COLUMNS = {"id", "user_id", "base_model_id", "name", "params", "meta", "updated_at", "created_at", "is_active"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Safely upsert Freyja home-agent models into Open WebUI's model table.")
    parser.add_argument("--import-json", type=Path, default=DEFAULT_IMPORT)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run.")
    return parser


def load_import(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("export_type") != "open-webui-home-agent-import":
        raise ValueError("unexpected import export_type")
    if payload.get("secrets_included") is not False:
        raise ValueError("refusing import payload that may contain secrets")
    return payload


def inspect_model_table(conn: sqlite3.Connection) -> set[str]:
    if not conn.execute("select name from sqlite_master where type='table' and name='model'").fetchone():
        raise ValueError("Open WebUI model table not found")
    return {str(row[1]) for row in conn.execute("pragma table_info(model)").fetchall()}


def build_model_rows(payload: dict[str, Any], now: int | None = None) -> list[dict[str, Any]]:
    timestamp = int(now or time.time())
    rows = []
    for record in payload.get("records") or []:
        if not isinstance(record, dict):
            continue
        rows.append(
            {
                "id": str(record["id"]),
                "user_id": None,
                "base_model_id": str(record["base_model_id"]),
                "name": str(record["name"]),
                "params": json.dumps(record.get("params") or {}, sort_keys=True),
                "meta": json.dumps(
                    {
                        **(record.get("meta") or {}),
                        "access_control": record.get("access_control") or {},
                        "freyja": record.get("freyja") or {},
                    },
                    sort_keys=True,
                ),
                "updated_at": timestamp,
                "created_at": timestamp,
                "is_active": 1,
            }
        )
    if not rows:
        raise ValueError("no model records found")
    return rows


def backup_database(db_path: Path, backup_dir: Path | None) -> Path:
    target_dir = backup_dir or db_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    backup = target_dir / f"{db_path.name}.backup-before-home-agents-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup


def upsert_rows(conn: sqlite3.Connection, rows: list[dict[str, Any]]) -> None:
    conn.executemany(
        """
        INSERT INTO model (
            id, user_id, base_model_id, name, params, meta, updated_at, created_at, is_active
        ) VALUES (
            :id, :user_id, :base_model_id, :name, :params, :meta, :updated_at, :created_at, :is_active
        )
        ON CONFLICT(id) DO UPDATE SET
            user_id=excluded.user_id,
            base_model_id=excluded.base_model_id,
            name=excluded.name,
            params=excluded.params,
            meta=excluded.meta,
            updated_at=excluded.updated_at,
            is_active=excluded.is_active
        """,
        rows,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = load_import(args.import_json)
    rows = build_model_rows(payload)
    conn = sqlite3.connect(args.db)
    try:
        columns = inspect_model_table(conn)
        missing = sorted(MODEL_COLUMNS - columns)
        if missing:
            raise ValueError(f"model table missing expected columns: {missing}")
        existing = {
            row[0]
            for row in conn.execute(
                "select id from model where id in ({})".format(",".join("?" for _ in rows)),
                [row["id"] for row in rows],
            ).fetchall()
        }
        report = {
            "report_type": "open-webui-home-agent-offline-import",
            "db": str(args.db),
            "import_json": str(args.import_json),
            "secrets_included": False,
            "mode": "apply" if args.apply else "dry-run",
            "model_ids": [row["id"] for row in rows],
            "insert_count": len([row for row in rows if row["id"] not in existing]),
            "update_count": len([row for row in rows if row["id"] in existing]),
            "touched_tables": ["model"],
        }
        if args.apply:
            backup = backup_database(args.db, args.backup_dir)
            report["backup"] = str(backup)
            upsert_rows(conn, rows)
            conn.commit()
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
