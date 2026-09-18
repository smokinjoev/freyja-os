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
    assert config["mcpServers"]["freyja-core"]["url"] == "${FREYJA_CORE_MCP_URL}"
    assert config["mcpServers"]["freyja-core"]["type"] == "streamable-http"
    assert "host.docker.internal:8766" in config["mcpSettings"]["allowedAddresses"]
    assert "100.94.80.21:3939" in config["endpoints"]["allowedAddresses"]


def test_librechat_env_example_contains_no_real_secrets() -> None:
    text = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "NEXUS_OPENAI_BASE_URL=http://100.94.80.21:3939/v1" in text
    assert "FREYJA_CORE_MCP_URL=http://host.docker.internal:8766/mcp" in text
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
