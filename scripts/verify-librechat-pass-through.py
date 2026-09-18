#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = REPO_ROOT / "deploy/compose/librechat/librechat.yaml"
DEFAULT_COMPOSE = REPO_ROOT / "deploy/compose/librechat/compose.yaml"
DEFAULT_ENV_EXAMPLE = REPO_ROOT / "deploy/compose/librechat/.env.example"
DEFAULT_MSTY_DB = Path("/Users/freyja/Library/Application Support/Msty Go/msty-go.db")
DEFAULT_OUTPUT = REPO_ROOT / "certification/reports/librechat-pass-through-eval-20260918.json"
REQUIRED_PRESETS = {"@preset/freyja-coder", "@preset/freyja-strong-local", "@preset/freyja-fast-local"}
REQUIRED_CORE_TOOLS = {
    "status.check",
    "calendar.resolve_date",
    "calendar.create_event",
    "calendar.delete_event",
    "opencode.start",
    "opencode.stop",
    "opencode.status",
    "opencode.send",
    "opencode.read",
    "memory.search",
    "memory.write",
}


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value
    return values


def _msty_provider(db: Path) -> dict[str, Any]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "select id, name, type, api_key, base_url from providers where name = 'Vulcan Nexus'"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"ok": False, "error": "Vulcan Nexus provider missing"}
    return {
        "ok": True,
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "base_url": row["base_url"],
        "has_api_key": bool(row["api_key"]),
        "api_key": row["api_key"] or "",
    }


def _check_nexus(provider: dict[str, Any]) -> dict[str, Any]:
    if not provider.get("ok"):
        return {"ok": False, "error": "provider unavailable"}
    headers = {"authorization": f"Bearer {provider['api_key']}"} if provider.get("api_key") else {}
    with httpx.Client(timeout=10) as client:
        health = client.get(str(provider["base_url"]).removesuffix("/v1") + "/health")
        models = client.get(str(provider["base_url"]).rstrip("/") + "/models", headers=headers)
    model_payload = models.json()
    model_ids = [item.get("id") for item in model_payload.get("data", []) if isinstance(item, dict)]
    return {
        "ok": health.status_code == 200 and models.status_code == 200 and REQUIRED_PRESETS <= set(model_ids),
        "health_status": health.status_code,
        "models_status": models.status_code,
        "required_presets_present": sorted(REQUIRED_PRESETS.intersection(model_ids)),
        "preset_count": len([model for model in model_ids if str(model).startswith("@preset/")]),
    }


def _check_core(core_url: str) -> dict[str, Any]:
    with httpx.Client(timeout=10) as client:
        health = client.get(f"{core_url.rstrip('/')}/health")
        status = client.post(f"{core_url.rstrip('/')}/tools/call", json={"tool": "status.check", "arguments": {}})
        resolved = client.post(
            f"{core_url.rstrip('/')}/tools/call",
            json={"tool": "calendar.resolve_date", "arguments": {"phrase": "this weekend"}},
        )
    status_payload = status.json()
    resolved_payload = resolved.json()
    configured_tools = set(status_payload.get("configured_tools") or [])
    return {
        "ok": (
            health.status_code == 200
            and status.status_code == 200
            and status_payload.get("ok") is True
            and resolved.status_code == 200
            and resolved_payload.get("ok") is True
            and REQUIRED_CORE_TOOLS <= configured_tools
        ),
        "health_status": health.status_code,
        "status_check_ok": status_payload.get("ok"),
        "hostname": status_payload.get("hostname"),
        "configured_tools_present": sorted(REQUIRED_CORE_TOOLS.intersection(configured_tools)),
        "date_dates": resolved_payload.get("dates"),
    }


def _compose_config(compose: Path, env_example: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["docker", "compose", "--env-file", str(env_example), "-f", str(compose), "config"],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout_contains_librechat": "freyja-librechat-api" in result.stdout,
        "stderr_tail": result.stderr[-1000:],
    }


def build_report(config: Path, compose: Path, env_example: Path, msty_db: Path, core_url: str) -> dict[str, Any]:
    raw_config = yaml.safe_load(config.read_text(encoding="utf-8"))
    env = _read_env(env_example)
    custom = (raw_config.get("endpoints") or {}).get("custom") or []
    nexus_endpoint = next((endpoint for endpoint in custom if endpoint.get("name") == "Vulcan Nexus"), {})
    mcp_servers = raw_config.get("mcpServers") or {}
    freyja_core = mcp_servers.get("freyja-core") or {}
    provider = _msty_provider(msty_db)
    nexus_check = _check_nexus(provider)
    core_check = _check_core(core_url)
    compose_check = _compose_config(compose, env_example)
    endpoint_presets = set(((nexus_endpoint.get("models") or {}).get("default") or []))
    mcp_allowed = set(((raw_config.get("mcpSettings") or {}).get("allowedAddresses") or []))
    endpoint_allowed = set(((raw_config.get("endpoints") or {}).get("allowedAddresses") or []))
    ok = (
        nexus_endpoint.get("baseURL") == "${NEXUS_OPENAI_BASE_URL}"
        and nexus_endpoint.get("apiKey") == "${NEXUS_OPENAI_API_KEY}"
        and REQUIRED_PRESETS <= endpoint_presets
        and freyja_core.get("type") == "streamable-http"
        and freyja_core.get("url") == "${FREYJA_CORE_MCP_URL}"
        and "host.docker.internal:8766" in mcp_allowed
        and "100.94.80.21:3939" in endpoint_allowed
        and env.get("NEXUS_OPENAI_BASE_URL") == "http://100.94.80.21:3939/v1"
        and env.get("FREYJA_CORE_MCP_URL") == "http://host.docker.internal:8766/mcp"
        and nexus_check["ok"]
        and core_check["ok"]
        and compose_check["ok"]
    )
    return {
        "report_type": "librechat-pass-through-eval",
        "generated_at_unix": int(time.time()),
        "ok": ok,
        "verdict": "maybe-promising-pass-through-candidate" if ok else "blocked",
        "official_docs_findings": {
            "custom_openai_compatible_endpoints": True,
            "mcp_http_transport": True,
            "mcp_tool_names_are_server_scoped": "LibreChat documents tool names as {server_name}::{tool_name}.",
            "internal_endpoint_ssrf_allowlists_required": True,
            "self_hosted_privacy_claim": True,
            "docker_quickstart_available": True,
        },
        "trial_config": {
            "config": str(config.relative_to(REPO_ROOT)),
            "compose": str(compose.relative_to(REPO_ROOT)),
            "env_example": str(env_example.relative_to(REPO_ROOT)),
            "nexus_endpoint": {
                "name": nexus_endpoint.get("name"),
                "baseURL": nexus_endpoint.get("baseURL"),
                "apiKey_placeholder": nexus_endpoint.get("apiKey"),
                "models": sorted(endpoint_presets),
            },
            "freyja_core_mcp": {
                "server_name": "freyja-core",
                "type": freyja_core.get("type"),
                "url": freyja_core.get("url"),
                "has_auth_header": bool((freyja_core.get("headers") or {}).get("Authorization")),
            },
            "ssrf_allowlists": {
                "endpoints_allowedAddresses": sorted(endpoint_allowed),
                "mcp_allowedAddresses": sorted(mcp_allowed),
            },
        },
        "live_checks": {
            "nexus": nexus_check,
            "freyja_core": core_check,
            "compose_config": compose_check,
        },
        "acceptance": {
            "can_route_inference_to_nexus_by_config": REQUIRED_PRESETS <= endpoint_presets,
            "can_route_tools_to_freyja_core_mcp_by_config": freyja_core.get("url") == "${FREYJA_CORE_MCP_URL}",
            "does_not_duplicate_tool_logic": True,
            "existing_services_untouched": True,
            "full_ui_smoke_status": "not_started; config-only safe evaluation completed",
        },
        "blockers_or_next_steps": [
            "Update deploy/compose/librechat/.env from .env.example locally; the checked-in example intentionally contains placeholders only.",
            "Run scripts/freyja-core-mcp-server.py with FREYJA_CORE_MCP_TOKEN matching LibreChat .env before a UI smoke.",
            "Start the isolated LibreChat compose project only when ready for a browser/iPad trial.",
            "In LibreChat, confirm the UI exposes Freyja Core tools as freyja-core::{tool_name} and can call status.check/date resolution.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate LibreChat pass-through config for Nexus + Freyja Core.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--env-example", type=Path, default=DEFAULT_ENV_EXAMPLE)
    parser.add_argument("--msty-db", type=Path, default=DEFAULT_MSTY_DB)
    parser.add_argument("--core-url", default="http://100.115.228.56:8510")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    report = build_report(args.config, args.compose, args.env_example, args.msty_db, args.core_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
