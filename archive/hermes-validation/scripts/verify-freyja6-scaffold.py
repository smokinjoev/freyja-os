#!/usr/bin/env python3
"""Verify Freyja 6.0 scaffold invariants without touching live credentials."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_LITELLM_IMAGE = "ghcr.io/berriai/litellm:v1.89.0"
SOURCE_FILES = {
    "agent_config": ROOT / "config/freyja6/freyja-test.yaml",
    "contract": ROOT / "config/freyja6/hermes-runtime-contract.yaml",
    "isolation": ROOT / "config/freyja6/future-agent-isolation.yaml",
    "compose": ROOT / "deploy/compose/freyja6/compose.yaml",
    "litellm": ROOT / "deploy/compose/freyja6/litellm.config.yaml",
    "env_example": ROOT / "deploy/compose/freyja6/.env.example",
}


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _check_source_files(source_files: dict[str, Path]) -> list[str]:
    failures: list[str] = []
    for label, path in source_files.items():
        if not path.exists():
            failures.append(f"Scaffold source file is missing: {label} ({path}).")
        elif path.is_symlink():
            failures.append(f"Scaffold source file must not be a symlink: {label} ({path}).")
        elif not path.is_file():
            failures.append(f"Scaffold source file must be a regular file: {label} ({path}).")
    return failures


def _expand_env_reference(value: str, env: dict[str, str]) -> str:
    expanded = value
    for key, replacement in env.items():
        expanded = expanded.replace(f"${{{key}}}", replacement)
    return expanded


def _image_tag(image: str) -> str:
    if ":" not in image.rsplit("/", 1)[-1]:
        return ""
    return image.rsplit(":", 1)[1]


def main(source_files: dict[str, Path] | None = None) -> int:
    sources = source_files or SOURCE_FILES
    failures = _check_source_files(sources)
    if failures:
        result = {"ok": False, "failures": failures}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    agent_config = _load_yaml(sources["agent_config"])
    contract = _load_yaml(sources["contract"])
    isolation = _load_yaml(sources["isolation"])
    compose = _load_yaml(sources["compose"])
    litellm = _load_yaml(sources["litellm"])
    env_example = _load_env(sources["env_example"])

    agents = agent_config.get("agents", [])
    if [agent.get("id") for agent in agents] != ["freyja-test"]:
        failures.append("Phase 1 must define exactly one live agent: freyja-test.")
    future_agents = agent_config.get("future_agents", [])
    expected_future = ["Freyja", "Cloyd", "Benedict", "Agent 44", "Jenna"]
    if future_agents != expected_future:
        failures.append("Future agent roster must remain Freyja, Cloyd, Benedict, Agent 44, Jenna.")
    reservations = isolation.get("future_agents", [])
    reserved_names = [agent.get("display_name") for agent in reservations]
    if isolation.get("live_agents") != ["freyja-test"] or reserved_names != expected_future:
        failures.append("Future-agent isolation manifest must reserve the migration roster without enabling it.")
    boundary_fields = [
        "slug",
        "identity_file",
        "sessions_dir",
        "private_memory_dir",
        "credentials_env_prefix",
        "mcp_token_env",
    ]
    for field in boundary_fields:
        values = [agent.get(field) for agent in reservations]
        if len(values) != len(set(values)):
            failures.append(f"Future-agent isolation boundary must be unique: {field}.")
    messaging_tokens = [agent.get("messaging", {}).get("token_env") for agent in reservations]
    messaging_channels = [agent.get("messaging", {}).get("channel_env") for agent in reservations]
    if len(messaging_tokens) != len(set(messaging_tokens)) or len(messaging_channels) != len(set(messaging_channels)):
        failures.append("Future-agent Discord token and channel env vars must be unique.")

    services = compose.get("services", {})
    if "hermes-freyja-test" not in services:
        failures.append("Compose must include the single Hermes freyja-test service.")
    if contract.get("service", {}).get("name") != "hermes-freyja-test":
        failures.append("Hermes runtime contract must target hermes-freyja-test.")
    forbidden_services = {"freyja", "cloyd", "benedict", "agent-44", "jenna"}
    created_forbidden = sorted(forbidden_services.intersection(services))
    if created_forbidden:
        failures.append(f"Compose creates future agents too early: {created_forbidden}.")

    if services.get("litellm", {}).get("image") != "${LITELLM_IMAGE}":
        failures.append("Compose LiteLLM image must come from LITELLM_IMAGE.")
    if services.get("hermes-freyja-test", {}).get("image") != "${HERMES_AGENT_IMAGE}":
        failures.append("Compose Hermes image must come from HERMES_AGENT_IMAGE.")
    litellm_image = env_example.get("LITELLM_IMAGE", "")
    hermes_version = env_example.get("HERMES_AGENT_VERSION", "")
    hermes_image = _expand_env_reference(env_example.get("HERMES_AGENT_IMAGE", ""), env_example)
    if litellm_image != EXPECTED_LITELLM_IMAGE:
        failures.append(f"LiteLLM image must remain pinned to {EXPECTED_LITELLM_IMAGE}.")
    if _image_tag(hermes_image) != hermes_version:
        failures.append("Hermes Agent image tag must exactly match HERMES_AGENT_VERSION.")

    model_names = {entry.get("model_name") for entry in litellm.get("model_list", [])}
    required_models = {"vulcan-fast", "vulcan-general", "vulcan-code"}
    required_model_targets = {
        "vulcan-fast": "ollama/qwen2.5:7b",
        "vulcan-general": "ollama/qwen2.5:72b",
        "vulcan-code": "ollama/qwen3-coder-next:q4_K_M",
    }
    missing_models = sorted(required_models - model_names)
    if missing_models:
        failures.append(f"LiteLLM is missing model aliases: {missing_models}.")
    if model_names != required_models:
        failures.append("LiteLLM must expose only the Freyja 6 Vulcan validation aliases.")
    for entry in litellm.get("model_list", []):
        params = entry.get("litellm_params", {})
        if params.get("model") != required_model_targets.get(entry.get("model_name")):
            failures.append("LiteLLM validation models must route to Ollama/Vulcan.")
        if params.get("api_base") != "os.environ/VULCAN_OLLAMA_BASE_URL":
            failures.append("LiteLLM validation models must use the Vulcan base URL env.")

    agent = agents[0] if agents else {}
    if agent.get("messaging", {}).get("gateway") != "discord":
        failures.append("Initial messaging gateway must be Discord.")
    messaging = agent.get("messaging", {})
    if messaging.get("channel_scope") != "dedicated-test-channel":
        failures.append("Initial messaging must use one dedicated Discord test channel.")
    if messaging.get("credentials_source") != "environment":
        failures.append("Discord credentials must be sourced from environment.")
    if messaging.get("env", {}).get("token") != "FREYJA6_DISCORD_BOT_TOKEN":
        failures.append("Discord bot token must use the Freyja 6 test env var.")
    if messaging.get("env", {}).get("channel_id") != "FREYJA6_DISCORD_CHANNEL_ID":
        failures.append("Discord channel must use the Freyja 6 test env var.")
    if agent.get("memory", {}).get("provider") != "hermes-native":
        failures.append("Initial memory provider must be Hermes native memory.")
    if agent.get("memory", {}).get("private_dir") != "/var/lib/hermes/agents/freyja-test/memory/private":
        failures.append("freyja-test private memory must stay under its Hermes agent root.")
    if agent.get("memory", {}).get("shared_household_dir") is not None:
        failures.append("Shared household memory must remain disabled during Phase 1.")
    runtime_paths = contract.get("runtime_paths", {})
    if runtime_paths.get("private_memory_dir") != agent.get("memory", {}).get("private_dir"):
        failures.append("Hermes runtime contract private memory path must match freyja-test config.")
    terminal = agent.get("tools", {}).get("terminal", {})
    if terminal.get("enabled") is not True:
        failures.append("Terminal tool must be explicitly enabled for freyja-test.")
    if terminal.get("safe_commands") != ["pwd", "date", "whoami", "ls", "rg"]:
        failures.append("Terminal safe commands must remain the Freyja 6 non-mutating allowlist.")
    filesystem = agent.get("tools", {}).get("filesystem", {})
    if filesystem.get("approved_roots") != ["/workspace/approved"]:
        failures.append("Filesystem access must be limited to /workspace/approved.")
    if filesystem.get("mode") != "read-only":
        failures.append("Filesystem access must remain read-only.")
    if runtime_paths.get("approved_files_root") != "/workspace/approved":
        failures.append("Hermes runtime contract approved filesystem root must match freyja-test config.")
    tools = agent.get("tools", {})
    if tools.get("mcp", {}).get("enabled") is not True:
        failures.append("MCP support must be enabled for freyja-test.")
    if tools.get("calendar", {}).get("boundary") != "mcp":
        failures.append("Calendar must route through MCP.")
    if tools.get("calendar", {}).get("enabled") is not True:
        failures.append("Calendar tool must be enabled for freyja-test.")
    if tools.get("home_assistant", {}).get("boundary") != "mcp":
        failures.append("Home Assistant must route through MCP.")
    if tools.get("coding_agent", {}).get("executor") != "opencode":
        failures.append("Coding workflow must keep OpenCode as the executor.")
    if tools.get("coding_agent", {}).get("enabled") is not True:
        failures.append("Coding workflow must be enabled for freyja-test.")
    schedules_config = agent.get("schedules", {})
    if schedules_config.get("enabled") is not True:
        failures.append("Schedules must be enabled for freyja-test.")
    if schedules_config.get("host_config_source") != "config/freyja6/schedules.yaml":
        failures.append("Schedules host_config_source must be config/freyja6/schedules.yaml.")
    if agent.get("models", {}).get("gateway_base_url") != "http://litellm:4000/v1":
        failures.append("Agent model access must go through LiteLLM, not Vulcan directly.")
    if contract.get("required_environment", {}).get("OPENAI_BASE_URL") != "http://litellm:4000/v1":
        failures.append("Hermes runtime contract must route model calls through LiteLLM.")
    if agent.get("models", {}).get("allowed_models") != ["vulcan-fast", "vulcan-general", "vulcan-code"]:
        failures.append("Agent allowed models must remain the Freyja 6 Vulcan aliases.")

    guardrails = agent_config.get("guardrails", {})
    if not guardrails.get("do_not_migrate_existing_systems"):
        failures.append("Migration guardrail is missing.")
    if not guardrails.get("cloud_model_use_requires_explicit_approval"):
        failures.append("Cloud model approval guardrail is missing.")

    result = {"ok": not failures, "failures": failures}
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
