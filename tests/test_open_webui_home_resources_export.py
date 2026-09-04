from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "export-open-webui-home-resources.py"


def _module():
    spec = importlib.util.spec_from_file_location("export_open_webui_home_resources", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_home_resources_export_validates_policy() -> None:
    module = _module()
    payload = module.build_export()

    assert module.validate_export(payload) == []
    assert payload["secrets_included"] is False
    assert payload["private_content_included"] is False
    assert payload["native_memory"]["mode"] == "per_user"
    assert payload["native_memory"]["policy"]["cross_user_reads"] == "forbidden"


def test_benedict_restricted_knowledge_is_isolated() -> None:
    payload = _module().build_export()
    knowledge = {item["id"]: item for item in payload["knowledge"]}
    benedict = knowledge["benedict_restricted"]["meta"]["freyja"]

    assert benedict["allowed_agents"] == ["benedict"]
    assert set(benedict["excluded_agents"]) == {"freyja", "cloyd", "agent-44", "jenna"}
    assert benedict["scope"] == "restricted:benedict"
    assert benedict["sensitivity"] == "restricted"
    assert benedict["seed_policy"]["cloud_sync"] == "forbidden"


def test_tool_boundaries_are_narrow_and_children_are_not_admins() -> None:
    payload = _module().build_export()
    tools = {item["id"]: item for item in payload["tools"]}

    assert tools["iris_apple"]["boundary"] == "mcp"
    assert tools["iris_apple"]["meta"]["freyja"]["host"] == "iris"
    assert tools["iris_apple"]["meta"]["freyja"]["children_allowed_operations"] == []
    assert tools["home_assistant"]["meta"]["freyja"]["confirmation_required"] == ["home.device_action"]
    assert tools["home_assistant"]["meta"]["freyja"]["openapi_schema_report"] == "certification/reports/open-webui-tools-openapi.json"
    assert tools["infrastructure_health"]["meta"]["freyja"]["children_allowed_operations"] == []
    assert all(tool["meta"]["freyja"]["destructive_default"] == "deny" for tool in tools.values())


def test_exporter_writes_reviewable_payload(tmp_path: Path, capsys) -> None:
    output = tmp_path / "resources.json"
    assert _module().main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["ok"] is True
    assert len(written["knowledge"]) == 3
    assert len(written["tools"]) == 6
