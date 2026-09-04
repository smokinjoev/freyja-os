from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "audit-open-webui-inference-policy.py"


def _module():
    spec = importlib.util.spec_from_file_location("audit_open_webui_inference_policy", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inference_policy_audit_is_secret_free_and_complete() -> None:
    audit = _module().build_audit()

    assert audit["secrets_included"] is False
    assert audit["private_content_included"] is False
    assert isinstance(audit["generated_at_unix"], int)
    assert audit["git_head"]
    assert audit["ok"] is True
    checks = {check["name"]: check for check in audit["checks"]}
    assert checks["open_webui_uses_model_proxy"]["ok"] is True
    assert checks["model_profiles_complete"]["ok"] is True
    assert checks["model_profiles_local_only"]["ok"] is True
    assert checks["unloads_other_primary_models"]["ok"] is True
    assert checks["cloud_fallback_disabled_for_open_webui_path"]["ok"] is True


def test_inference_policy_audit_lists_required_model_profiles() -> None:
    profiles = _module().build_audit()["model_profiles"]

    assert set(profiles) == {"coding", "fast_chat", "strong_reasoning", "vision_documents"}
    assert profiles["coding"] == "qwen3-coder-next:q4_K_M"
    assert profiles["vision_documents"] == "qwen2.5vl:72b"


def test_inference_policy_audit_writes_report(tmp_path: Path, capsys) -> None:
    output = tmp_path / "inference.json"

    assert _module().main(["--output", str(output)]) == 0

    written = json.loads(output.read_text(encoding="utf-8"))
    printed = json.loads(capsys.readouterr().out)
    assert written == printed
    assert written["report_type"] == "open-webui-inference-policy-audit"
    assert isinstance(written["generated_at_unix"], int)
    assert written["git_head"]
