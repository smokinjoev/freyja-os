#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path("/app/backend/data/webui.db")
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-home-resources-live-counts.json"
DEFAULT_OPEN_WEBUI_CONTAINER = "freyja-open-webui-atlas-open-webui-1"
TABLES = ("knowledge", "knowledge_file", "tool", "function", "memory")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Count sanitized live Open WebUI resource tables.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--open-webui-container", default=DEFAULT_OPEN_WEBUI_CONTAINER)
    parser.add_argument("--no-container-snapshot", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def snapshot_open_webui_database(container: str, target_dir: Path) -> Path | None:
    target_dir.mkdir(parents=True, exist_ok=True)
    copied_main = False
    for filename in ("webui.db", "webui.db-wal", "webui.db-shm"):
        proc = subprocess.run(
            ["docker", "cp", f"{container}:/app/backend/data/{filename}", str(target_dir / filename)],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if filename == "webui.db":
            copied_main = proc.returncode == 0
    return target_dir / "webui.db" if copied_main else None


def table_count(conn: sqlite3.Connection, table: str) -> int | None:
    if not conn.execute("select name from sqlite_master where type='table' and name=?", (table,)).fetchone():
        return None
    quoted = '"' + table.replace('"', '""') + '"'
    return int(conn.execute(f"select count(*) from {quoted}").fetchone()[0])


def build_report(db: Path, *, snapshot_source: dict[str, Any] | None = None) -> dict[str, Any]:
    generated_at = int(time.time())
    if not db.exists():
        return {
            "report_type": "open-webui-home-resources-live-counts",
            "generated_at_unix": generated_at,
            "git_head": _git_head(),
            "secrets_included": False,
            "private_content_included": False,
            "db": str(db),
            "counts": {table: None for table in TABLES},
            "pending": ["open_webui_database_unavailable"],
            "ok": False,
        }
    conn = sqlite3.connect(db)
    try:
        counts = {table: table_count(conn, table) for table in TABLES}
    finally:
        conn.close()
    pending = []
    if not counts.get("knowledge") and not counts.get("tool") and not counts.get("memory"):
        pending.extend(["open_webui_owner_user_missing", "authenticated_resource_import_missing"])
    report: dict[str, Any] = {
        "report_type": "open-webui-home-resources-live-counts",
        "generated_at_unix": generated_at,
        "git_head": _git_head(),
        "secrets_included": False,
        "private_content_included": False,
        "db": str(db),
        "counts": counts,
        "pending": pending,
        "ok": all(value is not None for value in counts.values()),
    }
    if snapshot_source is not None:
        report["dry_run_snapshot"] = snapshot_source
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = args.db
    snapshot_source = None
    with tempfile.TemporaryDirectory(prefix="open-webui-home-resource-counts-") as tmp:
        if not args.no_container_snapshot and not db.exists():
            snapshot = snapshot_open_webui_database(args.open_webui_container, Path(tmp))
            if snapshot is not None:
                db = snapshot
                snapshot_source = {
                    "container": args.open_webui_container,
                    "source": "/app/backend/data/webui.db",
                    "wal_and_shm_attempted": True,
                }
        report = build_report(db, snapshot_source=snapshot_source)
    report["db"] = str(args.db)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
