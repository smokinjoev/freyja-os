from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "inventory-open-webui-home-agent-platform.py"


def _module():
    spec = importlib.util.spec_from_file_location("inventory_open_webui_home_agent_platform", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_platform_inventory_contains_required_hosts_and_no_secret_values() -> None:
    inventory = _module().build_inventory(now=1)
    serialized = json.dumps(inventory).lower()

    assert inventory["secrets_included"] is False
    assert inventory["private_content_included"] is False
    assert set(inventory["hosts"]) == {"atlas", "vulcan", "iris", "hera"}
    assert inventory["hosts"]["vulcan"]["nexus_required"] is False
    assert "password=" not in serialized
    assert "token=" not in serialized
    assert "api_key=" not in serialized


def test_platform_inventory_records_endpoint_map_and_credential_locations_only() -> None:
    inventory = _module().build_inventory(now=1)

    assert inventory["endpoints"]["open_webui"] == "http://127.0.0.1:3001"
    assert inventory["endpoints"]["vulcan_ollama"] == "http://100.94.80.21:11434"
    assert inventory["credential_policy"]["values_recorded"] is False
    assert inventory["credential_policy"]["locations_only"] is True
    assert "deploy/compose/open-webui/.env" in inventory["hosts"]["atlas"]["credential_locations"]


def test_platform_inventory_writes_report(tmp_path: Path, capsys) -> None:
    output = tmp_path / "inventory.json"

    assert _module().main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "open-webui-home-agent-platform-inventory"
