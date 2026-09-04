from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "count-open-webui-home-resources-live.py"


def _module():
    spec = importlib.util.spec_from_file_location("count_open_webui_home_resources_live", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        for table in ("knowledge", "knowledge_file", "tool", "function", "memory"):
            conn.execute(f'CREATE TABLE "{table}" (id TEXT PRIMARY KEY)')
        conn.execute('INSERT INTO "knowledge" (id) VALUES ("k1")')
        conn.execute('INSERT INTO "tool" (id) VALUES ("t1")')
        conn.commit()
    finally:
        conn.close()


def test_resource_live_counts_report_is_sanitized(tmp_path: Path) -> None:
    module = _module()
    db = tmp_path / "webui.db"
    _db(db)

    report = module.build_report(db)

    assert report["ok"] is True
    assert report["secrets_included"] is False
    assert report["private_content_included"] is False
    assert isinstance(report["generated_at_unix"], int)
    assert report["git_head"]
    assert report["counts"]["knowledge"] == 1
    assert report["counts"]["tool"] == 1
    assert report["counts"]["memory"] == 0
    assert "token" not in json.dumps(report).lower()


def test_resource_live_counts_missing_db_fails_closed(tmp_path: Path) -> None:
    report = _module().build_report(tmp_path / "missing.db")

    assert report["ok"] is False
    assert report["pending"] == ["open_webui_database_unavailable"]
    assert all(value is None for value in report["counts"].values())


def test_resource_live_counts_main_writes_report(tmp_path: Path, capsys) -> None:
    db = tmp_path / "webui.db"
    output = tmp_path / "counts.json"
    _db(db)

    assert _module().main(["--db", str(db), "--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "open-webui-home-resources-live-counts"
