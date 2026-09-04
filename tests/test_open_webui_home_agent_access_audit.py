from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_SCRIPT = REPO_ROOT / "scripts" / "audit-open-webui-home-agent-access.py"
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
                role VARCHAR
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
                data TEXT,
                meta TEXT,
                permissions TEXT,
                user_ids TEXT,
                created_at BIGINT,
                updated_at BIGINT
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
    apply_module = _module(APPLY_SCRIPT)
    assert apply_module.main(["--apply", "--import-json", str(import_path), "--db", str(db_path), "--backup-dir", str(tmp_path)]) == 0


def test_access_audit_reports_embedded_groups_and_pending_open_webui_accounts(tmp_path: Path) -> None:
    db_path = tmp_path / "webui.db"
    _db(db_path)
    _import_agents(db_path, tmp_path)
    audit_module = _module(AUDIT_SCRIPT)

    conn = sqlite3.connect(db_path)
    try:
        report = audit_module.audit(conn)
    finally:
        conn.close()

    assert report["ok"] is True
    assert report["user_count"] == 0
    assert report["group_count"] == 0
    assert report["pending"] == ["open_webui_users_missing", "open_webui_groups_missing"]
    by_name = {check["name"]: check for check in report["checks"]}
    assert by_name["agent/benedict:read_groups"]["evidence"]["group_ids"] == ["beth"]
    assert by_name["agent/agent-47:read_groups"]["evidence"]["group_ids"] == ["beth", "joe", "liam"]


def test_access_audit_fails_closed_on_wrong_group_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "webui.db"
    _db(db_path)
    _import_agents(db_path, tmp_path)
    conn = sqlite3.connect(db_path)
    try:
        raw = conn.execute("select meta from model where id='agent/benedict'").fetchone()[0]
        meta = json.loads(raw)
        meta["access_control"]["read"]["group_ids"] = ["household"]
        conn.execute("update model set meta=? where id='agent/benedict'", (json.dumps(meta),))
        conn.commit()

        report = _module(AUDIT_SCRIPT).audit(conn)
    finally:
        conn.close()

    assert report["ok"] is False
    check = next(check for check in report["checks"] if check["name"] == "agent/benedict:read_groups")
    assert check["ok"] is False
    assert check["evidence"]["expected"] == ["beth"]
