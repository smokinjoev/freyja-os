from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "export-open-webui-tools-openapi.py"


def _module():
    spec = importlib.util.spec_from_file_location("export_open_webui_tools_openapi", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_open_webui_tools_openapi_export_is_narrow_and_secret_free() -> None:
    module = _module()
    schema = module.build_schema()

    assert module.validate_schema(schema) == []
    assert set(schema["paths"]) == {"/open-webui-tools", "/open-webui-tools/invoke"}
    assert schema["x-freyja"]["secrets_included"] is False
    assert schema["x-freyja"]["private_content_included"] is False
    assert schema["x-freyja"]["boundary"] == "openapi"
    assert "ToolInvocationRequest" in schema["components"]["schemas"]
    assert "FREYJA_CONNECTOR_TOKEN=" not in json.dumps(schema)


def test_open_webui_tools_openapi_export_writes_report(tmp_path: Path, capsys) -> None:
    output = tmp_path / "openapi.json"

    assert _module().main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "open-webui-tools-openapi-export"
    assert isinstance(written["generated_at_unix"], int)
    assert written["git_head"]
    assert written["ok"] is True
