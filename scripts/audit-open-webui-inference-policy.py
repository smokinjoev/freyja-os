#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-inference-policy-audit.json"
PROXY = REPO_ROOT / "deploy" / "compose" / "open-webui" / "model-proxy.py"
COMPOSE = REPO_ROOT / "deploy" / "compose" / "open-webui" / "compose.yaml"
ENV_EXAMPLE = REPO_ROOT / "deploy" / "compose" / "open-webui" / ".env.example"
AGENTS = REPO_ROOT / "config" / "open-webui-home-agents.yaml"
PROXY_CATALOG = REPO_ROOT / "certification" / "reports" / "open-webui-model-proxy-catalog.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit Open WebUI inference policy without live credentials.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def _load_proxy():
    spec = importlib.util.spec_from_file_location("open_webui_model_proxy_policy_audit", PROXY)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load model proxy")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def build_audit() -> dict[str, Any]:
    proxy = _load_proxy()
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    env_example = ENV_EXAMPLE.read_text(encoding="utf-8")
    agents = yaml.safe_load(AGENTS.read_text(encoding="utf-8"))
    catalog = json.loads(PROXY_CATALOG.read_text(encoding="utf-8"))
    open_webui_env = compose["services"]["open-webui"]["environment"]
    proxy_env = compose["services"]["model-proxy"]["environment"]
    source = PROXY.read_text(encoding="utf-8")

    profiles = agents.get("model_profiles") or {}
    expected_profiles = {"fast_chat", "strong_reasoning", "vision_documents", "coding"}
    checks = [
        {
            "name": "open_webui_uses_model_proxy",
            "ok": open_webui_env.get("OPENAI_API_BASE_URL") == "${OPENAI_API_BASE_URL:-http://model-proxy:8080/v1}",
        },
        {
            "name": "primary_vulcan_endpoint_configured",
            "ok": "100.94.80.21:8088/v1" in proxy_env.get("PRIMARY_BASE_URL", "") or "OPENAI_PRIMARY_BASE_URL=http://100.94.80.21:8088/v1" in env_example,
        },
        {
            "name": "vulcan_ollama_unload_endpoint_configured",
            "ok": "100.94.80.21:11434" in proxy_env.get("PRIMARY_OLLAMA_BASE_URL", "") or "OPENAI_PRIMARY_OLLAMA_BASE_URL=http://100.94.80.21:11434" in env_example,
        },
        {
            "name": "nexus_not_required",
            "ok": "NEXUS" not in env_example and "NEXUS" not in source,
        },
        {
            "name": "model_profiles_complete",
            "ok": expected_profiles <= set(profiles),
            "evidence": {"profiles": sorted(profiles)},
        },
        {
            "name": "model_profiles_local_only",
            "ok": all(profile.get("provider") == "vulcan_ollama" and profile.get("keep_local") is True for profile in profiles.values()),
        },
        {
            "name": "unloads_other_primary_models",
            "ok": "_unload_other_primary_models(requested_model)" in source and "keep_alive\": 0" in source,
        },
        {
            "name": "large_model_guard_enabled",
            "ok": bool(proxy.GARBAGE_GUARD_MODELS) and proxy.GARBAGE_GUARD_MIN_TOKENS >= 512,
            "evidence": {"guarded_model_count": len(proxy.GARBAGE_GUARD_MODELS), "min_tokens": proxy.GARBAGE_GUARD_MIN_TOKENS},
        },
        {
            "name": "agent_models_in_proxy_catalog",
            "ok": catalog.get("ok") is True and not catalog.get("agent_models_missing"),
            "evidence": {"agent_models_present": catalog.get("agent_models_present")},
        },
        {
            "name": "cloud_fallback_disabled_for_open_webui_path",
            "ok": "CLOUD_ENABLED=true" not in env_example and "openrouter" not in env_example.lower(),
        },
    ]
    return {
        "report_type": "open-webui-inference-policy-audit",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "secrets_included": False,
        "private_content_included": False,
        "checks": checks,
        "ok": all(check["ok"] for check in checks),
        "model_profiles": {name: profiles[name]["model"] for name in sorted(profiles)},
    }


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    audit = build_audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2, sort_keys=True))
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
