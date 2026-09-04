from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "audit-open-webui-home-agent-completion.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_open_webui_home_agent_completion", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_completion_audit_reports_expected_current_gate_statuses() -> None:
    audit = _module().build_audit()

    assert audit["secrets_included"] is False
    assert audit["private_content_included"] is False
    assert audit["complete"] is False
    assert audit["status_counts"]["complete"] >= 5
    assert audit["status_counts"]["auth_gated"] >= 3
    assert audit["status_counts"]["credential_gated"] >= 1
    ids = [item["requirement_id"] for item in audit["items"]]
    assert len(ids) == len(set(ids))
    assert {"five_agents", "memory_layers", "tools"}.issubset(
        {item["requirement_id"] for item in audit["items"] if item["status"] == "auth_gated"}
    )
    assert {"messaging_channels"} == {item["requirement_id"] for item in audit["items"] if item["status"] == "credential_gated"}
    statuses = {item["requirement"]: item["status"] for item in audit["items"]}
    assert statuses["Inspect repository, running services, Docker stacks, endpoints, credentials locations, and Open WebUI config"] == "complete"
    assert statuses["Identify Open WebUI host and Vulcan path"] == "complete"
    assert statuses["Keep inference local by default and connect Open WebUI to Vulcan"] == "partial"
    assert statuses["Create/import five Open WebUI agents"] == "auth_gated"
    assert statuses["Implement deterministic Telegram/Signal channel gateway with WhatsApp disabled"] == "credential_gated"
    assert statuses["Add proactive behavior disabled by default"] == "complete"
    assert statuses["Preserve Freyja 4.1 fallback"] == "complete"


def test_completion_audit_writes_report(tmp_path: Path, capsys) -> None:
    output = tmp_path / "completion.json"

    assert _module().main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "open-webui-home-agent-completion-audit"


def test_completion_audit_loader_rejects_reports_not_marked_secret_free(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"secrets_included": True}), encoding="utf-8")

    with pytest.raises(ValueError, match="secret-free"):
        _module()._load(bad)
