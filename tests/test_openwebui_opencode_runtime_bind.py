from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "ops" / "openwebui" / "bind_opencode_runtime_tool.py"


def _module():
    spec = importlib.util.spec_from_file_location("bind_opencode_runtime_tool", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("create table tool (id text primary key, user_id text, updated_at integer)")
    conn.execute("create table model (id text primary key, meta text, params text, updated_at integer)")
    conn.execute("insert into tool (id, user_id, updated_at) values ('opencode_runtime', null, 0)")
    for model_id in ("agent/freyja", "agent/cloyd-gibbler", "agent/freyja-coder"):
        conn.execute(
            "insert into model (id, meta, params, updated_at) values (?, ?, ?, 0)",
            (
                model_id,
                json.dumps({"toolIds": ["opencode_runtime"] if model_id == "agent/cloyd-gibbler" else []}),
                json.dumps({"system": f"{model_id} system"}),
            ),
        )
    conn.commit()
    return conn


def test_bind_opencode_runtime_only_attaches_to_coding_agents(tmp_path: Path) -> None:
    conn = _db(tmp_path / "webui.db")
    try:
        report = _module().apply(conn, now=123)
        rows = {
            row[0]: (json.loads(row[1]), json.loads(row[2]))
            for row in conn.execute("select id, meta, params from model").fetchall()
        }
        tool = conn.execute("select user_id, updated_at from tool where id = 'opencode_runtime'").fetchone()
    finally:
        conn.close()

    assert report["ok"] is True
    assert tuple(tool) == (_module().JOE_USER_ID, 123)
    assert rows["agent/freyja"][0]["toolIds"] == ["opencode_runtime"]
    assert rows["agent/freyja-coder"][0]["toolIds"] == ["opencode_runtime"]
    assert rows["agent/cloyd-gibbler"][0]["toolIds"] == []
    assert "OpenCode Runtime tool is available" in rows["agent/freyja-coder"][1]["system"]
    assert "OpenCode Runtime tool is available" not in rows["agent/cloyd-gibbler"][1]["system"]


def test_openwebui_opencode_runtime_supports_atlas_and_iris_aliases() -> None:
    content = (REPO_ROOT / "ops" / "openwebui" / "create_iris_tools.py").read_text(encoding="utf-8")

    assert '"atlas-dashboard"' in content
    assert '"http://100.119.235.114:4097"' in content
    assert '"/home/joe/cloyd-services"' in content
    assert '"freyja-code"' in content
    assert '"http://100.115.228.56:4097"' in content
    assert '"/Users/freyja/freyja-os"' in content
    assert "opencode-iris-password" in content


def test_openwebui_includes_cloyd_smith_loop_tool() -> None:
    content = (REPO_ROOT / "ops" / "openwebui" / "create_iris_tools.py").read_text(encoding="utf-8")

    assert "CLOYD_SMITH_LOOP" in content
    assert "cloyd_smith_submit" in content
    assert "cloyd_smith_status" in content
    assert "cloyd_smith_stop" in content
    assert "cloyd-smith-loop-jobs.json" in content
    assert '"cloyd_smith_loop"' in content
