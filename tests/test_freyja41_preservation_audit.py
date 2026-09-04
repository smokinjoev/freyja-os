from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "audit-freyja41-preservation.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_freyja41_preservation", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preservation_audit_marks_secret_free_and_tracks_baseline(monkeypatch) -> None:
    module = _module()

    def fake_command(args):
        if args[:2] == ["git", "rev-parse"]:
            return 0, "abc123"
        if args[:2] == ["docker", "ps"]:
            return (
                0,
                "\n".join(
                    [
                        "freyja-open-webui-atlas-open-webui-1\tUp 1 hour (healthy)",
                        "freyja-open-webui-atlas-model-proxy-1\tUp 1 hour",
                        "freyja3-agent-gateway-1\tUp 1 hour (healthy)",
                        "freyja3-litellm-1\tUp 1 hour (healthy)",
                        "freyja5-gateway-1\tUp 1 hour (healthy)",
                    ]
                ),
            )
        return 1, ""

    monkeypatch.setattr(module, "_command", fake_command)
    monkeypatch.setattr(
        module,
        "_endpoint_checks",
        lambda: [
            {"name": "freyja3_agent_gateway_health", "ok": True, "evidence": {"status": 200, "healthy": True}},
            {"name": "freyja3_litellm_health_auth_boundary", "ok": True, "evidence": {"status": 401, "auth_required": True}},
        ],
    )
    monkeypatch.setattr(module, "ROLLBACK_FILES", ["pyproject.toml"])

    report = module.build_report(now=1)

    assert report["secrets_included"] is False
    assert report["private_content_included"] is False
    assert report["baseline_tag"] == module.BASELINE_TAG
    assert report["ok"] is True
    assert report["pending"] == ["dedicated_freyja41_endpoint_contract"]
    endpoint_check = next(check for check in report["checks"] if check["name"] == "protected_legacy_endpoints_respond")
    assert endpoint_check["ok"] is True


def test_preservation_audit_fails_when_protected_service_missing(monkeypatch) -> None:
    module = _module()

    def fake_command(args):
        if args[:2] == ["git", "rev-parse"]:
            return 0, "abc123"
        if args[:2] == ["docker", "ps"]:
            return 0, "freyja-open-webui-atlas-open-webui-1\tUp 1 hour"
        return 1, ""

    monkeypatch.setattr(module, "_command", fake_command)
    monkeypatch.setattr(module, "_endpoint_checks", lambda: [])
    monkeypatch.setattr(module, "ROLLBACK_FILES", ["pyproject.toml"])

    report = module.build_report(now=1)

    assert report["ok"] is False
    check = next(check for check in report["checks"] if check["name"] == "protected_containers_running")
    assert check["ok"] is False


def test_preservation_audit_script_writes_report(tmp_path: Path, capsys, monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "ROLLBACK_FILES", ["pyproject.toml"])
    output = tmp_path / "freyja41.json"

    assert module.main(["--output", str(output)]) in {0, 1}

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "freyja41-preservation-audit"
