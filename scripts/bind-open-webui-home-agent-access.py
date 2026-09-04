#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path("/app/backend/data/webui.db")
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-home-agent-access-bind-dry-run.json"
DEFAULT_OPEN_WEBUI_CONTAINER = "freyja-open-webui-atlas-open-webui-1"
GROUPS = {"joe": "Joe", "beth": "Beth", "liam": "Liam", "jenna": "Jenna"}
MODEL_GROUPS = {
    "agent/freyja": ["joe", "beth"],
    "agent/cloyd-gibbler": ["joe"],
    "agent/benedict": ["beth"],
    "agent/agent-47": ["liam", "joe", "beth"],
    "agent/jennacide": ["jenna", "joe", "beth"],
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bind Freyja home-agent Open WebUI models to existing Open WebUI users/groups.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--apply", action="store_true", help="Write changes. Default is dry-run.")
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--open-webui-container", default=DEFAULT_OPEN_WEBUI_CONTAINER)
    parser.add_argument("--no-container-snapshot", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'pragma table_info("{table}")').fetchall()}


def _require_schema(conn: sqlite3.Connection) -> None:
    required = {
        "user": {"id", "name", "email", "username"},
        "group": {"id", "user_id", "name", "description", "data", "meta", "permissions", "created_at", "updated_at"},
        "group_member": {"id", "group_id", "user_id", "created_at", "updated_at"},
        "access_grant": {"id", "resource_type", "resource_id", "principal_type", "principal_id", "permission", "created_at"},
        "model": {"id"},
    }
    for table, columns in required.items():
        present = _table_columns(conn, table)
        missing = sorted(columns - present)
        if missing:
            raise ValueError(f"{table} table missing expected columns: {missing}")


def _load_users(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("select id, name, email, username from user").fetchall()
    by_group: dict[str, str] = {}
    for row in rows:
        user_id = str(row[0])
        fields = {str(value).strip().casefold() for value in row[1:] if value}
        email_prefixes = {value.split("@", 1)[0] for value in fields if "@" in value}
        fields |= email_prefixes
        for group_id in GROUPS:
            if group_id in fields and group_id not in by_group:
                by_group[group_id] = user_id
    return by_group


def _backup_database(db_path: Path, backup_dir: Path | None) -> Path:
    target_dir = backup_dir or db_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    backup = target_dir / f"{db_path.name}.backup-before-access-bind-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(backup)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup


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


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def plan(conn: sqlite3.Connection) -> dict[str, Any]:
    conn.row_factory = sqlite3.Row
    _require_schema(conn)
    model_ids = {
        str(row[0])
        for row in conn.execute(
            "select id from model where id in ({})".format(",".join("?" for _ in MODEL_GROUPS)),
            list(MODEL_GROUPS),
        ).fetchall()
    }
    users = _load_users(conn)
    missing_users = sorted(set(GROUPS) - set(users))
    missing_models = sorted(set(MODEL_GROUPS) - model_ids)

    existing_groups = {str(row[0]) for row in conn.execute('select id from "group"').fetchall()}
    existing_members = {
        (str(row[0]), str(row[1]))
        for row in conn.execute("select group_id, user_id from group_member").fetchall()
    }
    existing_grants = {
        (str(row[0]), str(row[1]), str(row[2]), str(row[3]), str(row[4]))
        for row in conn.execute(
            "select resource_type, resource_id, principal_type, principal_id, permission from access_grant"
        ).fetchall()
    }

    group_inserts = [group_id for group_id in GROUPS if group_id not in existing_groups]
    member_inserts = [
        {"group_id": group_id, "user_id": users[group_id]}
        for group_id in GROUPS
        if group_id in users and (group_id, users[group_id]) not in existing_members
    ]
    grant_inserts = []
    for model_id, group_ids in MODEL_GROUPS.items():
        if model_id not in model_ids:
            continue
        for group_id in group_ids:
            key = ("model", model_id, "group", group_id, "read")
            if key not in existing_grants:
                grant_inserts.append({"resource_type": "model", "resource_id": model_id, "principal_type": "group", "principal_id": group_id, "permission": "read"})

    return {
        "report_type": "open-webui-home-agent-access-bind",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "secrets_included": False,
        "private_content_included": False,
        "missing_users": missing_users,
        "missing_models": missing_models,
        "group_inserts": group_inserts,
        "member_insert_count": len(member_inserts),
        "grant_insert_count": len(grant_inserts),
        "member_inserts": member_inserts,
        "grant_inserts": grant_inserts,
        "ready": not missing_users and not missing_models,
    }


def apply_plan(conn: sqlite3.Connection, report: dict[str, Any]) -> None:
    now = int(time.time())
    conn.executemany(
        """
        INSERT INTO "group" (id, user_id, name, description, data, meta, permissions, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name,
            description=excluded.description,
            data=excluded.data,
            meta=excluded.meta,
            permissions=excluded.permissions,
            updated_at=excluded.updated_at
        """,
        [
            (
                group_id,
                None,
                GROUPS[group_id],
                f"Freyja home-agent access group for {GROUPS[group_id]}.",
                json.dumps({"freyja_home_agent": True}, sort_keys=True),
                json.dumps({"managed_by": "freyja-home-agent"}, sort_keys=True),
                json.dumps({}, sort_keys=True),
                now,
                now,
            )
            for group_id in GROUPS
        ],
    )
    conn.executemany(
        """
        INSERT INTO group_member (id, group_id, user_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(group_id, user_id) DO UPDATE SET updated_at=excluded.updated_at
        """,
        [(str(uuid.uuid4()), item["group_id"], item["user_id"], now, now) for item in report["member_inserts"]],
    )
    conn.executemany(
        """
        INSERT INTO access_grant (id, resource_type, resource_id, principal_type, principal_id, permission, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(resource_type, resource_id, principal_type, principal_id, permission) DO NOTHING
        """,
        [(str(uuid.uuid4()), item["resource_type"], item["resource_id"], item["principal_type"], item["principal_id"], item["permission"], now) for item in report["grant_inserts"]],
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot_source = None
    db = args.db
    tmp_context = tempfile.TemporaryDirectory(prefix="open-webui-home-access-db-")
    try:
        if not args.apply and not args.no_container_snapshot and not db.exists():
            snapshot = snapshot_open_webui_database(args.open_webui_container, Path(tmp_context.name))
            if snapshot is not None:
                db = snapshot
                snapshot_source = {
                    "container": args.open_webui_container,
                    "source": "/app/backend/data/webui.db",
                    "wal_and_shm_attempted": True,
                }
        if not db.exists():
            report = {
                "report_type": "open-webui-home-agent-access-bind",
                "generated_at_unix": int(time.time()),
                "git_head": _git_head(),
                "secrets_included": False,
                "private_content_included": False,
                "mode": "apply" if args.apply else "dry-run",
                "db": str(args.db),
                "ready": False,
                "applied": False,
                "reason": "Open WebUI database is not available at the requested path",
            }
            rendered = json.dumps(report, indent=2, sort_keys=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
            print(rendered)
            return 0
        conn = sqlite3.connect(db)
        try:
            report = plan(conn)
            report["mode"] = "apply" if args.apply else "dry-run"
            report["db"] = str(args.db)
            if snapshot_source is not None:
                report["dry_run_snapshot"] = snapshot_source
            if args.apply:
                if not report["ready"]:
                    report["applied"] = False
                    report["reason"] = "missing required Open WebUI users or models"
                else:
                    backup = _backup_database(args.db, args.backup_dir)
                    apply_plan(conn, report)
                    conn.commit()
                    report["backup"] = str(backup)
                    report["applied"] = True
            else:
                report["applied"] = False
            rendered = json.dumps(report, indent=2, sort_keys=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
            print(rendered)
        finally:
            conn.close()
    finally:
        tmp_context.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
