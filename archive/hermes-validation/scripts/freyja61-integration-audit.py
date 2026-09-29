#!/usr/bin/env python3
"""Verify Freyja 6.1 integration contracts without contacting live services."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "freyja61"


def load_yaml(name: str) -> dict[str, Any]:
    path = CONFIG / name
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"required regular file missing: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def fail_if(condition: bool, message: str, failures: list[str]) -> None:
    if condition:
        failures.append(message)


def audit() -> dict[str, Any]:
    failures: list[str] = []
    registry = load_yaml("endpoint-registry.yaml")
    parent = load_yaml("hermes-parent.yaml")
    roles = load_yaml("subagent-roles.yaml")
    activation = load_yaml("tool-activation.yaml")
    memory = load_yaml("memory-boundaries.yaml")

    endpoints = {item.get("id"): item for item in registry.get("endpoints", [])}
    required = {"freyja61-litellm", "freyja-core", "freyja-core-mcp", "macagent-mcp", "opencode", "nexus", "vulcan-ollama", "msty-go", "open-webui-iris", "freyja5", "freyja3"}
    fail_if(not required.issubset(endpoints), "Endpoint registry is missing a required 6.1 or preserved surface.", failures)
    fail_if(endpoints.get("freyja61-litellm", {}).get("host") != "iris", "Freyja 6.1 LiteLLM must remain on Iris.", failures)
    fail_if(endpoints.get("vulcan-ollama", {}).get("host") != "vulcan-1", "Vulcan must remain the inference host.", failures)
    for endpoint_id in ("msty-go", "open-webui-iris", "freyja5", "freyja3"):
        fail_if(endpoints.get(endpoint_id, {}).get("lifecycle") != "preserved", f"{endpoint_id} must be preserved.", failures)
    for endpoint_id in ("macagent-mcp", "opencode"):
        fail_if(endpoints.get(endpoint_id, {}).get("callers") != ["freyja-core"], f"{endpoint_id} must be reachable only through Freyja Core.", failures)

    fail_if(parent.get("runtime_agent_id") != "freyja-test", "The initial 6.1 parent must retain the working freyja-test runtime.", failures)
    delegation = parent.get("delegation", {})
    fail_if(delegation.get("max_concurrent_children") != 2, "Delegation concurrency must be capped at two.", failures)
    fail_if(delegation.get("max_spawn_depth") != 1, "Delegation must remain flat.", failures)
    fail_if(delegation.get("child_public_delivery") is not False, "Child roles must not deliver directly to Discord.", failures)
    fail_if(parent.get("tool_transport", {}).get("direct_downstream_access") is not False, "Hermes must not have direct downstream tool access.", failures)

    expected_roles = {"research", "household", "coding"}
    actual_roles = {role.get("id") for role in roles.get("roles", [])}
    fail_if(actual_roles != expected_roles, "Freyja 6.1 must define exactly research, household, and coding child roles.", failures)
    for role in roles.get("roles", []):
        role_id = role.get("id", "unknown")
        fail_if(role.get("direct_credentials") is not False, f"{role_id} must not have direct credentials.", failures)
        fail_if(role.get("durable_memory_write") is not False, f"{role_id} must not write durable memory.", failures)
        fail_if(role.get("discord_delivery") is not False, f"{role_id} must not deliver to Discord.", failures)

    stages = activation.get("stages", [])
    expected_stages = ["status-and-calendar-read", "calendar-write", "home-read", "opencode-lifecycle"]
    fail_if([stage.get("id") for stage in stages] != expected_stages, "Tool activation stages must remain ordered and narrow.", failures)
    fail_if(activation.get("default_state") != "disabled-until-certified", "Tool activation must default to disabled until certification.", failures)

    store_ids = {store.get("id") for store in memory.get("stores", [])}
    fail_if(store_ids != {"msty-go-named-agent-memory", "hermes-parent-private-memory", "freyja-core-shared-memory"}, "Memory stores must retain the three-tier boundary.", failures)
    fail_if(memory.get("future_bridge", {}).get("state") != "design-only", "The Msty Go bridge must remain design-only.", failures)
    return {"ok": not failures, "failures": failures, "checked": {"endpoints": len(endpoints), "roles": len(actual_roles), "activation_stages": len(stages)}}


if __name__ == "__main__":
    report = audit()
    print(json.dumps(report, indent=2, sort_keys=True))
    sys.exit(0 if report["ok"] else 1)
