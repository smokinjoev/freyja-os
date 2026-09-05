#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-home-agent-platform-inventory.json"
ATLAS_OPEN_WEBUI_URL = "http://100.119.235.114:3001"
IRIS_DUPLICATE_OPEN_WEBUI_URL = "http://100.115.228.56:3001"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a redacted Freyja Open WebUI platform inventory.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _docker_ps() -> dict[str, dict[str, str]]:
    proc = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if proc.returncode != 0:
        return {}
    rows: dict[str, dict[str, str]] = {}
    for line in proc.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        rows[parts[0]] = {"image": parts[1], "status": parts[2], "ports": parts[3]}
    return rows


def _open_webui_public_config(url: str = "http://127.0.0.1:3001", timeout: float = 5.0) -> dict[str, Any]:
    req = urllib.request.Request(f"{url.rstrip('/')}/api/config", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {
            "reachable": False,
            "error_class": exc.__class__.__name__,
            "secrets_included": False,
            "private_content_included": False,
        }
    features = payload.get("features") if isinstance(payload.get("features"), dict) else {}
    oauth = payload.get("oauth") if isinstance(payload.get("oauth"), dict) else {}
    providers = oauth.get("providers") if isinstance(oauth.get("providers"), dict) else {}
    return {
        "reachable": True,
        "onboarding": bool(payload.get("onboarding")),
        "status": bool(payload.get("status")),
        "version": payload.get("version"),
        "auth_enabled": bool(features.get("auth")),
        "signup_enabled": bool(features.get("enable_signup")),
        "login_form_enabled": bool(features.get("enable_login_form")),
        "auth_trusted_header": bool(features.get("auth_trusted_header")),
        "oauth_provider_count": len(providers),
        "secrets_included": False,
        "private_content_included": False,
    }


def build_inventory(now: int | None = None) -> dict[str, Any]:
    planes = _load_yaml(REPO_ROOT / "config" / "freyja-5.0-planes.yaml")
    mcp = _load_yaml(REPO_ROOT / "config" / "freyja-5.0-mcp-topology.yaml")
    resources = _load_yaml(REPO_ROOT / "config" / "open-webui-home-resources.yaml")
    docker = _docker_ps()

    atlas_public_config = _open_webui_public_config(ATLAS_OPEN_WEBUI_URL)
    iris_duplicate_public_config = _open_webui_public_config(IRIS_DUPLICATE_OPEN_WEBUI_URL, timeout=1.0)

    hosts = {
        "atlas": {
            "role": "always-on Open WebUI, shared memory, messaging adapters, non-Apple services",
            "open_webui_url": ATLAS_OPEN_WEBUI_URL,
            "open_webui_public_config": atlas_public_config,
            "current_services_note": "Docker service inventory is local to the machine running this script; Atlas service truth is the tailnet HTTP probe unless the script is run on Atlas.",
            "current_services": {
                name: docker[name]
                for name in sorted(docker)
                if name.startswith("freyja3-") or name.startswith("freyja5-") or name.startswith("freyja-signal-atlas")
            },
            "credential_locations": [
                "deploy/compose/open-webui/.env",
                "deploy/compose/freyja5/.env",
                "deploy/compose/signal/.env",
            ],
        },
        "vulcan": {
            "role": "local inference through Ollama/OpenAI-compatible endpoints",
            "endpoints": {
                "openai": "http://100.94.80.21:8088/v1",
                "ollama": "http://100.94.80.21:11434",
            },
            "nexus_required": False,
        },
        "iris": {
            "role": "Apple capability server for Calendar, Reminders, iMessage, Shortcuts, HomePod actions",
            "endpoint": "http://100.115.228.56:11434/v1",
            "mcp_host": "iris",
            "duplicate_open_webui": {
                "url": IRIS_DUPLICATE_OPEN_WEBUI_URL,
                "status": "disabled_expected",
                "public_config": iris_duplicate_public_config,
            },
        },
        "hera": {
            "role": "future voice/avatar interface",
            "status": "future",
        },
    }
    endpoints = {
        "open_webui": ATLAS_OPEN_WEBUI_URL,
        "open_webui_tailnet": ATLAS_OPEN_WEBUI_URL,
        "iris_duplicate_open_webui": IRIS_DUPLICATE_OPEN_WEBUI_URL,
        "freyja5_gateway": "http://127.0.0.1:8500",
        "freyja_home_memory": "http://127.0.0.1:8500/freyja-home-memory",
        "model_proxy_internal": "http://model-proxy:8080/v1",
        "vulcan_openai": "http://100.94.80.21:8088/v1",
        "vulcan_ollama": "http://100.94.80.21:11434",
        "iris_fallback": "http://100.115.228.56:11434/v1",
    }
    return {
        "report_type": "open-webui-home-agent-platform-inventory",
        "generated_at_unix": int(now or time.time()),
        "git_head": _git_head(),
        "secrets_included": False,
        "private_content_included": False,
        "hosts": hosts,
        "endpoints": endpoints,
        "open_webui_public_config": atlas_public_config,
        "open_webui_next_action_hint": (
            f"Complete first-account Open WebUI onboarding at {ATLAS_OPEN_WEBUI_URL}, then rerun post-auth activation."
            if atlas_public_config.get("onboarding")
            else "Use the existing Atlas Open WebUI admin account to generate/provide an admin API key or authenticated session, then rerun post-auth activation."
        ),
        "source_topology": {
            "planes": "config/freyja-5.0-planes.yaml",
            "mcp": "config/freyja-5.0-mcp-topology.yaml",
            "home_resources": "config/open-webui-home-resources.yaml",
            "atlas_recoverable_fallback_tag": (planes.get("atlas") or {}).get("recoverable_fallback_tag"),
            "mcp_hosts": sorted({server.get("host") for server in (mcp.get("servers") or []) if server.get("host")}),
            "resource_tool_count": len(((resources.get("resources") or {}).get("tools") or [])),
        },
        "credential_policy": {
            "values_recorded": False,
            "locations_only": True,
            "secret_env_names_redacted": True,
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inventory = build_inventory()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(inventory, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
