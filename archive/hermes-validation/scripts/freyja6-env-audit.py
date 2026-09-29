#!/usr/bin/env python3
"""Audit Freyja 6 environment readiness without exposing secret values."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_ENV_FILE = Path("deploy/compose/freyja6/.env")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-env-audit.json")
PLACEHOLDER_PREFIX = "replace-with-"
EXPECTED_LITELLM_IMAGE = "ghcr.io/berriai/litellm:v1.89.0"

REQUIRED_ENV = [
    "COMPOSE_PROJECT_NAME",
    "LITELLM_IMAGE",
    "HERMES_AGENT_VERSION",
    "HERMES_AGENT_IMAGE",
    "HERMES_AGENT_SOURCE",
    "LITELLM_MASTER_KEY",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "VULCAN_OLLAMA_BASE_URL",
    "VULCAN_FAST_MODEL",
    "VULCAN_GENERAL_MODEL",
    "VULCAN_CODE_MODEL",
    "FREYJA6_DISCORD_BOT_TOKEN",
    "FREYJA6_DISCORD_CHANNEL_ID",
    "FREYJA6_CORE_MCP_TOKEN",
    "FREYJA6_TERMINAL_MCP_TOKEN",
    "FREYJA6_APPROVED_FILES_ROOT",
    "FREYJA6_LOG_ROOT",
    "FREYJA6_HERMES_DATA",
]

SECRET_KEYS = {
    "LITELLM_MASTER_KEY",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "FREYJA6_DISCORD_BOT_TOKEN",
    "FREYJA6_CORE_MCP_TOKEN",
    "FREYJA6_TERMINAL_MCP_TOKEN",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 .env readiness and redact configured secrets.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(*, env_file: Path) -> dict[str, Any]:
    env_path = _resolve(env_file)
    source_check = _check_env_source_file(env_path)
    if source_check:
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-env-audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "blocked",
            "env_file": str(env_file),
            "checks": [source_check],
            "failures": failures,
            "secrets_included": False,
            "redacted_summary": _redacted_summary({}),
            "next_actions": _next_actions(failures),
        }
    env = _load_env(env_path)
    checks = [
        _check_env_file(env_path),
        _check_required_values(env),
        _check_compose_project(env),
        _check_image_pins(env),
        _check_database_url(env),
        _check_vulcan_url(env),
        _check_live_helper_endpoints(env),
        _check_vulcan_models(env),
        _check_hermes_source_path(env),
        _check_host_roots(env),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-env-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "ready" if ok else "blocked",
        "env_file": str(env_file),
        "checks": checks,
        "failures": failures,
        "secrets_included": False,
        "redacted_summary": _redacted_summary(env),
        "next_actions": _next_actions(failures),
    }


def _check_env_file(path: Path) -> dict[str, Any]:
    if path.exists():
        return _passed("env_file", f"Found {path.name}.")
    return _failed("env_file", f"Environment file does not exist: {path}.")


def _check_env_source_file(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Freyja 6 environment source file must be a regular file, not a symlink.",
            "symlinks": [str(path)],
            "not_regular": [],
        }
    if path.exists() and not path.is_file():
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Freyja 6 environment source file must be a regular file, not a symlink.",
            "symlinks": [],
            "not_regular": [str(path)],
        }
    return None


def _check_required_values(env: dict[str, str]) -> dict[str, Any]:
    missing = [key for key in REQUIRED_ENV if key not in env]
    placeholders = [
        key
        for key in REQUIRED_ENV
        if key in env and _looks_placeholder(env[key])
    ]
    if missing or placeholders:
        return {
            "id": "required_values",
            "status": "fail",
            "message": "Required Freyja 6 environment values are missing, blank, or placeholders.",
            "missing": missing,
            "placeholders": placeholders,
        }
    return _passed("required_values", "Required Freyja 6 environment values are populated.")


def _check_compose_project(env: dict[str, str]) -> dict[str, Any]:
    if env.get("COMPOSE_PROJECT_NAME") != "freyja6":
        return _failed("compose_project", "COMPOSE_PROJECT_NAME must be exactly freyja6.")
    return _passed("compose_project", "Compose project is isolated to freyja6.")


def _check_image_pins(env: dict[str, str]) -> dict[str, Any]:
    failures: list[str] = []
    litellm = env.get("LITELLM_IMAGE", "")
    hermes_version = env.get("HERMES_AGENT_VERSION", "")
    hermes_image = env.get("HERMES_AGENT_IMAGE", "")
    for key, image in (("LITELLM_IMAGE", litellm), ("HERMES_AGENT_IMAGE", hermes_image)):
        tag = image.rsplit(":", 1)[-1] if ":" in image else ""
        if not tag or tag in {"latest", "main"}:
            failures.append(f"{key} must use an immutable validation tag.")
    if litellm and litellm != EXPECTED_LITELLM_IMAGE:
        failures.append(f"LITELLM_IMAGE must remain pinned to {EXPECTED_LITELLM_IMAGE}.")
    if hermes_version and hermes_image and _image_tag(hermes_image) != hermes_version:
        failures.append("HERMES_AGENT_IMAGE tag must exactly match HERMES_AGENT_VERSION.")
    if failures:
        return {
            "id": "image_pins",
            "status": "fail",
            "message": "Image pins are not strict enough for Freyja 6 validation.",
            "failures": failures,
        }
    return _passed("image_pins", "LiteLLM and Hermes images use pinned validation tags.")


def _image_tag(image: str) -> str:
    return image.rsplit(":", 1)[-1] if ":" in image else ""


def _check_database_url(env: dict[str, str]) -> dict[str, Any]:
    raw = env.get("DATABASE_URL", "")
    parsed = urlparse(raw)
    failures: list[str] = []
    if parsed.scheme not in {"postgresql", "postgres"}:
        failures.append("DATABASE_URL must use postgresql.")
    if parsed.hostname != "litellm-db":
        failures.append("DATABASE_URL must point at the litellm-db compose service.")
    if parsed.username != "litellm":
        failures.append("DATABASE_URL must use the litellm database user.")
    if (parsed.path or "").lstrip("/") != "litellm":
        failures.append("DATABASE_URL must target the litellm database.")
    if failures:
        return {
            "id": "database_url",
            "status": "fail",
            "message": "DATABASE_URL is not scoped to the Freyja 6 LiteLLM database.",
            "failures": failures,
        }
    return _passed("database_url", "DATABASE_URL targets the Freyja 6 LiteLLM database service.")


def _check_vulcan_url(env: dict[str, str]) -> dict[str, Any]:
    raw = env.get("VULCAN_OLLAMA_BASE_URL", "")
    parsed = urlparse(raw)
    failures: list[str] = []
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        failures.append("VULCAN_OLLAMA_BASE_URL must be an HTTP(S) URL.")
    hostname = (parsed.hostname or "").lower()
    if hostname in {"127.0.0.1", "localhost", "0.0.0.0", "litellm", "hermes-freyja-test", "litellm-db"}:
        failures.append("VULCAN_OLLAMA_BASE_URL must point at the Vulcan inference host, not Atlas loopback or compose services.")
    elif hostname and not _vulcan_host_is_private(hostname):
        failures.append("VULCAN_OLLAMA_BASE_URL must use a private, tailnet, or explicitly Vulcan-scoped host.")
    if failures:
        return {
            "id": "vulcan_url",
            "status": "fail",
            "message": "VULCAN_OLLAMA_BASE_URL is not scoped to the Vulcan inference host.",
            "failures": failures,
        }
    return {
        "id": "vulcan_url",
        "status": "pass",
        "message": "Vulcan Ollama base URL is syntactically valid.",
        "base_url_redacted": _redact_url(raw),
    }


def _vulcan_host_is_private(hostname: str) -> bool:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return hostname.endswith(".local") or hostname.startswith("vulcan-") or hostname == "vulcan"
    return address.is_private or hostname.startswith("100.")


def _check_live_helper_endpoints(env: dict[str, str]) -> dict[str, Any]:
    endpoints = {
        "FREYJA6_LITELLM_BASE_URL": env.get("FREYJA6_LITELLM_BASE_URL", "http://127.0.0.1:4600/v1"),
        "FREYJA6_CORE_URL": env.get("FREYJA6_CORE_URL", "http://127.0.0.1:8510"),
        "FREYJA6_CORE_MCP_HEALTH_URL": env.get("FREYJA6_CORE_MCP_HEALTH_URL", "http://127.0.0.1:8766/healthz"),
        "FREYJA6_TERMINAL_MCP_HEALTH_URL": env.get("FREYJA6_TERMINAL_MCP_HEALTH_URL", "http://127.0.0.1:8765/healthz"),
    }
    failures: list[dict[str, str]] = []
    redacted: dict[str, str] = {}
    for key, raw in endpoints.items():
        parsed = urlparse(raw)
        hostname = (parsed.hostname or "").lower()
        redacted[key] = _redact_url(raw)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            failures.append({"key": key, "reason": "must be an HTTP(S) URL"})
            continue
        path_failure = _live_helper_path_failure(key, parsed.path)
        if path_failure:
            failures.append({"key": key, "reason": path_failure})
        if key == "FREYJA6_LITELLM_BASE_URL" and hostname in {"litellm-db", "hermes-freyja-test"}:
            failures.append({"key": key, "reason": "must point at the LiteLLM gateway, not internal services"})
        elif key != "FREYJA6_LITELLM_BASE_URL" and hostname in {"litellm-db", "litellm", "hermes-freyja-test"}:
            failures.append({"key": key, "reason": "must point at the Atlas Core or MCP service endpoint, not compose internals"})
        elif hostname and not _live_helper_host_is_local_or_private(hostname):
            failures.append({"key": key, "reason": "must use Atlas loopback, private, tailnet, .local, or explicitly service-scoped host"})
    if failures:
        return {
            "id": "live_helper_endpoints",
            "status": "fail",
            "message": "Freyja 6 live helper endpoints are not safely scoped.",
            "failures": failures,
            "endpoints_redacted": redacted,
        }
    return {
        "id": "live_helper_endpoints",
        "status": "pass",
        "message": "Freyja 6 live helper endpoints are local/private scoped.",
        "endpoints_redacted": redacted,
    }


def _live_helper_host_is_local_or_private(hostname: str) -> bool:
    if hostname in {"localhost", "litellm", "freyja-core", "freyja-core-gateway", "freyja-terminal"}:
        return True
    if hostname.startswith(("litellm-", "freyja-core-", "freyja-terminal-")) or hostname.endswith(".local"):
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or hostname.startswith("100.")


def _live_helper_path_failure(key: str, path: str) -> str:
    normalized = path.rstrip("/")
    if key == "FREYJA6_LITELLM_BASE_URL" and normalized != "/v1":
        return "must include the LiteLLM /v1 API base path"
    if key in {"FREYJA6_CORE_MCP_HEALTH_URL", "FREYJA6_TERMINAL_MCP_HEALTH_URL"} and normalized != "/healthz":
        return "must point at the MCP /healthz endpoint"
    return ""


def _check_vulcan_models(env: dict[str, str]) -> dict[str, Any]:
    keys = ["VULCAN_FAST_MODEL", "VULCAN_GENERAL_MODEL", "VULCAN_CODE_MODEL"]
    values = [env.get(key, "").strip() for key in keys if env.get(key, "").strip()]
    if len(values) != len(keys):
        return _failed("vulcan_models", "All three Vulcan model aliases must be configured.")
    if len(set(values)) != len(values):
        return {
            "id": "vulcan_models",
            "status": "fail",
            "message": "Freyja 6 Vulcan aliases must point at three distinct configured models.",
            "duplicates": sorted({value for value in values if values.count(value) > 1}),
        }
    return _passed("vulcan_models", "Freyja 6 Vulcan aliases point at distinct configured models.")


def _check_hermes_source_path(env: dict[str, str]) -> dict[str, Any]:
    raw = env.get("HERMES_AGENT_SOURCE", "")
    if not raw:
        return _failed("hermes_source_path", "HERMES_AGENT_SOURCE is missing.")
    source = Path(raw).expanduser()
    if not source.is_absolute():
        return _failed("hermes_source_path", "HERMES_AGENT_SOURCE must be an absolute path.")
    return _passed("hermes_source_path", "Hermes Agent source path is absolute.")


def _check_host_roots(env: dict[str, str]) -> dict[str, Any]:
    keys = ["FREYJA6_APPROVED_FILES_ROOT", "FREYJA6_LOG_ROOT", "FREYJA6_HERMES_DATA"]
    failures: list[dict[str, str]] = []
    values: list[str] = []
    for key in keys:
        raw = env.get(key, "")
        values.append(raw)
        path = Path(raw).expanduser()
        if not path.is_absolute():
            failures.append({"key": key, "reason": "must be absolute"})
        elif path.is_symlink():
            failures.append({"key": key, "reason": "must not be a symlink"})
        elif path in {Path("/"), Path("/srv"), Path.home(), REPO_ROOT}:
            failures.append({"key": key, "reason": "must not point at a broad host root"})
        elif not _has_freyja6_segment(path):
            failures.append({"key": key, "reason": "must stay under a freyja6-specific host path"})
    if len(set(values)) != len(values):
        failures.append({"key": "FREYJA6_HOST_ROOTS", "reason": "approved files, logs, and Hermes data must be distinct"})
    if failures:
        return {
            "id": "host_roots",
            "status": "fail",
            "message": "Freyja 6 host roots are not safely isolated.",
            "failures": failures,
        }
    return _passed("host_roots", "Freyja 6 host roots are absolute, distinct, and isolated.")


def _redacted_summary(env: dict[str, str]) -> dict[str, Any]:
    configured = [key for key in REQUIRED_ENV if env.get(key, "").strip()]
    secret_status = {
        key: _secret_fingerprint(env[key])
        for key in SECRET_KEYS
        if env.get(key, "").strip() and not env[key].strip().startswith(PLACEHOLDER_PREFIX)
    }
    return {
        "configured_keys": configured,
        "secret_keys_configured": sorted(secret_status),
        "secret_fingerprints": secret_status,
        "discord_channel_id": _redact_identifier(env.get("FREYJA6_DISCORD_CHANNEL_ID", "")),
        "host_roots": {
            key: _redact_path(env.get(key, ""))
            for key in ("FREYJA6_APPROVED_FILES_ROOT", "FREYJA6_LOG_ROOT", "FREYJA6_HERMES_DATA")
            if env.get(key)
        },
    }


def _secret_fingerprint(value: str) -> str:
    return f"<redacted:{len(value)}:{value[-4:] if len(value) >= 4 else 'short'}>"


def _redact_identifier(value: str) -> str:
    if not value.strip():
        return ""
    return f"<redacted:{len(value)}:{value[-4:] if len(value) >= 4 else 'short'}>"


def _redact_path(value: str) -> str:
    if not value:
        return ""
    path = Path(value).expanduser()
    return str(Path(*path.parts[-2:])) if len(path.parts) >= 2 else path.name


def _redact_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc:
        return "<invalid>"
    host = _redacted_host(parsed.hostname or "")
    port = f":{parsed.port}" if parsed.port else ""
    return urlunparse((parsed.scheme, f"{host}{port}", parsed.path, "", "", ""))


def _redacted_host(hostname: str) -> str:
    hostname = hostname.lower()
    if hostname in {"127.0.0.1", "localhost", "::1"}:
        return "atlas-loopback"
    if hostname in {"litellm", "freyja-core", "freyja-core-gateway", "freyja-terminal"}:
        return hostname
    if hostname.startswith("litellm-"):
        return "litellm-private"
    if hostname.startswith("freyja-core-"):
        return "freyja-core-private"
    if hostname.startswith("freyja-terminal-"):
        return "freyja-terminal-private"
    if hostname.startswith("vulcan-"):
        return "vulcan-private"
    if hostname.endswith(".local"):
        return "atlas-local"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return "atlas-public"
    if address.is_loopback:
        return "atlas-loopback"
    if str(address).startswith("100."):
        return "vulcan-tailnet"
    if address.is_private:
        return "atlas-private"
    return "atlas-public"


def _has_freyja6_segment(path: Path) -> bool:
    return "freyja6" in {part.lower() for part in path.parts}


def _looks_placeholder(value: str) -> bool:
    text = value.strip().lower()
    return not text or text.startswith(PLACEHOLDER_PREFIX) or any(marker in text for marker in ("example", "placeholder", "<", ">"))


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Run Hermes image verification, Atlas preflight, and live validation."]


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = _expand_env_value(value.strip(), values)
    return values


def _expand_env_value(value: str, values: dict[str, str]) -> str:
    expanded = value
    for key, replacement in values.items():
        expanded = expanded.replace("${" + key + "}", replacement)
    return expanded


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _passed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "pass", "message": message}


def _failed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "fail", "message": message}


def _output_path_failure(output: Path) -> str | None:
    if output.is_symlink():
        return f"output path must not be a symlink: {output.name}"
    if output.exists() and not output.is_file():
        return f"output path must be a regular file: {output.name}"
    return None


def _error_report(error: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-env-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "status": "fail",
        "error": error,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_failure = _output_path_failure(args.output)
    report = _error_report(output_failure) if output_failure else build_report(env_file=args.env_file)
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
