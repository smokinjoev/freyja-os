#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import httpx


DEFAULT_DB = Path("/Users/freyja/Library/Application Support/Msty Go/msty-go.db")
DEFAULT_CORE_URL = "http://100.115.228.56:8510"
DEFAULT_OUTPUT = Path("certification/reports/msty-nexus-core-posture-20260918.json")
REQUIRED_PRESETS = {
    "@preset/freyja-fast-local",
    "@preset/freyja-strong-local",
    "@preset/freyja-coder",
    "@preset/freyja-vision-docs",
    "@preset/freyja-private-local",
    "@preset/benedict-paralegal-local",
}
PRIMARY_BOTS = {"freyja", "cloyd-gibbler"}


def _load_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _db_snapshot(db: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        provider = conn.execute(
            "select id, name, type, api_key, base_url, hidden, metadata_json from providers where name = 'Vulcan Nexus'"
        ).fetchone()
        if provider is None:
            raise RuntimeError("Vulcan Nexus provider row is missing")
        custom_models = [
            dict(row)
            for row in conn.execute(
                "select model_id, display_name, capabilities_json from provider_custom_models where provider_id = ? order by model_id",
                (provider["id"],),
            )
        ]
        bots = [
            dict(row)
            for row in conn.execute(
                """
                select id, name, provider_id, model, shell_access_enabled, web_access_enabled,
                       search_lens_enabled, custom_instructions
                from bots
                where id in ('freyja','cloyd-gibbler','benedict','agent-47','jennacide','benedict-paralegal')
                order by id
                """
            )
        ]
        mcp_servers = [dict(row) for row in conn.execute("select id, name, transport_type, enabled from mcp_servers order by id")]
        recent_tool_events = [
            dict(row)
            for row in conn.execute(
                """
                select tool_name, status, provider_name, provider_type, model, conversation_id, message_id, created_at
                from tool_call_usage_events
                order by created_at desc
                limit 10
                """
            )
        ]
    finally:
        conn.close()

    provider_public = {
        "id": provider["id"],
        "name": provider["name"],
        "type": provider["type"],
        "base_url": provider["base_url"],
        "hidden": bool(provider["hidden"]),
        "metadata": _load_json(provider["metadata_json"], {}),
        "has_api_key": bool(provider["api_key"]),
    }
    bot_reports = []
    for bot in bots:
        instructions = bot.pop("custom_instructions") or ""
        bot_reports.append(
            {
                **bot,
                "shell_access_enabled": bool(bot["shell_access_enabled"]),
                "web_access_enabled": bool(bot["web_access_enabled"]),
                "search_lens_enabled": bool(bot["search_lens_enabled"]),
                "has_core_gateway_block": "Freyja Core tool gateway:" in instructions,
                "mentions_tools_call": "/tools/call" in instructions,
                "mentions_nexus_inference_only": "Nexus/Vulcan is inference only" in instructions,
            }
        )
    return {
        "provider": provider_public,
        "api_key": provider["api_key"] or "",
        "custom_models": custom_models,
        "bots": bot_reports,
        "mcp_servers": mcp_servers,
        "recent_tool_events": recent_tool_events,
    }


def _http_checks(provider: dict[str, Any], api_key: str, core_url: str) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    with httpx.Client(timeout=10) as client:
        nexus_base = str(provider["base_url"]).removesuffix("/v1")
        try:
            health = client.get(f"{nexus_base}/health")
            checks["nexus_health"] = {"ok": health.status_code == 200, "status_code": health.status_code}
        except Exception as exc:  # noqa: BLE001
            checks["nexus_health"] = {"ok": False, "error": str(exc)}
        try:
            models = client.get(
                f"{provider['base_url'].rstrip('/')}/models",
                headers={"authorization": f"Bearer {api_key}"} if api_key else {},
            )
            payload = models.json() if models.headers.get("content-type", "").startswith("application/json") else {}
            model_ids = [item.get("id") for item in payload.get("data", []) if isinstance(item, dict)]
            checks["nexus_models"] = {
                "ok": models.status_code == 200,
                "status_code": models.status_code,
                "preset_count": len([model for model in model_ids if str(model).startswith("@preset/")]),
                "required_presets_present": sorted(REQUIRED_PRESETS.intersection(model_ids)),
            }
        except Exception as exc:  # noqa: BLE001
            checks["nexus_models"] = {"ok": False, "error": str(exc)}
        try:
            core = client.post(
                f"{core_url.rstrip('/')}/tools/call",
                json={"tool": "status.check", "arguments": {}},
            )
            payload = core.json()
            checks["core_status"] = {
                "ok": core.status_code == 200 and payload.get("ok") is True,
                "status_code": core.status_code,
                "hostname": payload.get("hostname"),
                "configured_tools": payload.get("configured_tools"),
                "downstream": payload.get("downstream"),
            }
        except Exception as exc:  # noqa: BLE001
            checks["core_status"] = {"ok": False, "error": str(exc)}
        try:
            date = client.post(
                f"{core_url.rstrip('/')}/tools/call",
                json={"tool": "calendar.resolve_date", "arguments": {"phrase": "this weekend"}},
            )
            payload = date.json()
            checks["core_date"] = {
                "ok": date.status_code == 200 and payload.get("ok") is True,
                "status_code": date.status_code,
                "dates": payload.get("dates"),
            }
        except Exception as exc:  # noqa: BLE001
            checks["core_date"] = {"ok": False, "error": str(exc)}
    return checks


def build_report(db: Path, core_url: str) -> dict[str, Any]:
    snapshot = _db_snapshot(db)
    provider = snapshot["provider"]
    checks = _http_checks(provider, snapshot.pop("api_key"), core_url)
    custom_model_ids = {row["model_id"] for row in snapshot["custom_models"]}
    bots = {row["id"]: row for row in snapshot["bots"]}
    primary_ok = all(
        bot_id in bots
        and bots[bot_id]["provider_id"] == provider["id"]
        and bots[bot_id]["model"] == "@preset/freyja-coder"
        and bots[bot_id]["shell_access_enabled"]
        and bots[bot_id]["has_core_gateway_block"]
        and bots[bot_id]["mentions_tools_call"]
        and bots[bot_id]["mentions_nexus_inference_only"]
        for bot_id in PRIMARY_BOTS
    )
    ok = (
        provider["base_url"] == "http://100.94.80.21:3939/v1"
        and REQUIRED_PRESETS <= custom_model_ids
        and primary_ok
        and checks["nexus_health"].get("ok") is True
        and checks["nexus_models"].get("ok") is True
        and checks["core_status"].get("ok") is True
        and checks["core_date"].get("ok") is True
    )
    return {
        "report_type": "msty-nexus-core-posture",
        "generated_at_unix": int(time.time()),
        "ok": ok,
        "role_contract": {
            "msty_go": "primary named-agent UI",
            "nexus_vulcan": "inference plane only",
            "freyja_core_iris": "tool authority",
            "openwebui": "secondary/raw-model testing only",
        },
        "msty": snapshot,
        "checks": checks,
        "acceptance": {
            "primary_bots_route_to_nexus_coder_preset": primary_ok,
            "nexus_required_presets_present": REQUIRED_PRESETS <= custom_model_ids,
            "msty_mcp_servers_configured": bool(snapshot["mcp_servers"]),
            "msty_mcp_config_action": "not changed; keep shell+curl bridge until transport_config shape is proven",
            "core_status_check_passed": checks["core_status"].get("ok") is True,
            "core_date_check_passed": checks["core_date"].get("ok") is True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify Msty Go + Nexus + Freyja Core ownership posture.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--core-url", default=DEFAULT_CORE_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = build_report(args.db, args.core_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
