#!/usr/bin/env python3
"""Preflight the Freyja 6.0 Atlas validation stack without starting it."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_ENV_FILE = Path("deploy/compose/freyja6/.env")
EXAMPLE_ENV_FILE = Path("deploy/compose/freyja6/.env.example")
COMPOSE_FILE = Path("deploy/compose/freyja6/compose.yaml")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-atlas-preflight.json")
PLACEHOLDER_PREFIX = "replace-with-"
EXPECTED_LITELLM_IMAGE = "ghcr.io/berriai/litellm:v1.89.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preflight Freyja 6.0 Atlas validation readiness.")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check-vulcan", action="store_true", help="Probe Vulcan Ollama tags endpoint.")
    parser.add_argument("--check-images", action="store_true", help="Inspect local/pullable Docker images.")
    parser.add_argument("--create-dirs", action="store_true", help="Create Freyja 6 data/log/approved-file directories.")
    parser.add_argument("--timeout", type=float, default=5.0)
    return parser


def build_report(
    *,
    env_file: Path,
    check_vulcan: bool = False,
    check_images: bool = False,
    create_dirs: bool = False,
    timeout: float = 5.0,
) -> dict[str, Any]:
    env_path = _resolve(env_file)
    source_check = _check_env_source_file(env_path)
    if source_check:
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-atlas-preflight",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ready": False,
            "status": "blocked",
            "env_file": str(env_file),
            "checks": [source_check],
            "blockers": [source_check],
            "warnings": [],
            "next_actions": _next_actions([source_check], []),
        }
    env_file_exists = env_path.exists()
    env = _load_env(env_path if env_file_exists else _resolve(EXAMPLE_ENV_FILE))
    checks = [
        _check_env_file(env_path),
        _check_required_env(env),
        _check_compose_project(env),
        _check_image_pins(env),
        _check_database_url(env),
        _check_freyja6_config_files(),
        _check_hermes_source(env),
        _check_compose_config(env_path if env_path.exists() else _resolve(EXAMPLE_ENV_FILE)),
        _check_vulcan_url(env),
        _check_live_helper_endpoints(env),
        _check_vulcan_models(env),
        _check_directories(env, create=create_dirs, env_file_exists=env_file_exists),
    ]
    if check_images:
        checks.append(_check_images(env))
    else:
        checks.append(_skipped("docker_images", "Run with --check-images to verify local/pullable image pins."))
    if check_vulcan:
        checks.append(_check_vulcan(env, timeout=timeout))
    else:
        checks.append(_skipped("vulcan_reachability", "Run with --check-vulcan on Atlas or tailnet-connected host."))

    blockers = [check for check in checks if check["status"] == "fail"]
    warnings = [check for check in checks if check["status"] == "warn"]
    ready = not blockers
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-atlas-preflight",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ready": ready,
        "status": "ready" if ready else "blocked",
        "env_file": str(env_file),
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
        "next_actions": _next_actions(blockers, warnings),
    }


def _check_env_file(path: Path) -> dict[str, Any]:
    if path.exists():
        return _passed("env_file", f"Found {path}.")
    return _warning("env_file", f"{path} is missing; using .env.example for structural checks only.")


def _check_env_source_file(path: Path) -> dict[str, Any] | None:
    if path.is_symlink():
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Freyja 6 preflight environment source file must be a regular file, not a symlink.",
            "symlinks": [str(path)],
            "not_regular": [],
        }
    if path.exists() and not path.is_file():
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Freyja 6 preflight environment source file must be a regular file, not a symlink.",
            "symlinks": [],
            "not_regular": [str(path)],
        }
    return None


def _check_required_env(env: dict[str, str]) -> dict[str, Any]:
    required = [
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
    missing = [key for key in required if key not in env]
    placeholders = [
        key
        for key in required
        if key in env and _looks_placeholder(env[key])
    ]
    if missing or placeholders:
        return {
            "id": "required_env",
            "status": "fail",
            "message": "Required Freyja 6 environment values are missing or still placeholders.",
            "missing": missing,
            "placeholders": placeholders,
        }
    return _passed("required_env", "Required Freyja 6 environment values are populated.")


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


def _check_compose_config(env_file: Path) -> dict[str, Any]:
    if not shutil.which("docker"):
        return _failed("compose_config", "Docker CLI is not available.")
    cmd = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(_resolve(COMPOSE_FILE)),
        "config",
    ]
    result = subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        return {
            "id": "compose_config",
            "status": "fail",
            "message": "Docker Compose could not render the Freyja 6 stack.",
            "stderr_tail": result.stderr[-1000:],
        }
    return _passed("compose_config", "Docker Compose renders the Freyja 6 stack.")


def _check_freyja6_config_files() -> dict[str, Any]:
    required = [
        Path("config/freyja6/freyja-test.yaml"),
        Path("config/freyja6/bootstrap/identity.md"),
        Path("config/freyja6/bootstrap/approved-smoke.txt"),
        Path("config/freyja6/mcp/freyja-test.json"),
        Path("config/freyja6/schedules.yaml"),
        Path("config/freyja6/tool-boundaries.yaml"),
    ]
    missing = [str(path) for path in required if not _resolve(path).exists()]
    if missing:
        return {
            "id": "freyja6_config_files",
            "status": "fail",
            "message": "Required Freyja 6 config files are missing.",
            "missing": missing,
        }
    return _passed("freyja6_config_files", "Required Freyja 6 config files are present.")


def _check_hermes_source(env: dict[str, str]) -> dict[str, Any]:
    raw = env.get("HERMES_AGENT_SOURCE", "")
    if not raw:
        return _failed("hermes_source", "HERMES_AGENT_SOURCE is missing.")
    source = Path(raw).expanduser()
    if not source.exists():
        return _failed("hermes_source", f"Hermes Agent source does not exist: {source}.")
    if not (source / "Dockerfile").exists():
        return _failed("hermes_source", f"Hermes Agent Dockerfile does not exist: {source / 'Dockerfile'}.")
    return _passed("hermes_source", "Hermes Agent source checkout and Dockerfile are present.")


def _check_directories(env: dict[str, str], *, create: bool, env_file_exists: bool = True) -> dict[str, Any]:
    keys = ["FREYJA6_APPROVED_FILES_ROOT", "FREYJA6_LOG_ROOT", "FREYJA6_HERMES_DATA"]
    if create and not env_file_exists:
        return {
            "id": "host_directories",
            "status": "fail",
            "message": "Host directories cannot be created from .env.example; provide the real Freyja 6 env file.",
            "missing": ["env_file"],
            "unsafe": [],
            "created": [],
        }
    missing: list[str] = []
    unsafe: list[dict[str, str]] = []
    created: list[str] = []
    values: list[str] = []
    for key in keys:
        raw = env.get(key, "")
        values.append(raw)
        if not raw:
            missing.append(key)
            continue
        path = Path(raw).expanduser()
        unsafe_reason = _unsafe_host_root_reason(path)
        if unsafe_reason:
            unsafe.append({"key": key, "path": _redact_path(path), "reason": unsafe_reason})
            continue
        if path.exists():
            continue
        if create:
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path))
        else:
            missing.append(str(path))
    if len(set(values)) != len(values):
        unsafe.append({"key": "FREYJA6_HOST_ROOTS", "path": "", "reason": "approved files, logs, and Hermes data must be distinct"})
    if missing or unsafe:
        return {
            "id": "host_directories",
            "status": "fail",
            "message": "Required Freyja 6 host directories are missing or unsafe.",
            "missing": missing,
            "unsafe": unsafe,
            "created": created,
        }
    return {
        "id": "host_directories",
        "status": "pass",
        "message": "Required Freyja 6 host directories exist.",
        "created": created,
    }


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


def _check_vulcan_url(env: dict[str, str]) -> dict[str, Any]:
    raw = env.get("VULCAN_OLLAMA_BASE_URL", "").strip()
    parsed = urlparse(raw)
    failures: list[str] = []
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        failures.append("VULCAN_OLLAMA_BASE_URL must be an http(s) URL.")
    forbidden_hosts = {"127.0.0.1", "localhost", "0.0.0.0", "litellm", "hermes-freyja-test", "litellm-db"}
    hostname = (parsed.hostname or "").lower()
    if hostname in forbidden_hosts:
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
    return _passed("vulcan_url", "VULCAN_OLLAMA_BASE_URL points at a dedicated Vulcan inference host.")


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


def _vulcan_host_is_private(hostname: str) -> bool:
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return hostname.endswith(".local") or hostname.startswith("vulcan-") or hostname == "vulcan"
    return address.is_private or hostname.startswith("100.")


def _unsafe_host_root_reason(path: Path) -> str:
    if not path.is_absolute():
        return "must be absolute"
    if path.is_symlink():
        return "must not be a symlink"
    if path in {Path("/"), Path("/srv"), Path.home(), REPO_ROOT}:
        return "must not point at a broad host root"
    if "freyja6" not in {part.lower() for part in path.parts}:
        return "must stay under a freyja6-specific host path"
    return ""


def _looks_placeholder(value: str) -> bool:
    text = value.strip().lower()
    return not text or text.startswith(PLACEHOLDER_PREFIX) or any(marker in text for marker in ("example", "placeholder", "<", ">"))


def _check_images(env: dict[str, str]) -> dict[str, Any]:
    if not shutil.which("docker"):
        return _failed("docker_images", "Docker CLI is not available.")
    images = [env.get("LITELLM_IMAGE", ""), env.get("HERMES_AGENT_IMAGE", ""), "postgres:16.4-alpine"]
    hermes_image = env.get("HERMES_AGENT_IMAGE", "")
    hermes_version = env.get("HERMES_AGENT_VERSION", "")
    failures: list[dict[str, str]] = []
    for image in images:
        if not image:
            failures.append({"image": image, "reason": "missing image value"})
            continue
        local = subprocess.run(["docker", "image", "inspect", image], text=True, capture_output=True, check=False)
        if local.returncode == 0:
            if image == hermes_image and _local_image_version_label(local.stdout) != hermes_version:
                failures.append({"image": image, "reason": "org.opencontainers.image.version label must match HERMES_AGENT_VERSION"})
            continue
        manifest = subprocess.run(["docker", "manifest", "inspect", image], text=True, capture_output=True, check=False)
        if manifest.returncode != 0:
            failures.append({"image": image, "reason": (manifest.stderr or manifest.stdout)[-500:]})
    if failures:
        return {
            "id": "docker_images",
            "status": "fail",
            "message": "One or more Freyja 6 images are neither local nor pullable from this host.",
            "failures": failures,
        }
    return _passed("docker_images", "Freyja 6 image pins are locally present or pullable.")


def _local_image_version_label(inspect_stdout: str) -> str:
    try:
        payload = json.loads(inspect_stdout)
    except json.JSONDecodeError:
        return ""
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], dict):
        return ""
    labels = payload[0].get("Config", {}).get("Labels", {})
    if not isinstance(labels, dict):
        return ""
    return str(labels.get("org.opencontainers.image.version") or "")


def _check_vulcan(env: dict[str, str], *, timeout: float) -> dict[str, Any]:
    base_url = env.get("VULCAN_OLLAMA_BASE_URL", "").rstrip("/")
    if not base_url:
        return _failed("vulcan_reachability", "VULCAN_OLLAMA_BASE_URL is missing.")
    try:
        response = httpx.get(f"{base_url}/api/tags", timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return {
            "id": "vulcan_reachability",
            "status": "fail",
            "message": "Could not reach Vulcan Ollama tags endpoint.",
            "base_url_redacted": _redact_url(base_url),
            "error": str(exc),
        }
    payload = response.json()
    models = payload.get("models") if isinstance(payload, dict) else []
    model_names = sorted(str(model.get("name")) for model in models if isinstance(model, dict) and model.get("name"))
    configured = [env.get("VULCAN_FAST_MODEL"), env.get("VULCAN_GENERAL_MODEL"), env.get("VULCAN_CODE_MODEL")]
    missing_models = sorted(model for model in configured if model and model not in model_names)
    status = "warn" if missing_models else "pass"
    return {
        "id": "vulcan_reachability",
        "status": status,
        "message": "Reached Vulcan Ollama tags endpoint.",
        "base_url_redacted": _redact_url(base_url),
        "configured_models_missing": missing_models,
        "model_count": len(model_names),
    }


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


def _next_actions(blockers: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> list[str]:
    if blockers:
        return [str(blocker["message"]) for blocker in blockers]
    if warnings:
        return [str(warning["message"]) for warning in warnings]
    return ["Start the Freyja 6 compose stack and begin live acceptance evidence capture."]


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


def _redact_path(path: Path) -> str:
    return str(Path(*path.parts[-2:])) if len(path.parts) >= 2 else path.name


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _passed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "pass", "message": message}


def _warning(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "warn", "message": message}


def _failed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "fail", "message": message}


def _skipped(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "skip", "message": message}


def _output_path_failure(output: Path) -> str | None:
    if output.is_symlink():
        return f"output path must not be a symlink: {output.name}"
    if output.exists() and not output.is_file():
        return f"output path must be a regular file: {output.name}"
    return None


def _error_report(error: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-atlas-preflight",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ready": False,
        "status": "fail",
        "error": error,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_failure = _output_path_failure(args.output)
    report = (
        _error_report(output_failure)
        if output_failure
        else build_report(
            env_file=args.env_file,
            check_vulcan=args.check_vulcan,
            check_images=args.check_images,
            create_dirs=args.create_dirs,
            timeout=args.timeout,
        )
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
