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
DEFAULT_SOURCE = REPO_ROOT / "config" / "open-webui-home-resources.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "certification" / "reports" / "open-webui-home-resources-export.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export Freyja Open WebUI Knowledge, memory, and tool resource payloads.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def load_source(path: Path = DEFAULT_SOURCE) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("resource manifest must be a mapping")
    if data.get("secrets_included") is not False:
        raise ValueError("refusing resource manifest that may contain secrets")
    return data


def _git_head() -> str | None:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def build_export(source: dict[str, Any] | None = None) -> dict[str, Any]:
    manifest = source or load_source()
    resources = manifest.get("resources") or {}
    knowledge = []
    for item in resources.get("knowledge") or []:
        knowledge.append(
            {
                "id": item["id"],
                "name": item["name"],
                "description": item.get("description") or "",
                "meta": {
                    "freyja": {
                        "scope": item["scope"],
                        "owner_group": item["owner_group"],
                        "sensitivity": item["sensitivity"],
                        "allowed_agents": item.get("allowed_agents") or [],
                        "excluded_agents": item.get("excluded_agents") or [],
                        "seed_policy": item.get("seed_policy") or {},
                    }
                },
                "data": {"source": "freyja-open-webui-home-resources"},
            }
        )

    tools = []
    for item in resources.get("tools") or []:
        tools.append(
            {
                "id": item["id"],
                "name": item["name"],
                "boundary": item["boundary"],
                "operations": item.get("operations") or [],
                "meta": {
                    "freyja": {
                        "allowed_agents": item.get("allowed_agents") or [],
                        "confirmation_required": item.get("confirmation_required") or [],
                        "destructive_default": item.get("destructive_default"),
                        "children_allowed_operations": item.get("children_allowed_operations") or [],
                        "host": item.get("host"),
                        "base_url": item.get("base_url"),
                        "remote_capabilities": item.get("remote_capabilities") or {},
                        "openapi_schema_report": "certification/reports/open-webui-tools-openapi.json"
                        if item.get("boundary") == "openapi"
                        else None,
                    }
                },
            }
        )

    return {
        "report_type": "open-webui-home-resources-export",
        "export_type": "open-webui-home-resources",
        "schema_version": manifest.get("schema_version"),
        "generated_at_unix": int(time.time()),
        "git_head": _git_head(),
        "secrets_included": False,
        "private_content_included": False,
        "knowledge": knowledge,
        "native_memory": resources.get("native_memory") or {},
        "tools": tools,
        "readiness": {
            "requires_open_webui_owner_user": True,
            "requires_authenticated_import": True,
            "safe_for_source_control": True,
        },
    }


def validate_export(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    knowledge = {item["id"]: item for item in payload.get("knowledge") or []}
    tools = {item["id"]: item for item in payload.get("tools") or []}
    if {"freyja_household", "freyja_projects", "benedict_restricted"} - set(knowledge):
        errors.append("missing required Knowledge collection")
    benedict = knowledge.get("benedict_restricted", {})
    allowed = set(benedict.get("meta", {}).get("freyja", {}).get("allowed_agents") or [])
    excluded = set(benedict.get("meta", {}).get("freyja", {}).get("excluded_agents") or [])
    if allowed != {"benedict"}:
        errors.append("Benedict restricted Knowledge must allow only Benedict")
    if not {"freyja", "cloyd", "agent-44", "jenna"} <= excluded:
        errors.append("Benedict restricted Knowledge must exclude other agents")
    for tool in tools.values():
        meta = tool.get("meta", {}).get("freyja", {})
        if meta.get("destructive_default") != "deny":
            errors.append(f"{tool['id']} destructive_default must be deny")
    iris = tools.get("iris_apple", {})
    if iris.get("boundary") != "mcp" or iris.get("meta", {}).get("freyja", {}).get("host") != "iris":
        errors.append("Iris tool boundary must be MCP on Iris")
    iris_remote = iris.get("meta", {}).get("freyja", {}).get("remote_capabilities") or {}
    if set(iris_remote.get("read_only") or []) != {"calendar.read", "reminders.read"}:
        errors.append("Iris read-only remote capabilities must be Calendar and Reminders reads")
    if not {"calendar.create", "reminders.create", "imessage.send.approved", "shortcuts.run"} <= set(
        iris_remote.get("approved_writes") or []
    ):
        errors.append("Iris approved remote writes must include Calendar, Reminders, iMessage, and Shortcuts")
    if iris_remote.get("homepod_path") != "shortcuts.run":
        errors.append("Iris HomePod path must remain Shortcuts-based")
    if iris_remote.get("requires_active_macos_user_session") is not True:
        errors.append("Iris remote actions must require an active macOS user session")
    if tools.get("freyja_home_memory", {}).get("boundary") != "openapi":
        errors.append("home-memory tool boundary must be OpenAPI")
    if payload.get("native_memory", {}).get("mode") != "per_user":
        errors.append("native memory mode must be per_user")
    if payload.get("secrets_included") is not False:
        errors.append("export must not include secrets")
    return errors


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = build_export(load_source(args.source))
    errors = validate_export(payload)
    payload["validation_errors"] = errors
    payload["ok"] = not errors
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
