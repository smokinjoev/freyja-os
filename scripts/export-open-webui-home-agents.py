#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
    "benedict": "agent/benedict",
    "agent-44": "agent/agent-47",
    "jenna": "agent/jennacide",
}


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
        records.append(
            {
                "id": model_id,
                "name": str(agent["display_name"]),
                "base_model_id": model_id,
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
        "schema_version": "1",
        "export_type": "open-webui-home-agent-import",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "config/open-webui-home-agents.yaml",
        "source_controlled": True,
        "secrets_included": False,
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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    export = build_export(load_manifest(args.source))
    rendered = json.dumps(export, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
