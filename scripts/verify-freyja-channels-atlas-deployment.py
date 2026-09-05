#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "freyja-channels-atlas-deployment.json"
COMPOSE = REPO_ROOT / "deploy" / "compose" / "freyja-channels" / "compose.yaml"
ENV_EXAMPLE = REPO_ROOT / "deploy" / "compose" / "freyja-channels" / ".env.example"
README = REPO_ROOT / "deploy" / "compose" / "freyja-channels" / "README.md"
DOCKERFILE = REPO_ROOT / "deploy" / "docker" / "freyja-channels.Dockerfile"
ATLAS_READINESS = REPO_ROOT / "certification" / "reports" / "freyja-channels-readiness-atlas.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify the Atlas Freyja channel deployment artifacts without exposing secrets.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--atlas-readiness", type=Path, default=ATLAS_READINESS)
    return parser


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("secrets_included") is not False:
        raise ValueError(f"report is not marked secret-free: {path}")
    return data


def _compose_config_ok() -> bool:
    proc = subprocess.run(
        ["docker", "compose", "--env-file", str(ENV_EXAMPLE), "-f", str(COMPOSE), "config"],
        cwd=REPO_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return proc.returncode == 0


def verify(atlas_readiness: Path = ATLAS_READINESS) -> dict[str, Any]:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")) if COMPOSE.exists() else {}
    services = compose.get("services") if isinstance(compose, dict) else {}
    networks = compose.get("networks") if isinstance(compose, dict) else {}
    secrets = compose.get("secrets") if isinstance(compose, dict) else {}
    env = _env_values(ENV_EXAMPLE)
    readme = README.read_text(encoding="utf-8") if README.exists() else ""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8") if DOCKERFILE.exists() else ""
    readiness = _load_json(atlas_readiness)

    required_services = {"telegram-pilot", "telegram-dry-run", "signal-pilot", "signal-dry-run"}
    checks = {
        "compose_exists": COMPOSE.exists(),
        "env_example_exists": ENV_EXAMPLE.exists(),
        "runbook_exists": README.exists(),
        "dockerfile_exists": DOCKERFILE.exists(),
        "compose_config_valid": _compose_config_ok(),
        "required_services_present": set(services) == required_services,
        "profiles_gate_live_services": services.get("telegram-pilot", {}).get("profiles") == ["telegram"]
        and services.get("signal-pilot", {}).get("profiles") == ["signal"],
        "operator_profiles_present": services.get("telegram-dry-run", {}).get("profiles") == ["operator"]
        and services.get("signal-dry-run", {}).get("profiles") == ["operator"],
        "no_published_ports": all("ports" not in service for service in services.values()),
        "open_webui_key_file_secret": (secrets.get("open_webui_api_key") or {}).get("file")
        == "${OPEN_WEBUI_API_KEY_HOST_FILE:-/home/joe/.freyja/open-webui-api-key}",
        "state_bind_mount_configured": all(
            "${FREYJA_CHANNEL_STATE_DIR:-../../../data/freyja-channels}:/state" in (service.get("volumes") or [])
            for service in services.values()
        ),
        "signal_private_network_configured": (networks.get("signal-private") or {}).get("external") is True
        and (networks.get("signal-private") or {}).get("name") == "${SIGNAL_PRIVATE_NETWORK:-freyja-signal-atlas_signal-private}",
        "telegram_not_on_signal_private_network": "signal-private" not in (services.get("telegram-pilot", {}).get("networks") or []),
        "signal_on_signal_private_network": "signal-private" in (services.get("signal-pilot", {}).get("networks") or []),
        "env_defaults_disable_live_services": env.get("TELEGRAM_ENABLED") == "false" and env.get("SIGNAL_ENABLED") == "false",
        "env_defaults_deny_all_allowlists": env.get("TELEGRAM_ALLOWED_USER_IDS") == "" and env.get("SIGNAL_ALLOWED_SENDERS") == "",
        "env_uses_key_file": env.get("OPEN_WEBUI_API_KEY_FILE") == "/run/secrets/open_webui_api_key",
        "dockerfile_copies_package_sources": "COPY certification ./certification" in dockerfile and "COPY connectors ./connectors" in dockerfile,
        "runbook_documents_no_public_ports": "publish no ports" in readme or "publishes no ports" in readme,
        "runbook_documents_deny_all": "empty allowlist is deny-all" in readme.lower(),
        "atlas_readiness_secret_free": readiness.get("secrets_included") is False,
        "atlas_readiness_open_webui_key_file_ok": (readiness.get("open_webui_client") or {}).get("api_key_configured") is True,
        "atlas_readiness_telegram_waits_for_credentials": set((readiness.get("telegram") or {}).get("missing_configuration") or [])
        == {"TELEGRAM_ALLOWED_USER_IDS", "TELEGRAM_BOT_TOKEN", "TELEGRAM_IDENTITY_MAP"},
        "atlas_readiness_signal_waits_for_credentials": set((readiness.get("signal") or {}).get("missing_configuration") or [])
        <= {"SIGNAL_ALLOWED_SENDERS", "SIGNAL_ACCOUNT_NUMBER", "SIGNAL_IDENTITY_MAP", "SIGNAL_REST_API_URL"},
    }
    return {
        "report_type": "freyja-channels-atlas-deployment",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "secrets_included": False,
        "private_content_included": False,
        "ok": all(checks.values()),
        "checks": checks,
        "artifacts": {
            "compose": str(COMPOSE.relative_to(REPO_ROOT)),
            "env_example": str(ENV_EXAMPLE.relative_to(REPO_ROOT)),
            "runbook": str(README.relative_to(REPO_ROOT)),
            "dockerfile": str(DOCKERFILE.relative_to(REPO_ROOT)),
            "atlas_readiness": str(atlas_readiness.relative_to(REPO_ROOT)) if atlas_readiness.is_relative_to(REPO_ROOT) else str(atlas_readiness),
        },
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = verify(args.atlas_readiness)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
