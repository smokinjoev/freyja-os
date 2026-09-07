from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "five-agent-system-audit.py"


def load_audit_module():
    spec = importlib.util.spec_from_file_location("five_agent_system_audit", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_msty_db(path: Path, *, include_signal: bool = False) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE providers (
          id TEXT PRIMARY KEY,
          name TEXT,
          type TEXT,
          base_url TEXT,
          hidden INTEGER,
          api_key TEXT
        );
        CREATE TABLE bots (
          id TEXT PRIMARY KEY,
          name TEXT,
          provider_id TEXT,
          model TEXT,
          status TEXT,
          workspace_path TEXT
        );
        CREATE TABLE bot_bindings (
          bot_id TEXT,
          platform TEXT,
          channel_id TEXT,
          trigger_word TEXT,
          is_primary INTEGER
        );
        CREATE TABLE memory_packs (
          id TEXT PRIMARY KEY,
          title TEXT,
          current_revision_id TEXT,
          archived INTEGER
        );
        CREATE TABLE memory_mounts (
          owner_type TEXT,
          owner_id TEXT,
          pack_id TEXT
        );
        CREATE TABLE memory_pack_revisions (
          id TEXT PRIMARY KEY,
          pack_id TEXT,
          revision_number INTEGER,
          state_json TEXT
        );
        CREATE TABLE memory_pack_search_docs (
          pack_id TEXT PRIMARY KEY,
          revision_id TEXT,
          title TEXT,
          tags_json TEXT,
          content_text TEXT
        );
        CREATE TABLE conversations (
          id TEXT PRIMARY KEY,
          bot_id TEXT
        );
        CREATE TABLE messages (
          id TEXT PRIMARY KEY,
          conversation_id TEXT,
          role TEXT,
          content TEXT,
          sequence INTEGER,
          created_at TEXT
        );
        """
    )
    con.execute(
        "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?)",
        ("vulcan-nexus", "Vulcan Nexus", "openai", "http://100.94.80.21:3939/v1", 0, "expected-nexus-key"),
    )
    agents = load_audit_module().AGENTS
    for slug, agent in agents.items():
        con.execute(
            "INSERT INTO bots VALUES (?, ?, ?, ?, ?, ?)",
            (agent["bot_id"], agent["name"], "vulcan-nexus", agent["model"], "ready", f"workspaces/{slug}"),
        )
        con.execute(
            "INSERT INTO bot_bindings VALUES (?, ?, ?, ?, ?)",
            (agent["bot_id"], "telegram", "telegram-freyja-home", slug, 1),
        )
        if include_signal:
            con.execute(
                "INSERT INTO bot_bindings VALUES (?, ?, ?, ?, ?)",
                (agent["bot_id"], "signal", "signal-freyja-home", slug, 1),
            )
        con.execute(
            "INSERT INTO memory_mounts VALUES (?, ?, ?)",
            ("bot", agent["bot_id"], "freyja5-shared-household"),
        )
    con.execute(
        "INSERT INTO bots VALUES (?, ?, ?, ?, ?, ?)",
        ("benedict-paralegal", "Benedict Paralegal", "vulcan-nexus", "@preset/benedict-paralegal-local", "ready", "workspaces/benedict-paralegal"),
    )
    con.execute(
        "INSERT INTO memory_packs VALUES (?, ?, ?, ?)",
        ("freyja5-shared-household", "Freyja 5 Shared Household Memory", "rev2", 0),
    )
    con.execute(
        "INSERT INTO memory_pack_revisions VALUES (?, ?, ?, ?)",
        (
            "rev2",
            "freyja5-shared-household",
            2,
            json.dumps({"items": [{"text": "Five-agent shared memory canary saved on 2026-09-05 for persistence."}]}),
        ),
    )
    con.execute(
        "INSERT INTO memory_pack_search_docs VALUES (?, ?, ?, ?, ?)",
        (
            "freyja5-shared-household",
            "rev2",
            "Freyja 5 Shared Household Memory",
            json.dumps(["five-agent-system", "shared-memory", "canary"]),
            "Five-agent shared memory canary saved on 2026-09-05 for persistence.",
        ),
    )
    con.commit()
    con.close()


def write_channel_pilot(path: Path, *, channel: str, complete: bool = False, handled: int = 0) -> None:
    path.write_text(
        json.dumps(
            {
                "report_type": f"freyja-channels-{channel}-pilot",
                "mode": "run",
                "ready": complete,
                "live_round_trip_complete": complete,
                "totals": {"handled": handled},
                "next_actions": [] if complete else [f"Complete {channel} live round trip."],
            }
        ),
        encoding="utf-8",
    )


def write_restart_report(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "report_type": "five-agent-msty-go-restart-persistence",
                "timestamp": "2026-09-05T18:32:00Z",
                "msty_go_restarted": True,
                "provider_key_matches_nexus_after_restart": True,
                "five_agent_rows_persisted": True,
                "shared_memory_bot_mounts_persisted": True,
                "recall_conversation_mounts_persisted": True,
                "native_recall_attempt_messages_persisted": True,
                "secrets_included": False,
            }
        ),
        encoding="utf-8",
    )


def test_audit_maps_msty_db_and_reports_partial_live_proofs(tmp_path: Path) -> None:
    audit_module = load_audit_module()
    db = tmp_path / "msty-go.db"
    apple = tmp_path / "apple.json"
    open_webui = tmp_path / "open-webui.json"
    chat_smoke = tmp_path / "chat-smoke.json"
    telegram_pilot = tmp_path / "telegram-pilot.json"
    signal_pilot = tmp_path / "signal-pilot.json"
    restart = tmp_path / "restart.json"
    create_msty_db(db)
    write_channel_pilot(telegram_pilot, channel="telegram")
    write_channel_pilot(signal_pilot, channel="signal")
    write_restart_report(restart)
    apple.write_text(json.dumps({"report_type": "five-agent-apple-preservation-live", "ok": True, "incomplete": []}), encoding="utf-8")
    open_webui.write_text(
        json.dumps(
            {
                "report_type": "open-webui-home-agent-completion-audit",
                "status": "incomplete",
                "complete": False,
                "remaining_blockers": ["protected_open_webui_containers_absent"],
            }
        ),
        encoding="utf-8",
    )
    chat_smoke.write_text(
        json.dumps(
            {
                "report_type": "open-webui-home-agent-chat-smoke",
                "status": "complete",
                "complete": True,
                "checks": [
                    {"agent_id": "freyja", "open_webui_model_id": "agent/freyja", "ok": True},
                    {"agent_id": "cloyd", "open_webui_model_id": "agent/cloyd-gibbler", "ok": True},
                    {"agent_id": "benedict", "open_webui_model_id": "agent/benedict", "ok": True},
                    {"agent_id": "agent-44", "open_webui_model_id": "agent/agent-47", "ok": True},
                    {"agent_id": "jenna", "open_webui_model_id": "agent/jennacide", "ok": True},
                ],
            }
        ),
        encoding="utf-8",
    )

    report = audit_module.build_audit(
        msty_db=db,
        apple_report=apple,
        open_webui_report=open_webui,
        open_webui_chat_smoke=chat_smoke,
        telegram_pilot=telegram_pilot,
        signal_pilot=signal_pilot,
        restart_persistence=restart,
        nexus_api_key="expected-nexus-key",
        skip_gateway_live=True,
    )
    requirements = {item["id"]: item for item in report["requirements"]}

    assert report["status"] == "incomplete"
    assert report["restart_persistence"]["ok"] is True
    assert report["agents"]["freyja"]["host"] == "Iris Msty Go"
    assert report["agents"]["freyja"]["gateway_endpoint"].endswith("/agents/freyja/v1/chat/completions")
    assert report["agents"]["freyja"]["access_methods"] == {
        "msty_go": True,
        "telegram": True,
        "signal": False,
        "open_webui": True,
    }
    assert report["agents"]["freyja"]["test_results"]["shared_memory_mounted"] is True
    assert requirements["A"]["status"] == "complete"
    assert requirements["B"]["status"] == "complete"
    assert requirements["B"]["evidence"]["provider"]["api_key_matches_expected_nexus_key"] is True
    assert requirements["D"]["status"] == "complete"
    assert requirements["D"]["evidence"]["memory"]["search_doc"]["contains_canary"] is True
    assert requirements["E"]["status"] == "complete"
    assert requirements["F"]["issues"] == [
        "signal_binding_missing:freyja",
        "signal_binding_missing:cloyd-gibbler",
        "signal_binding_missing:benedict",
        "signal_binding_missing:agent-47",
        "signal_binding_missing:jennacide",
    ]
    assert requirements["F"]["evidence"]["signal"]["documentation_url"] == "https://docs.msty.ai/go/channels"
    assert "Signal is not listed" in requirements["F"]["evidence"]["signal"]["limitation"]
    assert requirements["G"]["status"] == "complete"
    assert requirements["G"]["evidence"]["open_webui"]["completion_complete"] is False
    assert requirements["H"]["status"] == "complete"
    assert requirements["I"]["issues"] == ["native_msty_go_chat_recall_not_proven"]
    assert requirements["I"]["evidence"]["native_recall"]["conversation_canary_hits_by_bot"] == {}
    assert requirements["I"]["evidence"]["native_recall"]["documentation_url"] == "https://docs.msty.ai/go/memory-bank"
    assert "Agents" in requirements["I"]["evidence"]["native_recall"]["documented_memory_owners"]
    assert requirements["J"]["issues"] == ["telegram_live_roundtrip_not_proven", "signal_live_roundtrip_not_proven"]


def test_audit_detects_benedict_private_memory_mount(tmp_path: Path) -> None:
    audit_module = load_audit_module()
    db = tmp_path / "msty-go.db"
    create_msty_db(db, include_signal=True)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO memory_mounts VALUES (?, ?, ?)", ("bot", "benedict-paralegal", "freyja5-shared-household"))
    con.commit()
    con.close()

    status = audit_module.inspect_msty_db(db)

    assert status["memory_ok"] is False
    assert "benedict_protected_bot_mounted_to_shared_pack" in status["memory_issues"]


def test_audit_detects_provider_api_key_mismatch(tmp_path: Path) -> None:
    audit_module = load_audit_module()
    db = tmp_path / "msty-go.db"
    create_msty_db(db, include_signal=True)

    status = audit_module.inspect_msty_db(db, expected_nexus_api_key="different-key")

    assert status["provider_ok"] is False
    assert "vulcan_nexus_provider_api_key_mismatch" in status["provider_issues"]
    assert status["provider"]["api_key_configured"] is True
    assert status["provider"]["api_key_matches_expected_nexus_key"] is False


def test_audit_detects_missing_memory_search_doc_canary(tmp_path: Path) -> None:
    audit_module = load_audit_module()
    db = tmp_path / "msty-go.db"
    create_msty_db(db, include_signal=True)
    con = sqlite3.connect(db)
    con.execute("UPDATE memory_pack_search_docs SET content_text = 'stale memory index'")
    con.commit()
    con.close()

    status = audit_module.inspect_msty_db(db)

    assert status["memory_ok"] is False
    assert "shared_memory_canary_search_doc_missing" in status["memory_issues"]


def test_audit_detects_native_msty_recall_conversation_hit(tmp_path: Path) -> None:
    audit_module = load_audit_module()
    db = tmp_path / "msty-go.db"
    create_msty_db(db, include_signal=True)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO conversations VALUES (?, ?)", ("conv-1", "cloyd-gibbler"))
    con.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
        (
            "msg-1",
            "conv-1",
            "assistant",
            "Five-agent shared memory canary saved on 2026-09-05 for persistence.",
            1,
            "2026-09-05T12:00:00Z",
        ),
    )
    con.commit()
    con.close()

    status = audit_module.inspect_msty_db(db)

    assert status["native_recall"]["ok"] is True
    assert status["native_recall"]["assistant_recalled_by_bot_ids"] == ["cloyd-gibbler"]


def test_audit_records_native_msty_not_found_recall_attempt(tmp_path: Path) -> None:
    audit_module = load_audit_module()
    db = tmp_path / "msty-go.db"
    create_msty_db(db, include_signal=True)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO conversations VALUES (?, ?)", ("conv-1", "cloyd-gibbler"))
    con.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
        (
            "msg-1",
            "conv-1",
            "user",
            "Memory recall validation. A shared five-agent memory canary was saved on 2026-09-05. Without guessing, reply with the exact saved canary sentence if it is available in your Msty Go memory. If it is not available, reply exactly: NOT FOUND",
            1,
            "2026-09-05T12:00:00Z",
        ),
    )
    con.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
        ("msg-2", "conv-1", "assistant", "NOT FOUND", 2, "2026-09-05T12:00:05Z"),
    )
    con.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
        (
            "msg-3",
            "conv-1",
            "user",
            "Memory recall validation retry after mounting the shared memory pack on this conversation. A shared five-agent memory canary was saved on 2026-09-05. Without guessing, reply with the exact saved canary sentence if it is available in your Msty Go memory. If it is not available, reply exactly: NOT FOUND",
            3,
            "2026-09-05T12:01:00Z",
        ),
    )
    con.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
        ("msg-4", "conv-1", "assistant", "NOT FOUND", 4, "2026-09-05T12:01:05Z"),
    )
    con.execute("INSERT INTO memory_mounts VALUES (?, ?, ?)", ("conversation", "conv-1", "freyja5-shared-household"))
    con.commit()
    con.close()

    status = audit_module.inspect_msty_db(db)

    assert status["native_recall"]["ok"] is False
    assert status["native_recall"]["recall_attempts_by_bot"] == {
        "cloyd-gibbler": {
            "prompt_count": 2,
            "not_found_count": 2,
            "error_count": 0,
            "pending_count": 0,
            "latest_prompt_at": "2026-09-05T12:01:00Z",
        }
    }
    assert status["native_recall"]["attempt_conversation_ids"] == ["conv-1"]
    assert status["native_recall"]["attempt_conversation_memory_mounts"] == [
        {"conversation_id": "conv-1", "pack_id": "freyja5-shared-household"}
    ]
    assert "native Msty Go chat has not recalled" in status["native_recall"]["limitation"]


def test_audit_records_native_msty_error_recall_attempt(tmp_path: Path) -> None:
    audit_module = load_audit_module()
    db = tmp_path / "msty-go.db"
    create_msty_db(db, include_signal=True)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO conversations VALUES (?, ?)", ("conv-1", "freyja"))
    con.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
        (
            "msg-1",
            "conv-1",
            "user",
            "Memory recall validation. A shared five-agent memory canary was saved on 2026-09-05. Without guessing, reply with the exact saved canary sentence if it is available in your Msty Go memory. If it is not available, reply exactly: NOT FOUND",
            1,
            "2026-09-05T12:00:00Z",
        ),
    )
    con.execute(
        "INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?)",
        ("msg-2", "conv-1", "assistant", "**Error:** Request canceled", 2, "2026-09-05T12:00:05Z"),
    )
    con.commit()
    con.close()

    status = audit_module.inspect_msty_db(db)

    assert status["native_recall"]["ok"] is False
    assert status["native_recall"]["recall_attempts_by_bot"]["freyja"] == {
        "prompt_count": 1,
        "not_found_count": 0,
        "error_count": 1,
        "pending_count": 0,
        "latest_prompt_at": "2026-09-05T12:00:00Z",
    }


def test_audit_cli_writes_report(tmp_path: Path, capsys) -> None:
    audit_module = load_audit_module()
    db = tmp_path / "msty-go.db"
    output = tmp_path / "audit.json"
    telegram_pilot = tmp_path / "telegram-pilot.json"
    signal_pilot = tmp_path / "signal-pilot.json"
    restart = tmp_path / "restart.json"
    create_msty_db(db, include_signal=True)
    write_channel_pilot(telegram_pilot, channel="telegram")
    write_channel_pilot(signal_pilot, channel="signal")
    write_restart_report(restart)

    assert (
        audit_module.main(
            [
                "--msty-db",
                str(db),
                "--telegram-pilot",
                str(telegram_pilot),
                "--signal-pilot",
                str(signal_pilot),
                "--restart-persistence",
                str(restart),
                "--skip-gateway-live",
                "--output",
                str(output),
            ]
        )
        == 2
    )

    printed = json.loads(capsys.readouterr().out)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert printed["report_type"] == "five-agent-system-audit"
    assert written["requirements"] == printed["requirements"]


def test_audit_requires_all_five_open_webui_chat_smoke_models(tmp_path: Path) -> None:
    audit_module = load_audit_module()
    completion = tmp_path / "completion.json"
    chat_smoke = tmp_path / "chat-smoke.json"
    completion.write_text(json.dumps({"report_type": "open-webui-home-agent-completion-audit"}), encoding="utf-8")
    chat_smoke.write_text(
        json.dumps(
            {
                "report_type": "open-webui-home-agent-chat-smoke",
                "status": "complete",
                "complete": True,
                "checks": [
                    {"agent_id": "freyja", "open_webui_model_id": "agent/freyja", "ok": True},
                ],
            }
        ),
        encoding="utf-8",
    )

    status = audit_module.inspect_open_webui(completion, chat_smoke)

    assert status["ok"] is False
    assert "open_webui_model_missing:agent/cloyd-gibbler" in status["issues"]
    assert "open_webui_model_missing:agent/jennacide" in status["issues"]


def test_channel_round_trip_audit_requires_handled_messages(tmp_path: Path) -> None:
    audit_module = load_audit_module()
    telegram_pilot = tmp_path / "telegram-pilot.json"
    signal_pilot = tmp_path / "signal-pilot.json"
    write_channel_pilot(telegram_pilot, channel="telegram", complete=True, handled=1)
    write_channel_pilot(signal_pilot, channel="signal", complete=False, handled=0)

    status = audit_module.inspect_channel_round_trips(telegram_pilot, signal_pilot)

    assert status["ok"] is False
    assert status["telegram"]["ok"] is True
    assert status["signal"]["issues"] == ["signal_live_roundtrip_incomplete", "signal_handled_zero"]
    assert status["issues"] == ["signal_live_roundtrip_not_proven"]


def test_restart_persistence_audit_requires_secret_safe_checks(tmp_path: Path) -> None:
    audit_module = load_audit_module()
    restart = tmp_path / "restart.json"
    write_restart_report(restart)

    status = audit_module.inspect_restart_persistence(restart)

    assert status["ok"] is True
    assert status["checks"]["provider_key_matches_nexus_after_restart"] is True

    payload = json.loads(restart.read_text(encoding="utf-8"))
    payload["secrets_included"] = True
    restart.write_text(json.dumps(payload), encoding="utf-8")

    status = audit_module.inspect_restart_persistence(restart)

    assert status["ok"] is False
    assert "restart_persistence_report_secret_safety_unproven" in status["issues"]


def test_gateway_audit_checks_models_and_chat_metadata(monkeypatch) -> None:
    audit_module = load_audit_module()
    calls = []

    def fake_http_json(method, url, *, timeout, token, payload=None):
        calls.append({"method": method, "url": url, "timeout": timeout, "token": token, "payload": payload})
        slug = url.split("/agents/", 1)[1].split("/", 1)[0]
        expected = audit_module.AGENTS[slug]["gateway_model"]
        if method == "GET":
            return {"data": [{"id": expected}]}
        return {
            "choices": [{"message": {"content": "online"}}],
            "freyja": {
                "agent_model": expected,
                "provider": "nexus",
                "egress_state": "local-only",
                "endpoint": "vulcan-nexus",
            },
        }

    monkeypatch.setattr(audit_module, "_http_json", fake_http_json)

    status = audit_module.inspect_gateway("http://gateway.test", token="secret", chat_timeout=123)

    assert status["ok"] is True
    assert status["issues"] == []
    assert all(agent["models_ok"] and agent["chat_ok"] for agent in status["agents"].values())
    post_calls = [call for call in calls if call["method"] == "POST"]
    assert len(post_calls) == 5
    assert {call["payload"]["model"] for call in post_calls} == {"agent/freyja"}
    assert {call["timeout"] for call in post_calls} == {123}
    assert {call["token"] for call in calls} == {"secret"}


def test_audit_script_is_executable() -> None:
    assert SCRIPT_PATH.exists()
