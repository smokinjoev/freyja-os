#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path("/app/backend/data/webui.db")
DEFAULT_RESOURCES = REPO_ROOT / "certification" / "reports" / "open-webui-home-resources-export.json"
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-home-agent-post-auth-activation.json"
DEFAULT_OPEN_WEBUI_CONTAINER = "freyja-open-webui-atlas-open-webui-1"


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the post-auth Freyja Open WebUI activation sequence.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--resources-json", type=Path, default=DEFAULT_RESOURCES)
    parser.add_argument("--script-dir", type=Path, default=REPO_ROOT / "scripts")
    parser.add_argument("--owner-user-id", help="Existing Open WebUI owner/admin user ID for resource rows.")
    parser.add_argument("--apply", action="store_true", help="Apply activation. Default is dry-run.")
    parser.add_argument(
        "--open-webui-container",
        default=DEFAULT_OPEN_WEBUI_CONTAINER,
        help="Open WebUI container to snapshot for dry-run planning when --db is unavailable.",
    )
    parser.add_argument(
        "--no-container-snapshot",
        action="store_true",
        help="Do not snapshot the Open WebUI container for dry-run planning.",
    )
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _run_live_verifier() -> dict[str, Any]:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "open-webui-home-agent-verify.py"),
            "--model-proxy-url",
            "http://127.0.0.1:3001/openai",
            "--output",
            str(REPO_ROOT / "certification" / "reports" / "open-webui-home-agent-live.json"),
        ],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return {"returncode": proc.returncode, "ran": True}


def _helpers(script_dir: Path):
    access = _load_module(script_dir / "bind-open-webui-home-agent-access.py")
    resources = _load_module(script_dir / "apply-open-webui-home-resources-offline.py")
    return access, resources


def snapshot_open_webui_database(container: str, target_dir: Path) -> Path | None:
    target_dir.mkdir(parents=True, exist_ok=True)
    copied_main = False
    for filename in ("webui.db", "webui.db-wal", "webui.db-shm"):
        proc = subprocess.run(
            ["docker", "cp", f"{container}:/app/backend/data/{filename}", str(target_dir / filename)],
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if filename == "webui.db":
            copied_main = proc.returncode == 0
    return target_dir / "webui.db" if copied_main else None


def build_activation_plan(db: Path, resources_json: Path, owner_user_id: str | None, script_dir: Path = REPO_ROOT / "scripts") -> dict[str, Any]:
    if not db.exists():
        return {
            "ready": False,
            "reason": "Open WebUI database is not available at the requested path",
            "db": str(db),
            "access": {"ready": False, "reason": "database unavailable"},
            "resources": {"ready": False, "reason": "database unavailable"},
        }
    if not resources_json.exists():
        return {
            "ready": False,
            "reason": "Open WebUI resource export is not available at the requested path",
            "resources_json": str(resources_json),
            "access": {"ready": False, "reason": "resource export unavailable"},
            "resources": {"ready": False, "reason": "resource export unavailable"},
        }
    access_helper, resource_helper = _helpers(script_dir)
    payload = resource_helper.load_import(resources_json)
    conn = sqlite3.connect(db)
    try:
        access = access_helper.plan(conn)
        resource_helper.inspect_schema(conn)
        owner = resource_helper.resolve_owner(conn, owner_user_id)
        user_count = conn.execute("select count(*) from user").fetchone()[0]
        resource_rows = resource_helper.build_rows(payload, owner) if owner else None
        resource_plan: dict[str, Any] = {
            "ready": owner is not None,
            "owner_user_id_resolved": owner is not None,
            "owner_resolution_policy": "explicit_owner_user_id" if owner_user_id else "auto_single_user_only",
            "user_count": int(user_count),
            "reason": None if owner else "missing or ambiguous Open WebUI owner user",
            "knowledge_count": len(payload.get("knowledge") or []),
            "tool_count": len(payload.get("tools") or []),
            "memory_policy_count": len((payload.get("native_memory") or {}).get("private_preferences") or {}),
        }
        if resource_rows:
            for table, rows in resource_rows.items():
                ids = [row["id"] for row in rows]
                existing = resource_helper.count_existing(conn, table, ids)
                resource_plan[f"{table}_insert_count"] = len([row_id for row_id in ids if row_id not in existing])
                resource_plan[f"{table}_update_count"] = len([row_id for row_id in ids if row_id in existing])
        return {
            "access": access,
            "resources": resource_plan,
            "ready": bool(access.get("ready") and resource_plan.get("ready")),
        }
    finally:
        conn.close()


def apply_activation(db: Path, resources_json: Path, owner_user_id: str | None, backup_dir: Path | None, script_dir: Path = REPO_ROOT / "scripts") -> dict[str, Any]:
    access_helper, resource_helper = _helpers(script_dir)
    payload = resource_helper.load_import(resources_json)
    conn = sqlite3.connect(db)
    try:
        access_report = access_helper.plan(conn)
        resource_helper.inspect_schema(conn)
        owner = resource_helper.resolve_owner(conn, owner_user_id)
        if not access_report.get("ready") or owner is None:
            return {"applied": False, "reason": "activation plan is not ready"}
        access_backup = access_helper._backup_database(db, backup_dir)
        access_helper.apply_plan(conn, access_report)
        resource_rows = resource_helper.build_rows(payload, owner)
        resource_backup = resource_helper._backup_database(db, backup_dir)
        resource_helper.upsert(conn, resource_rows)
        conn.commit()
        return {"applied": True, "access_backup": str(access_backup), "resource_backup": str(resource_backup)}
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot_source = None
    with tempfile.TemporaryDirectory(prefix="open-webui-home-agent-db-") as tmp:
        db = args.db
        if not args.apply and not args.no_container_snapshot and not db.exists():
            snapshot = snapshot_open_webui_database(args.open_webui_container, Path(tmp))
            if snapshot is not None:
                db = snapshot
                snapshot_source = {
                    "container": args.open_webui_container,
                    "source": "/app/backend/data/webui.db",
                    "wal_and_shm_attempted": True,
                }
        plan = build_activation_plan(db, args.resources_json, args.owner_user_id, args.script_dir)
    report: dict[str, Any] = {
        "report_type": "open-webui-home-agent-post-auth-activation",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "mode": "apply" if args.apply else "dry-run",
        "secrets_included": False,
        "private_content_included": False,
        "ready": plan["ready"],
        "plan": plan,
    }
    if snapshot_source is not None:
        report["dry_run_snapshot"] = snapshot_source
    if args.apply:
        if not plan["ready"]:
            result = {"applied": False, "reason": plan.get("reason") or "activation plan is not ready"}
        else:
            result = apply_activation(args.db, args.resources_json, args.owner_user_id, args.backup_dir, args.script_dir)
        report["apply_result"] = result
        if result.get("applied"):
            report["live_verifier"] = _run_live_verifier()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not args.apply or bool(report.get("apply_result", {}).get("applied")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
