from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify-open-webui-home-agent-db.py"


def _module():
    spec = importlib.util.spec_from_file_location("verify_open_webui_home_agent_db", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _db(path: Path, *, bad_specs: bool = False) -> None:
    module = _module()
    conn = sqlite3.connect(path)
    try:
        conn.execute("create table user (id text primary key)")
        conn.execute("create table auth (id text primary key)")
        conn.execute("create table api_key (id text primary key)")
        conn.execute("create table config (key text primary key, value text)")
        conn.execute("create table model (id text primary key)")
        conn.execute("create table knowledge (id text primary key)")
        conn.execute("create table tool (id text primary key, specs text)")
        conn.execute("create table memory (id text primary key)")
        conn.execute("insert into config (key, value) values ('auth.enable_api_keys', 'true')")
        conn.executemany("insert into model (id) values (?)", [(item,) for item in module.MODEL_IDS])
        conn.executemany("insert into knowledge (id) values (?)", [(item,) for item in module.KNOWLEDGE_IDS])
        conn.executemany(
            "insert into tool (id, specs) values (?, ?)",
            [(item, json.dumps({"bad": True} if bad_specs else [])) for item in module.TOOL_IDS],
        )
        conn.executemany("insert into memory (id) values (?)", [(item,) for item in module.MEMORY_IDS])
        conn.commit()
    finally:
        conn.close()


def test_db_verification_passes_for_managed_rows(tmp_path: Path, capsys) -> None:
    db = tmp_path / "webui.db"
    output = tmp_path / "verify.json"
    _db(db)

    assert _module().main(["--db", str(db), "--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["ok"] is True
    assert report["secrets_included"] is False
    assert report["private_content_included"] is False
    assert all(report["models_present"].values())
    assert all(report["knowledge_present"].values())
    assert all(report["tools_present"].values())
    assert all(report["memory_policies_present"].values())
    assert report["managed_tool_specs_are_lists"] is True


def test_db_verification_fails_for_bad_tool_specs(tmp_path: Path) -> None:
    db = tmp_path / "webui.db"
    _db(db, bad_specs=True)

    report = _module().verify(db)

    assert report["ok"] is False
    assert report["managed_tool_specs_are_lists"] is False
    assert set(report["tool_spec_types"].values()) == {"dict"}
