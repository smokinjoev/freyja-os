from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "activate-open-webui-home-agent-post-auth.py"
AGENTS_APPLY = REPO_ROOT / "scripts" / "apply-open-webui-home-agents-offline.py"
AGENTS_EXPORT = REPO_ROOT / "scripts" / "export-open-webui-home-agents.py"
RESOURCES_EXPORT = REPO_ROOT / "scripts" / "export-open-webui-home-resources.py"


def _module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _db(path: Path, *, users: bool) -> None:
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
                username VARCHAR(50),
                created_at BIGINT
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
        for table, columns in {
            "knowledge": "id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL, description TEXT, meta JSON, created_at BIGINT NOT NULL, updated_at BIGINT, data JSON",
            "tool": "id VARCHAR PRIMARY KEY, user_id VARCHAR, name TEXT, content TEXT, specs TEXT, meta TEXT, valves TEXT, updated_at BIGINT, created_at BIGINT",
            "memory": "id VARCHAR PRIMARY KEY, user_id VARCHAR, content TEXT, updated_at BIGINT, created_at BIGINT, type VARCHAR NOT NULL DEFAULT 'context', path TEXT, meta JSON",
        }.items():
            conn.execute(f"CREATE TABLE {table} ({columns})")
        if users:
            conn.executemany(
                "insert into user (id, name, email, username, created_at) values (?, ?, ?, ?, ?)",
                [
                    ("owner-joe", "Joe", "joe@example.invalid", "joe", 1),
                    ("user-beth", "Beth", "beth@example.invalid", "beth", 2),
                    ("user-liam", "Liam", "liam@example.invalid", "liam", 3),
                    ("user-jenna", "Jenna", "jenna@example.invalid", "jenna", 4),
                ],
            )
        conn.commit()
    finally:
        conn.close()


def _write_imports(tmp_path: Path) -> tuple[Path, Path]:
    agent_import = tmp_path / "agents.json"
    resource_import = tmp_path / "resources.json"
    agent_import.write_text(json.dumps(_module(AGENTS_EXPORT).build_export()), encoding="utf-8")
    resources = _module(RESOURCES_EXPORT).build_export()
    resources["ok"] = True
    resources["validation_errors"] = []
    resource_import.write_text(json.dumps(resources), encoding="utf-8")
    return agent_import, resource_import


def _import_agents(db: Path, agent_import: Path, tmp_path: Path) -> None:
    assert _module(AGENTS_APPLY).main(["--apply", "--import-json", str(agent_import), "--db", str(db), "--backup-dir", str(tmp_path)]) == 0


def test_post_auth_activation_plan_fails_closed_when_database_is_missing(tmp_path: Path) -> None:
    _, resource_import = _write_imports(tmp_path)

    plan = _module(SCRIPT).build_activation_plan(tmp_path / "missing-webui.db", resource_import, None)

    assert plan["ready"] is False
    assert plan["reason"] == "Open WebUI database is not available at the requested path"
    assert plan["access"]["reason"] == "database unavailable"
    assert plan["resources"]["reason"] == "database unavailable"


def test_post_auth_activation_main_can_dry_run_from_container_snapshot(tmp_path: Path, monkeypatch, capsys) -> None:
    db = tmp_path / "source-webui.db"
    _db(db, users=False)
    agent_import, resource_import = _write_imports(tmp_path)
    _import_agents(db, agent_import, tmp_path)
    module = _module(SCRIPT)
    output = tmp_path / "activation.json"
    capsys.readouterr()

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
    monkeypatch.setattr(module, "_git_head", lambda: "test-head")

    assert module.main(["--db", str(tmp_path / "missing.db"), "--resources-json", str(resource_import), "--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert isinstance(written["generated_at_unix"], int)
    assert written["git_head"] == "test-head"
    assert written["dry_run_snapshot"]["container"] == module.DEFAULT_OPEN_WEBUI_CONTAINER
    assert written["plan"]["access"]["missing_models"] == []
    assert written["plan"]["access"]["missing_users"] == ["beth", "jenna", "joe", "liam"]


def test_post_auth_activation_apply_does_not_use_container_snapshot(tmp_path: Path, monkeypatch, capsys) -> None:
    _, resource_import = _write_imports(tmp_path)
    module = _module(SCRIPT)
    output = tmp_path / "activation.json"
    capsys.readouterr()

    def fail_if_called(*args, **kwargs):
        raise AssertionError("snapshot should not be used in apply mode")

    monkeypatch.setattr(module.subprocess, "run", fail_if_called)
    monkeypatch.setattr(module, "_git_head", lambda: "test-head")

    assert (
        module.main(
            [
                "--apply",
                "--db",
                str(tmp_path / "missing.db"),
                "--resources-json",
                str(resource_import),
                "--output",
                str(output),
            ]
        )
        == 1
    )

    printed = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == printed
    assert "dry_run_snapshot" not in printed
    assert isinstance(printed["generated_at_unix"], int)
    assert printed["git_head"] == "test-head"
    assert printed["plan"]["reason"] == "Open WebUI database is not available at the requested path"
    assert printed["apply_result"]["applied"] is False


def test_post_auth_activation_plan_is_not_ready_without_users(tmp_path: Path) -> None:
    db = tmp_path / "webui.db"
    _db(db, users=False)
    agent_import, resource_import = _write_imports(tmp_path)
    _import_agents(db, agent_import, tmp_path)

    plan = _module(SCRIPT).build_activation_plan(db, resource_import, None)

    assert plan["ready"] is False
    assert plan["access"]["missing_users"] == ["beth", "jenna", "joe", "liam"]
    assert plan["resources"]["reason"] == "missing or ambiguous Open WebUI owner user"
    assert plan["resources"]["owner_resolution_policy"] == "auto_single_user_only"
    assert plan["resources"]["user_count"] == 0
    assert _module(SCRIPT).activation_next_actions(plan) == [
        "Create/sign in Open WebUI users for: beth, jenna, joe, liam.",
        "Complete first-account onboarding, or pass --owner-user-id when multiple Open WebUI users exist.",
    ]


def test_post_auth_activation_apply_binds_access_and_resources(tmp_path: Path) -> None:
    db = tmp_path / "webui.db"
    _db(db, users=True)
    agent_import, resource_import = _write_imports(tmp_path)
    _import_agents(db, agent_import, tmp_path)
    module = _module(SCRIPT)

    plan = module.build_activation_plan(db, resource_import, "owner-joe")
    assert plan["ready"] is True
    assert plan["resources"]["owner_resolution_policy"] == "explicit_owner_user_id"
    assert plan["resources"]["user_count"] == 4
    result = module.apply_activation(db, resource_import, "owner-joe", tmp_path)
    assert result["applied"] is True

    conn = sqlite3.connect(db)
    try:
        assert conn.execute('select count(*) from "group"').fetchone()[0] == 4
        assert conn.execute("select count(*) from group_member").fetchone()[0] == 4
        assert conn.execute("select count(*) from access_grant").fetchone()[0] == 10
        assert conn.execute("select count(*) from knowledge").fetchone()[0] == 3
        assert conn.execute("select count(*) from tool").fetchone()[0] == 6
        assert conn.execute("select count(*) from memory").fetchone()[0] == 4
    finally:
        conn.close()


def test_post_auth_activation_plan_auto_resolves_single_owner_user(tmp_path: Path) -> None:
    db = tmp_path / "webui.db"
    _db(db, users=True)
    conn = sqlite3.connect(db)
    try:
        conn.execute("delete from user where id != 'owner-joe'")
        conn.commit()
    finally:
        conn.close()
    agent_import, resource_import = _write_imports(tmp_path)
    _import_agents(db, agent_import, tmp_path)

    plan = _module(SCRIPT).build_activation_plan(db, resource_import, None)

    assert plan["resources"]["ready"] is True
    assert plan["resources"]["owner_user_id_resolved"] is True
    assert plan["resources"]["owner_resolution_policy"] == "auto_single_user_only"
    assert plan["resources"]["user_count"] == 1
    assert plan["ready"] is False
    assert _module(SCRIPT).activation_next_actions(plan) == [
        "Create/sign in Open WebUI users for: beth, jenna, liam.",
    ]


def test_post_auth_activation_main_apply_returns_zero_when_applied(tmp_path: Path, monkeypatch, capsys) -> None:
    db = tmp_path / "webui.db"
    _db(db, users=True)
    agent_import, resource_import = _write_imports(tmp_path)
    _import_agents(db, agent_import, tmp_path)
    module = _module(SCRIPT)
    output = tmp_path / "activation.json"
    monkeypatch.setattr(module, "_run_live_verifier", lambda: {"returncode": 0, "ran": True})
    capsys.readouterr()

    assert (
        module.main(
            [
                "--apply",
                "--db",
                str(db),
                "--resources-json",
                str(resource_import),
                "--owner-user-id",
                "owner-joe",
                "--backup-dir",
                str(tmp_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )

    printed = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == printed
    assert isinstance(printed["generated_at_unix"], int)
    assert printed["git_head"]
    assert printed["apply_result"]["applied"] is True
    assert printed["live_verifier"] == {"returncode": 0, "ran": True}
    assert printed["next_actions"] == [
        "Run this script again with --apply against the writable Open WebUI database.",
        "After apply succeeds, run the five-agent authenticated chat smoke with OPEN_WEBUI_API_KEY set.",
    ]
