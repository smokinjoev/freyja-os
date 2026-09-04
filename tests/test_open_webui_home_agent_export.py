from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "export-open-webui-home-agents.py"


def _module():
    spec = importlib.util.spec_from_file_location("export_open_webui_home_agents", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_open_webui_home_agent_export_is_complete_and_secret_free() -> None:
    export = _module().build_export()
    records = {record["id"]: record for record in export["records"]}

    assert export["export_type"] == "open-webui-home-agent-import"
    assert export["source_controlled"] is True
    assert export["secrets_included"] is False
    assert export["open_webui_provider"] == "http://model-proxy:8080/v1"
    assert set(records) == {"agent/freyja", "agent/cloyd-gibbler", "agent/benedict", "agent/agent-47", "agent/jennacide"}
    assert "token" not in str(export).lower()
    assert "api_key" not in str(export).lower()


def test_benedict_export_has_local_only_restricted_policy() -> None:
    records = {record["id"]: record for record in _module().build_export()["records"]}
    benedict = records["agent/benedict"]

    assert benedict["freyja"]["agent_id"] == "benedict"
    assert benedict["freyja"]["memory_policy"]["cloud_fallback"] == "forbidden"
    assert benedict["freyja"]["permitted_knowledge"] == ["personal:beth", "restricted:benedict"]
    assert "cloud_fallback" in benedict["freyja"]["tools"]["deny"]
    assert benedict["access_control"]["read"]["group_ids"] == ["beth"]


def test_child_exports_deny_admin_messaging_and_device_actions() -> None:
    records = {record["id"]: record for record in _module().build_export()["records"]}

    for record_id, friendly_id in (("agent/agent-47", "agent-44"), ("agent/jennacide", "jenna")):
        denied = records[record_id]["freyja"]["tools"]["deny"]
        assert records[record_id]["freyja"]["agent_id"] == friendly_id
        assert records[record_id]["freyja"]["runtime_model_id"] == record_id
        assert "admin" in denied
        assert "messaging.send" in denied
        assert "home.device_action" in denied
        assert records[record_id]["freyja"]["tools"]["confirm"] == []


def test_open_webui_home_agent_export_cli_writes_json(tmp_path: Path, capsys) -> None:
    module = _module()
    output = tmp_path / "agents.json"

    assert module.main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["records"][0]["base_model_id"].startswith("agent/")
