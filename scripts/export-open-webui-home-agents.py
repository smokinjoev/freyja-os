#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "config" / "open-webui-home-agents.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-home-agents-import.json"
AGENT_MODEL_IDS = {
    "freyja": "agent/freyja",
    "cloyd": "agent/cloyd-gibbler",
    "smith": "agent/freyja-coder",
    "benedict": "agent/benedict",
    "agent-44": "agent/agent-47",
    "jenna": "agent/jennacide",
}
REQUIRED_AGENT_IDS = {"freyja", "cloyd", "smith", "benedict", "agent-44", "jenna"}
CHILD_AGENT_IDS = {"agent-44", "jenna"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export non-secret Open WebUI home-agent import payloads.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def load_manifest(path: Path = DEFAULT_SOURCE) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("agent manifest must be a mapping")
    return data


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def build_export(manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    source = manifest or load_manifest()
    model_profiles = source.get("model_profiles") if isinstance(source.get("model_profiles"), dict) else {}
    agents = source.get("agents") if isinstance(source.get("agents"), list) else []

    records = []
    for agent in agents:
        if not isinstance(agent, dict):
            continue
        agent_id = str(agent["id"])
        profile_id = str(agent["model_profile"])
        profile = model_profiles[profile_id]
        model_id = AGENT_MODEL_IDS.get(agent_id, f"agent/{agent_id}")
        base_model_id = str(profile["model"])
        records.append(
            {
                "id": model_id,
                "name": str(agent["display_name"]),
                "base_model_id": base_model_id,
                "meta": {
                    "profile_image_url": "/static/favicon.png",
                    "description": str(agent["purpose"]),
                    "capabilities": {
                        "vision": profile_id == "vision_documents" or "image.analyze" in _tool_list(agent, "allow"),
                        "citations": True,
                        "usage": True,
                    },
                    "suggestion_prompts": [],
                    "tags": ["freyja", "home-agent", profile_id],
                },
                "params": {
                    "system": str(agent["system_prompt"]).strip(),
                    "temperature": 0.2 if profile_id in {"coding", "strong_reasoning"} else 0.4,
                    "top_p": 0.9,
                },
                "access_control": {
                    "read": {"group_ids": list(agent.get("access") or [])},
                    "write": {"group_ids": []},
                },
                "freyja": {
                    "agent_id": agent_id,
                    "runtime_model_id": model_id,
                    "base_model_id": base_model_id,
                    "model_profile": profile_id,
                    "provider": profile["provider"],
                    "local_model": profile["model"],
                    "keep_local": bool(profile.get("keep_local")),
                    "permitted_knowledge": list(agent.get("permitted_knowledge") or []),
                    "memory_policy": agent.get("memory_policy") or {},
                    "tools": agent.get("tools") or {},
                    "access": list(agent.get("access") or []),
                },
            }
        )

    return {
        "report_type": "open-webui-home-agents-import",
        "schema_version": "1",
        "export_type": "open-webui-home-agent-import",
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "config/open-webui-home-agents.yaml",
        "source_controlled": True,
        "secrets_included": False,
        "private_content_included": False,
        "open_webui_provider": "http://model-proxy:8080/v1",
        "records": records,
        "knowledge_collections": sorted(
            {
                item
                for agent in agents
                if isinstance(agent, dict)
                for item in agent.get("permitted_knowledge", [])
            }
        ),
        "tool_assignments": {
            str(agent["id"]): agent.get("tools") or {}
            for agent in agents
            if isinstance(agent, dict) and agent.get("id")
        },
        "memory_assignments": {
            str(agent["id"]): agent.get("memory_policy") or {}
            for agent in agents
            if isinstance(agent, dict) and agent.get("id")
        },
    }


def _tool_list(agent: dict[str, Any], key: str) -> list[str]:
    tools = agent.get("tools") if isinstance(agent.get("tools"), dict) else {}
    values = tools.get(key) if isinstance(tools, dict) else []
    return [str(value) for value in values or []]


def validate_export(export: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    records = {record.get("freyja", {}).get("agent_id"): record for record in export.get("records") or []}
    record_ids = {record.get("id") for record in export.get("records") or []}
    missing_agents = REQUIRED_AGENT_IDS - set(records)
    if missing_agents:
        errors.append(f"missing required agents: {sorted(missing_agents)}")
    missing_model_ids = set(AGENT_MODEL_IDS.values()) - record_ids
    if missing_model_ids:
        errors.append(f"missing required Open WebUI model IDs: {sorted(missing_model_ids)}")

    for agent_id, record in records.items():
        freyja = record.get("freyja") or {}
        tools = freyja.get("tools") or {}
        if freyja.get("provider") != "vulcan_ollama":
            errors.append(f"{agent_id} provider must be vulcan_ollama")
        if freyja.get("keep_local") is not True:
            errors.append(f"{agent_id} must keep inference local")
        if "cloud_fallback" not in set(tools.get("deny") or []):
            errors.append(f"{agent_id} must deny cloud_fallback")

    benedict = records.get("benedict") or {}
    benedict_freyja = benedict.get("freyja") or {}
    benedict_tools = benedict_freyja.get("tools") or {}
    benedict_access = ((benedict.get("access_control") or {}).get("read") or {}).get("group_ids") or []
    if benedict_access != ["beth"]:
        errors.append("Benedict access must be restricted to Beth")
    if benedict_freyja.get("memory_policy", {}).get("cloud_fallback") != "forbidden":
        errors.append("Benedict memory policy must forbid cloud fallback")
    if set(benedict_freyja.get("permitted_knowledge") or []) != {"personal:beth", "restricted:benedict"}:
        errors.append("Benedict permitted knowledge must be Beth personal and restricted Benedict only")
    if set(benedict_tools.get("confirm") or []):
        errors.append("Benedict must not have confirmable write tools")

    cloyd = records.get("cloyd") or {}
    cloyd_tools = (cloyd.get("freyja") or {}).get("tools") or {}
    cloyd_denied = set(cloyd_tools.get("deny") or [])
    for required in ("opencode.start", "opencode.send", "opencode.shell", "opencode.stop"):
        if required not in set(cloyd_tools.get("coding") or []):
            errors.append(f"Cloyd must be able to command {required}")
    for required in ("children.admin", "cloud_fallback", "unrestricted_shell"):
        if required not in cloyd_denied:
            errors.append(f"Cloyd must deny {required}")

    smith = records.get("smith") or {}
    smith_freyja = smith.get("freyja") or {}
    smith_tools = smith_freyja.get("tools") or {}
    if smith.get("id") != "agent/freyja-coder":
        errors.append("Agent Smith must export as agent/freyja-coder")
    if smith_freyja.get("model_profile") != "coding":
        errors.append("Agent Smith must use the coding model profile")
    if set(smith_tools.get("coding") or []) != {"opencode.start", "opencode.send", "opencode.shell", "opencode.stop"}:
        errors.append("Agent Smith must have the OpenCode coding runtime tools")
    for prohibited in ("calendar.create", "reminders.create", "messaging.send", "home.device_action", "cloud_fallback"):
        if prohibited not in set(smith_tools.get("deny") or []):
            errors.append(f"Agent Smith must deny {prohibited}")
    if set(smith_tools.get("confirm") or []):
        errors.append("Agent Smith must not have household confirm tools")

    for agent_id in CHILD_AGENT_IDS:
        child = records.get(agent_id) or {}
        child_tools = (child.get("freyja") or {}).get("tools") or {}
        denied = set(child_tools.get("deny") or [])
        for required in ("admin", "messaging.send", "home.device_action", "cloud_fallback"):
            if required not in denied:
                errors.append(f"{agent_id} must deny {required}")
        if child_tools.get("confirm"):
            errors.append(f"{agent_id} must not have confirmable tools")
    if export.get("secrets_included") is not False:
        errors.append("export must not include secrets")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    export = build_export(load_manifest(args.source))
    errors = validate_export(export)
    export["validation_errors"] = errors
    export["ok"] = not errors
    rendered = json.dumps(export, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if export["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
