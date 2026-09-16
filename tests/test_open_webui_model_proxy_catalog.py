from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check-open-webui-model-proxy-catalog.py"


def _module():
    spec = importlib.util.spec_from_file_location("check_open_webui_model_proxy_catalog", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_model_proxy_catalog_report_tracks_agent_models() -> None:
    module = _module()
    report = module.build_report(sorted(module.EXPECTED_AGENT_MODELS | {"qwen3.8:27b", "qwen3:30b-a3b"}))

    assert report["ok"] is True
    assert report["secrets_included"] is False
    assert report["private_content_included"] is False
    assert isinstance(report["generated_at_unix"], int)
    assert report["timestamp_unix"] == report["generated_at_unix"]
    assert report["git_head"]
    assert report["agent_models_missing"] == []
    assert report["agent_profiles_missing"] == []
    assert report["agent_profiles_non_local"] == []
    assert report["agent_profile_map"]["agent/freyja"]["model_profile"] == "strong_reasoning"
    assert report["agent_profile_map"]["agent/freyja"]["provider"] == "vulcan_ollama"
    assert report["agent_profile_map"]["agent/freyja"]["keep_local"] is True
    assert report["agent_profile_map"]["agent/benedict-paralegal"]["agent_id"] == "benedict-paralegal"
    assert report["model_count"] == 9


def test_model_proxy_catalog_report_fails_when_agent_missing() -> None:
    module = _module()
    report = module.build_report(["agent/freyja"])

    assert report["ok"] is False
    assert "agent/benedict" in report["agent_models_missing"]


def test_model_proxy_catalog_report_fails_when_manifest_profile_is_not_local() -> None:
    module = _module()
    manifest = module.load_manifest()
    manifest["model_profiles"]["strong_reasoning"] = {
        **manifest["model_profiles"]["strong_reasoning"],
        "provider": "cloud",
    }

    report = module.build_report(sorted(module.EXPECTED_AGENT_MODELS), manifest=manifest)

    assert report["ok"] is False
    assert "agent/freyja" in report["agent_profiles_non_local"]
    assert "agent/benedict" in report["agent_profiles_non_local"]


def test_model_proxy_catalog_main_writes_report(tmp_path: Path, monkeypatch, capsys) -> None:
    module = _module()
    output = tmp_path / "catalog.json"
    monkeypatch.setattr(module, "fetch_model_ids", lambda url, timeout: (sorted(module.EXPECTED_AGENT_MODELS), 200, None))

    assert module.main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "open-webui-model-proxy-catalog"


def test_model_proxy_catalog_main_falls_back_to_container_probe(tmp_path: Path, monkeypatch, capsys) -> None:
    module = _module()
    output = tmp_path / "catalog.json"
    monkeypatch.setattr(module, "fetch_model_ids", lambda url, timeout: ([], 401, None))
    monkeypatch.setattr(module, "fetch_model_ids_from_container", lambda container, url, timeout: (sorted(module.EXPECTED_AGENT_MODELS), 200, None))

    assert module.main(["--output", str(output)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert json.loads(output.read_text(encoding="utf-8")) == report
    assert report["probe"] == "container"
    assert report["container"] == module.DEFAULT_CONTAINER
    assert report["agent_models_missing"] == []
