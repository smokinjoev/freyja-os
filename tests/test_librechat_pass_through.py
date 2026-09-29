from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify-librechat-pass-through.py"
CONFIG = REPO_ROOT / "deploy/compose/librechat/librechat.yaml"
ENV_EXAMPLE = REPO_ROOT / "deploy/compose/librechat/.env.example"


def _module():
    spec = importlib.util.spec_from_file_location("verify_librechat_pass_through", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_librechat_trial_config_routes_only_to_nexus_and_freyja_core() -> None:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    endpoint = next(endpoint for endpoint in config["endpoints"]["custom"] if endpoint["name"] == "Vulcan Nexus")

    assert endpoint["baseURL"] == "${NEXUS_OPENAI_BASE_URL}"
    assert endpoint["apiKey"] == "${NEXUS_OPENAI_API_KEY}"
    assert set(endpoint["models"]["default"]) >= {
        "@preset/freyja-coder",
        "@preset/freyja-strong-local",
        "@preset/freyja-fast-local",
    }
    expected_mcp_servers = {
        "freyja-core-freyja": "${FREYJA_CORE_MCP_FREYJA_TOKEN}",
        "freyja-core-cloyd": "${FREYJA_CORE_MCP_CLOYD_GIBBLER_TOKEN}",
        "freyja-core-benedict": "${FREYJA_CORE_MCP_BENEDICT_TOKEN}",
        "freyja-core-agent47": "${FREYJA_CORE_MCP_AGENT_47_TOKEN}",
        "freyja-core-jenna": "${FREYJA_CORE_MCP_JENNACIDE_TOKEN}",
    }
    assert set(config["mcpServers"]) == set(expected_mcp_servers)
    for server_name, token_placeholder in expected_mcp_servers.items():
        server = config["mcpServers"][server_name]
        assert server["url"] == "${FREYJA_CORE_MCP_URL}"
        assert server["type"] == "streamable-http"
        assert server["headers"]["Authorization"] == f"Bearer {token_placeholder}"
    assert "host.docker.internal:8766" in config["mcpSettings"]["allowedAddresses"]
    assert "100.94.80.21:3939" in config["endpoints"]["allowedAddresses"]


def test_librechat_env_example_contains_no_real_secrets() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "NEXUS_OPENAI_BASE_URL=http://100.94.80.21:3939/v1" in text
    assert "FREYJA_CORE_MCP_URL=http://100.115.228.56:8766/mcp" in text
    for variable in (
        "FREYJA_CORE_MCP_FREYJA_TOKEN",
        "FREYJA_CORE_MCP_CLOYD_GIBBLER_TOKEN",
        "FREYJA_CORE_MCP_BENEDICT_TOKEN",
        "FREYJA_CORE_MCP_AGENT_47_TOKEN",
        "FREYJA_CORE_MCP_JENNACIDE_TOKEN",
    ):
        assert f"{variable}=replace-with-" in text
    assert "nxs_" not in text
    assert "replace-with-local-nexus-token" in text


def test_librechat_msty_provider_snapshot_redacts_key(tmp_path: Path) -> None:
    module = _module()
    db = tmp_path / "msty-go.db"
    conn = sqlite3.connect(db)
    conn.execute("create table providers (id text, name text, type text, api_key text, base_url text)")
    conn.execute(
        "insert into providers values (?, ?, ?, ?, ?)",
        ("p1", "Vulcan Nexus", "openai", "secret", "http://100.94.80.21:3939/v1"),
    )
    conn.commit()
    conn.close()

    provider = module._msty_provider(db)

    assert provider["ok"] is True
    assert provider["has_api_key"] is True
    assert provider["api_key"] == "secret"
