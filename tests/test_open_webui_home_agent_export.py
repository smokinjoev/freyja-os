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
    assert export["report_type"] == "open-webui-home-agents-import"
    assert isinstance(export["generated_at_unix"], int)
    assert export["git_head"]
    assert export["source_controlled"] is True
    assert export["secrets_included"] is False
    assert export["private_content_included"] is False
    assert export["open_webui_provider"] == "http://model-proxy:8080/v1"
    assert _module().validate_export(export) == []
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


def test_agent_export_validation_rejects_missing_required_agent() -> None:
    module = _module()
    export = module.build_export()
    export["records"] = [record for record in export["records"] if record["freyja"]["agent_id"] != "jenna"]

    errors = module.validate_export(export)

    assert "missing required agents: ['jenna']" in errors
    assert "missing required Open WebUI model IDs: ['agent/jennacide']" in errors


def test_agent_export_validation_rejects_nonlocal_or_cloud_fallback_policy() -> None:
    module = _module()
    export = module.build_export()
    freyja = next(record for record in export["records"] if record["freyja"]["agent_id"] == "freyja")
    freyja["freyja"]["provider"] = "nexus"
    freyja["freyja"]["keep_local"] = False
    freyja["freyja"]["tools"]["deny"] = []

    errors = module.validate_export(export)

    assert "freyja provider must be vulcan_ollama" in errors
    assert "freyja must keep inference local" in errors
    assert "freyja must deny cloud_fallback" in errors


def test_agent_export_validation_rejects_benedict_policy_drift() -> None:
    module = _module()
    export = module.build_export()
    benedict = next(record for record in export["records"] if record["freyja"]["agent_id"] == "benedict")
    benedict["access_control"]["read"]["group_ids"] = ["beth", "joe"]
    benedict["freyja"]["memory_policy"]["cloud_fallback"] = "allowed"
    benedict["freyja"]["permitted_knowledge"] = ["household"]
    benedict["freyja"]["tools"]["confirm"] = ["calendar.create"]

    errors = module.validate_export(export)

    assert "Benedict access must be restricted to Beth" in errors
    assert "Benedict memory policy must forbid cloud fallback" in errors
    assert "Benedict permitted knowledge must be Beth personal and restricted Benedict only" in errors
    assert "Benedict must not have confirmable write tools" in errors


def test_agent_export_validation_rejects_child_policy_drift() -> None:
    module = _module()
    export = module.build_export()
    child = next(record for record in export["records"] if record["freyja"]["agent_id"] == "agent-44")
    child["freyja"]["tools"]["deny"] = ["cloud_fallback"]
    child["freyja"]["tools"]["confirm"] = ["home.device_action"]

    errors = module.validate_export(export)

    assert "agent-44 must deny admin" in errors
    assert "agent-44 must deny messaging.send" in errors
    assert "agent-44 must deny home.device_action" in errors
    assert "agent-44 must not have confirmable tools" in errors


def test_open_webui_home_agent_export_cli_writes_json(tmp_path: Path, capsys) -> None:
    module = _module()
    output = tmp_path / "agents.json"

    assert module.main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "open-webui-home-agents-import"
    assert written["ok"] is True
    assert written["validation_errors"] == []
    assert isinstance(written["generated_at_unix"], int)
    assert written["git_head"]
    assert written["records"][0]["base_model_id"].startswith("agent/")
