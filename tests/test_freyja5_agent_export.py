from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "freyja5-export-agent-definitions.py"


def load_export_module():
    spec = importlib.util.spec_from_file_location("freyja5_agent_export", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_freyja5_agent_export_is_source_controlled_and_secret_free() -> None:
    export = load_export_module().build_export()

    assert export["export_type"] == "freyja5-agent-definitions"
    assert export["source_controlled"] is True
    assert export["secrets_included"] is False
    assert export["opaque_product_database"] is False
    assert export["intended_import_boundary"] == "atlas-persistent-agent-plane"
    assert "api_key" not in str(export).lower()
    assert "token" not in str(export).lower()


def test_freyja5_agent_export_includes_agents_routes_and_mcp_boundaries() -> None:
    export = load_export_module().build_export()
    agents = {agent["id"]: agent for agent in export["agents"]}

    assert set(agents) == {"freyja", "cloyd-gibbler", "benedict", "benedict-paralegal", "agent-47", "jennacide"}
    assert agents["freyja"]["mcp_tool_count"] == 11
    assert agents["benedict-paralegal"]["cloud_egress_policy"] == "paralegal-local-only"
    assert agents["benedict-paralegal"]["mcp_tool_grants"] == [
        "browser.control",
        "documents.process",
        "vision.inspect",
    ]
    assert set(export["semantic_routes"]["routes"]) == {"fast", "general", "deep", "code", "vision", "embedding", "private"}
    assert export["semantic_routes"]["owner"] == "nexus"
    assert export["semantic_routes"]["cloud_fallback"] == "explicit_only"
    assert [server["id"] for server in export["mcp"]["servers"]] == [
        "iris-apple-mcp",
        "atlas-household-mcp",
        "atlas-media-mcp",
    ]
    assert export["mcp"]["default_agent_mcp_servers"] is False
    assert export["mcp"]["agent_consumption"]["freyja"] == "scoped_agent_tool_grants"
    assert export["gateway_policy"]["no_physical_model_selection"] is True


def test_freyja5_agent_export_cli_writes_json(tmp_path: Path, capsys) -> None:
    module = load_export_module()
    output = tmp_path / "freyja5-agents.json"

    assert module.main(["--output", str(output)]) == 0

    printed = json.loads(capsys.readouterr().out)
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["export_type"] == "freyja5-agent-definitions"
    assert printed["agents"] == written["agents"]


def test_freyja5_agent_export_script_is_executable() -> None:
    assert SCRIPT_PATH.exists()
    assert SCRIPT_PATH.stat().st_mode & 0o111
