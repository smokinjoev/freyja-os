#!/usr/bin/env python3
"""Audit Freyja 6 model routing for local-only validation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"
if sys.version_info < (3, 11) and VENV_PYTHON.exists():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), *sys.argv])

DEFAULT_AGENT_CONFIG = Path("config/freyja6/freyja-test.yaml")
DEFAULT_LITELLM_CONFIG = Path("deploy/compose/freyja6/litellm.config.yaml")
DEFAULT_COMPOSE = Path("deploy/compose/freyja6/compose.yaml")
DEFAULT_CONTRACT = Path("config/freyja6/hermes-runtime-contract.yaml")
DEFAULT_OUTPUT = Path("certification/reports/freyja6-model-privacy-audit.json")
EXPECTED_MODELS = ["vulcan-fast", "vulcan-general", "vulcan-code"]
EXPECTED_MODEL_TARGETS = {
    "vulcan-fast": "ollama/qwen2.5:7b",
    "vulcan-general": "ollama/qwen3.8:27b",
    "vulcan-code": "ollama/qwen3-coder-next:q4_K_M",
}
CLOUD_PROVIDER_MARKERS = (
    "openai/",
    "anthropic/",
    "azure/",
    "bedrock/",
    "vertex_ai/",
    "gemini/",
    "cohere/",
    "mistral/",
    "groq/",
    "perplexity/",
)
CLOUD_ENV_MARKERS = (
    "OPENAI_API_BASE",
    "OPENAI_API_KEY",
    "ANTHROPIC",
    "AZURE",
    "BEDROCK",
    "VERTEX",
    "GEMINI",
    "COHERE",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Freyja 6 LiteLLM/Hermes model routing privacy.")
    parser.add_argument("--agent-config", type=Path, default=DEFAULT_AGENT_CONFIG)
    parser.add_argument("--litellm-config", type=Path, default=DEFAULT_LITELLM_CONFIG)
    parser.add_argument("--compose", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def build_report(*, agent_config: Path, litellm_config: Path, compose: Path, contract: Path) -> dict[str, Any]:
    source_check = _check_files(agent_config, litellm_config, compose, contract)
    if source_check["status"] == "fail":
        failures = [source_check]
        return {
            "schema_version": "1.0",
            "report_type": "freyja6-model-privacy-audit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "status": "fail",
            "checks": [source_check],
            "failures": failures,
            "next_actions": _next_actions(failures),
        }
    agent_doc = _load_yaml(agent_config)
    litellm_doc = _load_yaml(litellm_config)
    compose_doc = _load_yaml(compose)
    contract_doc = _load_yaml(contract)
    checks = [
        source_check,
        _check_guardrails(agent_doc),
        _check_agent_models(agent_doc),
        _check_litellm_models(litellm_doc),
        _check_compose_model_environment(compose_doc),
        _check_hermes_gateway(compose_doc, contract_doc),
    ]
    failures = [check for check in checks if check["status"] == "fail"]
    ok = not failures
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-model-privacy-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "status": "pass" if ok else "fail",
        "checks": checks,
        "failures": failures,
        "next_actions": _next_actions(failures),
    }


def _check_guardrails(agent_doc: dict[str, Any]) -> dict[str, Any]:
    guardrails = agent_doc.get("guardrails") if isinstance(agent_doc.get("guardrails"), dict) else {}
    required = ["local_private_data_default", "cloud_model_use_requires_explicit_approval"]
    missing = [key for key in required if guardrails.get(key) is not True]
    if missing:
        return {
            "id": "privacy_guardrails",
            "status": "fail",
            "message": "Model privacy guardrails are missing or disabled.",
            "missing": missing,
        }
    return _passed("privacy_guardrails", "Private data defaults local and cloud model use requires explicit approval.")


def _check_agent_models(agent_doc: dict[str, Any]) -> dict[str, Any]:
    agent = _agent(agent_doc)
    models = agent.get("models", {}) if isinstance(agent.get("models"), dict) else {}
    failures: list[str] = []
    if models.get("gateway_base_url") != "http://litellm:4000/v1":
        failures.append("Agent model gateway must be LiteLLM.")
    if models.get("default_model") != "vulcan-general":
        failures.append("Default model must remain vulcan-general during validation.")
    if models.get("allowed_models") != EXPECTED_MODELS:
        failures.append("Allowed models must be exactly the Freyja 6 Vulcan aliases.")
    if failures:
        return {"id": "agent_models", "status": "fail", "message": "freyja-test model config is not local-only.", "failures": failures}
    return _passed("agent_models", "freyja-test models are restricted to LiteLLM Vulcan aliases.")


def _check_litellm_models(litellm_doc: dict[str, Any]) -> dict[str, Any]:
    model_list = litellm_doc.get("model_list") if isinstance(litellm_doc.get("model_list"), list) else []
    names = [entry.get("model_name") for entry in model_list if isinstance(entry, dict)]
    failures: list[dict[str, Any]] = []
    if names != EXPECTED_MODELS:
        failures.append({"reason": "unexpected_model_aliases", "model_names": names})
    for entry in model_list:
        if not isinstance(entry, dict):
            failures.append({"reason": "model_entry_not_object"})
            continue
        name = str(entry.get("model_name") or "")
        params = entry.get("litellm_params") if isinstance(entry.get("litellm_params"), dict) else {}
        model = str(params.get("model") or "")
        api_base = str(params.get("api_base") or "")
        if not model.startswith("ollama/"):
            failures.append({"model_name": name, "reason": "model_not_routed_to_ollama_vulcan", "model": model})
        expected_target = EXPECTED_MODEL_TARGETS.get(name)
        if model != expected_target:
            failures.append({"model_name": name, "reason": "unexpected_vulcan_model_target", "model": model})
        if api_base != "os.environ/VULCAN_OLLAMA_BASE_URL":
            failures.append({"model_name": name, "reason": "api_base_not_vulcan_env", "api_base": _redact_url(api_base)})
        lowered_model = model.lower()
        if any(marker in lowered_model for marker in CLOUD_PROVIDER_MARKERS):
            failures.append({"model_name": name, "reason": "cloud_provider_marker", "model": model})
    failures.extend(_fallback_failures(litellm_doc))
    if failures:
        return {"id": "litellm_models", "status": "fail", "message": "LiteLLM config is not restricted to Vulcan local inference.", "failures": failures}
    return _passed("litellm_models", "LiteLLM exposes only Vulcan Ollama validation aliases.")


def _fallback_failures(litellm_doc: dict[str, Any]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    allowed = set(EXPECTED_MODELS)
    for path, value in _fallback_values(litellm_doc):
        text = str(value)
        lowered = text.lower()
        if any(marker in lowered for marker in CLOUD_PROVIDER_MARKERS):
            failures.append({"reason": "cloud_fallback_marker", "path": path, "target": text})
        elif text not in allowed:
            failures.append({"reason": "fallback_target_not_vulcan_alias", "path": path, "target": text})
    return failures


def _fallback_values(value: Any, path: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        found: list[tuple[str, Any]] = []
        for key, item in value.items():
            key_text = str(key)
            next_path = f"{path}.{key_text}" if path else key_text
            lowered_key = key_text.lower()
            if "fallback" in lowered_key:
                found.extend((child_path, child_value) for child_path, child_value in _flatten_values(item, next_path))
            else:
                found.extend(_fallback_values(item, next_path))
        return found
    if isinstance(value, list):
        found: list[tuple[str, Any]] = []
        for index, item in enumerate(value):
            found.extend(_fallback_values(item, f"{path}[{index}]"))
        return found
    return []


def _flatten_values(value: Any, path: str) -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        found: list[tuple[str, Any]] = []
        for key, item in value.items():
            found.extend(_flatten_values(item, f"{path}.{key}"))
        return found
    if isinstance(value, list):
        found: list[tuple[str, Any]] = []
        for index, item in enumerate(value):
            found.extend(_flatten_values(item, f"{path}[{index}]"))
        return found
    if value in (None, ""):
        return []
    return [(path, value)]


def _check_compose_model_environment(compose_doc: dict[str, Any]) -> dict[str, Any]:
    services = compose_doc.get("services") if isinstance(compose_doc.get("services"), dict) else {}
    litellm_env = _environment(services.get("litellm", {}))
    hermes_env = _environment(services.get("hermes-freyja-test", {}))
    cloud_like_keys: list[str] = []
    forbidden_hermes_vulcan_keys = sorted(key for key in hermes_env if key.startswith("VULCAN_"))
    for service_name, env in (("litellm", litellm_env), ("hermes-freyja-test", hermes_env)):
        for key in sorted(env):
            if key == "OPENAI_API_KEY" and service_name == "hermes-freyja-test" and env[key] == "${LITELLM_MASTER_KEY}":
                continue
            if any(marker in key for marker in CLOUD_ENV_MARKERS):
                cloud_like_keys.append(f"{service_name}.{key}")
    expected_vulcan = {"VULCAN_OLLAMA_BASE_URL", "VULCAN_FAST_MODEL", "VULCAN_GENERAL_MODEL", "VULCAN_CODE_MODEL"}
    missing_vulcan = sorted(key for key in expected_vulcan if key not in litellm_env)
    if cloud_like_keys or missing_vulcan or forbidden_hermes_vulcan_keys:
        return {
            "id": "compose_model_environment",
            "status": "fail",
            "message": "Compose model environment contains provider drift, Hermes direct-Vulcan access, or missing Vulcan env.",
            "cloud_like_keys": cloud_like_keys,
            "forbidden_hermes_vulcan_keys": forbidden_hermes_vulcan_keys,
            "missing_vulcan_keys": missing_vulcan,
        }
    return _passed("compose_model_environment", "Compose model environment is scoped to LiteLLM and Vulcan.")


def _check_hermes_gateway(compose_doc: dict[str, Any], contract_doc: dict[str, Any]) -> dict[str, Any]:
    services = compose_doc.get("services") if isinstance(compose_doc.get("services"), dict) else {}
    hermes_env = services.get("hermes-freyja-test", {}).get("environment", {}) if isinstance(services.get("hermes-freyja-test"), dict) else {}
    contract_env = contract_doc.get("required_environment") if isinstance(contract_doc.get("required_environment"), dict) else {}
    failures: list[str] = []
    if hermes_env.get("OPENAI_BASE_URL") != "http://litellm:4000/v1":
        failures.append("Compose Hermes OPENAI_BASE_URL must point to LiteLLM.")
    if contract_env.get("OPENAI_BASE_URL") != "http://litellm:4000/v1":
        failures.append("Runtime contract OPENAI_BASE_URL must point to LiteLLM.")
    if hermes_env.get("HERMES_DEFAULT_MODEL") != "vulcan-general":
        failures.append("Hermes default model must remain vulcan-general.")
    if failures:
        return {"id": "hermes_gateway", "status": "fail", "message": "Hermes model access is not locked to LiteLLM.", "failures": failures}
    return _passed("hermes_gateway", "Hermes model access goes through LiteLLM with the Vulcan default model.")


def _environment(service_doc: Any) -> dict[str, str]:
    if not isinstance(service_doc, dict):
        return {}
    env = service_doc.get("environment")
    if isinstance(env, dict):
        return {str(key): str(value) for key, value in env.items()}
    if isinstance(env, list):
        parsed: dict[str, str] = {}
        for item in env:
            if isinstance(item, str) and "=" in item:
                key, value = item.split("=", 1)
                parsed[key] = value
        return parsed
    return {}


def _agent(agent_doc: dict[str, Any]) -> dict[str, Any]:
    agents = agent_doc.get("agents") if isinstance(agent_doc.get("agents"), list) else []
    return next((agent for agent in agents if isinstance(agent, dict) and agent.get("id") == "freyja-test"), {})


def _next_actions(failures: list[dict[str, Any]]) -> list[str]:
    if failures:
        return [str(failures[0]["message"])]
    return ["Continue Freyja 6 validation with local Vulcan inference only."]


def _check_files(*paths: Path) -> dict[str, Any]:
    missing = [str(path) for path in paths if not _resolve(path).exists()]
    symlinks = [str(path) for path in paths if _resolve(path).is_symlink()]
    not_regular = [str(path) for path in paths if _resolve(path).exists() and not _resolve(path).is_file()]
    if missing:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required model privacy source files are missing.",
            "missing": missing,
        }
    if symlinks or not_regular:
        return {
            "id": "source_files",
            "status": "fail",
            "message": "Required model privacy source files must be regular files, not symlinks.",
            "symlinks": symlinks,
            "not_regular": not_regular,
        }
    return _passed("source_files", "Model privacy source files are present.")


def _load_yaml(path: Path) -> dict[str, Any]:
    resolved = _resolve(path)
    try:
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except OSError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _redact_url(url: str) -> str:
    return url.replace("100.94.80.21", "vulcan-tailnet").replace("127.0.0.1", "atlas-loopback")


def _passed(check_id: str, message: str) -> dict[str, Any]:
    return {"id": check_id, "status": "pass", "message": message}


def _output_path_failure(output: Path) -> str | None:
    if output.is_symlink():
        return f"output path must not be a symlink: {output.name}"
    if output.exists() and not output.is_file():
        return f"output path must be a regular file: {output.name}"
    return None


def _error_report(error: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "report_type": "freyja6-model-privacy-audit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ok": False,
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
            agent_config=args.agent_config,
            litellm_config=args.litellm_config,
            compose=args.compose,
            contract=args.contract,
        )
    )
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if not output_failure:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
