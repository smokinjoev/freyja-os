from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify-freyja-channels-atlas-deployment.py"


def _module():
    spec = importlib.util.spec_from_file_location("verify_freyja_channels_atlas_deployment", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_atlas_channel_deployment_verifier_reports_secret_free_ready_artifacts(monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_compose_config_ok", lambda: True)

    report = module.verify()

    assert report["secrets_included"] is False
    assert report["private_content_included"] is False
    assert report["ok"] is True
    assert report["checks"]["required_services_present"] is True
    assert report["checks"]["no_published_ports"] is True
    assert report["checks"]["open_webui_key_file_secret"] is True
    assert report["checks"]["state_bind_mount_configured"] is True
    assert report["checks"]["signal_private_network_configured"] is True
    assert report["checks"]["telegram_not_on_signal_private_network"] is True
    assert report["checks"]["telegram_timeout_env_passthrough"] is True
    assert report["checks"]["signal_on_signal_private_network"] is True
    assert report["checks"]["atlas_readiness_open_webui_key_file_ok"] is True
    assert report["artifacts"]["compose"] == "deploy/compose/freyja-channels/compose.yaml"
    assert report["artifacts"]["atlas_readiness"] == "certification/reports/freyja-channels-readiness-atlas.json"


def test_atlas_channel_deployment_verifier_writes_report(tmp_path: Path, capsys, monkeypatch) -> None:
    module = _module()
    monkeypatch.setattr(module, "_compose_config_ok", lambda: True)
    output = tmp_path / "atlas-channels.json"

    assert module.main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "freyja-channels-atlas-deployment"


def test_atlas_channel_deployment_verifier_rejects_non_secret_free_readiness(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"secrets_included": True}), encoding="utf-8")

    with pytest.raises(ValueError, match="secret-free"):
        _module().verify(bad)
