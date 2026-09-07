#!/usr/bin/env python3
"""Audit the current five-agent Msty Go/Nexus system state."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MSTY_DB = Path.home() / "Library/Application Support/Msty Go/msty-go.db"
DEFAULT_OUTPUT = REPO_ROOT / "certification/reports/five-agent-system-audit.json"
DEFAULT_APPLE_REPORT = REPO_ROOT / "certification/reports/five-agent-apple-preservation-live.json"
DEFAULT_OPEN_WEBUI_REPORT = REPO_ROOT / "certification/reports/open-webui-home-agent-completion-audit.json"
DEFAULT_OPEN_WEBUI_CHAT_SMOKE = REPO_ROOT / "certification/reports/open-webui-home-agent-chat-smoke.json"
DEFAULT_TELEGRAM_PILOT = REPO_ROOT / "certification/reports/freyja-channels-telegram-pilot.json"
DEFAULT_SIGNAL_PILOT = REPO_ROOT / "certification/reports/freyja-channels-signal-pilot.json"
DEFAULT_RESTART_PERSISTENCE = REPO_ROOT / "certification/reports/five-agent-msty-go-restart-persistence.json"
DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:8503"

AGENTS = {
    "freyja": {"name": "Freyja", "bot_id": "freyja", "model": "@preset/freyja-coder", "gateway_model": "agent/freyja"},
    "cloyd": {
        "name": "Cloyd",
        "bot_id": "cloyd-gibbler",
        "model": "@preset/freyja-coder",
        "gateway_model": "agent/cloyd-gibbler",
    },
    "benedict": {
        "name": "Benedict",
        "bot_id": "benedict",
        "model": "@preset/freyja-strong-local",
        "gateway_model": "agent/benedict",
    },
    "agent-44": {
        "name": "Agent 44",
        "bot_id": "agent-47",
        "model": "@preset/freyja-fast-local",
        "gateway_model": "agent/agent-47",
    },
    "jenna": {
        "name": "Jenna",
        "bot_id": "jennacide",
        "model": "@preset/freyja-fast-local",
        "gateway_model": "agent/jennacide",
    },
}

SHARED_MEMORY_PACK_ID = "freyja5-shared-household"
BENEDICT_PRIVATE_BOT_ID = "benedict-paralegal"
VULCAN_PROVIDER_ID = "vulcan-nexus"
VULCAN_BASE_URL = "http://100.94.80.21:3939/v1"
CANARY_TEXT = "Five-agent shared memory canary saved on 2026-09-05"
MSTY_GO_CHANNEL_DOCS_URL = "https://docs.msty.ai/go/channels"
MSTY_GO_MEMORY_DOCS_URL = "https://docs.msty.ai/go/memory-bank"
DOCUMENTED_MSTY_GO_CHANNELS = ["Discord", "Telegram", "WhatsApp", "Msty Go mobile route"]
DOCUMENTED_MSTY_GO_MEMORY_OWNERS = ["Conversations", "Agents", "Playbooks", "Scheduled jobs"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit five-agent Msty Go/Nexus live state.")
    parser.add_argument("--msty-db", type=Path, default=DEFAULT_MSTY_DB)
    parser.add_argument("--gateway-base-url", default=DEFAULT_GATEWAY_BASE_URL)
    parser.add_argument("--apple-report", type=Path, default=DEFAULT_APPLE_REPORT)
    parser.add_argument("--open-webui-report", type=Path, default=DEFAULT_OPEN_WEBUI_REPORT)
    parser.add_argument("--open-webui-chat-smoke", type=Path, default=DEFAULT_OPEN_WEBUI_CHAT_SMOKE)
    parser.add_argument("--telegram-pilot", type=Path, default=DEFAULT_TELEGRAM_PILOT)
    parser.add_argument("--signal-pilot", type=Path, default=DEFAULT_SIGNAL_PILOT)
    parser.add_argument("--restart-persistence", type=Path, default=DEFAULT_RESTART_PERSISTENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--token", default=os.environ.get("FREYJA_CONNECTOR_TOKEN"))
    parser.add_argument("--nexus-api-key", default=os.environ.get("NEXUS_API_KEY"))
    parser.add_argument("--gateway-chat-timeout", type=int, default=90)
    parser.add_argument("--skip-gateway-live", action="store_true")
    return parser


def build_audit(
    *,
    msty_db: Path,
    gateway_base_url: str = DEFAULT_GATEWAY_BASE_URL,
    apple_report: Path = DEFAULT_APPLE_REPORT,
    open_webui_report: Path = DEFAULT_OPEN_WEBUI_REPORT,
    open_webui_chat_smoke: Path = DEFAULT_OPEN_WEBUI_CHAT_SMOKE,
    telegram_pilot: Path = DEFAULT_TELEGRAM_PILOT,
    signal_pilot: Path = DEFAULT_SIGNAL_PILOT,
    restart_persistence: Path = DEFAULT_RESTART_PERSISTENCE,
    token: str | None = None,
    nexus_api_key: str | None = None,
    gateway_chat_timeout: int = 90,
    skip_gateway_live: bool = False,
) -> dict[str, Any]:
    db_status = inspect_msty_db(msty_db, expected_nexus_api_key=nexus_api_key)
    native_recall = db_status["native_recall"]
    gateway_status = (
        {"status": "skipped", "ok": None, "agents": {}}
        if skip_gateway_live
        else inspect_gateway(gateway_base_url, token=token, chat_timeout=gateway_chat_timeout)
    )
    apple_status = inspect_apple_report(apple_report)
    open_webui_status = inspect_open_webui(open_webui_report, open_webui_chat_smoke)
    channel_round_trips = inspect_channel_round_trips(telegram_pilot, signal_pilot)
    restart_status = inspect_restart_persistence(restart_persistence)

    requirements = [
        _requirement(
            "A",
            "Five named persistent Msty Go agents exist with expected provider and models.",
            db_status["agents_ok"],
            db_status["agent_issues"],
            {"agents": db_status["agents"]},
        ),
        _requirement(
            "B",
            "All five model requests route through Vulcan Msty Nexus.",
            db_status["provider_ok"] and db_status["agents_ok"],
            db_status["provider_issues"] + db_status["agent_issues"],
            {"provider": db_status["provider"]},
        ),
        _requirement(
            "C",
            "Each agent has a scoped gateway endpoint/config.",
            gateway_status["ok"] is True,
            gateway_status.get("issues", []),
            {"gateway": gateway_status},
        ),
        _requirement(
            "D",
            "Shared Msty Go memory pool is mounted to the five agents and excludes Benedict protected material.",
            db_status["memory_ok"],
            db_status["memory_issues"],
            {"memory": db_status["memory"]},
        ),
        _requirement(
            "E",
            "Telegram access is bound through Msty Go integrations for all five agents.",
            db_status["telegram_ok"],
            db_status["telegram_issues"],
            {"telegram": db_status["telegram"]},
        ),
        _requirement(
            "F",
            "Signal access is available through Msty Go integrations.",
            db_status["signal_ok"],
            db_status["signal_issues"],
            {"signal": db_status["signal"]},
        ),
        _requirement(
            "G",
            "Open WebUI uses the same existing agents when straightforwardly supported.",
            open_webui_status["ok"] is True,
            open_webui_status["issues"],
            {"open_webui": open_webui_status},
        ),
        _requirement(
            "H",
            "Freyja Apple services remain on Iris and are preserved.",
            apple_status["ok"] is True,
            apple_status["issues"],
            {"apple": apple_status},
        ),
        _requirement(
            "I",
            "Native Msty Go chat recall of the shared canary is proven.",
            native_recall["ok"],
            native_recall["issues"],
            {"canary": CANARY_TEXT, "native_recall": native_recall},
        ),
        _requirement(
            "J",
            "Live Telegram/Signal round trips are proven from allowed senders.",
            channel_round_trips["ok"],
            channel_round_trips["issues"],
            {"channel_round_trips": channel_round_trips},
        ),
    ]
    incomplete = [item["id"] for item in requirements if item["status"] != "complete"]
    report = {
        "schema_version": "1.0",
        "report_type": "five-agent-system-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if not incomplete else "incomplete",
        "ok": not incomplete,
        "msty_db": str(msty_db),
        "restart_persistence": restart_status,
        "agents": per_agent_summary(db_status, gateway_status, open_webui_status),
        "requirements": requirements,
        "incomplete_requirements": incomplete,
    }
    return report


def per_agent_summary(
    db_status: dict[str, Any],
    gateway_status: dict[str, Any],
    open_webui_status: dict[str, Any],
) -> dict[str, Any]:
    summary = {}
    for slug, expected in AGENTS.items():
        bot = db_status.get("agents", {}).get(slug) or {}
        telegram = db_status.get("telegram", {}).get("bindings_by_bot", {}).get(expected["bot_id"], [])
        signal = db_status.get("signal", {}).get("bindings_by_bot", {}).get(expected["bot_id"], [])
        gateway = gateway_status.get("agents", {}).get(slug) or {}
        summary[slug] = {
            "display_name": expected["name"],
            "host": "Iris Msty Go",
            "bot_id": expected["bot_id"],
            "msty_model": bot.get("model"),
            "provider_id": bot.get("provider_id"),
            "gateway_endpoint": gateway.get("chat_url")
            or f"{DEFAULT_GATEWAY_BASE_URL}/agents/{slug}/v1/chat/completions",
            "gateway_model": expected["gateway_model"],
            "access_methods": {
                "msty_go": bool(bot),
                "telegram": bool(telegram),
                "signal": bool(signal),
                "open_webui": expected["gateway_model"] in set(open_webui_status.get("chat_smoke_models") or []),
            },
            "test_results": {
                "msty_go_agent_row": bool(bot),
                "vulcan_nexus_provider": bot.get("provider_id") == VULCAN_PROVIDER_ID,
                "gateway_models": gateway.get("models_ok") is True,
                "gateway_chat": gateway.get("chat_ok") is True,
                "shared_memory_mounted": expected["bot_id"] in set(db_status.get("memory", {}).get("mounted_bot_ids") or []),
                "telegram_binding": bool(telegram),
                "signal_binding": bool(signal),
                "open_webui_chat": expected["gateway_model"] in set(open_webui_status.get("chat_smoke_models") or []),
            },
        }
    return summary


def inspect_channel_round_trips(telegram_pilot: Path, signal_pilot: Path) -> dict[str, Any]:
    telegram = inspect_channel_pilot(telegram_pilot, "telegram")
    signal = inspect_channel_pilot(signal_pilot, "signal")
    issues = []
    if telegram["ok"] is not True:
        issues.append("telegram_live_roundtrip_not_proven")
    if signal["ok"] is not True:
        issues.append("signal_live_roundtrip_not_proven")
    return {
        "ok": not issues,
        "issues": issues,
        "telegram": telegram,
        "signal": signal,
    }


def inspect_restart_persistence(path: Path) -> dict[str, Any]:
    payload = _load_json_optional(path)
    if payload is None:
        return {"path": str(path), "ok": False, "issues": ["restart_persistence_report_missing"]}
    required_true = [
        "msty_go_restarted",
        "provider_key_matches_nexus_after_restart",
        "five_agent_rows_persisted",
        "shared_memory_bot_mounts_persisted",
        "recall_conversation_mounts_persisted",
        "native_recall_attempt_messages_persisted",
    ]
    issues = [f"{key}_not_proven" for key in required_true if payload.get(key) is not True]
    if payload.get("secrets_included") is not False:
        issues.append("restart_persistence_report_secret_safety_unproven")
    return {
        "path": str(path),
        "ok": not issues,
        "issues": issues,
        "report_type": payload.get("report_type"),
        "timestamp": payload.get("timestamp"),
        "checks": {key: payload.get(key) for key in required_true},
    }


def inspect_channel_pilot(path: Path, channel: str) -> dict[str, Any]:
    payload = _load_json_optional(path)
    if payload is None:
        return {"path": str(path), "ok": False, "issues": [f"{channel}_pilot_report_missing"]}
    totals = payload.get("totals") if isinstance(payload.get("totals"), dict) else {}
    handled = int(totals.get("handled") or 0)
    complete = payload.get("live_round_trip_complete") is True and handled > 0
    issues = []
    if payload.get("live_round_trip_complete") is not True:
        issues.append(f"{channel}_live_roundtrip_incomplete")
    if handled <= 0:
        issues.append(f"{channel}_handled_zero")
    failure = payload.get("failure") if isinstance(payload.get("failure"), dict) else {}
    if failure:
        reason = failure.get("reason") or failure.get("exception_type") or "unknown"
        issues.append(f"{channel}_failure:{reason}")
    return {
        "path": str(path),
        "ok": complete,
        "issues": issues,
        "report_type": payload.get("report_type"),
        "mode": payload.get("mode"),
        "ready": payload.get("ready"),
        "live_round_trip_complete": payload.get("live_round_trip_complete"),
        "handled": handled,
        "totals": totals,
        "next_actions": payload.get("next_actions") if isinstance(payload.get("next_actions"), list) else [],
    }


def inspect_msty_db(path: Path, *, expected_nexus_api_key: str | None = None) -> dict[str, Any]:
    if not path.exists():
        issues = [f"msty_db_missing:{path}"]
        return _empty_db_status(issues)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        provider = _one(
            con,
            "SELECT id, name, type, base_url, hidden, api_key FROM providers WHERE id = ?",
            (VULCAN_PROVIDER_ID,),
        )
        bots = {
            row["id"]: dict(row)
            for row in con.execute(
                "SELECT id, name, provider_id, model, status, workspace_path FROM bots WHERE id IN (%s)"
                % ",".join("?" for _ in [*AGENTS.values(), {"bot_id": BENEDICT_PRIVATE_BOT_ID}]),
                tuple([agent["bot_id"] for agent in AGENTS.values()] + [BENEDICT_PRIVATE_BOT_ID]),
            )
        }
        bindings = [dict(row) for row in con.execute("SELECT bot_id, platform, channel_id, trigger_word, is_primary FROM bot_bindings")]
        memory = inspect_memory(con)
        native_recall = inspect_native_recall(con)
    finally:
        con.close()

    provider_issues = []
    if not provider:
        provider_issues.append("vulcan_nexus_provider_missing")
    elif provider["base_url"] != VULCAN_BASE_URL:
        provider_issues.append("vulcan_nexus_provider_base_url_mismatch")
    if provider and expected_nexus_api_key and provider["api_key"] != expected_nexus_api_key:
        provider_issues.append("vulcan_nexus_provider_api_key_mismatch")

    agent_rows, agent_issues = {}, []
    for slug, expected in AGENTS.items():
        row = bots.get(expected["bot_id"])
        if not row:
            agent_issues.append(f"{slug}_bot_missing")
            continue
        agent_rows[slug] = _select(row, ["id", "name", "provider_id", "model", "status", "workspace_path"])
        if row["provider_id"] != VULCAN_PROVIDER_ID:
            agent_issues.append(f"{slug}_provider_mismatch")
        if row["model"] != expected["model"]:
            agent_issues.append(f"{slug}_model_mismatch")

    telegram = inspect_bindings(bindings, "telegram")
    signal = inspect_bindings(bindings, "signal")
    return {
        "provider_ok": not provider_issues,
        "provider_issues": provider_issues,
        "provider": _provider_evidence(provider, expected_nexus_api_key=expected_nexus_api_key) if provider else None,
        "agents_ok": not agent_issues and len(agent_rows) == len(AGENTS),
        "agent_issues": agent_issues,
        "agents": agent_rows,
        "memory_ok": memory["ok"],
        "memory_issues": memory["issues"],
        "memory": memory,
        "telegram_ok": telegram["ok"],
        "telegram_issues": telegram["issues"],
        "telegram": telegram,
        "signal_ok": signal["ok"],
        "signal_issues": signal["issues"],
        "signal": signal,
        "native_recall": native_recall,
    }


def inspect_native_recall(con: sqlite3.Connection) -> dict[str, Any]:
    expected_bot_ids = {agent["bot_id"] for agent in AGENTS.values()}
    rows = [
        dict(row)
        for row in con.execute(
            """
            SELECT c.bot_id, m.role, count(*) AS hit_count, max(m.created_at) AS latest_hit_at
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            WHERE m.content LIKE ?
              AND c.bot_id IN (%s)
            GROUP BY c.bot_id, m.role
            """
            % ",".join("?" for _ in expected_bot_ids),
            tuple([f"%{CANARY_TEXT}%"] + sorted(expected_bot_ids)),
        )
    ]
    hits_by_bot: dict[str, dict[str, Any]] = {}
    for row in rows:
        hits_by_bot.setdefault(row["bot_id"], {})[row["role"]] = {
            "hit_count": row["hit_count"],
            "latest_hit_at": row["latest_hit_at"],
        }
    recalled_by = sorted(
        bot_id
        for bot_id, roles in hits_by_bot.items()
        if (roles.get("assistant") or {}).get("hit_count", 0) > 0
    )
    raw_attempts = [
        dict(row)
        for row in con.execute(
            """
            SELECT
              c.bot_id,
              user_msg.conversation_id,
              user_msg.created_at,
              (
                SELECT assistant_msg.content
                FROM messages assistant_msg
                WHERE assistant_msg.conversation_id = user_msg.conversation_id
                  AND assistant_msg.role = 'assistant'
                  AND assistant_msg.sequence > user_msg.sequence
                ORDER BY assistant_msg.sequence
                LIMIT 1
              ) AS assistant_content
            FROM messages user_msg
            JOIN conversations c ON c.id = user_msg.conversation_id
            WHERE user_msg.role = 'user'
              AND user_msg.content LIKE ?
              AND c.bot_id IN (%s)
            """
            % ",".join("?" for _ in expected_bot_ids),
            tuple(["%Memory recall validation%five-agent memory canary%2026-09-05%"] + sorted(expected_bot_ids)),
        )
    ]
    attempts: dict[str, dict[str, Any]] = {}
    for row in raw_attempts:
        item = attempts.setdefault(
            row["bot_id"],
            {
                "prompt_count": 0,
                "not_found_count": 0,
                "error_count": 0,
                "pending_count": 0,
                "latest_prompt_at": None,
            },
        )
        content = (row["assistant_content"] or "").strip()
        item["prompt_count"] += 1
        item["not_found_count"] += 1 if content == "NOT FOUND" else 0
        item["error_count"] += 1 if "**Error:**" in content else 0
        item["pending_count"] += 1 if not content else 0
        if item["latest_prompt_at"] is None or row["created_at"] > item["latest_prompt_at"]:
            item["latest_prompt_at"] = row["created_at"]
    attempt_conversation_ids = [
        row["conversation_id"]
        for row in con.execute(
            """
            SELECT DISTINCT user_msg.conversation_id
            FROM messages user_msg
            JOIN conversations c ON c.id = user_msg.conversation_id
            WHERE user_msg.role = 'user'
              AND user_msg.content LIKE ?
              AND c.bot_id IN (%s)
            """
            % ",".join("?" for _ in expected_bot_ids),
            tuple(["%Memory recall validation%five-agent memory canary%2026-09-05%"] + sorted(expected_bot_ids)),
        )
    ]
    conversation_mounts = []
    if attempt_conversation_ids:
        conversation_mounts = [
            dict(row)
            for row in con.execute(
                """
                SELECT owner_id AS conversation_id, pack_id
                FROM memory_mounts
                WHERE owner_type = 'conversation'
                  AND owner_id IN (%s)
                ORDER BY owner_id, pack_id
                """
                % ",".join("?" for _ in attempt_conversation_ids),
                tuple(attempt_conversation_ids),
            )
        ]
    issues = [] if recalled_by else ["native_msty_go_chat_recall_not_proven"]
    return {
        "ok": bool(recalled_by),
        "issues": issues,
        "assistant_recalled_by_bot_ids": recalled_by,
        "conversation_canary_hits_by_bot": hits_by_bot,
        "attempt_conversation_ids": sorted(attempt_conversation_ids),
        "attempt_conversation_memory_mounts": conversation_mounts,
        "recall_attempts_by_bot": attempts,
        "documentation_url": MSTY_GO_MEMORY_DOCS_URL,
        "documented_memory_owners": DOCUMENTED_MSTY_GO_MEMORY_OWNERS,
        "limitation": (
            "Shared memory is attached through documented Agent and Conversation owners, "
            "but native Msty Go chat has not recalled the canary."
        ),
    }


def _provider_evidence(row: sqlite3.Row, *, expected_nexus_api_key: str | None) -> dict[str, Any]:
    evidence = _select(row, ["id", "name", "type", "base_url", "hidden"])
    api_key = row["api_key"] or ""
    evidence["api_key_configured"] = bool(api_key)
    evidence["api_key_length"] = len(api_key)
    evidence["api_key_matches_expected_nexus_key"] = bool(expected_nexus_api_key and api_key == expected_nexus_api_key)
    return evidence


def inspect_memory(con: sqlite3.Connection) -> dict[str, Any]:
    pack = _one(
        con,
        "SELECT id, title, current_revision_id, archived FROM memory_packs WHERE id = ?",
        (SHARED_MEMORY_PACK_ID,),
    )
    mounts = [
        row["owner_id"]
        for row in con.execute(
            "SELECT owner_id FROM memory_mounts WHERE owner_type = 'bot' AND pack_id = ?",
            (SHARED_MEMORY_PACK_ID,),
        )
    ]
    canary_rows = [
        dict(row)
        for row in con.execute(
            "SELECT id, revision_number, state_json FROM memory_pack_revisions WHERE pack_id = ? ORDER BY revision_number",
            (SHARED_MEMORY_PACK_ID,),
        )
        if CANARY_TEXT in (row["state_json"] or "")
    ]
    search_doc = _one(
        con,
        """
        SELECT pack_id, revision_id, title, tags_json, content_text
        FROM memory_pack_search_docs
        WHERE pack_id = ?
        """,
        (SHARED_MEMORY_PACK_ID,),
    )
    search_doc_contains_canary = bool(search_doc and CANARY_TEXT in (search_doc["content_text"] or ""))
    expected_mounts = {agent["bot_id"] for agent in AGENTS.values()}
    issues = []
    if not pack:
        issues.append("shared_memory_pack_missing")
    if set(mounts) & {BENEDICT_PRIVATE_BOT_ID}:
        issues.append("benedict_protected_bot_mounted_to_shared_pack")
    missing_mounts = sorted(expected_mounts - set(mounts))
    if missing_mounts:
        issues.extend(f"shared_memory_mount_missing:{bot_id}" for bot_id in missing_mounts)
    if not canary_rows:
        issues.append("shared_memory_canary_revision_missing")
    if not search_doc_contains_canary:
        issues.append("shared_memory_canary_search_doc_missing")
    return {
        "ok": not issues,
        "issues": issues,
        "pack": _select(pack, ["id", "title", "current_revision_id", "archived"]) if pack else None,
        "mounted_bot_ids": sorted(mounts),
        "canary_revision_ids": [row["id"] for row in canary_rows],
        "search_doc": {
            "present": search_doc is not None,
            "revision_id": search_doc["revision_id"] if search_doc else None,
            "contains_canary": search_doc_contains_canary,
            "tags_json": search_doc["tags_json"] if search_doc else None,
        },
    }


def inspect_bindings(bindings: list[dict[str, Any]], platform: str) -> dict[str, Any]:
    by_bot = {agent["bot_id"]: [] for agent in AGENTS.values()}
    for binding in bindings:
        if binding.get("platform") == platform and binding.get("bot_id") in by_bot:
            by_bot[binding["bot_id"]].append(_select(binding, ["channel_id", "trigger_word", "is_primary"]))
    missing = [bot_id for bot_id, rows in by_bot.items() if not rows]
    result = {
        "ok": not missing,
        "issues": [f"{platform}_binding_missing:{bot_id}" for bot_id in missing],
        "bindings_by_bot": by_bot,
    }
    if platform == "signal":
        result["documented_supported_platforms"] = DOCUMENTED_MSTY_GO_CHANNELS
        result["documentation_url"] = MSTY_GO_CHANNEL_DOCS_URL
        result["limitation"] = "Signal is not listed in the current official Msty Go channel platform list."
    return result


def inspect_gateway(base_url: str, *, token: str | None = None, chat_timeout: int = 90) -> dict[str, Any]:
    agents, issues = {}, []
    for slug, expected in AGENTS.items():
        models_url = f"{base_url.rstrip('/')}/agents/{slug}/v1/models"
        chat_url = f"{base_url.rstrip('/')}/agents/{slug}/v1/chat/completions"
        agent_status: dict[str, Any] = {
            "ok": False,
            "models_url": models_url,
            "chat_url": chat_url,
            "auth": "bearer" if token else "none",
        }
        try:
            payload = _http_json("GET", models_url, timeout=3, token=token)
            models = [item.get("id") for item in payload.get("data", []) if isinstance(item, dict)]
            models_ok = models == [expected["gateway_model"]]
            if not models_ok:
                issues.append(f"{slug}_gateway_model_scope_mismatch")
            agent_status.update({"models_ok": models_ok, "models": models})
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            issues.append(f"{slug}_gateway_unreachable")
            agent_status.update({"models_ok": False, "models_error": str(exc)})
            agents[slug] = agent_status
            continue
        try:
            chat_payload = {
                "model": "agent/freyja",
                "messages": [{"role": "user", "content": f"Five-agent gateway audit for {expected['name']}. Reply briefly."}],
                "stream": False,
                "temperature": 0,
                "max_tokens": 64,
            }
            payload = _http_json("POST", chat_url, timeout=chat_timeout, token=token, payload=chat_payload)
            metadata = payload.get("freyja") if isinstance(payload.get("freyja"), dict) else {}
            choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
            content = ""
            if choices and isinstance(choices[0], dict):
                content = (choices[0].get("message") or {}).get("content") or ""
            chat_ok = (
                bool(content.strip())
                and metadata.get("agent_model") == expected["gateway_model"]
                and metadata.get("provider") == "nexus"
                and metadata.get("egress_state") == "local-only"
            )
            if not chat_ok:
                issues.append(f"{slug}_gateway_chat_route_mismatch")
            agent_status.update(
                {
                    "chat_ok": chat_ok,
                    "response_present": bool(content.strip()),
                    "agent": metadata.get("agent"),
                    "agent_model": metadata.get("agent_model"),
                    "provider": metadata.get("provider"),
                    "egress_state": metadata.get("egress_state"),
                    "endpoint": metadata.get("endpoint"),
                }
            )
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            issues.append(f"{slug}_gateway_chat_unreachable")
            agent_status.update({"chat_ok": False, "chat_error": str(exc)})
        agent_status["ok"] = agent_status.get("models_ok") is True and agent_status.get("chat_ok") is True
        agents[slug] = agent_status
    return {"status": "checked", "ok": not issues, "issues": issues, "agents": agents}


def inspect_apple_report(path: Path) -> dict[str, Any]:
    payload = _load_json_optional(path)
    if payload is None:
        return {"path": str(path), "ok": False, "issues": ["apple_preservation_report_missing"]}
    issues = list(payload.get("incomplete") or [])
    return {"path": str(path), "ok": payload.get("ok") is True, "issues": issues, "report_type": payload.get("report_type")}


def inspect_open_webui(report_path: Path, chat_smoke_path: Path) -> dict[str, Any]:
    completion = _load_json_optional(report_path)
    chat_smoke = _load_json_optional(chat_smoke_path)
    if chat_smoke is None:
        return {
            "path": str(report_path),
            "chat_smoke_path": str(chat_smoke_path),
            "ok": False,
            "issues": ["open_webui_chat_smoke_missing"],
            "completion_report_type": completion.get("report_type") if completion else None,
        }
    checks = chat_smoke.get("checks") if isinstance(chat_smoke.get("checks"), list) else []
    expected_models = {agent["gateway_model"] for agent in AGENTS.values()}
    smoke_models = {str(check.get("open_webui_model_id")) for check in checks if isinstance(check, dict)}
    failed_agents = [
        str(check.get("agent_id") or check.get("open_webui_model_id"))
        for check in checks
        if isinstance(check, dict) and check.get("ok") is not True
    ]
    missing_models = sorted(expected_models - smoke_models)
    issues = []
    if chat_smoke.get("complete") is not True or chat_smoke.get("status") != "complete":
        issues.append("open_webui_chat_smoke_not_complete")
    issues.extend(f"open_webui_chat_failed:{agent}" for agent in failed_agents)
    issues.extend(f"open_webui_model_missing:{model}" for model in missing_models)
    return {
        "path": str(report_path),
        "chat_smoke_path": str(chat_smoke_path),
        "ok": not issues,
        "issues": issues,
        "completion_report_type": completion.get("report_type") if completion else None,
        "completion_complete": completion.get("complete") if completion else None,
        "completion_status_counts": completion.get("status_counts") if completion else None,
        "chat_smoke_report_type": chat_smoke.get("report_type"),
        "chat_smoke_complete": chat_smoke.get("complete"),
        "chat_smoke_models": sorted(smoke_models),
    }


def _requirement(requirement_id: str, description: str, ok: bool, issues: list[str], evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": requirement_id,
        "description": description,
        "status": "complete" if ok else "incomplete",
        "issues": issues,
        "evidence": evidence,
    }


def _empty_db_status(issues: list[str]) -> dict[str, Any]:
    return {
        "provider_ok": False,
        "provider_issues": issues,
        "provider": None,
        "agents_ok": False,
        "agent_issues": issues,
        "agents": {},
        "memory_ok": False,
        "memory_issues": issues,
        "memory": {"ok": False, "issues": issues},
        "telegram_ok": False,
        "telegram_issues": issues,
        "telegram": {"ok": False, "issues": issues, "bindings_by_bot": {}},
        "signal_ok": False,
        "signal_issues": issues,
        "signal": {"ok": False, "issues": issues, "bindings_by_bot": {}},
        "native_recall": {"ok": False, "issues": issues, "assistant_recalled_by_bot_ids": [], "conversation_canary_hits_by_bot": {}},
    }


def _one(con: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
    return con.execute(sql, params).fetchone()


def _select(row: dict[str, Any] | sqlite3.Row | None, keys: list[str]) -> dict[str, Any]:
    if row is None:
        return {}
    available = set(row.keys())
    return {key: row[key] for key in keys if key in available}


def _http_json(
    method: str,
    url: str,
    *,
    timeout: int,
    token: str | None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _load_json_optional(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    return payload if isinstance(payload, dict) else {}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_audit(
        msty_db=args.msty_db,
        gateway_base_url=args.gateway_base_url,
        apple_report=args.apple_report,
        open_webui_report=args.open_webui_report,
        open_webui_chat_smoke=args.open_webui_chat_smoke,
        telegram_pilot=args.telegram_pilot,
        signal_pilot=args.signal_pilot,
        restart_persistence=args.restart_persistence,
        token=args.token,
        nexus_api_key=args.nexus_api_key,
        gateway_chat_timeout=args.gateway_chat_timeout,
        skip_gateway_live=args.skip_gateway_live,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
