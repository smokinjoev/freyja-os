from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "apply-open-webui-home-agents-offline.py"
EXPORT_SCRIPT = REPO_ROOT / "scripts" / "export-open-webui-home-agents.py"


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
        conn.execute("CREATE TABLE chat (id TEXT PRIMARY KEY, chat TEXT)")
        conn.commit()
    finally:
        conn.close()


def test_offline_import_dry_run_does_not_write(tmp_path: Path, capsys) -> None:
    apply_module = _module(SCRIPT)
    export = _module(EXPORT_SCRIPT).build_export()
    import_path = tmp_path / "import.json"
    db_path = tmp_path / "webui.db"
    import_path.write_text(json.dumps(export), encoding="utf-8")
    _db(db_path)

    assert apply_module.main(["--import-json", str(import_path), "--db", str(db_path)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "dry-run"
    assert isinstance(report["generated_at_unix"], int)
    assert report["git_head"]
    assert report["private_content_included"] is False
    assert report["model_count"] == 6
    assert report["insert_count"] == 6
    assert report["touched_tables"] == ["model"]
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("select count(*) from model").fetchone()[0] == 0
    finally:
        conn.close()


def test_offline_import_apply_upserts_models_and_creates_backup(tmp_path: Path, capsys) -> None:
    apply_module = _module(SCRIPT)
    export = _module(EXPORT_SCRIPT).build_export()
    import_path = tmp_path / "import.json"
    db_path = tmp_path / "webui.db"
    import_path.write_text(json.dumps(export), encoding="utf-8")
    _db(db_path)

    assert apply_module.main(["--apply", "--import-json", str(import_path), "--db", str(db_path), "--backup-dir", str(tmp_path)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "apply"
    assert isinstance(report["generated_at_unix"], int)
    assert report["git_head"]
    assert report["private_content_included"] is False
    assert report["model_count"] == 6
    assert Path(report["backup"]).exists()
    assert "token" not in str(report).lower()
    assert "api_key" not in str(report).lower()

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("select id, base_model_id, name, params, meta from model order by id").fetchall()
    finally:
        conn.close()
    ids = {row[0] for row in rows}
    assert ids == {
        "agent/freyja",
        "agent/cloyd-gibbler",
        "agent/freyja-coder",
        "agent/benedict",
        "agent/agent-47",
        "agent/jennacide",
    }
    benedict = next(row for row in rows if row[0] == "agent/benedict")
    meta = json.loads(benedict[4])
    assert meta["freyja"]["memory_policy"]["cloud_fallback"] == "forbidden"
    assert meta["access_control"]["read"]["group_ids"] == ["beth"]
