from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "audit-open-webui-home-agent-secret-safety.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_open_webui_home_agent_secret_safety", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_secret_safety_audit_scans_current_home_agent_artifacts() -> None:
    report = _module().build_report()

    assert report["secrets_included"] is False
    assert report["private_content_included"] is False
    assert report["ok"] is True
    assert report["artifact_count"] == 58
    assert report["missing_artifacts"] == []
    assert report["secret_pattern_findings"] == []
    assert report["json_flag_failures"] == []
    assert "certification/reports/open-webui-home-agent-readiness-summary.md" in _module().TEXT_ARTIFACTS


def test_secret_safety_text_scanner_detects_key_material(tmp_path: Path) -> None:
    path = tmp_path / "bad.txt"
    text = "-----BEGIN " + "PRIVATE KEY-----\nabc\n-----END " + "PRIVATE KEY-----\n"

    findings = _module()._scan_text(path, text)

    assert findings == [{"path": str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path), "kind": "private_key"}]


def test_secret_safety_audit_writes_report(tmp_path: Path, capsys) -> None:
    output = tmp_path / "secret-safety.json"

    assert _module().main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "open-webui-home-agent-secret-safety"
