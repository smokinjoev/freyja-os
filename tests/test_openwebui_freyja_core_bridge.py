from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "ops" / "openwebui" / "upsert_freyja_core_bridge_tool.py"


def _module():
    spec = importlib.util.spec_from_file_location("upsert_freyja_core_bridge_tool", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("create table tool (id text primary key, user_id text, updated_at integer)")
    conn.execute("create table model (id text primary key, meta text, params text, updated_at integer)")
    conn.execute("insert into tool (id, user_id, updated_at) values ('freyja_core_bridge', null, 0)")
    for model_id in ("agent/freyja", "agent/cloyd-gibbler", "agent/freyja-coder"):
        conn.execute(
            "insert into model (id, meta, params, updated_at) values (?, ?, ?, 0)",
            (
                model_id,
                json.dumps({"toolIds": ["existing_tool"], "capabilities": {"tools": False}}),
                json.dumps({"system": f"{model_id} system"}),
            ),
        )
    conn.commit()
    return conn


def test_freyja_core_bridge_content_is_thin_post_adapter() -> None:
    module = _module()
    content = module.CONTENT

    assert "def freyja_core_call(self, tool: str, arguments_json: str = \"{}\")" in content
    assert '"http://100.115.228.56:8510/tools/call"' in content
    assert '"tool": tool_name' in content
    assert '"arguments": arguments' in content
    assert 'method="POST"' in content
    assert "create_calendar_event" not in content
    assert "opencode_start" not in content
    assert "memory.write" not in content


def test_freyja_core_bridge_binds_models_without_removing_existing_tools(tmp_path: Path) -> None:
    module = _module()
    conn = _db(tmp_path / "webui.db")
    try:
        report = module.bind_models(conn, now=123)
        rows = {
            row[0]: (json.loads(row[1]), json.loads(row[2]))
            for row in conn.execute("select id, meta, params from model order by id").fetchall()
        }
        tool = tuple(conn.execute("select user_id, updated_at from tool where id = 'freyja_core_bridge'").fetchone())
    finally:
        conn.close()

    assert [row["model"] for row in report] == ["agent/freyja", "agent/cloyd-gibbler", "agent/freyja-coder"]
    assert tool == (module.JOE_USER_ID, 123)
    for meta, params in rows.values():
        assert meta["toolIds"] == ["existing_tool", "freyja_core_bridge"]
        assert meta["capabilities"]["function_calling"] is True
        assert meta["capabilities"]["tools"] is True
        assert "prefer the freyja_core_call tool" in params["system"]


def test_freyja_core_bridge_backup_copies_db_and_sidecars(tmp_path: Path) -> None:
    module = _module()
    db = tmp_path / "webui.db"
    db.write_text("db", encoding="utf-8")
    Path(str(db) + "-wal").write_text("wal", encoding="utf-8")
    Path(str(db) + "-shm").write_text("shm", encoding="utf-8")

    backup = module.backup_db(db, tmp_path / "backups", now=123)

    assert backup.read_text(encoding="utf-8") == "db"
    assert (backup.parent / "webui.db-wal.bak").read_text(encoding="utf-8") == "wal"
    assert (backup.parent / "webui.db-shm.bak").read_text(encoding="utf-8") == "shm"
