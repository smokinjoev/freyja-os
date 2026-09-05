from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check-open-webui-tools-gateway.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_open_webui_tools_gateway", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tool_gateway_readiness_report_proves_fail_closed_policy() -> None:
    report = _module().build_report()

    assert report["ok"] is True
    assert isinstance(report["generated_at_unix"], int)
    assert report["timestamp_unix"] == report["generated_at_unix"]
    assert report["git_head"]
    assert report["secrets_included"] is False
    assert report["private_content_included"] is False
    assert report["operation_count"] == 20
    assert report["missing_operations"] == []
    assert report["destructive_default_all_deny"] is True
    assert report["live_side_effects_invoked"] is False
    assert report["execution_statuses"]["read_only"] == "dry_run_available"
    assert report["execution_statuses"]["pdf_analysis"] == "dry_run_available"
    assert report["execution_statuses"]["image_analysis"] == "dry_run_available"
    assert report["execution_statuses"]["confirmed_write"] == "confirmed_not_configured"
    assert "calendar.create" in report["confirmation_required"]
    assert "home.device_action" in report["confirmation_required"]
    assert "imessage.send.approved" in report["confirmation_required"]
    assert "shortcuts.run" in report["confirmation_required"]
    assert report["child_allowed_operations"] == [
        "image.analyze",
        "pdf.analyze",
        "recent-events",
        "search",
        "weather.read",
    ]
    assert report["checks"]["unknown_operation_denied"] is True
    assert report["checks"]["benedict_cannot_read_household_files"] is True
    assert report["checks"]["benedict_can_analyze_pdf"] is True
    assert report["checks"]["benedict_can_analyze_image"] is True
    assert report["checks"]["children_cannot_use_admin_tools"] is True
    assert report["checks"]["children_can_analyze_pdf"] is True
    assert report["checks"]["children_can_analyze_image"] is True
    assert report["checks"]["pdf_image_analysis_are_dry_run_only"] is True


def test_tool_gateway_readiness_writes_report(tmp_path: Path, capsys) -> None:
    output = tmp_path / "tools.json"

    assert _module().main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "open-webui-tools-gateway-readiness"
