from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify-msty-nexus-core-posture.py"


def _module():
    spec = importlib.util.spec_from_file_location("verify_msty_nexus_core_posture", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_msty_posture_db_snapshot_redacts_api_key_and_checks_primary_bots(tmp_path: Path) -> None:
    module = _module()
    db = tmp_path / "msty-go.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "create table providers (id text, name text, type text, api_key text, base_url text, hidden integer, metadata_json text)"
    )
    conn.execute(
        "create table provider_custom_models (provider_id text, model_id text, display_name text, capabilities_json text)"
    )
    conn.execute(
        """
        create table bots (
            id text, name text, provider_id text, model text, shell_access_enabled integer,
            web_access_enabled integer, search_lens_enabled integer, custom_instructions text
        )
        """
    )
    conn.execute("create table mcp_servers (id text, name text, transport_type text, enabled integer)")
    conn.execute(
        """
        create table tool_call_usage_events (
            tool_name text, status text, provider_name text, provider_type text, model text,
            conversation_id text, message_id text, created_at text
        )
        """
    )
    conn.execute(
        "insert into providers values (?, ?, ?, ?, ?, ?, ?)",
        (
            "provider-1",
            "Vulcan Nexus",
            "openai",
            "secret-token",
            "http://100.94.80.21:3939/v1",
            0,
            json.dumps({"machine": "vulcan"}),
        ),
    )
    for preset in module.REQUIRED_PRESETS:
        conn.execute(
            "insert into provider_custom_models values (?, ?, ?, ?)",
            ("provider-1", preset, preset, json.dumps(["chat"])),
        )
    core_block = "Freyja Core tool gateway: POST /tools/call. Nexus/Vulcan is inference only."
    for bot_id in ("freyja", "cloyd-gibbler"):
        conn.execute(
            "insert into bots values (?, ?, ?, ?, 1, 1, 1, ?)",
            (bot_id, bot_id, "provider-1", "@preset/freyja-coder", core_block),
        )
    conn.commit()
    conn.close()

    snapshot = module._db_snapshot(db)

    assert snapshot["api_key"] == "secret-token"
    assert snapshot["provider"]["has_api_key"] is True
    assert "api_key" not in snapshot["provider"]
    assert {row["model_id"] for row in snapshot["custom_models"]} == module.REQUIRED_PRESETS
    assert all(row["has_core_gateway_block"] for row in snapshot["bots"])
