from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "apply-open-webui-home-resources-offline.py"
EXPORT_SCRIPT = REPO_ROOT / "scripts" / "export-open-webui-home-resources.py"


def _module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _db(path: Path, *, with_user: bool = False) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE user (
                id VARCHAR PRIMARY KEY,
                name VARCHAR,
                email VARCHAR,
                username VARCHAR(50),
                created_at BIGINT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE knowledge (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                meta JSON,
                created_at BIGINT NOT NULL,
                updated_at BIGINT,
                data JSON
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE tool (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR,
                name TEXT,
                content TEXT,
                specs TEXT,
                meta TEXT,
                valves TEXT,
                updated_at BIGINT,
                created_at BIGINT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE memory (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR,
                content TEXT,
                updated_at BIGINT,
                created_at BIGINT,
                type VARCHAR NOT NULL DEFAULT 'context',
                path TEXT,
                meta JSON
            )
            """
        )
        if with_user:
            conn.execute(
                "insert into user (id, name, email, username, created_at) values (?, ?, ?, ?, ?)",
                ("owner-1", "Joe", "joe@example.invalid", "joe", 1),
            )
        conn.commit()
    finally:
        conn.close()


def _export(tmp_path: Path) -> Path:
    path = tmp_path / "resources.json"
    export = _module(EXPORT_SCRIPT).build_export()
    export["ok"] = True
    export["validation_errors"] = []
    path.write_text(json.dumps(export), encoding="utf-8")
    return path


def test_resource_import_dry_run_reports_missing_owner_without_writing(tmp_path: Path, capsys) -> None:
    db = tmp_path / "webui.db"
    _db(db)
    resource_export = _export(tmp_path)
    output = tmp_path / "resource-import.json"

    assert _module(SCRIPT).main(["--import-json", str(resource_export), "--db", str(db), "--output", str(output), "--apply"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["ready"] is False
    assert isinstance(report["generated_at_unix"], int)
    assert report["git_head"]
    assert report["applied"] is False
    assert report["reason"] == "missing or ambiguous Open WebUI owner user"
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("select count(*) from knowledge").fetchone()[0] == 0
        assert conn.execute("select count(*) from tool").fetchone()[0] == 0
        assert conn.execute("select count(*) from memory").fetchone()[0] == 0
    finally:
        conn.close()


def test_resource_import_fails_closed_when_database_is_missing(tmp_path: Path, capsys) -> None:
    resource_export = _export(tmp_path)
    output = tmp_path / "resource-import.json"

    assert _module(SCRIPT).main(["--import-json", str(resource_export), "--db", str(tmp_path / "missing.db"), "--output", str(output), "--apply"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["ready"] is False
    assert isinstance(report["generated_at_unix"], int)
    assert report["git_head"]
    assert report["applied"] is False
    assert report["reason"] == "Open WebUI database is not available at the requested path"


def test_resource_import_can_dry_run_from_container_snapshot(tmp_path: Path, monkeypatch, capsys) -> None:
    db = tmp_path / "source-webui.db"
    _db(db)
    resource_export = _export(tmp_path)
    output = tmp_path / "resource-import.json"
    module = _module(SCRIPT)

    def fake_run(args, **kwargs):
        destination = Path(args[-1])
        source = str(args[2])
        if source.endswith("/webui.db"):
            destination.write_bytes(db.read_bytes())
            return subprocess.CompletedProcess(args, 0)
        if source.endswith("/webui.db-wal") or source.endswith("/webui.db-shm"):
            return subprocess.CompletedProcess(args, 1)
        raise AssertionError(args)

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module.main(["--import-json", str(resource_export), "--db", str(tmp_path / "missing.db"), "--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["dry_run_snapshot"]["container"] == module.DEFAULT_OPEN_WEBUI_CONTAINER
    assert report["ready"] is False
    assert report["reason"] == "missing or ambiguous Open WebUI owner user"


def test_resource_import_apply_does_not_use_container_snapshot(tmp_path: Path, monkeypatch, capsys) -> None:
    resource_export = _export(tmp_path)
    output = tmp_path / "resource-import.json"
    module = _module(SCRIPT)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("snapshot should not be used in apply mode")

    monkeypatch.setattr(module.subprocess, "run", fail_if_called)

    assert _module(SCRIPT).main(["--import-json", str(resource_export), "--db", str(tmp_path / "missing.db"), "--output", str(output), "--apply"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert "dry_run_snapshot" not in report
    assert report["ready"] is False
    assert report["reason"] == "Open WebUI database is not available at the requested path"


def test_resource_import_apply_writes_expected_rows_and_backup(tmp_path: Path, capsys) -> None:
    db = tmp_path / "webui.db"
    _db(db, with_user=True)
    resource_export = _export(tmp_path)
    output = tmp_path / "resource-import.json"

    assert (
        _module(SCRIPT).main(
            [
                "--import-json",
                str(resource_export),
                "--db",
                str(db),
                "--owner-user-id",
                "owner-1",
                "--backup-dir",
                str(tmp_path),
                "--output",
                str(output),
                "--apply",
            ]
        )
        == 0
    )

    report = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["ready"] is True
    assert isinstance(report["generated_at_unix"], int)
    assert report["git_head"]
    assert report["applied"] is True
    assert Path(report["backup"]).exists()
    assert report["knowledge_insert_count"] == 3
    assert report["tool_insert_count"] == 6
    assert report["memory_insert_count"] == 4
    assert report["touched_tables"] == ["knowledge", "tool", "memory"]

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("select count(*) from knowledge").fetchone()[0] == 3
        assert conn.execute("select count(*) from tool").fetchone()[0] == 6
        assert conn.execute("select count(*) from memory").fetchone()[0] == 4
        specs = conn.execute("select specs from tool where id='freyja_home_memory'").fetchone()[0]
        parsed_specs = json.loads(specs)
        assert isinstance(parsed_specs, list)
        assert parsed_specs[0]["name"] == "search"
        benedict = conn.execute("select meta from knowledge where id='benedict_restricted'").fetchone()[0]
        assert json.loads(benedict)["freyja"]["allowed_agents"] == ["benedict"]
        memory = conn.execute("select meta from memory where id='freyja_native_memory_policy:beth'").fetchone()[0]
        assert json.loads(memory)["freyja"]["scope"] == "personal:beth"
    finally:
        conn.close()
