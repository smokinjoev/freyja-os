from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify-msty-freyja-core-routing.py"
spec = importlib.util.spec_from_file_location("verify_msty_freyja_core_routing", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def create_db(path: Path, *, instructions: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE bots (
                id TEXT PRIMARY KEY,
                name TEXT,
                model TEXT,
                shell_access_enabled INTEGER,
                web_access_enabled INTEGER,
                search_lens_enabled INTEGER,
                custom_instructions TEXT
            );
            CREATE TABLE tool_call_usage_events (
                id TEXT PRIMARY KEY,
                tool_name TEXT NOT NULL,
                status TEXT,
                model TEXT,
                conversation_id TEXT,
                session_id TEXT,
                message_id TEXT,
                created_at TEXT
            );
            CREATE TABLE messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT,
                role TEXT,
                content TEXT,
                tool_calls TEXT,
                metadata TEXT,
                sequence INTEGER,
                created_at TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO bots VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("freyja", "Freyja", "@preset/freyja-strong-local", 1, 1, 1, instructions),
        )
        conn.execute(
            "INSERT INTO tool_call_usage_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("event-1", "shell", "completed", "@preset/freyja-strong-local", "conv-1", "sess-1", "msg-1", "2026-09-17T13:00:00Z"),
        )
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "msg-1",
                "conv-1",
                "assistant",
                '["2026-09-19","2026-09-20"]',
                '[{"name":"shell","input":{"command":"curl -fsS http://127.0.0.1:8510/tools/call"},"status":"completed","isError":false}]',
                "{}",
                1,
                "2026-09-17T13:00:01Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_inspect_msty_db_accepts_core_routing_block(tmp_path: Path) -> None:
    db = tmp_path / "msty-go.db"
    create_db(
        db,
        instructions=(
            "Freyja Core tool gateway:\n"
            "- Use the shell tool to call POST /tools/call with curl when needed."
        ),
    )

    report = module.inspect_msty_db(db, since="2026-09-17T12:00:00Z")

    assert report["configured"] is True
    assert report["bot"]["shell_access_enabled"] is True
    assert report["bot"]["core_routing_block_present"] is True
    assert report["recent_core_tool_events"][0]["id"] == "event-1"
    assert report["recent_core_tool_messages"][0]["id"] == "msg-1"


def test_inspect_msty_db_rejects_missing_core_routing_block(tmp_path: Path) -> None:
    db = tmp_path / "msty-go.db"
    create_db(db, instructions="ordinary instructions")

    report = module.inspect_msty_db(db)

    assert report["configured"] is False
    assert report["bot"]["core_routing_block_present"] is False
