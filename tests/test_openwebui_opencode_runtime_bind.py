from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "ops" / "openwebui" / "bind_opencode_runtime_tool.py"
DAEMON_SCRIPT = REPO_ROOT / "ops" / "openwebui" / "cloyd_smith_loop_daemon.py"
AUTOMATION_PATCH_SCRIPT = REPO_ROOT / "ops" / "openwebui" / "patch_monitor_opencode_automation.py"


def _module():
    spec = importlib.util.spec_from_file_location("bind_opencode_runtime_tool", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _daemon_module():
    spec = importlib.util.spec_from_file_location("cloyd_smith_loop_daemon", DAEMON_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _automation_patch_module():
    spec = importlib.util.spec_from_file_location("patch_monitor_opencode_automation", AUTOMATION_PATCH_SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("create table tool (id text primary key, user_id text, updated_at integer)")
    conn.execute("create table model (id text primary key, meta text, params text, updated_at integer)")
    conn.execute("insert into tool (id, user_id, updated_at) values ('opencode_runtime', null, 0)")
    conn.execute("insert into tool (id, user_id, updated_at) values ('cloyd_smith_loop', null, 0)")
    for model_id in ("agent/freyja", "agent/cloyd-gibbler", "agent/freyja-coder"):
        conn.execute(
            "insert into model (id, meta, params, updated_at) values (?, ?, ?, 0)",
            (
                model_id,
                json.dumps({"toolIds": []}),
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
        tools = {
            row[0]: (row[1], row[2])
            for row in conn.execute("select id, user_id, updated_at from tool order by id").fetchall()
        }
    finally:
        conn.close()

    assert report["ok"] is True
    assert tools["opencode_runtime"] == (_module().JOE_USER_ID, 123)
    assert tools["cloyd_smith_loop"] == (_module().JOE_USER_ID, 123)
    assert rows["agent/freyja"][0]["toolIds"] == ["opencode_runtime", "cloyd_smith_loop"]
    assert rows["agent/freyja-coder"][0]["toolIds"] == ["opencode_runtime", "cloyd_smith_loop"]
    assert rows["agent/cloyd-gibbler"][0]["toolIds"] == ["opencode_runtime", "cloyd_smith_loop"]
    assert "OpenCode Runtime and Cloyd-Smith Loop tools are available" in rows["agent/freyja-coder"][1]["system"]
    assert "cloyd_smith_retry" in rows["agent/cloyd-gibbler"][1]["system"]
    assert "cloyd_smith_replace" in rows["agent/cloyd-gibbler"][1]["system"]


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
    assert "cloyd_smith_retry" in content
    assert "cloyd_smith_mark_done" in content
    assert "cloyd_smith_mark_blocked" in content
    assert "cloyd_smith_follow_up" in content
    assert "cloyd_smith_replace" in content
    assert "/agent-runs/api/jobs/{job_id}/replace" in content
    assert "http://100.115.228.56:8000" in content
    assert "/agent-runs/api/status" in content
    assert '"cloyd_smith_loop"' in content


def test_openwebui_json_ledger_daemon_is_deprecated() -> None:
    daemon = _daemon_module()

    result = daemon.run_once()

    assert result[0]["status"] == "deprecated"
    assert "local SQLite supervisor" in result[0]["message"]


def test_monitor_opencode_automation_patch_adds_supervisor_summary(tmp_path: Path) -> None:
    module = _automation_patch_module()
    automations = tmp_path / "automations.py"
    automations.write_text(
        "before\n"
        + module.OLD_LINES_BLOCK
        + "after\n",
        encoding="utf-8",
    )

    first = module.patch_file(automations)
    second = module.patch_file(automations)
    content = automations.read_text(encoding="utf-8")

    assert first["changed"] is True
    assert second["changed"] is False
    assert first["has_supervisor_summary"] is True
    assert "Supervisor:" in content
    assert "} open," in content
    assert "active, {status.get('attention_count'" not in content


def test_monitor_opencode_automation_patch_rejects_unknown_formatter(tmp_path: Path) -> None:
    module = _automation_patch_module()
    automations = tmp_path / "automations.py"
    automations.write_text("no monitor formatter here\n", encoding="utf-8")

    try:
        module.patch_file(automations)
    except ValueError as exc:
        assert "anchor not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")
