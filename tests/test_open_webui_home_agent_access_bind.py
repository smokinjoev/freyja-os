from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
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


def test_access_bind_main_writes_dry_run_output(tmp_path: Path, capsys) -> None:
    db_path = tmp_path / "webui.db"
    output = tmp_path / "access-bind.json"
    _db(db_path)
    _import_agents(db_path, tmp_path)
    capsys.readouterr()

    assert _module(BIND_SCRIPT).main(["--db", str(db_path), "--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["ready"] is False
    assert report["applied"] is False
    assert report["mode"] == "dry-run"
    assert report["missing_users"] == ["beth", "jenna", "joe", "liam"]


def test_access_bind_fails_closed_when_database_is_missing(tmp_path: Path, capsys) -> None:
    output = tmp_path / "access-bind.json"

    assert _module(BIND_SCRIPT).main(["--db", str(tmp_path / "missing.db"), "--output", str(output), "--apply"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["ready"] is False
    assert report["applied"] is False
    assert report["reason"] == "Open WebUI database is not available at the requested path"
    assert "dry_run_snapshot" not in report


def test_access_bind_can_dry_run_from_container_snapshot(tmp_path: Path, monkeypatch, capsys) -> None:
    source_db = tmp_path / "source-webui.db"
    output = tmp_path / "access-bind.json"
    _db(source_db)
    _import_agents(source_db, tmp_path)
    capsys.readouterr()
    module = _module(BIND_SCRIPT)

    def fake_run(args, **kwargs):
        destination = Path(args[-1])
        source = str(args[2])
        if source.endswith("/webui.db"):
            destination.write_bytes(source_db.read_bytes())
            return subprocess.CompletedProcess(args, 0)
        if source.endswith("/webui.db-wal") or source.endswith("/webui.db-shm"):
            return subprocess.CompletedProcess(args, 1)
        raise AssertionError(args)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module.main(["--db", str(tmp_path / "missing.db"), "--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["dry_run_snapshot"]["container"] == module.DEFAULT_OPEN_WEBUI_CONTAINER
    assert report["ready"] is False
    assert report["missing_users"] == ["beth", "jenna", "joe", "liam"]


def test_access_bind_apply_does_not_use_container_snapshot(tmp_path: Path, monkeypatch, capsys) -> None:
    output = tmp_path / "access-bind.json"
    module = _module(BIND_SCRIPT)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("snapshot should not be used in apply mode")

    monkeypatch.setattr(module.subprocess, "run", fail_if_called)

    assert module.main(["--db", str(tmp_path / "missing.db"), "--output", str(output), "--apply"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["ready"] is False
    assert report["applied"] is False
    assert report["reason"] == "Open WebUI database is not available at the requested path"


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
