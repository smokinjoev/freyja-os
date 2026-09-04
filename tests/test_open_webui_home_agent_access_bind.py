from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BIND_SCRIPT = REPO_ROOT / "scripts" / "bind-open-webui-home-agent-access.py"
EXPORT_SCRIPT = REPO_ROOT / "scripts" / "export-open-webui-home-agents.py"
APPLY_SCRIPT = REPO_ROOT / "scripts" / "apply-open-webui-home-agents-offline.py"


def _module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE model (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                base_model_id TEXT,
                name TEXT,
                params TEXT,
                meta TEXT,
                updated_at BIGINT,
                created_at BIGINT,
                is_active BOOLEAN NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE user (
                id VARCHAR PRIMARY KEY,
                name VARCHAR,
                email VARCHAR,
                role VARCHAR,
                username VARCHAR(50)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE "group" (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                name TEXT,
                description TEXT,
                data JSON,
                meta JSON,
                permissions JSON,
                created_at BIGINT,
                updated_at BIGINT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE group_member (
                id TEXT PRIMARY KEY,
                group_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                created_at BIGINT,
                updated_at BIGINT,
                UNIQUE(group_id, user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE access_grant (
                id TEXT PRIMARY KEY,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                principal_type TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                permission TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                UNIQUE(resource_type, resource_id, principal_type, principal_id, permission)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _import_agents(db_path: Path, tmp_path: Path) -> None:
    export = _module(EXPORT_SCRIPT).build_export()
    import_path = tmp_path / "import.json"
    import_path.write_text(json.dumps(export), encoding="utf-8")
    assert _module(APPLY_SCRIPT).main(["--apply", "--import-json", str(import_path), "--db", str(db_path), "--backup-dir", str(tmp_path)]) == 0


def test_access_bind_dry_run_waits_for_real_users(tmp_path: Path) -> None:
    db_path = tmp_path / "webui.db"
    _db(db_path)
    _import_agents(db_path, tmp_path)

    conn = sqlite3.connect(db_path)
    try:
        report = _module(BIND_SCRIPT).plan(conn)
    finally:
        conn.close()

    assert report["ready"] is False
    assert report["missing_users"] == ["beth", "jenna", "joe", "liam"]
    assert report["group_inserts"] == ["joe", "beth", "liam", "jenna"]
    assert report["grant_insert_count"] == 10


def test_access_bind_apply_creates_groups_memberships_and_model_grants(tmp_path: Path) -> None:
    db_path = tmp_path / "webui.db"
    _db(db_path)
    _import_agents(db_path, tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executemany(
            "insert into user (id, name, email, role, username) values (?, ?, ?, ?, ?)",
            [
                ("user-joe", "Joe", "joe@example.invalid", "user", "joe"),
                ("user-beth", "Beth", "beth@example.invalid", "user", "beth"),
                ("user-liam", "Liam", "liam@example.invalid", "user", "liam"),
                ("user-jenna", "Jenna", "jenna@example.invalid", "user", "jenna"),
            ],
        )
        conn.commit()
        bind = _module(BIND_SCRIPT)
        report = bind.plan(conn)
        assert report["ready"] is True
        bind.apply_plan(conn, report)
        conn.commit()

        assert conn.execute('select count(*) from "group"').fetchone()[0] == 4
        assert conn.execute("select count(*) from group_member").fetchone()[0] == 4
        assert conn.execute("select count(*) from access_grant").fetchone()[0] == 10
        benedict_groups = conn.execute(
            "select principal_id from access_grant where resource_id='agent/benedict' order by principal_id"
        ).fetchall()
        assert [row[0] for row in benedict_groups] == ["beth"]
    finally:
        conn.close()
